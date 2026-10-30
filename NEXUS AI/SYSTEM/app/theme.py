"""Acik gri arayuz temasi ve vurgu rengi yardimcilari."""

from __future__ import annotations

from PySide6.QtGui import QColor

BASE_BG = "#e8eaee"
CARD_BG = "#f7f8fa"
BORDER = "#dde1e7"
TEXT = "#1e232b"
MUTED = "#77808d"


def lighten(hex_color: str, ratio: float) -> str:
    color = QColor(hex_color)
    h, s, light, a = color.getHslF()
    light = min(1.0, light + (1.0 - light) * ratio)
    return QColor.fromHslF(h, s, light, a).name()


def darken(hex_color: str, ratio: float) -> str:
    color = QColor(hex_color)
    h, s, light, a = color.getHslF()
    light = max(0.0, light * (1.0 - ratio))
    return QColor.fromHslF(h, s, light, a).name()


def alpha(hex_color: str, value: int) -> str:
    color = QColor(hex_color)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {value})"


def build_stylesheet(accent: str) -> str:
    soft = lighten(accent, 0.82)
    return f"""
    QWidget {{
        font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif;
        color: {TEXT};
        font-size: 13px;
    }}
    QWidget#Root {{ background: {BASE_BG}; }}

    QFrame#Card {{
        background: {CARD_BG};
        border: 1px solid {BORDER};
        border-radius: 16px;
    }}
    QFrame#FlatCard {{
        background: transparent;
        border: none;
    }}
    QLabel#CardTitle {{
        color: {MUTED};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.4px;
    }}
    QLabel#Muted {{ color: {MUTED}; font-size: 11px; }}
    QLabel#Tiny {{ color: {MUTED}; font-size: 10px; }}
    QLabel#WeatherTemp {{ font-size: 30px; font-weight: 600; }}
    QLabel#Clock {{ font-size: 34px; font-weight: 600; letter-spacing: 1px; }}

    QToolButton#IconButton {{
        background: #ffffff;
        border: 1px solid {BORDER};
        border-radius: 19px;
        padding: 7px 11px;
        font-size: 15px;
    }}
    QToolButton#IconButton:hover {{ background: #f1f3f6; }}
    QToolButton#IconButton:checked {{
        background: {soft};
        border: 1px solid {accent};
    }}
    QToolButton#ModeButton {{
        background: #ffffff;
        border: 1px solid {BORDER};
        border-radius: 19px;
        padding: 7px 22px;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    QToolButton#ModeButton:hover {{ background: #f1f3f6; }}
    QToolButton#ModeButton:checked {{
        background: {accent};
        border: 1px solid {accent};
        color: #ffffff;
    }}

    QPushButton#AccentButton {{
        background: {accent};
        color: #ffffff;
        border: none;
        border-radius: 10px;
        padding: 9px 18px;
        font-weight: 600;
    }}
    QPushButton#AccentButton:hover {{ background: {darken(accent, 0.12)}; }}
    QPushButton#GhostButton {{
        background: #ffffff;
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 8px 16px;
        font-weight: 600;
    }}
    QPushButton#GhostButton:hover {{ background: #f1f3f6; }}
    QPushButton#LinkButton {{
        background: transparent;
        border: none;
        color: {accent};
        text-align: left;
        padding: 2px;
        font-size: 12px;
    }}
    QPushButton#LinkButton:hover {{ text-decoration: underline; }}
    QPushButton#MiniButton {{
        background: transparent;
        border: none;
        color: {MUTED};
        font-size: 14px;
        padding: 0px 4px;
    }}
    QPushButton#MiniButton:hover {{ color: {accent}; }}

    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QTimeEdit {{
        background: #ffffff;
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 8px 12px;
        selection-background-color: {lighten(accent, 0.6)};
        selection-color: {TEXT};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{
        border: 1px solid {accent};
    }}
    QLineEdit#ChatInput {{
        border-radius: 21px;
        padding: 11px 18px;
        font-size: 13px;
    }}
    QTextEdit#Transcript {{
        background: transparent;
        border: none;
        padding: 0px;
    }}
    QPlainTextEdit#NotesEdit {{
        background: #ffffff;
        border: 1px solid {BORDER};
        border-radius: 12px;
        font-size: 12px;
    }}

    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border-radius: 5px;
        border: 1px solid {BORDER};
        background: #ffffff;
    }}
    QCheckBox::indicator:checked {{
        background: {accent};
        border: 1px solid {accent};
    }}

    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{
        background: transparent; width: 8px; margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {alpha(TEXT, 45)}; border-radius: 4px; min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

    QDialog {{ background: {BASE_BG}; }}
    QToolTip {{
        background: #2b313a; color: #ffffff; border: none;
        padding: 6px 10px; border-radius: 8px;
    }}
    """
