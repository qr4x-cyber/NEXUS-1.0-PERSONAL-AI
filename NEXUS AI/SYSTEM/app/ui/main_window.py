"""Ana pencere: paneller, reaktör, sohbet, sesli oturum ve sistem kontrolü."""

from __future__ import annotations

import html
import threading
from datetime import datetime

from PySide6.QtCore import QBuffer, QIODevice, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..audio import Speaker, VoiceListener
from ..config import Config
from ..gemini import GeminiBrain
from ..live import LiveEngine
from ..theme import build_stylesheet
from ..tools import ToolRegistry
from ..utils import Task, name_spoken
from .onboarding import OnboardingDialog
from .panels import (
    CameraPreview,
    ClockPanel,
    MapPanel,
    NewsPanel,
    NotesPanel,
    RemindersPanel,
    WeatherPanel,
)
from .reactor import ReactorCore
from .settings import SettingsDialog


# ---------------------------------------------------------------------- yardimci
class ConfirmBridge(QObject):
    requested = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._event = threading.Event()
        self._result = False
        self._lock = threading.Lock()

    def ask(self, title: str, detail: str) -> bool:
        with self._lock:
            self._result = False
            self._event.clear()
            self.requested.emit(title, detail)
            self._event.wait(60)
            return self._result

    def resolve(self, ok: bool) -> None:
        self._result = ok
        self._event.set()


