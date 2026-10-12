# bot.py
import os
import json
import random
from datetime import datetime
from typing import Any, Optional, Dict, List
from flask import Flask, request, abort, jsonify
from telebot import TeleBot, types
from telebot.types import BotCommand
from deep_translator import GoogleTranslator
from dotenv import load_dotenv
import requests

# ---------------- Environment ----------------
load_dotenv()
TOKEN = os.getenv("TOKEN")
PUBLIC_URL_PATH = "/etc/secrets/PUBLIC_URL"
QUIZ_SECRET = os.getenv("QUIZ_SECRET", "")  # secret for /trigger_quiz

if os.path.exists(PUBLIC_URL_PATH):
    with open(PUBLIC_URL_PATH, "r") as f:
        PUBLIC_URL = f.read().strip()
else:
    PUBLIC_URL = os.getenv("PUBLIC_URL", "")

if not TOKEN:
    raise RuntimeError("TOKEN is required in .env")
if not PUBLIC_URL:
    print("Warning: PUBLIC_URL not set. Webhook may not work automatically. Set PUBLIC_URL env var on Render.")

BOT_NAME = "Vocabulary with Mr. Korsh"
print("Bot Name:", BOT_NAME)
print("Public URL:", PUBLIC_URL)

# ---------------- File paths ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
WORDS_FILE = os.path.join(DATA_DIR, "words.json")
PHRASES_FILE = os.path.join(DATA_DIR, "phrases.json")
TRACK_FILE = os.path.join(BASE_DIR, "tracking.json")

# Known parts of speech for quiz options
KNOWN_POS = ["noun", "verb", "adjective", "adverb"]

# ---------------- Helpers ----------------
def load_json(file_path: str) -> Any:
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load JSON {file_path}: {e}")
    return {}

def save_json(file_path: str, data: Any):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[ERROR] Failed to save JSON {file_path}: {e}")

# ---------------- Tracking ----------------
def load_tracking() -> Dict:
    data = load_json(TRACK_FILE)
    if not isinstance(data, dict):
        data = {}
    if "users" not in data:
        data["users"] = {}
    # global mapping of active polls to user
    if "active_polls" not in data:
        data["active_polls"] = {}
    return data

def save_tracking(data: Dict):
    save_json(TRACK_FILE, data)

# ---------------- User Tracking ----------------
# Required keys for every user record
_USER_DEFAULTS = {
    "username": "",
    "first_name": "",
    "usage_count": 0,
    "history": [],
    "last_quiz_date": "",
    "daily_quiz_count": 0,
    "current_quiz": None,
    "results": [],
}

def ensure_user_record(user_id: int, username: str = "", first_name: str = ""):
    """
    Create or patch a user record so all required keys exist.
    Existing users missing 'current_quiz', 'results', etc. are backfilled.
    """
    data = load_tracking()
    users = data["users"]
    sid = str(user_id)
    if sid not in users:
        users[sid] = {
            "username": username or "",
            "first_name": first_name or "",
            "usage_count": 0,
            "history": [],
            "last_quiz_date": "",
            "daily_quiz_count": 0,
            "current_quiz": None,
            "results": [],
        }
    else:
        # Backfill any missing keys for existing users
        for key, default in _USER_DEFAULTS.items():
            if key not in users[sid]:
                users[sid][key] = default
        # Update identity fields if provided
        if username:
            users[sid]["username"] = username
        if first_name:
            users[sid]["first_name"] = first_name
    data["users"] = users
    save_tracking(data)

def track_user(user_id: int, username: str = "", first_name: str = ""):
    ensure_user_record(user_id, username, first_name)

def increment_usage_count(user_id: int, item: Optional[str] = None):
    data = load_tracking()
    sid = str(user_id)
    if sid in data["users"]:
        data["users"][sid]["usage_count"] = data["users"][sid].get("usage_count", 0) + 1
        if item:
            data["users"][sid].setdefault("history", []).append(item)
        save_tracking(data)

