import sys
import os
import re
import glob
import json
import time
import subprocess
import multiprocessing
import numpy as np
import shutil
import platform
import wave
import struct
import math
import traceback
import threading
import asyncio
import io
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

# --- DEPENDENCIES ---
try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False
    print("WARNING: edge-tts not found. Audio generation disabled. Run 'pip install edge-tts'")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("WARNING: Pillow not found. Run 'pip install playwright pillow'")

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    print("WARNING: Playwright not found. Run 'pip install playwright && playwright install chromium'")

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QPushButton, QLabel, QListWidget, QListWidgetItem, 
                             QTextEdit, QHBoxLayout, QMessageBox,
                             QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox,
                             QSplitter, QTabWidget, QPlainTextEdit, QInputDialog, QProgressBar, QScrollArea)
from PyQt6.QtCore import QEventLoop, QTimer, Qt, qInstallMessageHandler, QtMsgType
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings

# --- CONFIGURATION ---
DEFAULT_CONFIG = {
    "width": 1280,
    "height": 720,
    "fps": 30,
    "encoder": "auto",
    "preset": "p5",
    "transition_duration": 0.5,
    "edge_voice": "en-US-AriaNeural",
    "render_workers": 3
}

# --- UTILITIES ---

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', s)]

def detect_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return "ffmpeg"
    except FileNotFoundError:
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            return get_ffmpeg_exe()
        except:
            print("FFmpeg not found.")
            return None

FFMPEG_PATH = detect_ffmpeg()

def detect_encoder():
    if not FFMPEG_PATH: return "libx264"
    try:
        r = subprocess.run([FFMPEG_PATH, "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        enc = r.stdout
        if "h264_nvenc" in enc: return "h264_nvenc"
        if "h264_amf" in enc: return "h264_amf"
        if "h264_qsv" in enc: return "h264_qsv"
    except: pass
    return "libx264"

def handle_log_message(mode, context, message):
    noise = ["direct_composition_support", "cdn.tailwindcss.com", "QFontDatabase", 
             "propagateSizeHints", "All renderer processes", "type conversion", 
             "invalid connect", "libpng warning", "Remote debugging server started"]
    if any(n in message for n in noise): return

# --- TASK PROGRESS WIDGET ---

class TaskProgressWidget(QWidget):
    def __init__(self, project_name):
        super().__init__()
        self.project_name = project_name
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 2, 0, 2)
        self.setLayout(self.layout)

        # Label: Name + Status
        self.label = QLabel(f"{project_name}")
        self.label.setStyleSheet("font-weight: bold; font-size: 12px;")
        
        # Progress Bar
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFormat("%p%")
        self.bar.setTextVisible(True)
        self.bar.setFixedHeight(15)

        self.layout.addWidget(self.label)
        self.layout.addWidget(self.bar)

    def update_status(self, current, total, status_text=""):
        if isinstance(current, int) and isinstance(total, int) and total > 0:
            percentage = int((current / total) * 100)
            self.bar.setValue(percentage)
            self.bar.setFormat(f"{current}/{total} ({percentage}%)")
        else:
            # Indeterminate or state-based
            self.bar.setRange(0, 0) # Busy mode
        
        if status_text:
            self.label.setText(f"{self.project_name}: {status_text}")
        else:
            self.label.setText(self.project_name)

    def mark_complete(self, success=True):
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.bar.setFormat("Done")
        color = "#1e3a1e" if success else "#5a1e1e"
        self.label.setStyleSheet(f"font-weight: bold; color: {'#2ecc71' if success else '#e74c3c'};")
        self.setStyleSheet(f"background-color: {color}; border-radius: 4px; padding: 4px;")

# --- SETTINGS DIALOG ---

class SettingsDialog(QDialog):
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Renderer Settings")
        self.config = current_config.copy()
        layout = QFormLayout()
        
        self.width_spin = QSpinBox()
        self.width_spin.setRange(640, 3840)
        self.width_spin.setValue(self.config['width'])
        
        self.height_spin = QSpinBox()
        self.height_spin.setRange(480, 2160)
        self.height_spin.setValue(self.config['height'])
        
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(10, 60)
        self.fps_spin.setValue(self.config['fps'])
        
        self.trans_spin = QDoubleSpinBox()
        self.trans_spin.setRange(0.0, 5.0)
        self.trans_spin.setSingleStep(0.1)
        self.trans_spin.setValue(self.config.get('transition_duration', 0.5))
        self.trans_spin.setToolTip("Duration of (Single Project)")
        
        self.enc_combo = QComboBox()
        encs = ["auto", "libx264", "h264_nvenc", "h264_amf", "h264_qsv"]
        self.enc_combo.addItems(encs)
        self.enc_combo.setCurrentText(self.config['encoder'])

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 8)
        self.workers_spin.setValue(self.config.get('render_workers', 3))
        self.workers_spin.setToolTip("Number of parallel render processes")

        self.voice_combo = QComboBox()
        common_voices = [
            ("en-US-AriaNeural", "Aria (US Female)"),
            ("en-US-GuyNeural", "Guy (US Male)"),
            ("en-GB-SoniaNeural", "Sonia (UK Female)"),
            ("en-GB-RyanNeural", "Ryan (UK Male)"),
            ("en-AU-NatashaNeural", "Natasha (AU Female)"),
            ("en-IN-NeerjaNeural", "Neerja (IN Female)"),
            ("de-DE-KatjaNeural", "Katja (DE Female)"),
            ("es-ES-ElviraNeural", "Elvira (ES Female)"),
            ("fr-FR-DeniseNeural", "Denise (FR Female)"),
            ("ja-JP-NanamiNeural", "Nanami (JP Female)")
        ]
        current_voice = self.config.get('edge_voice', 'en-US-AriaNeural')
        for voice_id, name in common_voices:
            self.voice_combo.addItem(name, voice_id)
            if voice_id == current_voice:
                self.voice_combo.setCurrentIndex(self.voice_combo.count() - 1)
        self.voice_combo.setToolTip("Select the Edge-TTS neural voice.")
        
        layout.addRow("Width:", self.width_spin)
        layout.addRow("Height:", self.height_spin)
        layout.addRow("FPS:", self.fps_spin)
        layout.addRow("Transition (s):", self.trans_spin)
        layout.addRow("Encoder:", self.enc_combo)
        layout.addRow("Render Workers:", self.workers_spin)
        layout.addRow("TTS Voice:", self.voice_combo)
        
        btn_box = QHBoxLayout()
        ok_btn = QPushButton("Save")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(ok_btn)
        btn_box.addWidget(cancel_btn)
        layout.addRow(btn_box)
        self.setLayout(layout)

    def get_config(self):
        return {
            'width': self.width_spin.value(),
            'height': self.height_spin.value(),
            'fps': self.fps_spin.value(),
            'encoder': self.enc_combo.currentText(),
            'preset': self.config['preset'],
            'output_dir': self.config['output_dir'],
            'transition_duration': self.trans_spin.value(),
            'edge_voice': self.voice_combo.currentData(),
            'render_workers': self.workers_spin.value()
        }

