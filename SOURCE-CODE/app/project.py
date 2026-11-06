"""Model proyek: satu folder = satu novel. Setiap .md di root = satu bab."""
import fcntl
import json
import os
import re
import time
from pathlib import Path

from PySide6.QtCore import QSettings

from .diskio import (atomic_write, cleanup_temp_files, read_document,
                     signature)

MD_EXT = {".md", ".markdown"}
HISTORY_DIR = ".history"
HISTORY_INTERVAL = 600      # detik; snapshot paling cepat 10 menit sekali
HISTORY_KEEP = 40           # snapshot per bab yang disimpan
RECENT_MAX = 10

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")


def _hidden_map() -> dict:
    raw = QSettings().value("hidden/map", "")
    if isinstance(raw, dict):
        return dict(raw)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _save_hidden_map(mapping: dict):
    QSettings().setValue("hidden/map", json.dumps(mapping))


RECENT_FILES_MAX = 12


def add_recent_file(path):
    """Catat file yang dibuka lewat Open File (terpisah dari daftar proyek)."""
    files = load_recent_files()
    target = str(Path(path))
    files = [item for item in files if item != target]
    files.insert(0, target)
    files = files[:RECENT_FILES_MAX]
    QSettings().setValue("recent/files", json.dumps(files))
    return files


def load_recent_files():
    raw = QSettings().value("recent/files", "[]")
    if isinstance(raw, dict):
        return [str(v) for v in raw.values()]
    if isinstance(raw, str):
        try:
            values = json.loads(raw or "[]")
        except ValueError:
            return []
        return [str(v) for v in values if isinstance(v, str)]
    return []


def remove_recent_file(path):
    target = str(Path(path))
    files = [item for item in load_recent_files() if item != target]
    QSettings().setValue("recent/files", json.dumps(files))
    return files


def natural_key(path: Path):
    parts = re.split(r"(\d+)", path.name.lower())
    return [int(p) if p.isdigit() else p for p in parts]


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:60] or "chapter"


def headings_of(text: str):
    """[(level, judul, indeks_blok)] dari satu naskah."""
    out = []
    for i, line in enumerate(text.split("\n")):
        m = HEADING_RE.match(line.strip())
        if m:
            out.append((len(m.group(1)), m.group(2).strip(), i))
    return out


