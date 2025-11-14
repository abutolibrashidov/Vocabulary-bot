# send_quiz.py
from bot import send_quiz_to_user, load_all_users, TRACK_FILE, load_json, save_json
import logging

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def reset_unfinished_quizzes():
    """
    Resets current quizzes for users so daily or scheduled quizzes start fresh.
    """
    data = load_json(TRACK_FILE)
    if not isinstance(data, dict):
        return

    users = data.get("users", {})
    for sid, info in users.items():
        if "current_quiz" in info:
            info.pop("current_quiz")  # Remove unfinished quiz
    data["users"] = users
    save_json(TRACK_FILE, data)
    logging.info("✅ Reset all unfinished quizzes.")

def main():
    reset_unfinished_quizzes()  # Ensure fresh quizzes
    users = load_all_users()    # Returns dict {user_id: {info}}
    if not users:
        logging.warning("No users found to send quizzes.")
        return

    for uid, info in users.items():
        try:
            send_quiz_to_user(int(uid))  # New multiple-choice quiz handles usage internally
            logging.info(f"✅ Sent quiz to {info.get('username', uid)}")
        except Exception as e:
            logging.error(f"❌ Failed to send quiz to {info.get('username', uid)}: {e}")

if __name__ == "__main__":
    main()
