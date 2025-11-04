import random

# -----------------------------
# Format a word response nicely
# -----------------------------
def format_word_response(word, info):
    """
    Returns a nicely formatted message for a word with emojis and Markdown.
    """
    prefixes = ", ".join(info.get("prefixes", [])) or "N/A"
    suffixes = ", ".join(info.get("suffixes", [])) or "N/A"
    singular_plural = info.get("singular_plural", "N/A")
    examples = info.get("examples", ["N/A", "N/A"])

    message = (
        f"🔹 *Word:* {word}\n"
        f"🔹 *Translation:* {info.get('translation', 'N/A')}\n"
        f"🔹 *Part of Speech:* {info.get('part_of_speech', 'N/A')}\n"
        f"🔹 *Level:* {info.get('level', 'N/A')}\n"
        f"🔹 *Prefixes/Suffixes:* {prefixes} / {suffixes}\n"
        f"🔹 *Singular/Plural:* {singular_plural}\n"
        f"🔹 *Examples:*\n"
        f"   1. {examples[0]}\n"
        f"   2. {examples[1]}"
    )
    return message


# -----------------------------
# Pick a random phrase from a list
# -----------------------------
def pick_random_phrase(phrases_list):
    """
    Returns a random phrase from a list of phrases.
    Each item in phrases_list should be a dictionary with 'phrase' and 'meaning'.
    """
    if not phrases_list:
        return "❗ No phrases available."
    item = random.choice(phrases_list)
    return f"🌟 {item['phrase']} – {item['meaning']}"


# -----------------------------
# Detect language (English or Uzbek)
# -----------------------------
def detect_language(text):
    """
    Simple language detection: English letters vs others.
    Returns 'english', 'uzbek', or None.
    """
    text = text.strip()
    if not text:
        return None
    if all(ord(c) < 128 for c in text):
        return "english"
    else:
        return "uzbek"
