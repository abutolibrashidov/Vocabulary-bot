import json
import requests
from deep_translator import GoogleTranslator

# Path to your local word cache
WORD_FILE = "word.json"

# Load or create cache
try:
    with open(WORD_FILE, "r", encoding="utf-8") as f:
        CACHE = json.load(f)
except FileNotFoundError:
    CACHE = {}

def save_cache():
    """Save the updated cache."""
    with open(WORD_FILE, "w", encoding="utf-8") as f:
        json.dump(CACHE, f, ensure_ascii=False, indent=2)

def lookup_word(word):
    """Get definitions, synonyms, and Uzbek translation for a given word."""
    word = word.lower().strip()

    # 1. Check cache
    if word in CACHE:
        return CACHE[word]

    # 2. Get definition + synonyms (Free Dictionary API + Datamuse)
    dict_url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    resp = requests.get(dict_url)
    if resp.status_code != 200:
        return {"error": "Word not found"}

    data = resp.json()[0]
    meaning = data["meanings"][0]
    part_of_speech = meaning.get("partOfSpeech", "")
    definition = meaning["definitions"][0].get("definition", "")

    # 3. Get synonyms from Datamuse API
    syn_resp = requests.get(f"https://api.datamuse.com/words?rel_syn={word}")
    synonyms = [item["word"] for item in syn_resp.json()[:5]]

    # 4. Translate definition to Uzbek (based on part of speech)
    # Add context for verbs to improve accuracy
    text_to_translate = f"({part_of_speech}) {definition}"
    uzbek_translation = GoogleTranslator(source="en", target="uz").translate(text_to_translate)

    level = None
    prefixes = []
    suffixes = []
    example_sentence_1 = ""
    example_sentence_2 = ""

    result = {
    "word": word,
    "translation_uz": uzbek_translation,
    "part_of_speech": part_of_speech,
    "level": level,  # e.g., A1, B2
    "prefixes": prefixes,  # e.g., ["un-", "re-"]
    "suffixes": suffixes,  # e.g., ["-ness", "-ful"]
    "definition_en": definition,
    "example_sentences": [
        example_sentence_1,
        example_sentence_2
    ],
    "synonyms_en": synonyms
}


    # 5. Cache result for future use
    CACHE[word] = result
    save_cache()

    return result
