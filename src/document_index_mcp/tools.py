"""MCP tool implementations for Document-Index-MCP.

Tools:
- index_document_tool: Parse + store + FTS5 index a document (seconds)
- search_document_tool: Full-text search with BM25 ranking + snippets
- get_section_tool: Retrieve a specific section by doc_id + section_ref
- get_document_overview_tool: Document metadata + section TOC
- list_documents_tool: List indexed documents visible to the caller
- get_surrounding_sections_tool: N sections before/after a given section
- delete_document_tool: Remove a document the caller is allowed to manage
- get_statistics_tool: Aggregate stats for the caller's visible documents
"""

from datetime import datetime
import logging
import os
from pathlib import Path
from typing import Any, Optional
import uuid

from .database import Database
from .fts import build_fts_query
from .parsers import (
    CSVParser,
    DOCXParser,
    HTMLParser,
    ImageParser,
    PDFParser,
    PPTXParser,
    TextParser,
    XLSXParser,
)

logger = logging.getLogger(__name__)

_db_cache: dict[str, Database] = {}


async def _get_db(db_path: Path) -> Database:
    """Return a cached Database instance, initializing on first access."""
    key = str(db_path)
    if key not in _db_cache:
        db = Database(db_path)
        await db.initialize()
        _db_cache[key] = db
    return _db_cache[key]


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

_VALID_SCOPES = {"conversation", "organization"}


def _normalize_scope(scope: str) -> str:
    normalized = (scope or "").strip().lower()
    if normalized not in _VALID_SCOPES:
        raise ValueError(f"Invalid scope '{scope}'. Expected one of: {', '.join(sorted(_VALID_SCOPES))}")
    return normalized


def _document_access_clause(
    *,
    alias: str,
    org_id: str,
    user_id: str | None,
) -> tuple[str, list[Any]]:
    clause = f"{alias}.org_id = ? AND ({alias}.scope = 'organization'"
    params: list[Any] = [org_id]
    if user_id:
        clause += f" OR ({alias}.scope = 'conversation' AND {alias}.owner_user_id = ?)"
        params.append(user_id)
    clause += ")"
    return clause, params


def _require_org_write(scope: str, allow_org_write: bool) -> None:
    if scope == "organization" and not allow_org_write:
        raise PermissionError("Managing organization-scoped documents requires allow_org_write=true.")


async def index_document_tool(
    file_path: str,
    db_path: Path,
    *,
    org_id: str,
    scope: str = "conversation",
    owner_user_id: str | None = None,
    title: str | None = None,
    filename_override: str | None = None,
    allow_org_write: bool = False,
) -> dict[str, Any]:
    """Parse and index a document into SQLite with FTS5."""
    normalized_scope = _normalize_scope(scope)
    _require_org_write(normalized_scope, allow_org_write)
    if normalized_scope == "conversation" and not owner_user_id:
        raise ValueError("owner_user_id is required for conversation-scoped documents.")

    fp = Path(file_path).resolve()
    if ALLOWED_UPLOAD_DIR:
        allowed = Path(ALLOWED_UPLOAD_DIR).resolve()
        if not str(fp).startswith(str(allowed) + os.sep) and fp != allowed:
            raise ValueError(f"Access denied: file must be under {ALLOWED_UPLOAD_DIR}")
    if not fp.exists():
        raise FileNotFoundError(f"File not found: {fp.name}")
    if fp.stat().st_size > MAX_FILE_SIZE:
        raise ValueError(f"File too large (max {MAX_FILE_SIZE // (1024*1024)} MB)")

    parser_cls = _PARSER_MAP.get(fp.suffix.lower())
    if parser_cls is None:
        raise ValueError(f"Unsupported file type: {fp.suffix}")

    parse_result = parser_cls().parse(fp)
    effective_filename = filename_override or parse_result.filename
    effective_title = title.strip() if isinstance(title, str) and title.strip() else None

    db = await _get_db(db_path)
    doc_id = str(uuid.uuid4())

    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO documents ("
            "doc_id, org_id, owner_user_id, scope, filename, title, upload_date, "
            "page_count, sections_count, file_type, file_size_bytes"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                doc_id,
                org_id,
                owner_user_id,
                normalized_scope,
                effective_filename,
                effective_title,
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
        "org_id": org_id,
        "scope": normalized_scope,
        "owner_user_id": owner_user_id,
        "filename": effective_filename,
        "title": effective_title,
        "sections_count": len(parse_result.sections),
        "page_count": parse_result.page_count,
        "status": "indexed",
        "sections_preview": [s.title for s in parse_result.sections[:5]],
        "sections": [
            {
                "section_ref": s.section_ref,
                "title": s.title,
                "content": s.content,
                "section_index": idx,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "parent_ref": s.parent_ref,
            }
            for idx, s in enumerate(parse_result.sections)
        ],
        "_metadata": _METADATA_TEMPLATE,
    }


