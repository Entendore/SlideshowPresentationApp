# dialogs.py
import logging
import html  
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QWidget, 
    QComboBox, QPushButton, QHBoxLayout, QVBoxLayout, 
    QMessageBox, QCheckBox, QLabel, QLineEdit, QFileDialog, QTabWidget, QGroupBox, QTextEdit
)
from PyQt6.QtCore import Qt, QMetaObject, Q_ARG
from constants import EDGE_VOICES, EDGE_TONES, AZURE_REGIONS, AZURE_STYLES

class QTextEditLogger(logging.Handler):
    def __init__(self, text_edit):
        super().__init__()
        self.text_edit = text_edit
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S'))

    def emit(self, record):
        try:
            if not self.text_edit: return
            
            msg = self.format(record)
            msg = html.escape(msg)
            
            color = "#d4d4d4" 
            if record.levelno >= logging.ERROR: color = "#ff6b6b"
            elif record.levelno >= logging.WARNING: color = "#f1c40f"
            elif record.levelname == "INFO": color = "#3498db"
            
            html_msg = f'<span style="color:{color}">{msg}</span>'
            
            QMetaObject.invokeMethod(
                self.text_edit, "append", 
                Qt.ConnectionType.QueuedConnection, 
                Q_ARG(str, html_msg)
            )
        except Exception:
            self.handleError(record)

