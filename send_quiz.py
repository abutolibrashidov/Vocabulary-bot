from bot import send_quiz_to_user, load_all_users, load_json
import random

def main():
    users = load_all_users()
    words = load_json("data/words.json")  # Make sure path matches your project

    if not words:
        print("No words found in words.json.")
        return

    for uid in users:
        try:
            # Select 3 random words for each quiz
            quiz_words = random.sample(list(words.items()), min(3, len(words)))
            message = "🎯 Quiz time! Translate these words:\n"
            for word, info in quiz_words:
                message += f"- {word}\n"
            send_quiz_to_user(int(uid), message_text=message)
            print(f"✅ Sent quiz to {uid}")
        except Exception as e:
            print(f"❌ Failed to send quiz to {uid}: {e}")

if __name__ == "__main__":
    main()


import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def main():
    users = load_all_users()
    for uid in users:
        try:
            send_quiz_to_user(int(uid))
            logging.info(f"✅ Sent quiz to {uid}")
        except Exception as e:
            logging.error(f"❌ Failed to send quiz to {uid}: {e}")

if __name__ == "__main__":
    main()
