# syllables.py
import random

try:
    import eng_to_ipa as ipa_lib
except ImportError:
    ipa_lib = None

# Language-specific character sets
LANG_CHARSETS = {
    "en": {
        "vowels": "aeiou",
        "consonants": "bcdfghjklmnpqrstvwxyz",
        "clusters": [
            "bl", "br", "ch", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr",
            "sc", "sh", "sk", "sl", "sm", "sn", "sp", "st", "sw", "th", "tr", "tw", "wh", "wr",
        ]
    },
    "es": { # Spanish
        "vowels": "aeiouáéíóúü",
        "consonants": "bcdfghjklmnñpqrstvwxyz",
        "clusters": [
            "br", "bl", "ch", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "ll", "pl", "pr",
            "rr", "sc", "tr",
        ]
    },
    "de": { # German
        "vowels": "aeiouäöü",
        "consonants": "bcdfghjklmnpqrstvwxyz",
        "clusters": [
            "sch", "ch", "sp", "st", "pf", "br", "bl", "pr", "pl", "tr", "dr", "kn", "gn",
        ]
    },
    "fr": { # French
        "vowels": "aeiouéèàâêîôû",
        "consonants": "bcdfghjklmnpqrstvwxyz",
        "clusters": [
            "bl", "br", "ch", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "tr",
            "gn", "qu", "ph",
        ]
    },
    "it": { # Italian
        "vowels": "aeiouàèéìòù",
        "consonants": "bcdfghjklmnpqrstvwxyz",
        "clusters": [
            "bl", "br", "ch", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "tr",
            "gn", "sc", "z",
        ]
    },
    "ja": { # Japanese (Romaji approximation for generation logic)
        "vowels": "aeiou",
        "consonants": "kstnhmyrwgzdbp", # Simplified for CV structure
        "clusters": [] # Japanese is mostly CV, no complex clusters
    },
    "zh": { # Chinese (Pinyin approximation)
        "vowels": "aeiou",
        "consonants": "bpmfdtnlgkhjqxzcsryw",
        "clusters": ["zh", "ch", "sh"]
    }
}

def random_consonant(lang="en"):
    cs = LANG_CHARSETS.get(lang, LANG_CHARSETS["en"])["consonants"]
    return random.choice(cs)

def random_vowel(lang="en"):
    cs = LANG_CHARSETS.get(lang, LANG_CHARSETS["en"])["vowels"]
    return random.choice(cs)

def random_onset(lang="en"):
    data = LANG_CHARSETS.get(lang, LANG_CHARSETS["en"])
    clusters = data.get("clusters", [])
    if clusters and random.random() < 0.3: # 30% chance of cluster
        return random.choice(clusters)
    else:
        return random.choice(data["consonants"])

def random_coda(lang="en"):
    data = LANG_CHARSETS.get(lang, LANG_CHARSETS["en"])
    clusters = data.get("clusters", [])
    
    # Languages like Japanese usually don't have codas
    if lang == "ja": return ""

    if clusters and random.random() < 0.2: # 20% chance of coda cluster
        return random.choice(clusters)
    elif random.random() < 0.5: # 50% chance of simple coda
        return random.choice(data["consonants"])
    return ""

def random_syllable(lang="en") -> str:
    """Generate a random pronounceable syllable based on language rules."""
    onset = random_onset(lang)
    vowel = random_vowel(lang)
    coda = random_coda(lang)
    return onset + vowel + coda

def random_word(min_syllables=1, max_syllables=3, lang="en") -> str:
    """Generate a nonsense word."""
    n = random.randint(min_syllables, max_syllables)
    return "".join(random_syllable(lang) for _ in range(n))

def word_to_ipa(word: str, lang="en") -> str:
    """
    Convert to IPA. 
    NOTE: eng_to_ipa only supports English. For other languages, 
    we return a placeholder or the word itself since random nonsense 
    words don't have dictionary IPA.
    """
    if lang != "en":
        return f"/{word}/" # Fallback for non-English
        
    if ipa_lib is None:
        return "/?/"
    try:
        ipa_str = ipa_lib.convert(word).strip()
        ipa_str = ipa_str.replace("*", "")
        if not ipa_str.startswith("/"):
            ipa_str = "/" + ipa_str
        if not ipa_str.endswith("/"):
            ipa_str = ipa_str + "/"
        return ipa_str
    except Exception:
        return "/?/"

def generate_random_item(mode: str = "word", lang: str = "en"):
    """
    mode: 'syllable' or 'word'
    lang: language code (e.g., 'en', 'es', 'de')
    """
    if mode == "syllable":
        text = random_syllable(lang)
    else:  # 'word'
        text = random_word(lang=lang)
    ipa = word_to_ipa(text, lang)
    return text, ipa