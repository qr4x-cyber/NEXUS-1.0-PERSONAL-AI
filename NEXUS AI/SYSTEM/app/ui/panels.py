"""Arayuz panelleri: hava durumu, hatirlaticilar, notlar, harita, haberler, saat."""

from __future__ import annotations

import os
import webbrowser
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import services
from ..config import Config
from ..theme import CARD_BG, MUTED
from ..utils import Task, turkish_date, turkish_short_date


# ------------------------------------------------------------------------ temel
class Card(QFrame):
    def __init__(self, title: str = "", icon: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(16, 12, 16, 14)
        self.outer.setSpacing(10)
        self.header = QHBoxLayout()
        self.header.setSpacing(6)
        self.header.setContentsMargins(0, 0, 0, 0)
        if title:
            if icon:
                icon_label = QLabel(icon)
                icon_label.setStyleSheet("font-size:12px;")
                self.header.addWidget(icon_label)
            label = QLabel(title.upper())
            label.setObjectName("CardTitle")
            self.header.addWidget(label)
            self.header.addStretch(1)
            self.outer.addLayout(self.header)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.outer.addLayout(self.body, 1)


class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ----------------------------------------------------------------------- hava
class WeatherPanel(Card):
    def __init__(self, config: Config, parent=None):
        super().__init__("Hava Durumu", "🌤", parent)
        self.config = config
        self._busy = False

        self.temp_label = QLabel("—")
        self.temp_label.setObjectName("WeatherTemp")
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.temp_label)
        self.icon_label = QLabel("🌡")
        self.icon_label.setStyleSheet("font-size:26px;")
        row.addWidget(self.icon_label, 0, Qt.AlignVCenter)
        row.addStretch(1)
        self.body.addLayout(row)

        self.city_label = QLabel("Konum alınıyor…")
        self.city_label.setObjectName("Muted")
        self.body.addWidget(self.city_label)

        self.detail_label = QLabel("")
        self.detail_label.setObjectName("Tiny")
        self.body.addWidget(self.detail_label)

        self._task = None
        self.refresh()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(15 * 60 * 1000)

    def refresh(self):
        if self._busy:
            return
        self._busy = True
        self._task = Task(self._fetch)
        self._task.done.connect(self.apply)
        self._task.failed.connect(self.fail)
        self._task.start()

    def _fetch(self):
        loc = self.config.location
        if not loc or not loc.get("lat"):
            loc = services.fetch_location()
            if loc:
                self.config.location = loc
                self.config.save()
        if not loc:
            raise RuntimeError("Konum alınamadı")
        data = services.fetch_weather(float(loc["lat"]), float(loc["lon"]))
        data["city"] = loc.get("city") or loc.get("region") or ""
        return data

    def apply(self, data: dict):
        self._busy = False
        self.temp_label.setText(f"{data['temp']}°")
        self.icon_label.setText(data["icon"])
        city = data.get("city") or ""
        self.city_label.setText(f"{city} · {data['label']}" if city else data["label"])
        self.detail_label.setText(
            f"Hissedilen {data['feels']}°   ·   Nem %{data['humidity']}   ·   "
            f"Rüzgâr {data['wind']} km/s\nEn yüksek {data['tmax']}° / En düşük {data['tmin']}°"
        )

    def fail(self, message: str):
        self._busy = False
        if self.city_label.text() == "Konum alınıyor…":
            self.city_label.setText("Hava durumu alınamadı")
        self.setToolTip(message)


# --------------------------------------------------------------- hatirlaticilar
class ReminderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yeni hatırlatıcı")
        self.setFixedWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("HATIRLATICI")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Ne hatırlatayım?")
        layout.addWidget(self.text_edit)

        row = QHBoxLayout()
        row.addWidget(QLabel("Kaç dakika sonra?"))
        self.minutes = QSpinBox()
        self.minutes.setRange(0, 10080)
        self.minutes.setValue(15)
        self.minutes.setSuffix(" dk")
        row.addWidget(self.minutes)
        row.addStretch(1)
        layout.addLayout(row)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        for value in (5, 15, 30, 60, 180):
            btn = QPushButton(f"{value} dk")
            btn.setObjectName("GhostButton")
            btn.clicked.connect(lambda _, v=value: self.minutes.setValue(v))
            chips.addWidget(btn)
        chips.addStretch(1)
        layout.addLayout(chips)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Vazgeç")
        cancel.setObjectName("GhostButton")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        save = QPushButton("Ekle")
        save.setObjectName("AccentButton")
        save.clicked.connect(self._accept)
        actions.addWidget(save)
        layout.addLayout(actions)
        self.text_edit.returnPressed.connect(self._accept)

    def _accept(self):
        if not self.text_edit.text().strip():
            self.text_edit.setFocus()
            return
        self.accept()

    def values(self) -> tuple[str, int]:
        return self.text_edit.text().strip(), self.minutes.value()


