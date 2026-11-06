"""Ekspor naskah ke .docx dengan format manuskrip standar.

Pandoc dipakai untuk konversi; gaya (Times New Roman 12pt, spasi ganda,
indentasi baris pertama 0,5 inci) ditanamkan lewat reference.docx yang dibuat
sekali di cache, bukan bergantung pada setelan pandoc default.
"""
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .softbreaks import with_hard_breaks

CACHE = Path.home() / ".cache" / "ketikaketik"

DOC_DEFAULTS = (
    '<w:docDefaults>'
    '<w:rPrDefault><w:rPr>'
    '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>'
    '<w:sz w:val="24"/><w:szCs w:val="24"/>'
    '</w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr>'
    '<w:spacing w:before="0" w:after="0" w:line="480" w:lineRule="auto"/>'
    '<w:ind w:firstLine="720"/>'
    '</w:pPr></w:pPrDefault>'
    '</w:docDefaults>'
)

PAGE_BREAK = (
    '\n\n```{=openxml}\n'
    '<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n'
    '```\n\n'
)


class ExportError(RuntimeError):
    pass


def pandoc_path():
    return shutil.which("pandoc")


def _build_reference(dest: Path):
    pandoc = pandoc_path()
    if not pandoc:
        raise ExportError("pandoc was not found in PATH.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = dest.with_suffix(".raw.docx")
    subprocess.run([pandoc, "-f", "markdown", "-t", "docx", "-o", str(raw)],
                   input=b"reference\n", check=True, capture_output=True)

    with zipfile.ZipFile(raw) as z:
        items = {name: z.read(name) for name in z.namelist()}
    raw.unlink(missing_ok=True)

    styles = items["word/styles.xml"].decode("utf-8")
    patched = re.sub(r"<w:docDefaults>.*?</w:docDefaults>", DOC_DEFAULTS,
                     styles, count=1, flags=re.S)
    if patched == styles:
        raise ExportError("Failed to apply manuscript styles to reference.docx.")
    items["word/styles.xml"] = patched.encode("utf-8")

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in items.items():
            z.writestr(name, data)


def reference_docx() -> Path:
    ref = CACHE / "reference.docx"
    if not ref.exists():
        _build_reference(ref)
    return ref


def export_manuscript(chapters, out_path, title: str = "") -> Path:
    pandoc = pandoc_path()
    if not pandoc:
        raise ExportError("pandoc was not found. Install it with: sudo pacman -S pandoc")
    chapters = [Path(c) for c in chapters]
    if not chapters:
        raise ExportError("This project has no .md chapters yet.")

    parts = []
    if title:
        parts.append(f"# {title}")
    for chapter in chapters:
        try:
            text = chapter.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            # aturan yang sama dengan preview: satu baris baru = patah baris
            parts.append(with_hard_breaks(text))
    if not parts:
        raise ExportError("Every chapter is empty.")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkstemp(suffix=".md", prefix="ketikaketik-")[1])
    try:
        tmp.write_text(PAGE_BREAK.join(parts), encoding="utf-8")
        proc = subprocess.run(
            [pandoc, str(tmp), "-f", "markdown", "-t", "docx",
             "--reference-doc", str(reference_docx()),
             "-o", str(out_path)],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise ExportError(proc.stderr.strip() or "pandoc failed.")
    finally:
        tmp.unlink(missing_ok=True)
    return out_path