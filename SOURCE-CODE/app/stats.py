"""Penghitung. Sengaja sederhana dan cepat: dipanggil tiap ~200 ms saat mengetik."""
import re

WORD_RE = re.compile(r"[\w'\u2019\-]+", re.UNICODE)
SENT_END = re.compile(r"[^.!?\u2026]+[.!?\u2026]+|[^.!?\u2026]+$", re.UNICODE)


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def count_sentences(text: str) -> int:
    total = 0
    for chunk in SENT_END.finditer(text):
        piece = chunk.group(0)
        if WORD_RE.search(piece):
            total += 1
    return total


def count_paragraphs(text: str) -> int:
    return sum(1 for line in text.split("\n") if line.strip())


def reading_minutes(words: int, wpm: int = 200) -> int:
    return max(1, round(words / wpm)) if words else 0


def summarize(text: str) -> dict:
    words = count_words(text)
    return {
        "words": words,
        "sentences": count_sentences(text),
        "paragraphs": count_paragraphs(text),
        "minutes": reading_minutes(words),
    }