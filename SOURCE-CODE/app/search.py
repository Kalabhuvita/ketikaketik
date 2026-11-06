"""Panel pencarian (find/replace) dan pencarian lintas proyek."""
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)


class SearchBar(QWidget):
    changed = Signal()
    navigate = Signal(int)          # +1 berikutnya, -1 sebelumnya
    replaceOne = Signal()
    replaceAll = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)

        self.query = QLineEdit(self)
        self.query.setPlaceholderText("Find…")
        self.query.setClearButtonEnabled(True)
        self.query.textChanged.connect(lambda _t: self.changed.emit())

        self.word = QToolButton(self)
        self.word.setText("ab")
        self.word.setCheckable(True)
        self.word.setChecked(True)
        self.word.setToolTip("Whole word only — 'yang' will not match 'sayang'")
        self.word.toggled.connect(lambda _v: self.changed.emit())

        self.case = QToolButton(self)
        self.case.setText("Aa")
        self.case.setCheckable(True)
        self.case.setToolTip("Match uppercase/lowercase exactly (Aa = off means ignore case)")
        self.case.toggled.connect(lambda _v: self.changed.emit())

        self.regex = QToolButton(self)
        self.regex.setText(".*")
        self.regex.setCheckable(True)
        self.regex.setToolTip("Use a regular expression (whole word is ignored)")
        self.regex.toggled.connect(self._on_regex_toggled)
        self.regex.toggled.connect(lambda _v: self.changed.emit())

        self.counter = QLabel("0 results", self)
        self.counter.setMinimumWidth(90)

        prev = QToolButton(self)
        prev.setText("‹")
        prev.setToolTip("Previous (Shift+Enter)")
        prev.clicked.connect(lambda: self.navigate.emit(-1))

        nxt = QToolButton(self)
        nxt.setText("›")
        nxt.setToolTip("Next (Enter)")
        nxt.clicked.connect(lambda: self.navigate.emit(1))

        close = QToolButton(self)
        close.setText("✕")
        close.setToolTip("Close (Esc)")
        close.clicked.connect(self.closed.emit)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(4)
        row1.addWidget(self.query, 1)
        row1.addWidget(self.word)
        row1.addWidget(self.case)
        row1.addWidget(self.regex)
        row1.addWidget(self.counter)
        row1.addWidget(prev)
        row1.addWidget(nxt)
        row1.addWidget(close)

        self.replace = QLineEdit(self)
        self.replace.setPlaceholderText("Replace with…")
        self.replace.returnPressed.connect(self.replaceOne.emit)

        replace_btn = QPushButton("Replace", self)
        replace_btn.clicked.connect(self.replaceOne.emit)
        replace_all_btn = QPushButton("Replace all", self)
        replace_all_btn.clicked.connect(self.replaceAll.emit)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(4)
        row2.addWidget(self.replace, 1)
        row2.addWidget(replace_btn)
        row2.addWidget(replace_all_btn)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(5)
        outer.addLayout(row1)
        outer.addLayout(row2)

        self.query.returnPressed.connect(lambda: self.navigate.emit(1))

    # -- akses ---------------------------------------------
    def text(self) -> str:
        return self.query.text()

    def replace_text(self) -> str:
        return self.replace.text()

    def case_sensitive(self) -> bool:
        return self.case.isChecked()

    def use_regex(self) -> bool:
        return self.regex.isChecked()

    def whole_word(self) -> bool:
        return self.word.isChecked()

    def _on_regex_toggled(self, checked: bool):
        # whole word tidak masuk akal saat pola regex ditulis sendiri
        self.word.setEnabled(not checked)

    def set_counter(self, shown: int, total: int, invalid=False):
        if invalid:
            self.counter.setText("invalid regex")
        elif not self.text():
            self.counter.setText("0 results")
        else:
            self.counter.setText(f"{shown}/{total} results" if total else "0 results")

    def focus_query(self, with_replace=False):
        self.setVisible(True)
        target = self.replace if with_replace else self.query
        target.setFocus()
        target.selectAll()


