#!/usr/bin/env python3
"""Nexus AI kurulum betigi.

Kullanim:
    python setup.py          # bagimliliklari kurar
    python setup.py --run    # kurar ve uygulamayi baslatir
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIN_PYTHON = (3, 10)

try:  # Windows konsolunda Turkce karakterler icin
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def line(text: str = "") -> None:
    print(text)


def main() -> int:
    line("=" * 58)
    line("  NEXUS · Gemini tabanli masaustu asistani kurulumu")
    line("=" * 58)
    line()

    if sys.version_info < MIN_PYTHON:
        line(f"HATA: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} veya uzeri gerekli.")
        line(f"Su an: {sys.version.split()[0]}  ({sys.executable})")
        return 1

    requirements = HERE / "requirements.txt"
    if not requirements.exists():
        line("HATA: requirements.txt bulunamadi. Kurulum dosyasiyla ayni klasorde olmali.")
        return 1

    line(f"Python {sys.version.split()[0]} bulundu: {sys.executable}")
    line("Bagimliliklar kuruluyor (birkac dakika surebilir)…")
    line()

    commands = [
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        [sys.executable, "-m", "pip", "install", "-r", str(requirements)],
    ]
    for command in commands:
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as exc:
            line()
            line(f"HATA: Kurulum basarisiz (kod {exc.returncode}).")
            line("Ipucu: 'python -m pip install --upgrade pip' deneyin ve tekrar calistirin.")
            return exc.returncode or 1

    line()
    line("Kurulum tamamlandi.")
    line()
    line("Sonraki adim:  python main.py")
    line("Ilk acilista API anahtari, adin, asistanin adi ve tema rengi sorulacak.")
    line()

    if "--run" in sys.argv:
        return subprocess.call([sys.executable, str(HERE / "main.py")])

    try:
        answer = input("Uygulama simdi baslatilsin mi? [E/h]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "h"
    if answer in {"", "e", "evet", "y", "yes"}:
        return subprocess.call([sys.executable, str(HERE / "main.py")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
