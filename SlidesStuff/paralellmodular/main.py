# main.py
import sys
import os
import multiprocessing
import traceback
import shutil
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTreeWidget, QTreeWidgetItem, QHeaderView, QPushButton, 
    QToolBar, QFileDialog, QMessageBox, QProgressBar, QLabel, QSplitter
)
from PyQt6.QtCore import Qt, QTimer, QProcess
from PyQt6.QtGui import QAction, QIcon

# Import refactored modules
from config import AppConfig
from ui.dialogs import SettingsDialog, ScriptEditorDialog
from core.renderer import render_project_worker
from core.manifest import get_library_manifest_path, load_manifest
from utils.helpers import logger, setup_logger, detect_ffmpeg, get_project_dirs

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = AppConfig()
        self.setWindowTitle("PySlideshow Renderer (Modular)")
        self.resize(1000, 700)

        # Multiprocessing Setup
        self.msg_queue = multiprocessing.Queue()
        self.render_process = None
        self.current_project = None
        
        # UI Setup
        self.init_ui()
        
        # Timer to process messages from the worker process
        self.queue_timer = QTimer()
        self.queue_timer.timeout.connect(self.process_queue)
        self.queue_timer.start(100) # Check every 100ms

        # Initial Load
        self.refresh_library()

    def init_ui(self):
        # --- Toolbar ---
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        action_refresh = QAction("Refresh Library", self)
        action_refresh.triggered.connect(self.refresh_library)
        toolbar.addAction(action_refresh)

        toolbar.addSeparator()

        action_settings = QAction("Settings", self)
        action_settings.triggered.connect(self.open_settings)
        toolbar.addAction(action_settings)

        action_render = QAction("Render Selected", self)
        action_render.triggered.connect(self.start_render)
        toolbar.addAction(action_render)

        # --- Main Layout ---
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Top: Splitter (Library | Details/Logs)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Project Library
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Project Name", "Status", "Mode", "Video File"])
        self.tree.setColumnWidth(0, 200)
        self.tree.setColumnWidth(3, 250)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.itemDoubleClicked.connect(self.open_project_folder)
        splitter.addWidget(self.tree)

        # Right: Logs and Info
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_label = QLabel("Ready")
        right_layout.addWidget(self.status_label)
        right_layout.addWidget(self.progress_bar)

        # Log Viewer
        self.log_viewer = QTextEditLoggerSetup() # Custom wrapper to get the widget
        right_layout.addWidget(self.log_viewer.widget)
        
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 1) # Give logs more space
        layout.addWidget(splitter)

        # Hook logger to GUI
        setup_logger(self.log_viewer.widget)

    def refresh_library(self):
        self.tree.clear()
        lib_path = get_library_manifest_path()
        lib_data = load_manifest(lib_path)
        
        projects = lib_data.get("projects", {})
        
        if not projects:
            # Fallback: Scan directory if manifest is empty
            pres_dir = get_project_dirs()
            if os.path.exists(pres_dir):
                for d in os.listdir(pres_dir):
                    if os.path.isdir(os.path.join(pres_dir, d)):
                        self.add_tree_item(d, "Unknown", "N/A", "")
            return

        for name, data in projects.items():
            status = "Ready"
            if data.get("video_file") and os.path.exists(os.path.join(data.get("path", ""), "..", "Output", data.get("video_file"))):
                status = "Rendered"
            
            self.add_tree_item(
                name, 
                status, 
                data.get("render_mode", "N/A"), 
                data.get("video_file", "")
            )

    def add_tree_item(self, name, status, mode, video):
        item = QTreeWidgetItem([name, status, mode, video])
        # Store full path in data column 0 role if possible, or derive later
        self.tree.addTopLevelItem(item)

    def open_project_folder(self, item, column):
        name = item.text(0)
        pres_dir = get_project_dirs()
        path = os.path.join(pres_dir, name)
        if os.path.exists(path):
            import platform
            if platform.system() == "Windows": os.startfile(path)
            elif platform.system() == "Darwin": subprocess.call(["open", path])
            else: subprocess.call(["xdg-open", path])

    def open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            data = dlg.get_data()
            self.config.update(data)
            logger.info("Settings saved.")

    def start_render(self):
        if self.render_process and self.render_process.is_alive():
            QMessageBox.warning(self, "Busy", "A render is already in progress.")
            return

        selected = self.tree.selectedItems()
        if not selected:
            return

        project_name = selected[0].text(0)
        pres_dir = get_project_dirs()
        project_path = os.path.join(pres_dir, project_name)

        if not os.path.exists(project_path):
            QMessageBox.critical(self, "Error", f"Project folder not found: {project_path}")
            return

        # FFmpeg Check
        ffmpeg = detect_ffmpeg()
        if not ffmpeg:
            QMessageBox.critical(self, "Error", "FFmpeg not found. Please install FFmpeg or imageio-ffmpeg.")
            return
        
        # Update config with detected ffmpeg path if not set
        if not self.config.get('ffmpeg_path'):
            self.config.set('ffmpeg_path', ffmpeg)

        # Prepare Config Dict for Process
        # We must pass a dictionary, not the AppConfig object, for Pickling
        process_config = self.config.settings.copy()
        process_config['ffmpeg_path'] = ffmpeg

        logger.info(f"Starting render for {project_name}...")
        self.current_project = project_name
        self.status_label.setText(f"Rendering: {project_name}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Disable UI
        self.tree.setEnabled(False)

        # Start Process
        self.render_process = multiprocessing.Process(
            target=render_project_worker,
            args=(project_path, self.msg_queue, process_config)
        )
        self.render_process.start()

    def process_queue(self):
        if self.msg_queue.empty():
            return

        while not self.msg_queue.empty():
            try:
                msg = self.msg_queue.get_nowait()
                self.handle_message(msg)
            except Exception as e:
                logger.error(f"Error processing queue message: {e}")

    def handle_message(self, msg):
        # msg format: (TYPE, DATA, ...)
        msg_type = msg[0]

        if msg_type == "SKIP":
            logger.info(f"Skipped {msg[1]} (Up to date).")
            self.finish_render(success=True, skipped=True)

        elif msg_type == "ERROR":
            error_msg = msg[1]
            logger.error(f"Render Error: {error_msg}")
            QMessageBox.critical(self, "Render Failed", f"An error occurred:\n{error_msg}")
            self.finish_render(success=False)

        elif msg_type == "DONE":
            logger.info(f"Finished: {msg[1]}")
            self.finish_render(success=True)
            self.refresh_library() # Update status in tree

        elif isinstance(msg_type, str) and msg_type not in ["SKIP", "ERROR", "DONE", "INFO"]:
            # This is a project status update
            # format: (project_name, status_string, current_step, total_steps)
            project, status, current, total = msg
            
            if project == self.current_project:
                self.status_label.setText(f"{project}: {status}")
                if total > 0 and current > 0:
                    self.progress_bar.setValue(int((current / total) * 100))
                elif total == 0 and current == 0:
                    self.progress_bar.setRange(0, 0) # Indeterminate mode
        else:
            logger.info(f"Worker: {msg}")

    def finish_render(self, success, skipped=False):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        self.tree.setEnabled(True)
        
        if success:
            self.status_label.setText(f"Finished: {self.current_project}")
            if not skipped:
                # Optional: Auto-open output folder
                # out_dir = os.path.join(get_project_dirs(), "..", self.config.get('output_dir'))
                # if os.path.exists(out_dir): os.startfile(out_dir)
                pass
        else:
            self.status_label.setText("Render Failed")
        
        self.current_project = None

class QTextEditLoggerSetup:
    """Helper to hold the widget reference for the logger."""
    def __init__(self):
        from PyQt6.QtWidgets import QTextEdit
        self.widget = QTextEdit()
        self.widget.setReadOnly(True)
        # Dark theme for logs
        self.widget.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas;")

if __name__ == "__main__":
    # High DPI fix
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    
    # Ensure Playwright browsers are installed (Optional helper)
    # Usually done via CLI, but we can check or warn.
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())