# ---------------- Translation ----------------
def detect_uzbek(text: str) -> bool:
    if not text:
        return False
    for ch in text:
        if "\u0400" <= ch <= "\u04FF":
            return True
    lower = text.lower()
    uz_tokens = {"men", "sen", "biz", "siz", "ular", "va", "yoq", "yo'q",
                 "kitob", "rahmat", "salom", "yaxshi", "bor", "yo'qlik",
                 "qanday", "iltimos", "olma", "ot", "it", "bolalar"}
    for tok in lower.split():
        if tok.strip(".,!?;:") in uz_tokens:
            return True
    return False

def translate_dynamic(text: str):
    if not text.strip():
        return None, "unknown", "unknown"
    is_uz = detect_uzbek(text)
    try:
        if is_uz:
            return GoogleTranslator(source="uz", target="en").translate(text), "uz", "en"
        else:
            return GoogleTranslator(source="auto", target="uz").translate(text), "auto", "uz"
    except Exception as e:
        print("Translation error:", e)
        return None, ("uz" if is_uz else "auto"), ("en" if is_uz else "uz")

# ---------------- Word lookup ----------------
def load_words() -> Dict:
    """Load words from data/words.json, falling back to GitHub raw if empty."""
    words = load_json(WORDS_FILE)
    if not words:
        url = "https://raw.githubusercontent.com/abutolibrashidov/Vocabulary-bot/main/words.json"
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                fetched = r.json()
                if isinstance(fetched, dict):
                    words = fetched
        except Exception as e:
            print("Failed to load words from GitHub:", e)
    return words if isinstance(words, dict) else {}

def find_word_info(word: str) -> Optional[dict]:
    words = load_words()
    for key, value in words.items():
        if key.lower() == word.lower() and isinstance(value, dict):
            return value
    return None

# ---------------- Dynamic Fetch & Cache ----------------
def fetch_and_store_word(word: str) -> Optional[dict]:
    """
    Query the Free Dictionary API for `word`. If found:
    - Translate the word and its first definition to Uzbek
    - Build an entry matching the words.json schema
    - Persist it to data/words.json
    Returns the new entry dict, or None on failure.
    """
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.lower()}"
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        api_data = resp.json()
        if not isinstance(api_data, list) or not api_data:
            return None
    except Exception as e:
        print(f"[fetch_and_store_word] API error for '{word}': {e}")
        return None

    entry = api_data[0]
    meanings = entry.get("meanings", [])
    if not meanings:
        return None

    first_meaning = meanings[0]
    part_of_speech = first_meaning.get("partOfSpeech", "unknown")
    definitions = first_meaning.get("definitions", [])
    definition_text = definitions[0].get("definition", "") if definitions else ""
    example_text = definitions[0].get("example", "") if definitions else ""

    # Synonyms from meaning or top-level
    synonyms = first_meaning.get("synonyms", [])
    if not synonyms and definitions:
        synonyms = definitions[0].get("synonyms", [])

    # Translate word to Uzbek
    try:
        translation = GoogleTranslator(source="en", target="uz").translate(word)
    except Exception:
        translation = word

    # Translate definition to Uzbek (for display, optional enrichment)
    # We store it as part of examples in Uzbek context but keep English examples
    examples_en = [example_text] if example_text else []

    # Build entry
    new_entry = {
        "translation": translation or word,
        "part_of_speech": part_of_speech,
        "level": "B1",  # default – API doesn't provide CEFR level
        "prefixes": [],
        "suffixes": [],
        "singular_plural": "N/A",
        "examples": examples_en,
        "synonyms": synonyms[:4] if synonyms else [],
    }

    # Persist to data/words.json
    words = load_words()
    words[word.lower()] = new_entry
    save_json(WORDS_FILE, words)
    print(f"[fetch_and_store_word] Cached new word: '{word}'")
    return new_entry