class RemindersPanel(Card):
    def __init__(self, config: Config, on_add=None, parent=None):
        super().__init__("Hatırlatıcılar", "⏰", parent)
        self.config = config
        self.on_add = on_add

        add_btn = QPushButton("+")
        add_btn.setObjectName("MiniButton")
        add_btn.setToolTip("Yeni hatırlatıcı")
        add_btn.setFixedWidth(24)
        add_btn.clicked.connect(self.add_dialog)
        self.header.addWidget(add_btn)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.container)
        self.body.addWidget(self.scroll, 1)
        self.empty = QLabel("Henüz hatırlatıcı yok.\n+ ile ekleyebilirsin.")
        self.empty.setObjectName("Muted")
        self.empty.setWordWrap(True)
        self.body.addWidget(self.empty)
        self.reload()

    def add_dialog(self):
        dialog = ReminderDialog(self)
        if dialog.exec() == QDialog.Accepted:
            text, minutes = dialog.values()
            self.add(text, minutes)

    def add(self, text: str, minutes: int):
        from datetime import timedelta

        when = datetime.now() + timedelta(minutes=minutes)
        item = self.config.add_reminder(text, when.isoformat(timespec="seconds"))
        if self.on_add:
            self.on_add(item)
        self.reload()

    def reload(self):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        pending = [r for r in self.config.reminders if not r.get("fired")]
        pending.sort(key=lambda r: r.get("when", ""))
        self.empty.setVisible(not pending)
        for rem in pending[:12]:
            row = QFrame()
            row.setStyleSheet("background: #ffffff; border: 1px solid #e3e7ec; border-radius: 10px;")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(10, 6, 6, 6)
            layout.setSpacing(8)
            when = rem.get("when", "")
            try:
                label = datetime.fromisoformat(when).strftime("%H:%M")
            except Exception:
                label = "--:--"
            time_label = QLabel(label)
            time_label.setStyleSheet("border:none; font-weight:700; font-size:11px; color:#2f6bff;")
            time_label.setFixedWidth(38)
            layout.addWidget(time_label)
            text = QLabel(rem.get("text", ""))
            text.setWordWrap(True)
            text.setStyleSheet("border:none; font-size:12px;")
            layout.addWidget(text, 1)
            delete = QPushButton("×")
            delete.setObjectName("MiniButton")
            delete.setFixedWidth(18)
            delete.setToolTip("Sil")
            delete.clicked.connect(lambda _, rid=rem.get("id"): self._delete(rid))
            layout.addWidget(delete)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)

    def _delete(self, rid: str):
        self.config.remove_reminder(rid)
        self.reload()


# ----------------------------------------------------------------------- notlar
class NotesPanel(Card):
    def __init__(self, config: Config, on_save=None, parent=None):
        super().__init__("Notlar", "📝", parent)
        self.config = config
        self.on_save = on_save
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("NotesEdit")
        self.editor.setPlaceholderText("Aklına geleni yaz…")
        self.editor.setPlainText(config.notes or "")
        self.body.addWidget(self.editor, 1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self._save)
        self.editor.textChanged.connect(self._timer.start)

    def _save(self):
        self.config.notes = self.editor.toPlainText()
        self.config.save()
        if self.on_save:
            self.on_save(self.config.notes)

    def set_text(self, text: str):
        if text != self.editor.toPlainText():
            self.editor.blockSignals(True)
            self.editor.setPlainText(text)
            self.editor.blockSignals(False)


