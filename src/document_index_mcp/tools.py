"""MCP tool implementations for Document-Index-MCP.

Tools:
- index_document_tool: Parse + store + FTS5 index a document (seconds)
- search_document_tool: Full-text search with BM25 ranking + snippets
- get_section_tool: Retrieve a specific section by doc_id + section_ref
- get_document_overview_tool: Document metadata + section TOC
- list_documents_tool: List all indexed documents
- get_surrounding_sections_tool: N sections before/after a given section
- delete_document_tool: Remove document and all sections
- get_statistics_tool: Aggregate stats (section count, word count)
"""

import logging
import os
import uuid
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

from .database import Database
from .fts import build_fts_query
from .parsers import (
    PDFParser, TextParser, DOCXParser, XLSXParser,
    CSVParser, PPTXParser, HTMLParser, ImageParser,
)

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "50")) * 1024 * 1024
ALLOWED_UPLOAD_DIR = os.getenv("ALLOWED_UPLOAD_DIR", "")

_PARSER_MAP = {
    ".pdf": PDFParser,
    ".txt": TextParser,
    ".md": TextParser,
    ".docx": DOCXParser,
    ".xlsx": XLSXParser,
    ".csv": CSVParser,
    ".pptx": PPTXParser,
    ".html": HTMLParser,
    ".htm": HTMLParser,
    ".png": ImageParser,
    ".jpg": ImageParser,
    ".jpeg": ImageParser,
    ".tiff": ImageParser,
    ".tif": ImageParser,
    ".bmp": ImageParser,
    ".gif": ImageParser,
    ".webp": ImageParser,
}

_METADATA_TEMPLATE = {
    "source": "Document-Index-MCP",
    "processing_mode": "indexed",
    "disclaimer": "Indexed document content. No AI extraction applied.",
}


async def index_document_tool(
    file_path: str, db_path: Path
) -> dict[str, Any]:
    """Parse and index a document into SQLite with FTS5."""
    fp = Path(file_path).resolve()
    if ALLOWED_UPLOAD_DIR:
        allowed = Path(ALLOWED_UPLOAD_DIR).resolve()
        if not str(fp).startswith(str(allowed) + os.sep) and fp != allowed:
            raise ValueError(
                f"Access denied: file must be under {ALLOWED_UPLOAD_DIR}"
            )
    if not fp.exists():
        raise FileNotFoundError(f"File not found: {fp.name}")
    if fp.stat().st_size > MAX_FILE_SIZE:
        raise ValueError(f"File too large (max {MAX_FILE_SIZE // (1024*1024)} MB)")

    parser_cls = _PARSER_MAP.get(fp.suffix.lower())
    if parser_cls is None:
        raise ValueError(f"Unsupported file type: {fp.suffix}")

    parse_result = parser_cls().parse(fp)

    db = Database(db_path)
    await db.initialize()
    doc_id = str(uuid.uuid4())

    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO documents (doc_id, filename, upload_date, page_count, "
            "sections_count, file_type, file_size_bytes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                doc_id,
                parse_result.filename,
                datetime.now().isoformat(),
                parse_result.page_count,
                len(parse_result.sections),
                fp.suffix.lower(),
                fp.stat().st_size,
            ),
        )
        for idx, section in enumerate(parse_result.sections):
            await conn.execute(
                "INSERT INTO sections (doc_id, section_ref, title, content, "
                "section_index, page_start, page_end, parent_ref) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    doc_id,
                    section.section_ref,
                    section.title,
                    section.content,
                    idx,
                    section.page_start,
                    section.page_end,
                    section.parent_ref,
                ),
            )
        await conn.commit()

    return {
        "doc_id": doc_id,
        "filename": parse_result.filename,
        "sections_count": len(parse_result.sections),
        "page_count": parse_result.page_count,
        "status": "indexed",
        "sections_preview": [s.title for s in parse_result.sections[:5]],
        "_metadata": _METADATA_TEMPLATE,
    }


