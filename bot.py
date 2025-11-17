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

# Ensure tracking file structure
def load_tracking() -> Dict:
    data = load_json(TRACK_FILE)
    if not isinstance(data, dict):
        data = {}
    if "users" not in data:
        data["users"] = {}
    # global mapping of active polls to user
    if "active_polls" not in data:
        data["active_polls"] = {}
    save_json(TRACK_FILE, data)
    return data

# ---------------- User Tracking ----------------
def ensure_user_record(user_id: int, username: str = "", first_name: str = ""):
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
            "current_quiz": None  # {"questions": [...], "index": 0}
        }
        data["users"] = users
        save_json(TRACK_FILE, data)

def track_user(user_id: int, username: str = "", first_name: str = ""):
    ensure_user_record(user_id, username, first_name)

def increment_usage_count(user_id: int, item: Optional[str] = None):
    data = load_tracking()
    sid = str(user_id)
    if sid in data["users"]:
        data["users"][sid]["usage_count"] = data["users"][sid].get("usage_count", 0) + 1
        if item:
            data["users"][sid].setdefault("history", []).append(item)
        save_json(TRACK_FILE, data)

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
def load_words():
    words = load_json(WORDS_FILE)
    if not words:
        url = "https://raw.githubusercontent.com/abutolibrashidov/Vocabulary-bot/main/words.json"
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                words = r.json()
        except Exception as e:
            print("Failed to load words from GitHub:", e)
    return words if isinstance(words, dict) else {}

def find_word_info(word: str) -> Optional[dict]:
    words = load_words()
    for key, value in words.items():
        if key.lower() == word.lower():
            return value
    return None

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
    info = find_word_info(word)
    if info:
        translation = info.get("translation", word)
        response = format_word_response(word, translation, info)
    else:
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
        phrase = random.choice(phrases[topic])
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"🗣 Phrase from *{topic}*:\n\n👉 {phrase}")
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
        save_json(TRACK_FILE, data)
        send_quiz_to_user(user_id)

def build_quiz_questions() -> List[Dict]:
    """
    Build a small quiz (3 questions) from your data.
    Uses:
      - word translation (requires 'translation' in words.json)
      - part_of_speech from words.json
      - phrase recognition (asks 'which phrase belongs to X topic' with distractors)
    """
    questions = []
    words = load_words()
    phrases = load_json(PHRASES_FILE)

    # Word translation question
    if words:
        word, info = random.choice(list(words.items()))
        correct = info.get("translation", word)
        all_trans = [v.get("translation", k) for k, v in words.items() if k != word and isinstance(v, dict)]
        options = [correct] + (random.sample(all_trans, min(3, len(all_trans))) if all_trans else [])
        options = list(dict.fromkeys(options))[:4]  # unique, max 4
        while len(options) < 4:
            options.append(str(random.choice(list(words.keys()))))
        random.shuffle(options)
        questions.append({
            "type": "word_translation",
            "prompt": f"Translate this word: *{word}*",
            "options": options,
            "correct_index": options.index(correct) if correct in options else 0
        })

    # Part of speech question
    if words:
        word, info = random.choice(list(words.items()))
        correct = info.get("part_of_speech", "noun")
        all_pos = ["noun", "verb", "adjective", "adverb"]
        options = all_pos.copy()
        random.shuffle(options)
        questions.append({
            "type": "word_pos",
            "prompt": f"What is the part of speech of *{word}*?",
            "options": options,
            "correct_index": options.index(correct) if correct in options else 0
        })

    # Phrase recognition question
    if phrases:
        topic = random.choice(list(phrases.keys()))
        phrase = random.choice(phrases[topic])
        # build distractors from other phrases
        all_phrases = [p for plist in phrases.values() for p in plist if p != phrase]
        options = [phrase] + (random.sample(all_phrases, min(3, len(all_phrases))) if all_phrases else [])
        options = list(dict.fromkeys(options))[:4]
        while len(options) < 4:
            options.append("—")
        random.shuffle(options)
        questions.append({
            "type": "phrase_match",
            "prompt": f"Which phrase belongs to topic *{topic}*?",
            "options": options,
            "correct_index": options.index(phrase)
        })

    return questions

def send_quiz_to_user(user_id: int):
    """
    Create a quiz (list of poll questions) and send the first poll.
    We store the quiz in tracking.json under user's 'current_quiz'.
    We also store active poll mapping data['active_polls'][poll_id] = sid
    """
    ensure_user_record(user_id)
    data = load_tracking()
    words = load_words()
    phrases = load_json(PHRASES_FILE)
    if not words and not phrases:
        bot.send_message(user_id, "No words or phrases available for quiz.")
        return

    questions = build_quiz_questions()
    if not questions:
        bot.send_message(user_id, "Could not build a quiz right now. Try later.")
        return

    sid = str(user_id)
    data["users"].setdefault(sid, data["users"].get(sid, {}))
    data["users"][sid]["current_quiz"] = {"questions": questions, "index": 0, "results": []}
    save_json(TRACK_FILE, data)

    increment_usage_count(user_id, "quiz_sent")
    # send first question
    _send_quiz_poll(user_id)

