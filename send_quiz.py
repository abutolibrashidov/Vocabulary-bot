# send_quiz.py
from bot import send_quiz_to_user, load_all_users
import logging

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def main():
    users = load_all_users()
    if not users:
        logging.warning("No users found to send quizzes.")
        return

    for uid in users:
        try:
            send_quiz_to_user(int(uid))  # Dynamic quiz is built inside bot.py
            logging.info(f"✅ Sent quiz to user {uid}")
        except Exception as e:
            logging.error(f"❌ Failed to send quiz to user {uid}: {e}")

if __name__ == "__main__":
    main()
