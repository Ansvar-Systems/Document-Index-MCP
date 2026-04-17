"""Plain text / markdown parser.

Builds a canonical `full_text` stream during parsing and records char offsets
for every section, paragraph, and sentence.
"""

from pathlib import Path
from .base import BaseParser, ParseResult, Section
from .pdf_parser import _is_heading, _make_section_ref, _make_parent_ref
from .. import PARSER_VERSION
from ..segmenter import segment_section


_SECTION_SEPARATOR = "\n\n"  # Between sections in full_text


class TextParser(BaseParser):
    def parse(self, file_path: Path) -> ParseResult:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        sections: list[Section] = []
        full_text_parts: list[str] = []
        full_text_cursor = 0  # running offset into the assembled full_text
        section_index = 0
        current_title: str | None = None
        current_content: list[str] = []

        def _finalize_section():
            nonlocal full_text_cursor, section_index
            if not (current_title and current_content):
                return
            # Strip trailing blank lines to match what will be in full_text
            while current_content and current_content[-1] == "":
                current_content.pop()
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
                parent_ref=_make_parent_ref(ref),
                char_start=section_start,
                char_end=section_end,
                paragraphs=paragraphs,
            ))
            section_index += 1

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                current_content.append("")  # preserves paragraph breaks
                continue
            if _is_heading(stripped):
                _finalize_section()
                current_title = stripped
                current_content = []
            else:
                current_content.append(stripped)

        _finalize_section()

        if not sections:
            # No headings detected — treat whole file as one section
            full_text_parts = [text]
            paragraphs = segment_section(text, base_offset=0)
            sections.append(Section(
                title="Document",
                content=text,
                section_ref="page-1",
                char_start=0,
                char_end=len(text),
                paragraphs=paragraphs,
            ))
            full_text = text
        else:
            # Strip trailing separator
            full_text = "".join(full_text_parts).rstrip(_SECTION_SEPARATOR)

        return ParseResult(
            filename=file_path.name,
            sections=sections,
            raw_text=text,
            full_text=full_text,
            page_count=1,
            metadata={"parser": "text"},
            parser_version=PARSER_VERSION,
            language="en",  # naive default; language detection deferred
        )
