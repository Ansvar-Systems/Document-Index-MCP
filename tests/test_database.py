import pytest
from pathlib import Path
from document_index_mcp.database import Database


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


async def test_initialize_creates_tables(db_path):
    db = Database(db_path)
    await db.initialize()
    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
    assert "documents" in tables
    assert "sections" in tables
    assert "sections_fts" in tables
    assert "db_metadata" in tables


async def test_fts5_trigger_indexes_on_insert(db_path):
    db = Database(db_path)
    await db.initialize()
    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO documents (doc_id, filename, upload_date, sections_count) "
            "VALUES ('d1', 'test.pdf', '2026-01-01', 1)"
        )
        await conn.execute(
            "INSERT INTO sections (doc_id, section_ref, title, content, section_index) "
            "VALUES ('d1', 's1', 'Introduction', 'This document covers cybersecurity risks', 0)"
        )
        await conn.commit()
        cursor = await conn.execute(
            "SELECT title FROM sections_fts WHERE sections_fts MATCH 'cybersecurity'"
        )
        rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "Introduction"
