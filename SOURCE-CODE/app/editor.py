"""Widget teks: editor, preview read-only, dan panel yang bisa berganti mode."""
from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import (QColor, QFont, QFontInfo, QFontMetricsF, QTextCharFormat,
                           QTextCursor, QTextOption)
from PySide6.QtWidgets import (QFrame, QPlainTextEdit, QStackedWidget, QTextBrowser,
                               QTextEdit)

from .preview_layout import apply_layout

MIN_SIDE = 10


class Editor(QPlainTextEdit):
    """QPlainTextEdit dengan lebar baris maksimal (dalam em)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setFrameShape(QFrame.NoFrame)
        self.setCenterOnScroll(False)
        self._line_width_em = 34.0
        self._use_vp_margins = hasattr(self, "setViewportMargins")
        self._flash_color = QColor("#ffd98a")

    # -- tipografi ------------------------------------------------------
    def apply_typography(self, font: QFont, line_width_em: float):
        self._line_width_em = float(line_width_em)
        f = QFont(font)
        self.setFont(f)
        self.document().setDefaultFont(f)
        try:
            self.setTabStopDistance(QFontMetricsF(f).horizontalAdvance(" ") * 4)
        except Exception:
            pass
        self.update_margins()

    def update_margins(self):
        width = self.width()
        if width <= 0:
            return
        if self._line_width_em <= 0:
            side = MIN_SIDE
        else:
            em = QFontInfo(self.font()).pixelSize()
            if em <= 0:
                em = max(8, QFontMetricsF(self.font()).height())
            target = em * self._line_width_em
            side = int(max(MIN_SIDE, (width - target) / 2.0))

        if self._use_vp_margins:
            m = self.viewportMargins()
            if (m.left(), m.right()) != (side, side):
                self.setViewportMargins(side, 0, side, 0)
        else:
            self.setStyleSheet(
                f"QPlainTextEdit {{ padding-left: {side}px; padding-right: {side}px; }}"
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_margins()

    # -- navigasi -------------------------------------------------------
    def keyPressEvent(self, event):
        """Enter ditangani sendiri.

        Qt menelan satu Enter setelah format blok diterapkan (mis. jarak
        baris), sehingga penulis harus menekan Enter dua-tiga kali untuk turun
        satu paragraf. Di sini blok baru dibuat langsung, mewarisi format blok
        dan format huruf yang sedang dipakai.
        """
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (
                event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            cursor = self.textCursor()
            if cursor.hasSelection():
                cursor.removeSelectedText()
            block_format = cursor.blockFormat()
            char_format = cursor.charFormat()
            cursor.beginEditBlock()
            cursor.insertBlock(block_format, char_format)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            self.ensureCursorVisible()
            event.accept()
            return
        super().keyPressEvent(event)

    def goto_position(self, pos: int, focus: bool = True):
        """Pindahkan kursor. `focus=False` dipakai dari panel pencarian: merebut
        fokus di tengah pengetikan akan mengeluarkan kursor dari kolom search."""
        cursor = self.textCursor()
        cursor.setPosition(max(0, min(pos, len(self.toPlainText()))))
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        if focus:
            self.setFocus()

    def goto_line(self, line: int, focus: bool = True):
        block = self.document().findBlockByNumber(max(0, line))
        if block.isValid():
            self.goto_position(block.position(), focus)

    # -- menandai baris yang dituju (dipakai panel markdown issues) ------
    def set_flash_color(self, color):
        self._flash_color = QColor(color)

    def reveal_line(self, line: int, flash_ms: int = 2500):
        """Gulung ke baris, taruh kursor di awalnya, lalu kilaukan seluruh baris.

        Sengaja TIDAK menyeleksi baris: seleksi dicat di atas latar format,
        sehingga warna kilau tidak akan pernah terlihat.
        """
        block = self.document().findBlockByNumber(max(0, line))
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()
        self.setFocus()
        self._flash(block, flash_ms)

    def _flash(self, block, flash_ms: int):
        selection = QTextEdit.ExtraSelection()
        selection.cursor = QTextCursor(block)
        selection.cursor.select(QTextCursor.LineUnderCursor)
        fmt = QTextCharFormat()
        fmt.setBackground(self._flash_color)
        fmt.setProperty(QTextCharFormat.FullWidthSelection, True)
        selection.format = fmt
        self.setExtraSelections([selection])
        QTimer.singleShot(flash_ms, self._clear_flash)

    def _clear_flash(self):
        self.setExtraSelections([])


class Preview(QTextBrowser):
    """Live preview sejati: read-only, markdown ter-render, tanpa penanda."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QFrame.NoFrame)
        self._line_width_em = 34.0
        self._last_text = ""
        self._anchor = {}
        self._applying = False
        # dokumen besar: tinggi layout baru final beberapa saat setelah
        # setMarkdown(), jadi posisi gulir harus diterapkan ulang saat rentang
        # scrollbar berubah. Tanpa ini, nilai gulir terpotong ke atas.
        self.verticalScrollBar().rangeChanged.connect(self._on_range_changed)

    def apply_typography(self, font: QFont, line_width_em: float):
        self._line_width_em = float(line_width_em)
        self.setFont(QFont(font))
        self.document().setDefaultFont(QFont(font))
        self.update_margins()

    def update_margins(self):
        width = self.width()
        if width <= 0:
            return
        if self._line_width_em <= 0:
            side = MIN_SIDE + 8
        else:
            em = QFontInfo(self.font()).pixelSize()
            if em <= 0:
                em = max(8, QFontMetricsF(self.font()).height())
            target = em * self._line_width_em
            side = int(max(MIN_SIDE, (width - target) / 2.0))
        pad = f"padding: 14px {side}px;"
        self.setStyleSheet(f"QTextBrowser {{ background: palette(base); {pad} }}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_margins()

    def set_base_dir(self, path):
        """Supaya gambar/tautan relatif di naskah bisa ditampilkan."""
        if path is None:
            return
        base = str(path)
        if not base.endswith("/"):
            base += "/"
        self.document().setBaseUrl(QUrl.fromLocalFile(base))

    def set_markdown_text(self, text: str, anchor=None):
        """Render ulang naskah, lalu tempelkan gulir pada paragraf yang sama.

        Pecahan karakter saja tidak cukup untuk naskah panjang: sumber dan hasil
        render tidak sama panjang (penanda markdown dibuang), sehingga selisihnya
        menumpuk jadi puluhan paragraf. Di sini paragraf dicari berdasarkan
        teksnya sendiri, dengan nomor urut dan pecahan sebagai cadangan.
        """
        if anchor is not None:
            self._anchor = dict(anchor)
        if text == self._last_text:
            self._apply_anchor()
            return
        self._last_text = text
        self.document().setMarkdown(text)
        apply_layout(self.document(), text,
                     paragraph_gap=max(10, int(self.fontMetrics().height() * 0.9)))
        self._apply_anchor()
        QTimer.singleShot(0, self._apply_anchor)
        QTimer.singleShot(150, self._apply_anchor)

    def _block_by_ordinal(self, ordinal: int):
        block = self.document().firstBlock()
        seen = 0
        while block.isValid():
            if block.text().strip():
                if seen == ordinal:
                    return block
                seen += 1
            block = block.next()
        return None

    def _on_range_changed(self, _minimum, _maximum):
        if self._applying:
            return
        self._apply_anchor()

    def _apply_anchor(self):
        document = self.document()
        bar = self.verticalScrollBar()
        anchor = getattr(self, "_anchor", None) or {}
        total = len(document.toPlainText())
        if not total:
            return

        fraction = float(anchor.get("fraction") or 0.0)
        expected = int(total * max(0.0, min(1.0, fraction)))
        block = None

        needle = (anchor.get("text") or "").strip()
        if len(needle) >= 4:
            cursor = document.find(needle, expected)
            if cursor.isNull():
                cursor = document.find(needle, 0)
            if not cursor.isNull():
                block = cursor.block()

        if block is None and anchor.get("ordinal") is not None:
            block = self._block_by_ordinal(int(anchor["ordinal"]))

        if block is None:
            block = document.findBlock(expected)

        if block is None or not block.isValid():
            return
        rect = document.documentLayout().blockBoundingRect(block)
        self._applying = True
        try:
            bar.setValue(int(max(0.0, rect.top())))
        finally:
            self._applying = False

    def scroll_to_anchor(self, anchor):
        self._anchor = dict(anchor)
        self._apply_anchor()

    def scroll_ratio(self) -> float:
        bar = self.verticalScrollBar()
        return bar.value() / bar.maximum() if bar.maximum() else 0.0

    def set_scroll_ratio(self, ratio: float):
        bar = self.verticalScrollBar()
        if bar.maximum():
            bar.setValue(int(bar.maximum() * max(0.0, min(1.0, ratio))))


class Pane(QStackedWidget):
    """Satu panel: bisa berupa editor atau preview."""

    EDITOR = 0
    PREVIEW = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.editor = Editor(self)
        self.preview = Preview(self)
        self.addWidget(self.editor)
        self.addWidget(self.preview)
        self.mode = "editor"

    def set_mode(self, mode: str):
        self.mode = "preview" if mode == "preview" else "editor"
        self.setCurrentIndex(self.PREVIEW if self.mode == "preview" else self.EDITOR)

    @property
    def is_editor(self) -> bool:
        return self.mode == "editor"

    def active_widget(self):
        return self.preview if self.mode == "preview" else self.editor