# ---------------------------------------------------------------------- harita
class MapView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image: QImage | None = None
        self.city = ""
        self.url = ""
        self.empty_text = "Harita yükleniyor…"
        self.setMinimumHeight(160)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Haritayı tarayıcıda aç")

    def set_map(self, data: dict):
        count = data.get("count", 3)
        size = count * 256
        canvas = QImage(size, size, QImage.Format_RGB32)
        canvas.fill(QColor("#dfe5ec"))
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        for dx, dy, raw in data.get("tiles", []):
            tile = QImage.fromData(raw)
            if not tile.isNull():
                painter.drawImage(dx * 256, dy * 256, tile)
        painter.end()
        self.image = canvas
        self.city = data.get("city", "")
        self.url = data.get("map_url", "")
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        painter.setClipPath(path)

        if self.image is None or self.image.isNull():
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0, QColor("#e6ebf2"))
            gradient.setColorAt(1, QColor("#d3dbe6"))
            painter.fillRect(rect, gradient)
            pen = QPen(QColor(255, 255, 255, 140))
            pen.setWidth(1)
            painter.setPen(pen)
            step = 26
            for x in range(0, int(rect.width()), step):
                painter.drawLine(x, 0, x, int(rect.height()))
            for y in range(0, int(rect.height()), step):
                painter.drawLine(0, y, int(rect.width()), y)
            painter.setPen(QColor("#7b8794"))
            font = QFont(self.font())
            font.setPointSizeF(9)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, self.empty_text)
        else:
            iw, ih = self.image.width(), self.image.height()
            scale = max(rect.width() / iw, rect.height() / ih)
            tw, th = iw * scale, ih * scale
            target = QRectF(
                rect.center().x() - tw / 2, rect.center().y() - th / 2, tw, th
            )
            painter.drawImage(target, self.image)

            # isaretci
            center = rect.center()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 45))
            painter.drawEllipse(QPointF(center.x(), center.y() + 3), 9, 4)
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(center, 9, 9)
            painter.setBrush(QColor("#e8453c"))
            painter.drawEllipse(center, 6, 6)
            painter.setBrush(QColor(255, 255, 255, 220))
            painter.drawEllipse(QPointF(center.x() - 1.6, center.y() - 1.8), 1.8, 1.8)

        # sehir etiketi
        if self.city:
            font = QFont(self.font())
            font.setPointSizeF(9)
            font.setBold(True)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            width = metrics.horizontalAdvance(self.city) + 20
            pill = QRectF(10, 10, width, 24)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 225))
            painter.drawRoundedRect(pill, 12, 12)
            painter.setPen(QColor("#2b313a"))
            painter.drawText(pill, Qt.AlignCenter, self.city)

        painter.setClipping(False)
        if self.image is not None:
            painter.setPen(QColor(255, 255, 255, 200))
            font = QFont(self.font())
            font.setPointSizeF(6.5)
            painter.setFont(font)
            painter.drawText(
                rect.adjusted(0, 0, -8, -4), Qt.AlignRight | Qt.AlignBottom, "© OpenStreetMap"
            )
        painter.end()

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if self.url:
            webbrowser.open(self.url)


class MapPanel(Card):
    def __init__(self, config: Config, parent=None):
        super().__init__("Harita", "🗺", parent)
        self.config = config
        self.city_label = QLabel("")
        self.city_label.setObjectName("Tiny")
        self.header.addWidget(self.city_label)

        self.view = MapView()
        self.body.addWidget(self.view, 1)
        self._busy = False
        self._task = None
        self.refresh()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(20 * 60 * 1000)

    def refresh(self):
        if self._busy:
            return
        self._busy = True
        self._task = Task(self._fetch)
        self._task.done.connect(self.apply)
        self._task.failed.connect(self.fail)
        self._task.start()

    def _fetch(self):
        loc = self.config.location
        if not loc or not loc.get("lat"):
            loc = services.fetch_location()
            if loc:
                self.config.location = loc
                self.config.save()
        if not loc:
            raise RuntimeError("Konum alınamadı")
        data = services.fetch_map(float(loc["lat"]), float(loc["lon"]), zoom=12, radius=1)
        data["city"] = loc.get("city") or loc.get("region") or ""
        return data

    def apply(self, data: dict):
        self._busy = False
        self.view.set_map(data)
        self.city_label.setText(data.get("city", ""))

    def fail(self, message: str):
        self._busy = False
        self.setToolTip(message)
        if self.view.image is None:
            self.view.empty_text = "Harita yüklenemedi"
            self.view.update()