async def search_document_tool(
    query: str,
    db_path: Path,
    *,
    org_id: str,
    user_id: Optional[str] = None,
    doc_id: Optional[str] = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Full-text search across indexed documents with BM25 ranking."""
    limit = min(max(limit, 1), 100)
    fts = build_fts_query(query)
    if not fts.primary:
        return {"results": [], "query": query, "_metadata": _METADATA_TEMPLATE}

    db = await _get_db(db_path)
    access_clause, access_params = _document_access_clause(alias="d", org_id=org_id, user_id=user_id)

    async def _run_query(match_expr: str) -> list[dict]:
        async with db.connection() as conn:
            sql = f"""
                SELECT
                    s.doc_id,
                    d.filename,
                    d.title AS doc_title,
                    d.scope,
                    s.section_ref,
                    s.title,
                    s.page_start,
                    s.page_end,
                    snippet(sections_fts, 1, '>>>', '<<<', '...', 40) AS snippet,
                    bm25(sections_fts) AS relevance
                FROM sections_fts
                JOIN sections s ON s.id = sections_fts.rowid
                JOIN documents d ON d.doc_id = s.doc_id
                WHERE sections_fts MATCH ?
                  AND {access_clause}
            """
            params: list[Any] = [match_expr, *access_params]
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
    doc_id: str,
    section_ref: str,
    db_path: Path,
    *,
    org_id: str,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Retrieve a specific section by document ID and section reference."""
    db = await _get_db(db_path)
    access_clause, access_params = _document_access_clause(alias="d", org_id=org_id, user_id=user_id)

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT s.*, d.filename, d.title AS doc_title, d.scope "
            "FROM sections s "
            "JOIN documents d ON d.doc_id = s.doc_id "
            f"WHERE s.doc_id = ? AND s.section_ref = ? AND {access_clause}",
            (doc_id, section_ref, *access_params),
        )
        row = await cursor.fetchone()

    if not row:
        raise ValueError(f"Section {section_ref} not found in document {doc_id}")

    return {**dict(row), "_metadata": _METADATA_TEMPLATE}


