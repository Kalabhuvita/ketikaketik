"""Outline otomatis: semua heading di semua bab, tersusun jadi pohon."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from .project import headings_of


class Outline(QTreeWidget):
    goto = Signal(object, int)      # (path, nomor_baris)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setIndentation(14)
        self.itemClicked.connect(self._clicked)
        self.itemActivated.connect(self._clicked)

    def rebuild(self, project, current_path=None, only=None):
        self.clear()
        if project is None:
            return
        chapters = [only] if only is not None else project.chapters
        for chapter in chapters:
            try:
                heads = headings_of(project.read(chapter))
            except OSError:
                continue
            if not heads:
                continue
            top = QTreeWidgetItem([chapter.stem])
            top.setData(0, Qt.UserRole, (str(chapter), 0))
            self.addTopLevelItem(top)
            if current_path and str(chapter) == str(current_path):
                font = top.font(0)
                font.setBold(True)
                top.setFont(0, font)
            stack = [(0, top)]
            for level, title, line in heads:
                while stack and stack[-1][0] >= level:
                    stack.pop()
                parent = stack[-1][1] if stack else top
                item = QTreeWidgetItem([title or "(untitled)"])
                item.setData(0, Qt.UserRole, (str(chapter), line))
                parent.addChild(item)
                stack.append((level, item))
            top.setExpanded(True)

    def _clicked(self, item, _column=0):
        data = item.data(0, Qt.UserRole)
        if data:
            self.goto.emit(data[0], int(data[1]))