"""Jendela utama: semua fitur disatukan di sini."""
import re
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSettings, Qt, QTimer
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QGuiApplication, QIcon,
                           QKeySequence, QPixmap, QTextBlockFormat, QTextCursor,
                           QTextDocument)
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog,
                               QHBoxLayout, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QSplitter, QToolButton, QVBoxLayout,
                               QWidget)

from .confirm import ConfirmOverlay
from .editor import Pane
from .export import ExportError, export_manuscript
from .fontpicker import FontChooser
from .highlighter import MarkdownHighlighter, SearchHighlighter
from .lint import lint_text
from .outline import Outline
from .project import (Project, add_recent, add_recent_file, load_recent,
                      load_recent_files, remove_recent, remove_recent_file)
from .recovery import clear_journal, read_journal, write_journal
from .reflow import reflow_paragraphs
from .sample import SAMPLE_TEXT, SAMPLE_TITLE
from .search import ProjectSearchDialog, SearchBar
from .stats import count_words, summarize
from .theme import THEME_LABEL, apply_theme, colors

PREVIEW_MS = 450
STATS_MS = 180


ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICON_FILE = ASSETS / "games.png"

ABOUT_TITLE = "About Ketikaketik"
ABOUT_LINE = "A markdown editor for writing novel"
ABOUT_COPYRIGHT = ("Untuk anak-anak bulu: Keanu, Lemon, Sabrina, Boba, Mia, Goomba, "
                   "Koopa, Ultra, Jaja, Atom, Hawai, dan Puri")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.project = None
        self.current_path = None
        self.cursor_cache = {}
        self.session_base = None
        self.lint_issues = []
        self._loading = False
        self._selecting = False
        self._hits = []
        self._hit_index = -1

        self.theme_name = self.settings.value("ui/theme", "day")
        self.font_family = self.settings.value("ui/font_family", "")
        self.font_size = float(self.settings.value("ui/font_size", 12))
        self.line_width_em = float(self.settings.value("ui/line_width_em", 34))
        self.autosave_minutes = int(self.settings.value("ui/autosave_minutes", 5))
        self.line_spacing = float(self.settings.value("ui/line_spacing", 1.35))
        self._loaded_sig = None
        self._doc_meta = {}
        self.rep_window = None
        self.file_mode = False

        self._syncing = False
        self._sync_source = None
        self._confirming = False

        self._build_ui()

        # Tiap editor memakai dokumennya sendiri. Jangan pakai setDocument():
        # di build Qt ini panggilan itu diabaikan dan isi dokumen hilang.
        self.doc.setDocumentMargin(6)
        self.doc_b.setDocumentMargin(6)
        self.md_hl = MarkdownHighlighter(self.doc, self.theme_name, self.font_size)
        self.md_hl_b = MarkdownHighlighter(self.doc_b, self.theme_name, self.font_size)
        self.search_hl = SearchHighlighter(self.doc, self.theme_name)
        self.search_hl_b = SearchHighlighter(self.doc_b, self.theme_name)
        formatted = self.settings.value("ui/editor_mode", "formatted") == "formatted"
        self.md_hl.set_enabled(formatted)
        self.md_hl_b.set_enabled(formatted)

        self._build_timers()
        self._build_actions()
        self._build_menus()
        self._apply_theme(self.theme_name)
        self._apply_typography()
        self._wire()

        self._apply_start_geometry()
        self.setWindowTitle("Ketikaketik")
        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))
        self._restore_layout()
        self._restore_session()
        self._update_stats()
        self._refresh_previews()

    @property
    def doc(self):
        return self.pane_a.editor.document()

    @property
    def doc_b(self):
        return self.pane_b.editor.document()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.search = SearchBar(central)
        self.search.word.setChecked(
            self.settings.value("search/whole_word", True, type=bool))
        self.search.case.setChecked(
            self.settings.value("search/match_case", False, type=bool))
        self.search.word.toggled.connect(
            lambda v: self.settings.setValue("search/whole_word", bool(v)))
        self.search.case.toggled.connect(
            lambda v: self.settings.setValue("search/match_case", bool(v)))
        outer.addWidget(self.search)

        body = QWidget(central)
        lay = QHBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        side = QWidget(body)
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(8, 8, 8, 8)
        side_lay.setSpacing(6)
        self.chapter_label = QLabel("CHAPTERS", side)
        self.chapter_list = QListWidget(side)
        self.chapter_list.setAlternatingRowColors(False)
        self.outline_label = QLabel("OUTLINE", side)
        self.outline = Outline(side)
        for lbl in (self.chapter_label, self.outline_label):
            f = lbl.font()
            f.setPointSizeF(max(7.5, f.pointSizeF() - 1.5))
            f.setLetterSpacing(QFont.PercentageSpacing, 118)
            lbl.setFont(f)

        chapters_box = QWidget(side)
        self.chapters_box = chapters_box
        chapters_lay = QVBoxLayout(chapters_box)
        chapters_lay.setContentsMargins(0, 0, 0, 0)
        chapters_lay.setSpacing(4)
        chapters_lay.addWidget(self.chapter_label)
        chapters_lay.addWidget(self.chapter_list, 1)

        outline_box = QWidget(side)
        outline_lay = QVBoxLayout(outline_box)
        outline_lay.setContentsMargins(0, 0, 0, 0)
        outline_lay.setSpacing(4)
        outline_lay.addWidget(self.outline_label)
        outline_lay.addWidget(self.outline, 1)

        inner = QSplitter(Qt.Vertical, side)
        inner.addWidget(chapters_box)
        inner.addWidget(outline_box)
        inner.setSizes([300, 420])
        side_lay.addWidget(inner, 1)
        side.setMinimumWidth(170)
        side.setMaximumWidth(430)

        self.splitter = QSplitter(Qt.Horizontal, body)
        self.splitter.setHandleWidth(8)          # mudah digeser dengan mouse
        self.splitter.setChildrenCollapsible(False)
        self.pane_a = Pane(self.splitter)
        self.pane_b = Pane(self.splitter)
        for pane in (self.pane_a, self.pane_b):
            pane.setMinimumWidth(140)            # tidak bisa menyusut jadi tak terpakai
        self.splitter.addWidget(self.pane_a)
        self.splitter.addWidget(self.pane_b)
        self.splitter.setSizes([620, 560])
        split_on = self.settings.value("ui/split", True, type=bool)
        self.pane_b.setVisible(split_on)

        lay.addWidget(side)
        lay.addWidget(self.splitter, 1)
        outer.addWidget(body, 1)

        self.issues_panel = QWidget(central)
        panel_lay = QVBoxLayout(self.issues_panel)
        panel_lay.setContentsMargins(10, 6, 10, 8)
        panel_lay.setSpacing(4)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        self.issues_title = QLabel("MARKDOWN ISSUES", self.issues_panel)
        self.issues_hint = QLabel("Click an issue to jump to its line.", self.issues_panel)
        f = self.issues_title.font()
        f.setPointSizeF(max(7.5, f.pointSizeF() - 1.5))
        f.setLetterSpacing(QFont.PercentageSpacing, 118)
        self.issues_title.setFont(f)
        close_btn = QToolButton(self.issues_panel)
        close_btn.setText("✕")
        close_btn.setAutoRaise(True)
        close_btn.setToolTip("Hide (F7)")
        close_btn.clicked.connect(self.toggle_lint_panel)
        head.addWidget(self.issues_title)
        head.addSpacing(10)
        head.addWidget(self.issues_hint)
        head.addStretch(1)
        head.addWidget(close_btn)

        self.issue_list = QListWidget(self.issues_panel)
        self.issue_list.setMaximumHeight(140)
        self.issue_list.setMinimumHeight(70)
        self.issue_list.itemClicked.connect(self._jump_to_issue)
        panel_lay.addLayout(head)
        panel_lay.addWidget(self.issue_list)
        self.issues_panel.setVisible(False)
        outer.addWidget(self.issues_panel)

        self.setCentralWidget(central)

        self.confirm = ConfirmOverlay(self)

        bar = self.statusBar()
        self.lbl_stats = QLabel("0 words")
        self.lbl_session = QLabel("session +0 words")
        self.btn_lint = QToolButton()
        self.btn_lint.setAutoRaise(True)
        self.btn_lint.setText("✓ no issues")
        self.btn_lint.setToolTip("Markdown check")
        self.lbl_cursor = QLabel("Ln 1, Col 1")
        self.lbl_cursor.setToolTip("Cursor position")
        bar.addPermanentWidget(self.lbl_cursor)
        bar.addPermanentWidget(self.lbl_stats)
        bar.addPermanentWidget(self.lbl_session)
        bar.addPermanentWidget(self.btn_lint)

    # ------------------------------------------------------------- actions
    def _act(self, text, slot, shortcut=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if checkable:
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        return a

    def _build_actions(self):
        self.act_new_project = self._act("New Project…", self.new_project, "Ctrl+Shift+N")
        self.act_open_file = self._act("Open File…", self.choose_file, "Ctrl+O")
        self.act_open_project = self._act("Open Project Folder…", self.choose_project,
                                          "Ctrl+Shift+O")
        self.act_rescan = self._act("Rescan Folder", self.rescan_project, "F5")
        self.act_new_chapter = self._act("New Chapter…", self.new_chapter, "Ctrl+N")
        self.act_sample = self._act("New Chapter from Sample Text", self.load_sample_chapter)
        self.act_recent = self._act("Manage Recent Projects…", self.manage_recent)
        self.act_rename_chapter = self._act("Rename Chapter…", self.rename_chapter)
        self.act_delete_chapter = self._act("Delete Chapter (move to .history)",
                                            self.delete_chapter)
        self.act_hide_chapter = self._act("Remove from Project (keep file)",
                                          self.hide_current_chapter)
        self.act_hidden = self._act("Hidden Chapters…", self.manage_hidden)
        self.act_save = self._act("Save", self.save, "Ctrl+S")
        self.act_save_as = self._act("Save As…", lambda: self.save(force_as=True),
                                     "Ctrl+Shift+S")
        self.act_export = self._act("Export to .docx…", self.export_docx, "Ctrl+E")
        self.act_quit = self._act("Quit", self.close, "Ctrl+Q")

        self.act_find = self._act("Find…", lambda: self.open_search(False), "Ctrl+F")
        self.act_replace = self._act("Find && Replace…", lambda: self.open_search(True), "Ctrl+H")
        self.act_find_project = self._act("Find in Project…", self.find_in_project,
                                          "Ctrl+Shift+F")
        self.act_find_next = self._act("Next", lambda: self.find_next(1), "F3")
        self.act_find_prev = self._act("Previous", lambda: self.find_next(-1), "Shift+F3")

        self.act_reflow = self._act("Reflow Paragraphs", self.do_reflow, "Ctrl+Shift+J")
        self.act_theme = self._act("Toggle Theme", self.toggle_theme, "Ctrl+D")

        self.act_split = self._act("Split View", self.toggle_split, "Ctrl+\\", checkable=True)
        self.act_split.setChecked(self.settings.value("ui/split", True, type=bool))

        self.act_mode_raw = self._act("Raw", lambda on: on and self.set_editor_mode("raw"),
                                      checkable=True)
        self.act_mode_fmt = self._act("Formatted source",
                                      lambda on: on and self.set_editor_mode("formatted"),
                                      checkable=True)
        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)
        mode_group.addAction(self.act_mode_raw)
        mode_group.addAction(self.act_mode_fmt)
        current_mode = self.settings.value("ui/editor_mode", "formatted")
        (self.act_mode_fmt if current_mode == "formatted" else self.act_mode_raw).setChecked(True)
        self.mode_group = mode_group

        self.act_left_editor = self._act("Left: Editor", lambda on: on and self.set_pane_mode(0, "editor"),
                                         checkable=True)
        self.act_left_preview = self._act("Left: Preview", lambda on: on and self.set_pane_mode(0, "preview"),
                                          checkable=True)
        self.act_right_editor = self._act("Right: Editor", lambda on: on and self.set_pane_mode(1, "editor"),
                                          checkable=True)
        self.act_right_preview = self._act("Right: Preview", lambda on: on and self.set_pane_mode(1, "preview"),
                                           checkable=True)
        self.pane_group_left = QActionGroup(self)
        self.pane_group_left.setExclusive(True)
        self.pane_group_left.addAction(self.act_left_editor)
        self.pane_group_left.addAction(self.act_left_preview)
        self.pane_group_right = QActionGroup(self)
        self.pane_group_right.setExclusive(True)
        self.pane_group_right.addAction(self.act_right_editor)
        self.pane_group_right.addAction(self.act_right_preview)

        right_preview_default = self.settings.value("ui/pane_b", "preview")
        self.act_right_preview.setChecked(right_preview_default == "preview")
        self.act_right_editor.setChecked(right_preview_default != "preview")
        self.pane_b.set_mode(right_preview_default)
        self.pane_a.set_mode("editor")
        self.act_left_editor.setChecked(True)

        self.act_reset_size = self._act("Reset Window Size", self._apply_start_geometry)
        self.act_font = self._act("Font…", self.choose_font)
        self.act_lint = self._act("Markdown Issues", self.toggle_lint_panel, "F7")
        self.act_repetition = self._act("Repetition…", self.open_repetition, "Ctrl+Shift+R")
        self.act_about = self._act("About Ketikaketik", self.about)

    def _build_menus(self):
        bar = self.menuBar()

        m_file = bar.addMenu("&File")
        m_file.addAction(self.act_new_project)
        m_file.addAction(self.act_open_file)
        m_file.addAction(self.act_open_project)
        m_file.addAction(self.act_rescan)
        self.recent_files_menu = m_file.addMenu("Recent Files")
        self.refresh_recent_files_menu()
        self.recent_menu = m_file.addMenu("Recent Projects")
        self.refresh_recent_menu()
        m_file.addSeparator()
        m_file.addAction(self.act_new_chapter)
        m_file.addAction(self.act_sample)
        m_file.addAction(self.act_rename_chapter)
        m_file.addAction(self.act_hide_chapter)
        m_file.addAction(self.act_delete_chapter)
        m_file.addAction(self.act_hidden)
        m_file.addSeparator()
        m_file.addAction(self.act_save)
        m_file.addAction(self.act_save_as)
        m_file.addAction(self.act_export)
        m_file.addSeparator()
        m_file.addAction(self.act_quit)

        m_edit = bar.addMenu("&Edit")
        self.act_undo = self._act("Undo", lambda: self._active_editor().undo(), "Ctrl+Z")
        self.act_redo = self._act("Redo", lambda: self._active_editor().redo(), "Ctrl+Shift+Z")
        m_edit.addAction(self.act_undo)
        m_edit.addAction(self.act_redo)
        m_edit.addSeparator()
        for text, slot, key in (
            ("Cut", "cut", "Ctrl+X"),
            ("Copy", "copy", "Ctrl+C"),
            ("Paste", "paste", "Ctrl+V"),
            ("Select All", "selectAll", "Ctrl+A"),
        ):
            a = QAction(text, self)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(lambda _c=False, s=slot: getattr(self._active_editor(), s)())
            m_edit.addAction(a)
        m_edit.addSeparator()
        m_edit.addAction(self.act_find)
        m_edit.addAction(self.act_replace)
        m_edit.addAction(self.act_find_next)
        m_edit.addAction(self.act_find_prev)
        m_edit.addAction(self.act_find_project)
        m_edit.addSeparator()
        m_edit.addAction(self.act_reflow)

        m_view = bar.addMenu("&View")
        m_theme = m_view.addMenu("Theme")
        self.act_theme_day = self._act("Day (cream)", lambda on: on and self.set_theme("day"),
                                       checkable=True)
        self.act_theme_night = self._act("Night (warm dark)",
                                         lambda on: on and self.set_theme("night"),
                                         checkable=True)
        tg = QActionGroup(self)
        tg.setExclusive(True)
        tg.addAction(self.act_theme_day)
        tg.addAction(self.act_theme_night)
        (self.act_theme_night if self.theme_name == "night" else self.act_theme_day).setChecked(True)
        m_theme.addAction(self.act_theme_day)
        m_theme.addAction(self.act_theme_night)
        m_view.addSeparator()
        m_mode = m_view.addMenu("Editor mode")
        m_mode.addAction(self.act_mode_raw)
        m_mode.addAction(self.act_mode_fmt)
        m_panes = m_view.addMenu("Panes")
        m_panes.addAction(self.act_left_editor)
        m_panes.addAction(self.act_left_preview)
        m_panes.addSeparator()
        m_panes.addAction(self.act_right_editor)
        m_panes.addAction(self.act_right_preview)
        m_view.addAction(self.act_split)
        m_view.addSeparator()
        m_view.addAction(self.act_reset_size)
        m_view.addAction(self.act_font)
        self.width_menu = m_view.addMenu("Line width")
        self.width_group = QActionGroup(self)
        self.width_group.setExclusive(True)
        for label, em in (("Unlimited", 0), ("Narrow (28em)", 28), ("Comfortable (34em)", 34),
                          ("Roomy (40em)", 40), ("Wide (46em)", 46), ("Full (60em)", 60)):
            a = self._act(label, lambda _c=False, v=em: self.set_line_width(v), checkable=True)
            a.setChecked(abs(self.line_width_em - em) < 0.01)
            self.width_group.addAction(a)
            self.width_menu.addAction(a)
        self.width_menu.addAction(self._act("Custom…", self.ask_line_width))
        self.autosave_menu = m_view.addMenu("Autosave")
        self.autosave_group = QActionGroup(self)
        self.autosave_group.setExclusive(True)
        for minutes in (3, 5, 10):
            choice = self._act(f"Every {minutes} minutes",
                               lambda on, m=minutes: on and self.set_autosave_interval(m),
                               checkable=True)
            choice.setChecked(minutes == self.autosave_minutes)
            self.autosave_group.addAction(choice)
            self.autosave_menu.addAction(choice)
        m_view.addSeparator()
        m_view.addAction(self.act_lint)
        m_view.addAction(self.act_repetition)

        m_help = bar.addMenu("&Help")
        m_help.addAction(self.act_about)

    def _build_timers(self):
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(self.autosave_minutes * 60_000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(PREVIEW_MS)
        self.preview_timer.timeout.connect(self._refresh_previews)

        self.sync_timer = QTimer(self)
        self.sync_timer.setSingleShot(True)
        self.sync_timer.setInterval(220)
        self.sync_timer.timeout.connect(self._sync_documents)

        self.rep_section_timer = QTimer(self)
        self.rep_section_timer.setSingleShot(True)
        self.rep_section_timer.setInterval(400)
        self.rep_section_timer.timeout.connect(self._check_section_follow)

        self.rep_timer = QTimer(self)
        self.rep_timer.setSingleShot(True)
        self.rep_timer.setInterval(1500)
        self.rep_timer.timeout.connect(self._refresh_repetition)

        self.lint_timer = QTimer(self)
        self.lint_timer.setSingleShot(True)
        self.lint_timer.setInterval(600)
        self.lint_timer.timeout.connect(self._refresh_lint_if_visible)

        self.journal_timer = QTimer(self)
        self.journal_timer.setInterval(8000)
        self.journal_timer.timeout.connect(self._write_journal_if_dirty)
        self.journal_timer.start()

        self.stats_timer = QTimer(self)
        self.stats_timer.setSingleShot(True)
        self.stats_timer.setInterval(STATS_MS)
        self.stats_timer.timeout.connect(self._update_stats)

    def _wire(self):
        self.doc.contentsChanged.connect(self._on_contents)
        self.doc_b.contentsChanged.connect(self._on_contents)
        self.doc.modificationChanged.connect(self._on_modified_changed)
        self.chapter_list.currentItemChanged.connect(self._on_chapter_selected)
        self.chapter_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chapter_list.customContextMenuRequested.connect(self._chapter_menu)
        self.outline.goto.connect(self._goto_chapter_line)
        self.search.changed.connect(self._search_changed)
        self.search.navigate.connect(self.find_next)
        self.search.replaceOne.connect(self.replace_one)
        self.search.replaceAll.connect(self.replace_all)
        self.search.closed.connect(self.close_search)
        self.btn_lint.clicked.connect(self.toggle_lint_panel)
        for pane in (self.pane_a, self.pane_b):
            pane.editor.verticalScrollBar().valueChanged.connect(self._sync_scroll)
            pane.editor.cursorPositionChanged.connect(self._update_cursor_label)
            pane.editor.textChanged.connect(
                lambda e=pane.editor: self._on_editor_changed(e))

    # --------------------------------------------------------------- tema
    def _apply_theme(self, name):
        self.theme_name = name
        apply_theme(QApplication.instance(), name)
        for hl in (self.md_hl, self.md_hl_b, self.search_hl, self.search_hl_b):
            hl.set_theme(name)
        c = colors(name)
        self.chapter_label.setStyleSheet(f"color: {c['dim']};")
        self.outline_label.setStyleSheet(f"color: {c['dim']};")
        self.confirm.set_colors(c)
        self.issues_title.setStyleSheet(f"color: {c['dim']};")
        self.issues_hint.setStyleSheet(f"color: {c['dim']};")
        for pane in (self.pane_a, self.pane_b):
            pane.preview.setStyleSheet(f"QTextBrowser {{ background: {c['base']}; border: none; }}")
            pane.editor.set_flash_color(c["flash"])
        self.settings.setValue("ui/theme", name)
        self._refresh_previews()

    def set_theme(self, name):
        self._apply_theme(name)
        (self.act_theme_night if name == "night" else self.act_theme_day).setChecked(True)

    def toggle_theme(self):
        self.set_theme("night" if self.theme_name == "day" else "day")

    # ----------------------------------------------------------- tipografi
    def _apply_typography(self, persist: bool = True):
        font = QFont(self.font_family) if self.font_family else QFont()
        if not self.font_family:
            font.setFamily(self.settings.value("ui/default_family", font.family()))
        font.setPointSizeF(self.font_size)
        font.setStyleStrategy(QFont.PreferAntialias)
        for pane in (self.pane_a, self.pane_b):
            pane.editor.apply_typography(font, self.line_width_em)
            pane.preview.apply_typography(font, self.line_width_em)
        self.md_hl.set_base_point(self.font_size)
        self.md_hl_b.set_base_point(self.font_size)
        self._apply_line_spacing(self.doc)
        self._apply_line_spacing(self.doc_b)
        if persist:
            self.settings.setValue("ui/font_family", self.font_family)
            self.settings.setValue("ui/font_size", self.font_size)
            self.settings.setValue("ui/line_width_em", self.line_width_em)
            self.settings.setValue("ui/line_spacing", self.line_spacing)

    def _apply_line_spacing(self, document):
        """Jarak baris disimpan di blok teks, bukan di widget."""
        if abs(float(document.property("ktktSpacing") or 0.0) - self.line_spacing) < 1e-6:
            return
        was_modified = document.isModified()
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        block_format = QTextBlockFormat()
        proportional = QTextBlockFormat.ProportionalHeight
        proportional = getattr(proportional, "value", proportional)
        block_format.setLineHeight(float(self.line_spacing * 100), proportional)
        cursor.mergeBlockFormat(block_format)
        cursor.endEditBlock()
        document.setProperty("ktktSpacing", self.line_spacing)
        document.setModified(was_modified)

    def _preview_font(self, family: str, size: float, spacing=None):
        """Terapkan sementara, jangan simpan dulu -- supaya Cancel bisa kembali."""
        self.font_family = family
        self.font_size = max(6.0, float(size))
        if spacing is not None:
            self.line_spacing = max(1.0, min(2.6, float(spacing)))
        self._apply_typography(persist=False)

    def choose_font(self):
        original = (self.font_family, self.font_size, self.line_spacing)
        chooser = FontChooser(self.font_family, self.font_size, self.line_spacing, self)
        chooser.changed.connect(self._preview_font)
        self.confirm.build(
            "Editor font",
            "Changes apply to the manuscript immediately. Cancel restores the previous font.",
            [("ok", "OK", "primary"), ("cancel", "Cancel", "")],
            content=chooser, dim=False, placement="bottom")
        # pratinjau awal, supaya naskah sudah memakai font yang sedang terpilih
        self._preview_font(chooser.family(), chooser.size(), chooser.line_spacing())
        choice = self.confirm.run()
        if choice == "ok":
            self._preview_font(chooser.family(), chooser.size(), chooser.line_spacing())
            self._apply_typography()          # simpan permanen
            self.statusBar().showMessage(
                f"Font: {chooser.family()} {chooser.size():.0f} pt, "
                f"spacing {chooser.line_spacing():.2f}", 3000)
        else:
            self.font_family, self.font_size, self.line_spacing = original
            self._apply_typography(persist=False)

    def set_line_width(self, em):
        self.line_width_em = float(em)
        self._apply_typography()

    def set_autosave_interval(self, minutes: int):
        self.autosave_minutes = int(minutes)
        self.autosave_timer.setInterval(self.autosave_minutes * 60_000)
        self.settings.setValue("ui/autosave_minutes", self.autosave_minutes)
        self.statusBar().showMessage(
            f"Autosave every {self.autosave_minutes} minutes", 2500)

    def ask_line_width(self):
        value, ok = QInputDialog.getDouble(
            self, "Line width", "Text column width (em, 0 = unlimited):",
            self.line_width_em, 0, 120, 1)
        if ok:
            self.set_line_width(value)

    def set_editor_mode(self, mode):
        self.md_hl.set_enabled(mode == "formatted")
        self.md_hl_b.set_enabled(mode == "formatted")
        self.settings.setValue("ui/editor_mode", mode)
        (self.act_mode_fmt if mode == "formatted" else self.act_mode_raw).setChecked(True)

    def set_pane_mode(self, index, mode):
        pane = self.pane_a if index == 0 else self.pane_b
        pane.set_mode(mode)
        if index == 1:
            self.settings.setValue("ui/pane_b", mode)
            if mode == "preview":
                self._refresh_previews()
            else:
                self._sync_documents(force=True)
                pane.editor.setFocus()
        else:
            if mode == "preview":
                self._refresh_previews()
            else:
                pane.editor.setFocus()

    def toggle_split(self, on):
        self.pane_b.setVisible(on)
        self.settings.setValue("ui/split", on)
        if on:
            self.splitter.setSizes([620, 560])

    # ------------------------------------------------------------ proyek
    def new_project(self):
        root = QFileDialog.getExistingDirectory(self, "Choose a folder for the new project")
        if not root:
            return
        self.open_project(Path(root), offer_chapter=True)

    def choose_project(self):
        root = QFileDialog.getExistingDirectory(self, "Open project folder")
        if root:
            self.open_project(Path(root))

    def choose_file(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, "Open file", str(Path.home()),
            "Markdown (*.md *.markdown);;Text (*.txt);;All files (*)")
        if path:
            self.open_document(Path(path))

    def open_document(self, path, remember=True):
        """Mode file klasik: satu naskah, tanpa daftar bab."""
        path = Path(path).expanduser().resolve()
        if not path.is_file():
            QMessageBox.warning(self, "Ketikaketik", f"File not found:\n{path}")
            return
        if self.current_path and Path(self.current_path) == path:
            self._active_editor().setFocus()
            return
        if not self._save_if_dirty():
            return

        if self.project is None or self.project.root != path.parent:
            if self.project is not None:
                self.project.release_lock()
            self.project = Project(path.parent)
            self.project.acquire_lock()          # best effort, tanpa dialog
        self.project.scan()

        self.file_mode = True
        self.settings.setValue("session/mode", "file")
        self.settings.setValue("session/file", str(path))
        self.chapters_box.setVisible(False)
        self._fill_chapters()
        self._open_chapter(path)
        if remember:
            add_recent_file(path)
            self.refresh_recent_files_menu()

    def rescan_project(self, silent=False):
        """Baca ulang isi folder: file baru yang kamu tambahkan langsung muncul."""
        if self.project is None or self.file_mode:
            return
        if not self.project.root.is_dir():
            # folder dipindah atau diubah namanya di luar aplikasi
            self.statusBar().showMessage(
                f"Folder is gone: {self.project.root} — renamed or moved? "
                "Use File → Recent Projects.", 0)
            return
        before = [str(item) for item in self.project.chapters]
        self.project.scan()
        after = [str(item) for item in self.project.chapters]
        self._fill_chapters(self.current_path)
        self._rebuild_outline(self.current_path)
        if not silent or before != after:
            self.statusBar().showMessage(
                f"{len(after)} chapter{'s' if len(after) != 1 else ''} in {self.project.name}",
                4000)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowActivate and not self.file_mode:
            self.rescan_project(silent=True)

    def refresh_recent_files_menu(self):
        menu = getattr(self, "recent_files_menu", None)
        if menu is None:
            return
        menu.clear()
        files = load_recent_files()
        if not files:
            action = menu.addAction("(none)")
            action.setEnabled(False)
            return
        for item in files:
            path = Path(item)
            action = menu.addAction(f"{path.name}  —  {path.parent}")
            action.triggered.connect(lambda _checked=False, p=path: self.open_document(p))

    def open_project(self, root, offer_chapter=False, load_first=True):
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            QMessageBox.warning(self, "Ketikaketik", f"Folder not found:\n{root}")
            return
        if not self._save_if_dirty():
            return
        candidate = Project(root)
        if not candidate.acquire_lock():
            choice = self.confirm.ask(
                "Project already open",
                "Another Ketikaketik window appears to have this project open.\n\n"
                "Two windows writing the same files can overwrite each other.",
                [("continue", "Open anyway", "destructive"),
                 ("cancel", "Cancel", "primary")])
            if choice != "continue":
                return                    # proyek lama tetap seperti apa adanya
        if self.project is not None:
            self.project.release_lock()
        self.project = candidate
        self.file_mode = False
        self.settings.setValue("session/mode", "project")
        self.settings.setValue("session/project", str(root))
        self.chapters_box.setVisible(True)
        add_recent(root)
        self.refresh_recent_menu()
        self.project.scan()
        self.current_path = None
        self.session_base = None     # hitungan "sesi" mulai ulang per proyek
        self._fill_chapters()
        self._rebuild_outline(None)
        self.setWindowTitle(f"Ketikaketik — {self.project.name}")

        chapters = self.project.chapters
        if offer_chapter and not chapters:
            self.new_chapter()
            return
        if not load_first:
            return
        if chapters:
            wanted = self.settings.value("session/file", "")
            target = next((c for c in chapters if str(c) == wanted), chapters[0])
            self._select_chapter_item(target)
            self._open_chapter(target)
        else:
            self.new_chapter()

    def refresh_recent_menu(self):
        self.recent_menu.clear()
        items = load_recent()
        if not items:
            a = self.recent_menu.addAction("(none)")
            a.setEnabled(False)
            return
        for path in items:
            a = self.recent_menu.addAction(Path(path).name + f"  —  {path}")
            a.triggered.connect(lambda _c=False, p=path: self.open_project(p))
        self.recent_menu.addSeparator()
        self.recent_menu.addAction(self.act_recent)

    def new_chapter(self):
        if not self._ensure_project():
            return
        title, ok = QInputDialog.getText(self, "New chapter", "Chapter title:")
        if not ok or not title.strip():
            return
        path = self.project.create_chapter(title.strip())
        if self.file_mode:
            # menambah bab berarti kembali ke mode folder
            self.file_mode = False
            self.settings.setValue("session/mode", "project")
            self.chapters_box.setVisible(True)
        self.project.scan()
        self._fill_chapters(path)
        self._open_chapter(path)
        self._rebuild_outline(path)

    def load_sample_chapter(self):
        if not self._ensure_project():
            return
        path = self.project.create_chapter(SAMPLE_TITLE)
        body, _changed = reflow_paragraphs(SAMPLE_TEXT)
        self.project.save(path, body)
        self.project.scan()
        self._fill_chapters(path)
        self._open_chapter(path)
        self._rebuild_outline(path)
        if not self.issues_panel.isVisibleTo(self):
            self.toggle_lint_panel()
        self.statusBar().showMessage(
            "Sample text loaded. The two markdown issues it contains are intentional.",
            7000)

    def _center_on_window(self, widget):
        """Qt membiarkan window manager menaruh dialog di mana saja; kita paksa
        di tengah jendela induk."""
        widget.adjustSize()
        frame = self.frameGeometry()
        widget.move(frame.center() - widget.rect().center())

    def _pick_dialog(self, title, hint, items, action_text, extra_items=()):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(500, 330)
        lay = QVBoxLayout(dialog)
        caption = QLabel(hint, dialog)
        caption.setWordWrap(True)
        lay.addWidget(caption)
        listing = QListWidget(dialog)
        for label in list(items) + list(extra_items):
            listing.addItem(label)
        lay.addWidget(listing, 1)
        row = QHBoxLayout()
        act_btn = QPushButton(action_text, dialog)
        close_btn = QPushButton("Close", dialog)
        row.addStretch(1)
        row.addWidget(act_btn)
        row.addWidget(close_btn)
        lay.addLayout(row)
        chosen = {}
        act_btn.clicked.connect(
            lambda: (chosen.update(items=[i.text() for i in listing.selectedItems()]),
                     dialog.accept()))
        close_btn.clicked.connect(dialog.reject)
        self._center_on_window(dialog)
        dialog.exec()
        return chosen.get("items", [])

    def hide_current_chapter(self):
        if not self.current_path:
            return
        self._hide_path(Path(self.current_path))

    def _hide_path(self, path):
        if self.project is None:
            return
        path = Path(path)
        is_open = self.current_path is not None and Path(self.current_path) == path
        self.project.hide_chapter(path)
        if is_open:
            self.current_path = None
            self._fill_chapters()
            if self.project.chapters:
                self._open_chapter(self.project.chapters[0])
            else:
                self._load_text("")
                self.setWindowTitle(f"Ketikaketik — {self.project.name}")
        else:
            self._fill_chapters(self.current_path)
        self._rebuild_outline(self.current_path)
        self.statusBar().showMessage(
            f"{path.name} removed from the project. The file is untouched; "
            "restore it from File → Hidden Chapters.", 7000)

    def _chapter_menu(self, pos):
        item = self.chapter_list.itemAt(pos)
        if item is None:
            return
        path = Path(item.data(Qt.UserRole))
        menu = QMenu(self)
        menu.addAction("Open", lambda: self._open_chapter(path))
        menu.addSeparator()
        menu.addAction("Remove from Project (keep file)", lambda: self._hide_path(path))
        if self.current_path and Path(self.current_path) == path:
            menu.addAction("Rename Chapter…", self.rename_chapter)
            menu.addAction("Delete Chapter (move to .history)", self.delete_chapter)
        menu.exec(self.chapter_list.mapToGlobal(pos))

    def manage_hidden(self):
        if self.project is None:
            return
        hidden = self.project.hidden_chapters()
        if not hidden:
            QMessageBox.information(
                self, "Hidden Chapters",
                "No chapters are hidden from this project.\n\n"
                "Use File → Remove from Project (keep file) to hide one without "
                "touching the file.")
            return
        picks = self._pick_dialog(
            "Hidden Chapters",
            "These files are still on disk but hidden from the chapter list and outline. "
            "Select one or more to bring them back into the project.",
            [p.name for p in hidden], "Restore Selected")
        if not picks:
            return
        for name in picks:
            self.project.restore_chapter(name)
        self._fill_chapters(self.current_path)
        self._rebuild_outline(self.current_path)
        self.statusBar().showMessage(f"Restored {len(picks)} chapter(s).", 5000)

    def manage_recent(self):
        items = load_recent()
        if not items:
            QMessageBox.information(self, "Recent Projects", "The recent list is empty.")
            return
        picks = self._pick_dialog(
            "Recent Projects",
            "Select a project to remove from the recent list. Nothing on disk is "
            "changed or deleted.",
            items, "Remove Selected")
        for path in picks:
            remove_recent(path)
        self.refresh_recent_menu()
        if picks:
            self.statusBar().showMessage(f"Removed {len(picks)} entry from the recent list.",
                                         5000)

    def rename_chapter(self):
        if not self.current_path:
            return
        new, ok = QInputDialog.getText(self, "Rename chapter", "File name:",
                                       text=self.current_path.name)
        if not ok or not new.strip():
            return
        try:
            path = self.project.rename_chapter(self.current_path, new.strip())
        except (OSError, FileExistsError) as exc:
            QMessageBox.warning(self, "Ketikaketik", f"Rename failed:\n{exc}")
            return
        self.current_path = path
        self._fill_chapters(path)
        self._rebuild_outline(path)

    def delete_chapter(self):
        if not self.current_path:
            return
        choice = self.confirm.ask(
            "Delete chapter?",
            f"Delete '{self.current_path.name}'?\n\n"
            "The file is moved to .history/deleted, not erased.",
            [("delete", "Delete", "destructive"), ("cancel", "Cancel", "primary")])
        if choice != "delete":
            return
        self.project.delete_chapter(self.current_path)
        self.current_path = None
        self._fill_chapters()
        self._rebuild_outline(None)
        if self.project.chapters:
            self._open_chapter(self.project.chapters[0])
        else:
            self._load_text("")

    def _ensure_project(self):
        if self.project is not None:
            return True
        root = QFileDialog.getExistingDirectory(self, "Choose project folder")
        if not root:
            return False
        self.open_project(Path(root), load_first=False)
        return self.project is not None

    # ------------------------------------------------------------- bab
    def _fill_chapters(self, select_path=None):
        self._selecting = True
        self.chapter_list.clear()
        if self.project:
            for chapter in self.project.chapters:
                item = QListWidgetItem(chapter.stem)
                item.setData(Qt.UserRole, str(chapter))
                item.setToolTip(chapter.name)
                self.chapter_list.addItem(item)
        self._selecting = False
        if select_path:
            self._select_chapter_item(select_path)

    def _select_chapter_item(self, path):
        target = str(Path(path))
        for i in range(self.chapter_list.count()):
            item = self.chapter_list.item(i)
            if item.data(Qt.UserRole) == target:
                self._selecting = True
                self.chapter_list.setCurrentItem(item)
                self._selecting = False
                return

    def _on_chapter_selected(self, item, _prev):
        if self._selecting or item is None:
            return
        self._open_chapter(Path(item.data(Qt.UserRole)))

    def _load_text(self, text):
        self._loading = True
        self.doc.setPlainText(text)
        self.doc_b.setPlainText(text)
        for document in (self.doc, self.doc_b):
            document.setProperty("ktktSpacing", 0.0)
            self._apply_line_spacing(document)
        self._mark_saved()
        self._loading = False
        self._update_stats()
        self._refresh_previews()

    def _open_chapter(self, path):
        path = Path(path)
        if self.current_path and path == self.current_path:
            return
        if self.current_path:
            if self.doc.isModified() and not self._save_if_dirty():
                return
            self.cursor_cache[str(self.current_path)] = self._active_editor().textCursor().position()
        try:
            if self.project:
                text, meta = self.project.read_with_meta(path)
            else:
                text, meta = path.read_text(encoding="utf-8"), {}
        except OSError as exc:
            QMessageBox.warning(self, "Ketikaketik", f"Could not read {path.name}:\n{exc}")
            return
        self._doc_meta = meta

        restored = False
        if self.project:
            record = read_journal(self.project.root, path)
            if record and record.get("text") != text:
                import time as _time
                when = _time.strftime("%d %b %H:%M", _time.localtime(record.get("saved_at", 0)))
                choice = self.confirm.ask(
                    "Unsaved work found",
                    f"A recovery copy of '{path.name}' from {when} has text that is not on disk.\n\n"
                    "Restore that text, or discard it and keep the file as it is?",
                    [("restore", "Restore", "primary"), ("discard", "Discard", "")])
                if choice == "restore":
                    text = record["text"]
                    restored = True
                else:
                    clear_journal(self.project.root, path)
        if meta.get("readonly"):
            self.statusBar().showMessage(
                f"{path.name} is not valid UTF-8 — opened read-only so its bytes stay safe.", 0)

        self._load_text(text)
        if restored:
            self.doc.setModified(True)
        self.current_path = path
        self._loaded_sig = self._disk_signature(path)
        self.settings.setValue("session/file", str(path))
        pos = self.cursor_cache.get(str(path), 0)
        for pane in (self.pane_a, self.pane_b):
            pane.editor.goto_position(pos)
        self._select_chapter_item(path)
        self._rebuild_outline(path)
        if self.file_mode:
            self.setWindowTitle(f"Ketikaketik — {path.name}")
        else:
            self.setWindowTitle(f"Ketikaketik — {self.project.name if self.project else ''}"
                                f" — {path.stem}")
        self._update_lint()
        if self.session_base is None:
            self.session_base = count_words(text)
        self._refresh_repetition()
        self._active_editor().setFocus()

    def _goto_chapter_line(self, path, line):
        path = Path(path)
        if self.current_path != path:
            self._open_chapter(path)
        self._active_editor().goto_line(int(line))

    # ------------------------------------------------------------- simpan
    def save(self, force_as=False):
        if not self._ensure_project():
            return
        if force_as or not self.current_path:
            suggestion = self.current_path or (self.project.root / f"{self.project.next_number():02d}-new-chapter.md")
            chosen, _ = QFileDialog.getSaveFileName(
                self, "Save chapter", str(suggestion), "Markdown (*.md)")
            if not chosen:
                return
            self.current_path = Path(chosen)
            self._doc_meta = {}
            self.project.scan()
            self._fill_chapters(self.current_path)
        if not force_as and self._changed_on_disk():
            choice = self.confirm.ask(
                "File changed on disk",
                f"'{self.current_path.name}' was changed by something else since you opened it.\n\n"
                "Overwrite it with what you see, or load the version from disk?",
                [("overwrite", "Overwrite", "destructive"),
                 ("reload", "Load from disk", "primary"),
                 ("cancel", "Cancel", "")])
            if choice in (None, "cancel"):
                return
            if choice == "reload":
                self._reload_current()
                return
        try:
            self.project.save(self.current_path, self._current_text(),
                              force_snapshot=self._changed_on_disk(),
                              meta=self._doc_meta)
        except PermissionError as exc:
            QMessageBox.warning(self, "Ketikaketik", str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(self, "Ketikaketik",
                                f"Save failed — your text is still here, nothing was lost:\n{exc}")
            return
        clear_journal(self.project.root, self.current_path)
        self._loaded_sig = self._disk_signature(self.current_path)
        self._mark_saved()
        self.settings.setValue("session/file", str(self.current_path))
        self._update_lint()
        self._rebuild_outline(self.current_path)
        self.statusBar().showMessage(f"Saved: {self.current_path.name}", 2500)
        self.refresh_recent_menu()

    def _disk_signature(self, path):
        try:
            stat = Path(path).stat()
            return (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None

    def _changed_on_disk(self) -> bool:
        """True kalau file di disk berubah sejak kita membacanya."""
        if not self.current_path or self._loaded_sig is None:
            return False
        current = self._disk_signature(self.current_path)
        return current is not None and current != self._loaded_sig

    def _is_modified(self) -> bool:
        return self.doc.isModified() or self.doc_b.isModified()

    def _mark_saved(self):
        self.doc.setModified(False)
        self.doc_b.setModified(False)

    def _save_if_dirty(self) -> bool:
        """Simpan bila perlu. False = gagal, dan pemanggil harus membatalkan aksinya."""
        if not (self.project and self.current_path and self._is_modified()):
            return True
        external = self._changed_on_disk()
        try:
            self.project.save(self.current_path, self._current_text(),
                              force_snapshot=external, meta=self._doc_meta)
        except OSError as exc:
            self.statusBar().showMessage(
                f"Could not save {self.current_path.name}: {exc}", 0)
            self._write_journal_if_dirty()
            return False
        clear_journal(self.project.root, self.current_path)
        self._loaded_sig = self._disk_signature(self.current_path)
        self._mark_saved()
        if external:
            self.statusBar().showMessage(
                "File had changed on disk; that version was kept in .history.", 7000)
        return True

    def _write_journal_if_dirty(self):
        if not (self.project and self.current_path and self._is_modified()):
            return
        try:
            write_journal(self.project.root, self.current_path, self._current_text())
        except OSError as exc:
            self.statusBar().showMessage(f"Recovery journal failed: {exc}", 6000)

    def autosave(self):
        if self.project and self.current_path and self._is_modified():
            if self._changed_on_disk():
                self.statusBar().showMessage(
                    "File changed on disk — autosave paused. Press Ctrl+S to decide.", 7000)
                return
            try:
                self.project.save(self.current_path, self._current_text(),
                                  meta=self._doc_meta)
                clear_journal(self.project.root, self.current_path)
                self._loaded_sig = self._disk_signature(self.current_path)
                self._mark_saved()
                self.statusBar().showMessage(
                    f"Autosaved at {time.strftime('%H:%M')}", 3000)
            except OSError as exc:
                self.statusBar().showMessage(f"Autosave failed: {exc}", 5000)

    def _on_modified_changed(self, modified):
        if self._selecting:
            return
        item = self.chapter_list.currentItem()
        if item:
            base = Path(item.data(Qt.UserRole)).stem
            item.setText(("● " if modified else "") + base)

    # -------------------------------------------------------------- cari
    def open_search(self, with_replace=False):
        cursor = self._active_editor().textCursor()
        if not with_replace and cursor.hasSelection():
            selected = cursor.selectedText().strip()
            if selected and "\n" not in selected and len(selected) < 200:
                self.search.query.setText(selected)
        self.search.focus_query(with_replace)
        self._search_changed()

    def close_search(self):
        self.search.setVisible(False)
        for hl in (self.search_hl, self.search_hl_b):
            hl.set_query("")
        self._hits = []
        self._hit_index = -1
        self._active_editor().setFocus()

    def _search_changed(self):
        query = self.search.text()
        invalid = False
        if query and self.search.use_regex():
            try:
                re.compile(query)
            except re.error:
                invalid = True
        if invalid:
            self.search_hl.set_query("")
            self._hits = []
            self.search.set_counter(0, 0, invalid=True)
            return
        whole_word = self.search.whole_word() and not self.search.use_regex()
        for hl in (self.search_hl, self.search_hl_b):
            hl.set_query(query, self.search.case_sensitive(),
                         self.search.use_regex(), whole_word)
        self._hits = self.search_hl.find_all(self._current_text())
        self._hit_index = -1
        self.search.set_counter(0, len(self._hits))
        if self._hits:
            self.find_next(1)

    def find_next(self, direction=1):
        editor = self._active_editor()
        self._hits = self.search_hl.find_all(editor.toPlainText())
        if not self._hits:
            self.search.set_counter(0, 0)
            return
        pos = editor.textCursor().position()
        if direction >= 0:
            nxt = next((h for h in self._hits if h > pos), self._hits[0])
        else:
            prev = [h for h in self._hits if h < pos]
            nxt = prev[-1] if prev else self._hits[-1]
        self._hit_index = self._hits.index(nxt)
        self._set_active_match(nxt)
        editor.goto_position(nxt, focus=False)
        self.search.set_counter(self._hit_index + 1, len(self._hits))

    def _match_spans(self, text):
        return self.search_hl.spans(text, cap=self.search_hl.MAX_TOTAL)

    def replace_one(self):
        query = self.search.text()
        if not query or not self._hits:
            return
        editor = self._active_editor()
        text = editor.toPlainText()
        spans = self._match_spans(text)
        if not spans:
            return
        pos = self._active_editor().textCursor().position()
        chosen = next(((s, e) for s, e in spans if s >= pos), spans[0])
        start, end = chosen
        if self.search.use_regex():
            try:
                pattern = re.compile(query, 0 if self.search.case_sensitive() else re.IGNORECASE)
                new_text = pattern.sub(self.search.replace_text(), text[start:end], count=1)
            except re.error:
                return
        else:
            new_text = self.search.replace_text()

        cursor = QTextCursor(editor.document())
        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(new_text)
        cursor.endEditBlock()
        cursor.setPosition(start + len(new_text))
        editor.setTextCursor(cursor)
        self._hits = self.search_hl.find_all(editor.toPlainText())
        self.search.set_counter(0, len(self._hits))
        self.find_next(1)

    def replace_all(self):
        query = self.search.text()
        if not query:
            return
        self._sync_documents(force=True)
        editor = self._active_editor()
        text = editor.toPlainText()
        flags = 0 if self.search.case_sensitive() else re.IGNORECASE
        try:
            if self.search.use_regex():
                pattern = re.compile(query, flags)
                new_text, n = pattern.subn(self.search.replace_text(), text)
            else:
                escaped = re.escape(query)
                if self.search.whole_word():
                    escaped = rf"(?<!\w){escaped}(?!\w)"
                pattern = re.compile(escaped, flags)
                new_text, n = pattern.subn(lambda _m: self.search.replace_text(), text)
        except re.error:
            QMessageBox.warning(self, "Ketikaketik", "Invalid regex.")
            return
        if not n:
            self.statusBar().showMessage("No matches.", 2500)
            return
        cursor = QTextCursor(editor.document())
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(new_text)
        cursor.endEditBlock()
        self.statusBar().showMessage(f"{n} replaced. Press Ctrl+Z to undo.", 4000)
        self._hits = self.search_hl.find_all(editor.toPlainText())
        self.search.set_counter(0, len(self._hits))

    def find_in_project(self):
        if not self._ensure_project():
            return
        dialog = ProjectSearchDialog(self.project, self)
        dialog.jump.connect(self._goto_chapter_line)
        self._center_on_window(dialog)
        dialog.exec()
        self._reload_current()

    def do_reflow(self):
        """Sambung baris yang dipatahkan manual di dalam paragraf."""
        editor = self._active_editor()
        new_text, changed = reflow_paragraphs(editor.toPlainText())
        if not changed:
            self.statusBar().showMessage(
                "Nothing to reflow — every paragraph is already a single line.", 4000)
            return
        cursor = QTextCursor(editor.document())
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(new_text)
        cursor.endEditBlock()
        for document in (self.doc, self.doc_b):
            document.setProperty("ktktSpacing", 0.0)
            self._apply_line_spacing(document)
        self.statusBar().showMessage(
            f"Joined {changed} wrapped paragraph(s). Ctrl+Z to undo.", 5000)

    def _rebuild_outline(self, path=None):
        only = Path(path) if (self.file_mode and path) else None
        self.outline.rebuild(self.project, path, only=only)

    def _current_line(self) -> int:
        return self._active_editor().textCursor().blockNumber() + 1

    def _current_text(self) -> str:
        return self._active_editor().toPlainText()

    def _on_editor_changed(self, source):
        if self._syncing or source is not self._active_editor():
            return
        self._sync_source = source
        self.sync_timer.start()

    def _sync_documents(self, force=False):
        """Cerminkan teks dari panel yang dipakai ke panel editor lainnya.

        Dua panel tidak bisa berbagi satu QTextDocument, jadi teks dicerminkan
        dengan jeda singkat. Panel yang tidak sedang difokus tidak mengganggu.
        """
        src = self._sync_source if self._sync_source is not None else self.pane_a.editor
        if src not in (self.pane_a.editor, self.pane_b.editor):
            src = self.pane_a.editor
        dst = self.pane_b.editor if src is self.pane_a.editor else self.pane_a.editor
        dst_pane = self.pane_b if dst is self.pane_b.editor else self.pane_a
        if not force and (not dst_pane.is_editor or not dst_pane.isVisibleTo(self)):
            return
        text = src.toPlainText()
        if dst.toPlainText() == text:
            return
        pos = dst.textCursor().position()
        bar = dst.verticalScrollBar()
        ratio = bar.value() / bar.maximum() if bar.maximum() else 0.0
        self._syncing = True
        try:
            dst.setPlainText(text)
        finally:
            self._syncing = False
        if dst is self.pane_a.editor:
            self.doc.setModified(True)   # isi berubah: autosave harus jalan
        cursor = dst.textCursor()
        cursor.setPosition(min(pos, len(text)))
        dst.setTextCursor(cursor)
        if bar.maximum():
            bar.setValue(int(bar.maximum() * ratio))

    def _set_active_match(self, pos):
        for hl in (self.search_hl, self.search_hl_b):
            hl.set_active(pos)

    def _reload_current(self):
        if not self.current_path:
            return
        try:
            text = self.project.read(self.current_path)
        except OSError:
            return
        if text != self.doc.toPlainText():
            pos = self._active_editor().textCursor().position()
            self._load_text(text)
            self._loaded_sig = self._disk_signature(self.current_path)
            self._active_editor().goto_position(min(pos, len(text)))
            self._rebuild_outline(self.current_path)

    # ------------------------------------------------------------ preview
    def _on_contents(self):
        if self._loading:
            return
        self.stats_timer.start()
        # dokumen raksasa: render hanya saat benar-benar berhenti mengetik
        long_document = len(self._current_text()) > 200_000
        self.preview_timer.setInterval(1200 if long_document else PREVIEW_MS)
        self.preview_timer.start()
        if self.issues_panel.isVisibleTo(self):
            self.lint_timer.start()
        if self.rep_window is not None and self.rep_window.isVisible():
            self.rep_timer.start()

    @staticmethod
    def _plain_needle(line: str) -> str:
        """Teks paragraf tanpa penanda markdown, untuk dicari di preview."""
        text = line.strip()
        text = re.sub(r"^(#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)", "", text)
        text = text.replace("**", "").replace("__", "").replace("`", "")
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"(?<!\w)[*_](\S.*?)[*_](?!\w)", r"\1", text)
        return text.strip()[:60]

    def _preview_anchor(self) -> dict:
        """Paragraf yang sedang terlihat di atas editor.

        Dipakai preview untuk mendarat di paragraf yang sama: teksnya sendiri
        (paling tepat), nomor urut paragraf (cadangan), dan pecahan karakter
        (cadangan terakhir).
        """
        editor = self._active_editor()
        text = editor.toPlainText()
        if not text:
            return {"text": "", "fraction": 0.0, "ordinal": None}

        document = editor.document()
        block = editor.cursorForPosition(QPoint(0, 0)).block()
        if not block.isValid():
            block = document.firstBlock()
        # lewati baris kosong: paragraf kosong tidak bisa dicari di preview
        while block.isValid() and not block.text().strip():
            block = block.next()
        if not block.isValid():
            block = document.lastBlock()

        ordinal = 0
        walker = document.firstBlock()
        while walker.isValid() and walker != block:
            if walker.text().strip():
                ordinal += 1
            walker = walker.next()

        return {
            "text": self._plain_needle(block.text()),
            "fraction": block.position() / max(1, len(text)),
            "ordinal": ordinal,
        }

    def _refresh_previews(self):
        # teks mentah: preview sendiri yang membedakan baris baru vs paragraf
        text = self._current_text()
        anchor = self._preview_anchor()
        base = self.project.root if self.project is not None else None
        for pane in (self.pane_a, self.pane_b):
            if not pane.is_editor:
                if base is not None:
                    pane.preview.set_base_dir(base)
                pane.preview.set_markdown_text(text, anchor)

    def _sync_scroll(self):
        """Gulir manual di editor ikut menggeser preview -- sumber jangkarnya sama
        dengan pembaruan otomatis, jadi keduanya tidak bisa saling menimpa."""
        anchor = self._preview_anchor()
        for pane in (self.pane_a, self.pane_b):
            if not pane.is_editor and pane.isVisibleTo(self):
                pane.preview.scroll_to_anchor(anchor)

    # ------------------------------------------------------------ statistik
    def _update_stats(self):
        s = summarize(self._current_text())
        self.lbl_stats.setText(
            f"{s['words']:,} words · {s['sentences']:,} sentences · "
            f"{s['paragraphs']:,} paragraphs · ~{s['minutes']} min read")
        if self.session_base is not None:
            delta = s["words"] - self.session_base
            sign = "+" if delta >= 0 else ""
            self.lbl_session.setText(f"session {sign}{delta:,} words")
        self._refresh_hits()
        self._update_cursor_label()

    def _refresh_lint_if_visible(self):
        if self.issues_panel.isVisibleTo(self):
            self._update_lint()

    def _update_cursor_label(self):
        cursor = self._active_editor().textCursor()
        self.lbl_cursor.setText(
            f"Ln {cursor.blockNumber() + 1}, Col {cursor.positionInBlock() + 1}")
        self._follow_section()

    def _follow_section(self):
        """Kursor bergerak: jadwalkan pemeriksaan, jangan dihitung tiap ketukan."""
        window = self.rep_window
        if window is None or not window.isVisible() or window.scope.currentIndex() != 1:
            return
        self.rep_section_timer.start()

    def _check_section_follow(self):
        """Kalau heading di bawah kursor berubah, analisis diulang sendiri."""
        window = self.rep_window
        if window is None or not window.isVisible() or window.scope.currentIndex() != 1:
            return
        from .sections import section_at

        start, end, _title = section_at(self._current_text(), self._current_line())
        if (start, end) != window.section_key:
            self._refresh_repetition()

    def _refresh_hits(self):
        """Angka hasil disegarkan setiap dokumen berubah -- termasuk saat mengetik
        kata yang sedang dicari. Sorotannya sendiri digambar highlighter."""
        if not self.search.isVisibleTo(self) or not self.search.text():
            self._hits = []
            self._hit_index = -1
            return
        self._hits = self.search_hl.find_all(self._current_text())
        if self._hit_index >= len(self._hits):
            self._hit_index = -1
        self._set_active_match(
            self._hits[self._hit_index] if self._hit_index >= 0 else -1)
        self.search.set_counter(max(0, self._hit_index + 1), len(self._hits))

    # ---------------------------------------------------------------- lint
    def _update_lint(self):
        text = self._current_text()
        base = self.current_path.parent if self.current_path else None
        self.lint_issues = lint_text(text, base)
        warn = sum(1 for _l, level, _m in self.lint_issues if level == "warn")
        info = len(self.lint_issues) - warn
        if not self.lint_issues:
            self.btn_lint.setText("✓ no issues")
        else:
            self.btn_lint.setText(f"⚠ {warn} · ℹ {info}")
        self.btn_lint.setToolTip("\n".join(
            f"line {l}: {m}" for l, _lv, m in self.lint_issues[:12]) or "No issues")
        if self.issues_panel.isVisibleTo(self):
            self._fill_issue_list()

    def toggle_lint_panel(self):
        show = not self.issues_panel.isVisibleTo(self)
        self.issues_panel.setVisible(show)
        if show:
            self._update_lint()
            self._fill_issue_list()
            self.issue_list.setFocus()

    def _fill_issue_list(self):
        self.issue_list.clear()
        if not self.lint_issues:
            item = QListWidgetItem("No issues found.")
            item.setFlags(Qt.NoItemFlags)
            self.issue_list.addItem(item)
            return
        accent = QColor(colors(self.theme_name)["accent"])
        for line, level, message in self.lint_issues:
            item = QListWidgetItem(f"line {line} — {message}")
            item.setData(Qt.UserRole, int(line))
            if level == "warn":
                item.setForeground(accent)
            self.issue_list.addItem(item)

    def _jump_to_issue(self, item):
        line = item.data(Qt.UserRole)
        if line is None:
            return
        self._active_editor().reveal_line(int(line) - 1)

    # ------------------------------------------------------------- repetisi
    def open_repetition(self):
        if not self.current_path:
            QMessageBox.information(self, "Repetition",
                                    "Open a novel or a project folder first.")
            return
        from .repetition_window import RepetitionWindow

        if self.rep_window is None:
            self.rep_window = RepetitionWindow(self)
            self.rep_window.jump.connect(self._jump_from_repetition)
        self.rep_window.set_context(self.project, self.current_path,
                                    self._current_text, self._current_line)
        self.rep_window.show()
        self.rep_window.raise_()
        self.rep_window.activateWindow()
        self.rep_window.refresh()

    def _jump_from_repetition(self, path, line):
        target = Path(path)
        if self.current_path != target:
            self._open_chapter(target)
        if self.current_path == target:
            self._active_editor().reveal_line(max(0, int(line) - 1))

    def _refresh_repetition(self):
        if self.rep_window is not None and self.rep_window.isVisible():
            self.rep_window.set_context(self.project, self.current_path,
                                        self._current_text, self._current_line)
            self.rep_window.refresh()

    # -------------------------------------------------------------- ekspor
    def export_docx(self):
        if not self._ensure_project():
            return
        self._save_if_dirty()
        self.project.scan()
        if not self.project.chapters:
            QMessageBox.information(self, "Export", "There are no chapters to export.")
            return
        suggestion = self.project.root.parent / f"{self.project.name}.docx"
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Export manuscript", str(suggestion), "Word (*.docx)")
        if not chosen:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            path = export_manuscript(self.project.chapters, chosen, title=self.project.name)
        except ExportError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Export failed", f"{type(exc).__name__}: {exc}")
            return
        QApplication.restoreOverrideCursor()
        QMessageBox.information(self, "Export finished",
                                f"Saved:\n{path}\n\n{len(self.project.chapters)} chapters.")

    # ------------------------------------------------------------- lainnya
    def _editors(self):
        panels = [p for p in (self.pane_a, self.pane_b) if p.isVisibleTo(self)]
        return [p.editor for p in panels if p.is_editor]

    def _active_editor(self):
        focused = QApplication.focusWidget()
        for editor in self._editors():
            if focused is editor or (focused is not None and editor.isAncestorOf(focused)):
                return editor
        editors = self._editors()
        return editors[0] if editors else self.pane_a.editor

    def _about_icon(self):
        if not ICON_FILE.exists():
            return None
        return QPixmap(str(ICON_FILE)).scaled(
            72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def about(self):
        self.confirm.ask(ABOUT_LINE, ABOUT_COPYRIGHT,
                         [("ok", "OK", "primary")], self._about_icon())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.search.isVisible():
            self.close_search()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------ sesi
    def _restore_session(self):
        last = self.settings.value("session/project", "")
        last_file = self.settings.value("session/file", "")
        mode = self.settings.value("session/mode", "project")
        if str(mode) == "file" and last_file and Path(last_file).is_file():
            self.open_document(Path(last_file))
        elif last and Path(last).is_dir():
            self.open_project(last)
        else:
            self.statusBar().showMessage(
                "Open a file (Ctrl+O), a project folder (Ctrl+Shift+O), or start a new project (Ctrl+Shift+N).", 0)

    def _apply_start_geometry(self):
        """70% dari area layar yang tersedia, lalu diletakkan di tengah.

        Di Wayland posisi jendela utama ditentukan desktop, bukan aplikasi;
        ukurannya tetap 70%.
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1180, 780)
            return
        area = screen.availableGeometry()
        width = min(area.width(), max(900, int(area.width() * 0.7)))
        height = min(area.height(), max(600, int(area.height() * 0.7)))
        self.resize(width, height)
        self.move(area.center() - self.rect().center())

    def _restore_layout(self):
        state = self.settings.value("ui/splitter")
        if state:
            self.splitter.restoreState(state)

    def _persist(self):
        self.settings.setValue("ui/splitter", self.splitter.saveState())
        self.settings.setValue("session/project",
                               str(self.project.root) if self.project else "")
        self.settings.setValue("session/mode", "file" if self.file_mode else "project")
        if self.current_path:
            self.settings.setValue("session/file", str(self.current_path))
            self.cursor_cache[str(self.current_path)] = self._active_editor().textCursor().position()
            if self.cursor_cache:
                keep = dict(list(self.cursor_cache.items())[-40:])
                for key, pos in keep.items():
                    self.settings.setValue(f"session/cursor/{key}", pos)
        self.settings.setValue("ui/pane_b", self.pane_b.mode)
        self.settings.setValue("ui/split", self.pane_b.isVisibleTo(self))
        self.settings.setValue("ui/theme", self.theme_name)
        self.settings.sync()

    def closeEvent(self, event):
        if self._confirming:
            event.ignore()
            return
        if not self._confirm_exit():
            event.ignore()
            return
        if not self._save_if_dirty():
            choice = self.confirm.ask(
                "Could not save",
                "Your last changes could not be written to disk. A recovery copy has been "
                "kept, and it will be offered the next time you open this chapter.\n\n"
                "Quit anyway?",
                [("quit", "Quit anyway", "destructive"),
                 ("cancel", "Cancel", "primary")])
            if choice != "quit":
                event.ignore()
                return
        self._persist()
        if self.project is not None:
            self.project.release_lock()
        super().closeEvent(event)

    def _exit_options(self, dirty: bool):
        if dirty:
            name = self.current_path.name if self.current_path else "Untitled chapter"
            return ("Save your changes before quitting?",
                    f"Unsaved changes in {name}.",
                    [("save", "Save", "primary"),
                     ("discard", "Discard", "destructive"),
                     ("cancel", "Cancel", "")])
        return ("Quit Ketikaketik?", "No unsaved changes.",
                [("quit", "Quit", "primary"), ("cancel", "Cancel", "")])

    def _confirm_exit(self) -> bool:
        if self._confirming:
            return False
        self._confirming = True
        try:
            dirty = self._is_modified()
            title, message, options = self._exit_options(dirty)
            choice = self.confirm.ask(title, message, options)
            if choice in (None, "cancel"):
                return False
            if dirty and choice == "save":
                self.save()
                return not self._is_modified()
            return True
        finally:
            self._confirming = False