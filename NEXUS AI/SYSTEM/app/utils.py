"""Kucuk yardimcilar: arka plan gorevleri, tarih/saat ve metin normalizasyonu."""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from datetime import datetime

from PySide6.QtCore import QObject, Signal

TR_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]
TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


class Task(QObject):
    """Bloklayan bir islemi arka planda calistirip sonucu sinyal ile bildirir."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def start(self) -> "Task":
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def _run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 - UI'a tasinir
            self.failed.emit(str(exc))
        else:
            self.done.emit(result)


def turkish_date(dt: datetime | None = None) -> str:
    dt = dt or datetime.now()
    return f"{dt.day} {TR_MONTHS[dt.month - 1]} {dt.year} {TR_DAYS[dt.weekday()]}"


def turkish_short_date(dt: datetime | None = None) -> str:
    dt = dt or datetime.now()
    return f"{dt.day} {TR_MONTHS[dt.month - 1]} {dt.year}"


def humanize_minutes(minutes: float) -> str:
    minutes = int(round(minutes))
    if minutes <= 0:
        return "şimdi"
    if minutes < 60:
        return f"{minutes} dakika sonra"
    hours, mins = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} saat" + (f" {mins} dakika" if mins else "") + " sonra"
    return f"{hours // 24} gün sonra"


def norm(text: str) -> str:
    """Turkce karakterleri sadelestirip karsilastirma icin normalize eder."""
    text = text.lower().replace("ı", "i")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def name_spoken(transcript: str, name: str) -> bool:
    """Transkriptte AI'nin adi geciyor mu? (kucuk yazim hatalarina toleransli)"""
    import difflib

    target = norm(name)
    if not target or not transcript:
        return False
    words = norm(transcript).split()
    if target in norm(transcript):
        return True
    for word in words:
        if len(word) < 3:
            continue
        if difflib.SequenceMatcher(None, word, target).ratio() >= 0.78:
            return True
        if target in word or word in target:
            return True
    return False


def jsonable(obj):
    """Araç sonuclarini JSON'a cevrilebilir hale getirir."""
    try:
        json.dumps(obj)
        return obj
    except Exception:  # noqa: BLE001
        return str(obj)