class ProjectSearchDialog(QDialog):
    """Cari & ganti di semua bab. Daftar hasil sekaligus jadi pratinjau."""
    jump = Signal(object, int)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Find in project")
        self.resize(760, 520)
        self.matches = []          # [(path, line_no, line_text)]

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        row = QHBoxLayout()
        self.query = QLineEdit(self)
        self.query.setPlaceholderText("Word or regex…")
        self.query.textChanged.connect(self.refresh)
        self.case = QCheckBox("Match case", self)
        self.case.toggled.connect(self.refresh)
        self.regex = QCheckBox("Regex", self)
        self.regex.toggled.connect(self.refresh)
        self.word = QCheckBox("Whole word", self)
        self.word.setChecked(True)
        self.word.toggled.connect(self.refresh)
        row.addWidget(self.query, 1)
        row.addWidget(self.word)
        row.addWidget(self.case)
        row.addWidget(self.regex)
        root.addLayout(row)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Chapter / line", "Text"])
        self.tree.setRootIsDecorated(True)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        root.addWidget(self.tree, 1)

        row2 = QHBoxLayout()
        self.replace = QLineEdit(self)
        self.replace.setPlaceholderText("Replace with…")
        self.btn_one = QPushButton("Replace selected", self)
        self.btn_one.clicked.connect(self._replace_selected)
        self.btn_all = QPushButton("Replace in all chapters", self)
        self.btn_all.clicked.connect(self._replace_all)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        row2.addWidget(self.replace, 1)
        row2.addWidget(self.btn_one)
        row2.addWidget(self.btn_all)
        row2.addWidget(close)
        root.addLayout(row2)

        self.status = QLabel("", self)
        root.addWidget(self.status)

        self.refresh()

    # -- pencocokan ------------------------------------------------------
    def _pattern(self):
        q = self.query.text()
        if not q:
            return None
        flags = 0 if self.case.isChecked() else re.IGNORECASE
        try:
            if self.regex.isChecked():
                return re.compile(q, flags)
            escaped = re.escape(q)
            if self.word.isChecked():
                escaped = rf"(?<!\w){escaped}(?!\w)"
            return re.compile(escaped, flags)
        except re.error:
            self.status.setText("Invalid regex.")
            return "invalid"

    def refresh(self):
        self.tree.clear()
        self.matches = []
        pattern = self._pattern()
        if not pattern:
            self.status.setText("Type something to search.")
            return
        if pattern == "invalid":
            return
        total = 0
        for chapter in self.project.chapters:
            try:
                text = self.project.read(chapter)
            except OSError:
                continue
            lines = text.split("\n")
            hits = []
            for i, line in enumerate(lines, start=1):
                for _m in pattern.finditer(line):
                    hits.append(i)
            if hits:
                parent = QTreeWidgetItem([chapter.name, f"{len(hits)} matches"])
                self.tree.addTopLevelItem(parent)
                for line_no in hits:
                    snippet = lines[line_no - 1].strip()
                    if len(snippet) > 120:
                        snippet = snippet[:117] + "…"
                    child = QTreeWidgetItem([f"line {line_no}", snippet])
                    child.setData(0, Qt.UserRole, (str(chapter), line_no))
                    parent.addChild(child)
                    self.matches.append((chapter, line_no, lines[line_no - 1]))
                    total += 1
                parent.setExpanded(True)
        self.status.setText(f"{total} matches in "
                            f"{self.tree.topLevelItemCount()} chapters.")

    def _on_double_click(self, item, _col):
        data = item.data(0, Qt.UserRole)
        if data:
            self.jump.emit(data[0], data[1])

    # -- penggantian -----------------------------------------------------
    def _replace_all(self):
        pattern = self._pattern()
        if not pattern or pattern == "invalid":
            return
        replacement = self.replace.text()
        from .project import add_recent  # noqa: F401  (hanya memastikan impor aman)
        changed_files = 0
        changed_hits = 0
        for chapter in self.project.chapters:
            text = self.project.read(chapter)
            new_text, n = pattern.subn(lambda _m: replacement, text)
            if n:
                self.project.save(chapter, new_text)
                changed_files += 1
                changed_hits += n
        self.status.setText(
            f"{changed_hits} replaced in {changed_files} chapters. Active chapter reloaded.")
        self.refresh()

    def _replace_selected(self):
        item = self.tree.currentItem()
        data = item.data(0, Qt.UserRole) if item else None
        if not data:
            self.status.setText("Select a result row first.")
            return
        pattern = self._pattern()
        if not pattern or pattern == "invalid":
            return
        path, line_no = data
        text = self.project.read(path)
        lines = text.split("\n")
        if 0 < line_no <= len(lines):
            lines[line_no - 1] = pattern.sub(lambda _m: self.replace.text(),
                                             lines[line_no - 1])
            self.project.save(path, "\n".join(lines))
        self.refresh()