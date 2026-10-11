# utils/helpers.py
import os
import re
import subprocess
import logging
import sys
import json
import html
import traceback
from datetime import datetime
from typing import Dict, Any, Optional, List
from PyQt6.QtCore import Qt, qInstallMessageHandler, QMessageLogContext, QMetaObject, Q_ARG
from PyQt6.QtWidgets import QTextEdit

# --- Logging Setup ---

logger = logging.getLogger()

class QTextEditLogger(logging.Handler):
    def __init__(self, text_edit):
        super().__init__()
        self.text_edit = text_edit
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S'))

    def emit(self, record):
        try:
            if not self.text_edit: return
            msg = html.escape(self.format(record))
            color = "#d4d4d4"
            if record.levelno >= logging.ERROR: color = "#ff6b6b"
            elif record.levelno >= logging.WARNING: color = "#f1c40f"
            elif record.levelname == "INFO": color = "#3498db"
            
            html_msg = f'<span style="color:{color}">{msg}</span>'
            QMetaObject.invokeMethod(self.text_edit, "append", Qt.ConnectionType.QueuedConnection, Q_ARG(str, html_msg))
        except: self.handleError(record)

def setup_logger(text_widget):
    global logger
    logger.setLevel(logging.DEBUG)
    if not any(isinstance(h, QTextEditLogger) for h in logger.handlers):
        gui_handler = QTextEditLogger(text_widget)
        gui_handler.setLevel(logging.DEBUG)
        logger.addHandler(gui_handler)
    
    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(console_handler)
    return logger

def handle_qt_log(msg_type, context, msg):
    if "setParent" in msg and "different thread" in msg:
        print("=== Qt threading error ===")
        print(msg)
        traceback.print_exc()
    
    level = {0: logging.DEBUG, 1: logging.WARNING, 2: logging.CRITICAL, 3: logging.ERROR}.get(msg_type, logging.INFO)
    logger.log(level, msg)

qInstallMessageHandler(handle_qt_log)

# --- System Helpers ---

def natural_sort_key(s: str):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def detect_ffmpeg() -> Optional[str]:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return "ffmpeg"
    except FileNotFoundError:
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            return get_ffmpeg_exe()
        except ImportError:
            return None

def get_project_dirs() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pres_dir = os.path.join(base_dir, "Presentations")
    os.makedirs(pres_dir, exist_ok=True)
    return pres_dir