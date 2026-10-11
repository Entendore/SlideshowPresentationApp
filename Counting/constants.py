# constants.py

# Edge TTS Configuration
EDGE_VOICES = [
    ("en-US-AriaNeural", "Aria (US)"), ("en-US-GuyNeural", "Guy (US)"),
    ("en-GB-SoniaNeural", "Sonia (UK)"), ("en-GB-RyanNeural", "Ryan (UK)"),
    ("de-DE-KatjaNeural", "Katja (DE)"), ("ja-JP-NanamiNeural", "Nanami (JP)")
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

# Azure TTS Configuration
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