def format_word_response(word: str, translation: str, info: Optional[dict] = None) -> str:
    response = f"📝 Word: *{word}*\n🔤 Translation: *{translation}*\n"
    if info:
        if info.get("part_of_speech"):
            response += f"📚 Part of Speech: {info['part_of_speech']}\n"
        if info.get("level"):
            response += f"⭐ Level: {info['level']}\n"
        if info.get("prefixes"):
            response += f"➕ Prefixes: {', '.join(info['prefixes'])}\n"
        if info.get("suffixes"):
            response += f"➖ Suffixes: {', '.join(info['suffixes'])}\n"
        if info.get("singular_plural"):
            response += f"👤 Singular/Plural: {info['singular_plural']}\n"
        if info.get("examples"):
            response += "📖 Examples:\n"
            for ex in info['examples']:
                response += f" - {ex}\n"
        if info.get("synonyms"):
            response += f"💡 Synonyms: {', '.join(info['synonyms'])}\n"
    return response.strip()

# ---------------- Bot Setup ----------------
bot = TeleBot(TOKEN, parse_mode="Markdown")

# Expose commands - makes them visible in desktop clients
try:
    commands = [BotCommand("start", "Start the bot"), BotCommand("quiz", "Take a quiz")]
    bot.set_my_commands(commands)
except Exception as e:
    print("Warning: could not set bot commands:", e)

def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🌐 Translate a Word", "🗣 Learn a Phrase")
    markup.row("🎯 Take a Quiz")
    return markup

# ---------------- Commands ----------------
@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    track_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "")
    bot.send_message(
        message.chat.id,
        f"Hello {message.from_user.first_name}! 👋\nWelcome to *{BOT_NAME}*!",
        reply_markup=get_main_menu()
    )

@bot.message_handler(commands=["quiz"])
def cmd_quiz(message: types.Message):
    user_id = message.from_user.id
    send_quiz_to_user(user_id)

# ---------------- Message Handling ----------------
@bot.message_handler(func=lambda msg: True)
def main_handler(message: types.Message):
    text = (message.text or "").strip()
    user_id = getattr(message.from_user, "id", None)
    track_user(user_id, message.from_user.username or "", message.from_user.first_name or "")

    if text == "🌐 Translate a Word":
        msg = bot.send_message(message.chat.id, "Please enter the word to translate (English or Uzbek):")
        bot.register_next_step_handler(msg, translate_word)
    elif text == "🗣 Learn a Phrase":
        phrases = load_json(PHRASES_FILE)
        if not phrases:
            bot.send_message(message.chat.id, "No phrase topics found.")
            return
        markup = types.InlineKeyboardMarkup()
        for key in phrases.keys():
            markup.add(types.InlineKeyboardButton(key, callback_data=f"phrase:{key}"))
        bot.send_message(message.chat.id, "Select a phrase topic:", reply_markup=markup)
    elif text == "🎯 Take a Quiz":
        if user_id:
            send_quiz_to_user(user_id)
    else:
        translate_word(message)

def translate_word(message: types.Message):
    word = (message.text or "").strip()
    if not word:
        bot.send_message(message.chat.id, "Please enter a word.", reply_markup=get_main_menu())
        return

    # 1. Check local dictionary first
    info = find_word_info(word)
    if info:
        translation = info.get("translation", word)
        response = format_word_response(word, translation, info)
    else:
        # 2. Try Free Dictionary API + auto-cache (English words only)
        fetched = None
        if not detect_uzbek(word):
            fetched = fetch_and_store_word(word)

        if fetched:
            translation = fetched.get("translation", word)
            response = format_word_response(word, translation, fetched)
            response += "\n\n_✨ Fetched and saved to dictionary!_"
        else:
            # 3. Fall back to plain translation
            translation, _, _ = translate_dynamic(word)
            if not translation:
                translation = word
            response = f"📝 Word: *{word}*\n🔤 Translation: *{translation}*"

    increment_usage_count(message.from_user.id, word)
    bot.send_message(message.chat.id, response, reply_markup=get_main_menu())

    # Check automatic quiz
    send_quiz_if_allowed(message.from_user.id)

