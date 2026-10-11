# ui/dialogs.py
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTextEdit, QMessageBox, QApplication)
from PyQt6.QtCore import Qt
import os
import subprocess
import platform
import threading
import asyncio
from ui.widgets import VideoSettingsWidget, AudioSettingsWidget, VisualEffectsWidget
from utils.helpers import logger, detect_ffmpeg

try:
    import edge_tts
except ImportError: edge_tts = None

class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Renderer Settings")
        self.resize(400, 600)
        
        layout = QVBoxLayout(self)
        
        self.video_widget = VideoSettingsWidget(config)
        self.audio_widget = AudioSettingsWidget(config)
        self.viz_widget = VisualEffectsWidget(config)
        
        layout.addWidget(self.video_widget)
        layout.addWidget(self.audio_widget)
        layout.addWidget(self.viz_widget)
        
        btns = QHBoxLayout()
        ok = QPushButton("Save"); ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addWidget(ok); btns.addWidget(cancel)
        layout.addLayout(btns)

    def get_data(self):
        data = {}
        data.update(self.video_widget.get_data())
        data.update(self.audio_widget.get_data())
        data.update(self.viz_widget.get_data())
        return data

class ScriptEditorDialog(QDialog):
    def __init__(self, script_path, voice_id, parent=None):
        super().__init__(parent)
        self.script_path = script_path
        self.voice_id = voice_id
        self.setWindowTitle("Edit Script")
        self.resize(600, 400)
        
        layout = QVBoxLayout(self)
        self.text = QTextEdit()
        layout.addWidget(self.text)
        
        h = QHBoxLayout()
        self.btn_play = QPushButton("Play Audio")
        self.btn_play.clicked.connect(self.play_preview)
        btn_save = QPushButton("Save"); btn_save.clicked.connect(self.accept)
        btn_close = QPushButton("Close"); btn_close.clicked.connect(self.reject)
        h.addWidget(self.btn_play); h.addWidget(btn_save); h.addWidget(btn_close)
        layout.addLayout(h)

        if os.path.exists(self.script_path):
            try:
                with open(self.script_path, 'r', encoding='utf-8') as f:
                    self.text.setPlainText(f.read())
            except Exception as e:
                logger.error(f"Failed to load script: {e}")

    def play_preview(self):
        txt = self.text.toPlainText().strip()
        ffmpeg_path = detect_ffmpeg()
        if not txt or not ffmpeg_path or not edge_tts: 
            logger.warning("Cannot play preview: Missing dependencies.")
            return
        
        self.btn_play.setEnabled(False)
        self.btn_play.setText("Generating...")
        
        def run():
            mp3 = "temp_preview.mp3"
            wav = "temp_preview.wav"
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(edge_tts.Communicate(txt, self.voice_id).save(mp3))
                finally: loop.close()
                
                subprocess.run([ffmpeg_path, "-y", "-i", mp3, "-ar", "22050", wav], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if platform.system() == "Windows": os.startfile(wav)
                elif platform.system() == "Darwin": subprocess.call(["open", wav])
                else: subprocess.call(["xdg-open", wav])
                
                import time
                time.sleep(1)
                try:
                    if os.path.exists(mp3): os.remove(mp3)
                    if os.path.exists(wav): os.remove(wav)
                except: pass
                    
            except Exception as e: logger.error(f"Preview failed: {e}")
            finally: 
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(1000, lambda: self.btn_play.setEnabled(True) or self.btn_play.setText("Play Audio"))

        threading.Thread(target=run, daemon=True).start()
    
    def accept(self):
        try:
            with open(self.script_path, 'w', encoding='utf-8') as f:
                f.write(self.text.toPlainText())
            super().accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save script:\n{e}")