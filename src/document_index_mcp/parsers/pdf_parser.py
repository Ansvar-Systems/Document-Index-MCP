"""PDF parser with cross-page section merging AND sentence-level offsets.

Improvement over Document-Logic-MCP: sections span multiple pages instead of
being reset per page boundary. New in Plan 1: populates `Paragraph` and
`Sentence` objects with absolute char offsets into `ParseResult.full_text`.
"""

import logging
import re
from pathlib import Path
from .base import BaseParser, ParseResult, Section
from ..segmenter import segment_section
from .. import PARSER_VERSION

logger = logging.getLogger(__name__)

_OCR_THRESHOLD = 50
_SECTION_SEPARATOR = "\n\n"

_NUMBERED_HEADING_PATTERNS = [
    (re.compile(r"^\d+\.\d+\.\d+\s+[A-Z]\w"), 3),
    (re.compile(r"^\d+\.\d+\s+[A-Z]\w"), 2),
    (re.compile(r"^\d+\.\s+[A-Z]\w"), 1),
]
_MAX_HEADING_LENGTH = 120
_LIST_ITEM_CHARS = re.compile(r"[,;]")
_NUMBER_PREFIX_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+(.*)")
_SENTENCE_STARTERS = frozenset({
    "The", "This", "These", "Those", "That", "A", "An", "Each", "Every",
    "All", "It", "Its", "Our", "We", "They", "When", "If", "For", "In",
    "On", "At", "There", "Here", "Any", "Some", "No", "Most", "Many", "Several",
})
_HEADING_NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)*)")


def _is_heading(line: str) -> bool:
    if not line or len(line) >= _MAX_HEADING_LENGTH:
        return False
    if line.isupper() and 2 <= len(line.split()) <= 8:
        return True
    if _LIST_ITEM_CHARS.search(line):
        return False
    m = _NUMBER_PREFIX_RE.match(line)
    if m:
        rest = m.group(1)
        words = rest.split()
        if words and words[0] in _SENTENCE_STARTERS:
            return False
    for pattern, _level in _NUMBERED_HEADING_PATTERNS:
        if pattern.match(line):
            return True
    return False


def _make_section_ref(title: str, index: int) -> str:
    """Derive section_ref from heading number or fallback to index."""
    m = _HEADING_NUMBER_RE.match(title)
    if m:
        return f"s{m.group(1)}"
    return f"s{index + 1}"


def _make_parent_ref(section_ref: str) -> str | None:
    """Derive parent_ref: 's2.1.3' -> 's2.1', 's2' -> None."""
    parts = section_ref.rsplit(".", 1)
    if len(parts) > 1:
        return parts[0]
    return None


class PDFParser(BaseParser):
    """PDF parser with cross-page section merging and OCR fallback."""

    def parse(self, file_path: Path) -> ParseResult:
        import pdfplumber

        raw_pages: list[str] = []
        sections: list[Section] = []
        full_text_parts: list[str] = []
        full_text_cursor = 0
        section_index = 0

        current_title: str | None = None
        current_content: list[str] = []
        current_page_start: int | None = None

        def _finalize_section(end_page: int) -> None:
            nonlocal full_text_cursor, section_index
            if not (current_title and current_content):
                return
            section_content = "\n".join(current_content)
            section_start = full_text_cursor
            full_text_parts.append(section_content)
            section_end = section_start + len(section_content)
            full_text_cursor = section_end + len(_SECTION_SEPARATOR)
            full_text_parts.append(_SECTION_SEPARATOR)

            ref = _make_section_ref(current_title, section_index)
            paragraphs = segment_section(section_content, base_offset=section_start)
            sections.append(Section(
                title=current_title,
                content=section_content,
                section_ref=ref,
                page_start=current_page_start,
                page_end=end_page,
                parent_ref=_make_parent_ref(ref),
                char_start=section_start,
                char_end=section_end,
                paragraphs=paragraphs,
            ))
            section_index += 1

        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)

            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                non_ws = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
                if non_ws < _OCR_THRESHOLD:
                    ocr_text = self._ocr_page(file_path, page_num)
                    if ocr_text:
                        text = ocr_text
                raw_pages.append(text)

                for line in text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue

                    if _is_heading(line):
                        _finalize_section(page_num - 1 if page_num > 1 else 1)
                        current_title = line
                        current_content = []
                        current_page_start = page_num
                    else:
                        current_content.append(line)

            _finalize_section(page_count)

        if not sections:
            full_content = "\n".join(raw_pages)
            paragraphs = segment_section(full_content, base_offset=0)
            sections.append(Section(
                title="Document",
                content=full_content,
                section_ref="page-1",
                page_start=1,
                page_end=page_count,
                char_start=0,
                char_end=len(full_content),
                paragraphs=paragraphs,
            ))
            full_text = full_content
        else:
            full_text = "".join(full_text_parts).rstrip(_SECTION_SEPARATOR)

        return ParseResult(
            filename=file_path.name,
            sections=sections,
            raw_text="\n".join(raw_pages),
            full_text=full_text,
            page_count=page_count,
            metadata={"parser": "pdfplumber"},
            parser_version=PARSER_VERSION,
            language="en",
        )

    @staticmethod
    def _ocr_page(file_path: Path, page_num: int) -> str | None:
        try:
            from pdf2image import convert_from_path
            import pytesseract
            images = convert_from_path(file_path, first_page=page_num, last_page=page_num, dpi=300)
            if images:
                return pytesseract.image_to_string(images[0]).strip()
        except (ImportError, Exception):
            pass
        return None
