#!/usr/bin/env python3
"""Nexus AI · Gemini tabanlı, sesli konuşan ve PC'yi yöneten masaüstü asistan."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication, QDialog
    except ImportError as exc:
        print("Eksik paket:", exc)
        print("Kurulum için:  python setup.py")
        return 1

    from app.config import APP_TITLE, Config
    from app.ui.main_window import MainWindow
    from app.ui.onboarding import OnboardingDialog

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)
    app.setFont(QFont("Segoe UI", 10))

    config = Config.load()
    if not config.ready:
        wizard = OnboardingDialog(config)
        if wizard.exec() != QDialog.Accepted:
            return 0

    window = MainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