# --- SCRIPT EDITOR DIALOG ---

class ScriptEditorDialog(QDialog):
    def __init__(self, script_path, voice_id=None, parent=None):
        super().__init__(parent)
        self.script_path = script_path
        self.voice_id = voice_id if voice_id else 'en-US-AriaNeural'
        self.setWindowTitle("Edit Script (Edge-TTS)")
        self.resize(600, 400)
        self.setStyleSheet("""
            QDialog { background-color: #2d2d30; color: #d4d4d4; }
            QTextEdit { background-color: #1e1e1e; color: #9cdcfe; border: 1px solid #3e3e42; font-family: Consolas; font-size: 14px; }
            QPushButton { background: #3e3e42; border: 1px solid #555; padding: 6px 12px; border-radius: 4px; color: white; min-width: 80px;}
            QPushButton:hover { background: #505055; }
            QPushButton#btnPlay { background-color: #2d8f2d; border: 1px solid #1e6b1e; font-weight: bold;}
            QPushButton#btnSave { background-color: #007acc; font-weight: bold;}
        """)
        
        layout = QVBoxLayout()
        self.text_edit = QTextEdit()
        layout.addWidget(self.text_edit)
        
        btn_layout = QHBoxLayout()
        self.btn_play = QPushButton("Play")
        self.btn_play.setObjectName("btnPlay")
        self.btn_play.clicked.connect(self.play_audio)
        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("btnSave")
        self.btn_save.clicked.connect(self.save_script)
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_play)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        
        try:
            if os.path.exists(self.script_path):
                with open(self.script_path, 'r', encoding='utf-8') as f:
                    self.text_edit.setPlainText(f.read())
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not read script file:\n{e}")

    def play_audio(self):
        text = self.text_edit.toPlainText().strip()
        if not text: return
        if not FFMPEG_PATH:
            QMessageBox.warning(self, "Error", "FFmpeg is required for audio preview.")
            return

        self.btn_play.setEnabled(False)
        self.btn_play.setText("Generating...")
        QApplication.processEvents()
        
        temp_mp3 = "temp_preview.mp3"
        temp_wav = "temp_preview.wav"
        
        def gen_and_play():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    communicate = edge_tts.Communicate(text, self.voice_id)
                    loop.run_until_complete(communicate.save(temp_mp3))
                finally:
                    loop.close()
                
                if not os.path.exists(temp_mp3): raise Exception("Failed to generate MP3")

                subprocess.run([FFMPEG_PATH, "-y", "-i", temp_mp3, "-ar", "22050", "-ac", "1", temp_wav], 
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                self.btn_play.setText("Playing...")
                if platform.system() == "Windows": os.startfile(temp_wav)
                elif platform.system() == "Darwin": subprocess.call(["open", temp_wav])
                else: subprocess.call(["xdg-open", temp_wav])
            except Exception as e:
                QMessageBox.critical(self, "TTS Error", f"Playback failed: {e}")
            finally:
                QTimer.singleShot(1000, lambda: self.reset_play_button(self))
                try:
                    if os.path.exists(temp_mp3): os.remove(temp_mp3)
                    if os.path.exists(temp_wav): os.remove(temp_wav)
                except: pass

        threading.Thread(target=gen_and_play, daemon=True).start()

    def reset_play_button(self, dlg_ref):
        dlg_ref.btn_play.setEnabled(True)
        dlg_ref.btn_play.setText("Play")

    def save_script(self):
        text = self.text_edit.toPlainText()
        try:
            with open(self.script_path, 'w', encoding='utf-8') as f: f.write(text)
            self.accept() 
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save script:\n{e}")

# --- MAIN GUI CLASS ---

class SlideCastStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        
        qInstallMessageHandler(handle_log_message)
        self.setWindowTitle("SlideCast Studio (Parallel Audio + Multi-Process Video)")
        self.resize(1600, 900)
        
        self.config = DEFAULT_CONFIG.copy()
        try:
            self.config['output_dir'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Output")
            os.makedirs(self.config['output_dir'], exist_ok=True)
        except Exception as e:
            print(f"Warning: Could not create output directory: {e}")
            
        if 'edge_voice' not in self.config:
            self.config['edge_voice'] = 'en-US-AriaNeural'
        if 'render_workers' not in self.config:
            self.config['render_workers'] = 3

        self.manifest = {}
        self.mgr = multiprocessing.Manager()
        self.msg_queue = self.mgr.Queue()
        self.executor = None
        self.is_rendering = False
        
        self.queue_timer = QTimer()
        self.queue_timer.timeout.connect(self.check_progress_queue)

        self.current_project_path = None
        self.current_slides = []
        self.current_slide_idx = 0
        
        self.editor_save_timer = QTimer()
        self.editor_save_timer.setSingleShot(True)
        self.editor_save_timer.timeout.connect(self.save_editor_content)

        # --- PARALLEL AUDIO POOL ---
        self.audio_pool = ThreadPoolExecutor(max_workers=4)
        self.audio_tasks_submitted = 0
        self.audio_tasks_completed = 0
        self.post_audio_action = None
        
        # --- MULTI-RENDERING TRACKERS ---
        self.rendering_projects_total = 0
        self.rendering_projects_active = 0
        self.task_widgets = {} # Map project_name -> TaskProgressWidget

        self.init_ui()
        self.load_manifest()
        self.scan_projects()

        if not FFMPEG_PATH:
            QMessageBox.critical(self, "Critical Error", "FFmpeg not found!\nRendering and audio processing will be disabled.")

    def closeEvent(self, event):
        if hasattr(self, 'audio_pool'):
            self.audio_pool.shutdown(wait=False)
        super().closeEvent(event)

    def create_h_line(self):
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #555;")
        return line

    def init_ui(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #cccccc; font-weight: bold; font-size: 12px; margin-top: 5px;}
            QPushButton { background: #3e3e42; border: 1px solid #555; padding: 6px 12px; border-radius: 4px; color: white; }
            QPushButton:hover { background: #505055; }
            QPushButton:disabled { background-color: #2a2a2a; color: #555; }
            QPushButton#btnStop { background-color: #d13a3a; border: 1px solid #a01010; }
            QPushButton#btnStop:hover { background-color: #e64d4d; }
            QPushButton#btnAudio { background-color: #9b59b6; border: 1px solid #8e44ad; font-weight: bold;}
            QPushButton#btnAudio:hover { background-color: #a569bd; }
            QPushButton#btnAdd { background-color: #2d8f2d; border: 1px solid #1e6b1e; }
            QPushButton#btnDelSlide { background-color: #a01010; border: 1px solid #800000; }
            QPushButton#btnEditScript { background-color: #d35400; border: 1px solid #a04000; font-weight: bold; }
            QListWidget { background: #252526; border: 1px solid #3e3e42; border-radius: 4px; color: #d4d4d4; }
            QTextEdit, QPlainTextEdit { background: #1e1e1e; color: #9cdcfe; border: 1px solid #3e3e42; font-family: Consolas; }
            QProgressBar { border: 1px solid #3e3e42; border-radius: 4px; text-align: center; color: white; background-color: #2a2a2a;}
            QProgressBar::chunk { background-color: #007acc; }
            QTabWidget::pane { border: 1px solid #3e3e42; }
            QScrollArea { border: 1px solid #3e3e42; background-color: #1e1e1e; }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        left_layout = QVBoxLayout()
        main_layout.addLayout(left_layout, stretch=1)

        grp_list = QGroupBox("Projects")
        grp_layout = QVBoxLayout()
        self.project_list = QListWidget()
        self.project_list.itemClicked.connect(self.on_project_selected)
        grp_layout.addWidget(self.project_list)
        
        btn_layout = QHBoxLayout()
        btn_new = QPushButton("New Project")
        btn_new.clicked.connect(self.create_new_project)
        btn_del = QPushButton("Delete Project")
        btn_del.clicked.connect(self.delete_project)
        btn_layout.addWidget(btn_new)
        btn_layout.addWidget(btn_del)
        grp_layout.addLayout(btn_layout)
        grp_list.setLayout(grp_layout)
        left_layout.addWidget(grp_list)

        # --- RENDERING UI ---
        grp_render = QGroupBox("Rendering Actions")
        render_layout = QVBoxLayout()
        
        lbl_sel = QLabel("<b>Selected Project:</b>")
        render_layout.addWidget(lbl_sel)

        # 1. Smart Render
        self.btn_smart_render = QPushButton("Smart Render (Audio + Video)")
        self.btn_smart_render.setStyleSheet("background-color: #27ae60; font-weight: bold; border: 1px solid #1e8449;")
        self.btn_smart_render.setToolTip("Checks for missing audio, generates it in parallel, then renders.")
        self.btn_smart_render.clicked.connect(self.auto_render_selected)
        self.btn_smart_render.setEnabled(FFMPEG_PATH is not None)
        render_layout.addWidget(self.btn_smart_render)

        # 2. Split Audio/Video
        h_layout = QHBoxLayout()
        self.btn_audio = QPushButton("1. Audio Only (Parallel)")
        self.btn_audio.setObjectName("btnAudio")
        self.btn_audio.clicked.connect(self.manual_audio_start)
        self.btn_audio.setEnabled(HAS_EDGE_TTS and FFMPEG_PATH is not None)
        
        self.btn_single = QPushButton("2. Video Only")
        self.btn_single.clicked.connect(lambda: self.start_rendering(selected_only=True))
        self.btn_single.setEnabled(FFMPEG_PATH is not None)
        
        h_layout.addWidget(self.btn_audio)
        h_layout.addWidget(self.btn_single)
        render_layout.addLayout(h_layout)

        render_layout.addWidget(self.create_h_line())

        # 3. Batch
        lbl_batch = QLabel("<b>Batch Processing:</b>")
        render_layout.addWidget(lbl_batch)
        
        self.btn_batch = QPushButton("Batch Render All (Unfinished)")
        self.btn_batch.setStyleSheet("background-color: #007acc; font-weight: bold;")
        self.btn_batch.clicked.connect(lambda: self.start_rendering())
        self.btn_batch.setEnabled(FFMPEG_PATH is not None)
        render_layout.addWidget(self.btn_batch)
        
        self.btn_stop = QPushButton("STOP / CANCEL")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.clicked.connect(self.stop_rendering)
        self.btn_stop.setEnabled(False)
        render_layout.addWidget(self.btn_stop)
        
        self.status_label = QLabel("Ready")
        render_layout.addWidget(self.status_label)
        
        # --- TASK PROGRESS SCROLL AREA ---
        self.task_scroll = QScrollArea()
        self.task_scroll.setWidgetResizable(True)
        self.task_scroll.setFixedHeight(150)
        self.task_container = QWidget()
        self.task_layout = QVBoxLayout()
        self.task_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.task_container.setLayout(self.task_layout)
        self.task_scroll.setWidget(self.task_container)
        
        render_layout.addWidget(self.task_scroll)
        
        grp_render.setLayout(render_layout)
        left_layout.addWidget(grp_render)
        
        ctrl_layout = QHBoxLayout()
        btn_set = QPushButton("Settings")
        btn_set.clicked.connect(self.open_settings)
        btn_out = QPushButton("Output Folder")
        btn_out.clicked.connect(self.open_output_folder)
        ctrl_layout.addWidget(btn_set)
        ctrl_layout.addWidget(btn_out)
        left_layout.addLayout(ctrl_layout)
        
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(100)
        left_layout.addWidget(self.log)

        # RIGHT PANEL
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(right_splitter, stretch=3)

        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        
        nav_layout = QHBoxLayout()
        self.btn_prev = QPushButton("< Prev")
        self.btn_prev.clicked.connect(self.prev_slide)
        self.lbl_slide_info = QLabel("Preview: No Project")
        self.lbl_slide_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_next = QPushButton("Next >")
        self.btn_next.clicked.connect(self.next_slide)
        
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.lbl_slide_info, stretch=1)
        nav_layout.addWidget(self.btn_next)
        
        slide_actions = QHBoxLayout()
        btn_add_slide = QPushButton("+ Add Slide")
        btn_add_slide.setObjectName("btnAdd")
        btn_add_slide.clicked.connect(self.add_slide)
        btn_edit_script = QPushButton("Edit Script")
        btn_edit_script.setObjectName("btnEditScript")
        btn_edit_script.clicked.connect(self.open_script_editor)
        btn_del_slide = QPushButton("- Delete Slide")
        btn_del_slide.setObjectName("btnDelSlide")
        btn_del_slide.clicked.connect(self.delete_slide)
        
        slide_actions.addWidget(btn_add_slide)
        slide_actions.addWidget(btn_edit_script)
        slide_actions.addWidget(btn_del_slide)

        self.web = QWebEngineView()
        preview_layout.addLayout(nav_layout)
        preview_layout.addLayout(slide_actions)
        preview_layout.addWidget(self.web)
        
        right_splitter.addWidget(preview_widget)

        self.tabs = QTabWidget()
        self.html_editor = QPlainTextEdit()
        self.script_editor = QPlainTextEdit()
        
        self.tabs.addTab(self.html_editor, "HTML Source")
        self.tabs.addTab(self.script_editor, "TTS Script")
        
        self.html_editor.textChanged.connect(lambda: self.editor_save_timer.start(500))
        self.script_editor.textChanged.connect(lambda: self.editor_save_timer.start(500))
        
        right_splitter.addWidget(self.tabs)
        right_splitter.setSizes([500, 300])

    # --- SMART RENDER LOGIC ---

    def auto_render_selected(self):
        if not self.current_project_path:
            QMessageBox.warning(self, "Error", "Select a project first.")
            return
        if self.is_rendering:
            QMessageBox.warning(self, "Busy", "Already rendering.")
            return

        files = sorted(glob.glob(os.path.join(self.current_project_path, "slide*.html")), key=natural_sort_key)
        missing_audio = False
        for f in files:
            wav_path = os.path.splitext(f)[0] + ".wav"
            if not os.path.exists(wav_path):
                missing_audio = True
                break
        
        if missing_audio:
            reply = QMessageBox.question(
                self, 
                "Missing Audio", 
                "This project is missing audio files. Generate them now and then render?", 
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.log_msg("Smart Render: Generating audio first...")
                self.post_audio_action = lambda: self.start_rendering(selected_only=True)
                self.start_auto_audio()
            else:
                self.log_msg("Smart Render: Skipping audio generation.")
                self.start_rendering(selected_only=True)
        else:
            self.log_msg("Smart Render: Audio found. Starting video render...")
            self.start_rendering(selected_only=True)

    def manual_audio_start(self):
        """Called when user clicks 'Audio Only' button"""
        self.post_audio_action = None
        self.start_auto_audio()

    # --- PARALLEL AUDIO GENERATION ---

    def start_auto_audio(self):
        if not self.current_project_path:
            QMessageBox.warning(self, "Error", "Select a project first.")
            return
        if self.is_rendering:
            QMessageBox.warning(self, "Busy", "Cannot generate audio while rendering.")
            return
        if not FFMPEG_PATH:
            QMessageBox.critical(self, "Error", "Edge-TTS requires FFmpeg to convert MP3 to WAV.")
            return

        self.edge_voice = self.config.get('edge_voice', 'en-US-AriaNeural')

        self.audio_queue = []
        try:
            files = sorted(glob.glob(os.path.join(self.current_project_path, "slide*.html")), key=natural_sort_key)
            for html_file in files:
                txt_file = os.path.splitext(html_file)[0] + ".txt"
                wav_file = os.path.splitext(html_file)[0] + ".wav"
                self.audio_queue.append({'txt': txt_file, 'wav': wav_file})
        except Exception as e:
            self.log_msg(f"Error scanning project files: {e}")
            return

        if not self.audio_queue:
            QMessageBox.information(self, "Info", "No slides with scripts found.")
            return

        self.audio_tasks_submitted = len(self.audio_queue)
        self.audio_tasks_completed = 0
        self.btn_audio.setEnabled(False)
        
        self.status_label.setText(f"Generating Audio: 0 / {self.audio_tasks_submitted}")
        
        self.log_msg(f"Starting PARALLEL audio generation for {self.audio_tasks_submitted} slides...")
        
        for item in self.audio_queue:
            future = self.audio_pool.submit(self.generate_audio_task, item)
            future.add_done_callback(self.on_audio_task_done)
            
    def generate_audio_task(self, item):
        txt_path = item['txt']
        wav_path = item['wav']
        mp3_path = wav_path.replace(".wav", ".mp3")

        try:
            if os.path.exists(mp3_path):
                try: os.remove(mp3_path)
                except: pass
            if os.path.exists(wav_path):
                try: os.remove(wav_path)
                except: pass

            if os.path.exists(txt_path):
                with open(txt_path, "r", encoding="utf-8") as f:
                    text = f.read()
                
                if text.strip():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        communicate = edge_tts.Communicate(text, self.edge_voice)
                        loop.run_until_complete(
                            asyncio.wait_for(communicate.save(mp3_path), timeout=60.0)
                        )
                    except asyncio.TimeoutError:
                        pass 
                    except Exception as e:
                        print(f"TTS Error: {e}")
                    finally:
                        try:
                            loop.run_until_complete(loop.shutdown_asyncgens())
                        except: pass
                        loop.close()
                    
                    if os.path.exists(mp3_path):
                        try:
                            subprocess.run([
                                FFMPEG_PATH, "-y", "-i", mp3_path, 
                                "-ar", "22050", "-ac", "1", wav_path
                            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                            os.remove(mp3_path)
                        except Exception:
                            pass
        except Exception as e:
            print(f"Thread crash: {e}")

    def on_audio_task_done(self, future):
        try:
            future.result()
        except:
            pass
        self.audio_tasks_completed += 1
        QTimer.singleShot(0, self.update_audio_progress_ui)

    def update_audio_progress_ui(self):
        self.status_label.setText(f"Generating Audio: {self.audio_tasks_completed} / {self.audio_tasks_submitted}")

        if self.audio_tasks_completed >= self.audio_tasks_submitted:
            self.log_msg("Audio generation complete!")
            self.btn_audio.setEnabled(True)
            self.status_label.setText("Audio Ready")
            
            if self.post_audio_action:
                action = self.post_audio_action
                self.post_audio_action = None
                action()

    def create_silent_wav(self, path, duration):
        try:
            with wave.open(path, 'w') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(22050)
                num_samples = int(duration * 22050)
                data = struct.pack('<' + 'h' * num_samples, *[0] * num_samples)
                wav_file.writeframes(data)
        except Exception as e:
            self.log_msg(f"Warning: Could not create silent wav {path}: {e}")
    
    # --- UI LOGIC (Standard) ---
    
    def save_editor_content(self):
        if not self.current_project_path or self.is_rendering: return
        if not self.current_slides: return
        current_file = self.current_slides[self.current_slide_idx]
        base = os.path.splitext(current_file)[0]
        try:
            with open(current_file, "w", encoding="utf-8") as f: f.write(self.html_editor.toPlainText())
            with open(base + ".txt", "w", encoding="utf-8") as f: f.write(self.script_editor.toPlainText())
        except Exception as e: 
            self.log_msg(f"Error saving files: {e}")

    def update_editors(self):
        if not self.current_slides: return
        self.html_editor.blockSignals(True)
        self.script_editor.blockSignals(True)
        try:
            current_file = self.current_slides[self.current_slide_idx]
            with open(current_file, "r", encoding="utf-8") as f: self.html_editor.setPlainText(f.read())
            txt_file = os.path.splitext(current_file)[0] + ".txt"
            if os.path.exists(txt_file):
                with open(txt_file, "r", encoding="utf-8") as f: self.script_editor.setPlainText(f.read())
            else: self.script_editor.setPlainText("")
        except Exception as e:
            self.log_msg(f"Error loading editor content: {e}")
        finally:
            self.html_editor.blockSignals(False)
            self.script_editor.blockSignals(False)

    def add_slide(self):
        if not self.current_project_path: return
        try:
            nums = []
            files = sorted(glob.glob(os.path.join(self.current_project_path, "slide*.html")), key=natural_sort_key)
            for f in files:
                m = re.search(r'slide(\d+)\.html', os.path.basename(f))
                if m: nums.append(int(m.group(1)))
            next_num = max(nums) + 1 if nums else 1
            new_html = os.path.join(self.current_project_path, f"slide{next_num}.html")
            new_txt = os.path.join(self.current_project_path, f"slide{next_num}.txt")
            html = f"<!DOCTYPE html><html><head><style>body {{ background-color: #222; color: white; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }} h1 {{ font-size: 4em; }}</style></head><body><h1>Slide {next_num}</h1></body></html>"
            with open(new_html, "w", encoding="utf-8") as f: f.write(html)
            with open(new_txt, "w", encoding="utf-8") as f: f.write(f"Slide {next_num} script.")
            self.refresh_current_project()
            self.log_msg(f"Added slide {next_num}")
        except Exception as e:
            self.log_msg(f"Failed to add slide: {e}")

    def delete_slide(self):
        if not self.current_slides: return
        if len(self.current_slides) == 1: return QMessageBox.warning(self, "Warning", "Cannot delete the last slide.")
        reply = QMessageBox.question(self, "Confirm", "Delete current slide?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                os.remove(self.current_slides[self.current_slide_idx])
                txt = os.path.splitext(self.current_slides[self.current_slide_idx])[0] + ".txt"
                if os.path.exists(txt): os.remove(txt)
                self.refresh_current_project()
            except Exception as e: 
                self.log_msg(f"Error deleting slide: {e}")

    def refresh_current_project(self):
        try:
            self.current_slides = sorted(glob.glob(os.path.join(self.current_project_path, "slide*.html")), key=natural_sort_key)
            self.current_slide_idx = min(self.current_slide_idx, len(self.current_slides) - 1)
            self.update_preview_controls()
            self.load_slide_content()
            self.update_editors()
        except Exception as e:
            self.log_msg(f"Error refreshing project: {e}")

    def on_project_selected(self, item):
        try:
            name = item.text().replace(" (Completed)", "").strip()
            base_dir = os.path.dirname(os.path.abspath(__file__))
            pres_dir = os.path.join(base_dir, "Presentations")
            self.current_project_path = os.path.join(pres_dir, name)
            self.refresh_current_project()
        except Exception as e:
            self.log_msg(f"Error selecting project: {e}")

    def update_preview_controls(self):
        count = len(self.current_slides)
        if count > 0:
            self.lbl_slide_info.setText(f"Slide {self.current_slide_idx + 1} / {count}")
            self.btn_prev.setEnabled(self.current_slide_idx > 0)
            self.btn_next.setEnabled(self.current_slide_idx < count - 1)
            enabled = not self.is_rendering
            self.html_editor.setEnabled(enabled)
            self.script_editor.setEnabled(enabled)
        else:
            self.lbl_slide_info.setText("No Slides")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.html_editor.setEnabled(False)
            self.script_editor.setEnabled(False)

    def load_slide_content(self):
        if not self.current_slides: return
        try:
            html_file = self.current_slides[self.current_slide_idx]
            with open(html_file, 'r', encoding="utf-8") as f: html = f.read()
            def replacer(match):
                url = match.group(1)
                if not (url.startswith('http') or url.startswith('data')):
                    abs_path = os.path.abspath(os.path.join(os.path.dirname(html_file), url))
                    return f'file:///{abs_path.replace(os.sep, "/")}'
                return match.group(0)
            html = re.sub(r'src="(.*?)"', replacer, html, flags=re.IGNORECASE)
            self.web.setHtml(html)
        except Exception as e:
            self.log_msg(f"Error loading slide preview: {e}")

    def prev_slide(self):
        if self.current_slide_idx > 0:
            self.current_slide_idx -= 1
            self.update_preview_controls()
            self.load_slide_content()
            self.update_editors()

    def next_slide(self):
        if self.current_slide_idx < len(self.current_slides) - 1:
            self.current_slide_idx += 1
            self.update_preview_controls()
            self.load_slide_content()
            self.update_editors()
            
    def create_new_project(self):
        name, ok = QInputDialog.getText(self, "New Project", "Project Name:")
        if ok and name:
            safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            if not safe_name: return
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                pres_dir = os.path.join(base_dir, "Presentations")
                project_path = os.path.join(pres_dir, safe_name)
                if os.path.exists(project_path): 
                    QMessageBox.warning(self, "Error", "Project already exists.")
                    return
                os.makedirs(project_path)
                html = f"<!DOCTYPE html><html><head><style>body {{ background-color: #222; color: white; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; flex-direction: column; }} h1 {{ font-size: 5em; margin: 0; }} h2 {{ font-size: 2em; color: #aaa; margin-top: 10px; }}</style></head><body><h1>{safe_name}</h1><h2>Slide 1</h2></body></html>"
                with open(os.path.join(project_path, "slide1.html"), "w", encoding="utf-8") as f: f.write(html)
                with open(os.path.join(project_path, "slide1.txt"), "w", encoding="utf-8") as f: f.write(f"Welcome to {safe_name}.")
                
                self.scan_projects()
                self.log_msg(f"Created {safe_name}")
                items = self.project_list.findItems(safe_name, Qt.MatchFlag.MatchExactly)
                if items: self.project_list.setCurrentItem(items[0])
            except Exception as e:
                self.log_msg(f"Failed to create project: {e}")

    def delete_project(self):
        item = self.project_list.currentItem()
        if not item: return
        name = item.text().replace(" (Completed)", "").strip()
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Presentations", name)
        if QMessageBox.question(self, "Delete", f"Delete {name}?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                shutil.rmtree(path)
                self.scan_projects()
                self.web.setHtml("")
                self.current_slides = []
                self.html_editor.setPlainText("")
                self.script_editor.setPlainText("")
            except Exception as e:
                self.log_msg(f"Failed to delete project: {e}")

    def scan_projects(self):
        self.project_list.clear()
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            pres_dir = os.path.join(base_dir, "Presentations")
            os.makedirs(pres_dir, exist_ok=True)
            folders = sorted([f for f in os.listdir(pres_dir) if os.path.isdir(os.path.join(pres_dir, f))])
            for f in folders:
                item = QListWidgetItem(f)
                if self.manifest.get(f, {}).get("status") == "Done":
                    item.setBackground(QColor("#1e3a1e"))
                    item.setText(f"{f} (Completed)")
                self.project_list.addItem(item)
            self.log_msg(f"Found {len(folders)} projects.")
        except Exception as e:
            self.log_msg(f"Error scanning projects: {e}")

    def load_manifest(self):
        m_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Presentations", "manifest.json")
        if os.path.exists(m_path):
            try: 
                with open(m_path, 'r') as f: self.manifest = json.load(f)
            except: pass

    def save_manifest(self):
        m_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Presentations", "manifest.json")
        try: 
            with open(m_path, 'w') as f: json.dump(self.manifest, f, indent=4)
        except: pass

    def log_msg(self, m):
        t = time.strftime("%H:%M:%S")
        self.log.append(f"[{t}] {m}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self.config = dlg.get_config()
            self.log_msg(f"Settings updated.")

    def open_output_folder(self):
        path = self.config['output_dir']
        if not os.path.exists(path):
            QMessageBox.warning(self, "Error", "Output folder does not exist.")
            return
        if platform.system() == "Windows": os.startfile(path)
        elif platform.system() == "Darwin": subprocess.Popen(["open", path])
        else: subprocess.Popen(["xdg-open", path])

    def open_script_editor(self):
        if not self.current_project_path or not self.current_slides: return
        try:
            current_file = self.current_slides[self.current_slide_idx]
            script_file = os.path.splitext(current_file)[0] + ".txt"
            voice_id = self.config.get('edge_voice', 'en-US-AriaNeural')
            dlg = ScriptEditorDialog(script_file, voice_id=voice_id, parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.update_editors()
                self.log_msg(f"Script updated for Slide {self.current_slide_idx + 1}")
        except Exception as e:
            self.log_msg(f"Error opening script editor: {e}")

    # --- RENDERING LOGIC (MULTI-PROCESSING) ---
    
    def start_rendering(self, selected_only=False):
        if not FFMPEG_PATH:
            QMessageBox.critical(self, "Error", "FFmpeg is not installed or not found in PATH.")
            return
        if not HAS_PLAYWRIGHT:
            QMessageBox.critical(self, "Error", "Playwright is not installed. Run 'pip install playwright && playwright install chromium'")
            return

        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            pres_dir = os.path.join(base_dir, "Presentations")
            all_folders = [os.path.join(pres_dir, f) for f in os.listdir(pres_dir) if os.path.isdir(os.path.join(pres_dir, f))]
            render_queue = []
            
            if selected_only:
                item = self.project_list.currentItem()
                if item:
                    name = item.text().replace(" (Completed)", "").strip()
                    folder = os.path.join(pres_dir, name)
                    if name in self.manifest: del self.manifest[name]
                    render_queue.append(folder)
            else:
                for folder in all_folders:
                    name = os.path.basename(folder)
                    if self.manifest.get(name, {}).get("status") != "Done":
                        render_queue.append(folder)

            if not render_queue:
                QMessageBox.information(self, "Info", "Nothing to render.")
                return

            workers = self.config.get('render_workers', 3)
            self.rendering_projects_total = len(render_queue)
            self.rendering_projects_done = 0
            
            self.log_msg(f"Starting render with {workers} parallel worker(s) for {len(render_queue)} projects...")
            
            self.is_rendering = True
            self.update_preview_controls()
            
            self.btn_batch.setEnabled(False)
            self.btn_single.setEnabled(False)
            self.btn_smart_render.setEnabled(False)
            self.btn_audio.setEnabled(False)
            self.btn_stop.setEnabled(True)
            
            # --- SETUP INDIVIDUAL TASK WIDGETS ---
            # Clear old widgets
            for i in reversed(range(self.task_layout.count())): 
                self.task_layout.itemAt(i).widget().setParent(None)
            self.task_widgets = {}
            
            for folder_path in render_queue:
                project_name = os.path.basename(folder_path)
                widget = TaskProgressWidget(project_name)
                self.task_layout.addWidget(widget)
                self.task_widgets[project_name] = widget
            
            while not self.msg_queue.empty(): self.msg_queue.get_nowait()

            self.queue_timer.start(100)
            
            self.executor = ProcessPoolExecutor(max_workers=workers)
            self.futures = {self.executor.submit(render_project_worker, f, self.msg_queue, self.config): f for f in render_queue}

            self.monitor_timer = QTimer()
            self.monitor_timer.timeout.connect(self.check_futures)
            self.monitor_timer.start(200)
            
        except Exception as e:
            self.log_msg(f"Failed to start rendering: {e}")
            self.is_rendering = False
            self.update_preview_controls()

    def stop_rendering(self):
        if self.executor:
            self.log_msg("Stopping...")
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.monitor_timer.stop()
            self.queue_timer.stop()
            self.is_rendering = False
            self.update_preview_controls()
            
            self.btn_batch.setEnabled(True)
            self.btn_single.setEnabled(True)
            self.btn_smart_render.setEnabled(True)
            self.btn_audio.setEnabled(HAS_EDGE_TTS)
            self.btn_stop.setEnabled(False)
            self.status_label.setText("Stopped.")

    def check_futures(self):
        if not self.futures: return
        for future in list(self.futures.keys()):
            if future.done():
                folder = self.futures.pop(future)
                name = os.path.basename(folder)
                self.rendering_projects_done += 1
                try:
                    result = future.result()
                    self.log_msg(f"Finished: {name}")
                    self.manifest[name] = {"status": "Done", "timestamp": time.time()}
                    self.save_manifest()
                    # Mark widget complete
                    if name in self.task_widgets:
                        self.task_widgets[name].mark_complete(True)
                except Exception as e:
                    self.log_msg(f"<span style='color:#ff6b6b'>Failed: {name} - {e}</span>")
                    if name in self.task_widgets:
                        self.task_widgets[name].mark_complete(False)

        if not self.futures:
            self.monitor_timer.stop()
            self.queue_timer.stop()
            self.is_rendering = False
            self.update_preview_controls()
            self.btn_batch.setEnabled(True)
            self.btn_single.setEnabled(True)
            self.btn_smart_render.setEnabled(True)
            self.btn_audio.setEnabled(HAS_EDGE_TTS)
            self.btn_stop.setEnabled(False)
            self.status_label.setText("Complete!")
            self.scan_projects()

    def check_progress_queue(self):
        while not self.msg_queue.empty():
            try:
                msg = self.msg_queue.get_nowait()
                if msg[0] == "ERROR":
                    self.log_msg(f"<span style='color:#ff6b6b'>{msg[1]}</span>")
                    continue
                project, current, total = msg
                
                # Update specific widget
                if project in self.task_widgets:
                    status_text = ""
                    if isinstance(current, str):
                        status_text = current
                        # Reset bar to busy if status is string
                        self.task_widgets[project].bar.setRange(0, 0)
                    elif isinstance(current, int):
                        # Already handled by update_status logic inside widget
                        pass
                    
                    self.task_widgets[project].update_status(current, total, status_text)
                
                # Also update global status label (optional, keeps general feedback)
                if isinstance(current, str):
                    self.status_label.setText(f"Active | {project}: {current}")
                elif isinstance(current, int):
                    self.status_label.setText(f"Active | {project}: {current}/{total}")
                    
            except: break

# --- WORKER FUNCTION (PLAYWRIGHT VERSION) ---

def render_project_worker(project_path, msg_queue, config):
    async def run_async_worker():
        project_name = os.path.basename(project_path)
        temp_dir = os.path.join(config['output_dir'], "temp", project_name)
        
        try:
            os.makedirs(temp_dir, exist_ok=True)
        except Exception as e:
            msg_queue.put(("ERROR", f"Cannot create temp dir: {e}"))
            return

        final_video = os.path.join(config['output_dir'], project_name + ".mp4")
        transition_duration = config.get('transition_duration', 0.5) 
        transition_frames = int(transition_duration * config['fps'])

        ffmpeg_proc = None

        try:
            msg_queue.put((project_name, "PREPARING AUDIO", 0))
            try:
                html_files = sorted(glob.glob(os.path.join(project_path, "slide*.html")), key=natural_sort_key)
            except Exception as e:
                msg_queue.put(("ERROR", f"Failed to scan slides: {e}"))
                return
            
            if not html_files:
                msg_queue.put(("ERROR", "No slides found."))
                return

            timeline = []
            
            def create_silent_wav(path, duration):
                try:
                    with wave.open(path, 'w') as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(22050)
                        num_samples = int(duration * 22050)
                        data = struct.pack('<' + 'h' * num_samples, *[0] * num_samples)
                        wav_file.writeframes(data)
                except Exception as e:
                    print(f"Warning: Silent wav gen failed: {e}")

            for i, html_file in enumerate(html_files):
                match = re.search(r'slide(\d+)\.html', os.path.basename(html_file))
                slide_num = match.group(1) if match else str(i+1)
                
                source_wav = os.path.join(project_path, f"slide{slide_num}.wav")
                txt_file = os.path.splitext(html_file)[0] + ".txt"
                target_audio = os.path.join(temp_dir, f"a{i}.wav")
                
                duration = 3.0
                
                if os.path.exists(source_wav):
                    try:
                        shutil.copy(source_wav, target_audio)
                        with wave.open(target_audio, 'r') as w:
                            frames = w.getnframes()
                            rate = w.getframerate()
                            duration = frames / float(rate)
                    except Exception as e:
                        print(f"Error reading WAV: {e}. Falling back to text.")
                        duration = 3.0
                        create_silent_wav(target_audio, duration)
                else:
                    script = ""
                    if os.path.exists(txt_file):
                        try:
                            with open(txt_file, "r", encoding="utf-8") as f:
                                script = f.read()
                        except: pass
                    words = len(script.split())
                    duration = max(3.0, words / 2.5)
                    create_silent_wav(target_audio, duration)

                timeline.append({
                    'html': html_file,
                    'audio': target_audio,
                    'duration': duration
                })

            msg_queue.put((project_name, "RENDERING VIDEO", 0))
            raw_video = os.path.join(temp_dir, "video_raw.mp4")
            
            enc = config['encoder']
            if enc == "auto": enc = detect_encoder()

            cmd = [
                FFMPEG_PATH, "-y",
                "-f", "rawvideo", "-vcodec", "rawvideo",
                "-pix_fmt", "rgb24", "-s", f"{config['width']}x{config['height']}",
                "-r", str(config['fps']), "-i", "-",
                "-c:v", enc, "-preset", "fast",
                "-pix_fmt", "yuv420p", "-crf", "23", raw_video
            ]
            
            try:
                ffmpeg_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            except Exception as e:
                msg_queue.put(("ERROR", f"FFmpeg Start Failed: {e}"))
                return

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_viewport_size({"width": config['width'], "height": config['height']})
                
                total_slides = len(timeline)
                msg_queue.put((project_name, 0, total_slides))

                def capture_frame_from_bytes(img_bytes):
                    try:
                        img = Image.open(io.BytesIO(img_bytes))
                        if img.mode == 'RGBA': img = img.convert('RGB')
                        elif img.mode != 'RGB': img = img.convert('RGB')
                        return np.array(img)
                    except:
                        return np.zeros((config['height'], config['width'], 3), dtype=np.uint8)

                for i, slide_data in enumerate(timeline):
                    try:
                        abs_path = os.path.abspath(slide_data['html'])
                        file_url = f"file:///{abs_path.replace(os.sep, '/')}"
                        
                        await page.goto(file_url, wait_until="networkidle")
                        img_bytes = await page.screenshot(type="png")
                        img_current = capture_frame_from_bytes(img_bytes)

                        duration = slide_data['duration']
                        is_last = (i == total_slides - 1)
                        
                        if is_last:
                            static_frames = int(math.ceil(duration * config['fps']))
                        else:
                            static_frames = int(math.ceil((duration - transition_duration) * config['fps']))
                            if static_frames < 0: static_frames = 0

                        for _ in range(static_frames):
                            try:
                                ffmpeg_proc.stdin.write(img_current.tobytes())
                            except BrokenPipeError:
                                msg_queue.put(("ERROR", "FFmpeg pipe broken."))
                                raise SystemExit

                        if not is_last:
                            next_data = timeline[i+1]
                            abs_path_next = os.path.abspath(next_data['html'])
                            file_url_next = f"file:///{abs_path_next.replace(os.sep, '/')}"
                            
                            await page.goto(file_url_next, wait_until="networkidle")
                            img_bytes_next = await page.screenshot(type="png")
                            img_next = capture_frame_from_bytes(img_bytes_next)

                            try:
                                for t in range(transition_frames):
                                    alpha = t / transition_frames
                                    blended = (img_current * (1.0 - alpha) + img_next * alpha).astype(np.uint8)
                                    try:
                                        ffmpeg_proc.stdin.write(blended.tobytes())
                                    except BrokenPipeError:
                                        return False
                            except: return False

                        msg_queue.put((project_name, i + 1, total_slides))

                    except SystemExit:
                        raise
                    except Exception as e:
                        msg_queue.put(("ERROR", f"Render Loop Error (Slide {i+1}): {e}"))
                        raise
                
                await browser.close()

        except Exception as e:
            err_trace = traceback.format_exc()
            msg_queue.put(("ERROR", f"CRITICAL WORKER FAILURE:\n{err_trace}"))
        
        finally:
            if ffmpeg_proc:
                try:
                    if ffmpeg_proc.stdin: ffmpeg_proc.stdin.close()
                    ffmpeg_proc.wait(timeout=5)
                    if ffmpeg_proc.returncode != 0:
                        stderr_output = ffmpeg_proc.stderr.read().decode('utf-8', errors='ignore')
                        if stderr_output:
                            msg_queue.put(("ERROR", f"FFmpeg Error: {stderr_output[-300:]}"))
                except Exception as e:
                    msg_queue.put(("ERROR", f"Cleanup Error: {e}"))

        msg_queue.put((project_name, "FINALIZING", 0))
        try:
            audio_files = [s['audio'] for s in timeline]
            listfile = os.path.join(temp_dir, "audio_list.txt")
            with open(listfile, "w") as f:
                for a in audio_files:
                    f.write(f"file '{os.path.abspath(a).replace(os.sep, '/')}'\n")
            
            audio_full = os.path.join(temp_dir, "audio_full.wav")
            res = subprocess.run([FFMPEG_PATH, "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", audio_full], 
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                 msg_queue.put(("ERROR", f"Audio concat failed: {res.stderr[-200:]}"))
            
            res = subprocess.run([FFMPEG_PATH, "-y", "-i", raw_video, "-i", audio_full, 
                            "-c:v", "copy", "-c:a", "aac", "-shortest", final_video], 
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                 msg_queue.put(("ERROR", f"Final Mux failed: {res.stderr[-200:]}"))

        except Exception as e:
            msg_queue.put(("ERROR", f"Muxing Phase Failed: {e}"))

        return project_name

    try:
        asyncio.run(run_async_worker())
    except Exception as e:
        msg_queue.put(("ERROR", f"Async Wrapper Failed: {e}"))

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = SlideCastStudio()
    window.show()
    sys.exit(app.exec())