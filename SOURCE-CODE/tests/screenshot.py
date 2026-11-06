"""Tangkap tangkapan layar mode day & night tanpa butuh layar (offscreen)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="ktkt-shot-"))
CFG = TMP / "cfg"
CFG.mkdir()
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(CFG))
QSettings.setPath(QSettings.IniFormat, QSettings.SystemScope, str(CFG))

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from app.theme import apply_theme  # noqa: E402
from app.window import MainWindow  # noqa: E402

BAB1 = """# Bab Satu — Pasar Malam

Hujan belum turun, tapi udara sudah berbau tanah. Aruna berdiri di depan los
**kerupuk** yang sudah tutup, menghitung uang di kantongnya untuk kesepuluh kali.

> "Kamu menunggu siapa?" tanya penjaga los.

*Bukan menunggu*, pikirnya. *Menunggu itu pekerjaan orang yang punya tujuan.*

## Adegan Kedua

Babi-babi kecil berlarian di antara tenda. Aruna tersenyum. Di kampungnya,
babi bukan hewan ternak — babi adalah tanda bahwa pasar akan ramai.

- Kerupuk sepuluh bungkus
- Uang kembalian tiga ribu
- Satu janji yang belum ditepati

## Adegan Ketiga

Malam makin larut. Aruna mencatat semuanya di buku kecil, lalu menutupnya
perlahan, seolah takut suara kertas itu membangunkan seseorang.
"""

BAB2 = """# Bab Dua — Hujan

Hujan turun pukul sembilan. Aruna sudah pulang, tapi pikirannya masih di pasar,
pada babi-babi kecil yang berlarian di antara tenda.
"""


def main():
    proj = TMP / "senja-di-pasar"
    proj.mkdir()
    (proj / "01-bab-satu.md").write_text(BAB1, encoding="utf-8")
    (proj / "02-bab-dua.md").write_text(BAB2, encoding="utf-8")

    app = QApplication([sys.argv[0]])
    app.setApplicationName("ketikaketik")
    app.setOrganizationName("ketikaketik")
    apply_theme(app, "day")

    win = MainWindow()
    win.resize(1280, 820)
    win.show()
    win.open_project(proj)
    win.pane_a.editor.goto_line(6)
    QTest.qWait(300)

    for theme in ("day", "night"):
        win.set_theme(theme)
        win.open_search(False)
        win.search.query.setText("babi")
        QTest.qWait(400)
        win.grab().save(str(ROOT / f"tests/shot-{theme}.png"))
        win.close_search()
        print(f"tersimpan: tests/shot-{theme}.png")
    # tangkapan layar panel markdown issues + kilau baris
    win.set_theme("day")
    win.load_sample_chapter()
    QTest.qWait(300)
    if win.issue_list.count():
        win._jump_to_issue(win.issue_list.item(0))
        QTest.qWait(120)                # masih di dalam 1,6 detik kilau
    win.grab().save(str(ROOT / "tests/shot-issues.png"))
    print("tersimpan: tests/shot-issues.png")

    win._confirm_exit = lambda: True   # jangan tampilkan dialog saat menutup di tes
    win.close()


if __name__ == "__main__":
    main()