# ---------------- Phrase Learning ----------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("phrase:"))
def phrase_callback(call: types.CallbackQuery):
    topic = call.data.split(":", 1)[1]
    phrases = load_json(PHRASES_FILE)
    if topic in phrases:
        phrase_list = phrases[topic]
        if not phrase_list:
            bot.answer_callback_query(call.id, "No phrases in this topic.")
            return
        item = random.choice(phrase_list)
        # Support both plain-string and {"phrase": ..., "meaning": ...} formats
        if isinstance(item, dict):
            phrase_text = item.get("phrase", "")
            meaning_text = item.get("meaning", "")
            display = f"👉 *{phrase_text}*\n💡 _{meaning_text}_"
        else:
            display = f"👉 {item}"
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"🗣 Phrase from *{topic}*:\n\n{display}")
        increment_usage_count(call.from_user.id, f"phrase:{topic}")
        send_quiz_if_allowed(call.from_user.id)
    else:
        bot.answer_callback_query(call.id, "Topic not found.")

# ---------------- Quiz System (POLL-based) ----------------
def send_quiz_if_allowed(user_id: int):
    ensure_user_record(user_id)
    data = load_tracking()
    user = data["users"].get(str(user_id))
    if not user:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    if user.get("last_quiz_date") != today:
        user["daily_quiz_count"] = 0
        user["last_quiz_date"] = today

    if user.get("daily_quiz_count", 0) < 2:
        user["daily_quiz_count"] = user.get("daily_quiz_count", 0) + 1
        data["users"][str(user_id)] = user
        save_tracking(data)
        send_quiz_to_user(user_id)

def _safe_phrase_text(item) -> str:
    """Extract a plain string from a phrase item (dict or str)."""
    if isinstance(item, dict):
        return item.get("phrase", str(item))
    return str(item)

def build_quiz_questions() -> List[Dict]:
    """
    Build a small quiz (3 questions) from local data.
    Handles:
    - Missing/malformed words or phrases gracefully
    - part_of_speech values outside the known list
    - phrase items as dicts {"phrase": ..., "meaning": ...}
    """
    questions = []
    words = load_words()
    phrases = load_json(PHRASES_FILE)

    # --- Word translation question ---
    valid_words = {k: v for k, v in words.items() if isinstance(v, dict) and v.get("translation")}
    if valid_words:
        word, info = random.choice(list(valid_words.items()))
        correct = info["translation"]
        all_trans = [
            v["translation"] for k, v in valid_words.items()
            if k != word and isinstance(v, dict) and v.get("translation") and v["translation"] != correct
        ]
        options = [correct] + random.sample(all_trans, min(3, len(all_trans)))
        options = list(dict.fromkeys(options))[:4]  # unique, max 4
        while len(options) < 4:
            options.append("—")
        random.shuffle(options)
        correct_index = options.index(correct) if correct in options else 0
        questions.append({
            "type": "word_translation",
            "prompt": f"Translate this word: *{word}*",
            "options": options,
            "correct_index": correct_index,
        })

    # --- Part of speech question ---
    if valid_words:
        # Pick a word whose POS is in our known list for a fair question
        pos_words = {k: v for k, v in valid_words.items() if v.get("part_of_speech") in KNOWN_POS}
        pool = pos_words if pos_words else valid_words
        word, info = random.choice(list(pool.items()))
        correct_pos = info.get("part_of_speech", "noun")
        options = KNOWN_POS.copy()
        # If the word's POS isn't in options, replace a random option
        if correct_pos not in options:
            options[random.randint(0, 3)] = correct_pos
        random.shuffle(options)
        correct_index = options.index(correct_pos) if correct_pos in options else 0
        questions.append({
            "type": "word_pos",
            "prompt": f"What is the part of speech of *{word}*?",
            "options": options,
            "correct_index": correct_index,
        })

    # --- Phrase recognition question ---
    if phrases:
        # Collect topics that have at least one item
        valid_topics = [t for t, lst in phrases.items() if isinstance(lst, list) and lst]
        if valid_topics:
            topic = random.choice(valid_topics)
            phrase_item = random.choice(phrases[topic])
            phrase = _safe_phrase_text(phrase_item)

            # Distractors: other phrases from other topics
            all_other_phrases = [
                _safe_phrase_text(p)
                for t, plist in phrases.items()
                if t != topic and isinstance(plist, list)
                for p in plist
                if _safe_phrase_text(p) != phrase
            ]
            options = [phrase] + random.sample(all_other_phrases, min(3, len(all_other_phrases)))
            options = list(dict.fromkeys(options))[:4]
            while len(options) < 4:
                options.append("—")
            random.shuffle(options)
            correct_index = options.index(phrase) if phrase in options else 0
            questions.append({
                "type": "phrase_match",
                "prompt": f"Which phrase belongs to topic *{topic}*?",
                "options": options,
                "correct_index": correct_index,
            })

    return questions

