from bot import send_quiz_to_user, load_all_users

def main():
    users = load_all_users()
    for uid in users:
        try:
            send_quiz_to_user(int(uid))
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