# ---------------------------------------------------------------------- haber
class NewsPanel(Card):
    def __init__(self, config: Config, parent=None):
        super().__init__("Güncel Haberler", "📰", parent)
        self.config = config
        self.items: list[dict] = []
        self.page = 0
        self._busy = False
        self.rows: list[QLabel] = []
        for _ in range(4):
            label = QLabel("")
            label.setWordWrap(True)
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            label.setStyleSheet("font-size:12px;")
            self.body.addWidget(label)
            self.rows.append(label)
        self.body.addStretch(1)
        self.status = QLabel("Haberler yükleniyor…")
        self.status.setObjectName("Tiny")
        self.body.addWidget(self.status)

        self._task = None
        self.refresh()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(10 * 60 * 1000)
        self._rotate = QTimer(self)
        self._rotate.timeout.connect(self._next_page)
        self._rotate.start(12 * 1000)

    def refresh(self):
        if self._busy:
            return
        self._busy = True
        self._task = Task(services.fetch_news, self.config.feeds, 28)
        self._task.done.connect(self.apply)
        self._task.failed.connect(self.fail)
        self._task.start()

    def apply(self, items: list[dict]):
        self._busy = False
        if items:
            self.items = items
            self.page = 0
            self._render()
            self.status.setText(f"{len(items)} başlık · {datetime.now():%H:%M} güncellendi")
        elif not self.items:
            self.status.setText("Haberler alınamadı")

    def fail(self, message: str):
        self._busy = False
        if not self.items:
            self.status.setText("Haberler alınamadı")

    def _next_page(self):
        if not self.items:
            return
        self.page = (self.page + 4) % len(self.items)
        self._render()

    def _render(self):
        accent = self.config.accent
        for index, label in enumerate(self.rows):
            position = self.page + index
            if position >= len(self.items):
                label.setText("")
                continue
            item = self.items[position]
            title = item.get("title", "").replace("<", "&lt;")
            source = item.get("source", "")
            url = item.get("link", "")
            label.setText(
                f'<div style="margin-bottom:2px;">'
                f'<a href="{url}" style="color:#1e232b; text-decoration:none;">{title}</a>'
                f'</div><div style="color:{MUTED}; font-size:10px; margin-bottom:7px;">{source}</div>'
            )
            label.setToolTip(title)


# ----------------------------------------------------------------------- saat
class ClockPanel(Card):
    def __init__(self, parent=None):
        super().__init__("", "", parent)
        self.outer.setContentsMargins(18, 14, 18, 16)
        self.time_label = QLabel("00:00:00")
        self.time_label.setObjectName("Clock")
        self.time_label.setAlignment(Qt.AlignRight)
        self.body.addWidget(self.time_label)

        self.date_label = QLabel("")
        self.date_label.setObjectName("Muted")
        self.date_label.setAlignment(Qt.AlignRight)
        self.body.addWidget(self.date_label)

        self.zone_label = QLabel("")
        self.zone_label.setObjectName("Tiny")
        self.zone_label.setAlignment(Qt.AlignRight)
        self.body.addWidget(self.zone_label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)
        self._tick()

    def _tick(self):
        now = datetime.now()
        self.time_label.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(turkish_date(now))
        self.zone_label.setText(f"{turkish_short_date(now)} · yerel saat")


# --------------------------------------------------------------------- kamera
class CameraPreview(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(240, 150)
        self.setStyleSheet(
            "background: #20242b; border-radius: 14px; border: 1px solid #2f353e;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.view = QLabel("Kamera bekleniyor…")
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setStyleSheet(
            "background: transparent; color: #9aa4b2; font-size: 11px; border: none;"
        )
        layout.addWidget(self.view)
        self._last_ratio = None

    def set_frame(self, image: QImage):
        pixmap = QPixmap.fromImage(image)
        self.view.setPixmap(
            pixmap.scaled(self.view.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        )

    def set_message(self, text: str):
        self.view.setPixmap(QPixmap())
        self.view.setText(text)
