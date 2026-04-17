"""Deterministic paragraph + sentence segmentation for legal / regulatory text.

Design: regex-based, not NLP-grade. Handles common abbreviations, numbered list
items, and quoted sentences that appear in legal boilerplate. Returns (char_start,
char_end, text) tuples where offsets are into the input string.
"""

from __future__ import annotations

import re
from typing import List, Tuple

Span = Tuple[int, int, str]


# Abbreviations that must NOT trigger a sentence boundary even when followed by
# a period. Lowercase checked against the lowercased word ending at the period.
_ABBREVIATIONS = frozenset({
    "art", "arts",           # Article(s)
    "sec", "secs",           # Section(s)
    "ch", "chap", "chaps",   # Chapter(s)
    "para", "paras",         # Paragraph(s)
    "no", "nos",             # Number(s)
    "vs", "vs",              # versus
    "eg", "ie", "etc",       # e.g., i.e., etc.
    "mr", "mrs", "ms", "dr", # titles
    "jr", "sr",              # suffixes
    "inc", "ltd", "plc",     # corp forms
    "co",                    # Company
    "fig", "figs",           # Figure(s)
    "eq", "eqs",             # Equation(s)
    "cf",                    # confer
    "al",                    # et al.
    "u",                     # U.S., U.K.
    "p", "pp",               # page(s)
    "v",                     # v. (versus, legal)
    "viz",                   # viz.
})

# A terminator is `.`, `!`, or `?` (possibly repeated). We check the word
# ending immediately before the terminator to see if it's an abbreviation.
_TERMINATOR_RE = re.compile(r"([.!?]+)(?=\s|$)")

# Extract the "word" immediately preceding position `i` in text.
_WORD_BEFORE_RE = re.compile(r"([A-Za-z]+)$")


def _is_abbreviation_terminator(text: str, term_start: int, term_char: str) -> bool:
    """True iff the terminator at `text[term_start]` is an abbreviation period,
    not a sentence-ending period.

    Only applies to `.` — `!` and `?` are always sentence-ending.
    The `§` (section) sign is not a terminator; it's a content character.
    """
    if term_char != ".":
        return False
    # Look at the word ending right before the period.
    m = _WORD_BEFORE_RE.search(text[:term_start])
    if not m:
        return False
    word = m.group(1).lower()
    # A single-letter initial like "U" in "U.S." or "A" in "A. B. C." is an abbreviation.
    if len(word) == 1:
        return True
    return word in _ABBREVIATIONS


def segment_sentences(text: str) -> List[Span]:
    """Split text into sentences. Returns list of (char_start, char_end, sentence_text).

    Offsets are into the input string. Leading whitespace inside a sentence span
    is trimmed so `text[start:end]` equals the third tuple element.
    """
    if not text:
        return []

    spans: List[Span] = []
    start = 0
    i = 0
    n = len(text)

    while i < n:
        m = _TERMINATOR_RE.search(text, i)
        if not m:
            remainder = text[start:].rstrip()
            if remainder:
                end = start + len(remainder)
                # Strip leading whitespace from the span
                leading_ws = len(text[start:end]) - len(text[start:end].lstrip())
                spans.append((start + leading_ws, end, text[start + leading_ws:end]))
            break

        term_start = m.start()
        term_end = m.end()
        # Is this an abbreviation period? If so, skip past it and continue.
        term_char = m.group(1)[0]
        if _is_abbreviation_terminator(text, term_start, term_char):
            i = term_end
            continue

        sentence_text = text[start:term_end]
        leading_ws = len(sentence_text) - len(sentence_text.lstrip())
        sentence_start = start + leading_ws
        spans.append((sentence_start, term_end, text[sentence_start:term_end]))
        start = term_end
        while start < n and text[start].isspace():
            start += 1
        i = start

    return spans
