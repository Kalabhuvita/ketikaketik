"""Uji asap end-to-end tanpa layar (QT_QPA_PLATFORM=offscreen).

Menjalankan aplikasi sungguhan: buka proyek, cari, ganti, simpan, autosave,
riwayat, preview, outline, statistik, tema, dan ekspor .docx.
"""
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="ktkt-test-"))
CFG = TMP / "cfg"
CFG.mkdir()
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(CFG))
QSettings.setPath(QSettings.IniFormat, QSettings.SystemScope, str(CFG))

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from app.export import export_manuscript  # noqa: E402
from app.project import Project, headings_of  # noqa: E402
from app.stats import summarize  # noqa: E402
from app.theme import apply_theme  # noqa: E402
from app.window import MainWindow  # noqa: E402

passed = []
failed = []


def check(name, cond, extra=""):
    if cond:
        passed.append(name)
        print(f"  ok  {name}")
    else:
        failed.append(f"{name} {extra}")
        print(f"FAIL  {name} {extra}")


def make_project():
    proj = TMP / "novel"
    proj.mkdir()
    (proj / "01-bab-satu.md").write_text(
        "# Bab Satu\n\nBabi itu berjalan di pasar. Budi melihat **babi** lagi.\n\n"
        "Lalu Budi berkata: *Babi!* dan semua orang menoleh.\n", encoding="utf-8")
    (proj / "02-bab-dua.md").write_text(
        "# Bab Dua\n\n## Adegan\n\nDi sini tidak ada hewan. Hanya hujan.\n", encoding="utf-8")
    (proj / "catatan").mkdir()
    (proj / "catatan" / "riset.md").write_text("# riset\n\nBabi palsu\n", encoding="utf-8")
    return proj


