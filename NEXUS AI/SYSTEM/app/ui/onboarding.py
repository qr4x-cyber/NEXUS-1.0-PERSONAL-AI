"""İlk kurulum sihirbazı: API anahtarı, kullanıcı profili, AI adı ve tema rengi."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import ACCENTS, Config
from ..gemini import validate_key
from ..theme import build_stylesheet
from ..utils import Task


class OnboardingDialog(QDialog):
    completed = Signal()

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.accent = config.accent if config.accent in ACCENTS.values() else ACCENTS["Mavi"]
        self.setWindowTitle("Nexus · İlk Kurulum")
        self.setFixedSize(660, 590)
        self.setStyleSheet(build_stylesheet(self.accent))

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 20)
        root.setSpacing(14)

        # baslik
        head = QHBoxLayout()
        head.setSpacing(12)
        self.dot = QLabel("◉")
        self.dot.setStyleSheet(f"color:{self.accent}; font-size:26px;")
        head.addWidget(self.dot)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("NEXUS")
        title.setStyleSheet("font-size:19px; font-weight:700; letter-spacing:4px;")
        titles.addWidget(title)
        subtitle = QLabel("Kişisel yapay zekâ asistanın · Gemini ile çalışır")
        subtitle.setObjectName("Muted")
        titles.addWidget(subtitle)
        head.addLayout(titles)
        head.addStretch(1)
        root.addLayout(head)

        # icerik
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_api())
        self.stack.addWidget(self._page_user())
        self.stack.addWidget(self._page_ai_name())
        self.stack.addWidget(self._page_color())
        root.addWidget(self.stack, 1)

        # alt satir
        footer = QHBoxLayout()
        self.dots = []
        dots_row = QHBoxLayout()
        dots_row.setSpacing(6)
        for index in range(4):
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{self.accent if index == 0 else '#c9d0d8'}; font-size:10px;")
            dots_row.addWidget(dot)
            self.dots.append(dot)
        footer.addLayout(dots_row)
        footer.addStretch(1)
        self.error = QLabel("")
        self.error.setStyleSheet("color:#d64545; font-size:11px;")
        footer.addWidget(self.error)
        self.back_btn = QPushButton("Geri")
        self.back_btn.setObjectName("GhostButton")
        self.back_btn.clicked.connect(self._back)
        self.back_btn.setEnabled(False)
        footer.addWidget(self.back_btn)
        self.next_btn = QPushButton("Devam")
        self.next_btn.setObjectName("AccentButton")
        self.next_btn.setMinimumWidth(110)
        self.next_btn.clicked.connect(self._next)
        footer.addWidget(self.next_btn)
        root.addLayout(footer)

        self.api_input.setFocus()

    # ------------------------------------------------------------------ sayfalar
    def _page_api(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        heading = QLabel("Başlamak için Gemini API anahtarın")
        heading.setStyleSheet("font-size:16px; font-weight:600;")
        layout.addWidget(heading)
        info = QLabel(
            "Anahtarını <a href='https://aistudio.google.com/apikey' "
            "style='color:#2f6bff;'>Google AI Studio</a> üzerinden ücretsiz "
            "oluşturabilirsin. Anahtar sadece bu bilgisayarda saklanır."
        )
        info.setOpenExternalLinks(True)
        info.setWordWrap(True)
        info.setObjectName("Muted")
        layout.addWidget(info)

        row = QHBoxLayout()
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("AIza…")
        self.api_input.setEchoMode(QLineEdit.Password)
        self.api_input.setMinimumHeight(38)
        row.addWidget(self.api_input, 1)
        self.show_btn = QPushButton("Göster")
        self.show_btn.setObjectName("GhostButton")
        self.show_btn.setCheckable(True)
        self.show_btn.toggled.connect(self._toggle_key)
        row.addWidget(self.show_btn)
        layout.addLayout(row)

        check_row = QHBoxLayout()
        self.check_btn = QPushButton("Anahtarı doğrula")
        self.check_btn.setObjectName("GhostButton")
        self.check_btn.clicked.connect(self._check_key)
        check_row.addWidget(self.check_btn)
        self.check_status = QLabel("")
        self.check_status.setObjectName("Tiny")
        check_row.addWidget(self.check_status, 1)
        layout.addLayout(check_row)
        layout.addStretch(1)
        return page

    def _page_user(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        heading = QLabel("Seni tanıyalım")
        heading.setStyleSheet("font-size:16px; font-weight:600;")
        layout.addWidget(heading)
        layout.addWidget(self._hint("Asistanın sana nasıl hitap etmesini istersin?"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Adın veya lakabın")
        self.name_input.setMinimumHeight(38)
        layout.addWidget(self.name_input)
        layout.addWidget(self._hint("Hakkında bilmesi gerekenler (ilgi alanların, işin, tarzın…)"))
        self.about_input = QPlainTextEdit()
        self.about_input.setPlaceholderText(
            "Örn: Yazılım geliştiriciyim, kısa ve net cevapları severim, "
            "sabahları erken çalışırım…"
        )
        self.about_input.setMinimumHeight(120)
        layout.addWidget(self.about_input)
        layout.addStretch(1)
        return page

    def _page_ai_name(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)
        heading = QLabel("Asistanının adı ne olsun?")
        heading.setStyleSheet("font-size:16px; font-weight:600;")
        layout.addWidget(heading)
        layout.addWidget(
            self._hint("Bu isimle ona seslenebileceksin. Reaktör uykudayken adını söylemen yeterli.")
        )
        self.ai_input = QLineEdit("Nexus")
        self.ai_input.setMinimumHeight(38)
        layout.addWidget(self.ai_input)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        for name in ("Nexus", "Jarvis", "Aria", "Orion", "Nova", "Ada"):
            chip = QPushButton(name)
            chip.setObjectName("GhostButton")
            chip.clicked.connect(lambda _, n=name: self.ai_input.setText(n))
            chips.addWidget(chip)
        chips.addStretch(1)
        layout.addLayout(chips)
        layout.addStretch(1)
        return page

    def _page_color(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)
        heading = QLabel("Arayüz rengini seç")
        heading.setStyleSheet("font-size:16px; font-weight:600;")
        layout.addWidget(heading)
        layout.addWidget(self._hint("Bu renk reaktör çekirdeğinde ve vurgularda kullanılacak."))

        self.group = QButtonGroup(self)
        swatches = QHBoxLayout()
        swatches.setSpacing(12)
        self.swatches = {}
        for index, (name, hexcode) in enumerate(ACCENTS.items()):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setFixedSize(48, 48)
            btn.setToolTip(name)
            btn.setChecked(hexcode == self.accent)
            btn.clicked.connect(lambda _, h=hexcode: self._pick_color(h))
            self.group.addButton(btn, index)
            swatches.addWidget(btn)
            self.swatches[hexcode] = btn
        swatches.addStretch(1)
        layout.addLayout(swatches)
        self._refresh_swatches()

        preview = QWidget()
        preview.setStyleSheet(
            f"background:#f7f8fa; border:1px solid #dde1e7; border-radius:16px;"
        )
        preview_layout = QHBoxLayout(preview)
        preview_layout.setContentsMargins(18, 16, 18, 16)
        preview_layout.setSpacing(14)
        orb = QLabel()
        orb.setFixedSize(54, 54)
        orb.setStyleSheet(
            f"border-radius:27px; background:{self.accent}; border:6px solid {self.accent};"
        )
        preview_layout.addWidget(orb)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        sample = QLabel("Merhaba, ben hazırım.")
        sample.setStyleSheet("border:none; font-size:13px; font-weight:600;")
        texts.addWidget(sample)
        sample2 = QLabel("Sesli sohbet · PC kontrolü · Hatırlatıcılar")
        sample2.setObjectName("Muted")
        sample2.setStyleSheet("border:none; color:#77808d; font-size:11px;")
        texts.addWidget(sample2)
        preview_layout.addLayout(texts, 1)
        self.preview_orb = orb
        self.preview_accent_btn = QPushButton("Vurgu")
        self.preview_accent_btn.setStyleSheet(
            f"background:{self.accent}; color:white; border:none; border-radius:9px; padding:7px 14px;"
        )
        preview_layout.addWidget(self.preview_accent_btn)
        layout.addWidget(preview)
        layout.addStretch(1)
        return page

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("Muted")
        return label

    # -------------------------------------------------------------- etkilesim
    def _toggle_key(self, shown: bool):
        self.api_input.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password)
        self.show_btn.setText("Gizle" if shown else "Göster")

    def _check_key(self):
        key = self.api_input.text().strip()
        if len(key) < 15:
            self.check_status.setText("Anahtar çok kısa görünüyor.")
            return
        self.check_status.setText("Doğrulanıyor…")
        self.check_btn.setEnabled(False)
        self._task = Task(validate_key, key)
        self._task.done.connect(self._key_ok)
        self._task.failed.connect(lambda msg: self._key_fail(msg))
        self._task.start()

    def _key_ok(self, result):
        ok, message = result
        self.check_btn.setEnabled(True)
        if ok:
            self.check_status.setText("✓ Anahtar çalışıyor")
            self.check_status.setStyleSheet("color:#18a558; font-size:11px;")
        else:
            self.check_status.setText("✗ Doğrulanamadı: " + message[:70])
            self.check_status.setStyleSheet("color:#d64545; font-size:11px;")

    def _key_fail(self, message: str):
        self.check_btn.setEnabled(True)
        self.check_status.setText("✗ " + message[:70])

    def _pick_color(self, hexcode: str):
        self.accent = hexcode
        self.setStyleSheet(build_stylesheet(hexcode))
        self.dot.setStyleSheet(f"color:{hexcode}; font-size:26px;")
        self._refresh_swatches()
        self.preview_orb.setStyleSheet(
            f"border-radius:27px; background:{hexcode}; border:6px solid {hexcode};"
        )
        self.preview_accent_btn.setStyleSheet(
            f"background:{hexcode}; color:white; border:none; border-radius:9px; padding:7px 14px;"
        )
        for index, dot in enumerate(self.dots):
            dot.setStyleSheet(
                f"color:{hexcode if index == self.stack.currentIndex() else '#c9d0d8'}; font-size:10px;"
            )

    def _refresh_swatches(self):
        for hexcode, btn in self.swatches.items():
            selected = hexcode == self.accent
            border = "3px solid #ffffff" if selected else "3px solid transparent"
            btn.setText("✓" if selected else "")
            btn.setStyleSheet(
                f"background:{hexcode}; border-radius:24px; border:{border};"
                "color:#ffffff; font-weight:700;"
            )

    # ----------------------------------------------------------------- adimlar
    def _next(self):
        index = self.stack.currentIndex()
        if index == 0:
            key = self.api_input.text().strip()
            if len(key) < 15:
                self.error.setText("Geçerli bir API anahtarı gir.")
                return
            self.config.api_key = key
        elif index == 1:
            name = self.name_input.text().strip()
            if not name:
                self.error.setText("Adını yazmadan devam edemeyiz.")
                return
            self.config.user_name = name
            self.config.user_about = self.about_input.toPlainText().strip()
        elif index == 2:
            ai_name = self.ai_input.text().strip()
            if not ai_name:
                self.error.setText("Asistanına bir ad ver.")
                return
            self.config.ai_name = ai_name
        else:
            self.config.accent = self.accent
            self.config.onboarding_done = True
            self.config.save()
            self.completed.emit()
            self.accept()
            return

        self.error.setText("")
        self.stack.setCurrentIndex(index + 1)
        self.back_btn.setEnabled(True)
        if index + 1 == 3:
            self.next_btn.setText("Başla")
        for idx, dot in enumerate(self.dots):
            dot.setStyleSheet(
                f"color:{self.accent if idx <= index + 1 else '#c9d0d8'}; font-size:10px;"
            )
        if index + 1 == 1:
            self.name_input.setFocus()
        elif index + 1 == 2:
            self.ai_input.setFocus()

    def _back(self):
        index = self.stack.currentIndex()
        if index == 0:
            return
        self.stack.setCurrentIndex(index - 1)
        self.back_btn.setEnabled(index - 1 > 0)
        self.next_btn.setText("Devam")
        self.error.setText("")
        for idx, dot in enumerate(self.dots):
            dot.setStyleSheet(
                f"color:{self.accent if idx <= index - 1 else '#c9d0d8'}; font-size:10px;"
            )