def send_quiz_to_user(user_id: int):
    """
    Create a quiz (list of poll questions) and send the first poll.
    Stores the quiz state in tracking.json under the user's 'current_quiz'.
    """
    ensure_user_record(user_id)
    words = load_words()
    phrases = load_json(PHRASES_FILE)
    if not words and not phrases:
        bot.send_message(user_id, "No words or phrases available for quiz.")
        return

    questions = build_quiz_questions()
    if not questions:
        bot.send_message(user_id, "Could not build a quiz right now. Try later.")
        return

    # Write quiz state atomically in one load+save
    data = load_tracking()
    sid = str(user_id)
    if sid not in data["users"]:
        data["users"][sid] = {k: v for k, v in _USER_DEFAULTS.items()}
    data["users"][sid]["current_quiz"] = {"questions": questions, "index": 0, "results": []}
    save_tracking(data)

    increment_usage_count(user_id, "quiz_sent")
    _send_quiz_poll(user_id)

def _send_quiz_poll(user_id: int):
    """
    Send the next poll for the user's current quiz.
    Loads tracking once, updates active_polls, saves once — no double-load race.
    """
    data = load_tracking()
    sid = str(user_id)
    user_data = data["users"].get(sid, {})
    quiz = user_data.get("current_quiz")
    if not quiz:
        bot.send_message(user_id, "No active quiz. Start one with 🎯 Take a Quiz.")
        return

    idx = quiz.get("index", 0)
    questions = quiz.get("questions", [])

    if idx >= len(questions):
        # Quiz finished — send summary then clean up
        results = quiz.get("results", [])
        correct_count = sum(1 for r in results if r.get("correct"))
        total = len(results)
        bot.send_message(user_id, "✅ Quiz finished! Great job!", reply_markup=get_main_menu())
        bot.send_message(user_id, f"📊 Score: *{correct_count}/{total}* correct.")
        data["users"][sid].pop("current_quiz", None)
        save_tracking(data)
        return

    q = questions[idx]
    question_text = q["prompt"][:300]  # Telegram poll question limit: 300 chars
    options = q["options"]
    correct_index = q["correct_index"]

    try:
        msg = bot.send_poll(
            chat_id=user_id,
            question=question_text,
            options=options,
            type="quiz",
            correct_option_id=correct_index,
            is_anonymous=False,
        )
        # Store active poll mapping in the SAME data dict (no second load)
        poll_id = msg.poll.id
        data["active_polls"][poll_id] = {"user": sid}
        save_tracking(data)
    except Exception as e:
        print("Failed to send poll:", e)
        bot.send_message(user_id, "Failed to send quiz poll. Try again later.")