class ConfirmBox(QObject):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent

    def __call__(self, title: str, detail: str) -> bool:
        box = QMessageBox(self.parent)
        box.setWindowTitle(title)
        box.setText(detail)
        box.setIcon(QMessageBox.Question)
        ok_button = box.addButton("Onayla", QMessageBox.AcceptRole)
        box.addButton("İptal", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is ok_button


class Toast(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setStyleSheet(
            "QFrame#Toast { background: #2b313a; border-radius: 12px; }"
            "QLabel { color: #ffffff; font-size: 12px; background: transparent; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.hide()

    def show_message(self, text: str, msec: int = 5200):
        self.label.setText(text)
        self.label.setMaximumWidth(520)
        self.adjustSize()
        self._reposition()
        self.raise_()
        self.show()
        QTimer.singleShot(msec, self.hide)

    def _reposition(self):
        parent = self.parentWidget()
        if not parent:
            return
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 150
        self.move(max(12, x), max(12, y))


class CameraFeed(QObject):
    frame_ready = Signal(QImage)
    still_ready = Signal(bytes)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.camera = None
        self.session = None
        self._sink = None
        self._last_still = 0.0

    def start(self) -> bool:
        try:
            from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices, QVideoSink
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Kamera modülü yok: {exc}")
            return False
        devices = QMediaDevices.videoInputs()
        if not devices:
            self.failed.emit("Kamera bulunamadı.")
            return False
        try:
            self._sink = QVideoSink()
            self._sink.videoFrameChanged.connect(self._on_frame)
            self.camera = QCamera(devices[0])
            self.session = QMediaCaptureSession()
            self.session.setCamera(self.camera)
            self.session.setVideoSink(self._sink)
            self.camera.start()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Kamera açılamadı: {exc}")
            return False
        return True

    def stop(self) -> None:
        try:
            if self.camera is not None:
                self.camera.stop()
        except Exception:
            pass
        self.camera = None
        self.session = None

    def _on_frame(self, frame):
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self.frame_ready.emit(image)
        now = datetime.now().timestamp()
        if now - self._last_still > 3.0:
            self._last_still = now
            scaled = image.scaled(640, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            buffer = QBuffer()
            buffer.open(QIODevice.WriteOnly)
            scaled.save(buffer, "JPEG", 82)
            data = bytes(buffer.data())
            if data:
                self.still_ready.emit(data)


# ------------------------------------------------------------------- ana pencere
class MainWindow(QWidget):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.setObjectName("Root")
        self.setWindowTitle(f"{config.ai_name} · Kişisel Yapay Zekâ Asistanı")
        self.resize(1400, 880)
        self.setMinimumSize(1120, 760)

        self.awake = False
        self._tasks: set = set()
        self._live_connected = False
        self._pending_text: list[str] = []
        self._pending_image: bytes | None = None
        self._stream_role = None
        self._messages: list[dict] = []
        self._transcribing = False
        self._speaking_timer = QTimer(self)
        self._speaking_timer.setInterval(350)
        self._speaking_timer.timeout.connect(self._check_speaking)
        self._last_error = ""

        self.speaker = Speaker()
        self.speaker.on_error = self._on_audio_error
        self.confirm_bridge = ConfirmBridge()
        self.confirm_box = ConfirmBox(self)
        self.confirm_bridge.requested.connect(self._ask_confirm)

        self.tools = ToolRegistry(
            config,
            hooks={
                "on_reminder": self._on_reminder_added,
                "on_notes_changed": self._on_notes_changed,
                "on_accent": self._on_accent_changed,
            },
            confirm=self.confirm_bridge.ask,
        )
        self.brain = GeminiBrain(config, self.tools)
        self.listener = VoiceListener()
        self.listener.clip_ready.connect(self._on_clip)
        self.listener.level.connect(self._on_level)
        self.listener.error.connect(self._on_listener_error)

        self.live = LiveEngine(config, self.brain, self.tools, self.speaker)
        self.live.user_text.connect(lambda text: self._append_stream("user", text))
        self.live.ai_text.connect(lambda text: self._append_stream("ai", text))
        self.live.turn_complete.connect(self._close_stream)
        self.live.state.connect(self._on_live_state)
        self.live.level.connect(self._on_level)
        self.live.error.connect(self._on_live_error)
        self.live.notice.connect(lambda text: self.toast(text, 3500))
        self.live.connected.connect(self._on_live_connected)

        self.camera = CameraFeed()
        self.camera.frame_ready.connect(self._on_camera_frame)
        self.camera.still_ready.connect(self._on_camera_still)
        self.camera.failed.connect(self._on_camera_error)

        self._build_ui()
        self.apply_theme()

        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(5000)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start()

        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)

        self._welcome()
        self._refresh_routing()
        if config.camera_enabled:
            self.camera_btn.setChecked(True)
            self._toggle_camera(True)
        if config.api_key:
            self._run_task(self.brain.resolve, "text")
        greeting = f"Merhaba {config.user_name}." if config.user_name else "Merhaba."
        self.toast(
            f"{greeting} Uyandırmak için çekirdeğe tıkla ya da “{config.ai_name}” diye seslen.",
            6500,
        )

    # -------------------------------------------------------------------- arayuz
    def _build_ui(self):
        root = QGridLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setHorizontalSpacing(14)
        root.setVerticalSpacing(14)

        # sol kolon
        left = QWidget()
        left.setFixedWidth(300)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)
        self.weather = WeatherPanel(self.config)
        left_layout.addWidget(self.weather)
        self.reminders = RemindersPanel(self.config, on_add=self._on_reminder_added)
        left_layout.addWidget(self.reminders, 3)
        self.notes = NotesPanel(self.config)
        left_layout.addWidget(self.notes, 4)
        root.addWidget(left, 0, 0)

        # orta kolon
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        self.settings_btn = QToolButton()
        self.settings_btn.setObjectName("IconButton")
        self.settings_btn.setText("⚙")
        self.settings_btn.setToolTip("Ayarlar (Ctrl+,)")
        self.settings_btn.clicked.connect(self.open_settings)
        bar.addWidget(self.settings_btn, 0, Qt.AlignTop)
        bar.addStretch(1)

        self.camera_btn = QToolButton()
        self.camera_btn.setObjectName("IconButton")
        self.camera_btn.setText("🎥")
        self.camera_btn.setCheckable(True)
        self.camera_btn.setToolTip("Canlı kamerayı aç / kapat")
        self.camera_btn.clicked.connect(self._toggle_camera)
        bar.addWidget(self.camera_btn)

        self.mode_btn = QToolButton()
        self.mode_btn.setObjectName("ModeButton")
        self.mode_btn.setCheckable(True)
        self.mode_btn.setChecked(self.config.mode == "s2s")
        self.mode_btn.setToolTip("Sesli sohbet ↔ yazı + ses modu")
        self.mode_btn.clicked.connect(self._toggle_mode)
        bar.addWidget(self.mode_btn)
        self._update_mode_button()

        self.mic_btn = QToolButton()
        self.mic_btn.setObjectName("IconButton")
        self.mic_btn.setText("🎤")
        self.mic_btn.setCheckable(True)
        self.mic_btn.setChecked(self.config.mic_enabled)
        self.mic_btn.setToolTip("Mikrofonu aç / kapat")
        self.mic_btn.clicked.connect(self._toggle_mic)
        bar.addWidget(self.mic_btn)
        bar.addStretch(1)

        self.status_pill = QLabel("")
        self.status_pill.setStyleSheet(
            "background:#ffffff; border:1px solid #dde1e7; border-radius:13px;"
            "padding:6px 12px; font-size:10px; font-weight:700; letter-spacing:1.2px; color:#77808d;"
        )
        bar.addWidget(self.status_pill, 0, Qt.AlignTop)
        center_layout.addLayout(bar)

        # reaktor
        reactor_wrap = QWidget()
        reactor_layout = QVBoxLayout(reactor_wrap)
        reactor_layout.setContentsMargins(0, 0, 0, 0)
        reactor_layout.setSpacing(6)
        reactor_layout.addStretch(1)
        self.reactor = ReactorCore(self.config.accent)
        self.reactor.clicked.connect(self._toggle_awake)
        reactor_layout.addWidget(self.reactor, 0, Qt.AlignHCenter)
        self.hint = QLabel("")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setObjectName("Muted")
        reactor_layout.addWidget(self.hint)
        reactor_layout.addStretch(1)
        center_layout.addWidget(reactor_wrap, 1)

        # kamera onizleme
        self.preview_row = QHBoxLayout()
        self.preview_row.addStretch(1)
        self.preview = CameraPreview()
        self.preview.hide()
        self.preview_row.addWidget(self.preview)
        self.preview_row.addStretch(1)
        center_layout.addLayout(self.preview_row)

        # sohbet dokumu
        self.chat = QTextEdit()
        self.chat.setObjectName("Transcript")
        self.chat.setReadOnly(True)
        self.chat.setMinimumHeight(120)
        self.chat.setMaximumHeight(210)
        self.chat.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        center_layout.addWidget(self.chat, 0)

        # giris satiri
        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setObjectName("ChatInput")
        self.input.setPlaceholderText("Bir şey yaz veya mikrofonla konuş…")
        self.input.returnPressed.connect(self._send)
        row.addWidget(self.input, 1)
        self.send_btn = QPushButton("Gönder")
        self.send_btn.setObjectName("AccentButton")
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)
        center_layout.addLayout(row)
        root.addWidget(center, 0, 1)

        # sag kolon
        right = QWidget()
        right.setFixedWidth(330)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)
        self.map_panel = MapPanel(self.config)
        right_layout.addWidget(self.map_panel)
        self.news = NewsPanel(self.config)
        right_layout.addWidget(self.news, 1)
        self.clock = ClockPanel()
        right_layout.addWidget(self.clock)
        root.addWidget(right, 0, 2)

        root.setColumnStretch(0, 0)
        root.setColumnStretch(1, 1)
        root.setColumnStretch(2, 0)

        self.toast_widget = Toast(self)
        self._set_state("sleeping")

    def apply_theme(self):
        self.setStyleSheet(build_stylesheet(self.config.accent))
        self.reactor.set_accent(self.config.accent)
        self._render_chat()

    # --------------------------------------------------------------------- sohbet
    def _run_task(self, fn, *args, on_done=None, on_fail=None):
        task = Task(fn, *args)
        self._tasks.add(task)
        if on_done is not None:
            task.done.connect(on_done)
        if on_fail is not None:
            task.failed.connect(on_fail)

        def cleanup(*_ignored):
            self._tasks.discard(task)

        task.done.connect(cleanup)
        task.failed.connect(cleanup)
        task.start()
        return task

    def _welcome(self):
        name = self.config.user_name or "dostum"
        self._messages = [
            {
                "role": "system",
                "text": (
                    f"Merhaba {name}. Ben {self.config.ai_name}. "
                    "Reaktöre tıklayarak ya da adımı söyleyerek beni uyandırabilirsin."
                ),
            }
        ]
        self._render_chat()

    def _render_chat(self):
        accent = self.config.accent
        blocks = []
        for message in self._messages[-40:]:
            role = message["role"]
            text = html.escape(message["text"]).replace("\n", "<br>")
            if role == "user":
                label = (self.config.user_name or "SEN").upper()
                color = "#77808d"
            elif role == "ai":
                label = self.config.ai_name.upper()
                color = accent
            else:
                label = "SİSTEM"
                color = "#a0a8b4"
            blocks.append(
                f"<div style='margin-bottom:9px;'>"
                f"<span style='color:{color}; font-size:10px; font-weight:700; "
                f"letter-spacing:1.2px;'>{html.escape(label)}</span>"
                f"<div style='color:#1e232b; font-size:13px;'>{text}</div>"
                f"</div>"
            )
        self.chat.setHtml("<div style='line-height:140%;'>" + "".join(blocks) + "</div>")
        self.chat.moveCursor(QTextCursor.End)

    def _append_block(self, role: str, text: str):
        self._stream_role = None
        self._messages.append({"role": role, "text": text})
        self._render_chat()

    def _append_stream(self, role: str, text: str):
        if not text:
            return
        if self._stream_role == role and self._messages:
            self._messages[-1]["text"] += text
        else:
            self._messages.append({"role": role, "text": text})
            self._stream_role = role
        self._render_chat()

    def _close_stream(self):
        self._stream_role = None
        self._render_chat()

    # ---------------------------------------------------------------------- durum
    def _set_state(self, state: str):
        self.reactor.set_state(state)
        hints = {
            "sleeping": "Adını söyle ya da çekirdeğe tıkla",
            "idle": "Hazırım · yazabilir veya mikrofonu kullanabilirsin",
            "connecting": "Bağlanıyor…",
            "listening": "Dinliyorum, konuşabilirsin",
            "thinking": "Düşünüyorum…",
            "speaking": "Konuşuyorum…",
        }
        self.hint.setText(hints.get(state, ""))
        labels = {
            "sleeping": "UYKUDA",
            "idle": "HAZIR",
            "connecting": "BAĞLANIYOR",
            "listening": "DİNLİYOR",
            "thinking": "DÜŞÜNÜYOR",
            "speaking": "KONUŞUYOR",
        }
        self.status_pill.setText(
            f"{self.config.ai_name.upper()} · {labels.get(state, 'HAZIR')}"
        )

    def _update_mode_button(self):
        s2s = self.config.mode == "s2s"
        self.mode_btn.setChecked(s2s)
        self.mode_btn.setText("SESLİ SOHBET" if s2s else "YAZI + SES")
        self.mode_btn.setToolTip(
            "Şu an: sesli sohbet (kesintisiz mikrofon). Tıkla → yazı + ses modu."
            if s2s
            else "Şu an: yazı + ses modu. Tıkla → sesli sohbet."
        )

    def toast(self, text: str, msec: int = 5200):
        if not text:
            return
        self.toast_widget.show_message(text, msec)

    # ------------------------------------------------------------------ uyandirma
    def _toggle_awake(self):
        if self.awake:
            self.sleep()
        else:
            self.wake()

    def wake(self, reason: str = "manual"):
        if self.awake:
            return
        self.awake = True
        self._stream_role = None
        QApplication.beep()
        if self.config.mode == "s2s":
            self._set_state("connecting")
            self._start_live()
            QTimer.singleShot(900, self._ensure_live)
        else:
            self._set_state("idle")
        self._refresh_routing()
        if reason == "voice":
            self._speak_short(f"Buradayım. Dinliyorum.")
        self.toast(f"{self.config.ai_name} uyandı.")

    def sleep(self):
        if not self.awake:
            return
        self.awake = False
        self._pending_text.clear()
        self.live.stop()
        self.speaker.clear()
        self._set_state("sleeping")
        self._refresh_routing()
        self.toast(f"{self.config.ai_name} uykuya geçti.")

    def _start_live(self):
        if not self.live.running:
            self.live.start()

    def _ensure_live(self):
        if self.awake and self.config.mode == "s2s" and not self.live.running:
            self.live.start()
            self._refresh_routing()

    # --------------------------------------------------------------- ses yonlendirme
    def _refresh_routing(self):
        live_owns_mic = self.awake and self.config.mode == "s2s" and self.live.running
        if live_owns_mic:
            self.listener.stop()
            self.live.set_mic(self.config.mic_enabled)
            return
        if self.live.running:
            self.live.set_mic(False)
        if not self.config.mic_enabled:
            self.listener.stop()
            return
        should_listen = (not self.awake and self.config.wake_word_enabled) or (
            self.awake and self.config.mode == "tts"
        )
        if should_listen:
            self.listener.gate = lambda: self.speaker.is_playing
            self.listener.start()
        else:
            self.listener.stop()

    def _toggle_mic(self, checked: bool):
        self.config.mic_enabled = checked
        self.config.save()
        self.live.set_mic(checked)
        self._refresh_routing()
        self.toast("Mikrofon açık" if checked else "Mikrofon kapalı", 2500)

    def _toggle_mode(self):
        self.config.mode = "tts" if self.config.mode == "s2s" else "s2s"
        self.config.save()
        self._update_mode_button()
        self._close_stream()
        if self.awake:
            self.speaker.clear()
            self.live.stop()
            if self.config.mode == "s2s":
                self._set_state("connecting")
                QTimer.singleShot(700, self._ensure_live)
            else:
                self._set_state("idle")
        self._refresh_routing()
        label = "sesli sohbet" if self.config.mode == "s2s" else "yazı + ses"
        self._append_block("system", f"Mod değişti: {label}.")
        self.toast(f"Mod: {label}", 2500)

    # --------------------------------------------------------------------- mikrofon
    def _on_clip(self, wav: bytes):
        if self._transcribing or not self.config.api_key:
            return
        self._transcribing = True
        waking = not self.awake
        self._run_task(
            self.brain.transcribe,
            wav,
            self.config.ai_name if waking else "",
            on_done=lambda text: self._on_transcript(text, waking),
            on_fail=lambda _msg: self._transcript_failed(),
        )

    def _transcript_failed(self):
        self._transcribing = False

    def _on_transcript(self, text: str, waking: bool):
        self._transcribing = False
        text = (text or "").strip()
        if not text:
            return
        if waking:
            if name_spoken(text, self.config.ai_name):
                self.wake(reason="voice")
            return
        self.input.setText(text)
        self._send()

    def _on_level(self, level: float):
        self.reactor.set_level(level)

    def _on_listener_error(self, message: str):
        self.toast(message, 5000)

    # ------------------------------------------------------------------- Live API
    def _on_live_connected(self, connected: bool):
        self._live_connected = connected
        if connected:
            while self._pending_text:
                self.live.send_text(self._pending_text.pop(0))
        elif self.awake and self.config.mode == "s2s":
            self._set_state("idle")
            self._refresh_routing()

    def _on_live_state(self, state: str):
        if state == "stopped":
            if self.awake and self.config.mode == "s2s":
                self._set_state("idle")
            self._refresh_routing()
            return
        if not self.awake:
            return
        self._set_state(state)
        if state == "listening":
            self._refresh_routing()

    def _on_live_error(self, message: str):
        if message == self._last_error:
            return
        self._last_error = message
        self._append_block("system", f"Sesli oturum hatası: {message}")
        self.toast(message, 7000)
        QTimer.singleShot(6000, lambda: setattr(self, "_last_error", ""))

    # ---------------------------------------------------------------------- sohbet
    def _send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        if not self.awake:
            self.wake(reason="manual")
        self._append_block("user", text)
        if self.config.mode == "s2s":
            if self._live_connected:
                self.live.send_text(text)
            else:
                self._pending_text.append(text)
                self.toast("Bağlanınca gönderilecek…", 2500)
        else:
            self._ask_text(text)

    def _ask_text(self, text: str):
        image = self._pending_image
        self._pending_image = None
        self._set_state("thinking")
        self._run_task(
            self.brain.ask, text, image,
            on_done=self._on_answer, on_fail=self._on_answer_error,
        )

    def _on_answer(self, answer: str):
        self._append_block("ai", answer)
        self._speak(answer)

    def _on_answer_error(self, message: str):
        self._set_state("idle")
        self._append_block("system", f"Hata: {message}")
        self.toast(message, 7000)

    def _speak(self, text: str):
        if not text.strip():
            self._set_state("idle")
            return
        self._set_state("speaking")
        self._run_task(
            self.brain.synthesize, text,
            on_done=self._on_audio_ready,
            on_fail=lambda message: (self._set_state("idle"), self.toast(message, 5000)),
        )

    def _on_audio_ready(self, data):
        if data:
            self.speaker.play_wav(data)
            self._speaking_timer.start()
        else:
            self._set_state("idle")

    def _speak_short(self, text: str):
        self._run_task(
            self.brain.synthesize, text,
            on_done=lambda data: data and self.speaker.play_wav(data),
        )

    def _check_speaking(self):
        if not self.speaker.is_playing:
            self._speaking_timer.stop()
            if self.awake:
                self._set_state("listening" if self.config.mode == "s2s" and self.live.running else "idle")

    def _on_audio_error(self, message: str):
        self.toast(message, 5000)

    # ---------------------------------------------------------------------- kamera
    def _toggle_camera(self, checked: bool):
        self.config.camera_enabled = checked
        self.config.save()
        if checked:
            if self.camera.start():
                self.preview.show()
                self.toast("Kamera açık · görüntü asistana iletilecek", 3000)
            else:
                self.camera_btn.setChecked(False)
                self.config.camera_enabled = False
                self.config.save()
        else:
            self.camera.stop()
            self.preview.hide()
            self._pending_image = None
            self.toast("Kamera kapalı", 2500)

    def _on_camera_frame(self, image: QImage):
        self.preview.set_frame(image.mirrored(True, False))

    def _on_camera_still(self, jpeg: bytes):
        if not self.config.camera_enabled:
            return
        if self.awake and self.config.mode == "s2s" and self.live.running:
            self.live.send_image(jpeg)
        else:
            self._pending_image = jpeg

    def _on_camera_error(self, message: str):
        self.camera_btn.setChecked(False)
        self.config.camera_enabled = False
        self.config.save()
        self.preview.hide()
        self.toast(message, 5000)

    # ------------------------------------------------------------------ hatirlatici
    def _on_reminder_added(self, item: dict):
        self.reminders.reload()
        text = item.get("text", "")
        when = item.get("when", "")
        try:
            clock = datetime.fromisoformat(when).strftime("%H:%M")
        except Exception:
            clock = ""
        self.toast(f"Hatırlatıcı kuruldu: {text} ({clock})", 4200)

    def _on_notes_changed(self, text: str):
        self.notes.set_text(text)

    def _on_accent_changed(self, hexcode: str):
        self.config.accent = hexcode
        self.apply_theme()
        self.toast("Arayüz rengi güncellendi.", 2500)

    def _check_reminders(self):
        now = datetime.now()
        changed = False
        for item in self.config.reminders:
            if item.get("fired"):
                continue
            try:
                due = datetime.fromisoformat(item.get("when", ""))
            except Exception:
                continue
            if due <= now:
                item["fired"] = True
                changed = True
                text = item.get("text", "")
                self.toast(f"⏰ Hatırlatıcı: {text}", 8000)
                self._append_block("system", f"Hatırlatıcı: {text}")
                QApplication.beep()
                self._speak_short(f"Hatırlatıcı: {text}")
        if changed:
            self.config.save()
            self.reminders.reload()

    # -------------------------------------------------------------------- onay
    def _ask_confirm(self, title: str, detail: str):
        ok = self.confirm_box(title, detail)
        self.confirm_bridge.resolve(ok)

    # -------------------------------------------------------------------- ayarlar
    def open_settings(self):
        dialog = SettingsDialog(self.config, self)
        dialog.changed.connect(self._settings_changed)
        dialog.exec()

    def _settings_changed(self):
        was_awake = self.awake
        self.setWindowTitle(f"{self.config.ai_name} · Kişisel Yapay Zekâ Asistanı")
        self.brain = GeminiBrain(self.config, self.tools)
        self.live.brain = self.brain
        self.live.config = self.config
        self.apply_theme()
        self._set_state(
            "sleeping" if not was_awake else ("connecting" if self.config.mode == "s2s" else "idle")
        )
        if was_awake and self.config.mode == "s2s":
            self.live.stop()
            QTimer.singleShot(700, self._ensure_live)
        self._refresh_routing()
        self.toast("Ayarlar kaydedildi.", 2500)

    # -------------------------------------------------------------------- kapanis
    def closeEvent(self, event):  # noqa: N802
        try:
            self.config.notes = self.notes.editor.toPlainText()
            self.config.save()
        except Exception:
            pass
        self.live.stop()
        self.listener.stop()
        self.camera.stop()
        self.speaker.stop()
        super().closeEvent(event)
