"""Ayarlar penceresi."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import ACCENTS, VOICES, Config
from ..theme import build_stylesheet


class SettingsDialog(QDialog):
    changed = Signal()

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Ayarlar")
        self.setFixedSize(560, 610)
        self.setStyleSheet(build_stylesheet(config.accent))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)

        title = QLabel("AYARLAR")
        title.setStyleSheet("font-size:11px; font-weight:700; letter-spacing:2px; color:#77808d;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setSpacing(10)

        self.api_input = QLineEdit(config.api_key)
        self.api_input.setEchoMode(QLineEdit.Password)
        self.api_input.setMinimumHeight(34)
        form.addRow("Gemini API anahtarı", self.api_input)

        self.name_input = QLineEdit(config.user_name)
        self.name_input.setMinimumHeight(34)
        form.addRow("Adın", self.name_input)

        self.ai_input = QLineEdit(config.ai_name)
        self.ai_input.setMinimumHeight(34)
        form.addRow("Asistanın adı", self.ai_input)

        self.about_input = QPlainTextEdit(config.user_about)
        self.about_input.setFixedHeight(80)
        form.addRow("Hakkında", self.about_input)

        self.accent_combo = QComboBox()
        for name, hexcode in ACCENTS.items():
            self.accent_combo.addItem(f"● {name}", hexcode)
        current = config.accent
        for index in range(self.accent_combo.count()):
            if self.accent_combo.itemData(index) == current:
                self.accent_combo.setCurrentIndex(index)
        self.accent_combo.currentIndexChanged.connect(self._apply_accent)
        form.addRow("Arayüz rengi", self.accent_combo)

        self.voice_combo = QComboBox()
        self.voice_combo.addItems(VOICES)
        if config.voice in VOICES:
            self.voice_combo.setCurrentText(config.voice)
        form.addRow("Ses", self.voice_combo)

        layout.addLayout(form)

        advanced_label = QLabel("GELİŞMİŞ")
        advanced_label.setStyleSheet(
            "font-size:10px; font-weight:700; letter-spacing:2px; color:#77808d;"
        )
        layout.addWidget(advanced_label)

        advanced = QFormLayout()
        advanced.setSpacing(8)
        self.live_model = QLineEdit(config.live_model)
        self.live_model.setPlaceholderText("otomatik")
        self.text_model = QLineEdit(config.text_model)
        self.text_model.setPlaceholderText("otomatik")
        self.tts_model = QLineEdit(config.tts_model)
        self.tts_model.setPlaceholderText("otomatik")
        advanced.addRow("Canlı (ses) modeli", self.live_model)
        advanced.addRow("Metin modeli", self.text_model)
        advanced.addRow("Seslendirme modeli", self.tts_model)
        layout.addLayout(advanced)

        self.confirm_check = QCheckBox("Tehlikeli işlemlerde onay sor (kapatma, komut, uygulama kapatma)")
        self.confirm_check.setChecked(config.confirm_dangerous)
        layout.addWidget(self.confirm_check)

        self.wake_check = QCheckBox("Uykudayken adımı söylediğimde uyan")
        self.wake_check.setChecked(config.wake_word_enabled)
        layout.addWidget(self.wake_check)

        hint = QLabel("Model alanları boş bırakılırsa çalışan model otomatik seçilir.")
        hint.setObjectName("Tiny")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Vazgeç")
        cancel.setObjectName("GhostButton")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("Kaydet")
        save.setObjectName("AccentButton")
        save.clicked.connect(self._save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _apply_accent(self):
        hexcode = self.accent_combo.currentData()
        if hexcode:
            self.setStyleSheet(build_stylesheet(hexcode))

    def _save(self):
        self.config.api_key = self.api_input.text().strip()
        self.config.user_name = self.name_input.text().strip()
        self.config.ai_name = self.ai_input.text().strip() or "Nexus"
        self.config.user_about = self.about_input.toPlainText().strip()
        self.config.accent = self.accent_combo.currentData() or self.config.accent
        self.config.voice = self.voice_combo.currentText()
        self.config.live_model = self.live_model.text().strip()
        self.config.text_model = self.text_model.text().strip()
        self.config.tts_model = self.tts_model.text().strip()
        self.config.confirm_dangerous = self.confirm_check.isChecked()
        self.config.wake_word_enabled = self.wake_check.isChecked()
        self.config.save()
        self.changed.emit()
        self.accept()
