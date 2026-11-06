"""Bagian naskah berdasarkan heading Markdown.

Satu file = satu novel; heading (#, ##, ###) membagi novel menjadi bagian.
Dipakai untuk cakupan "This section" di jendela analisis.
"""
import re

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def headings(text: str):
    """[(nomor_baris, level, judul)] untuk setiap heading di naskah."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = HEADING.match(line.strip())
        if match:
            found.append((number, len(match.group(1)), match.group(2).strip()))
    return found


def section_at(text: str, line: int):
    """(baris_awal, baris_akhir, judul) bagian yang memuat `line` (1-based)."""
    lines = text.splitlines()
    total = len(lines)
    items = headings(text)
    if not items:
        return 1, total, ""

    current = None
    for item in items:
        if item[0] <= line:
            current = item
        else:
            break
    if current is None:
        # di atas heading pertama: itu bagian pembuka
        return 1, max(1, items[0][0] - 1), ""

    start, level, title = current
    end = total
    for number, other_level, _other_title in items:
        if number > start and other_level <= level:
            end = number - 1
            break
    return start, max(start, end), title


def section_text(text: str, line: int):
    """(teks bagian, judul) -- kosong kalau naskah belum punya heading."""
    start, end, title = section_at(text, line)
    lines = text.splitlines()
    return "\n".join(lines[start - 1:end]), title