def main():
    app = QApplication([sys.argv[0]])
    app.setApplicationName("ketikaketik")
    app.setOrganizationName("ketikaketik")
    apply_theme(app, "day")

    proj_dir = make_project()
    win = MainWindow()
    win.resize(1000, 700)
    win.show()          # perlu tampil agar QSplitter punya geometri nyata
    QTest.qWait(120)
    win.open_project(proj_dir)

    # --- proyek -------------------------------------------------------
    check("proyek terbuka", win.project is not None)
    check("subfolder diabaikan (2 bab)", len(win.project.chapters) == 2,
          f"dapat {len(win.project.chapters)}")
    check("bab pertama dimuat", win.current_path is not None
          and win.current_path.name == "01-bab-satu.md")
    text0 = win.doc.toPlainText()
    check("isi bab terbaca", "Babi itu berjalan" in text0)

    # --- statistik ----------------------------------------------------
    counts = summarize(text0)
    check("word counter", counts["words"] > 10, counts)
    check("sentence counter", counts["sentences"] >= 3, counts)
    check("paragraf", counts["paragraphs"] >= 2, counts)
    check("statistics label filled", "words" in win.lbl_stats.text(), win.lbl_stats.text())

    # --- outline ------------------------------------------------------
    check("outline punya 2 bab", win.outline.topLevelItemCount() == 2)
    heads = headings_of(win.project.read(win.project.chapters[1]))
    check("heading terdeteksi", heads and heads[0][0] == 1 and heads[1][1] == "Adegan", heads)

    # --- pencarian: sorotan persisten ---------------------------------
    win.open_search(False)
    win.search.query.setText("Babi")
    hits_before = len(win._hits)
    check("cari menemukan semua 'Babi'", hits_before == 3, f"dapat {hits_before}")
    check("search counter filled", "results" in win.search.counter.text(), win.search.counter.text())

    # Sorotan benar-benar dicat ke blok (bukan cuma angka)
    def highlighted_blocks():
        total = 0
        block = win.doc.firstBlock()
        while block.isValid():
            fmt = block.layout().formats() if block.layout() else []
            if fmt:
                total += 1
            block = block.next()
        return total

    blocks_lit = highlighted_blocks()
    check("sorotan tercat di blok", blocks_lit >= 2, f"{blocks_lit} blok")

    # ganti satu kemunculan -> sisanya tetap tersorot
    win.replace_one()
    check("satu 'Babi' diganti", "Babi itu" not in win.doc.toPlainText(),
          win.doc.toPlainText()[:60])
    check("sisa kemunculan tetap 2", len(win._hits) == 2, f"dapat {len(win._hits)}")
    check("kata pengganti masuk", "Anjing" in win.doc.toPlainText().lower()
          or "Babi" not in win.doc.toPlainText()[:20])

    # mengetik kata baru langsung ikut tersorot
    cursor = win.pane_a.editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    cursor.insertText("\n\nBabi baru datang.")
    QTest.qWait(350)          # biarkan timer statistik/penghitung hasil berjalan
    check("kata baru ikut tersorot", len(win._hits) >= 3, f"dapat {len(win._hits)}")

    # ganti semua
    win.search.replace.setText("Anjing")
    win.replace_all()
    check("ganti semua", "Babi" not in win.doc.toPlainText(), win.doc.toPlainText()[-40:])
    check("counter jadi nol", len(win._hits) == 0)
    win.close_search()

    # --- dua editor (split editor/editor) ------------------------------
    win.set_pane_mode(1, "editor")
    win._sync_documents(force=True)
    check("panel kiri benar-benar menampilkan teks",
          win.pane_a.editor.toPlainText() == win.doc.toPlainText())
    win.pane_a.editor.setPlainText("# X\n\nTeks dari panel kiri.\n")
    win._sync_source = win.pane_a.editor
    win._sync_documents(force=True)
    check("panel kanan mencerminkan panel kiri",
          "Teks dari panel kiri" in win.pane_b.editor.toPlainText())
    win.pane_b.editor.setPlainText("# X\n\nTeks dari panel kanan.\n")
    win._sync_source = win.pane_b.editor
    win._sync_documents(force=True)
    check("panel kiri menerima dari panel kanan",
          "Teks dari panel kanan" in win.doc.toPlainText())
    win.set_pane_mode(1, "preview")

    # --- simpan & riwayat ---------------------------------------------
    win.doc.setPlainText("# Bab Satu\n\nIsi baru yang hendak disimpan.\n")
    win.doc.setModified(True)
    win.save()
    disk = (proj_dir / "01-bab-satu.md").read_text(encoding="utf-8")
    check("simpan ke disk", "Isi baru yang hendak disimpan." in disk)
    check("tidak ada file sementara tertinggal",
          not list(proj_dir.glob("*.ktktmp")))
    snaps = win.project.snapshots(win.current_path)
    check("riwayat versi dibuat", len(snaps) >= 1, f"{len(snaps)} snapshot")

    # autosave
    win.doc.setPlainText("# Bab Satu\n\nBaris autosave.\n")
    win.doc.setModified(True)
    win.autosave()
    check("autosave menulis", "Baris autosave" in
          (proj_dir / "01-bab-satu.md").read_text(encoding="utf-8"))
    check("bendera modified bersih", not win.doc.isModified())

    # --- preview ------------------------------------------------------
    win.doc.setPlainText("# Judul\n\nIni **tebal** dan *miring*.\n")
    win.set_pane_mode(1, "preview")
    win._refresh_previews()
    preview_text = win.pane_b.preview.toPlainText()
    check("preview me-render markdown", "**" not in preview_text and "tebal" in preview_text,
          repr(preview_text[:40]))

    # --- lebar baris / tipografi ---------------------------------------
    win.set_line_width(34)
    app.processEvents()
    margins = win.pane_a.editor.viewportMargins()
    check("lebar baris menghasilkan margin", margins.left() > 0, margins)
    win.set_line_width(0)
    app.processEvents()

    # --- split view bisa diatur ----------------------------------------
    splitter = win.splitter
    check("pegangan splitter cukup lebar", splitter.handleWidth() >= 8,
          splitter.handleWidth())
    splitter.setSizes([800, 300])
    QTest.qWait(80)
    wide, narrow = splitter.sizes()
    splitter.setSizes([300, 800])
    QTest.qWait(80)
    narrow2, wide2 = splitter.sizes()
    check("panel bisa dibesarkan & dikecilkan bebas",
          wide > narrow and wide2 > narrow2 and abs(wide - wide2) <= 8,
          (wide, narrow, narrow2, wide2))
    splitter.setSizes([500, 500])

    # --- autosave interval ---------------------------------------------
    check("autosave default 5 minutes", win.autosave_timer.interval() == 5 * 60_000,
          win.autosave_timer.interval())
    win.set_autosave_interval(3)
    check("autosave can be set to 3 minutes", win.autosave_timer.interval() == 180_000,
          win.autosave_timer.interval())
    win.set_autosave_interval(10)
    check("autosave can be set to 10 minutes", win.autosave_timer.interval() == 600_000,
          win.autosave_timer.interval())
    win.set_autosave_interval(5)

    # --- tema ---------------------------------------------------------
    win.set_theme("night")
    check("tema night aktif", win.theme_name == "night")
    win.set_theme("day")
    check("tema day aktif", win.theme_name == "day")

    # --- mode editor ---------------------------------------------------
    win.set_editor_mode("raw")
    check("mode raw", win.md_hl.enabled is False)
    win.set_editor_mode("formatted")
    check("mode formatted", win.md_hl.enabled is True)

    # --- lint ---------------------------------------------------------
    win.doc.setPlainText("# Bab\n\n### Lompat\n\n**tidak ditutup\n")
    win._update_lint()
    check("lint menemukan masalah", len(win.lint_issues) >= 2, win.lint_issues)

    # --- panel issues: klik = lompat + seleksi + kilau ------------------
    win.toggle_lint_panel()
    check("issues panel opens", win.issues_panel.isVisibleTo(win))
    check("issues listed in the panel",
          win.issue_list.count() == len(win.lint_issues), win.issue_list.count())
    first = win.issue_list.item(0)
    line_no = first.data(Qt.UserRole)
    win._jump_to_issue(first)
    cursor = win.pane_a.editor.textCursor()
    check("clicked issue moves the cursor to its line",
          cursor.blockNumber() == line_no - 1 and not cursor.hasSelection(),
          (cursor.blockNumber(), line_no))
    check("line flash applied", len(win.pane_a.editor.extraSelections()) == 1)
    QTest.qWait(2700)
    check("flash fades away", len(win.pane_a.editor.extraSelections()) == 0)
    check("panel stays open after jumping", win.issues_panel.isVisibleTo(win))

    # --- bab contoh -----------------------------------------------------
    from app.sample import SAMPLE_TEXT as _sample
    from app.stats import count_words as _count
    check("sample text is at least 2000 words", _count(_sample) >= 2000, _count(_sample))
    before = len(win.project.chapters)
    win.load_sample_chapter()
    QTest.qWait(250)
    check("sample chapter created and opened",
          len(win.project.chapters) == before + 1
          and "Mesin yang Belajar Diam" in win.doc.toPlainText(),
          len(win.project.chapters))
    check("sample keeps its two intentional issues",
          len(win.lint_issues) >= 2, win.lint_issues)

    # --- keluarkan bab dari proyek tanpa menyentuh file -----------------
    target = win.project.chapters[-1]
    win._hide_path(target)
    check("hidden chapter leaves the chapter list", target not in win.project.chapters)
    check("hidden chapter file is still on disk", target.exists())
    check("hidden chapter tracked as hidden", target in win.project.hidden_chapters())
    tops = [win.outline.topLevelItem(i).text(0)
            for i in range(win.outline.topLevelItemCount())]
    check("outline no longer lists the hidden chapter", target.stem not in tops, tops)
    win.project.restore_chapter(target.name)
    win._fill_chapters()
    check("restoring brings the chapter back", target in win.project.chapters)

    # --- recent project bisa dibuang dari daftar ------------------------
    from app.project import add_recent, load_recent, remove_recent
    p1 = TMP / "proj-one"
    p2 = TMP / "proj-two"
    p1.mkdir(exist_ok=True)
    p2.mkdir(exist_ok=True)
    add_recent(p1)
    add_recent(p2)
    remove_recent(p1)
    recent = load_recent()
    check("recent entry removed, the other kept",
          str(p1) not in recent and str(p2) in recent, recent)

    # --- ekspor docx ----------------------------------------------------
    win.save()
    out = TMP / "naskah.docx"
    export_manuscript(win.project.chapters, out, title="Novel Uji")
    check("docx dibuat", out.exists() and out.stat().st_size > 2000,
          out.stat().st_size if out.exists() else "tidak ada")
    if out.exists():
        with zipfile.ZipFile(out) as z:
            styles = z.read("word/styles.xml").decode("utf-8")
        check("gaya manuskrip ditanam", "Times New Roman" in styles)
        check("spasi ganda", 'w:line="480"' in styles)

    # --- teks tidak hilang saat folder dipilih di tengah penulisan ------
    typed = "Teks yang diketik sebelum memilih folder."
    win.doc.setPlainText(typed)
    other = TMP / "existing-project"
    other.mkdir(exist_ok=True)
    (other / "01-old.md").write_text("# Old\n\nold body\n", encoding="utf-8")
    win.open_project(other, load_first=False)
    check("text survives opening a project without loading a chapter",
          "sebelum memilih folder" in win.doc.toPlainText() and win.current_path is None)
    check("chapter list still filled", win.chapter_list.count() == 1)

    # --- fokus tidak direbut saat mengetik di kolom pencarian ----------
    win.set_pane_mode(1, "preview")
    win.doc.setPlainText("babi satu, babi dua, babi tiga.\n")
    win.open_search(False)
    win.search.query.clear()
    win.search.query.setFocus(Qt.OtherFocusReason)
    app.processEvents()
    QTest.keyClicks(win.search.query, "babi")
    QTest.qWait(250)
    check("focus stays in the search field",
          QApplication.focusWidget() is win.search.query
          or not win.pane_a.editor.hasFocus(),
          type(QApplication.focusWidget()).__name__)
    check("typed query actually searches", len(win._hits) == 3, len(win._hits))
    win.close_search()

    # --- sidebar: label tidak menumpuk di atas daftar -------------------
    check("OUTLINE label sits above the outline tree",
          win.outline_label.geometry().bottom() < win.outline.geometry().top(),
          (win.outline_label.geometry().getRect(), win.outline.geometry().getRect()))
    check("CHAPTERS label sits above the chapter list",
          win.chapter_label.geometry().bottom() < win.chapter_list.geometry().top(),
          (win.chapter_label.geometry().getRect(), win.chapter_list.geometry().getRect()))

    # --- konfirmasi sebelum keluar (overlay di dalam jendela) -----------
    title, message, options = win._exit_options(dirty=True)
    labels = win.confirm.build(title, message, options)
    check("unsaved exit offers Save / Discard / Cancel",
          labels == ["Save", "Discard", "Cancel"], labels)
    win.confirm.setGeometry(win.rect())
    win.confirm.show()
    app.processEvents()
    check("overlay covers the whole window",
          win.confirm.geometry() == win.rect(),
          (win.confirm.geometry().getRect(), win.rect().getRect()))
    delta_card = win.confirm.card.geometry().center() - win.confirm.rect().center()
    check("confirm card is centred in the window",
          abs(delta_card.x()) <= 2 and abs(delta_card.y()) <= 2,
          (delta_card.x(), delta_card.y()))
    discard_px = win.confirm._buttons["discard"].grab().toImage().pixelColor(4, 4)
    cancel_px = win.confirm._buttons["cancel"].grab().toImage().pixelColor(4, 4)
    check("destructive button is visually distinct", discard_px != cancel_px,
          (discard_px.getRgb(), cancel_px.getRgb()))
    win.confirm.hide()

    title2, message2, options2 = win._exit_options(dirty=False)
    labels2 = win.confirm.build(title2, message2, options2)
    check("clean exit offers Quit / Cancel", labels2 == ["Quit", "Cancel"], labels2)

    # loop overlay sungguhan: pilih Discard, lalu Cancel
    win.doc.setModified(True)
    QTimer.singleShot(150, lambda: win.confirm._buttons["discard"].click())
    check("overlay returns the chosen action", win._confirm_exit() is True)
    check("overlay hides after choosing", win.confirm.isVisible() is False)

    win.doc.setModified(True)
    QTimer.singleShot(150, lambda: win.confirm._buttons["cancel"].click())
    check("cancel returns False", win._confirm_exit() is False)

    win._confirm_exit = lambda: False
    win.close()
    check("Cancel keeps the window open", win.isVisible())
    win._confirm_exit = lambda: True

    # --- pemilih font: pratinjau langsung -------------------------------
    from app.fontpicker import FontChooser
    start_family, start_size = win.font_family, win.font_size
    saved_family = win.settings.value("ui/font_family", "")
    chooser = FontChooser(start_family, start_size, win.line_spacing, win)
    chooser.changed.connect(win._preview_font)
    chooser.spin.setValue(24)
    app.processEvents()
    check("font size previews on the manuscript immediately",
          abs(win.pane_a.editor.font().pointSizeF() - 24) < 0.6,
          win.pane_a.editor.font().pointSizeF())
    check("font preview does not persist yet",
          win.settings.value("ui/font_family", "") == saved_family)
    win.font_family, win.font_size = start_family, start_size
    win._apply_typography(persist=False)
    check("cancel would restore the previous size",
          abs(win.pane_a.editor.font().pointSizeF() - start_size) < 0.6,
          win.pane_a.editor.font().pointSizeF())

    win._preview_font("DejaVu Serif", 15)
    win._apply_typography()
    check("confirming a font persists it",
          win.settings.value("ui/font_family", "") == "DejaVu Serif",
          win.settings.value("ui/font_family", ""))
    win._preview_font(start_family, start_size)
    win._apply_typography()

    # --- alur penuh pilih font: Cancel lalu OK ---------------------------
    def drive_picker(size, button):
        def act():
            picker = win.confirm.card.findChild(FontChooser)
            if picker is not None:
                picker.spin.setValue(size)
            win.confirm._buttons[button].click()
        return act

    before_size = win.pane_a.editor.font().pointSizeF()
    QTimer.singleShot(200, drive_picker(30, "cancel"))
    win.choose_font()
    check("Cancel restores the font that was in use",
          abs(win.pane_a.editor.font().pointSizeF() - before_size) < 0.6,
          win.pane_a.editor.font().pointSizeF())

    QTimer.singleShot(200, drive_picker(30, "ok"))
    win.choose_font()
    check("OK keeps the chosen size",
          abs(win.pane_a.editor.font().pointSizeF() - 30) < 0.6,
          win.pane_a.editor.font().pointSizeF())
    check("OK persists the chosen size",
          abs(float(win.settings.value("ui/font_size", 0)) - 30) < 0.6,
          win.settings.value("ui/font_size", ""))

    win._preview_font(start_family, start_size)
    win._apply_typography()

    # --- jarak baris ----------------------------------------------------
    win.line_spacing = 1.8
    win._apply_typography(persist=False)
    line_height = win.doc.firstBlock().blockFormat().lineHeight()
    check("line spacing reaches the text blocks", abs(line_height - 180) < 1, line_height)
    win.line_spacing = 1.35
    win._apply_typography(persist=False)

    # --- preview: jangkar stabil & tahu folder proyek -------------------
    long_body = "# Bab\n\n" + "\n\n".join(
        f"Paragraf {i}. Kalimat panjang supaya dokumen bisa digulir." for i in range(80))
    win.doc.setPlainText(long_body)
    win.set_pane_mode(1, "preview")
    win._refresh_previews()
    app.processEvents()
    preview = win.pane_b.preview

    editor_bar = win.pane_a.editor.verticalScrollBar()
    editor_bar.setValue(editor_bar.maximum() // 2)
    win._refresh_previews()
    app.processEvents()
    editor_top = win._plain_needle(
        win.pane_a.editor.cursorForPosition(QPoint(0, 0)).block().text())
    preview_top = preview.cursorForPosition(QPoint(0, 0)).block().text().strip()
    check("preview lands on the paragraph visible in the editor",
          editor_top[:25] in preview_top, (editor_top[:40], preview_top[:40]))
    first = preview.verticalScrollBar().value()
    win._refresh_previews()
    app.processEvents()
    second = preview.verticalScrollBar().value()
    check("re-rendering keeps the preview where it was",
          abs(first - second) <= 2, (first, second))

    editor_bar.setValue(editor_bar.maximum() * 3 // 4)
    win._sync_scroll()
    app.processEvents()
    later = preview.verticalScrollBar().value()
    check("preview follows the editor viewport", later > second + 40, (second, later))
    base_url = preview.document().baseUrl().toLocalFile().rstrip("/")
    check("preview knows the project folder", base_url == str(win.project.root), base_url)

    # --- posisi kursor di status bar ------------------------------------
    win._active_editor().goto_position(0, focus=False)
    win._update_cursor_label()
    check("status bar shows the cursor position",
          win.lbl_cursor.text().startswith("Ln "), win.lbl_cursor.text())

    # --- lint ditunda, tidak tiap ketukan --------------------------------
    if not win.issues_panel.isVisibleTo(win):
        win.toggle_lint_panel()
    win.pane_a.editor.insertPlainText(" x")
    check("markdown check is deferred, not per keystroke", win.lint_timer.isActive())
    QTest.qWait(800)

    # --- file berubah dari luar -----------------------------------------
    win.doc.setPlainText("Versi dari aplikasi.\n")
    win._mark_saved()
    win.save()
    disk_text = "Versi lain dari editor luar.\n"
    QTest.qWait(30)
    win.current_path.write_text(disk_text, encoding="utf-8")
    check("change on disk is detected", win._changed_on_disk())
    win.doc.setPlainText("Versi aplikasi yang lebih baru.\n")
    win.doc.setModified(True)
    win.autosave()
    check("autosave refuses to overwrite an external change",
          win.current_path.read_text(encoding="utf-8") == disk_text)

    previous_ask = win.confirm.ask
    win.confirm.ask = lambda *a, **k: "overwrite"
    try:
        win.save()
    finally:
        win.confirm.ask = previous_ask
    check("saving after confirmation overwrites as asked",
          "lebih baru" in win.current_path.read_text(encoding="utf-8"))

    # --- hitungan sesi mulai ulang per proyek ---------------------------
    other = TMP / "proj-two"
    other.mkdir(exist_ok=True)
    (other / "01-lain.md").write_text("satu dua tiga empat\n", encoding="utf-8")
    win.open_project(other)
    QTest.qWait(150)
    expected = _count(win.doc.toPlainText())
    check("session word counter restarts for a new project",
          win.session_base == expected, (win.session_base, expected))

    # --- Enter tidak tertelan setelah jarak baris diterapkan -------------
    win.set_pane_mode(1, "preview")   # seperti saat menulis: panel kanan preview
    editor = win.pane_a.editor
    win.doc.setPlainText("satu\n\ndua\n")
    editor.setFocus()
    caret = editor.textCursor()
    caret.movePosition(caret.MoveOperation.EndOfBlock)
    editor.setTextCursor(caret)
    QTest.qWait(80)
    start_block = editor.textCursor().blockNumber()
    length_before = len(editor.toPlainText())
    for _ in range(5):
        QTest.keyClick(editor, Qt.Key_Return)
        QTest.qWait(60)
    check("every Enter inserts a line break (none swallowed)",
          len(editor.toPlainText()) - length_before == 5,
          (len(editor.toPlainText()), length_before))
    check("caret really advanced five blocks",
          editor.textCursor().blockNumber() == start_block + 5,
          (editor.textCursor().blockNumber(), start_block))

    # --- keamanan penyimpanan -------------------------------------------
    from app import recovery
    from app.project import Project as Project2

    # semua dialog di blok ini dijawab otomatis supaya uji tidak menggantung
    answers = {"default": "cancel"}
    asked = []
    def auto_ask(title, message, options, *a, **k):
        asked.append(title)
        return answers.get(title, answers["default"])
    original_ask = win.confirm.ask
    win.confirm.ask = auto_ask
    try:
        lock_test = Project2(win.project.root)
        check("second window cannot lock the same project", lock_test.acquire_lock() is False)
        win.project.release_lock()
        check("lock is available again after release", lock_test.acquire_lock() is True)
        lock_test.release_lock()
        win.project.acquire_lock()

        # BOM di file harus tetap ada setelah disimpan aplikasi
        bom_target = win.project.root / "02-bom.md"
        bom_target.write_bytes(b"\xef\xbb\xbfJudul BOM\n")
        win.project.scan()
        win._fill_chapters()
        win._open_chapter(bom_target)
        QTest.qWait(150)
        win.doc.setPlainText("Judul BOM diubah\n")
        win.doc.setModified(True)
        answers["default"] = "overwrite"
        win.save()
        answers["default"] = "cancel"
        check("BOM preserved when the app saves",
              bom_target.read_bytes().startswith(b"\xef\xbb\xbf"),
              bom_target.read_bytes()[:3])

        # jurnal pemulihan ditawarkan saat bab dibuka kembali
        journal_target = win.project.chapters[0]
        recovery.write_journal(win.project.root, journal_target,
                               "Teks dari jurnal pemulihan.\n")
        answers["Unsaved work found"] = "restore"
        if win.current_path == journal_target:
            win._open_chapter(bom_target)      # pindah dulu
        QTest.qWait(120)
        win._open_chapter(journal_target)
        QTest.qWait(150)
        answers.pop("Unsaved work found", None)
        check("recovery prompt appears for unsaved work",
              "Unsaved work found" in asked, asked)
        check("recovered text is put back in the editor",
              "jurnal pemulihan" in win.doc.toPlainText(), win.doc.toPlainText()[:40])
        check("recovered text is marked as unsaved", win.doc.isModified())
    finally:
        win.confirm.ask = original_ask

    # --- whole word & case sensitivity -----------------------------------
    win.open_search(False)
    win.search.word.setChecked(True)
    win.search.case.setChecked(False)
    win.doc.setPlainText("sayang peyang yang\n")
    win.search.query.setText("yang")
    win._search_changed()
    check("whole word ignores 'sayang' and 'peyang'",
          len(win._hits) == 1, win._hits)
    win.search.word.setChecked(False)
    check("turning whole word off matches substrings again",
          len(win._hits) == 3, win._hits)

    win.search.word.setChecked(True)
    win.search.case.setChecked(False)
    win.doc.setPlainText("Yang yang YANG\n")
    win.search.query.setText("yang")
    win._search_changed()
    check("case-insensitive by default matches all three",
          len(win._hits) == 3, win._hits)
    win.search.case.setChecked(True)
    check("match case narrows it to one", len(win._hits) == 1, win._hits)

    win.search.case.setChecked(False)
    win.doc.setPlainText("sayang yang yang\n")
    win.search.query.setText("yang")
    win._search_changed()
    win.search.replace.setText("X")
    win.replace_all()
    check("replace all respects whole word",
          win.doc.toPlainText().strip() == "sayang X X", win.doc.toPlainText())

    check("whole word is on by default for new sessions",
          win.settings.value("search/whole_word", None) in (True, "true", "1"),
          win.settings.value("search/whole_word", None))
    win.close_search()

    # --- patah baris ala Obsidian: 1x Enter vs 2x Enter ------------------
    from app.softbreaks import with_hard_breaks

    sample = "baris satu\nbaris dua\n\nparagraf baru\n\n```\nkode\nbaris kode\n```\n"
    transformed = with_hard_breaks(sample)
    check("single newline becomes a hard break", "baris satu  \n" in transformed, transformed[:40])
    check("blank line is left as a paragraph break", "\n\nparagraf baru" in transformed)
    check("code fences are untouched", "kode\nbaris kode" in transformed)

    win.doc.setPlainText("baris satu\nbaris dua\n")
    win._refresh_previews()
    app.processEvents()
    preview_doc = win.pane_b.preview.document()
    check("one Enter keeps it one paragraph with a line break",
          preview_doc.blockCount() == 1
          and "baris satu\nbaris dua" in preview_doc.toPlainText(),
          (preview_doc.blockCount(), preview_doc.toPlainText()))

    win.doc.setPlainText("paragraf satu\n\nparagraf dua\n")
    win._refresh_previews()
    app.processEvents()
    preview_doc = win.pane_b.preview.document()
    second = preview_doc.findBlockByNumber(1)
    check("two Enters make a real second paragraph",
          preview_doc.blockCount() == 2, preview_doc.blockCount())
    check("a new paragraph is visibly spaced",
          int(second.blockFormat().topMargin()) > 0,
          second.blockFormat().topMargin())

    win.doc.setPlainText("satu\n\n\ndua\n")
    win._refresh_previews()
    app.processEvents()
    check("three Enters do not create an extra empty paragraph",
          win.pane_b.preview.document().blockCount() == 2,
          win.pane_b.preview.document().blockCount())

    # ekspor harus mempertahankan patah baris yang sama dengan preview
    export_src = TMP / "softbreak.md"
    export_src.write_text("baris satu\nbaris dua\n", encoding="utf-8")
    export_out = TMP / "softbreak.docx"
    export_manuscript([export_src], export_out, title="Uji")
    with zipfile.ZipFile(export_out) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    check("export keeps the same line break as the preview",
          re.search(r"<w:br\s*/>", document_xml) is not None)

    # --- naskah raksasa: preview tetap di paragraf yang sama -------------
    big_para = ("Lara membuka naskah itu dan membaca halaman demi halaman sambil mencatat "
                "setiap kalimat yang terasa janggal di telinganya, lalu membandingkannya "
                "dengan versi yang sudah disunting mesin sebelumnya.")
    big_body = "# Besar\n\n" + "\n\n".join(
        f"Paragraf {i}. {big_para}" for i in range(2600))
    big_project = TMP / "big-novel"
    big_project.mkdir(exist_ok=True)
    (big_project / "01-big.md").write_text(big_body, encoding="utf-8")
    win.open_project(big_project)
    QTest.qWait(900)
    big_editor = win.pane_a.editor
    big_preview = win.pane_b.preview
    bar = big_editor.verticalScrollBar()
    bar.setValue(int(bar.maximum() * 0.5))
    QTest.qWait(120)
    win._refresh_previews()
    QTest.qWait(400)

    def top_line(widget):
        return widget.cursorForPosition(QPoint(0, 0)).block().text().strip()[:20]

    before_top = top_line(big_preview)
    cursor = big_editor.cursorForPosition(QPoint(200, 200))
    big_editor.setTextCursor(cursor)
    for _ in range(3):
        big_editor.insertPlainText("x")
        QTest.qWait(1400)
    after_top = top_line(big_preview)
    check("huge document: preview keeps the same paragraph while typing",
          before_top == after_top and before_top.startswith("Paragraf"),
          (before_top, after_top))

    # --- reflow: sambung baris yang dipatahkan manual --------------------
    from app.reflow import reflow_paragraphs

    wrapped = ("# Judul\n\n"
               "Baris pertama paragraf yang\n"
               "dipatahkan manual di tengah\n"
               "kalimatnya.\n\n"
               "- butir satu\n- butir dua\n\n"
               "> kutipan yang juga\n> terpatah\n\n"
               "```\nkode jangan diubah\nsama sekali\n```\n")
    joined, count = reflow_paragraphs(wrapped)
    check("reflow joins wrapped paragraph lines",
          "Baris pertama paragraf yang dipatahkan manual di tengah kalimatnya." in joined,
          joined.split("\n")[2][:60])
    check("reflow keeps lists, quotes and code untouched",
          "- butir satu" in joined and "> kutipan yang juga" in joined
          and "kode jangan diubah" in joined)
    check("reflow reports how many paragraphs it touched", count >= 1, count)

    win.doc.setPlainText(wrapped)
    original_text = win.doc.toPlainText()
    win.do_reflow()
    check("reflow command applies to the editor",
          "dipatahkan manual di tengah kalimatnya." in win.doc.toPlainText())
    win._active_editor().undo()
    check("reflow can be undone in one step",
          "dipatahkan manual di tengah" in win.doc.toPlainText(), win.doc.toPlainText()[:40])
    win.doc.setPlainText(original_text)

    # --- about & ikon ---------------------------------------------------
    from app.window import ABOUT_COPYRIGHT, ABOUT_LINE, ABOUT_TITLE, ICON_FILE
    check("about line is exactly as requested",
          ABOUT_LINE == "A markdown editor for writing novel", ABOUT_LINE)
    check("about copyright names the flock",
          ABOUT_COPYRIGHT.startswith("Untuk anak-anak bulu:")
          and "Puri" in ABOUT_COPYRIGHT, ABOUT_COPYRIGHT)
    win.confirm.build(ABOUT_LINE, ABOUT_COPYRIGHT, [("ok", "OK", "primary")],
                      win._about_icon())
    about_texts = [lbl.text() for lbl in win.confirm.card.findChildren(QLabel)]
    check("about shows both lines",
          ABOUT_LINE in about_texts and ABOUT_COPYRIGHT in about_texts, about_texts)
    check("about shows the icon",
          any(lbl.pixmap() is not None and not lbl.pixmap().isNull()
              for lbl in win.confirm.card.findChildren(QLabel)))
    QTimer.singleShot(400, lambda: win.confirm._buttons["ok"].click())
    win.confirm.run()
    check("about fades in (opacity effect attached)",
          win.confirm.card.graphicsEffect() is not None)
    win.confirm.hide()

    win._apply_start_geometry()
    area = QGuiApplication.primaryScreen().availableGeometry()
    want_w = min(area.width(), max(900, int(area.width() * 0.7)))
    want_h = min(area.height(), max(600, int(area.height() * 0.7)))
    check("start size is 70% of the available screen",
          abs(win.width() - want_w) <= 2 and abs(win.height() - want_h) <= 2,
          (win.width(), win.height(), want_w, want_h))
    check("start position is centred on that screen",
          abs(win.frameGeometry().center().x() - area.center().x()) <= 2
          and abs(win.frameGeometry().center().y() - area.center().y()) <= 2,
          (win.frameGeometry().center(), area.center()))
    check("icon file is games.png", ICON_FILE.name == "games.png" and ICON_FILE.exists(),
          str(ICON_FILE))
    check("window icon is set", not win.windowIcon().isNull())

    # --- close ----------------------------------------------------------
    win.close()

    # --- repetisi: mesin analisis ----------------------------------------
    from app import repetition

    sample = ("Mata Lara menatap layar. Mata itu lelah.\n\n"
              "Ia melihat mesin. Ia melihat layar lagi.\n\n"
              "Pada saat itu hujan turun.\n")

    check("enclitic -nya is stripped", repetition.strip_enclitic("matanya") == "mata")
    check("short word is not stripped", repetition.strip_enclitic("nya") == "nya")
    check("flavours are labelled",
          repetition.flavor_of("yang") == "function word"
          and repetition.flavor_of("kah") == "particle"
          and repetition.flavor_of("menatap") == "fiction habit"
          and repetition.flavor_of("mesin") == "content",
          [repetition.flavor_of(w) for w in ("yang", "kah", "menatap", "mesin")])

    words, totals = repetition.frequency(sample, min_count=2)
    names = [row["word"] for row in words]
    check("every word is counted by default", "itu" in names and "mata" in names, names)
    check("density per 1000 words is reported", all("per_1000" in row for row in words))
    from app.stats import count_sentences, count_words
    totals_check = repetition.analyze(sample)["totals"]
    check("repetition totals use the same counter as the status bar",
          totals_check["words"] == count_words(sample)
          and totals_check["sentences"] == count_sentences(sample),
          (totals_check, count_words(sample), count_sentences(sample)))

    repeats, _ = repetition.close_repetitions(sample, window=3)
    check("repetition inside a few sentences is flagged",
          "mata" in [row["word"] for row in repeats])
    check("findings carry a density", all("density" in row for row in repeats))
    scores = [row["score"] for row in repeats]
    check("most disruptive clusters come first", scores == sorted(scores, reverse=True), scores)
    narrow, _ = repetition.close_repetitions(sample, window=0, include_cliches=False)
    check("narrow window stops flagging distant repeats",
          "mata" not in [row["word"] for row in narrow])
    cliche_rows, _ = repetition.close_repetitions(sample, include_cliches=True)
    check("cliche phrase is detected",
          any(row["kind"] == "cliche" for row in cliche_rows),
          [row["word"] for row in cliche_rows])
    no_cliche, _ = repetition.close_repetitions(sample, include_cliches=False)
    check("cliche detection can be switched off",
          not any(row["kind"] == "cliche" for row in no_cliche))

    # --- repetisi: jendela terpisah --------------------------------------
    win._active_editor().setPlainText(sample * 2)
    win._on_contents()
    QTest.qWait(80)
    win.open_repetition()
    QTest.qWait(200)
    rw = win.rep_window
    check("repetition opens in its own window", rw is not None and rw.isWindow())
    check("analysis lives outside the writing UI",
          not win.centralWidget().isAncestorOf(rw))
    check("three lists are present", rw.tabs.count() == 3)

    phrase_rows, _ = repetition.repeated_phrases(
        "Ia menghela napas panjang. Lalu ia menghela napas panjang lagi.")
    phrase_names = [row["phrase"] for row in phrase_rows]
    check("longest phrase wins over its own fragments",
          "ia menghela napas panjang" in phrase_names
          and "menghela napas" not in phrase_names, phrase_names)
    boundary, _ = repetition.repeated_phrases("kata satu. kata dua.")
    check("phrases never cross a sentence end", boundary == [],
          [row["phrase"] for row in boundary])

    from app.sections import section_at, section_text
    doc = "# A\n\nalpha\n\n## B\n\nbeta\n\n## C\n\ngamma\n"
    check("section starts at its own heading", section_at(doc, 7)[0] == 5, section_at(doc, 7))
    section_body, section_title = section_text(doc, 7)
    check("section text stops at the next heading",
          "beta" in section_body and "gamma" not in section_body and section_title == "B",
          (section_title, section_body))
    check("repeat list is filled", rw.repeat_tree.topLevelItemCount() > 0)

    expected = len(repetition.analyze(win._current_text(),
                                      min_count=rw.min_count.value())["words"])
    check("nothing is filtered out of the list",
          rw.word_tree.topLevelItemCount() == expected,
          (rw.word_tree.topLevelItemCount(), expected))

    first = rw.repeat_tree.topLevelItem(0)
    target_line = first.data(0, Qt.UserRole)
    rw._emit_jump(first, 0)
    QTest.qWait(120)
    check("clicking a finding moves the caret to that line",
          win._active_editor().textCursor().blockNumber() + 1 == target_line,
          (win._active_editor().textCursor().blockNumber() + 1, target_line))

    check("analysis waits 1.5 s after typing",
          win.rep_timer.interval() == 1500 and win.rep_timer.isSingleShot())
    win.rep_timer.stop()
    win._active_editor().insertPlainText("kata ")
    QTest.qWait(60)
    check("typing schedules the analysis refresh", win.rep_timer.isActive())
    win.rep_timer.stop()

    check("whole novel is the default scope", "Whole novel" in rw.status.text(), rw.status.text())
    rw.scope.setCurrentIndex(1)
    QTest.qWait(150)
    check("this section scope works", "This section" in rw.status.text(), rw.status.text())
    rw.scope.setCurrentIndex(0)
    QTest.qWait(100)

    rw.tabs.setCurrentIndex(2)
    QTest.qWait(250)
    check("repeated phrases tab fills", rw.phrase_tree.topLevelItemCount() > 0,
          rw.phrase_tree.topLevelItemCount())
    top_phrase = rw.phrase_tree.topLevelItem(0).text(0)
    check("a phrase holds at least two words", len(top_phrase.split()) >= 2, top_phrase)
    check("phrase rows carry a line number",
          rw.phrase_tree.topLevelItem(0).data(3, 0) >= 1,
          rw.phrase_tree.topLevelItem(0).data(3, 0))
    check("longest phrases are listed first",
          rw.phrase_tree.topLevelItem(0).data(1, 0)
          >= rw.phrase_tree.topLevelItem(rw.phrase_tree.topLevelItemCount() - 1).data(1, 0))
    rw.tabs.setCurrentIndex(0)
    QTest.qWait(150)

    # abaikan satu kata: tetap tampil, tapi ditandai
    victim = rw.word_tree.topLevelItem(0).text(0)
    rw._set_ignored({victim})
    rw.refresh()
    QTest.qWait(80)
    rows = [rw.word_tree.topLevelItem(i).text(0)
            for i in range(rw.word_tree.topLevelItemCount())]
    check("ignoring keeps the word visible but marked", victim in rows, rows[:6])
    check("ignored row is struck out",
          rw.word_tree.topLevelItem(rows.index(victim)).font(0).strikeOut())

    rw.hide_ignored.setChecked(True)
    QTest.qWait(80)
    hidden_rows = [rw.word_tree.topLevelItem(i).text(0)
                   for i in range(rw.word_tree.topLevelItemCount())]
    check("Hide ignored removes it from the list", victim not in hidden_rows)
    rw.hide_ignored.setChecked(False)
    rw._restore_all()
    QTest.qWait(80)
    restored_rows = [rw.word_tree.topLevelItem(i).text(0)
                     for i in range(rw.word_tree.topLevelItemCount())]
    check("Restore all brings every word back", victim in restored_rows)

    rw.resize(420, 500)
    rw.show()
    QTest.qWait(80)
    check("window can be narrowed", rw.width() <= 460, rw.width())
    check("minimum width stays small", rw.minimumWidth() <= 400, rw.minimumWidth())

    rw.min_count.setValue(7)
    check("settings survive", int(QSettings().value("repetition/min_count", 0)) == 7)
    rw.min_count.setValue(3)
    check("menu shortcut is Ctrl+Shift+R",
          win.act_repetition.shortcut().toString() == "Ctrl+Shift+R",
          win.act_repetition.shortcut().toString())
    rw.close()
    QTest.qWait(80)
    win._mark_saved()

    # --- mode file klasik ------------------------------------------------
    import tempfile as _tempfile
    solo_dir = Path(_tempfile.mkdtemp()) / "solo"
    solo_dir.mkdir(parents=True)
    (solo_dir / "lain.md").write_text("# Lain\n\nisi lain.\n", encoding="utf-8")
    solo = solo_dir / "novel-solo.md"
    solo.write_text("# Solo\n\n## Satu\n\nsatu dua tiga. satu dua tiga.\n", encoding="utf-8")

    win.open_document(solo)
    QTest.qWait(150)
    check("file mode opens one file", win.file_mode and Path(win.current_path) == solo,
          win.current_path)
    check("chapters panel hides in file mode", not win.chapters_box.isVisibleTo(win))
    check("outline shows only that file", win.outline.topLevelItemCount() == 1,
          win.outline.topLevelItemCount())
    check("window title names the file", solo.name in win.windowTitle(), win.windowTitle())

    win._active_editor().setPlainText("# Solo\n\nteks berubah.\n")
    win.doc.setModified(True)
    win.save()
    check("file mode saves to disk", "berubah" in solo.read_text(encoding="utf-8"))

    from app.project import load_recent_files
    check("file lands in Recent Files", str(solo) in load_recent_files(), load_recent_files())

    win.open_repetition()
    QTest.qWait(200)
    check("repetition works without a project folder",
          win.rep_window is not None and win.rep_window.isVisible())
    win.rep_window.close()
    QTest.qWait(80)

    # --- folder dipindai ulang -------------------------------------------
    check("rescan has the F5 shortcut",
          win.act_rescan.shortcut().toString() == "F5",
          win.act_rescan.shortcut().toString())
    project_root = Path(_tempfile.mkdtemp()) / "proyek"
    project_root.mkdir(parents=True)
    (project_root / "01-satu.md").write_text("# Satu\n\nisinya.\n", encoding="utf-8")
    win.open_project(project_root)
    QTest.qWait(150)
    check("back to project mode shows chapters", not win.file_mode)
    (project_root / "02-dua.md").write_text("# Dua\n\nisinya.\n", encoding="utf-8")
    win.rescan_project()
    QTest.qWait(80)
    names = [win.chapter_list.item(i).data(Qt.UserRole)
             for i in range(win.chapter_list.count())]
    check("rescan finds files added on disk", str(project_root / "02-dua.md") in names, names)

    # --- section mengikuti kursor ----------------------------------------
    section_file = Path(_tempfile.mkdtemp()) / "headings.md"
    section_file.write_text(
        "# Novel\n\n## Bootup\n\nboot.\n\n## Prolog\n\n"
        "Lara menatap layar. Lara menatap layar lagi.\n\n"
        "### Jakarta\n\nHujan turun. Hujan turun lagi. Hujan turun deras.\n",
        encoding="utf-8")
    win.open_document(section_file)
    QTest.qWait(150)
    win.open_repetition()
    QTest.qWait(200)
    rw2 = win.rep_window
    rw2.scope.setCurrentIndex(1)
    QTest.qWait(300)

    editor2 = win._active_editor()
    def _go(line):
        cursor = editor2.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        for _ in range(line - 1):
            cursor.movePosition(cursor.MoveOperation.Down)
        editor2.setTextCursor(cursor)
        QTest.qWait(650)

    _go(9)
    prolog_label = rw2.status.text()
    _go(13)
    jakarta_label = rw2.status.text()
    check("section scope names its heading", "This section —" in prolog_label, prolog_label)
    check("analysis follows the cursor on its own", prolog_label != jakarta_label,
          (prolog_label, jakarta_label))
    check("section follow is debounced, not per keystroke",
          win.rep_section_timer.interval() == 400)
    check("scope tooltip explains the two choices",
          "heading" in rw2.scope.toolTip().lower())
    rw2.close()
    QTest.qWait(80)

    print(f"\n{len(passed)} lulus, {len(failed)} gagal")
    if failed:
        for item in failed:
            print("  -", item)
    shutil.rmtree(TMP, ignore_errors=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())