# ui/widgets.py
from PyQt6.QtWidgets import (QGroupBox, QFormLayout, QSpinBox, QDoubleSpinBox, 
                             QComboBox, QCheckBox, QTextEdit)
from PyQt6.QtCore import pyqtSignal, QObject

class Communicate(QObject):
    dataChanged = pyqtSignal()

class VideoSettingsWidget(QGroupBox):
    def __init__(self, config):
        super().__init__("Video Settings")
        self.config = config
        layout = QFormLayout(self)
        
        self.width_spin = QSpinBox(); self.width_spin.setRange(640, 3840); self.width_spin.setValue(config.get('width', 1280))
        self.height_spin = QSpinBox(); self.height_spin.setRange(480, 2160); self.height_spin.setValue(config.get('height', 720))
        self.fps_spin = QSpinBox(); self.fps_spin.setRange(10, 60); self.fps_spin.setValue(config.get('fps', 30))
        self.trans_spin = QDoubleSpinBox(); self.trans_spin.setRange(0.0, 5.0); self.trans_spin.setValue(config.get('transition_duration', 0.5))
        
        self.enc_combo = QComboBox()
        self.enc_combo.addItems(["auto", "libx264", "h264_nvenc", "h264_amf", "h264_qsv"])
        self.enc_combo.setCurrentText(config.get('encoder', 'auto'))
        
        self.render_mode_combo = QComboBox()
        self.render_mode_combo.addItem("Smart render (Video + Audio)", "full")
        self.render_mode_combo.addItem("Video only (no audio)", "video_only")
        idx = self.render_mode_combo.findData(config.get('render_mode', 'full'))
        if idx >= 0: self.render_mode_combo.setCurrentIndex(idx)

        self.worker_spin = QSpinBox(); self.worker_spin.setRange(1, 8); self.worker_spin.setValue(config.get('render_workers', 3))

        layout.addRow("Width:", self.width_spin)
        layout.addRow("Height:", self.height_spin)
        layout.addRow("FPS:", self.fps_spin)
        layout.addRow("Transition:", self.trans_spin)
        layout.addRow("Encoder:", self.enc_combo)
        layout.addRow("Render Mode:", self.render_mode_combo)
        layout.addRow("Render Workers:", self.worker_spin)

    def get_data(self):
        return {
            'width': self.width_spin.value(), 'height': self.height_spin.value(),
            'fps': self.fps_spin.value(), 'transition_duration': self.trans_spin.value(),
            'encoder': self.enc_combo.currentText(), 'render_mode': self.render_mode_combo.currentData(),
            'render_workers': self.worker_spin.value()
        }

