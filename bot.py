# bot.py
import os
import json
import random
from deep_translator import GoogleTranslator
import telebot
from telebot import types

# ---------------- Configuration ----------------
TOKEN = "8152698293:AAGioWeiu-Y7BVfDK0b0Wy9rx1Pz6Pu2Huc"  # 🔒 Your bot token
bot = telebot.TeleBot(TOKEN)

# ---------------- Paths ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
WORDS_FILE = os.path.join(DATA_DIR, "words.json")
PHRASES_FILE = os.path.join(DATA_DIR, "phrases.json")
TRACK_FILE = os.path.join(BASE_DIR, "tracking.json")

# ---------------- Helper Functions ----------------
def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def track_word(user_id, word):
    tracking = load_json(TRACK_FILE)
    uid = str(user_id)
    if uid not in tracking:
        tracking[uid] = []
    if word not in tracking[uid]:
        tracking[uid].append(word)
        save_json(TRACK_FILE, tracking)

def translate_word(word):
    try:
        return GoogleTranslator(source='auto', target='uz').translate(word)
    except Exception:
        return None

def find_word_info(word):
    words = load_json(WORDS_FILE)
    for key, value in words.items():
        if key.lower() == word.lower():
            return value
    return None

def format_word_response(word, translation, info=None):
    response = f"📝 Word: {word}\n🔤 Translation: {translation}\n"
    if info:
        if info.get("part_of_speech"):
            response += f"📚 Part of Speech: {info['part_of_speech']}\n"
        if info.get("level"):
            response += f"⭐ Level: {info['level']}\n"
        if info.get("prefixes"):
            response += f"➕ Prefixes: {', '.join(info['prefixes'])}\n"
        if info.get("suffixes"):
            response += f"➖ Suffixes: {', '.join(info['suffixes'])}\n"
        if info.get("singular"):
            response += f"👤 Singular: {info['singular']}\n"
        if info.get("plural"):
            response += f"👥 Plural: {info['plural']}\n"
        if info.get("examples"):
            response += "📖 Examples:\n"
            for ex in info['examples']:
                response += f" - {ex}\n"
        if info.get("synonyms"):
            response += f"💡 Synonyms: {', '.join(info['synonyms'])}\n"
    return response.strip()

# ---------------- Menus ----------------
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("Translate a Word")
    btn2 = types.KeyboardButton("Learn a Phrase")
    markup.add(btn1, btn2)
    return markup

def adjective_menu():
    phrases = load_json(PHRASES_FILE)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for adj in phrases.keys():
        markup.add(types.KeyboardButton(adj))
    markup.add(types.KeyboardButton("Back to Main Menu"))
    return markup

# ---------------- Handlers ----------------
@bot.message_handler(commands=['start'])
def handle_start(message):
    welcome = (
        "📚 Welcome to Vocabulary with Mr. Korsh!\n\n"
        "Translate words, learn useful phrases, and track your progress easily.\n"
        "Choose an option below to get started 👇"
    )
    bot.send_message(message.chat.id, welcome, reply_markup=main_menu())

# Translate word
@bot.message_handler(func=lambda msg: msg.text == "Translate a Word")
def ask_word(message):
    msg = bot.send_message(message.chat.id, "✏️ Send me a word to translate:")
    bot.register_next_step_handler(msg, process_word)

# Learn phrases → show adjectives
@bot.message_handler(func=lambda msg: msg.text == "Learn a Phrase")
def show_adjectives(message):
    phrases = load_json(PHRASES_FILE)
    if not phrases:
        bot.send_message(message.chat.id, "⚠️ No phrases found in your database.")
        return
    bot.send_message(message.chat.id, "Select a topic/adjective to learn phrases:", reply_markup=adjective_menu())

# Learn phrases → show all phrases for selected adjective
@bot.message_handler(func=lambda msg: msg.text in load_json(PHRASES_FILE).keys())
def show_phrases(message):
    phrases = load_json(PHRASES_FILE)
    adjective = message.text
    if adjective in phrases:
        response = f"💬 Phrases for '{adjective}':\n"
        for p in phrases[adjective]:
            response += f" - {p}\n"
        bot.send_message(message.chat.id, response)
    else:
        bot.send_message(message.chat.id, "⚠️ No phrases found for this topic.")
    bot.send_message(message.chat.id, "You can choose another topic or go back to the main menu.", reply_markup=adjective_menu())

# Back to main menu
@bot.message_handler(func=lambda msg: msg.text == "Back to Main Menu")
def back_to_main(message):
    bot.send_message(message.chat.id, "🔙 Back to main menu.", reply_markup=main_menu())

# Process a word
@bot.message_handler(func=lambda msg: True)
def process_word(message):
    word = message.text.strip()
    if not word:
        bot.send_message(message.chat.id, "⚠️ Please send a valid word.")
        return

    track_word(message.from_user.id, word)
    info = find_word_info(word)

    if info:
        translation = info.get("translation") or translate_word(word)
        response = format_word_response(word, translation, info)
    else:
        translation = translate_word(word)
        if translation:
            response = f"🔎 '{word}' not found locally.\nHere’s the automatic translation:\n\n📝 Word: {word}\n🔤 Translation: {translation}"
        else:
            response = "⚠️ Sorry, I couldn’t translate that word."

    bot.send_message(message.chat.id, response)
    bot.send_message(message.chat.id, "💡 You can send another word or choose an option below.", reply_markup=main_menu())

# ---------------- Run Bot ----------------
if __name__ == "__main__":
    print("🤖 Bot is running smoothly...")
    bot.infinity_polling()
