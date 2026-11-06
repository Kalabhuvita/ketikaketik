"""Tata letak preview: bedakan "baris baru" dari "paragraf baru".

Masalahnya: mesin markdown Qt memperlakukan baris baru dan baris kosong sama
saja -- keduanya jadi paragraf baru, dan tiga baris baru pun hasilnya sama.
Akibatnya preview tidak bisa membedakan 1x Enter (baris baru) dari 2x Enter
(paragraf baru), seperti yang dilakukan Obsidian.

Pendekatan di sini: biarkan Qt merender struktur markdown-nya, lalu:
  * baris-baris yang berasal dari satu paragraf disatukan kembali menjadi satu
    blok, dengan pemisah baris (U+2028) di antara barisnya;
  * blok pertama setiap paragraf diberi jarak atas, sehingga paragraf baru
    terlihat sebagai paragraf, bukan sekadar baris baru.
"""
import re

LINE_SEPARATOR = "\u2028"

MARKER_RE = re.compile(r"^(#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
EMPH_RE = re.compile(r"(?<!\w)[*_](\S.*?)[*_](?!\w)")
FENCE = ("```", "~~~")


def plain(line: str) -> str:
    """Teks sebuah baris tanpa penanda markdown (untuk mencocokkan blok)."""
    text = MARKER_RE.sub("", line.strip())
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = LINK_RE.sub(r"\1", text)
    text = EMPH_RE.sub(r"\1", text)
    return text.strip()


def paragraphs(text: str):
    """Pecah sumber menjadi paragraf (dipisah baris kosong). Blok kode utuh."""
    result = []
    current = []
    in_fence = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(FENCE):
            in_fence = not in_fence
            current.append(line)
            continue
        if in_fence:
            current.append(line)
            continue
        if not stripped:
            if current:
                result.append(current)
                current = []
            continue
        current.append(line)
    if current:
        result.append(current)
    return result


def apply_layout(document, text: str, paragraph_gap: int = 10) -> None:
    """Susun ulang dokumen hasil render: baris rapat, paragraf berjarak."""
    groups = paragraphs(text)
    if not groups:
        return

    blocks = []
    block = document.firstBlock()
    while block.isValid():
        blocks.append(block)
        block = block.next()
    if not blocks:
        return

    # 1. cocokkan setiap paragraf sumber ke blok hasil render
    starts = []
    search_from = 0
    for group in groups:
        needle = plain(group[0])[:40]
        found = None
        for index in range(search_from, len(blocks)):
            candidate = blocks[index].text()
            if needle and needle[:18] in candidate:
                found = index
                break
        if found is None:
            found = min(search_from, len(blocks) - 1)
        starts.append(found)
        search_from = min(found + 1, len(blocks))

    # 2. jarak antar paragraf (format blok -- tidak menggeser teks)
    from PySide6.QtGui import QTextBlockFormat, QTextCursor

    starts_set = set(starts)
    for index, block in enumerate(blocks):
        if not block.isValid():
            continue
        margin = paragraph_gap if index in starts_set and index > 0 else 0
        block_format = block.blockFormat()
        if int(block_format.topMargin()) != margin:
            block_format.setTopMargin(margin)
            cursor = QTextCursor(block)
            cursor.setBlockFormat(block_format)

    # 3. sisipkan pemisah baris di dalam paragraf yang punya beberapa baris
    edits = []
    for position, group in enumerate(groups):
        start = starts[position]
        end = starts[position + 1] if position + 1 < len(starts) else len(blocks)
        span = blocks[start:end]
        if len(group) < 2 or len(span) != 1:
            continue          # daftar/kutipan/heading: biarkan strukturnya

        target = span[0]
        remaining = target.text()
        offset = 0
        for line in group[1:]:
            needle = plain(line)
            if not needle:
                continue
            index = remaining.find(needle, offset)
            if index < 0:
                break
            absolute = target.position() + index
            # ganti spasi penghubung dengan pemisah baris
            if index > 0 and remaining[index - 1] == " ":
                absolute -= 1
            edits.append(absolute)
            offset = index + len(needle)

    for absolute in sorted(edits, reverse=True):
        cursor = QTextCursor(document)
        cursor.setPosition(max(0, absolute))
        cursor.setPosition(min(len(document.toPlainText()), absolute + 1),
                           QTextCursor.KeepAnchor)
        cursor.insertText(LINE_SEPARATOR)