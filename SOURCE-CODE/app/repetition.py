"""Analisis repetisi untuk prosa Indonesia.

Yang dihitung:
  * frekuensi kata;
  * kata yang muncul berdekatan dalam beberapa kalimat;
  * frasa klise yang terdengar seperti bahasa laporan, bukan prosa.

Tidak ada kata yang dibuang diam-diam: stopword, partikel, klise, dan kata
kebiasaan fiksi semuanya ikut terhitung dan diberi label, supaya penulis tahu
jenisnya. Penyaringan diserahkan kepada penulis lewat daftar abaikan di jendela.

Semua fungsi murni (tanpa Qt) supaya mudah diuji.
"""
import re
from bisect import bisect_right

from .stats import count_sentences, count_words

# ---------------------------------------------------------------- stopword
TIER_1 = frozenset("""
yang dan atau tetapi tapi namun melainkan sedangkan sementara lalu kemudian
lantas bahwa sehingga maka agar supaya karena sebab kalau jika bila walaupun
meskipun biarpun seolah seakan seperti sebagai
ketika saat setelah sesudah sebelum sejak selama hingga sampai sambil seraya
usai seusai
di ke dari pada dalam untuk bagi oleh dengan tanpa tentang terhadap antara
melalui kepada daripada demi per akan
aku saya kamu kau engkau dia ia mereka kita kami kalian ini itu begitu
demikian tersebut
sudah telah belum masih sedang pernah selalu sering kadang jarang segera
kembali lagi pula juga hanya saja cuma bahkan malah justru memang sangat
sekali terlalu amat cukup agak sedikit hampir nyaris tidak tak bukan jangan
adalah ialah merupakan ada menjadi terjadi berada
satu dua beberapa banyak semua seluruh setiap tiap para seorang sebuah
sebagian kebanyakan masing masing segala
""".split())

TIER_2 = frozenset("""
lah kah pun nya ya iya kan sih dong kok deh nih tuh lho oh ah eh wah aduh
""".split())

# Kata isi yang paling sering mengulang di fiksi pemula.
FICTION_HABITS = frozenset("""
melihat menatap memandang tersenyum berkata mengatakan bertanya merasa
merasakan mengangguk menghela tersentak terdiam menoleh menggeleng
mata matanya tangan tangannya kepala kepalanya wajah wajahnya suara suaranya
""".split())

CLICHES = (
    "hal ini", "hal tersebut", "pada saat itu", "saat itu", "ketika itu",
    "di mana", "yang mana", "seperti yang", "yang merupakan",
    "adalah merupakan", "oleh karena itu", "dengan demikian",
    "di samping itu", "selain itu", "sementara itu",
)

MIN_WORD_LENGTH = 3
MAX_RESULTS = 400

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
# untuk frasa, "hati-hati" tetap satu kata seperti di naskah dan di status bar
_PHRASE_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*", re.UNICODE)
_SENTENCE_END = re.compile(r"[.!?…]+|(?:\n[ \t]*\n)")