async def search_document_tool(
    query: str,
    db_path: Path,
    doc_id: Optional[str] = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Full-text search across indexed documents with BM25 ranking."""
    fts = build_fts_query(query)
    if not fts.primary:
        return {"results": [], "query": query, "_metadata": _METADATA_TEMPLATE}

    db = Database(db_path)
    await db.initialize()

    async def _run_query(match_expr: str) -> list[dict]:
        async with db.connection() as conn:
            sql = """
                SELECT
                    s.doc_id,
                    d.filename,
                    s.section_ref,
                    s.title,
                    s.page_start,
                    s.page_end,
                    snippet(sections_fts, 1, '>>>', '<<<', '...', 40) as snippet,
                    bm25(sections_fts) as relevance
                FROM sections_fts
                JOIN sections s ON s.id = sections_fts.rowid
                JOIN documents d ON d.doc_id = s.doc_id
                WHERE sections_fts MATCH ?
            """
            params: list = [match_expr]
            if doc_id:
                sql += " AND s.doc_id = ?"
                params.append(doc_id)
            sql += " ORDER BY relevance LIMIT ?"
            params.append(limit)

            cursor = await conn.execute(sql, params)
            return [dict(row) for row in await cursor.fetchall()]

    results = await _run_query(fts.primary)
    if not results and fts.fallback:
        results = await _run_query(fts.fallback)

    return {
        "results": results,
        "query": query,
        "match_count": len(results),
        "_metadata": _METADATA_TEMPLATE,
    }


async def get_section_tool(
    doc_id: str, section_ref: str, db_path: Path
) -> dict[str, Any]:
    """Retrieve a specific section by document ID and section reference."""
    db = Database(db_path)
    await db.initialize()

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT s.*, d.filename FROM sections s "
            "JOIN documents d ON d.doc_id = s.doc_id "
            "WHERE s.doc_id = ? AND s.section_ref = ?",
            (doc_id, section_ref),
        )
        row = await cursor.fetchone()

    if not row:
        raise ValueError(f"Section {section_ref} not found in document {doc_id}")

    return {**dict(row), "_metadata": _METADATA_TEMPLATE}


async def get_document_overview_tool(
    doc_id: str, db_path: Path
) -> dict[str, Any]:
    """Get document metadata and section table of contents."""
    db = Database(db_path)
    await db.initialize()

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
        )
        doc = await cursor.fetchone()
        if not doc:
            raise ValueError(f"Document {doc_id} not found")

        cursor = await conn.execute(
            "SELECT section_ref, title, page_start, page_end "
            "FROM sections WHERE doc_id = ? ORDER BY section_index",
            (doc_id,),
        )
        sections = [dict(row) for row in await cursor.fetchall()]

    return {
        **dict(doc),
        "sections": sections,
        "_metadata": _METADATA_TEMPLATE,
    }


async def list_documents_tool(
    db_path: Path, limit: int = 100, offset: int = 0
) -> dict[str, Any]:
    """List all indexed documents."""
    db = Database(db_path)
    await db.initialize()

    async with db.connection() as conn:
        count_cursor = await conn.execute("SELECT COUNT(*) as cnt FROM documents")
        total = (await count_cursor.fetchone())["cnt"]

        cursor = await conn.execute(
            "SELECT doc_id, filename, title, upload_date, page_count, "
            "sections_count, file_type FROM documents "
            "ORDER BY upload_date DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        documents = [dict(row) for row in await cursor.fetchall()]

    return {
        "documents": documents,
        "count": len(documents),
        "total": total,
        "_metadata": _METADATA_TEMPLATE,
    }


async def get_surrounding_sections_tool(
    doc_id: str, section_ref: str, db_path: Path, before: int = 1, after: int = 1
) -> dict[str, Any]:
    """Get N sections before and after a given section for context."""
    db = Database(db_path)
    await db.initialize()

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT section_index FROM sections WHERE doc_id = ? AND section_ref = ?",
            (doc_id, section_ref),
        )
        row = await cursor.fetchone()
        if not row:
            raise ValueError(f"Section {section_ref} not found")

        idx = row["section_index"]
        cursor = await conn.execute(
            "SELECT section_ref, title, content, page_start, page_end "
            "FROM sections WHERE doc_id = ? "
            "AND section_index BETWEEN ? AND ? ORDER BY section_index",
            (doc_id, idx - before, idx + after),
        )
        sections = [dict(row) for row in await cursor.fetchall()]

    return {
        "target_ref": section_ref,
        "sections": sections,
        "_metadata": _METADATA_TEMPLATE,
    }


async def delete_document_tool(
    doc_id: str, db_path: Path
) -> dict[str, Any]:
    """Delete a document and all indexed sections."""
    db = Database(db_path)
    await db.initialize()

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT filename FROM documents WHERE doc_id = ?", (doc_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise ValueError(f"Document {doc_id} not found")
        filename = row["filename"]

        await conn.execute("DELETE FROM sections WHERE doc_id = ?", (doc_id,))
        await conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        await conn.commit()

    return {
        "deleted": doc_id,
        "filename": filename,
        "status": "deleted",
        "_metadata": _METADATA_TEMPLATE,
    }


async def get_statistics_tool(db_path: Path) -> dict[str, Any]:
    """Aggregate statistics across all indexed documents."""
    db = Database(db_path)
    await db.initialize()

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) as doc_count, "
            "COALESCE(SUM(sections_count), 0) as total_sections, "
            "COALESCE(SUM(page_count), 0) as total_pages "
            "FROM documents"
        )
        stats = dict(await cursor.fetchone())

    return {**stats, "_metadata": _METADATA_TEMPLATE}
