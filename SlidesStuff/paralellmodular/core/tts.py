# core/tts.py
import os
import asyncio
import subprocess
import logging
import requests
from typing import Optional

try:
    import edge_tts
except ImportError:
    edge_tts = None

logger = logging.getLogger("TTS")

class TTSEngine:
    EDGE_TONE_PRESETS = {
        "general": {"rate": "+0%", "volume": "+0%", "pitch": "+0Hz"},
        "cheerful": {"rate": "+10%", "volume": "+10%", "pitch": "+5Hz"},
        "sad": {"rate": "-10%", "volume": "-10%", "pitch": "-5Hz"},
        "angry": {"rate": "+15%", "volume": "+20%", "pitch": "+10Hz"},
        "fearful": {"rate": "+10%", "volume": "+5%", "pitch": "+5Hz"},
        "neutral": {"rate": "+0%", "volume": "+0%", "pitch": "+0Hz"},
        "scared": {"rate": "+12%", "volume": "+8%", "pitch": "+8Hz"},
        "emotional": {"rate": "+5%", "volume": "+10%", "pitch": "+2Hz"},
        "relaxed": {"rate": "-10%", "volume": "-5%", "pitch": "-5Hz"},
        "excited": {"rate": "+20%", "volume": "+15%", "pitch": "+10Hz"},
        "calm": {"rate": "-5%", "volume": "-5%", "pitch": "-2Hz"},
        "empathetic": {"rate": "+0%", "volume": "+5%", "pitch": "+0Hz"},
    }

    @staticmethod
    def normalize_style_for_azure(style: str) -> str:
        mapping = {
            "general": "calm", "cheerful": "cheerful", "sad": "sad", "angry": "angry",
            "fearful": "fearful", "neutral": "calm", "scared": "fearful",
            "emotional": "empathetic", "relaxed": "calm", "excited": "excited",
            "calm": "calm", "empathetic": "empathetic",
        }
        return mapping.get(style.lower(), "calm")

    @staticmethod
    def build_azure_ssml(text: str, voice: str, style: str, styledegree: Optional[float], lang: str = "en-US") -> str:
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")
        style_attr = f'style="{style}"'
        if styledegree is not None:
            style_attr += f' styledegree="{max(0.01, min(2.0, styledegree)):.2f}"'
        return f"<speak version='1.0' xml:lang='{lang}'><voice name='{voice}'><mstts:express-as xmlns:mstts='https://www.w3.org/2001/mstts' {style_attr}>{text}</mstts:express-as></voice></speak>"

    @staticmethod
    async def generate_edge(text: str, output_mp3: str, voice_id: str, tone: str):
        if not edge_tts: raise Exception("edge-tts not installed")
        preset = TTSEngine.EDGE_TONE_PRESETS.get(tone, TTSEngine.EDGE_TONE_PRESETS["general"])
        communicate = edge_tts.Communicate(text, voice_id, rate=preset["rate"], volume=preset["volume"], pitch=preset["pitch"])
        await communicate.save(output_mp3)

    @staticmethod
    def generate_azure_sync(text: str, output_mp3: str, region: str, key: str, voice: str, style: str, styledegree: Optional[float]):
        url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        ssml = TTSEngine.build_azure_ssml(text, voice, style, styledegree)
        headers = {
            "Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3", "User-Agent": "SlideshowApp/1.0"
        }
        try:
            resp = requests.post(url, headers=headers, data=ssml.encode("utf-8"), timeout=30)
            if resp.status_code == 200:
                with open(output_mp3, "wb") as f: f.write(resp.content)
            else: raise Exception(f"Azure Error {resp.status_code}")
        except Exception as e: raise e

    @staticmethod
    def convert_mp3_to_wav(mp3_path: str, wav_path: str, ffmpeg_path: str):
        subprocess.run([
            ffmpeg_path, "-y", "-i", mp3_path, "-ar", "22050", "-ac", "1", wav_path
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
        if os.path.exists(mp3_path): os.remove(mp3_path)