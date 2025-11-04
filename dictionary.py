import json
from pathlib import Path
import requests  # ✅ Needed for API requests

# --- Load local data ---
data_dir = Path(__file__).parent / "data"

# Load words.json
WORDS_PATH = data_dir / "words.json"
if WORDS_PATH.exists():
    with open(WORDS_PATH, "r", encoding="utf-8") as f:
        WORDS = json.load(f)
else:
    WORDS = {}

# Load phrases.json
PHRASES_PATH = data_dir / "phrases.json"
if PHRASES_PATH.exists():
    with open(PHRASES_PATH, "r", encoding="utf-8") as f:
        PHRASES = json.load(f)
else:
    PHRASES = {}

# --- Define get_word_info() function ---
def get_word_info(word):
    """Fetch word definition and example sentences using dictionary API."""
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    response = requests.get(url)

    if response.status_code != 200:
        return {"error": f"Word not found: {word}"}

    data = response.json()[0]
    meanings = data.get("meanings", [])
    definitions = []

    for meaning in meanings:
        part_of_speech = meaning.get("partOfSpeech", "")
        for d in meaning.get("definitions", []):
            definition = d.get("definition", "")
            example = d.get("example", "")
            definitions.append({
                "part_of_speech": part_of_speech,
                "definition": definition,
                "example": example
            })

    return {
        "word": data.get("word", word),
        "phonetics": data.get("phonetics", []),
        "meanings": definitions
    }