class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Renderer Settings")
        self.resize(550, 500)
        
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QTabWidget::pane { border: 1px solid #3e3e42; background-color: #252526; }
            QTabBar::tab { background-color: #2d2d30; color: #aaa; padding: 8px 16px; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
            QTabBar::tab:selected { background-color: #3e3e42; color: #fff; font-weight: bold; }
            QGroupBox { border: 1px solid #3e3e42; margin-top: 10px; font-weight: bold; color: #ccc; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
            QLabel { color: #cccccc; }
            QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox { 
                background-color: #3c3c3c; color: white; border: 1px solid #555; padding: 4px; border-radius: 3px; }
            QPushButton { background-color: #3e3e42; border: 1px solid #555; color: white; padding: 6px; border-radius: 4px; }
            QPushButton:hover { background-color: #505055; }
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tab_video = QWidget()
        self.tab_visuals = QWidget()
        self.tab_audio = QWidget()
        self.tabs.addTab(self.tab_video, "Video")
        self.tabs.addTab(self.tab_visuals, "Visuals")
        self.tabs.addTab(self.tab_audio, "Audio & TTS")
        self.main_layout.addWidget(self.tabs)
        
        self.init_video_tab()
        self.init_visuals_tab()
        self.init_audio_tab()
        
        btns = QHBoxLayout()
        ok = QPushButton("Save Settings")
        ok.setStyleSheet("background-color: #007acc; font-weight: bold;")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(ok)
        btns.addWidget(cancel)
        self.main_layout.addLayout(btns)

    def init_video_tab(self):
        layout = QFormLayout(self.tab_video)
        res_layout = QHBoxLayout()
        self.width_spin = QSpinBox()
        self.width_spin.setRange(640, 3840)
        self.width_spin.setValue(self.config.get('width', 1280))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(480, 2160)
        self.height_spin.setValue(self.config.get('height', 720))
        res_layout.addWidget(self.width_spin)
        res_layout.addWidget(QLabel("x"))
        res_layout.addWidget(self.height_spin)
        layout.addRow("Resolution:", res_layout)
        
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(10, 60)
        self.fps_spin.setValue(self.config.get('fps', 30))
        layout.addRow("FPS:", self.fps_spin)
        
        self.enc_combo = QComboBox()
        self.enc_combo.addItems(["auto", "libx264", "h264_nvenc", "h264_amf", "h264_qsv"])
        self.enc_combo.setCurrentText(self.config.get('encoder', 'auto'))
        layout.addRow("Encoder:", self.enc_combo)
        
        out_layout = QHBoxLayout()
        self.out_dir_edit = QLineEdit()
        self.out_dir_edit.setText(self.config.get('output_dir', 'Output'))
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self.browse_output_dir)
        out_layout.addWidget(self.out_dir_edit)
        out_layout.addWidget(btn_browse)
        layout.addRow("Output Dir:", out_layout)

    def browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.out_dir_edit.text())
        if d: self.out_dir_edit.setText(d)

    def init_visuals_tab(self):
        layout = QFormLayout(self.tab_visuals)
        self.chk_zoom = QCheckBox("Enable Ken Burns (Slow Zoom)")
        self.chk_zoom.setChecked(self.config.get('enable_zoom', True))
        layout.addRow(self.chk_zoom)
        self.spin_zoom = QDoubleSpinBox()
        self.spin_zoom.setRange(1.01, 2.0)
        self.spin_zoom.setSingleStep(0.05)
        self.spin_zoom.setValue(self.config.get('zoom_factor', 1.1))
        self.spin_zoom.setSuffix("x")
        layout.addRow("Max Zoom:", self.spin_zoom)
        self.trans_spin = QDoubleSpinBox()
        self.trans_spin.setRange(0.0, 5.0)
        self.trans_spin.setSingleStep(0.1)
        self.trans_spin.setValue(self.config.get('transition_duration', 0.5))
        layout.addRow("Transition (s):", self.trans_spin)

    def init_audio_tab(self):
        layout = QVBoxLayout(self.tab_audio)
        form_backend = QFormLayout()
        self.tts_backend_combo = QComboBox()
        self.tts_backend_combo.addItem("Edge TTS (free)", "edge")
        self.tts_backend_combo.addItem("Azure AI Speech (SSML)", "azure")
        backend = self.config.get("tts_backend", "edge")
        idx = self.tts_backend_combo.findData(backend)
        if idx >= 0: self.tts_backend_combo.setCurrentIndex(idx)
        
        # Fixed: Changed currentDataChanged to currentTextChanged
        self.tts_backend_combo.currentTextChanged.connect(self.on_backend_changed)
        
        form_backend.addRow("TTS Backend:", self.tts_backend_combo)
        layout.addLayout(form_backend)
        
        self.grp_edge = QGroupBox("Edge TTS Settings")
        l_edge = QFormLayout()
        self.edge_voice_combo = QComboBox()
        curr_edge_voice = self.config.get('edge_voice', 'en-US-GuyNeural')
        for v_id, v_name in EDGE_VOICES:
            self.edge_voice_combo.addItem(v_name, v_id)
            if v_id == curr_edge_voice: self.edge_voice_combo.setCurrentIndex(self.edge_voice_combo.count() - 1)
        self.edge_tone_combo = QComboBox()
        self.edge_tone_combo.addItems(EDGE_TONES)
        self.edge_tone_combo.setCurrentText(self.config.get('edge_tone', 'general'))
        l_edge.addRow("Voice:", self.edge_voice_combo)
        l_edge.addRow("Tone:", self.edge_tone_combo)
        self.grp_edge.setLayout(l_edge)
        layout.addWidget(self.grp_edge)
        
        self.grp_azure = QGroupBox("Azure TTS Settings")
        l_azure = QFormLayout()
        self.azure_region_edit = QComboBox()
        self.azure_region_edit.setEditable(True)
        self.azure_region_edit.addItems(AZURE_REGIONS)
        self.azure_region_edit.setCurrentText(self.config.get("azure_region", "eastus"))
        self.azure_key_edit = QTextEdit()
        self.azure_key_edit.setPlainText(self.config.get("azure_subscription_key", ""))
        self.azure_key_edit.setMaximumHeight(60)
        self.azure_key_edit.setPlaceholderText("Paste Azure Subscription Key here...")
        self.azure_voice_edit = QComboBox()
        self.azure_voice_edit.setEditable(True)
        self.azure_voice_edit.addItem("en-US-GuyNeural")
        self.azure_voice_edit.setCurrentText(self.config.get("azure_voice", "en-US-GuyNeural"))
        self.azure_style_combo = QComboBox()
        self.azure_style_combo.addItems(AZURE_STYLES)
        self.azure_style_combo.setCurrentText(self.config.get("azure_style", "calm"))
        self.azure_styledegree_spin = QDoubleSpinBox()
        self.azure_styledegree_spin.setRange(0.01, 2.0)
        self.azure_styledegree_spin.setSingleStep(0.1)
        self.azure_styledegree_spin.setValue(self.config.get("azure_styledegree", 1.0))
        l_azure.addRow("Region:", self.azure_region_edit)
        l_azure.addRow("Key:", self.azure_key_edit)
        l_azure.addRow("Voice:", self.azure_voice_edit)
        l_azure.addRow("Style:", self.azure_style_combo)
        l_azure.addRow("Style Degree:", self.azure_styledegree_spin)
        self.grp_azure.setLayout(l_azure)
        layout.addWidget(self.grp_azure)
        
        form_vol = QFormLayout()
        self.vol_slider = QDoubleSpinBox()
        self.vol_slider.setRange(0.0, 1.0)
        self.vol_slider.setSingleStep(0.1)
        self.vol_slider.setValue(self.config.get('music_volume', 0.2))
        self.vol_slider.setToolTip("Background music volume (0.0 = silent, 1.0 = full)")
        form_vol.addRow("Music Volume:", self.vol_slider)
        layout.addLayout(form_vol)
        layout.addStretch() 
        
        # FIXED: Pass the current text as an argument to satisfy the function signature
        self.on_backend_changed(self.tts_backend_combo.currentText())

    def on_backend_changed(self, text):
        backend = self.tts_backend_combo.currentData()
        if backend == "azure":
            self.grp_edge.setEnabled(False)
            self.grp_azure.setEnabled(True)
        else:
            self.grp_edge.setEnabled(True)
            self.grp_azure.setEnabled(False)

    def get_data(self):
        return {
            'width': self.width_spin.value(),
            'height': self.height_spin.value(),
            'fps': self.fps_spin.value(),
            'transition_duration': self.trans_spin.value(),
            'encoder': self.enc_combo.currentText(),
            'render_workers': 1, # Hardcoded for this tool
            'output_dir': self.out_dir_edit.text(),
            'edge_voice': self.edge_voice_combo.currentData(),
            'edge_tone': self.edge_tone_combo.currentText(),
            'enable_zoom': self.chk_zoom.isChecked(),
            'zoom_factor': self.spin_zoom.value(),
            'music_volume': self.vol_slider.value(),
            'render_mode': 'full', 
            'tts_backend': self.tts_backend_combo.currentData(),
            'azure_region': self.azure_region_edit.currentText(),
            'azure_subscription_key': self.azure_key_edit.toPlainText().strip(),
            'azure_voice': self.azure_voice_edit.currentText(),
            'azure_style': self.azure_style_combo.currentText(),
            'azure_styledegree': self.azure_styledegree_spin.value(),
        }