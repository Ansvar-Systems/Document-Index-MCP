"""Database layer for Document-Index MCP.

SQLite + FTS5 schema following the Law MCP pattern.
Sections are indexed like legal provisions — one row per structural section,
full-text searchable via FTS5 with BM25 ranking.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Union

import aiosqlite

LEGACY_UNASSIGNED_ORG = "legacy_unassigned"

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL DEFAULT 'legacy_unassigned',
    owner_user_id TEXT,
    scope TEXT NOT NULL DEFAULT 'organization',
    filename TEXT NOT NULL,
    title TEXT,
    upload_date TEXT NOT NULL,
    page_count INTEGER,
    sections_count INTEGER,
    file_type TEXT,
    file_size_bytes INTEGER,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    section_ref TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    section_index INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    parent_ref TEXT,
    UNIQUE(doc_id, section_ref)
);

CREATE INDEX IF NOT EXISTS idx_sections_doc_id ON sections(doc_id);
CREATE INDEX IF NOT EXISTS idx_sections_ref ON sections(doc_id, section_ref);

CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
    title,
    content,
    content='sections',
    content_rowid='id',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS sections_fts_insert AFTER INSERT ON sections BEGIN
    INSERT INTO sections_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS sections_fts_delete AFTER DELETE ON sections BEGIN
    INSERT INTO sections_fts(sections_fts, rowid, title, content)
    VALUES('delete', old.id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS sections_fts_update AFTER UPDATE ON sections BEGIN
    INSERT INTO sections_fts(sections_fts, rowid, title, content)
    VALUES('delete', old.id, old.title, old.content);
    INSERT INTO sections_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;

CREATE TABLE IF NOT EXISTS db_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class Database:
    """SQLite database with FTS5 indexing for document sections."""

    def __init__(self, db_path: Union[str, Path]) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """Create all tables, indexes, FTS5 virtual table, and triggers."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA foreign_keys = ON")
            await db.executescript(SCHEMA)
            await self._migrate_documents_table(db)
            await db.commit()

    async def _migrate_documents_table(self, db: aiosqlite.Connection) -> None:
        columns_cursor = await db.execute("PRAGMA table_info(documents)")
        columns = {row[1] for row in await columns_cursor.fetchall()}

        if "org_id" not in columns:
            await db.execute(
                f"ALTER TABLE documents ADD COLUMN org_id TEXT NOT NULL DEFAULT '{LEGACY_UNASSIGNED_ORG}'"
            )
        if "owner_user_id" not in columns:
            await db.execute("ALTER TABLE documents ADD COLUMN owner_user_id TEXT")
        if "scope" not in columns:
            await db.execute(
                "ALTER TABLE documents ADD COLUMN scope TEXT NOT NULL DEFAULT 'organization'"
            )

        await db.execute(
            "UPDATE documents SET org_id = ? WHERE org_id IS NULL OR TRIM(org_id) = ''",
            (LEGACY_UNASSIGNED_ORG,),
        )
        await db.execute(
            "UPDATE documents SET scope = 'organization' WHERE scope IS NULL OR TRIM(scope) = ''"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_org_id ON documents(org_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_org_scope ON documents(org_id, scope)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_org_owner_scope "
            "ON documents(org_id, owner_user_id, scope)"
        )

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Async context manager for database connections."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            db.row_factory = aiosqlite.Row
            yield db