def strip_enclitic(word: str) -> str:
    """'matanya' -> 'mata'. Enklitik tidak dihitung sebagai kata sendiri."""
    for suffix in ("nya", "ku", "mu"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def flavor_of(word: str) -> str:
    """Label untuk tooltip: function word / particle / fiction habit / content / cliché."""
    if word in TIER_1:
        return "function word"
    if word in TIER_2 or strip_enclitic(word) in TIER_2:
        return "particle"
    if word in FICTION_HABITS or strip_enclitic(word) in FICTION_HABITS:
        return "fiction habit"
    return "content"


def split_sentences(text: str):
    """[(nomor_baris, kalimat)] -- dipisah titik/tanya/seru dan baris kosong."""
    newlines = [i for i, ch in enumerate(text) if ch == "\n"]

    def line_of(position: int) -> int:
        return bisect_right(newlines, position) + 1

    sentences = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        chunk = text[start:match.end()]
        if chunk.strip():
            sentences.append((line_of(start), chunk.strip()))
        start = match.end()
    tail = text[start:]
    if tail.strip():
        sentences.append((line_of(start), tail.strip()))
    return sentences


def iter_words(sentences):
    """[(kata, baris, indeks_kalimat)] untuk setiap kata di dalam kalimat."""
    for index, (line, sentence) in enumerate(sentences):
        for match in _WORD.finditer(sentence):
            yield match.group(0).lower(), line, index


def frequency(text: str, min_count: int = 3):
    """Semua kata, tanpa penyaringan. Penulis yang memilih apa yang diabaikan."""
    sentences = split_sentences(text)
    # penyebut kepadatan memakai penghitung yang sama dengan status bar,
    # supaya "per 1000" bisa dibandingkan dengan angka naskah
    total = count_words(text)
    counts = {}
    for word, _line, _index in iter_words(sentences):
        if len(word) < MIN_WORD_LENGTH:
            continue
        counts[word] = counts.get(word, 0) + 1

    rows = [
        {"word": word, "count": count,
         "per_1000": round(count * 1000.0 / total, 1) if total else 0.0,
         "flavor": flavor_of(word)}
        for word, count in counts.items()
        if count >= min_count
    ]
    rows.sort(key=lambda row: (-row["count"], row["word"]))
    return rows[:MAX_RESULTS], {"words": total, "sentences": len(sentences)}


def close_repetitions(text: str, window: int = 3, include_cliches: bool = True):
    """Kata yang muncul lagi dalam rentang beberapa kalimat."""
    sentences = split_sentences(text)
    positions = {}
    for word, line, index in iter_words(sentences):
        if len(word) < MIN_WORD_LENGTH:
            continue
        positions.setdefault(word, []).append((line, index))

    findings = []
    for word, hits in positions.items():
        if len(hits) < 2:
            continue
        cluster = [hits[0]]
        for current in hits[1:]:
            if current[1] - cluster[-1][1] <= window:
                cluster.append(current)
            else:
                _add_cluster(findings, word, cluster, sentences)
                cluster = [current]
        _add_cluster(findings, word, cluster, sentences)

    if include_cliches:
        findings.extend(_cliche_findings(text, sentences))

    # yang paling mengganggu dulu: rapat DAN banyak. Kepadatan saja membuat
    # tiga kata sambung dalam satu kalimat mengalahkan rantai panjang.
    for item in findings:
        item["score"] = round(item["count"] * item["density"], 2)
    findings.sort(key=lambda item: (-item["score"], -item["count"], item["line"]))
    return findings[:MAX_RESULTS], {"words": sum(len(v) for v in positions.values()),
                                    "sentences": len(sentences)}


def _add_cluster(findings, word, cluster, sentences):
    if len(cluster) < 2:
        return
    first_line, first_sentence = cluster[0]
    last_line, last_sentence = cluster[-1]
    span = max(0, last_sentence - first_sentence)
    findings.append({
        "word": word,
        "count": len(cluster),
        "line": first_line,
        "lines": [line for line, _ in cluster],
        "spread": span,
        "density": round(len(cluster) / (span + 1), 2),
        "lines_span": max(0, last_line - first_line),
        "sample": sentences[first_sentence][1][:160] if first_sentence < len(sentences) else "",
        "flavor": flavor_of(word),
        "kind": "repeat",
    })


def _cliche_findings(text, sentences):
    lowered = text.lower()
    findings = []
    for phrase in CLICHES:
        pattern = re.compile(r"\b" + re.escape(phrase) + r"\b")
        hits = list(pattern.finditer(lowered))
        if not hits:
            continue
        line = text.count("\n", 0, hits[0].start()) + 1
        findings.append({
            "word": phrase,
            "count": len(hits),
            "line": line,
            "lines": [text.count("\n", 0, h.start()) + 1 for h in hits],
            "spread": 0,
            "density": float(len(hits)),
            "lines_span": 0,
            "sample": _sentence_around(sentences, line),
            "flavor": "cliché",
            "kind": "cliche",
        })
    return findings


def _sentence_around(sentences, line):
    for sent_line, sent_text in sentences:
        if sent_line >= line:
            return sent_text[:160]
    return ""


def repeated_phrases(text: str, min_len: int = 2, max_len: int = 5,
                     min_count: int = 2):
    """Frasa berulang (minimal dua kata) yang tidak melintasi batas kalimat.

    Frasa yang bersarang dibuang: kalau 'dengan sangat hati-hati' dilaporkan,
    'dengan sangat' dan 'sangat hati-hati' tidak ikut muncul.
    """
    sentences = split_sentences(text)
    tokens = []
    for index, (line, sentence) in enumerate(sentences):
        for match in _PHRASE_WORD.finditer(sentence):
            tokens.append((match.group(0).lower(), line, index))
    if len(tokens) < min_len * min_count:
        return [], {"words": len(tokens), "sentences": len(sentences)}

    counts = {}
    for size in range(min_len, max_len + 1):
        for index in range(len(tokens) - size + 1):
            if tokens[index][2] != tokens[index + size - 1][2]:
                continue                      # hanya di dalam satu kalimat
            gram = tuple(token[0] for token in tokens[index:index + size])
            entry = counts.get(gram)
            if entry is None:
                counts[gram] = [1, index]
            else:
                entry[0] += 1

    candidates = {gram: entry for gram, entry in counts.items()
                  if entry[0] >= min_count}
    if not candidates:
        return [], {"words": len(tokens), "sentences": len(sentences)}

    # kumpulkan posisi kemunculan hanya untuk frasa yang lolos ambang
    starts = {gram: [] for gram in candidates}
    for size in range(min_len, max_len + 1):
        for index in range(len(tokens) - size + 1):
            if tokens[index][2] != tokens[index + size - 1][2]:
                continue
            gram = tuple(token[0] for token in tokens[index:index + size])
            if gram in starts:
                starts[gram].append(index)

    # buang frasa yang seluruh kemunculannya ada di dalam frasa lebih panjang
    # dengan jumlah kemunculan yang sama
    kept = []
    per_count = {}
    for gram, (count, _first) in candidates.items():
        per_count.setdefault(count, []).append(gram)
    for count in sorted(per_count, reverse=True):
        covered = set()
        for gram in sorted(per_count[count], key=lambda item: (-len(item), item)):
            hits = starts[gram]
            if hits and all(hit in covered for hit in hits):
                continue
            kept.append((gram, count))
            width = len(gram)
            for hit in hits:
                covered.update(range(hit, hit + width))

    rows = []
    for gram, count in kept:
        hits = starts[gram]
        if not hits:
            continue
        first = hits[0]
        line = tokens[first][1]
        sentence_indexes = [tokens[hit][2] for hit in hits]
        span = max(sentence_indexes) - min(sentence_indexes)
        rows.append({
            "phrase": " ".join(gram),
            "words": len(gram),
            "count": count,
            "line": line,
            "density": round(count / (span + 1), 2),
            "spread": span,
            "score": round(count * count / (span + 1), 2),
            "sample": sentences[tokens[first][2]][1][:160],
        })
    # frasa terpanjang dulu: "aku tidak" (200x) bukan temuan yang dicari,
    # sedangkan "ia menghela napas panjang" (2x) justru itu intinya.
    rows.sort(key=lambda row: (-row["words"], -row["count"], row["phrase"]))
    return rows[:MAX_RESULTS], {"words": len(tokens), "sentences": len(sentences)}


def analyze(text: str, min_count: int = 3, window: int = 3,
            include_cliches: bool = True):
    words, _totals = frequency(text, min_count)
    repeats, _ = close_repetitions(text, window, include_cliches)
    return {
        "words": words,
        "repeats": repeats,
        # angka yang ditampilkan = angka status bar, bukan token mentah
        "totals": {"words": count_words(text), "sentences": count_sentences(text)},
    }