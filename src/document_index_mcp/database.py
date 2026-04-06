"""Database layer for Document-Index MCP.

SQLite + FTS5 schema following the Law MCP pattern.
Sections are indexed like legal provisions — one row per structural section,
full-text searchable via FTS5 with BM25 ranking.
"""

import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Union

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    title TEXT,
    upload_date TEXT NOT NULL,
    page_count INTEGER,
    sections_count INTEGER,
    file_type TEXT,
    file_size_bytes INTEGER,
    metadata TEXT,

    -- GRC policy library fields (v2)
    scope TEXT DEFAULT 'general' CHECK (scope IN ('general', 'policy_library')),
    doc_type TEXT CHECK (doc_type IN (
        'policy', 'procedure', 'guideline', 'standard',
        'control_matrix', 'risk_register', 'asset_inventory',
        'soa', 'evidence', 'report', 'other'
    )),
    classification TEXT DEFAULT 'internal' CHECK (classification IN (
        'public', 'internal', 'confidential', 'restricted'
    )),
    status TEXT DEFAULT 'active' CHECK (status IN (
        'draft', 'active', 'under_review', 'superseded', 'retired'
    )),
    framework_refs TEXT,    -- JSON array: ["ISO 27001:A.8", "DORA:Art.9"]
    owner TEXT,
    version TEXT,
    review_date TEXT,
    effective_date TEXT,
    source_ref TEXT,        -- connector dedup key
    last_synced TEXT
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

    -- GRC fields (v2)
    control_refs TEXT,      -- JSON array: ["A.8.1", "A.5.15"]
    framework_refs TEXT,    -- JSON array (section-level)

    UNIQUE(doc_id, section_ref)
);

CREATE INDEX IF NOT EXISTS idx_sections_doc_id ON sections(doc_id);
CREATE INDEX IF NOT EXISTS idx_sections_ref ON sections(doc_id, section_ref);
CREATE INDEX IF NOT EXISTS idx_documents_scope ON documents(scope);
CREATE INDEX IF NOT EXISTS idx_documents_doc_type ON documents(doc_type);

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

# Migrations for existing databases — safe to run multiple times
MIGRATIONS_V2 = """
-- Documents: GRC columns
ALTER TABLE documents ADD COLUMN scope TEXT DEFAULT 'general';
ALTER TABLE documents ADD COLUMN doc_type TEXT;
ALTER TABLE documents ADD COLUMN classification TEXT DEFAULT 'internal';
ALTER TABLE documents ADD COLUMN status TEXT DEFAULT 'active';
ALTER TABLE documents ADD COLUMN framework_refs TEXT;
ALTER TABLE documents ADD COLUMN owner TEXT;
ALTER TABLE documents ADD COLUMN version TEXT;
ALTER TABLE documents ADD COLUMN review_date TEXT;
ALTER TABLE documents ADD COLUMN effective_date TEXT;
ALTER TABLE documents ADD COLUMN source_ref TEXT;
ALTER TABLE documents ADD COLUMN last_synced TEXT;

-- Sections: GRC columns
ALTER TABLE sections ADD COLUMN control_refs TEXT;
ALTER TABLE sections ADD COLUMN framework_refs TEXT;
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
            await self._run_migrations(db)
            await db.commit()

    async def _run_migrations(self, db: aiosqlite.Connection) -> None:
        """Apply schema migrations for existing databases. Safe to re-run."""
        # Check current schema version
        cursor = await db.execute(
            "SELECT value FROM db_metadata WHERE key = 'schema_version'"
        )
        row = await cursor.fetchone()
        current_version = int(row[0]) if row else 1

        if current_version < 2:
            for stmt in MIGRATIONS_V2.strip().split(";"):
                stmt = stmt.strip()
                if not stmt or stmt.startswith("--"):
                    continue
                try:
                    await db.execute(stmt)
                except Exception:
                    pass  # Column already exists — safe to skip

            # Create indexes that may not exist
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_scope ON documents(scope)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_doc_type ON documents(doc_type)"
            )

            await db.execute(
                "INSERT OR REPLACE INTO db_metadata (key, value) VALUES ('schema_version', '2')"
            )

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Async context manager for database connections."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            db.row_factory = aiosqlite.Row
            yield db
