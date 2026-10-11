# config.py
import os
import json
from utils import logger

class AppConfig:
    DEFAULT_CONFIG = {
        "width": 1280,
        "height": 720,
        "fps": 30,
        "encoder": "auto",
        "preset": "fast",
        "transition_duration": 0.5,
        "edge_voice": "en-US-GuyNeural",
        "edge_tone": "general",
        "tts_backend": "edge",
        "azure_region": "eastus",
        "azure_subscription_key": "",
        "azure_voice": "en-US-GuyNeural",
        "azure_style": "calm",
        "azure_styledegree": 1.0,
        "render_workers": 3,
        "output_dir": "Output",
        "render_mode": "full",
        "enable_zoom": False,
        "zoom_factor": 1.1,
        "music_volume": 0.2,
    }

    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
        self.settings = self.DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except Exception as e:
                logger.error(f"Error loading config: {e}")

    def save(self):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save()

    def update(self, data):
        self.settings.update(data)
        self.save()