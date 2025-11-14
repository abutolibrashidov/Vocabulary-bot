# bot.py
import os
import json
import random
from typing import Any, Optional
from flask import Flask, request, abort
from telebot import TeleBot, types
from deep_translator import GoogleTranslator
from dotenv import load_dotenv
import requests

# ---------------- Environment ----------------
load_dotenv()
TOKEN = os.getenv("TOKEN")
PUBLIC_URL_PATH = "/etc/secrets/PUBLIC_URL"

if os.path.exists(PUBLIC_URL_PATH):
    with open(PUBLIC_URL_PATH, "r") as f:
        PUBLIC_URL = f.read().strip()
else:
    PUBLIC_URL = os.getenv("PUBLIC_URL", "")

if not TOKEN:
    raise RuntimeError("TOKEN is required in .env")
if not PUBLIC_URL:
    print("Warning: PUBLIC_URL not set. Webhook may not work automatically.")

BOT_NAME = "Vocabulary with Mr. Korsh"
print("Bot Name:", BOT_NAME)
print("Bot token:", TOKEN)
print("Public URL:", PUBLIC_URL)

# ---------------- File paths ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
WORDS_FILE = os.path.join(DATA_DIR, "words.json")
PHRASES_FILE = os.path.join(DATA_DIR, "phrases.json")
TRACK_FILE = os.path.join(BASE_DIR, "tracking.json")

# ---------------- Helpers ----------------
def load_json(file_path: str) -> Any:
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}

def save_json(file_path: str, data: Any):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ---------------- Tracking ----------------
def track_user(user_id: int, username: str = "", first_name: str = ""):
    data = load_json(TRACK_FILE)
    if not isinstance(data, dict):
        data = {}
    users = data.get("users", {})
    sid = str(user_id)

    if sid not in users:
        users[sid] = {
            "username": username,
            "first_name": first_name,
            "usage_count": 0,
            "history": []
        }
    data["users"] = users
    save_json(TRACK_FILE, data)

def load_all_users() -> dict:
    data = load_json(TRACK_FILE)
    if isinstance(data, dict):
        return data.get("users", {})
    return {}

def increment_usage_count(user_id: int, item: Optional[str] = None):
    data = load_json(TRACK_FILE)
    sid = str(user_id)
    if "users" in data and sid in data["users"]:
        data["users"][sid]["usage_count"] += 1
        if item:
            data["users"][sid]["history"].append(item)
        save_json(TRACK_FILE, data)

def track_quiz_response(user_id: int, question_info: dict):
    """Track each quiz response with question, options, user choice, and correctness."""
    data = load_json(TRACK_FILE)
    sid = str(user_id)
    if "users" in data and sid in data["users"]:
        data["users"][sid]["history"].append(question_info)
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
        url = "https://github.com/abutolibrashidov/Vocabulary-bot/raw/refs/heads/main/words.json"
        try:
            r = requests.get(url)
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

# ---------------- Bot ----------------
bot = TeleBot(TOKEN, parse_mode="Markdown")

def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🌐 Translate a Word", "🗣 Learn a Phrase", "🎯 Take a Quiz")
    return markup

# ---------------- Commands ----------------
@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    track_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    bot.send_message(
        message.chat.id,
        f"Hello {message.from_user.first_name}!\nWelcome to *{BOT_NAME}*!",
        reply_markup=get_main_menu()
    )

# ---------------- Message Handling ----------------
@bot.message_handler(func=lambda msg: True)
def main_handler(message: types.Message):
    text = message.text.strip()
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
            markup.add(types.InlineKeyboardButton(key, callback_data=f"phrase_topic:{key}"))
        bot.send_message(message.chat.id, "Select a phrase topic:", reply_markup=markup)
    elif text == "🎯 Take a Quiz":
        send_quiz_to_user(message.chat.id)
    else:
        translate_word(message)

def translate_word(message: types.Message):
    word = message.text.strip()
    info = find_word_info(word)
    if info:
        translation = info.get("translation", word)
        response = format_word_response(word, translation, info)
    else:
        translation, _, _ = translate_dynamic(word)
        response = f"📝 Word: *{word}*\n🔤 Translation: *{translation}*"
    increment_usage_count(message.from_user.id, word)
    bot.send_message(message.chat.id, response, reply_markup=get_main_menu())

