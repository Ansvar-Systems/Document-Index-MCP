from document_index_mcp.fts import build_fts_query


def test_single_token():
    result = build_fts_query("cybersecurity")
    assert result.primary == "cybersecurity*"
    assert result.fallback is None


def test_multi_token_and_query():
    result = build_fts_query("authentication risk")
    assert result.primary == "authentication* risk*"
    assert result.fallback == "authentication* OR risk*"


def test_strips_single_char_tokens():
    result = build_fts_query("a cybersecurity risk")
    assert result.primary == "cybersecurity* risk*"


def test_unicode_tokens():
    result = build_fts_query("Datenschutz Sicherheit")
    assert result.primary == "Datenschutz* Sicherheit*"


def test_strips_special_chars():
    result = build_fts_query("risk; assessment, (2026)")
    assert "risk" in result.primary
    assert "assessment" in result.primary
    assert "2026" in result.primary
    assert ";" not in result.primary


def test_empty_query():
    result = build_fts_query("")
    assert result.primary == ""
    assert result.fallback is None
