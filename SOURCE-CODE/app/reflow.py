"""Merapikan naskah yang barisnya dipatahkan manual.

Naskah yang ditempel dari mana pun sering punya baris keras di tengah paragraf.
Di editor, itu terlihat seperti teks yang berhenti jauh sebelum tepi kanan --
makin sempit panelnya, makin parah. Fungsi di sini menyambung kembali baris
dalam satu paragraf menjadi satu baris panjang, tanpa menyentuh struktur
markdown (heading, list, kutipan, tabel, blok kode).
"""
import re

STRUCTURAL = re.compile(r"^\s*(#{1,6}\s|[-*+]\s|\d+[.)]\s|>|\||```|~~~|---+|\*\*\*+|___+)")


def reflow_paragraphs(text: str) -> tuple[str, int]:
    """Gabungkan baris dalam satu paragraf. Kembalikan (teks_baru, jumlah_paragraf)."""
    lines = text.split("\n")
    out = []
    buffer = []
    changed = 0
    in_fence = False

    def flush():
        nonlocal buffer, changed
        if len(buffer) > 1:
            out.append(" ".join(part.strip() for part in buffer if part.strip()))
            changed += 1
        elif buffer:
            out.append(buffer[0])
        buffer = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith(("```", "~~~")):
            flush()
            in_fence = not in_fence
            out.append(line)
            continue

        if in_fence or not stripped:
            flush()
            if not stripped and not in_fence:
                out.append(line)
            elif in_fence:
                out.append(line)
            continue

        if STRUCTURAL.match(stripped):
            flush()
            out.append(line)
            continue

        buffer.append(line)

    flush()
    result = "\n".join(out)
    # pertahankan jumlah baris kosong berlebih apa adanya
    if result.strip() == text.strip():
        return text, 0
    return result, changed