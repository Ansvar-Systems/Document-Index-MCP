import pytest
from pathlib import Path
from document_index_mcp.parsers.base import Section
from document_index_mcp.parsers.text_parser import TextParser
from document_index_mcp.parsers.pdf_parser import _is_heading, _make_section_ref, _make_parent_ref


def test_text_parser_detects_headings(tmp_path):
    doc = tmp_path / "test.txt"
    doc.write_text(
        "1. Introduction\n"
        "This is the intro content.\n"
        "More intro text here.\n"
        "\n"
        "2. Risk Assessment\n"
        "Risk content goes here.\n"
    )
    parser = TextParser()
    result = parser.parse(doc)
    assert len(result.sections) == 2
    assert result.sections[0].title == "1. Introduction"
    assert result.sections[0].section_ref == "s1"
    assert result.sections[1].title == "2. Risk Assessment"
    assert result.sections[1].section_ref == "s2"


def test_text_parser_cross_section_content(tmp_path):
    doc = tmp_path / "test.txt"
    doc.write_text(
        "1. First Section\n"
        "Content line 1.\n"
        "Content line 2.\n"
        "\n"
        "2. Second Section\n"
        "Content line 3.\n"
    )
    parser = TextParser()
    result = parser.parse(doc)
    assert "Content line 1" in result.sections[0].content
    assert "Content line 2" in result.sections[0].content


def test_no_headings_fallback(tmp_path):
    doc = tmp_path / "test.txt"
    doc.write_text("Just plain text without any headings or structure.")
    parser = TextParser()
    result = parser.parse(doc)
    assert len(result.sections) == 1
    assert result.sections[0].section_ref == "page-1"
    assert result.sections[0].title == "Document"


def test_hierarchical_section_refs(tmp_path):
    doc = tmp_path / "test.txt"
    doc.write_text(
        "1. Chapter One\n"
        "Intro text.\n"
        "\n"
        "1.1 First Subsection\n"
        "Subsection content.\n"
        "\n"
        "1.2 Second Subsection\n"
        "More content.\n"
    )
    parser = TextParser()
    result = parser.parse(doc)
    assert result.sections[0].section_ref == "s1"
    assert result.sections[0].parent_ref is None
    assert result.sections[1].section_ref == "s1.1"
    assert result.sections[1].parent_ref == "s1"
    assert result.sections[2].section_ref == "s1.2"
    assert result.sections[2].parent_ref == "s1"


def test_is_heading_all_caps():
    assert _is_heading("RISK ASSESSMENT") is True
    assert _is_heading("A") is False  # too short


def test_is_heading_numbered():
    assert _is_heading("1. Introduction") is True
    assert _is_heading("2.1 Risk Assessment") is True
    assert _is_heading("3.1.2 Sub Topic") is True


def test_is_heading_rejects_sentences():
    assert _is_heading("1. The system validates all tokens on each request.") is False
    assert _is_heading("2. This module handles authentication.") is False


def test_make_section_ref():
    assert _make_section_ref("1. Introduction", 0) == "s1"
    assert _make_section_ref("2.1 Risk", 1) == "s2.1"
    assert _make_section_ref("OVERVIEW", 0) == "s1"  # fallback


def test_make_parent_ref():
    assert _make_parent_ref("s2.1") == "s2"
    assert _make_parent_ref("s2.1.3") == "s2.1"
    assert _make_parent_ref("s2") is None
