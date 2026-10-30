"""Reaktör çekirdeği: uyku/uyanık/dinleme/düşünme/konuşma durumlarını çizer."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QFont,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

STATES = {
    "sleeping": ("UYKUDA", "#8d97a5"),
    "idle": ("HAZIR", "#7b8794"),
    "listening": ("DİNLİYOR", "#2f6bff"),
    "thinking": ("DÜŞÜNÜYOR", "#2f6bff"),
    "speaking": ("KONUŞUYOR", "#2f6bff"),
    "connecting": ("BAĞLANIYOR", "#2f6bff"),
}


class ReactorCore(QWidget):
    clicked = Signal()

    def __init__(self, accent: str = "#2f6bff", parent=None):
        super().__init__(parent)
        self.accent = accent
        self.state_name = "sleeping"
        self.level = 0.0
        self._phase = 0.0
        self._pulse = 0.0
        self.setMinimumSize(250, 250)
        self.setMaximumSize(380, 380)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Uyandırmak / uyutmak için tıkla")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def sizeHint(self):  # noqa: N802
        return QSize(330, 330)

    # ------------------------------------------------------------------ ayarlar
    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self.update()

    def set_state(self, state_name: str) -> None:
        self.state_name = state_name if state_name in STATES else "idle"
        self.update()

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(1.0, float(level) * 5.0))

    # --------------------------------------------------------------------- tick
    def _tick(self) -> None:
        speed = {
            "listening": 0.06,
            "speaking": 0.05,
            "thinking": 0.09,
            "connecting": 0.07,
        }.get(self.state_name, 0.018)
        self._phase = (self._phase + speed) % (math.pi * 2)
        self._pulse += 0.09
        self.level *= 0.92
        self.update()

    # -------------------------------------------------------------------- cizim
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        radius = min(w, h) / 2 - 12
        if radius <= 10:
            return

        label, default_color = STATES[self.state_name]
        base = QColor(default_color)
        if self.state_name != "sleeping":
            base = QColor(self.accent)
        if self.state_name == "sleeping":
            base.setAlpha(150)

        sleeping = self.state_name == "sleeping"
        active = self.state_name in {"listening", "speaking", "thinking", "connecting"}
        energy = 0.35 + self.level + (0.25 if self.state_name == "speaking" else 0.0)
        energy = min(1.4, energy)
        breathe = 0.5 + 0.5 * math.sin(self._pulse)

        # dis isima
        glow = QRadialGradient(QPointF(cx, cy), radius * (1.05 + 0.08 * breathe))
        glow_color = QColor(base)
        glow_color.setAlpha(int(18 + 42 * energy + 14 * breathe) if not sleeping else 16)
        glow.setColorAt(0.0, glow_color)
        glow.setColorAt(0.55, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 22))
        glow.setColorAt(1.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), radius * 1.18, radius * 1.18)

        # kadran cizgileri
        ticks = 72
        for i in range(ticks):
            angle = (i / ticks) * math.tau - math.pi / 2
            major = i % 6 == 0
            length = (11 if major else 6) * (1.0 + 0.12 * breathe)
            if active and major:
                length += 8 * energy
            inner = radius * 0.86
            outer = inner + length
            color = QColor(base)
            color.setAlpha(150 if major and not sleeping else 60)
            pen = QPen(color)
            pen.setWidthF(2.0 if major else 1.0)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(cx + inner * math.cos(angle), cy + inner * math.sin(angle)),
                QPointF(cx + outer * math.cos(angle), cy + outer * math.sin(angle)),
            )

        # donen halkalar
        if active:
            for idx, (span, speed, rad_f, width) in enumerate(
                [(70, 1.0, 0.72, 5.0), (110, -0.7, 0.80, 2.5), (46, 1.6, 0.64, 3.0)]
            ):
                color = QColor(base)
                color.setAlpha(200 - idx * 50)
                pen = QPen(color)
                pen.setWidthF(width)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                rect = QRectF(
                    cx - radius * rad_f,
                    cy - radius * rad_f,
                    radius * rad_f * 2,
                    radius * rad_f * 2,
                )
                start = math.degrees(self._phase * speed * (1.4 if idx == 1 else 1.0)) - idx * 40
                painter.drawArc(rect, int(start * 16), int(span * 16))

        # ice dogru hale
        halo = QRadialGradient(QPointF(cx, cy - radius * 0.08), radius * 0.95)
        inner_color = QColor(base).lighter(135)
        inner_color.setAlpha(70 if not sleeping else 26)
        halo.setColorAt(0.0, inner_color)
        halo.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(cx, cy), radius * 0.92, radius * 0.92)

        # cekirdek kure
        core_r = radius * (0.52 + 0.03 * breathe + 0.02 * self.level)
        sphere = QRadialGradient(
            QPointF(cx - core_r * 0.32, cy - core_r * 0.38), core_r * 1.55
        )
        if sleeping:
            sphere.setColorAt(0.0, QColor("#dfe4ea"))
            sphere.setColorAt(0.55, QColor("#b9c1cb"))
            sphere.setColorAt(1.0, QColor("#8f99a6"))
        else:
            sphere.setColorAt(0.0, QColor(base).lighter(185))
            sphere.setColorAt(0.45, QColor(base).lighter(115))
            sphere.setColorAt(0.85, QColor(base).darker(115))
            sphere.setColorAt(1.0, QColor(base).darker(165))
        painter.setBrush(sphere)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # konik parlama
        if not sleeping:
            cone = QConicalGradient(QPointF(cx, cy), math.degrees(self._phase * 1.5))
            shine = QColor(255, 255, 255, 90)
            cone.setColorAt(0.0, shine)
            cone.setColorAt(0.18, QColor(255, 255, 255, 0))
            cone.setColorAt(0.55, QColor(255, 255, 255, 60))
            cone.setColorAt(0.75, QColor(255, 255, 255, 0))
            painter.setBrush(cone)
            painter.drawEllipse(QPointF(cx, cy), core_r * 0.96, core_r * 0.96)

        # ic halka
        pen = QPen(QColor(255, 255, 255, 110 if not sleeping else 70))
        pen.setWidthF(1.6)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), core_r * 0.80, core_r * 0.80)

        # goz bebegi / guc simgesi
        if sleeping:
            pen = QPen(QColor(255, 255, 255, 200))
            pen.setWidthF(3.2)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(
                QRectF(cx - core_r * 0.30, cy - core_r * 0.30, core_r * 0.60, core_r * 0.60),
                int(120 * 16),
                int(300 * 16),
            )
            painter.drawLine(
                QPointF(cx, cy - core_r * 0.46), QPointF(cx, cy - core_r * 0.06)
            )
        else:
            dot_r = core_r * (0.10 + 0.05 * self.level)
            painter.setBrush(QColor(255, 255, 255, 220))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx, cy), dot_r, dot_r)

        # durum yazisi
        font = QFont(self.font())
        font.setPointSizeF(8.5)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2.2)
        font.setBold(True)
        painter.setFont(font)
        text_color = QColor(base)
        text_color.setAlpha(230)
        painter.setPen(text_color)
        rect = QRectF(cx - radius, cy + radius * 0.79, radius * 2, 22)
        painter.drawText(rect, Qt.AlignHCenter | Qt.AlignVCenter, label)

    # ------------------------------------------------------------------ etkilesim
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