# ---------------- Poll Answer Handler ----------------
@bot.poll_answer_handler(func=lambda x: True)
def handle_poll_answer(poll_answer: types.PollAnswer):
    """
    Called when a user answers a quiz poll.
    Looks up the poll in active_polls, evaluates the answer,
    sends feedback, advances the index, and sends the next poll.
    """
    poll_id = poll_answer.poll_id
    user_id = getattr(poll_answer.user, "id", None)
    if not user_id:
        return

    data = load_tracking()
    mapping = data.get("active_polls", {}).get(poll_id)
    if not mapping:
        # Poll not from this bot session (old or unknown)
        return

    sid = mapping.get("user")
    if sid != str(user_id):
        # Poll belongs to a different user
        return

    # Get user's quiz state
    user_record = data["users"].get(sid)
    if not user_record:
        return
    quiz = user_record.get("current_quiz")
    if not quiz:
        return

    qidx = quiz.get("index", 0)
    questions = quiz.get("questions", [])
    if qidx >= len(questions):
        return

    q = questions[qidx]
    chosen = poll_answer.option_ids[0] if poll_answer.option_ids else None
    is_correct = (chosen == q.get("correct_index"))

    # Record result
    quiz.setdefault("results", []).append({
        "type": q.get("type"),
        "prompt": q.get("prompt"),
        "chosen_index": chosen,
        "correct_index": q.get("correct_index"),
        "correct": is_correct,
    })

    # Send feedback
    if is_correct:
        bot.send_message(user_id, "✅ Correct! 🎉")
    else:
        corr_idx = q.get("correct_index")
        opts = q.get("options", [])
        correct_text = opts[corr_idx] if (corr_idx is not None and 0 <= corr_idx < len(opts)) else "N/A"
        bot.send_message(user_id, f"❌ Wrong — correct answer: *{correct_text}*")

    # Advance index and persist
    quiz["index"] = qidx + 1
    data["users"][sid]["current_quiz"] = quiz
    # Remove this poll from active mapping
    data["active_polls"].pop(poll_id, None)
    save_tracking(data)

    # Send next poll
    _send_quiz_poll(int(sid))

# ---------------- Flask Webhook & Trigger ----------------
app = Flask(__name__)
WEBHOOK_PATH = f"/webhook/{TOKEN}"

@app.route("/", methods=["GET"])
def index():
    return f"{BOT_NAME} is running."

@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    if request.headers.get("content-type") != "application/json":
        abort(403)
    json_str = request.get_data().decode("utf-8")
    try:
        update = types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        print("Failed to process update:", e)
    return "", 200

# Endpoint for external scheduler (GitHub Actions) to trigger quizzes.
# POST /trigger_quiz with JSON: {"secret": "<QUIZ_SECRET>", "user_id": optional}
@app.route("/trigger_quiz", methods=["POST"])
def trigger_quiz():
    if not QUIZ_SECRET:
        return jsonify({"error": "QUIZ_SECRET not configured on server."}), 500
    payload = request.get_json(force=True, silent=True) or {}
    if payload.get("secret") != QUIZ_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    target = payload.get("user_id")
    if target:
        try:
            uid = int(target)
            send_quiz_to_user(uid)
            return jsonify({"status": "ok", "sent_to": uid}), 200
        except Exception:
            return jsonify({"error": "invalid user_id"}), 400

    # Send to all users in tracking (respect daily quota)
    tdata = load_tracking()
    users = tdata.get("users", {})
    sent = []
    for sid, u in users.items():
        try:
            uid = int(sid)
            send_quiz_if_allowed(uid)
            sent.append(uid)
        except Exception:
            continue
    return jsonify({"status": "ok", "sent_count": len(sent)}), 200

def set_webhook():
    if not PUBLIC_URL:
        print("PUBLIC_URL not set; skipping webhook.")
        return
    url = f"{PUBLIC_URL.rstrip('/')}{WEBHOOK_PATH}"
    try:
        bot.remove_webhook()
        result = bot.set_webhook(url=url)
        if result:
            print("✅ Webhook successfully set to", url)
        else:
            print("❌ Failed to set webhook. Telegram rejected the URL:", url)
    except Exception as e:
        print("❌ Exception while setting webhook:", e)

# ---------------- Start ----------------
if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
