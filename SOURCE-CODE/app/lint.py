"""Pemeriksa ringan: bukan style guide, hanya kesalahan yang benar-benar merusak
markdown atau membingungkan saat naskah diekspor."""
import re
from pathlib import Path

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]*)[^)]*\)")


def lint_text(text: str, base_dir=None):
    """Kembalikan [(nomor_baris, tingkat, pesan)]. tingkat: 'warn' atau 'info'."""
    issues = []
    lines = text.split("\n")

    prev_level = 0
    fence_open = False
    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            fence_open = not fence_open

        if not stripped.startswith("```"):
            m = re.match(r"^(#{1,6})(\s|$)", stripped)
            if m:
                level = len(m.group(1))
                if level > prev_level + 1 and prev_level > 0:
                    issues.append((i, "warn",
                                   f"heading jumps from H{prev_level} to H{level}"))
                if not stripped[level:].strip():
                    issues.append((i, "warn", "heading has no title"))
                prev_level = level

            for mm in LINK_RE.finditer(line):
                target = mm.group(2)
                if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                if base_dir:
                    candidate = (Path(base_dir) / target.split("#")[0])
                    if target and not candidate.exists():
                        issues.append((i, "warn", f"link target not found: {target}"))

            if line.count("**") % 2:
                issues.append((i, "warn", "unbalanced bold marker (**)"))
            if line.count("`") % 2:
                issues.append((i, "info", "unbalanced backtick"))

            if len(line) - len(line.rstrip(" ")) == 1:
                issues.append((i, "info", "single trailing space"))

    if fence_open:
        issues.append((len(lines), "warn", "unclosed code fence (```)"))
    return issues