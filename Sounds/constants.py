# constants.py

# Mapping of language codes to display names
LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "de": "German",
    "fr": "French",
    "it": "Italian",
    "ja": "Japanese",
    "zh": "Chinese (Mandarin)",
}

EDGE_VOICES = [
    # English
    ("en-US-AriaNeural", "Aria (US - Female)", "en"),
    ("en-US-GuyNeural", "Guy (US - Male)", "en"),
    ("en-GB-SoniaNeural", "Sonia (UK - Female)", "en"),
    ("en-GB-RyanNeural", "Ryan (UK - Male)", "en"),
    # Spanish
    ("es-ES-ElviraNeural", "Elvira (ES - Female)", "es"),
    ("es-MX-JorgeNeural", "Jorge (MX - Male)", "es"),
    # German
    ("de-DE-KatjaNeural", "Katja (DE - Female)", "de"),
    ("de-DE-ConradNeural", "Conrad (DE - Male)", "de"),
    # French
    ("fr-FR-DeniseNeural", "Denise (FR - Female)", "fr"),
    ("fr-FR-HenriNeural", "Henri (FR - Male)", "fr"),
    # Italian
    ("it-IT-ElsaNeural", "Elsa (IT - Female)", "it"),
    ("it-IT-DiegoNeural", "Diego (IT - Male)", "it"),
    # Japanese
    ("ja-JP-NanamiNeural", "Nanami (JP - Female)", "ja"),
    ("ja-JP-KeitaNeural", "Keita (JP - Male)", "ja"),
    # Chinese
    ("zh-CN-XiaoxiaoNeural", "Xiaoxiao (CN - Female)", "zh"),
    ("zh-CN-YunyangNeural", "Yunyang (CN - Male)", "zh"),
]

EDGE_TONES = [
    "general", "cheerful", "sad", "angry", "fearful",
    "neutral", "scared", "emotional", "relaxed", "excited",
    "calm", "empathetic",
]

EDGE_TONE_PRESETS = {
    "general":   {"rate": "+0%",  "volume": "+0%", "pitch": "+0Hz"},
    "cheerful":  {"rate": "+10%", "volume": "+10%", "pitch": "+5Hz"},
    "sad":       {"rate": "-10%", "volume": "-10%", "pitch": "-5Hz"},
    "angry":     {"rate": "+15%", "volume": "+20%", "pitch": "+10Hz"},
    "fearful":   {"rate": "+10%", "volume": "+5%",  "pitch": "+5Hz"},
    "neutral":   {"rate": "+0%",  "volume": "+0%",  "pitch": "+0Hz"},
    "scared":    {"rate": "+12%", "volume": "+8%",  "pitch": "+8Hz"},
    "emotional": {"rate": "+5%",  "volume": "+10%", "pitch": "+2Hz"},
    "relaxed":   {"rate": "-10%", "volume": "-5%",  "pitch": "-5Hz"},
    "excited":   {"rate": "+20%", "volume": "+15%", "pitch": "+10Hz"},
    "calm":      {"rate": "-5%",  "volume": "-5%",  "pitch": "-2Hz"},
    "empathetic":{"rate": "+0%",  "volume": "+5%", "pitch": "+0Hz"},
}

AZURE_REGIONS = [
    "eastus", "westus", "westus2", "westus3",
    "eastus2", "centralus", "northcentralus", "southcentralus",
    "westeurope", "northeurope", "uksouth", "ukwest",
    "southeastasia", "eastasia", "japaneast", "japanwest",
]

AZURE_STYLES = [
    "calm", "cheerful", "sad", "angry", "fearful",
    "empathetic", "excited", "gentle", "friendly", "hopeful",
]