"""Base parser interface with section_ref, paragraphs, and sentences for citation-quality parsing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path


@dataclass
class Sentence:
    """A single sentence within a paragraph. Offsets are into ParseResult.full_text."""
    sentence_index: int
    char_start: int
    char_end: int
    text: str


@dataclass
class Paragraph:
    """A paragraph within a section. Offsets are into ParseResult.full_text."""
    paragraph_index: int
    char_start: int
    char_end: int
    sentences: List[Sentence] = field(default_factory=list)


@dataclass
class Section:
    """Document section — equivalent to a legal provision.

    `paragraphs`, `char_start`, `char_end` are populated by parsers that emit
    sentence-level offsets. They default to empty/None for backward compatibility
    with legacy callers that only need section-grained output.
    """
    title: str
    content: str
    section_ref: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    parent_ref: Optional[str] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    paragraphs: List[Paragraph] = field(default_factory=list)


@dataclass
class ParseResult:
    """Result of document parsing.

    `full_text` is the canonical contiguous string into which all Section/
    Paragraph/Sentence char offsets are measured. Parsers that don't yet
    emit offsets may set full_text == raw_text.
    """
    filename: str
    sections: List[Section]
    raw_text: str
    page_count: int
    metadata: dict
    full_text: str = ""
    parser_version: str = ""
    language: str = "en"


class BaseParser(ABC):
    """Base class for document parsers."""

    @abstractmethod
    def parse(self, file_path: Path) -> ParseResult:
        pass
