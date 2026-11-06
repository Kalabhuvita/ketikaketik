"""Baca/tulis file naskah dengan jaminan tidak merusak data.

Aturan yang dipegang:
  * file asli tidak pernah ditulis langsung -- selalu lewat file sementara di
    folder yang sama, di-fsync, lalu diganti dengan os.replace (atomik);
  * folder ikut di-fsync supaya penggantian nama bertahan saat listrik mati;
  * setelah menulis, isi file dibaca ulang dan dibandingkan byte-per-byte;
  * izin file, symlink, BOM, dan gaya baris baru (LF/CRLF) dipertahankan;
  * file yang bukan UTF-8 tidak pernah ditulis balik (dibuka read-only),
    supaya byte aslinya tidak hancur.
"""
import os
import stat
import tempfile
from pathlib import Path

TEMP_SUFFIX = ".ktktmp"
STALE_TEMP_SECONDS = 3600


class DiskError(OSError):
    """Kegagalan menulis yang tidak boleh diabaikan."""


def resolve_target(path) -> Path:
    """Ikuti symlink supaya yang ditulis adalah file aslinya, bukan link-nya."""
    target = Path(path)
    try:
        if target.is_symlink():
            return target.resolve(strict=False)
    except OSError:
        pass
    return target


def _newline_style(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _default_mode() -> int:
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def read_document(path):
    """Kembalikan (teks, meta). Meta dipakai lagi saat menyimpan."""
    target = resolve_target(path)
    raw = target.read_bytes()

    meta = {
        "path": target,
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "readonly": False,
        "newline": "\n",
        "mode": stat.S_IMODE(target.stat().st_mode),
    }

    try:
        text = raw.decode("utf-8-sig") if meta["bom"] else raw.decode("utf-8")
    except UnicodeDecodeError:
        # bukan UTF-8: bisa dibaca, tetapi tidak boleh ditulis balik
        text = raw.decode("latin-1")
        meta["readonly"] = True
        meta["newline"] = _newline_style(text)
        return text, meta

    meta["newline"] = _newline_style(text)
    return text, meta


def _fsync_dir(path: Path) -> None:
    try:
        handle = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def atomic_write(path, text: str, meta=None) -> Path:
    """Tulis teks ke `path` tanpa pernah meninggalkan file setengah jadi."""
    meta = dict(meta or {})
    if meta.get("readonly"):
        raise PermissionError(
            f"{Path(path).name} is not valid UTF-8; writing is disabled to protect its bytes")
    target = resolve_target(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    newline = meta.get("newline", "\n")
    body = text.replace("\r\n", "\n")
    if newline != "\n":
        body = body.replace("\n", newline)
    if meta.get("bom"):
        body = "\ufeff" + body

    payload = body.encode("utf-8")
    mode = meta.get("mode")
    if mode is None:
        try:
            mode = stat.S_IMODE(target.stat().st_mode)
        except OSError:
            mode = _default_mode()

    handle, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=TEMP_SUFFIX, dir=str(target.parent))
    temp_path = Path(temp_name)
    temp_inode = None
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
            temp_inode = os.fstat(stream.fileno()).st_ino
        os.chmod(temp_path, mode)

        # verifikasi isi file sementara SEBELUM dipublikasikan
        if temp_path.read_bytes() != payload:
            raise DiskError(f"short write while preparing {target}")

        os.replace(temp_path, target)
        _fsync_dir(target.parent)
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise

    # Setelah rename: kalau inode-nya masih milik kita, isinya wajib sama.
    # Kalau inode berbeda, proses lain baru saja menimpa -- penulisan kita
    # tetap atomik, jadi itu bukan kerusakan.
    try:
        if target.stat().st_ino == temp_inode:
            if target.read_bytes() != payload:
                raise DiskError(f"verification failed for {target}")
    except FileNotFoundError:
        raise DiskError(f"{target} disappeared right after writing")
    return target


def cleanup_temp_files(directory, older_than=STALE_TEMP_SECONDS) -> int:
    """Buang sisa file sementara dari proses yang mati di tengah penulisan."""
    import time

    removed = 0
    folder = Path(directory)
    if not folder.is_dir():
        return 0
    now = time.time()
    for candidate in folder.glob(f"*{TEMP_SUFFIX}"):
        try:
            if now - candidate.stat().st_mtime > older_than:
                candidate.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def signature(path):
    """(mtime_ns, ukuran) untuk mendeteksi perubahan dari luar."""
    try:
        info = Path(path).stat()
        return (info.st_mtime_ns, info.st_size)
    except OSError:
        return None