class Project:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.name = self.root.name
        self.chapters = []
        self.scan()

    # -- daftar bab -----------------------------------------------------
    def _all_files(self):
        if not self.root.is_dir():
            return []
        files = [p for p in self.root.iterdir()
                 if p.is_file() and p.suffix.lower() in MD_EXT and not p.name.startswith(".")]
        files.sort(key=natural_key)
        return files

    def scan(self):
        """Daftar bab = semua .md di root, minus yang disembunyikan dari proyek."""
        hidden = set(self.hidden_names())
        files = [p for p in self._all_files() if p.name not in hidden]
        self.chapters = files

        # buang sisa file sementara dari proses yang mati di tengah menulis
        cleanup_temp_files(self.root)
        try:
            from .recovery import prune
            prune(self.root)
        except OSError:
            pass
        return files

    # -- bab yang disembunyikan (file tetap di tempatnya) ----------------
    def hidden_names(self):
        names = _hidden_map().get(str(self.root), [])
        if isinstance(names, str):
            names = [names]
        return [str(n) for n in (names or [])]

    def _set_hidden(self, names):
        mapping = _hidden_map()
        mapping[str(self.root)] = sorted(set(names))
        _save_hidden_map(mapping)
        self.scan()

    def hidden_chapters(self):
        hidden = set(self.hidden_names())
        return [p for p in self._all_files() if p.name in hidden]

    def hide_chapter(self, path):
        """Keluarkan dari proyek tanpa menyentuh file di disk."""
        names = self.hidden_names()
        names.append(Path(path).name)
        self._set_hidden(names)

    def restore_chapter(self, name):
        self._set_hidden([n for n in self.hidden_names() if n != Path(name).name])

    def rel(self, path) -> str:
        try:
            return str(Path(path).relative_to(self.root))
        except ValueError:
            return Path(path).name

    def chapter_paths(self):
        return list(self.chapters)

    def index_of(self, path):
        p = Path(path).resolve()
        for i, c in enumerate(self.chapters):
            if c.resolve() == p:
                return i
        return -1

    # -- baca / tulis ---------------------------------------------------
    def read(self, path) -> str:
        return read_document(path)[0]

    def read_with_meta(self, path):
        """(teks, meta) -- meta dipakai lagi saat menyimpan (izin, BOM, CRLF)."""
        return read_document(path)

    # -- kunci proyek: cegah dua jendela saling menimpa -------------------
    def acquire_lock(self) -> bool:
        lock_path = self.root / HISTORY_DIR / "ketikaketik.lock"
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(lock_path, "w")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        self._lock_handle = handle
        return True

    def release_lock(self) -> None:
        handle = getattr(self, "_lock_handle", None)
        if not handle:
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()
        self._lock_handle = None

    def save(self, path, text: str, snapshot=True, force_snapshot=False,
             meta=None) -> Path:
        """Tulis naskah dengan pengamanan penuh; kembalikan path yang ditulis."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        old = None
        meta = dict(meta or {})
        if path.exists():
            try:
                old, existing_meta = read_document(path)
                if not meta:
                    meta = existing_meta
            except OSError:
                old = None
        if meta.get("readonly"):
            raise PermissionError(
                f"{path.name} is not valid UTF-8; saving is disabled to protect its bytes")

        written = atomic_write(path, text, meta)
        if snapshot and old is not None and old != text:
            self._snapshot(path, old, force=force_snapshot)
        return written

    # -- riwayat --------------------------------------------------------
    def history_dir(self, path) -> Path:
        return self.root / HISTORY_DIR / Path(path).stem

    def snapshots(self, path):
        d = self.history_dir(path)
        return sorted(d.glob("*.md")) if d.is_dir() else []

    def _snapshot(self, path, text: str, force: bool = False):
        """Simpan versi lama. Setiap isi yang berbeda disimpan -- tidak dibatasi waktu."""
        d = self.history_dir(path)
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        existing = sorted(d.glob("*.md"))
        if existing:
            try:
                if existing[-1].read_text(encoding="utf-8", errors="replace") == text:
                    return              # versi ini sudah ada
            except OSError:
                pass
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = d / f"{Path(path).stem}-{stamp}.md"
        if target.exists():
            target = d / f"{Path(path).stem}-{stamp}-{int(time.time() * 1000) % 1000:03d}.md"
        try:
            atomic_write(target, text)
        except OSError:
            return
        for extra in sorted(d.glob("*.md"))[:-HISTORY_KEEP]:
            try:
                extra.unlink()
            except OSError:
                pass

    # -- bab baru / ubah nama / hapus ------------------------------------
    def next_number(self) -> int:
        nums = []
        for c in self.chapters:
            m = re.match(r"(\d+)", c.name)
            if m:
                nums.append(int(m.group(1)))
        return (max(nums) + 1) if nums else 1

    def create_chapter(self, title: str) -> Path:
        title = title.strip() or "New Chapter"
        num = self.next_number()
        while True:
            candidate = self.root / f"{num:02d}-{slugify(title)}.md"
            if not candidate.exists():
                break
            num += 1
        candidate.write_text(f"# {title}\n\n", encoding="utf-8")
        self.scan()
        return candidate

    def rename_chapter(self, path, new_name: str) -> Path:
        src = Path(path)
        new_name = new_name.strip()
        if not new_name.lower().endswith(".md"):
            new_name += ".md"
        dst = src.with_name(new_name)
        if dst.exists() and dst.resolve() != src.resolve():
            raise FileExistsError(dst.name)
        src.rename(dst)
        self.scan()
        return dst

    def delete_chapter(self, path):
        src = Path(path)
        trash = self.root / HISTORY_DIR / "deleted"
        trash.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        src.rename(trash / f"{src.stem}-{stamp}.md")
        self.scan()

    def total_words(self) -> int:
        from .stats import count_words
        total = 0
        for c in self.chapters:
            try:
                total += count_words(self.read(c))
            except OSError:
                pass
        return total


# -- recent proyek (disimpan di QSettings) --------------------------------
def load_recent():
    value = QSettings().value("recent/projects", [])
    if isinstance(value, str):
        value = [value]
    return [str(p) for p in (value or []) if p and Path(p).is_dir()]


def add_recent(path):
    items = [p for p in load_recent() if Path(p) != Path(path)]
    items.insert(0, str(Path(path)))
    QSettings().setValue("recent/projects", items[:RECENT_MAX])
    return items[:RECENT_MAX]


def remove_recent(path):
    items = [p for p in load_recent() if Path(p) != Path(path)]
    QSettings().setValue("recent/projects", items)
    return items
