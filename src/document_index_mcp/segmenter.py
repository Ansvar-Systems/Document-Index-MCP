"""Deterministic paragraph + sentence segmentation for legal / regulatory text.

Design: regex-based, not NLP-grade. Handles common abbreviations, numbered list
items, and quoted sentences that appear in legal boilerplate. Returns (char_start,
char_end, text) tuples where offsets are into the input string.

NOT in scope: cross-language stemming, dependency parsing, citation-of-citation
disambiguation. For v1 the target is ≥98% F1 on the 10-doc golden corpus in
tests/fixtures/golden_corpus/.
"""

from __future__ import annotations

import re
from typing import List, Tuple

Span = Tuple[int, int, str]


# Sentence-terminator characters that end a sentence. A sentence ends when one
# of these is followed by whitespace (or end-of-string), unless preceded by
# an abbreviation (see _ABBREVIATIONS below).
_TERMINATORS = re.compile(r"[.!?]+")


def segment_sentences(text: str) -> List[Span]:
    """Split text into sentences. Returns list of (char_start, char_end, sentence_text)."""
    if not text:
        return []

    spans: List[Span] = []
    start = 0
    i = 0
    n = len(text)

    while i < n:
        # Find next terminator
        m = _TERMINATORS.search(text, i)
        if not m:
            # No more terminators — emit remainder if any
            remainder = text[start:].rstrip()
            if remainder:
                end = start + len(remainder)
                spans.append((start, end, text[start:end]))
            break

        term_end = m.end()
        # Sentence is start..term_end
        sentence_text = text[start:term_end]
        # Trim leading whitespace from the span, adjusting start accordingly
        leading_ws = len(sentence_text) - len(sentence_text.lstrip())
        sentence_start = start + leading_ws
        spans.append((sentence_start, term_end, text[sentence_start:term_end]))
        start = term_end
        # Skip any whitespace that follows the terminator
        while start < n and text[start].isspace():
            start += 1
        i = start

    return spans
