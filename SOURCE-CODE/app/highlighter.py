"""Dua highlighter yang hidup di atas satu QTextDocument.

1. MarkdownHighlighter -- mode "formatted source": tebal/miring/heading/code
   benar-benar ter-render, sementara penanda (`**`, `#`, backtick) diredupkan.
2. SearchHighlighter -- sorotan pencarian yang persisten.

Keduanya bekerja per blok. Itu sebabnya sorotan tidak tersendat di naskah
panjang: hanya paragraf yang berubah yang dihitung ulang.
"""
import re

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

HEADING_RE = re.compile(r"^(#{1,6})([ \t]+.*)?$")
BOLD_RE = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
ITAL_RE = re.compile(r"(?<![\*_\w])(\*|_)(?=\S)(.+?)(?<=\S)\1(?![\*_\w])")
CODE_RE = re.compile(r"(`+)([^`]+?)\1")
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]*)[^)]*\)")
QUOTE_RE = re.compile(r"^[ \t]*(>[ \t]?)")
LIST_RE = re.compile(r"^([ \t]*(?:[-*+]|\d+[.)])[ \t])")
RULE_RE = re.compile(r"^[ \t]*(?:---+|\*\*\*+|___+)[ \t]*$")


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _is_whole_word(text: str, start: int, end: int) -> bool:
    left_ok = start == 0 or not _is_word_char(text[start - 1])
    right_ok = end >= len(text) or not _is_word_char(text[end])
    return left_ok and right_ok


def _raw_spans(hay: str, needle: str, cap: int):
    out = []
    if not needle:
        return out
    index = hay.find(needle)
    while index != -1:
        out.append((index, index + len(needle)))
        if len(out) >= cap:
            break
        index = hay.find(needle, index + len(needle))
    return out


class MarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, document, theme_name="day", base_point=12.0):
        super().__init__(document)
        self.enabled = True
        self.base_point = float(base_point)
        self._build(theme_name)

    # -- konfigurasi ----------------------------------------------------
    def _build(self, theme_name):
        from .theme import colors

        c = colors(theme_name)
        self.dim = QColor(c["dim"])
        self.heading_col = QColor(c["heading"])
        self.accent = QColor(c["accent"])
        self.code_bg = QColor(c["code_bg"])

        self.fmt_marker = QTextCharFormat()
        self.fmt_marker.setForeground(self.dim)

        self.fmt_bold = QTextCharFormat()
        self.fmt_bold.setFontWeight(QFont.Bold)

        self.fmt_ital = QTextCharFormat()
        self.fmt_ital.setFontItalic(True)

        self.fmt_code = QTextCharFormat()
        self.fmt_code.setFontFamilies(["monospace"])
        self.fmt_code.setBackground(self.code_bg)
        self.fmt_code.setForeground(self.accent)

        self.fmt_link_text = QTextCharFormat()
        self.fmt_link_text.setForeground(self.accent)
        self.fmt_link_text.setFontUnderline(True)

    def set_theme(self, theme_name):
        self._build(theme_name)
        self.rehighlight()

    def set_enabled(self, on):
        self.enabled = bool(on)
        self.rehighlight()

    def set_base_point(self, point):
        self.base_point = float(point)
        self.rehighlight()

    # -- inti -----------------------------------------------------------
    def highlightBlock(self, text):
        if not self.enabled or not text:
            return

        if RULE_RE.match(text):
            self.setFormat(0, len(text), self.fmt_marker)
            return

        m = HEADING_RE.match(text)
        if m:
            level = len(m.group(1))
            f = QTextCharFormat()
            f.setForeground(self.heading_col)
            f.setFontWeight(QFont.Bold)
            f.setFontPointSize(max(1.0, self.base_point + (6 - level) * 1.3))
            self.setFormat(0, len(text), f)
            self.setFormat(0, level, self.fmt_marker)
            return

        m = QUOTE_RE.match(text)
        if m:
            self.setFormat(m.start(1), len(m.group(1)), self.fmt_marker)

        m = LIST_RE.match(text)
        if m:
            self.setFormat(m.start(1), len(m.group(1)), self.fmt_marker)

        for rx, fmt in ((CODE_RE, self.fmt_code), (BOLD_RE, self.fmt_bold),
                        (ITAL_RE, self.fmt_ital)):
            for mm in rx.finditer(text):
                self.setFormat(mm.start(), len(mm.group(0)), fmt)
                # penanda ikut redup: grup 1 (pembuka) & grup 3 (penutup)
                for gi in (1, 3):
                    try:
                        start, end = mm.start(gi), mm.end(gi)
                    except (IndexError, TypeError):
                        continue
                    if start >= 0 and end > start:
                        self.setFormat(start, end - start, self.fmt_marker)

        for mm in LINK_RE.finditer(text):
            self.setFormat(mm.start(1), len(mm.group(1)), self.fmt_link_text)
            tail = mm.end(1)
            self.setFormat(tail, len(mm.group(0)) - (tail - mm.start()), self.fmt_marker)


