"""Integration tests for the new /parse endpoint."""

import base64
from fastapi.testclient import TestClient
from document_index_mcp.http_server import app


client = TestClient(app)


def _make_test_txt(content: str) -> str:
    return base64.b64encode(content.encode("utf-8")).decode("ascii")


def test_parse_endpoint_returns_structured_output():
    content = _make_test_txt(
        "1. Introduction\n"
        "First sentence here. Second sentence here.\n"
        "\n"
        "Another paragraph. With two sentences.\n"
    )
    resp = client.post(
        "/parse",
        json={"filename": "test.txt", "content_base64": content},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "sections" in body
    assert "full_text" in body
    assert "parser_version" in body
    assert "language" in body
    assert body["parser_version"]  # non-empty
    assert len(body["sections"]) >= 1
    section = body["sections"][0]
    assert "paragraphs" in section
    assert "char_start" in section
    assert "char_end" in section
    assert len(section["paragraphs"]) >= 1
    para = section["paragraphs"][0]
    assert "sentences" in para
    assert len(para["sentences"]) >= 1
    sent = para["sentences"][0]
    assert "char_start" in sent
    assert "char_end" in sent
    assert "text" in sent
    # Round-trip: char offsets resolve back to text
    ft = body["full_text"]
    assert ft[sent["char_start"]:sent["char_end"]] == sent["text"]


def test_parse_endpoint_rejects_unsupported_content_type():
    resp = client.post(
        "/parse",
        json={"filename": "test.xlsx", "content_base64": "UEs="},
    )
    assert resp.status_code == 415


def test_parse_endpoint_rejects_empty_body():
    resp = client.post(
        "/parse",
        json={"filename": "test.txt", "content_base64": ""},
    )
    assert resp.status_code == 400
