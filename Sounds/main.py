# main.py
import sys
import os
import shutil
import subprocess
import multiprocessing
import time
import logging
import asyncio
import math
import re
import glob
from logging.handlers import RotatingFileHandler
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QSpinBox, QDoubleSpinBox, 
                             QProgressBar, QGroupBox, QFormLayout, QLineEdit,
                             QMessageBox, QTextEdit, QFileDialog, QCheckBox, QComboBox)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont

# Import local modules
from config import AppConfig
from dialogs import SettingsDialog, QTextEditLogger
from engines import render_project_worker
from utils import logger, detect_ffmpeg, natural_sort_key
from syllables import generate_random_item, word_to_ipa
from constants import EDGE_VOICES, EDGE_TONES, AZURE_REGIONS, AZURE_STYLES, LANGUAGES

# --- CSS STYLES ---
STYLESHEET = """
    QMainWindow, QDialog { background-color: #1e1e1e; color: #ffffff; font-family: 'Segoe UI', sans-serif; }
    QWidget { background-color: transparent; color: #e0e0e0; }
    QPushButton { 
        background-color: #333333; border: 1px solid #555555; color: #ffffff; 
        padding: 8px 16px; border-radius: 6px; font-weight: 600; min-height: 20px;
    }
    QPushButton:hover { background-color: #444444; border-color: #888888; }
    QPushButton:pressed { background-color: #222222; }
    QPushButton:disabled { background-color: #2a2a2a; color: #666666; border-color: #333333; }
    QPushButton#btnStop { background-color: #c62828; border-color: #e53935; }
    QPushButton#btnStop:hover { background-color: #d32f2f; }
    QPushButton#btnGreen { background-color: #2e7d32; border-color: #43a047; }
    QPushButton#btnGreen:hover { background-color: #388e3c; }
    QPushButton#btnBlue { background-color: #0277bd; border-color: #039be5; }
    QPushButton#btnBlue:hover { background-color: #0288d1; }
    QPushButton#btnSmall { padding: 4px 8px; font-size: 11px; } 
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox { 
        background-color: #2d2d2d; color: #ffffff; border: 1px solid #555555; 
        padding: 6px; border-radius: 4px; selection-background-color: #0078d4;
    }
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #0078d4; }
    QCheckBox { color: #e0e0e0; spacing: 5px; }
    QCheckBox::indicator { width: 18px; height: 18px; }
    QLabel { color: #e0e0e0; }
    QGroupBox { 
        border: 1px solid #444444; margin-top: 12px; padding-top: 10px; 
        font-weight: bold; border-radius: 4px;
    }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #ffffff; }
    QProgressBar { 
        border: 1px solid #444444; border-radius: 4px; text-align: center; 
        color: white; background-color: #333333;
    }
    QProgressBar::chunk { background-color: #0078d4; border-radius: 3px; }

    QComboBox#combo_sequence {
        background-color: #383838; 
        color: #ffffff;
        border: 2px solid #00d4ff; 
        padding: 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 13px;
    }

    /* Dropdown visibility fix for Dark Mode */
    QComboBox QAbstractItemView {
        background-color: #2d2d30; 
        color: #ffffff; 
        selection-background-color: #0078d4; 
        selection-color: white; 
        border: 1px solid #555;
    }
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = AppConfig()
        
        # --- Automatic Root Folder Setup ---
        # The root folder for presentations is now fixed to a "Presentations" folder next to the script.
        self.presentations_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Presentations")
        os.makedirs(self.presentations_root, exist_ok=True)
        
        self.output_dir = self.config.get('output_dir', 'Output')
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
        os.makedirs(self.template_dir, exist_ok=True)

        # --- Parallelism Variables ---
        self.max_workers = 1 
        self.active_processes = {}  
        self.pending_projects = [] 
        self.render_queue = multiprocessing.Queue()
        
        self.init_ui()
        self.setup_logger()
        self.cleanup_all_temp_files()
        
        self.queue_timer = QTimer()
        self.queue_timer.timeout.connect(self.process_queue)
        self.queue_timer.start(100)
        
        self.scheduler_timer = QTimer()
        self.scheduler_timer.timeout.connect(self.schedule_jobs)

    def init_ui(self):
        self.setWindowTitle("Syllable & Word Video Generator")
        self.resize(950, 820) 
        self.setStyleSheet(STYLESHEET)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # --- Left Panel: Configuration ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # 1. Language Settings
        grp_lang = QGroupBox("Language Settings")
        layout_lang = QVBoxLayout()
        
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Target Language:"))
        self.combo_language = QComboBox()
        for code, name in LANGUAGES.items():
            self.combo_language.addItem(name, code)
        self.combo_language.setCurrentIndex(0) # Default English
        self.combo_language.currentIndexChanged.connect(self.on_language_changed)
        lang_layout.addWidget(self.combo_language)
        
        self.lbl_language_note = QLabel("TTS and random generation will use this language.")
        self.lbl_language_note.setWordWrap(True)
        self.lbl_language_note.setStyleSheet("color: #888; font-style: italic; font-size: 11px;")
        
        layout_lang.addLayout(lang_layout)
        layout_lang.addWidget(self.lbl_language_note)
        grp_lang.setLayout(layout_lang)
        left_layout.addWidget(grp_lang)

        # 2. Generation Settings
        grp_gen = QGroupBox("Generation Settings")
        form_gen = QFormLayout()
        
        self.spin_batch = QSpinBox()
        self.spin_batch.setRange(1, 100)
        self.spin_batch.setValue(1)
        self.spin_batch.setToolTip("How many items to group into ONE slide.")
        
        self.combo_sequence = QComboBox()
        self.combo_sequence.setObjectName("combo_sequence") 
        self.combo_sequence.addItems([
            "Random Syllables (TTS + IPA)", 
            "Random Words (TTS + IPA)", 
            "Word List (Text File + IPA)",
            "Presentations Folder (slideX.txt)", 
        ])
        self.combo_sequence.setToolTip("Select the content source.")
        self.combo_sequence.currentIndexChanged.connect(self.on_sequence_changed)
        
        self.lbl_count = QLabel("Calculating...")
        
        # Dynamic Description Label
        self.lbl_mode_description = QLabel("Select a mode above to see details.")
        self.lbl_mode_description.setWordWrap(True)
        self.lbl_mode_description.setStyleSheet("color: #00d4ff; font-size: 12px; margin-top: 5px;")

        form_gen.addRow("Items Per Slide:", self.spin_batch)
        form_gen.addRow("Content Source:", self.combo_sequence)
        form_gen.addRow(self.lbl_mode_description)
        form_gen.addRow("Total Slides:", self.lbl_count)
        
        grp_gen.setLayout(form_gen)
        left_layout.addWidget(grp_gen)

        # 3. Random Slides Control
        self.grp_random_settings = QGroupBox("Random Settings")
        form_rand = QFormLayout()
        self.spin_random_slides = QSpinBox()
        self.spin_random_slides.setRange(1, 10000)
        self.spin_random_slides.setValue(50)
        self.spin_random_slides.setToolTip("How many random slides to generate.")
        form_rand.addRow("Total Random Slides:", self.spin_random_slides)
        self.grp_random_settings.setLayout(form_rand)
        left_layout.addWidget(self.grp_random_settings)
        self.grp_random_settings.setVisible(True)

        # 4. Word List Configuration
        self.grp_word_list = QGroupBox("Word List Input")
        layout_word_list = QVBoxLayout()
        
        self.input_word_list = QTextEdit()
        self.input_word_list.setPlaceholderText("Paste words here (one per line or comma separated)...")
        self.input_word_list.setMaximumHeight(100)
        
        btn_layout = QHBoxLayout()
        self.btn_load_words = QPushButton("Load from .txt File")
        self.btn_load_words.setMaximumWidth(150)
        self.btn_load_words.clicked.connect(self.load_words_from_file)
        btn_layout.addWidget(self.btn_load_words)
        btn_layout.addStretch()
        
        layout_word_list.addWidget(self.input_word_list)
        layout_word_list.addLayout(btn_layout)
        self.grp_word_list.setLayout(layout_word_list)
        left_layout.addWidget(self.grp_word_list)
        self.grp_word_list.setVisible(False)

        # 5. Presentations Folder Configuration (Automatic Root)
        self.grp_presentations = QGroupBox("Presentations Source")
        layout_pres = QVBoxLayout()
        
        # No browse button anymore. It uses the automatic self.presentations_root
        
        # Presentation Selector
        self.combo_presentation_list = QComboBox()
        self.combo_presentation_list.currentIndexChanged.connect(self.on_presentation_selected)
        
        layout_pres.addWidget(QLabel("Select Presentation:"))
        layout_pres.addWidget(self.combo_presentation_list)
        layout_pres.addWidget(QLabel(f"<i>Located in: {os.path.basename(self.presentations_root)}</i>"))
        
        self.grp_presentations.setLayout(layout_pres)
        left_layout.addWidget(self.grp_presentations)
        self.grp_presentations.setVisible(False)

        # 6. Template Selection
        grp_template = QGroupBox("Slide Template")
        form_template = QFormLayout()
        
        self.combo_number_template = QComboBox()
        
        btn_open_templates = QPushButton("Open Templates Folder")
        btn_open_templates.setMaximumWidth(200)
        btn_open_templates.clicked.connect(self.open_template_folder)
        
        form_template.addRow("Select Style:", self.combo_number_template)
        form_template.addRow("", btn_open_templates)
        grp_template.setLayout(form_template)
        left_layout.addWidget(grp_template)

        # 7. Title Slide Configuration
        grp_title = QGroupBox("Title Slide (Optional)")
        form_title = QFormLayout()
        
        self.chk_title = QCheckBox("Include Title Slide")
        self.chk_title.toggled.connect(self.toggle_title_inputs)
        
        self.input_title_text = QLineEdit()
        self.input_title_text.setPlaceholderText("e.g. Phonics Lesson 1")
        self.input_title_text.setEnabled(False)
        
        self.input_title_script = QLineEdit()
        self.input_title_script.setPlaceholderText("Spoken text (leave empty to use title)")
        self.input_title_script.setEnabled(False)
        
        self.combo_title_template = QComboBox()
        self.combo_title_template.setEnabled(False)
        
        form_title.addRow(self.chk_title)
        form_title.addRow("Visual Title:", self.input_title_text)
        form_title.addRow("Spoken Script:", self.input_title_script)
        form_title.addRow("Title Template:", self.combo_title_template)
        
        grp_title.setLayout(form_title)
        left_layout.addWidget(grp_title)
        
        # Action Buttons
        self.btn_generate = QPushButton("Generate Video")
        self.btn_generate.setObjectName("btnGreen")
        self.btn_generate.setFixedHeight(40)
        self.btn_generate.clicked.connect(self.prepare_and_generate)
        left_layout.addWidget(self.btn_generate)
        
        self.btn_stop = QPushButton("Stop Generation")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_all_renders)
        left_layout.addWidget(self.btn_stop)

        btn_settings = QPushButton("Settings (TTS, Video)")
        btn_settings.clicked.connect(self.open_settings)
        left_layout.addWidget(btn_settings)

        btn_cleanup = QPushButton("Clear Cache & Temp Files")
        btn_cleanup.setObjectName("btnBlue")
        btn_cleanup.setMaximumHeight(30)
        btn_cleanup.clicked.connect(self.manual_cleanup)
        left_layout.addWidget(btn_cleanup)
        
        left_layout.addStretch()
        left_layout.addWidget(QLabel("Output Directory:"))
        self.lbl_out_dir = QLabel(self.output_dir)
        self.lbl_out_dir.setWordWrap(True)
        self.lbl_out_dir.setStyleSheet("color: #888; font-style: italic;")
        left_layout.addWidget(self.lbl_out_dir)
        
        # --- Right Panel: Status & Logs ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        grp_status = QGroupBox("Status")
        status_layout = QVBoxLayout()
        self.lbl_status = QLabel("Idle")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.lbl_status)
        status_layout.addWidget(self.progress_bar)
        grp_status.setLayout(status_layout)
        right_layout.addWidget(grp_status)
        
        grp_logs = QGroupBox("Logs")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #2b2b2b; color: #d4d4d4; font-family: Consolas;")
        log_layout.addWidget(self.log_text)
        grp_logs.setLayout(log_layout)
        right_layout.addWidget(grp_logs)
        
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 2)

        self.load_templates()
        self.populate_presentations_list() # Auto-load from fixed root
        self.on_sequence_changed(0) # Initialize description

    # --- UI SLOTS ---

    def on_language_changed(self):
        lang_code = self.combo_language.currentData()
        lang_name = self.combo_language.currentText()
        self.lbl_language_note.setText(f"Generating content for: {lang_name}. Ensure voice settings match.")

    def on_sequence_changed(self, index):
        mode = self.combo_sequence.currentText()
        
        # Dynamic Description Logic
        if "Random" in mode:
            desc = "Algorithmically generates nonsense words/syllables based on phonetic rules of the selected language."
            self.grp_presentations.setVisible(False)
        elif "Word List" in mode:
            desc = "Reads text from the box below or a loaded .txt file. One line = one word."
            self.grp_presentations.setVisible(False)
        elif "Presentations Folder" in mode:
            desc = "Select a presentation from the automatic 'Presentations' folder."
            self.grp_presentations.setVisible(True)
        else:
            desc = ""
            self.grp_presentations.setVisible(False)
            
        self.lbl_mode_description.setText(desc)
        
        # Visibility Logic
        is_random = "Random" in mode
        self.grp_random_settings.setVisible(is_random)
        
        is_word_list = "Word List" in mode
        self.grp_word_list.setVisible(is_word_list)
        
        self.update_count_label()

    def update_count_label(self):
        mode = self.combo_sequence.currentText()
        count = 0
        
        if "Random" in mode:
            count = self.spin_random_slides.value()
        elif "Word List" in mode:
            raw_text = self.input_word_list.toPlainText()
            words = [w.strip() for w in re.split(r'[\n,]+', raw_text) if w.strip()]
            total_words = len(words)
            batch_size = self.spin_batch.value()
            if total_words > 0:
                count = math.ceil(total_words / batch_size)
        elif "Presentations Folder" in mode:
            # Count slideX.txt files in the selected presentation
            selected_pres = self.combo_presentation_list.currentText()
            if selected_pres:
                pres_path = os.path.join(self.presentations_root, selected_pres)
                if os.path.exists(pres_path):
                    # Look for files matching slideX.txt
                    slide_files = [f for f in os.listdir(pres_path) if f.lower().startswith("slide") and f.lower().endswith(".txt")]
                    slide_files.sort(key=natural_sort_key)
                    count = len(slide_files)

        if self.chk_title.isChecked():
            if isinstance(count, int):
                count = str(int(count) + 1)
            elif isinstance(count, str) and count.isdigit():
                 count = str(int(count) + 1)
            else:
                if count > 0:
                    count = str(count) + " (+Title)"

        self.lbl_count.setText(f"{count} Slides")

    def populate_presentations_list(self):
        self.combo_presentation_list.clear()
        
        if not os.path.exists(self.presentations_root):
            logger.warning(f"Presentations root does not exist: {self.presentations_root}")
            return
            
        try:
            # Get subfolders
            subfolders = [d for d in os.listdir(self.presentations_root) if os.path.isdir(os.path.join(self.presentations_root, d))]
            subfolders.sort(key=natural_sort_key)
            
            self.combo_presentation_list.addItems(subfolders)
            if subfolders:
                self.combo_presentation_list.setEnabled(True)
                self.update_count_label()
            else:
                self.combo_presentation_list.setEnabled(False)
                self.lbl_count.setText("0 Slides")
        except Exception as e:
            logger.error(f"Error reading presentations: {e}")

    def on_presentation_selected(self):
        self.update_count_label()

    def load_words_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Word List", "", "Text Files (*.txt);;All Files (*)")
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.input_word_list.setPlainText(content)
                self.update_count_label()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load file: {e}")

    def open_template_folder(self):
        import platform
        path = os.path.abspath(self.template_dir)
        if platform.system() == "Windows": os.startfile(path)
        elif platform.system() == "Darwin": subprocess.call(["open", path])
        else: subprocess.call(["xdg-open", path])

    def load_templates(self):
        self.combo_number_template.clear()
        self.combo_title_template.clear()
        if not os.path.exists(self.template_dir): return
        files = [f for f in os.listdir(self.template_dir) if f.endswith('.html')]
        files.sort()
        for f in files:
            display_name = f.replace('.html', '').replace('_', ' ').title()
            self.combo_number_template.addItem(display_name, f)
            self.combo_title_template.addItem(display_name, f)

    def toggle_title_inputs(self, checked):
        self.input_title_text.setEnabled(checked)
        self.input_title_script.setEnabled(checked)
        self.combo_title_template.setEnabled(checked)
        self.update_count_label()

    # --- LOGIC ---

    def prepare_and_generate(self):
        sequence_mode = self.combo_sequence.currentText()
        is_random = "Random" in sequence_mode
        is_word_list = "Word List" in sequence_mode
        is_presentations = "Presentations Folder" in sequence_mode
        
        has_title = self.chk_title.isChecked()
        number_template = self.combo_number_template.currentData()
        title_template = self.combo_title_template.currentData()
        
        lang_code = self.combo_language.currentData()
        
        if not number_template:
            QMessageBox.warning(self, "Error", "Please select a valid template.")
            return

        if is_presentations:
            pres_name = self.combo_presentation_list.currentText()
            if not pres_name:
                QMessageBox.warning(self, "Error", "Please select a Presentation from the list.")
                return

        if is_word_list:
            raw_text = self.input_word_list.toPlainText()
            if not raw_text.strip():
                QMessageBox.warning(self, "Error", "Please enter words or load a file.")
                return

        if has_title:
            if not title_template: 
                QMessageBox.warning(self, "Error", "Select title template.")
                return
            if not self.input_title_text.text().strip(): 
                QMessageBox.warning(self, "Error", "Enter Title Text.")
                return

        timestamp = int(time.time())
        # Name project after the presentation if possible
        if is_presentations:
            project_name = f"{self.combo_presentation_list.currentText()}_{timestamp}"
        else:
            project_name = f"words_{timestamp}"
            
        project_path = os.path.join(self.output_dir, "temp_projects", project_name)
        
        try: 
            os.makedirs(project_path, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create temp dir: {e}")
            return

        try:
            slide_index = 1
            batch_size = self.spin_batch.value()

            def format_textandipa_html(text, ipa):
                return f'<div style="font-size: 1.2em; margin: 4px 0;"><strong>{text}</strong> <span style="color: #888; font-size: 0.9em;">{ipa}</span></div>'

            def format_text_html(text, ipa):
                return f'<div style="font-size: 1.2em; margin: 4px 0;"><strong>{text}</strong></div>'
 

            # --- A. Title Slide ---
            if has_title:
                visual_title = self.input_title_text.text().strip()
                spoken_script = self.input_title_script.text().strip() or visual_title
                html_path = os.path.join(project_path, f"slide{slide_index}.html")
                txt_path = os.path.join(project_path, f"slide{slide_index}.txt")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(self.get_template_html(visual_title, title_template))
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(spoken_script)
                slide_index += 1

            # --- B. Content Slides ---
            
            # Logic for Presentations Folder (slideX.txt files inside subfolder)
            if is_presentations:
                pres_path = os.path.join(self.presentations_root, self.combo_presentation_list.currentText())
                
                # Find all files starting with "slide" and ending with .txt
                all_files = os.listdir(pres_path)
                slide_files = [f for f in all_files if f.lower().startswith("slide") and f.lower().endswith(".txt")]
                
                # Sort numerically (natural sort) so slide2 comes before slide10
                slide_files.sort(key=natural_sort_key)
                
                if not slide_files:
                    logger.warning(f"No slide files found in {pres_path}")
                
                for filename in slide_files:
                    file_path = os.path.join(pres_path, filename)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                    except Exception as e:
                        logger.warning(f"Could not read file {file_path}: {e}")
                        continue

                    html_parts = []
                    spoken_parts = []
                    
                    # Parse content line by line for IPA support
                    lines = content.split('\n')
                    for line in lines:
                        line = line.strip()
                        if not line: continue
                        
                        # Check for "Word /IPA/" format
                        match = re.match(r'^(.+?)\s+(/.+/)$', line)
                        if match:
                            word = match.group(1).strip()
                            ipa = match.group(2).strip()
                        else:
                            # Fallback: assume whole line is word, no IPA
                            word = line
                            ipa = ""
                        
                        html_parts.append(format_textandipa_html(word, ipa))
                        spoken_parts.append(word)
                    
                    if not html_parts: continue
                    
                    visual_content = "<div style='text-align: center;'>" + "<br>".join(html_parts) + "</div>"
                    spoken_content = " ".join(spoken_parts)
                    
                    html_path = os.path.join(project_path, f"slide{slide_index}.html")
                    txt_path = os.path.join(project_path, f"slide{slide_index}.txt")
                    
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(self.get_template_html(visual_content, number_template))
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(spoken_content)
                    
                    slide_index += 1

            elif is_random:
                total_slides = self.spin_random_slides.value()
                mode_type = "syllable" if "Syllables" in sequence_mode else "word"

                for _ in range(total_slides):
                    html_parts = []
                    spoken_parts = []
                    
                    for _ in range(batch_size):
                        text, _ = generate_random_item(mode=mode_type, lang=lang_code)
                        html_parts.append(format_text_html(text))
                        spoken_parts.append(text)
                    
                    visual_content = "<div style='text-align: center;'>" + "<br>".join(html_parts) + "</div>"
                    spoken_content = ", ".join(spoken_parts)
                    
                    html_path = os.path.join(project_path, f"slide{slide_index}.html")
                    txt_path = os.path.join(project_path, f"slide{slide_index}.txt")
                    
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(self.get_template_html(visual_content, number_template))
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(spoken_content)
                    
                    slide_index += 1

            elif is_word_list:
                words = [w.strip() for w in re.split(r'[\n,]+', self.input_word_list.toPlainText()) if w.strip()]
                
                for i in range(0, len(words), batch_size):
                    batch = words[i : i + batch_size]
                    html_parts = []
                    spoken_parts = []
                    
                    for word in batch:
                        ipa = word_to_ipa(word, lang_code)
                        html_parts.append(format_textandipa_html(word, ipa))
                        spoken_parts.append(word)
                    
                    visual_content = "<div style='text-align: center;'>" + "<br>".join(html_parts) + "</div>"
                    spoken_content = ", ".join(spoken_parts)
                    
                    html_path = os.path.join(project_path, f"slide{slide_index}.html")
                    txt_path = os.path.join(project_path, f"slide{slide_index}.txt")
                    
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(self.get_template_html(visual_content, number_template))
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(spoken_content)
                    
                    slide_index += 1

            logger.info(f"Generated {slide_index - 1} slides total.")
            
        except Exception as e:
            logger.error(f"Failed to generate slide files: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return

        self.add_to_queue(project_path, project_name)

    def add_to_queue(self, project_path, project_name):
        mode = self.combo_sequence.currentText()
        
        if "Word List" in mode:
            desired_name = f"WordList_Video.mp4"
        elif "Syllables" in mode:
            desired_name = f"Syllables_Video.mp4"
        elif "Presentations Folder" in mode:
            # Use the folder name as the video name
            desired_name = f"{self.combo_presentation_list.currentText()}.mp4"
        else:
            desired_name = f"RandomWords_Video.mp4"
            
        if self.chk_title.isChecked():
            desired_name = f"{self.input_title_text.text().replace(' ', '_')}.mp4"
        
        self.pending_projects.append({
            "path": project_path,
            "name": project_name,
            "output_name": desired_name
        })
        
        self.update_status_label(f"Added {desired_name} to queue.")
        if not self.scheduler_timer.isActive():
            self.scheduler_timer.start(500)

    def get_template_html(self, content: str, filename: str):
        if not filename: return "<html><body>No template selected</body></html>"
        path = os.path.join(self.template_dir, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                html = f.read()
            return html.replace("{content}", content)
        except Exception as e:
            return f"<html><body>Error loading template: {e}</body></html>"

    def setup_logger(self):
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(logging.DEBUG)
        
        gui_logger = QTextEditLogger(self.log_text)
        gui_logger.setLevel(logging.INFO)
        root_logger.addHandler(gui_logger)
        
        try:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
            os.makedirs(log_dir, exist_ok=True)
            file_handler = RotatingFileHandler(
                os.path.join(log_dir, "counting_gen.log"), maxBytes=5*1024*1024, backupCount=1
            )
            file_handler.setFormatter(logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s'))
            file_handler.setLevel(logging.DEBUG)
            root_logger.addHandler(file_handler)
        except Exception: pass

        logger.info("Syllable & Word Video Generator Initialized.")

    def schedule_jobs(self):
        if not self.pending_projects and not self.active_processes:
            self.scheduler_timer.stop()
            self.lbl_status.setText("Idle")
            self.progress_bar.setValue(0)
            self.btn_stop.setEnabled(False)
            self.btn_generate.setEnabled(True)
            logger.info("All tasks completed.")
            return

        self.btn_stop.setEnabled(True)
        self.btn_generate.setEnabled(False)

        active_count = len(self.active_processes)
        if active_count < self.max_workers and self.pending_projects:
            job = self.pending_projects.pop(0)
            self.start_worker(job)
            self.update_status_label(f"Rendering: {job['output_name']}...")

    def start_worker(self, job):
        ffmpeg = detect_ffmpeg()
        if not ffmpeg:
            logger.error("FFmpeg missing.")
            QMessageBox.critical(self, "Error", "FFmpeg not found.")
            return

        worker_config = self.config.settings.copy()
        worker_config['ffmpeg_path'] = ffmpeg
        
        proc = multiprocessing.Process(
            target=render_project_worker, 
            args=(job["path"], self.render_queue, worker_config)
        )
        proc.start()
        
        self.active_processes[proc.pid] = {
            'proc': proc, 
            'path': job["path"], 
            'output_name': job["output_name"],
            'name': job['name']
        }

    def stop_all_renders(self):
        logger.info("Stopping...")
        for job in self.pending_projects:
            self.delete_job_temps(job["path"], job["name"])
        self.pending_projects.clear()
        
        for proc_data in list(self.active_processes.values()):
            path = proc_data.get('path')
            name = proc_data.get('name')
            try:
                proc_data['proc'].terminate()
                proc_data['proc'].join(timeout=1.0)
                if proc_data['proc'].is_alive(): proc_data['proc'].kill()
                self.delete_job_temps(path, name)
            except Exception as e: logger.error(f"Stop error {name}: {e}")
        
        self.active_processes.clear()
        self.scheduler_timer.stop()
        self.lbl_status.setText("Stopped")
        self.progress_bar.setValue(0)
        self.btn_stop.setEnabled(False)
        self.btn_generate.setEnabled(True)

    def process_queue(self):
        try:
            while not self.render_queue.empty():
                msg = self.render_queue.get_nowait()
                self.handle_message(msg)
        except Exception as e: logger.error(f"Queue error: {e}")

        active_pids = list(self.active_processes.keys())
        for pid in active_pids:
            proc_data = self.active_processes[pid]
            if not proc_data['proc'].is_alive():
                exit_code = proc_data['proc'].exitcode
                job_path = proc_data['path']
                output_name = proc_data['output_name']
                job_name = proc_data['name']

                if exit_code == 0:
                    logger.info(f"Finished rendering {output_name}")
                    self.post_process(job_path, output_name)
                    self.delete_job_temps(job_path, job_name)
                else:
                    logger.error(f"Worker {pid} failed.")
                    self.delete_job_temps(job_path, job_name)
                
                del self.active_processes[pid]
                self.schedule_jobs()

    def handle_message(self, msg):
        if not isinstance(msg, tuple): return
        if msg[0] == "ERROR": logger.error(f"Error: {msg[1]}"); return
        try: project_name, status, data = msg
        except ValueError: return
        
        if isinstance(status, str) and status == "FINALIZING":
            logger.info("Processing complete.")
            
        if isinstance(status, int) and isinstance(data, int):
            pct = int((status / data) * 100)
            self.progress_bar.setValue(pct)
            self.lbl_status.setText(f"Rendering Slide {status} of {data}")
        elif isinstance(status, str):
            self.lbl_status.setText(f"Status: {status}")

    def post_process(self, project_path, desired_name):
        temp_video_name = os.path.basename(project_path) + ".mp4"
        temp_video_path = os.path.join(self.output_dir, temp_video_name)
        final_video_path = os.path.join(self.output_dir, desired_name)
        
        if not os.path.exists(temp_video_path):
            logger.warning(f"Expected video not found at {temp_video_path}")
            return

        try:
            if os.path.exists(final_video_path): os.remove(final_video_path)
            shutil.move(temp_video_path, final_video_path)
            logger.info(f"Video saved to: {final_video_path}")
            self.lbl_status.setText(f"Saved: {desired_name}")
            project_name = os.path.basename(project_path)
            self.delete_job_temps(project_path, project_name)
                
        except Exception as e:
            logger.error(f"Failed to move final video or cleanup: {e}")

    def delete_job_temps(self, project_path, project_name):
        if not project_path or not project_name: return
        try:
            if os.path.exists(project_path):
                shutil.rmtree(project_path, ignore_errors=True)
        except Exception as e: pass
        try:
            engine_temp_dir = os.path.join(self.output_dir, "temp", project_name)
            if os.path.exists(engine_temp_dir):
                shutil.rmtree(engine_temp_dir, ignore_errors=True)
        except Exception as e: pass

    def cleanup_all_temp_files(self):
        temp_projects_dir = os.path.join(self.output_dir, "temp_projects")
        if os.path.exists(temp_projects_dir):
            try:
                for item in os.listdir(temp_projects_dir):
                    item_path = os.path.join(temp_projects_dir, item)
                    try:
                        if os.path.isdir(item_path): shutil.rmtree(item_path, ignore_errors=True)
                        else: os.remove(item_path)
                    except Exception: pass
            except Exception: pass
        temp_root = os.path.join(self.output_dir, "temp")
        if os.path.exists(temp_root):
            try:
                shutil.rmtree(temp_root, ignore_errors=True)
                os.makedirs(temp_root, exist_ok=True)
            except Exception: pass
        try:
            if os.path.exists(self.output_dir):
                for filename in os.listdir(self.output_dir):
                    if filename.startswith("counting_") and filename.endswith(".mp4"):
                        is_orphan = True
                        for job in self.active_processes.values():
                            if job.get('output_name') == filename: is_orphan = False; break
                        for job in self.pending_projects:
                            if job.get('output_name') == filename: is_orphan = False; break
                        if is_orphan:
                            file_path = os.path.join(self.output_dir, filename)
                            try: os.remove(file_path)
                            except Exception: pass
        except Exception: pass

    def manual_cleanup(self):
        reply = QMessageBox.question(self, "Clear Cache", "Delete all temporary files?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.cleanup_all_temp_files()
            QMessageBox.information(self, "Done", "Temporary files cleaned.")

    def update_status_label(self, text):
        self.lbl_status.setText(text)

    def open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            data = dlg.get_data()
            self.config.update(data)
            logger.info("Settings updated.")

if __name__ == "__main__":
    if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())