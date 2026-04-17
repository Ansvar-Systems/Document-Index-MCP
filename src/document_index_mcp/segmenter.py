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

    # Check if this period is part of a list marker like "1. " or "(a) "
    # Look at the character(s) immediately before the period
    if term_start > 0:
        before = text[term_start - 1]
        # Check for digit before period (numbered list: "1. ", "12. ", etc.)
        if before.isdigit():
            # Verify it's followed by space (typical list format)
            if term_start + 1 < len(text) and text[term_start + 1].isspace():
                return True  # This is a list marker, not a sentence terminator

    # Look at the word ending right before the period.
    m = _WORD_BEFORE_RE.search(text[:term_start])
    if not m:
        return False
    word = m.group(1).lower()
    # A single-letter initial like "U" in "U.S." or "A" in "A. B. C." is an abbreviation.
    if len(word) == 1:
        return True
    return word in _ABBREVIATIONS


# List item patterns — triggers a secondary split within a coarse sentence.
# `1. ` or `(1) ` or `(a) ` at start of a clause.
_LIST_MARKER_RE = re.compile(r"(?:(?<=^)|(?<=[\s]))(?:\d+\.\s|\(\w\)\s|\([a-z]\)\s)")


def _split_on_list_markers(start: int, end: int, text: str) -> List[Span]:
    """Secondary pass: break a coarse sentence into per-list-item spans.

    Legal text often uses "The Processor shall: 1. notify; 2. preserve; 3. investigate."
    in one sentence. For citation quality each item needs its own span.
    """
    segment = text[start:end]
    # Find list-marker positions and split on semicolons between them.
    markers = list(_LIST_MARKER_RE.finditer(segment))
    if not markers:
        return [(start, end, segment)]

    # Build cut points: before each marker (except the first), and at each
    # semicolon that separates items.
    cuts = set()
    for mk in markers[1:]:
        cuts.add(mk.start())
    for m in re.finditer(r";\s*", segment):
        cuts.add(m.end())

    if not cuts:
        return [(start, end, segment)]

    boundary_points = sorted({0, *cuts, len(segment)})
    out: List[Span] = []
    for a, b in zip(boundary_points, boundary_points[1:]):
        sub = segment[a:b].rstrip(";").rstrip()
        if not sub:
            continue
        leading = len(segment[a:b]) - len(segment[a:b].lstrip())
        abs_start = start + a + leading
        abs_end = start + a + leading + len(sub)
        out.append((abs_start, abs_end, text[abs_start:abs_end]))
    return out


def segment_sentences(text: str) -> List[Span]:
    """Split text into sentences. Returns list of (char_start, char_end, sentence_text).

    Two-pass implementation:
    - Pass 1: Identify coarse sentence boundaries using terminators (. ! ?).
    - Pass 2: Within each sentence, if it contains list markers (1. , (a) , etc.),
      split on those markers and semicolons for per-item citation spans.

    Offsets are into the input string. Leading whitespace inside a sentence span
    is trimmed so `text[start:end]` equals the third tuple element.
    """
    if not text:
        return []

    coarse: List[Span] = []
    start = 0
    i = 0
    n = len(text)

    # PASS 1: Coarse segmentation on terminators
    while i < n:
        m = _TERMINATOR_RE.search(text, i)
        if not m:
            remainder = text[start:].rstrip()
            if remainder:
                end = start + len(remainder)
                leading_ws = len(text[start:end]) - len(text[start:end].lstrip())
                coarse.append((start + leading_ws, end, text[start + leading_ws:end]))
            break

        term_start = m.start()
        term_end = m.end()
        term_char = m.group(1)[0]
        if _is_abbreviation_terminator(text, term_start, term_char):
            i = term_end
            continue

        sentence_text = text[start:term_end]
        leading_ws = len(sentence_text) - len(sentence_text.lstrip())
        sentence_start = start + leading_ws
        coarse.append((sentence_start, term_end, text[sentence_start:term_end]))
        start = term_end
        while start < n and text[start].isspace():
            start += 1
        i = start

    # PASS 2: Secondary split on list markers
    fine: List[Span] = []
    for s_start, s_end, _ in coarse:
        fine.extend(_split_on_list_markers(s_start, s_end, text))
    return fine


# Paragraph boundary: two or more consecutive newlines (optionally with whitespace).
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n+")


def segment_paragraphs(text: str) -> List[Span]:
    """Split text into paragraphs on blank lines.

    Returns list of (char_start, char_end, paragraph_text). Each span excludes
    trailing newlines; `text[start:end]` equals the third tuple element.
    """
    if not text:
        return []

    spans: List[Span] = []
    start = 0
    for m in _PARAGRAPH_BREAK.finditer(text):
        end = m.start()
        para = text[start:end].strip()
        if para:
            # Compute offsets after stripping leading/trailing whitespace.
            raw = text[start:end]
            leading = len(raw) - len(raw.lstrip())
            trailing = len(raw) - len(raw.rstrip())
            s = start + leading
            e = end - trailing
            spans.append((s, e, text[s:e]))
        start = m.end()

    # Final paragraph (after last break).
    remainder = text[start:].strip()
    if remainder:
        raw = text[start:]
        leading = len(raw) - len(raw.lstrip())
        s = start + leading
        e = s + len(remainder)
        spans.append((s, e, text[s:e]))

    return spans