async def get_document_overview_tool(
    doc_id: str,
    db_path: Path,
    *,
    org_id: str,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Get document metadata and section table of contents."""
    db = await _get_db(db_path)
    access_clause, access_params = _document_access_clause(alias="documents", org_id=org_id, user_id=user_id)

    async with db.connection() as conn:
        cursor = await conn.execute(
            f"SELECT * FROM documents WHERE doc_id = ? AND {access_clause}",
            (doc_id, *access_params),
        )
        doc = await cursor.fetchone()
        if not doc:
            raise ValueError(f"Document {doc_id} not found")

        cursor = await conn.execute(
            "SELECT section_ref, title, content, section_index, "
            "page_start, page_end, parent_ref "
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
    db_path: Path,
    *,
    org_id: str,
    user_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """List indexed documents visible to the caller."""
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    db = await _get_db(db_path)
    access_clause, access_params = _document_access_clause(alias="documents", org_id=org_id, user_id=user_id)

    async with db.connection() as conn:
        count_cursor = await conn.execute(
            f"SELECT COUNT(*) AS cnt FROM documents WHERE {access_clause}",
            access_params,
        )
        total = (await count_cursor.fetchone())["cnt"]

        cursor = await conn.execute(
            "SELECT doc_id, filename, title, scope, upload_date, page_count, "
            "sections_count, file_type FROM documents "
            f"WHERE {access_clause} "
            "ORDER BY upload_date DESC LIMIT ? OFFSET ?",
            (*access_params, limit, offset),
        )
        documents = [dict(row) for row in await cursor.fetchall()]

    return {
        "documents": documents,
        "count": len(documents),
        "total": total,
        "_metadata": _METADATA_TEMPLATE,
    }


async def get_surrounding_sections_tool(
    doc_id: str,
    section_ref: str,
    db_path: Path,
    *,
    org_id: str,
    user_id: Optional[str] = None,
    before: int = 1,
    after: int = 1,
) -> dict[str, Any]:
    """Get N sections before and after a given section for context."""
    before = min(max(before, 0), 20)
    after = min(max(after, 0), 20)
    db = await _get_db(db_path)
    access_clause, access_params = _document_access_clause(alias="d", org_id=org_id, user_id=user_id)

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT s.section_index FROM sections s "
            "JOIN documents d ON d.doc_id = s.doc_id "
            f"WHERE s.doc_id = ? AND s.section_ref = ? AND {access_clause}",
            (doc_id, section_ref, *access_params),
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
    doc_id: str,
    db_path: Path,
    *,
    org_id: str,
    user_id: Optional[str] = None,
    allow_org_write: bool = False,
) -> dict[str, Any]:
    """Delete a document and all indexed sections."""
    db = await _get_db(db_path)
    access_clause, access_params = _document_access_clause(alias="documents", org_id=org_id, user_id=user_id)

    async with db.connection() as conn:
        cursor = await conn.execute(
            f"SELECT filename, scope FROM documents WHERE doc_id = ? AND {access_clause}",
            (doc_id, *access_params),
        )
        row = await cursor.fetchone()
        if not row:
            raise ValueError(f"Document {doc_id} not found")

        scope = row["scope"]
        _require_org_write(scope, allow_org_write)
        filename = row["filename"]

        await conn.execute(
            "DELETE FROM sections WHERE doc_id = ?",
            (doc_id,),
        )
        await conn.execute(
            "DELETE FROM documents WHERE doc_id = ? AND org_id = ?",
            (doc_id, org_id),
        )
        await conn.commit()

    return {
        "deleted": doc_id,
        "filename": filename,
        "status": "deleted",
        "_metadata": _METADATA_TEMPLATE,
    }


async def about_tool() -> dict[str, Any]:
    """Return information about this MCP server."""
    return {
        "name": "Document-Index-MCP",
        "version": "0.1.0",
        "description": (
            "Indexes large documents (30+ pages) into SQLite with FTS5 "
            "full-text search. Complements Document-Logic-MCP which uses "
            "LLM extraction for smaller documents."
        ),
        "supported_formats": list(_PARSER_MAP.keys()),
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "capabilities": [
            "Full-text search with BM25 ranking",
            "Cross-page section merging",
            "Section-level retrieval with context",
            "Tenant-scoped HTTP access controls",
            "PDF, DOCX, XLSX, CSV, PPTX, HTML, TXT, MD, image (OCR) support",
        ],
        "_metadata": _METADATA_TEMPLATE,
    }


async def list_supported_formats_tool() -> dict[str, Any]:
    """List all file formats this MCP can index, with details."""
    formats = {
        ".pdf": "PDF documents with cross-page section merging",
        ".docx": "Microsoft Word documents with heading detection and table extraction",
        ".xlsx": "Excel spreadsheets (one section per sheet)",
        ".csv": "CSV files (single section with full content)",
        ".pptx": "PowerPoint presentations (one section per slide)",
        ".html": "HTML pages with heading-based section splitting",
        ".htm": "HTML pages with heading-based section splitting",
        ".txt": "Plain text with heading detection",
        ".md": "Markdown files with heading detection",
        ".png": "Images via OCR (requires Tesseract)",
        ".jpg": "Images via OCR (requires Tesseract)",
        ".jpeg": "Images via OCR (requires Tesseract)",
        ".tiff": "Images via OCR (requires Tesseract)",
        ".tif": "Images via OCR (requires Tesseract)",
        ".bmp": "Images via OCR (requires Tesseract)",
        ".gif": "Images via OCR (requires Tesseract)",
        ".webp": "Images via OCR (requires Tesseract)",
    }
    return {
        "formats": formats,
        "count": len(formats),
        "_metadata": _METADATA_TEMPLATE,
    }


async def get_statistics_tool(
    db_path: Path,
    *,
    org_id: str,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Aggregate statistics across indexed documents visible to the caller."""
    db = await _get_db(db_path)
    access_clause, access_params = _document_access_clause(alias="documents", org_id=org_id, user_id=user_id)

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) AS doc_count, "
            "COALESCE(SUM(sections_count), 0) AS total_sections, "
            "COALESCE(SUM(page_count), 0) AS total_pages "
            f"FROM documents WHERE {access_clause}",
            access_params,
        )
        stats = dict(await cursor.fetchone())

    return {**stats, "_metadata": _METADATA_TEMPLATE}
