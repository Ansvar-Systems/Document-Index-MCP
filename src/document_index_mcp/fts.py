"""FTS5 query builder — safe tokenization with AND/OR fallback.

Ported from the Law MCP golden standard (src/utils/fts-query.ts).
Never passes raw user input to FTS5 MATCH. Always decomposes to
Unicode word tokens with prefix matching.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


@dataclass
class FtsQuery:
    """FTS5 query variants: primary (AND) and optional fallback (OR)."""
    primary: str
    fallback: Optional[str] = None


def _extract_tokens(query: str) -> list[str]:
    """Extract Unicode word tokens, filtering single-char tokens."""
    normalized = unicodedata.normalize("NFC", query)
    tokens = _TOKEN_RE.findall(normalized)
    return [t for t in tokens if len(t) > 1]


def build_fts_query(query: str) -> FtsQuery:
    """Build safe FTS5 query variants from user input.

    Returns:
        FtsQuery with primary (AND with prefix) and optional fallback (OR with prefix).
        Single-token queries have no fallback.
    """
    tokens = _extract_tokens(query)

    if not tokens:
        return FtsQuery(primary="")

    prefix_tokens = [f"{t}*" for t in tokens]

    primary = " ".join(prefix_tokens)

    fallback = None
    if len(tokens) > 1:
        fallback = " OR ".join(prefix_tokens)

    return FtsQuery(primary=primary, fallback=fallback)