class AudioSettingsWidget(QGroupBox):
    def __init__(self, config):
        super().__init__("Audio Settings")
        self.config = config
        layout = QFormLayout(self)

        # Backend Selection
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Edge TTS (free, no style)", "edge")
        self.backend_combo.addItem("Azure AI Speech (SSML + style)", "azure")
        current_backend = config.get("tts_backend", "edge")
        self.backend_combo.setCurrentIndex(1 if current_backend == "azure" else 0)
        
        # Volume
        self.vol_slider = QDoubleSpinBox()
        self.vol_slider.setRange(0.0, 1.0); self.vol_slider.setSingleStep(0.1)
        self.vol_slider.setValue(config.get('music_volume', 0.2))
        self.vol_slider.setToolTip("Background music volume")

        # Edge Group
        self.grp_edge = QGroupBox("Edge TTS")
        l_edge = QFormLayout()
        self.edge_voice_combo = QComboBox()
        voices = [("en-US-AriaNeural", "Aria (US)"), ("en-US-GuyNeural", "Guy (US)"), 
                  ("en-GB-SoniaNeural", "Sonia (UK)"), ("ja-JP-NanamiNeural", "Nanami (JP)")]
        for v_id, v_name in voices: self.edge_voice_combo.addItem(v_name, v_id)
        self.edge_voice_combo.setCurrentText(config.get('edge_voice', 'en-US-GuyNeural'))
        
        self.edge_tone_combo = QComboBox()
        self.edge_tone_combo.addItems(["general", "cheerful", "sad", "angry", "calm", "excited"])
        self.edge_tone_combo.setCurrentText(config.get('edge_tone', 'general'))
        l_edge.addRow("Voice:", self.edge_voice_combo); l_edge.addRow("Tone:", self.edge_tone_combo)
        self.grp_edge.setLayout(l_edge)

        # Azure Group
        self.grp_azure = QGroupBox("Azure TTS")
        l_azure = QFormLayout()
        self.azure_region = QComboBox(); self.azure_region.setEditable(True)
        self.azure_region.addItems(["eastus", "westus", "westeurope"])
        self.azure_region.setCurrentText(config.get("azure_region", "eastus"))
        
        self.azure_key = QTextEdit(); self.azure_key.setMaximumHeight(50)
        self.azure_key.setPlainText(config.get("azure_subscription_key", ""))
        
        self.azure_voice = QComboBox(); self.azure_voice.setEditable(True)
        self.azure_voice.addItem("en-US-GuyNeural")
        self.azure_voice.setCurrentText(config.get("azure_voice", "en-US-GuyNeural"))
        
        self.azure_style = QComboBox()
        self.azure_style.addItems(["calm", "cheerful", "sad", "angry", "excited"])
        self.azure_style.setCurrentText(config.get("azure_style", "calm"))
        
        self.azure_style_deg = QDoubleSpinBox(); self.azure_style_deg.setRange(0.01, 2.0)
        self.azure_style_deg.setValue(config.get("azure_styledegree", 1.0))

        l_azure.addRow("Region:", self.azure_region); l_azure.addRow("Key:", self.azure_key)
        l_azure.addRow("Voice:", self.azure_voice); l_azure.addRow("Style:", self.azure_style)
        l_azure.addRow("Style Deg:", self.azure_style_deg)
        self.grp_azure.setLayout(l_azure)

        # Layout Assembly
        layout.addRow("Backend:", self.backend_combo)
        layout.addRow(self.grp_edge)
        layout.addRow(self.grp_azure)
        layout.addRow("Music Vol:", self.vol_slider)

        # Logic
        self.backend_combo.currentDataChanged.connect(self.toggle_backend)
        self.toggle_backend()

    def toggle_backend(self):
        is_azure = self.backend_combo.currentData() == "azure"
        self.grp_edge.setEnabled(not is_azure)
        self.grp_azure.setEnabled(is_azure)

    def get_data(self):
        return {
            'tts_backend': self.backend_combo.currentData(),
            'edge_voice': self.edge_voice_combo.currentData(),
            'edge_tone': self.edge_tone_combo.currentText(),
            'music_volume': self.vol_slider.value(),
            'azure_region': self.azure_region.currentText(),
            'azure_subscription_key': self.azure_key.toPlainText().strip(),
            'azure_voice': self.azure_voice.currentText(),
            'azure_style': self.azure_style.currentText(),
            'azure_styledegree': self.azure_style_deg.value()
        }

class VisualEffectsWidget(QGroupBox):
    def __init__(self, config):
        super().__init__("Visual Effects")
        self.config = config
        layout = QFormLayout(self)
        
        self.chk_zoom = QCheckBox("Enable Ken Burns (Slow Zoom)")
        self.chk_zoom.setChecked(config.get('enable_zoom', True))
        
        self.spin_zoom = QDoubleSpinBox()
        self.spin_zoom.setRange(1.01, 2.0); self.spin_zoom.setSingleStep(0.05)
        self.spin_zoom.setValue(config.get('zoom_factor', 1.1)); self.spin_zoom.setSuffix("x")
        
        layout.addRow(self.chk_zoom)
        layout.addRow("Max Zoom:", self.spin_zoom)

    def get_data(self):
        return {'enable_zoom': self.chk_zoom.isChecked(), 'zoom_factor': self.spin_zoom.value()}