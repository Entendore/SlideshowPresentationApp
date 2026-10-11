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
from utils import logger, detect_ffmpeg
from theme import get_theme

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

    /* --- HIGH CONTRAST SEQUENCE LOGIC MENU --- */
    QComboBox#combo_sequence {
        background-color: #383838; 
        color: #ffffff;
        border: 2px solid #00d4ff; 
        padding: 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 13px;
    }
    QComboBox#combo_sequence:hover {
        background-color: #454545;
    }
    QComboBox#combo_sequence::drop-down {
        border: none;
        width: 20px;
    }
    QComboBox#combo_sequence::down-arrow {
        border-left: 6px solid transparent;
        border-right: 6px solid transparent;
        border-top: 6px solid #00d4ff; 
        width: 0; height: 0;
    }
    QComboBox#combo_sequence QAbstractItemView {
        background-color: #383838; 
        color: #ffffff;
        selection-background-color: #00d4ff; 
        selection-color: #000000; 
        border: 1px solid #555;
        padding: 4px;
        outline: none;
    }
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = AppConfig()
        
        # Setup Directories
        self.output_dir = self.config.get('output_dir', 'Output')
        os.makedirs(self.output_dir, self.output_dir, exist_ok=True)
        
        # Templates Directory
        self.template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
        os.makedirs(self.template_dir, exist_ok=True)

        # --- Parallelism Variables ---
        self.max_workers = 1 
        self.active_processes = {}  
        self.pending_projects = [] 
        self.render_queue = multiprocessing.Queue()
        
        self.init_ui()
        self.setup_logger()
        
        # --- Startup Cleanup ---
        self.cleanup_all_temp_files()
        
        # Timer to process messages
        self.queue_timer = QTimer()
        self.queue_timer.timeout.connect(self.process_queue)
        self.queue_timer.start(100)
        
        # Scheduler
        self.scheduler_timer = QTimer()
        self.scheduler_timer.timeout.connect(self.schedule_jobs)

    def init_ui(self):
        self.setWindowTitle("Counting Video Generator (Custom Patterns)")
        self.resize(950, 820) 
        self.setStyleSheet(STYLESHEET)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # --- Left Panel: Configuration ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # 1. Range Configuration
        grp_range = QGroupBox("Number Range")
        form_range = QFormLayout()
        
        self.spin_start = QDoubleSpinBox()
        self.spin_start.setRange(-1e12, 1e18)
        self.spin_start.setDecimals(0)
        self.spin_start.setValue(1) 
        
        self.spin_end = QDoubleSpinBox()
        self.spin_end.setRange(1, 1e18)
        self.spin_end.setDecimals(0)
        self.spin_end.setValue(10)
        
        # Step Size (Batch Size)
        self.spin_batch = QSpinBox()
        self.spin_batch.setRange(1, 100)
        self.spin_batch.setValue(1)
        self.spin_batch.setToolTip("How many numbers to group into ONE slide.")
        
        # Sequence Logic (Math Step)
        self.combo_sequence = QComboBox()
        self.combo_sequence.setObjectName("combo_sequence") 
        self.combo_sequence.addItems([
            "Standard (+1)", 
            "Even Numbers (+2)", 
            "Odd Numbers (+2)", 
            "Tens (+10)", 
            "Hundreds (+100)",
            "Thousands (+1000)",
            "Custom Pattern (Math Expression)" 
        ])
        self.combo_sequence.setToolTip("Determines how the numbers calculate from Start to End.")
        self.combo_sequence.currentIndexChanged.connect(self.on_sequence_changed)
        
        self.lbl_count = QLabel("Calculating...")
        
        form_range.addRow("Start Number:", self.spin_start)
        form_range.addRow("End Number:", self.spin_end)
        form_range.addRow("Numbers Per Slide:", self.spin_batch)
        form_range.addRow("Sequence Logic:", self.combo_sequence)
        form_range.addRow("Total Slides:", self.lbl_count)
        
        grp_range.setLayout(form_range)
        left_layout.addWidget(grp_range)

        # 2. Custom Pattern Inputs (Hidden by default)
        self.grp_custom = QGroupBox("Custom Pattern Settings")
        form_custom = QFormLayout()
        
        # Quick Select Dropdown
        self.combo_quick_select = QComboBox()
        self.combo_quick_select.addItem("Select a Preset...", "")
        self.combo_quick_select.addItems([
            "Squares (n^2)",
            "Cubes (n^3)",
            "Hundreds (n * 100)",
            "Thousands (n * 1000)",
            "Doubled + 5 ((n*2)+5)"
        ])
        self.combo_quick_select.currentIndexChanged.connect(self.on_quick_select_changed)
        
        # Expression Input
        self.input_custom_expr = QLineEdit()
        self.input_custom_expr.setPlaceholderText("e.g. n * n or n^3 or (n*2)+1")
        self.input_custom_expr.setEnabled(False)
        
        form_custom.addRow("Quick Presets:", self.combo_quick_select)
        form_custom.addRow("Expression (use 'n' for current num):", self.input_custom_expr)
        
        self.grp_custom.setLayout(form_custom)
        left_layout.addWidget(self.grp_custom)
        # Hide custom group initially
        self.grp_custom.setVisible(False) # FIX: Changed from grp_custom to self.grp_custom
        
        # 3. Number Template Selection
        grp_template = QGroupBox("Number Slides Template")
        form_template = QFormLayout()
        
        self.combo_number_template = QComboBox()
        
        btn_open_templates = QPushButton("Open Templates Folder")
        btn_open_templates.setMaximumWidth(200)
        btn_open_templates.clicked.connect(self.open_template_folder)
        
        form_template.addRow("Select Style:", self.combo_number_template)
        form_template.addRow("", btn_open_templates)
        grp_template.setLayout(form_template)
        left_layout.addWidget(grp_template)

        # 4. Title Slide Configuration
        grp_title = QGroupBox("Title Slide (Optional)")
        form_title = QFormLayout()
        
        self.chk_title = QCheckBox("Include Title Slide")
        self.chk_title.toggled.connect(self.toggle_title_inputs)
        
        self.input_title_text = QLineEdit()
        self.input_title_text.setPlaceholderText("e.g. Let's Count to 10!")
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
        
        # Status Group
        grp_status = QGroupBox("Status")
        status_layout = QVBoxLayout()
        self.lbl_status = QLabel("Idle")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        status_layout.addWidget(self.lbl_status)
        status_layout.addWidget(self.progress_bar)
        grp_status.setLayout(status_layout)
        right_layout.addWidget(grp_status)
        
        # Logs
        grp_logs = QGroupBox("Logs")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #2b2b2b; color: #d4d4d4; font-family: Consolas;")
        log_layout.addWidget(self.log_text)
        grp_logs.setLayout(log_layout)
        right_layout.addWidget(grp_logs)
        
        # Add panels to main layout
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 2)

        self.load_templates()

    # --- UI SLOTS FOR CUSTOM PATTERN ---

    def on_sequence_changed(self, index):
        """Show/Hide Custom Pattern settings based on dropdown selection."""
        mode = self.combo_sequence.currentText()
        is_custom = "Custom" in mode
        self.grp_custom.setVisible(is_custom)
        if is_custom and not self.input_custom_expr.text():
            # Default suggestion
            self.input_custom_expr.setText("n * 10")
        self.update_count_label()

    def on_quick_select_changed(self, index):
        """Fills in the expression box based on the quick preset."""
        selection = self.combo_quick_select.currentText()
        
        if "Squares" in selection:
            self.input_custom_expr.setText("n * n")
        elif "Cubes" in selection:
            self.input_custom_expr.setText("n * n * n")
        elif "Hundreds" in selection:
            self.input_custom_expr.setText("n * 100")
        elif "Thousands" in selection:
            self.input_custom_expr.setText("n * 1000")
        elif "Doubled + 5" in selection:
            self.input_custom_expr.setText("(n * 2) + 5") # FIX: Changed .text() to .setText()
        # Clear text if "Select..." selected
        elif selection == "Select a Preset...":
            self.input_custom_expr.clear()
        
        self.update_count_label()

    # --- LOGIC HELPERS ---

    def get_next_number(self, current: int, sequence_mode: str, custom_expr: str):
        """
        Calculates the next number.
        If 'Custom' mode, uses eval() on the custom_expr string.
        """
        if "Custom" in sequence_mode:
            try:
                # Prepare the string for eval
                # We replace 'n' with the integer value of current
                eval_string = custom_expr.replace("n", str(current))
                next_val = eval(eval_string)
                return next_val
            except Exception as e:
                logger.error(f"Custom Math Error ({eval_string}): {e}")
                return current + 1 # Fallback on error to prevent crash
        elif "Powers of 10" in sequence_mode:
            return current * 10
        elif "Powers of 2" in sequence_mode:
            return current * 2
        elif "Even Numbers" in sequence_mode:
            return current + 2
        elif "Odd Numbers" in sequence_mode:
            return current + 2
        elif "Tens" in sequence_mode:
            return current + 10
        elif "Hundreds" in sequence_mode:
            return current + 100
        elif "Thousands" in sequence_mode:
            return current + 1000
        elif "Doubling then +5" in sequence_mode:
            return (current * 2) + 5
        else: # Standard
            return current + 1

    def adjust_start_number(self, start: int, sequence_mode: str):
        """Smartly adjusts the start number for Evens/Odds."""
        if "Even Numbers" in sequence_mode:
            if start % 2 != 0: return start + 1
        elif "Odd Numbers" in sequence_mode:
            if start % 2 == 0: return start + 1
        elif "Powers of 10" in sequence_mode:
            if start == 0: return 1 
        return start

    def calculate_total_slides(self, start, end, sequence_mode, batch_size, custom_expr=""):
        """
        Calculates total slides. 
        Uses math shortcuts for powers (n^x) and direct evaluation for custom expressions (capped for performance).
        """
        # FIX: Adjust start number first so calculation matches actual generation
        start = self.adjust_start_number(start, sequence_mode)

        count = 0
        
        # 1. Custom Logic
        if "Custom" in sequence_mode and custom_expr:
            try:
                # Optimization: Detect n^2 or n^3 to use Sqrt/Cuberoot for instant calculation
                if "**2" in custom_expr or "n * n" in custom_expr:
                    # Assuming n*n implies squaring the index. 
                    # Since this is a recursive calculator (n = prev), we can't easily predict count without running loop
                    # But we attempt a dry run for accuracy.
                    pass 
                elif "**3" in custom_expr or "n * n * n" in custom_expr:
                    pass
                elif "*" in custom_expr or "+" in custom_expr:
                    # For complex expressions, we do a safe dry run (max 10,000 steps) to estimate
                    # This prevents UI freezing on infinite loops like "n * n * n"
                    safe_end = min(start + 10000, end)
                    curr = self.get_next_number(start, sequence_mode, custom_expr)
                    count = 0
                    # Note: get_next_number calculates the *next* based on current.
                    # We need to count steps from start to end.
                    curr = start # Reset to start to count correctly
                    while curr <= safe_end:
                        count += 1
                        curr = self.get_next_number(curr, sequence_mode, custom_expr)
                        if count > 100000:
                            return "~100000+"
                else:
                    return str(int(math.ceil(count / batch_size)))
            except Exception:
                return "Unknown"

        # 2. Geometric Sequences (Powers)
        elif "Powers of 10" in sequence_mode:
            if start == 0 or end < start: return "0"
            try: count = math.ceil(math.log(end / start, 10) + 1)
            except ValueError: return "0"
            return str(int(math.ceil(count / batch_size)))
        elif "Powers of 2" in sequence_mode:
            if start == 0 or end < start: return "0"
            try: count = math.ceil(math.log(end / start, 2) + 1)
            except ValueError: return "0"
            return str(int(math.ceil(count / batch_size)))

        # 3. Arithmetic Sequences
        step = 1
        if "+2" in sequence_mode: step = 2
        elif "+10" in sequence_mode: step = 10
        elif "+100" in sequence_mode: step = 100
        elif "+1000" in sequence_mode: step = 1000
        elif "Custom" in sequence_mode:
             # If eval failed in block 1, we just count linearly as fallback
             pass

        # Standard Formula: (End - Start) / Step + 1
        try:
            total_numbers = (end - start) // step + 1
        except ZeroDivisionError: return "0"
        if total_numbers > 100000:
            approx_slides = math.ceil(total_numbers / batch_size)
            return f"~{int(approx_slides)}"
        return str(int(math.ceil(total_numbers / batch_size)))

    # --- ROBUST CLEANUP ---

    def delete_mp3s_from_project(self, project_name):
        project_path = os.path.join(self.output_dir, "temp_projects", project_name)
        if os.path.exists(project_path):
            mp3_count = 0
            for f in os.listdir(project_path):
                if f.lower().endswith('.mp3'):
                    try:
                        os.remove(os.path.join(project_path, f))
                        mp3_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete MP3 {f}: {e}")
            if mp3_count > 0:
                logger.info(f"Deleted {mp3_count} redundant MP3 files from project folder.")

    def delete_job_temps(self, project_path, project_name):
        if not project_path or not project_name: return
        try:
            if os.path.exists(project_path):
                shutil.rmtree(project_path, ignore_errors=True)
                logger.info(f"Deleted project folder: {project_name}")
        except Exception as e:
            logger.warning(f"Warning: Failed to remove project folder {project_name}: {e}")

        try:
            engine_temp_dir = os.path.join(self.output_dir, "temp", project_name)
            if os.path.exists(engine_temp_dir):
                shutil.rmtree(engine_temp_dir, ignore_errors=True)
                logger.info(f"Deleted engine temp folder: {project_name}")
        except Exception as e:
            logger.warning(f"Warning: Failed to remove engine temp {project_name}: {e}")

    def cleanup_all_temp_files(self):
        logger.info("Running global temp cleanup...")
        temp_projects_dir = os.path.join(self.output_dir, "temp_projects")
        if os.path.exists(temp_projects_dir):
            try:
                for item in os.listdir(temp_projects_dir):
                    item_path = os.path.join(temp_projects_dir, item)
                    try:
                        if os.path.isdir(item_path): shutil.rmtree(item_path, ignore_errors=True)
                        else: os.remove(item_path)
                    except Exception: pass
                logger.info(f"Cleaned contents of {temp_projects_dir}")
            except Exception: pass

        temp_root = os.path.join(self.output_dir, "temp")
        if os.path.exists(temp_root):
            try:
                shutil.rmtree(temp_root, ignore_errors=True)
                os.makedirs(temp_root, exist_ok=True)
                logger.info(f" Cleaned and reset `temp_root`")
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
        reply = QMessageBox.question(self, "Clear Cache", "Delete all temporary files (HTML, Audio, Video) and orphaned renders?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.cleanup_all_temp_files()
            QMessageBox.information(self, "Done", "Temporary files and orphans cleaned.")

    # --- UI SLOTS ---

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

    def open_template_folder(self):
        import platform
        path = os.path.abspath(self.template_dir)
        if platform.system() == "Windows": os.startfile(path)
        elif platform.system() == "Darwin": subprocess.call(["open", path])
        else: subprocess.call(["xdg-open", path])

    def toggle_title_inputs(self, checked):
        self.input_title_text.setEnabled(checked)
        self.input_title_script.setEnabled(checked)
        self.combo_title_template.setEnabled(checked)
        self.update_count_label()

    def update_count_label(self):
        start = int(self.spin_start.value())
        end = int(self.spin_end.value())
        batch_size = self.spin_batch.value()
        mode = self.combo_sequence.currentText()
        
        expr = self.input_custom_expr.text().strip() if "Custom" in mode else ""
        
        count = self.calculate_total_slides(start, end, mode, batch_size, expr)
        
        if self.chk_title.isChecked():
            # FIX: Handle non-numeric counts (like "Unknown") safely
            if count.isdigit():
                try: 
                    count = str(int(count) + 1)
                except ValueError:
                    pass
            else:
                # If count is "Unknown" or "~...", we just append "+" to indicate title addition
                if not count.startswith("~"):
                    count = "Many"
                else:
                    count = count + " (+Title)"
                    
        self.lbl_count.setText(f"{count} Slides")

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

        logger.info("Counting Video Generator Initialized.")

    def get_template_html(self, content: str, filename: str):
        if not filename: return "<html><body>No template selected</body></html>"
        path = os.path.join(self.template_dir, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                html = f.read()
            return html.replace("{content}", content)
        except Exception as e:
            return f"<html><body>Error loading template: {e}</body></html>"

    def prepare_and_generate(self):
        start = int(self.spin_start.value())
        end = int(self.spin_end.value())
        batch_size = self.spin_batch.value()
        sequence_mode = self.combo_sequence.currentText()
        custom_expr = self.input_custom_expr.text().strip()
        has_title = self.chk_title.isChecked()
        
        original_start = start
        start = self.adjust_start_number(start, sequence_mode)
        if start != original_start:
            logger.info(f"Adjusted start number from {original_start} to {start} to fit '{sequence_mode}' pattern.")

        number_template = self.combo_number_template.currentData()
        title_template = self.combo_title_template.currentData()
        
        if not number_template:
            QMessageBox.warning(self, "Error", "Please select a valid template for numbers.")
            return
        if start > end:
            QMessageBox.warning(self, "Error", "Start number (adjusted) is greater than End number.")
            return
        if has_title:
            if not title_template: 
                QMessageBox.warning(self, "Error", "Select title template.")
                return
            if not self.input_title_text.text().strip(): 
                QMessageBox.warning(self, "Error", "Enter Title Text.")
                return

        timestamp = int(time.time())
        project_name = f"counting_{timestamp}"
        project_path = os.path.join(self.output_dir, "temp_projects", project_name)
        
        try: os.makedirs(project_path, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create temp dir: {e}")
            return

        try:
            slide_index = 1

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

            # --- B. Number Slides ---
            current = start
            current_batch_numbers = []
            
            while current <= end:
                current_batch_numbers.append(current)
                current = self.get_next_number(current, sequence_mode, custom_expr)
                
                if len(current_batch_numbers) >= batch_size or current > end:
                    if len(current_batch_numbers) == 1:
                        visual_content = str(current_batch_numbers[0])
                    else:
                        visual_content = f"{current_batch_numbers[0]} - {current_batch_numbers[-1]}"
                    
                    spoken_content = ", ".join([str(n) for n in current_batch_numbers])
                    
                    html_path = os.path.join(project_path, f"slide{slide_index}.html")
                    txt_path = os.path.join(project_path, f"slide{slide_index}.txt")
                    
                    with open(html_path, "w", encoding="utf-8") as f:
                        f.write(self.get_template_html(visual_content, number_template))
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(spoken_content)
                    
                    slide_index += 1
                    current_batch_numbers = [] 

                    if slide_index > 100000:
                        logger.error("Safety limit reached (100,000 slides). Stopping generation.")
                        break
            
            logger.info(f"Generated {slide_index - 1} slides total.")
            
        except Exception as e:
            logger.error(f"Failed to generate slide files: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return

        self.add_to_queue(project_path, project_name)

    def add_to_queue(self, project_path, project_name):
        desired_name = f"{int(self.spin_start.value())}_to_{int(self.spin_end.value())}.mp4"
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
            logger.info(f"Audio generation complete. Cleaning up redundant MP3s...")
            self.delete_mp3s_from_project(project_name)

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
            
            # 2. Cleanup specific useless artifacts
            project_name = os.path.basename(project_path)
            self.delete_job_temps(project_path, project_name)
                
        except Exception as e:
            logger.error(f"Failed to move final video or cleanup: {e}")

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