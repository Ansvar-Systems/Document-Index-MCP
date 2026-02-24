import pytest
from pathlib import Path
from document_index_mcp.tools import (
    index_document_tool,
    search_document_tool,
    get_section_tool,
    get_document_overview_tool,
    list_documents_tool,
    delete_document_tool,
    get_statistics_tool,
    get_surrounding_sections_tool,
    about_tool,
    list_supported_formats_tool,
)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def sample_doc(tmp_path):
    doc = tmp_path / "test.txt"
    doc.write_text(
        "1. Introduction\n"
        "This document covers cybersecurity risk assessment methodology.\n"
        "\n"
        "2. Risk Assessment\n"
        "Authentication mechanisms must be evaluated for bypass vulnerabilities.\n"
        "Multi-factor authentication is recommended for all admin interfaces.\n"
        "\n"
        "3. Conclusion\n"
        "Regular penetration testing should be scheduled quarterly.\n"
    )
    return doc


async def test_index_document(db_path, sample_doc):
    result = await index_document_tool(str(sample_doc), db_path)
    assert result["status"] == "indexed"
    assert result["sections_count"] == 3
    assert "doc_id" in result


async def test_search_document(db_path, sample_doc):
    await index_document_tool(str(sample_doc), db_path)
    result = await search_document_tool("authentication", db_path)
    assert len(result["results"]) >= 1
    assert any("authentication" in r["snippet"].lower() for r in result["results"])


async def test_search_within_document(db_path, sample_doc):
    idx = await index_document_tool(str(sample_doc), db_path)
    result = await search_document_tool(
        "authentication", db_path, doc_id=idx["doc_id"]
    )
    assert len(result["results"]) >= 1


async def test_get_section(db_path, sample_doc):
    idx = await index_document_tool(str(sample_doc), db_path)
    result = await get_section_tool(idx["doc_id"], "s2", db_path)
    assert result["title"] == "2. Risk Assessment"
    assert "authentication" in result["content"].lower()


async def test_get_document_overview(db_path, sample_doc):
    idx = await index_document_tool(str(sample_doc), db_path)
    result = await get_document_overview_tool(idx["doc_id"], db_path)
    assert result["filename"] == "test.txt"
    assert len(result["sections"]) == 3


async def test_list_documents(db_path, sample_doc):
    await index_document_tool(str(sample_doc), db_path)
    result = await list_documents_tool(db_path)
    assert result["total"] == 1
    assert result["documents"][0]["filename"] == "test.txt"


async def test_search_no_results(db_path, sample_doc):
    await index_document_tool(str(sample_doc), db_path)
    result = await search_document_tool("nonexistentxyz", db_path)
    assert len(result["results"]) == 0


async def test_delete_document(db_path, sample_doc):
    idx = await index_document_tool(str(sample_doc), db_path)
    result = await delete_document_tool(idx["doc_id"], db_path)
    assert result["status"] == "deleted"
    listing = await list_documents_tool(db_path)
    assert listing["total"] == 0


async def test_get_statistics(db_path, sample_doc):
    await index_document_tool(str(sample_doc), db_path)
    result = await get_statistics_tool(db_path)
    assert result["doc_count"] == 1
    assert result["total_sections"] == 3


async def test_get_surrounding_sections(db_path, sample_doc):
    idx = await index_document_tool(str(sample_doc), db_path)
    result = await get_surrounding_sections_tool(idx["doc_id"], "s2", db_path)
    assert len(result["sections"]) == 3  # s1, s2, s3
    assert result["target_ref"] == "s2"


async def test_about():
    result = await about_tool()
    assert result["name"] == "Document-Index-MCP"
    assert ".pdf" in result["supported_formats"]


async def test_list_supported_formats():
    result = await list_supported_formats_tool()
    assert result["count"] > 10
    assert ".pdf" in result["formats"]
    assert ".docx" in result["formats"]