def _send_quiz_poll(user_id: int):
    data = load_tracking()
    sid = str(user_id)
    user_data = data["users"].get(sid, {})
    quiz = user_data.get("current_quiz")
    if not quiz:
        bot.send_message(user_id, "No quiz found. Start a new quiz with 🎯 Take a Quiz.")
        return

    idx = quiz.get("index", 0)
    questions = quiz.get("questions", [])
    if idx >= len(questions):
        # finished
        bot.send_message(user_id, "✅ Quiz finished! Great job!", reply_markup=get_main_menu())
        # optionally summarize
        results = quiz.get("results", [])
        correct = sum(1 for r in results if r.get("correct"))
        bot.send_message(user_id, f"You answered {correct}/{len(results)} correctly.")
        # cleanup
        data["users"][sid].pop("current_quiz", None)
        save_json(TRACK_FILE, data)
        return

    q = questions[idx]
    question_text = q["prompt"]
    options = q["options"]
    correct_index = q["correct_index"]

    try:
        msg = bot.send_poll(
            chat_id=user_id,
            question=question_text,
            options=options,
            type="quiz",
            correct_option_id=correct_index,
            is_anonymous=False
        )
        # store active poll mapping so poll_answer can be resolved to user and quiz
        poll_id = msg.poll.id
        data = load_tracking()
        data["active_polls"][poll_id] = {"user": sid}
        save_json(TRACK_FILE, data)
    except Exception as e:
        print("Failed to send poll:", e)
        bot.send_message(user_id, "Failed to send quiz poll. Try again later.")

# ---------------- Poll Answer Handler ----------------
@bot.poll_answer_handler(func=lambda x: True)
def handle_poll_answer(poll_answer: types.PollAnswer):
    """
    Called when a user answers an existing poll. We look up which user
    this poll belongs to from tracking.json, evaluate, give feedback,
    and advance the quiz.
    """
    poll_id = poll_answer.poll_id
    user_id = getattr(poll_answer.user, "id", None)
    if not user_id:
        return

    data = load_tracking()
    mapping = data.get("active_polls", {}).get(poll_id)
    if not mapping:
        # we don't have this poll in mapping (maybe old or not from us)
        return

    sid = mapping.get("user")
    if sid != str(user_id):
        # poll belongs to someone else (ignore)
        return

    # get user's quiz state
    user_data = data["users"].get(sid, {})
    quiz = user_data.get("current_quiz")
    if not quiz:
        return

    qidx = quiz.get("index", 0)
    questions = quiz.get("questions", [])
    if qidx >= len(questions):
        return

    q = questions[qidx]
    chosen = poll_answer.option_ids[0] if poll_answer.option_ids else None
    correct = (chosen == q.get("correct_index"))
    # save result
    quiz.setdefault("results", []).append({
        "type": q.get("type"),
        "prompt": q.get("prompt"),
        "chosen_index": chosen,
        "correct_index": q.get("correct_index"),
        "correct": correct
    })

    # feedback to user
    if correct:
        bot.send_message(user_id, "✅ Correct! 🎉")
    else:
        corr_idx = q.get("correct_index")
        correct_text = q["options"][corr_idx] if corr_idx is not None and corr_idx < len(q["options"]) else "N/A"
        bot.send_message(user_id, f"❌ Wrong — correct answer: *{correct_text}*")

    # advance
    quiz["index"] = qidx + 1
    data["users"][sid] = user_data
    # remove this poll from active mapping
    data["active_polls"].pop(poll_id, None)
    save_json(TRACK_FILE, data)

    # send next poll
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
# POST /trigger_quiz with JSON: {"secret":"<QUIZ_SECRET>", "user_id": optional}
@app.route("/trigger_quiz", methods=["POST"])
def trigger_quiz():
    if not QUIZ_SECRET:
        return jsonify({"error": "QUIZ_SECRET not configured on server."}), 500
    data = request.get_json(force=True, silent=True) or {}
    if data.get("secret") != QUIZ_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    target = data.get("user_id")
    if target:
        try:
            user_id = int(target)
            send_quiz_to_user(user_id)
            return jsonify({"status": "ok", "sent_to": user_id}), 200
        except Exception as e:
            return jsonify({"error": "invalid user_id"}), 400

    # send to all users in tracking (respect daily quota)
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
