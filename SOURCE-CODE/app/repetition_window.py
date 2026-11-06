"""Jendela analisis repetisi.

Sengaja terpisah dari jendela utama: saat menulis tidak ada satu pun elemen
tambahan di layar. Jendela ini dibuka hanya saat dibutuhkan, boleh ditaruh di
monitor kedua, dan bisa "always on top".

Tidak ada kata yang disembunyikan secara default. Penulis yang memilih: klik
kanan satu baris untuk mengabaikannya, dan daftar abaikan itu diingat.
"""
import json
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QAction, QFont, QPalette
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                               QHBoxLayout, QLabel, QListWidget, QMenu,
                               QPushButton, QSpinBox, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)


MIN_SECTION_WORDS = 25


class RepetitionWindow(QWidget):
    """Daftar kata yang terlalu sering dan kata yang muncul berdekatan."""

    jump = Signal(str, int)          # path, nomor baris (1-based)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Repetition — Ketikaketik")
        self.settings = QSettings()
        self.project = None
        self.chapter_path = None
        self.text_provider = None
        self.line_provider = None
        self.section_key = None
        self._build()
        self._restore()

    # ------------------------------------------------------------------ UI
    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # baris 1: cakupan dan tombol utama
        top = QHBoxLayout()
        top.setSpacing(6)
        self.scope = QComboBox()
        self.scope.addItems(["Whole novel", "This section"])
        self.scope.setMaximumWidth(150)
        self.scope.setToolTip(
            "Whole novel — count the entire file.\n"
            "This section — count only from the heading your cursor is in to the next "
            "heading. It re-runs by itself as you move around the text.")
        self.scope.currentIndexChanged.connect(self._changed)
        top.addWidget(self.scope)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Recalculate now")
        self.refresh_button.clicked.connect(self.refresh)
        top.addWidget(self.refresh_button)
        top.addStretch(1)

        self.on_top = QCheckBox("On top")
        self.on_top.setToolTip("Keep this window above the editor")
        self.on_top.toggled.connect(self._set_on_top)
        top.addWidget(self.on_top)
        layout.addLayout(top)

        # baris 2: pengaturan, semuanya diringkas supaya jendela bisa dipersempit
        controls = QHBoxLayout()
        controls.setSpacing(5)
        min_label = QLabel("Min")
        min_label.setToolTip("Only show words that appear at least this many times")
        controls.addWidget(min_label)
        self.min_count = QSpinBox()
        self.min_count.setRange(2, 200)
        self.min_count.setValue(3)
        self.min_count.setMaximumWidth(64)
        self.min_count.valueChanged.connect(self._changed)
        controls.addWidget(self.min_count)

        within_label = QLabel("Within")
        within_label.setToolTip("How many sentences apart two occurrences still count as close")
        controls.addWidget(within_label)
        self.window_spin = QSpinBox()
        self.window_spin.setRange(1, 20)
        self.window_spin.setValue(3)
        self.window_spin.setMaximumWidth(64)
        self.window_spin.valueChanged.connect(self._changed)
        controls.addWidget(self.window_spin)
        sentences_label = QLabel("sent.")
        sentences_label.setToolTip("sentences")
        controls.addWidget(sentences_label)

        self.ignored_button = QPushButton("Ignored…")
        self.ignored_button.setCheckable(True)
        self.ignored_button.setToolTip("Words and phrases you have chosen to ignore")
        self.ignored_button.toggled.connect(self._toggle_ignored_panel)
        controls.addWidget(self.ignored_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.section_hint = QLabel(
            "This section = from the heading your cursor is in, up to the next heading. "
            "It updates by itself as you move.")
        self.section_hint.setWordWrap(True)
        palette = self.section_hint.palette()
        palette.setColor(QPalette.WindowText,
                         palette.color(QPalette.Disabled, QPalette.WindowText))
        self.section_hint.setPalette(palette)
        self.section_hint.setVisible(False)
        layout.addWidget(self.section_hint)

        self.tabs = QTabWidget()

        self.word_tree = QTreeWidget()
        self._prepare_tree(self.word_tree, ["Word", "Count", "Per 1000"])
        self.tabs.addTab(self.word_tree, "Frequent words")

        self.repeat_tree = QTreeWidget()
        self._prepare_tree(self.repeat_tree, ["Word or phrase", "Count", "Density", "Line"])
        self.tabs.addTab(self.repeat_tree, "Close repetitions")

        self.phrase_page = QWidget()
        page = QVBoxLayout(self.phrase_page)
        page.setContentsMargins(0, 6, 0, 0)
        page.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(5)
        row.addWidget(QLabel("Phrases of 2 to"))
        self.max_words = QSpinBox()
        self.max_words.setRange(2, 10)
        self.max_words.setValue(5)
        self.max_words.setMaximumWidth(64)
        self.max_words.setToolTip("Longest phrase to look for, in words")
        self.max_words.valueChanged.connect(self._changed)
        row.addWidget(self.max_words)
        row.addWidget(QLabel("words, repeated at least twice"))
        row.addStretch(1)
        page.addLayout(row)
        self.phrase_tree = QTreeWidget()
        self._prepare_tree(self.phrase_tree, ["Phrase", "Words", "Count", "Line"])
        self.phrase_tree.setSortingEnabled(True)
        page.addWidget(self.phrase_tree, 1)
        self.tabs.addTab(self.phrase_page, "Repeated phrases")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self.tabs, 1)

        self.ignored_panel = self._build_ignored_panel()
        layout.addWidget(self.ignored_panel)

        self.status = QLabel("Open a chapter to analyse it.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def _prepare_tree(self, tree, headers):
        from PySide6.QtWidgets import QHeaderView

        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setHeaderLabels(headers)
        tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tree.setMinimumWidth(220)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(
            lambda position, target=tree: self._show_menu(target, position))
        tree.itemClicked.connect(self._emit_jump)
        header = tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, len(headers)):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)

    def _build_ignored_panel(self):
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)

        row = QHBoxLayout()
        row.addWidget(QLabel("Ignored words and phrases"))
        self.hide_ignored = QCheckBox("Hide them in the lists")
        self.hide_ignored.setToolTip("Hide the words you have marked as ignored")
        self.hide_ignored.toggled.connect(self._changed)
        row.addWidget(self.hide_ignored)
        row.addStretch(1)
        restore = QPushButton("Restore")
        restore.clicked.connect(self._restore_selected)
        row.addWidget(restore)
        restore_all = QPushButton("Restore all")
        restore_all.clicked.connect(self._restore_all)
        row.addWidget(restore_all)
        box.addLayout(row)

        self.ignored_list = QListWidget()
        self.ignored_list.setMaximumHeight(110)
        box.addWidget(self.ignored_list)
        panel.hide()
        return panel

    # -------------------------------------------------------- daftar abaikan
    def _ignored(self) -> set:
        raw = self.settings.value("repetition/ignored", "[]")
        try:
            values = json.loads(raw) if isinstance(raw, str) else list(raw)
        except (TypeError, ValueError):
            return set()
        return {str(value).lower() for value in values}

    def _set_ignored(self, values):
        self.settings.setValue("repetition/ignored", json.dumps(sorted(values)))
        self._refresh_ignored_list()

    def _toggle_ignored_panel(self, checked: bool):
        self.ignored_panel.setVisible(checked)
        if checked:
            self._refresh_ignored_list()

    def _refresh_ignored_list(self):
        self.ignored_list.clear()
        self.ignored_list.addItems(sorted(self._ignored()))

    def _restore_selected(self):
        chosen = {item.text() for item in self.ignored_list.selectedItems()}
        if not chosen:
            return
        self._set_ignored(self._ignored() - chosen)
        self.refresh()

    def _restore_all(self):
        self._set_ignored(set())
        self.refresh()

    def _show_menu(self, tree, position):
        item = tree.itemAt(position)
        if item is None:
            return
        picked = tree.selectedItems() or [item]
        words = {str(entry.data(0, Qt.UserRole + 2)) for entry in picked
                 if entry.data(0, Qt.UserRole + 2)}
        if not words:
            return

        ignored = self._ignored()
        menu = QMenu(self)
        if words <= ignored:
            action = QAction(f"Stop ignoring ({len(words)})" if len(words) > 1
                             else "Stop ignoring", self)
        else:
            action = QAction(f"Ignore {len(words)} words" if len(words) > 1
                             else "Ignore this word", self)
        menu.addAction(action)

        chosen = menu.exec(tree.viewport().mapToGlobal(position))
        if chosen is not action:
            return
        if action.text().startswith("Stop"):
            ignored -= words
        else:
            ignored |= words
        self._set_ignored(ignored)
        self.refresh()

    # ------------------------------------------------------------- konteks
    def set_context(self, project, chapter_path, text_provider, line_provider=None):
        self.project = project
        self.chapter_path = chapter_path
        self.text_provider = text_provider
        self.line_provider = line_provider

    def _text_for_scope(self):
        if not self.text_provider or not self.chapter_path:
            return None, "", None
        text = self.text_provider()
        if self.scope.currentIndex() == 0:
            return text, "Whole novel", None

        from .sections import headings, section_at

        line = self.line_provider() if self.line_provider else 1
        start, end, title = section_at(text, line)
        lines = text.splitlines()
        body = "\n".join(lines[start - 1:end])

        # kursor di pembuka yang nyaris kosong: pakai bagian heading pertama,
        # supaya jendela ini tidak pernah menampilkan nol tanpa alasan
        if len(body.split()) < MIN_SECTION_WORDS:
            items = headings(text)
            if items and start <= 1:
                start, end, title = section_at(text, items[0][0])
                body = "\n".join(lines[start - 1:end])

        label = f"This section — {title}" if title else "This section"
        return body, label, (start, end)

    def _on_tab_changed(self, index):
        if index == 2:
            self.refresh()

    # -------------------------------------------------------------- analisis
    def refresh(self):
        text, scope_label, section_key = self._text_for_scope()
        self.section_key = section_key
        if text is None:
            self.status.setText("Open a novel first.")
            self.word_tree.clear()
            self.repeat_tree.clear()
            self.phrase_tree.clear()
            return

        from .repetition import analyze, repeated_phrases

        path = str(self.chapter_path) if self.chapter_path else ""
        result = analyze(
            text,
            min_count=self.min_count.value(),
            window=self.window_spin.value(),
            include_cliches=True,
        )
        ignored = self._ignored()
        hide = self.hide_ignored.isChecked()

        bold = QFont()
        bold.setBold(True)
        dim = self.palette().brush(QPalette.Disabled, QPalette.WindowText)
        shown = 0

        self.word_tree.clear()
        for row in result["words"]:
            if row["word"] in ignored:
                if hide:
                    continue
                shown += 1
            item = QTreeWidgetItem([row["word"], str(row["count"]), f"{row['per_1000']:.1f}"])
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
            item.setData(0, Qt.UserRole, 0)
            item.setData(0, Qt.UserRole + 1, path)
            item.setData(0, Qt.UserRole + 2, row["word"])
            item.setToolTip(0, f"{row['flavor']} — click to jump, right-click to ignore")
            if row["count"] >= max(10, self.min_count.value() * 3):
                item.setFont(1, bold)
            self._mark_ignored(item, row["word"] in ignored, dim)
            self.word_tree.addTopLevelItem(item)

        self.repeat_tree.clear()
        for row in result["repeats"]:
            if row["word"] in ignored:
                if hide:
                    continue
                shown += 1
            label = row["word"] + ("  ·  cliché" if row["kind"] == "cliche" else "")
            density = "phrase" if row["kind"] == "cliche" else f"{row['density']:.2f}"
            item = QTreeWidgetItem([label, str(row["count"]), density, f"line {row['line']}"])
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
            item.setData(0, Qt.UserRole, row["line"])
            item.setData(0, Qt.UserRole + 1, path)
            item.setData(0, Qt.UserRole + 2, row["word"])
            item.setToolTip(0, row.get("sample", ""))
            item.setToolTip(2, "Occurrences per sentence in the cluster — higher is tighter")
            self._mark_ignored(item, row["word"] in ignored, dim)
            self.repeat_tree.addTopLevelItem(item)

        phrases = None
        self.phrase_tree.clear()
        if self.tabs.currentIndex() == 2:
            phrases, _totals = repeated_phrases(
                text, max_len=self.max_words.value(), min_count=2)
            for row in phrases:
                if row["phrase"] in ignored:
                    if hide:
                        continue
                    shown += 1
                item = QTreeWidgetItem([row["phrase"]])
                item.setData(1, Qt.DisplayRole, int(row["words"]))
                item.setData(2, Qt.DisplayRole, int(row["count"]))
                item.setData(3, Qt.DisplayRole, int(row["line"]))
                for column in (1, 2, 3):
                    item.setTextAlignment(column, Qt.AlignRight | Qt.AlignVCenter)
                item.setData(0, Qt.UserRole, row["line"])
                item.setData(0, Qt.UserRole + 1, path)
                item.setData(0, Qt.UserRole + 2, row["phrase"])
                item.setToolTip(0, row.get("sample", ""))
                self._mark_ignored(item, row["phrase"] in ignored, dim)
                self.phrase_tree.addTopLevelItem(item)
            self.phrase_tree.sortItems(1, Qt.DescendingOrder)

        words_total = result["totals"]["words"]
        status = (
            f"{scope_label} · {result['totals']['words']:,} words · "
            f"{result['totals']['sentences']:,} sentences · "
            f"{len(result['words'])} frequent words · "
            f"{len(result['repeats'])} close repetitions")
        if section_key is not None and words_total < MIN_SECTION_WORDS:
            status += f" · this section is short ({words_total} words)"
        if phrases is not None:
            capped = " (top)" if len(phrases) >= 400 else ""
            status += f" · {len(phrases)} repeated phrases{capped}"
        if shown:
            status += f" · {shown} shown but ignored"
        if ignored and hide:
            status += f" · {len(ignored)} ignored"
        self.status.setText(status)

    @staticmethod
    def _mark_ignored(item, is_ignored: bool, dim):
        if not is_ignored:
            return
        for column in range(item.columnCount()):
            font = item.font(column)
            font.setStrikeOut(True)
            item.setFont(column, font)
            item.setForeground(column, dim)

    def _emit_jump(self, item, _column):
        line = item.data(0, Qt.UserRole)
        path = item.data(0, Qt.UserRole + 1)
        if line and path:
            self.jump.emit(path, int(line))

    # ------------------------------------------------------------- perilaku
    def _changed(self, *_args):
        self.section_hint.setVisible(self.scope.currentIndex() == 1)
        self._persist()
        self.refresh()

    def _persist(self):
        self.settings.setValue("repetition/scope", self.scope.currentIndex())
        self.settings.setValue("repetition/min_count", self.min_count.value())
        self.settings.setValue("repetition/window", self.window_spin.value())
        self.settings.setValue("repetition/max_words", self.max_words.value())
        self.settings.setValue("repetition/hide_ignored", self.hide_ignored.isChecked())
        self.settings.setValue("repetition/on_top", self.on_top.isChecked())

    def _set_on_top(self, checked: bool):
        flags = self.windowFlags()
        if checked:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()
        self.raise_()

    def _restore(self):
        self.setMinimumWidth(380)
        geometry = self.settings.value("repetition/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(600, 540)
        self.scope.setCurrentIndex(int(self.settings.value("repetition/scope", 0)))
        self.min_count.setValue(int(self.settings.value("repetition/min_count", 3)))
        self.window_spin.setValue(int(self.settings.value("repetition/window", 3)))
        self.max_words.setValue(int(self.settings.value("repetition/max_words", 5)))
        self.hide_ignored.setChecked(
            str(self.settings.value("repetition/hide_ignored", "false")) == "true")
        if str(self.settings.value("repetition/on_top", "false")) == "true":
            self.on_top.setChecked(True)
            self._set_on_top(True)
        self._refresh_ignored_list()
        self.section_hint.setVisible(self.scope.currentIndex() == 1)

    def closeEvent(self, event):
        self.settings.setValue("repetition/geometry", self.saveGeometry())
        self._persist()
        super().closeEvent(event)