# send_quiz.py
from bot import send_quiz_to_user, load_all_users, increment_usage_count
import logging

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def main():
    users = load_all_users()  # Now returns dict {user_id: {info}}
    if not users:
        logging.warning("No users found to send quizzes.")
        return

    for uid, info in users.items():
        try:
            send_quiz_to_user(int(uid))  # Dynamic quiz inside bot.py
            increment_usage_count(int(uid))
            logging.info(f"✅ Sent quiz to {info.get('username', uid)} "
                         f"(Usage count: {info.get('usage_count', 0) + 1})")
        except Exception as e:
            logging.error(f"❌ Failed to send quiz to {info.get('username', uid)}: {e}")

if __name__ == "__main__":
    main()
