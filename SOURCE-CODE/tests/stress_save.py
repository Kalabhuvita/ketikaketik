"""Uji ketahanan penyimpanan: tidak boleh ada naskah yang rusak.

Dijalankan terpisah dari uji asap karena menjalankan ratusan siklus tulis-baca
dan beberapa proses anak yang sengaja dibunuh di tengah penulisan.

    /usr/bin/python3 tests/stress_save.py
"""
import json
import multiprocessing as mp
import os
import random
import shutil
import signal
import stat
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import diskio, recovery
from app.project import Project

TMP = Path(tempfile.mkdtemp(prefix="ktkt-stress-"))
passed = []
failed = []


def check(name, condition, extra=""):
    if condition:
        passed.append(name)
        print(f"  ok  {name}")
    else:
        failed.append(f"{name} :: {extra}")
        print(f"FAIL  {name}  {extra}")


def random_text(seed: int) -> str:
    rng = random.Random(seed)
    alphabet = "abcdefghijklmnopqrstuvwxyz ABC .,;!?\n\n"
    extra = ["é", "ü", "ñ", "→", "…", "“", "”", "😀", "中", "—"]
    chunks = []
    for _ in range(rng.randint(5, 60)):
        line = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 90)))
        if rng.random() < 0.2:
            line += rng.choice(extra)
        chunks.append(line)
    return "\n".join(chunks)


# ---------------------------------------------------------------- inti tulis
def test_roundtrip():
    project_dir = TMP / "proj-roundtrip"
    project_dir.mkdir()
    project = Project(project_dir)
    target = project_dir / "01-bab.md"

    for i in range(300):
        text = random_text(i)
        project.save(target, text, snapshot=False)
        loaded, meta = project.read_with_meta(target)
        if loaded != text:
            check(f"roundtrip #{i}", False, "isi berubah setelah disimpan")
            return
    check("300 siklus simpan-baca identik", True)

    # tidak ada file sementara yang tertinggal
    leftovers = list(project_dir.glob(f"*{diskio.TEMP_SUFFIX}"))
    check("tidak ada file sementara tertinggal", not leftovers, leftovers)


def test_metadata():
    folder = TMP / "meta"
    folder.mkdir()
    target = folder / "bom.md"
    target.write_bytes(b"\xef\xbb\xbfbaris satu\r\nbaris dua\r\n")
    os.chmod(target, 0o640)

    text, meta = diskio.read_document(target)
    check("BOM dikenali", meta["bom"] is True)
    check("CRLF dikenali", meta["newline"] == "\r\n", meta["newline"])
    check("BOM tidak ikut ke teks", not text.startswith("\ufeff"))

    diskio.atomic_write(target, text + "baris tiga\n", meta)
    raw = target.read_bytes()
    check("BOM dipertahankan saat menulis", raw.startswith(b"\xef\xbb\xbf"))
    check("CRLF dipertahankan", b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""))
    check("izin file dipertahankan", stat.S_IMODE(target.stat().st_mode) == 0o640,
          oct(stat.S_IMODE(target.stat().st_mode)))

    # symlink harus tetap symlink
    real = folder / "asli.md"
    real.write_text("asli\n", encoding="utf-8")
    link = folder / "tautan.md"
    link.symlink_to(real)
    diskio.atomic_write(link, "lewat symlink\n", {})
    check("symlink tidak diganti file biasa", link.is_symlink())
    check("isi target ikut berubah", real.read_text(encoding="utf-8") == "lewat symlink\n")

    # file bukan UTF-8: boleh dibaca, tidak boleh ditimpa
    latin = folder / "latin.md"
    latin.write_bytes("café\n".encode("latin-1"))
    before = latin.read_bytes()
    text, meta = diskio.read_document(latin)
    check("file non-UTF8 ditandai read-only", meta["readonly"] is True)
    try:
        diskio.atomic_write(latin, text + "x", meta)
        check("penulisan file non-UTF8 ditolak", False, "tidak melempar error")
    except PermissionError:
        check("penulisan file non-UTF8 ditolak", True)
    check("byte file non-UTF8 tidak berubah", latin.read_bytes() == before)


def test_failure_paths():
    folder = TMP / "gagal"
    folder.mkdir()
    target = folder / "naskah.md"
    target.write_text("versi awal\n", encoding="utf-8")

    original_replace = os.replace
    def boom(*args, **kwargs):
        raise OSError(28, "No space left on device")
    os.replace = boom
    try:
        diskio.atomic_write(target, "versi baru\n", {})
        check("tulis gagal saat rename error", False, "tidak melempar error")
    except OSError:
        check("tulis gagal saat rename error", True)
    finally:
        os.replace = original_replace
    check("file lama utuh setelah gagal", target.read_text(encoding="utf-8") == "versi awal\n")
    check("tidak ada temp tertinggal setelah gagal",
          not list(folder.glob(f"*{diskio.TEMP_SUFFIX}")))

    # fsync gagal (disk bermasalah) -> file lama tetap utuh
    original_fsync = os.fsync
    def bad_fsync(fd):
        raise OSError(5, "Input/output error")
    os.fsync = bad_fsync
    try:
        diskio.atomic_write(target, "versi gagal\n", {})
        check("tulis gagal saat fsync error", False, "tidak melempar error")
    except OSError:
        check("tulis gagal saat fsync error", True)
    finally:
        os.fsync = original_fsync
    check("file lama utuh setelah fsync gagal",
          target.read_text(encoding="utf-8") == "versi awal\n")

    # verifikasi menangkap kerusakan setelah rename
    original_read = Path.read_bytes
    def corrupt(self):
        data = original_read(self)
        return data[:-1] if self == target else data
    Path.read_bytes = corrupt
    try:
        diskio.atomic_write(target, "versi verifikasi\n", {})
        check("kerusakan setelah tulis terdeteksi", False, "tidak melempar error")
    except diskio.DiskError:
        check("kerusakan setelah tulis terdeteksi", True)
    finally:
        Path.read_bytes = original_read