class SearchHighlighter(QSyntaxHighlighter):
    """Sorotan yang tidak peduli kamu sedang mengetik.

    Pencocokan selalu dihitung ulang dari teks terkini, jadi kata yang sudah
    kamu ganti otomatis berhenti tersorot, sementara kata lain tetap menyala.
    """

    MAX_PER_BLOCK = 800
    MAX_TOTAL = 20000

    def __init__(self, document, theme_name="day"):
        super().__init__(document)
        self.query = ""
        self.case = False
        self.use_regex = False
        self.whole_word = True
        self.active = -1
        self._build(theme_name)

    def _build(self, theme_name):
        from .theme import colors

        c = colors(theme_name)
        self.fmt_normal = QTextCharFormat()
        self.fmt_normal.setBackground(QColor(c["match"]))
        self.fmt_normal.setForeground(QColor(c["match_fg"]))

        self.fmt_active = QTextCharFormat()
        self.fmt_active.setBackground(QColor(c["match_active"]))
        self.fmt_active.setForeground(QColor(c["match_fg"]))
        self.fmt_active.setFontWeight(QFont.Bold)

    def set_theme(self, theme_name):
        self._build(theme_name)
        self.rehighlight()

    # -- pemindaian -----------------------------------------------------
    def _compile(self):
        if not self.use_regex:
            return None
        try:
            return re.compile(self.query, 0 if self.case else re.IGNORECASE)
        except re.error:
            return False

    def spans(self, text, cap=None):
        cap = cap or self.MAX_PER_BLOCK
        q = self.query
        if not q:
            return []
        out = []
        rx = self._compile()
        if rx is False:
            return []
        if rx is not None:
            for m in rx.finditer(text):
                if m.end() > m.start():
                    out.append((m.start(), m.end()))
                    if len(out) >= cap:
                        break
            return out

        needle = q if self.case else q.lower()
        hay = text if self.case else text.lower()
        if self.whole_word:
            return [(s, e) for s, e in _raw_spans(hay, needle, cap)
                    if _is_whole_word(text, s, e)]
        if len(hay) != len(text):  # unicode aneh (mis. 'İ'); pakai regex saja
            try:
                rx = re.compile(re.escape(q), 0 if self.case else re.IGNORECASE)
            except re.error:
                return []
            return [(m.start(), m.end()) for m in rx.finditer(text)][:cap]
        return _raw_spans(hay, needle, cap)
        while i != -1:
            out.append((i, i + len(needle)))
            if len(out) >= cap:
                break
            i = hay.find(needle, i + len(needle))
        return out

    def find_all(self, text):
        """Posisi awal setiap kecocokan di seluruh dokumen (untuk navigasi)."""
        return [s for s, _ in self.spans(text, cap=self.MAX_TOTAL)]

    def count(self, text):
        return len(self.spans(text, cap=self.MAX_TOTAL))

    # -- konfigurasi ----------------------------------------------------
    def set_query(self, query, case=None, use_regex=None, whole_word=None):
        if case is not None:
            self.case = bool(case)
        if use_regex is not None:
            self.use_regex = bool(use_regex)
        if whole_word is not None:
            self.whole_word = bool(whole_word)
        self.query = query or ""
        self.active = -1
        self.rehighlight()

    def set_active(self, pos):
        self.active = pos
        self.rehighlight()

    def highlightBlock(self, text):
        if not self.query or not text:
            return
        base = self.currentBlock().position()
        for s, e in self.spans(text):
            fmt = self.fmt_active if (base + s) == self.active else self.fmt_normal
            self.setFormat(s, e - s, fmt)