# ---------------- Quiz System ----------------
def send_quiz_to_user(user_id: int):
    words = load_words()
    phrases = load_json(PHRASES_FILE)
    if not words and not phrases:
        bot.send_message(user_id, "No words or phrases available for quiz.")
        return

    # Prepare 3 questions
    quiz_questions = []

    # 1) Phrase meaning
    if phrases:
        topic = random.choice(list(phrases.keys()))
        phrase = random.choice(phrases[topic])
        options = [phrase]  # Correct option
        # Random distractors
        all_phrases = [p for plist in phrases.values() for p in plist if p != phrase]
        while len(options) < 4 and all_phrases:
            distractor = random.choice(all_phrases)
            if distractor not in options:
                options.append(distractor)
        random.shuffle(options)
        quiz_questions.append({
            "type": "phrase_meaning",
            "question": f"What is the meaning of the phrase: *{phrase}*?",
            "answer": phrase,
            "options": options
        })

    # 2) Word property
    if words:
        word, info = random.choice(list(words.items()))
        correct = info.get("part_of_speech", "noun")
        all_pos = ["noun", "verb", "adjective", "adverb"]
        options = [correct]
        while len(options) < 4:
            distractor = random.choice(all_pos)
            if distractor not in options:
                options.append(distractor)
        random.shuffle(options)
        quiz_questions.append({
            "type": "word_property",
            "question": f"What is the part of speech of: *{word}*?",
            "answer": correct,
            "options": options
        })

    # 3) Random word translation
    if words:
        word, info = random.choice(list(words.items()))
        correct = info.get("translation", word)
        all_translations = [v.get("translation", k) for k, v in words.items() if k != word]
        options = [correct]
        while len(options) < 4 and all_translations:
            distractor = random.choice(all_translations)
            if distractor not in options:
                options.append(distractor)
        random.shuffle(options)
        quiz_questions.append({
            "type": "word_translation",
            "question": f"Translate this word: *{word}*",
            "answer": correct,
            "options": options
        })

    # Store quiz state
    user_data = load_json(TRACK_FILE).get("users", {}).get(str(user_id), {})
    user_data["current_quiz"] = {"questions": quiz_questions, "index": 0}
    data = load_json(TRACK_FILE)
    data["users"][str(user_id)] = user_data
    save_json(TRACK_FILE, data)

    # Send first question
    send_quiz_question(user_id)

def send_quiz_question(user_id: int):
    data = load_json(TRACK_FILE)
    user_data = data.get("users", {}).get(str(user_id), {})
    quiz = user_data.get("current_quiz")
    if not quiz:
        bot.send_message(user_id, "No quiz found. Start a new quiz with 🎯 Take a Quiz.")
        return
    index = quiz.get("index", 0)
    questions = quiz.get("questions", [])
    if index >= len(questions):
        bot.send_message(user_id, "✅ Quiz finished! Great job!", reply_markup=get_main_menu())
        user_data.pop("current_quiz", None)
        data["users"][str(user_id)] = user_data
        save_json(TRACK_FILE, data)
        return
    q = questions[index]
    markup = types.InlineKeyboardMarkup()
    for idx, opt in enumerate(q["options"]):
        markup.add(types.InlineKeyboardButton(opt, callback_data=f"quiz_{index}_{opt}"))
    bot.send_message(user_id, q["question"], reply_markup=markup)

# ---------------- Inline Callbacks ----------------
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call: types.CallbackQuery):
    data = call.data
    if data.startswith("phrase_topic:"):
        topic = data.split(":")[1]
        phrases_data = load_json(PHRASES_FILE)
        phrases_list = phrases_data.get(topic, [])
        if phrases_list:
            text = f"📌 Phrases for *{topic}*:\n" + "\n".join(f"- {p}" for p in phrases_list)
        else:
            text = "No phrases found for this topic."
        increment_usage_count(call.from_user.id)
        bot.send_message(call.message.chat.id, text, reply_markup=get_main_menu())
    elif data.startswith("quiz_"):
        parts = data.split("_")
        index = int(parts[1])
        selected = "_".join(parts[2:])
        # Load quiz
        user_id = call.from_user.id
        data_json = load_json(TRACK_FILE)
        user_data = data_json.get("users", {}).get(str(user_id), {})
        quiz = user_data.get("current_quiz", {})
        questions = quiz.get("questions", [])
        if index >= len(questions):
            return
        q = questions[index]
        correct = q["answer"]
        # Track response
        track_quiz_response(user_id, {
            "question_type": q["type"],
            "question": q["question"],
            "options": q["options"],
            "answer": correct,
            "user_choice": selected,
            "correct": selected == correct
        })
        # Feedback
        if selected == correct:
            bot.send_message(user_id, "✅ Great job! 🎉")
        else:
            bot.send_message(user_id, "❌ Keep going, I believe in you! 💪")
        # Move to next question
        user_data["current_quiz"]["index"] = index + 1
        data_json["users"][str(user_id)] = user_data
        save_json(TRACK_FILE, data_json)
        send_quiz_question(user_id)

# ---------------- Flask Webhook ----------------
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
    # Quiz sending handled externally
    set_webhook()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
