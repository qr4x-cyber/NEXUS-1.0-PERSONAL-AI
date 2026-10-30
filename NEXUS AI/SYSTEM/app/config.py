"""Kalici ayarlar: API anahtari, kullanici profili, AI kimligi, tema ve notlar."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_TITLE = "NEXUS"

DEFAULT_FEEDS = [
    ("Google Haberler", "https://news.google.com/rss?hl=tr&gl=TR&ceid=TR:tr"),
    ("BBC Türkçe", "https://feeds.bbci.co.uk/turkce/rss.xml"),
    ("NTV", "https://www.ntv.com.tr/son-dakika.rss"),
    ("Hürriyet", "https://www.hurriyet.com.tr/rss/anasayfa"),
]

# Model adlari zamanla degisiyor: ilk calisan model otomatik secilir ve config'e yazilir.
TEXT_MODELS = [
    "gemini-3.5-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]
LIVE_MODELS = [
    "gemini-3.8-live",
    "gemini-3.5-flash-live",
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-2.0-flash-live-001",
    "gemini-live-2.5-flash-preview",
]
TTS_MODELS = [
    "gemini-3.8-flash-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
]

VOICES = [
    "Kore",
    "Zephyr",
    "Puck",
    "Charon",
    "Aoede",
    "Leda",
    "Fenrir",
    "Orus",
    "Sulafat",
    "Achird",
]

ACCENTS = {
    "Mavi": "#2f6bff",
    "Turkuaz": "#00a8a8",
    "Mor": "#7b4dff",
    "Gül": "#e0407a",
    "Turuncu": "#f0711a",
    "Yeşil": "#18a558",
}


def config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "NexusAI"
    return Path.home() / ".config" / "nexus-ai"


CONFIG_PATH = config_dir() / "config.json"


@dataclass
class Config:
    api_key: str = ""
    user_name: str = ""
    user_about: str = ""
    ai_name: str = "Nexus"
    accent: str = "#2f6bff"
    voice: str = "Kore"
    mode: str = "s2s"  # "s2s" (sesli sesli) | "tts" (yazi + ses)
    mic_enabled: bool = True
    camera_enabled: bool = False
    confirm_dangerous: bool = True
    wake_word_enabled: bool = True
    onboarding_done: bool = False
    text_model: str = ""
    live_model: str = ""
    tts_model: str = ""
    notes: str = ""
    reminders: list = field(default_factory=list)
    memories: list = field(default_factory=list)
    feeds: list = field(default_factory=lambda: [list(f) for f in DEFAULT_FEEDS])
    location: dict = field(default_factory=dict)

    # ---------------------------------------------------------------- kalicilik
    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return cfg
        for key, value in raw.items():
            if hasattr(cfg, key) and value is not None:
                setattr(cfg, key, value)
        return cfg

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["api_key"] = self.api_key.strip()
        CONFIG_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------ yardimci
    @property
    def ready(self) -> bool:
        return bool(self.api_key.strip()) and self.onboarding_done

    def add_reminder(self, text: str, when_iso: str) -> dict:
        item = {"id": os.urandom(4).hex(), "text": text, "when": when_iso, "fired": False}
        self.reminders.append(item)
        self.save()
        return item

    def remove_reminder(self, rid: str) -> None:
        self.reminders = [r for r in self.reminders if r.get("id") != rid]
        self.save()

    def remember(self, fact: str) -> None:
        fact = fact.strip()
        if fact and fact not in self.memories:
            self.memories.append(fact)
            self.memories = self.memories[-40:]
            self.save()
