"""Jurnal pemulihan untuk ketikan yang belum tersimpan.

Autosave berjalan tiap beberapa menit; jurnal ini ditulis tiap beberapa detik.
Kalau aplikasi mati mendadak, isi terakhir masih bisa diambil dan dipulihkan.
"""
import json
import time
from pathlib import Path

from .diskio import atomic_write

RECOVERY_DIR = ".recovery"
MAX_AGE_SECONDS = 7 * 24 * 3600


def journal_path(project_root, path) -> Path:
    return Path(project_root) / RECOVERY_DIR / (Path(path).stem + ".json")


def write_journal(project_root, path, text: str) -> Path:
    target = journal_path(project_root, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {"path": str(Path(path)), "saved_at": time.time(), "text": text}
    atomic_write(target, json.dumps(record))
    return target


def read_journal(project_root, path):
    target = journal_path(project_root, path)
    if not target.exists():
        return None
    try:
        record = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if Path(record.get("path", "")) != Path(path):
        return None
    if not isinstance(record.get("text"), str):
        return None
    return record


def clear_journal(project_root, path) -> None:
    try:
        journal_path(project_root, path).unlink()
    except OSError:
        pass


def prune(project_root) -> int:
    folder = Path(project_root) / RECOVERY_DIR
    if not folder.is_dir():
        return 0
    removed = 0
    now = time.time()
    for candidate in folder.glob("*.json"):
        try:
            if now - candidate.stat().st_mtime > MAX_AGE_SECONDS:
                candidate.unlink()
                removed += 1
        except OSError:
            continue
    return removed