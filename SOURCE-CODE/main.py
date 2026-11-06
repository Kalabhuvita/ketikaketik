#!/usr/bin/env python3
"""Ketikaketik — editor markdown untuk menulis novel.

Jalankan:  /usr/bin/python3 main.py [folder-proyek]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QSettings              # noqa: E402
from PySide6.QtGui import QIcon                   # noqa: E402
from PySide6.QtWidgets import QApplication        # noqa: E402

from app.theme import apply_theme                  # noqa: E402
from app.window import ICON_FILE, MainWindow       # noqa: E402


def _configure_storage() -> None:
    """Setelan bisa ditaruh di folder bersama supaya tema, proyek terakhir, dan
    daftar bab tersembunyi ikut pindah antar distro (dual boot).

    Diaktifkan lewat env KETIKAKETIK_CONFIG, atau cukup dengan membuat file
    kosong `settings.ini` di samping main.py.
    """
    override = os.environ.get("KETIKAKETIK_CONFIG")
    marker = Path(__file__).resolve().parent / "settings.ini"
    if override:
        target = Path(override).expanduser()
    elif marker.exists():
        target = Path(__file__).resolve().parent / ".config"
    else:
        return
    target.mkdir(parents=True, exist_ok=True)
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(target))
    QSettings.setPath(QSettings.IniFormat, QSettings.SystemScope, str(target))


def main() -> int:
    argv = sys.argv[1:]
    _configure_storage()
    app = QApplication([sys.argv[0]])
    app.setApplicationName("ketikaketik")
    app.setOrganizationName("ketikaketik")
    app.setApplicationDisplayName("Ketikaketik")
    app.setDesktopFileName("ketikaketik")
    if ICON_FILE.exists():
        app.setWindowIcon(QIcon(str(ICON_FILE)))

    settings = QSettings()
    theme = settings.value("ui/theme", "day")
    apply_theme(app, theme)

    window = MainWindow()
    window.show()

    if argv and Path(argv[0]).is_dir():
        window.open_project(argv[0])
    elif argv and Path(argv[0]).is_file():
        window.open_document(Path(argv[0]))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())