def test_stale_temp():
    folder = TMP / "stale"
    folder.mkdir()
    stale = folder / f".bab.md.{os.getpid()}{diskio.TEMP_SUFFIX}"
    stale.write_text("sisa", encoding="utf-8")
    old = time.time() - 7200
    os.utime(stale, (old, old))
    fresh = folder / f".bab.md.fresh{diskio.TEMP_SUFFIX}"
    fresh.write_text("baru", encoding="utf-8")
    removed = diskio.cleanup_temp_files(folder)
    check("temp lama dibersihkan", removed == 1 and not stale.exists())
    check("temp baru dibiarkan", fresh.exists())


def test_recovery_journal():
    root = TMP / "jurnal"
    root.mkdir()
    chapter = root / "01-bab.md"
    chapter.write_text("versi disk\n", encoding="utf-8")

    recovery.write_journal(root, chapter, "versi jurnal yang belum disimpan\n")
    record = recovery.read_journal(root, chapter)
    check("jurnal bisa dibaca kembali", record and "belum disimpan" in record["text"])

    path = recovery.journal_path(root, chapter)
    path.write_text("{rusak", encoding="utf-8")
    check("jurnal rusak tidak membuat crash", recovery.read_journal(root, chapter) is None)

    recovery.clear_journal(root, chapter)
    check("jurnal bisa dihapus", not path.exists())

    # jurnal ikut pemulihan proyek dan tidak muncul sebagai bab
    recovery.write_journal(root, chapter, "x\n")
    project = Project(root)
    check("folder jurnal tidak dianggap bab",
          all(c.suffix == ".md" for c in project.chapters), project.chapters)


def test_large_document():
    folder = TMP / "besar"
    folder.mkdir()
    target = folder / "novel.md"
    body = ("Paragraf panjang. " * 60 + "\n\n") * 1200      # ~1 MB
    start = time.time()
    diskio.atomic_write(target, body, {})
    loaded, _ = diskio.read_document(target)
    elapsed = time.time() - start
    check("dokumen 1 MB utuh setelah simpan-baca", loaded == body, f"{elapsed:.2f}s")
    check("menyimpan 1 MB tetap cepat (< 2 detik)", elapsed < 2.0, f"{elapsed:.2f}s")


def _writer_process(path_str: str, marker: str, rounds: int):
    path = Path(path_str)
    payload = (marker * 4000) + "\n"
    for _ in range(rounds):
        diskio.atomic_write(path, payload, {})


def test_kill_mid_write():
    folder = TMP / "kill"
    folder.mkdir()
    target = folder / "korban.md"
    target.write_text("awal\n", encoding="utf-8")

    valid = {"awal\n", ("A" * 4000) + "\n", ("B" * 4000) + "\n"}
    killed = 0
    for round_index in range(12):
        marker = "A" if round_index % 2 == 0 else "B"
        process = mp.Process(target=_writer_process, args=(str(target), marker, 400))
        process.start()
        time.sleep(random.uniform(0.01, 0.08))
        if process.is_alive():
            os.kill(process.pid, signal.SIGKILL)
            killed += 1
        process.join(timeout=5)

        raw = target.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            check(f"siklus bunuh #{round_index}", False, "file tidak valid UTF-8")
            return
        if text not in valid:
            check(f"siklus bunuh #{round_index}", False, f"isi rusak ({len(text)} char)")
            return

    check(f"{killed} proses dibunuh di tengah penulisan, file selalu utuh", True)


def test_two_writers():
    folder = TMP / "dua"
    folder.mkdir()
    target = folder / "bersama.md"
    target.write_text("awal\n", encoding="utf-8")

    procs = [
        mp.Process(target=_writer_process, args=(str(target), m, 60))
        for m in ("A", "B")
    ]
    for process in procs:
        process.start()
    for process in procs:
        process.join(timeout=30)

    text = target.read_text(encoding="utf-8")
    check("dua penulis bersamaan tidak menghasilkan file campuran",
          text in {"awal\n", ("A" * 4000) + "\n", ("B" * 4000) + "\n"},
          f"{len(text)} char")


def main():
    print(f"direktori uji: {TMP}")
    start = time.time()
    test_roundtrip()
    test_metadata()
    test_failure_paths()
    test_stale_temp()
    test_recovery_journal()
    test_large_document()
    test_kill_mid_write()
    test_two_writers()

    print(f"\n{len(passed)} lulus, {len(failed)} gagal  ({time.time() - start:.1f}s)")
    for item in failed:
        print("  -", item)
    shutil.rmtree(TMP, ignore_errors=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())