# bot.py
import os
import requests
import json
import random
import threading
import time
from typing import Any, Optional
from flask import Flask, request, abort
from telebot import TeleBot, types
from deep_translator import GoogleTranslator
from dotenv import load_dotenv

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
def track_user(user_id: int):
    data = load_json(TRACK_FILE)
    if not isinstance(data, dict):
        data = {}
    users = data.get("users", [])
    sid = str(user_id)
    if sid not in users:
        users.append(sid)
        data["users"] = users
        save_json(TRACK_FILE, data)

def load_all_users():
    data = load_json(TRACK_FILE)
    if isinstance(data, dict):
        return list(data.get("users", []))
    return []

# ---------------- Translation ----------------
def detect_uzbek(text: str) -> bool:
    if not text:
        return False
    for ch in text:
        if "\u0400" <= ch <= "\u04FF":  # Cyrillic
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
https://github.com/abutolibrashidov/Vocabulary-bot/raw/refs/heads/main/words.json
def find_word_info(word: str) -> Optional[dict]:
    # Try to load dynamic words from GitHub
    words = load_words_from_github()
    if not isinstance(words, dict):
        words = load_json(WORDS_FILE)  # fallback to local file
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

# ---------------- Persistent options markup ----------------
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🌐 Translate a Word", "🗣 Learn a Phrase")
    return markup

# ---------------- Start command ----------------
@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    track_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"Hello {message.from_user.first_name}!\nWelcome to *{BOT_NAME}*!",
        reply_markup=get_main_menu()
    )

# ---------------- Main message handler ----------------
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
    else:
        # Treat anything else as a word translation
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
    bot.send_message(message.chat.id, response, reply_markup=get_main_menu())

# ---------------- Inline Callback handling ----------------
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call: types.CallbackQuery):
    data = call.data
    if data.startswith("phrase_topic:"):
        topic = data.split(":")[1]
        phrases_data = load_json(PHRASES_FILE)
        phrases_list = phrases_data.get(topic, [])
        if phrases_list:
            text = f"📌 Phrases for *{topic}*:\n"
            for p in phrases_list:
                text += f"- {p}\n"
        else:
            text = "No phrases found for this topic."
        bot.send_message(call.message.chat.id, text, reply_markup=get_main_menu())

# ---------------- Quiz sending ----------------
def send_quiz_to_user(user_id: int):
    words = load_json(WORDS_FILE)
    if not words:
        return
    word, info = random.choice(list(words.items()))
    translation = info.get("translation", None) or word
    bot.send_message(user_id, f"🎯 Quiz time! Translate this word: *{word}*", parse_mode="Markdown")

def quiz_dispatcher_loop(interval_hours=12):
    while True:
        users = load_all_users()
        for uid in users:
            try:
                send_quiz_to_user(int(uid))
            except Exception as e:
                print("Failed to send quiz to", uid, e)
        time.sleep(interval_hours * 3600)

def start_quiz_thread():
    t = threading.Thread(target=quiz_dispatcher_loop, args=(12,), daemon=True)
    t.start()

# ---------------- Flask webhook ----------------
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
    start_quiz_thread()
    set_webhook()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)



