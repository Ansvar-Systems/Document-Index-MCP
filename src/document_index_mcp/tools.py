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

import json
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

VALID_DOC_TYPES = {
    'policy', 'procedure', 'guideline', 'standard',
    'control_matrix', 'risk_register', 'asset_inventory',
    'soa', 'evidence', 'report', 'other',
}
VALID_CLASSIFICATIONS = {'public', 'internal', 'confidential', 'restricted'}
VALID_STATUSES = {'draft', 'active', 'under_review', 'superseded', 'retired'}

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


def _disambiguate_section_ref(section_ref: str, occurrence: int) -> str:
    """Return a stable, unique section_ref for duplicate headings."""
    if occurrence <= 1:
        return section_ref
    return f"{section_ref}--{occurrence}"


def _ensure_unique_section_refs(sections: list[Any]) -> None:
    """Make section refs unique within a parsed document.

    Some source documents repeat numbered headings such as "1. Scope" more
    than once. SQLite enforces uniqueness for (doc_id, section_ref), so later
    duplicates need a deterministic suffix before insert.
    """
    ref_counts: dict[str, int] = {}
    latest_ref_by_base: dict[str, str] = {}

    for idx, section in enumerate(sections):
        base_ref = (section.section_ref or "").strip() or f"section-{idx + 1}"
        base_parent_ref = (section.parent_ref or "").strip() or None

        occurrence = ref_counts.get(base_ref, 0) + 1
        ref_counts[base_ref] = occurrence

        unique_ref = _disambiguate_section_ref(base_ref, occurrence)
        section.section_ref = unique_ref
        section.parent_ref = (
            latest_ref_by_base.get(base_parent_ref, base_parent_ref)
            if base_parent_ref
            else None
        )

        latest_ref_by_base[base_ref] = unique_ref
        latest_ref_by_base[unique_ref] = unique_ref

        if occurrence > 1:
            logger.warning(
                "Duplicate section_ref %s detected; renamed to %s",
                base_ref,
                unique_ref,
            )


async def index_document_tool(
    file_path: str,
    db_path: Path,
    *,
    scope: str = "general",
    doc_type: Optional[str] = None,
    classification: str = "internal",
    status: str = "active",
    framework_refs: Optional[list[str]] = None,
    owner: Optional[str] = None,
    version: Optional[str] = None,
    review_date: Optional[str] = None,
    effective_date: Optional[str] = None,
    source_ref: Optional[str] = None,
    section_control_refs: Optional[dict[str, list[str]]] = None,
    section_framework_refs: Optional[dict[str, list[str]]] = None,
) -> dict[str, Any]:
    """Parse and index a document into SQLite with FTS5.

    GRC metadata (doc_type, framework_refs, etc.) is optional.
    Documents with scope='policy_library' are searchable via
    search_company_policies. section_control_refs maps section_ref
    to control identifiers (e.g. {"s4.1": ["A.8.24"]}).
    """
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

    if doc_type and doc_type not in VALID_DOC_TYPES:
        raise ValueError(f"Invalid doc_type: {doc_type}")
    if classification not in VALID_CLASSIFICATIONS:
        raise ValueError(f"Invalid classification: {classification}")
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    parser_cls = _PARSER_MAP.get(fp.suffix.lower())
    if parser_cls is None:
        raise ValueError(f"Unsupported file type: {fp.suffix}")

    parse_result = parser_cls().parse(fp)
    _ensure_unique_section_refs(parse_result.sections)

    db = await _get_db(db_path)
    doc_id = str(uuid.uuid4())
    fw_json = json.dumps(framework_refs) if framework_refs else None

    async with db.connection() as conn:
        await conn.execute(
            "INSERT INTO documents (doc_id, filename, upload_date, page_count, "
            "sections_count, file_type, file_size_bytes, "
            "scope, doc_type, classification, status, framework_refs, "
            "owner, version, review_date, effective_date, source_ref, last_synced) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                doc_id,
                parse_result.filename,
                datetime.now().isoformat(),
                parse_result.page_count,
                len(parse_result.sections),
                fp.suffix.lower(),
                fp.stat().st_size,
                scope,
                doc_type,
                classification,
                status,
                fw_json,
                owner,
                version,
                review_date,
                effective_date,
                source_ref,
                datetime.now().isoformat() if source_ref else None,
            ),
        )
        for idx, section in enumerate(parse_result.sections):
            s_ref = section.section_ref
            s_ctrl = json.dumps(section_control_refs.get(s_ref, [])) if section_control_refs and s_ref in section_control_refs else None
            s_fw = json.dumps(section_framework_refs.get(s_ref, [])) if section_framework_refs and s_ref in section_framework_refs else None
            await conn.execute(
                "INSERT INTO sections (doc_id, section_ref, title, content, "
                "section_index, page_start, page_end, parent_ref, "
                "control_refs, framework_refs) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    doc_id,
                    section.section_ref,
                    section.title,
                    section.content,
                    idx,
                    section.page_start,
                    section.page_end,
                    section.parent_ref,
                    s_ctrl,
                    s_fw,
                ),
            )
        await conn.commit()

    return {
        "doc_id": doc_id,
        "filename": parse_result.filename,
        "sections_count": len(parse_result.sections),
        "page_count": parse_result.page_count,
        "scope": scope,
        "doc_type": doc_type,
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
    doc_id: Optional[str] = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Full-text search across indexed documents with BM25 ranking."""
    limit = min(max(limit, 1), 100)
    fts = build_fts_query(query)
    if not fts.primary:
        return {"results": [], "query": query, "_metadata": _METADATA_TEMPLATE}

    db = await _get_db(db_path)

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


async def search_company_policies_tool(
    query: str,
    db_path: Path,
    doc_type: Optional[str] = None,
    framework: Optional[str] = None,
    classification: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search the client's authoritative policy library.

    Scoped to documents with scope='policy_library' — never returns ad-hoc
    uploads. Returns section-level results with control references, framework
    context, and parent policy metadata.
    """
    limit = min(max(limit, 1), 100)

    if doc_type and doc_type not in VALID_DOC_TYPES:
        raise ValueError(f"Invalid doc_type filter: {doc_type}")
    if classification and classification not in VALID_CLASSIFICATIONS:
        raise ValueError(f"Invalid classification filter: {classification}")
    if status and status not in VALID_STATUSES:
        raise ValueError(f"Invalid status filter: {status}")

    fts = build_fts_query(query)
    if not fts.primary:
        return {"results": [], "query": query, "total": 0, "_metadata": _METADATA_TEMPLATE}

    db = await _get_db(db_path)

    async def _run(match_expr: str) -> tuple[list[dict], int]:
        async with db.connection() as conn:
            conditions = ["sections_fts MATCH ?", "d.scope = 'policy_library'"]
            params: list[Any] = [match_expr]

            if doc_type:
                conditions.append("d.doc_type = ?")
                params.append(doc_type)
            if framework:
                conditions.append("d.framework_refs LIKE ?")
                params.append(f"%{framework}%")
            if classification:
                conditions.append("d.classification = ?")
                params.append(classification)
            if status:
                conditions.append("d.status = ?")
                params.append(status)

            where = " AND ".join(conditions)

            sql = f"""
                SELECT
                    s.id AS section_id,
                    s.section_ref,
                    s.title AS section_title,
                    s.content,
                    s.control_refs,
                    s.framework_refs AS section_framework_refs,
                    d.doc_id,
                    d.title AS policy_title,
                    d.doc_type,
                    d.classification,
                    d.framework_refs,
                    d.owner,
                    d.version,
                    d.status,
                    snippet(sections_fts, 1, '>>>', '<<<', '...', 40) AS snippet,
                    bm25(sections_fts) AS relevance
                FROM sections_fts
                JOIN sections s ON s.id = sections_fts.rowid
                JOIN documents d ON d.doc_id = s.doc_id
                WHERE {where}
                ORDER BY relevance
                LIMIT ?
            """
            params.append(limit)
            cursor = await conn.execute(sql, params)
            rows = [dict(r) for r in await cursor.fetchall()]

            # Skip COUNT query when we already have all results
            if len(rows) < limit:
                total = len(rows)
            else:
                count_sql = f"""
                    SELECT COUNT(*) AS cnt
                    FROM sections_fts
                    JOIN sections s ON s.id = sections_fts.rowid
                    JOIN documents d ON d.doc_id = s.doc_id
                    WHERE {where}
                """
                count_cursor = await conn.execute(count_sql, params[:-1])
                total = (await count_cursor.fetchone())["cnt"]

            return rows, total

    results, total = await _run(fts.primary)
    if not results and fts.fallback:
        results, total = await _run(fts.fallback)

    # Parse JSON arrays for clean output
    for r in results:
        for field in ("control_refs", "framework_refs", "section_framework_refs"):
            val = r.get(field)
            if val and isinstance(val, str):
                try:
                    r[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    r[field] = []
            elif not val:
                r[field] = []

    return {
        "results": results,
        "query": query,
        "total": total,
        "filters_applied": {
            k: v for k, v in {
                "doc_type": doc_type, "framework": framework,
                "classification": classification, "status": status,
            }.items() if v
        },
        "_metadata": _METADATA_TEMPLATE,
    }


async def update_policy_metadata_tool(
    doc_id: str,
    db_path: Path,
    *,
    scope: Optional[str] = None,
    doc_type: Optional[str] = None,
    classification: Optional[str] = None,
    status: Optional[str] = None,
    framework_refs: Optional[list[str]] = None,
    owner: Optional[str] = None,
    version: Optional[str] = None,
    review_date: Optional[str] = None,
    effective_date: Optional[str] = None,
) -> dict[str, Any]:
    """Update GRC metadata on an existing document. Admin override for auto-detected values."""
    db = await _get_db(db_path)

    updates: list[str] = []
    params: list[Any] = []

    if scope is not None:
        if scope not in ("general", "policy_library"):
            raise ValueError(f"Invalid scope: {scope}")
        updates.append("scope = ?")
        params.append(scope)
    if doc_type is not None:
        if doc_type not in VALID_DOC_TYPES:
            raise ValueError(f"Invalid doc_type: {doc_type}")
        updates.append("doc_type = ?")
        params.append(doc_type)
    if classification is not None:
        if classification not in VALID_CLASSIFICATIONS:
            raise ValueError(f"Invalid classification: {classification}")
        updates.append("classification = ?")
        params.append(classification)
    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        updates.append("status = ?")
        params.append(status)
    if framework_refs is not None:
        updates.append("framework_refs = ?")
        params.append(json.dumps(framework_refs))
    if owner is not None:
        updates.append("owner = ?")
        params.append(owner)
    if version is not None:
        updates.append("version = ?")
        params.append(version)
    if review_date is not None:
        updates.append("review_date = ?")
        params.append(review_date)
    if effective_date is not None:
        updates.append("effective_date = ?")
        params.append(effective_date)

    if not updates:
        raise ValueError("No fields to update")

    params.append(doc_id)

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT doc_id, filename FROM documents WHERE doc_id = ?", (doc_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise ValueError(f"Document {doc_id} not found")

        await conn.execute(
            f"UPDATE documents SET {', '.join(updates)} WHERE doc_id = ?",
            params,
        )
        await conn.commit()

    return {
        "doc_id": doc_id,
        "updated_fields": [u.split(" = ")[0] for u in updates],
        "status": "updated",
        "_metadata": _METADATA_TEMPLATE,
    }


async def get_section_tool(
    doc_id: str, section_ref: str, db_path: Path
) -> dict[str, Any]:
    """Retrieve a specific section by document ID and section reference."""
    db = await _get_db(db_path)

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
    db = await _get_db(db_path)

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
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
    db_path: Path, limit: int = 100, offset: int = 0
) -> dict[str, Any]:
    """List all indexed documents."""
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    db = await _get_db(db_path)

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
    before = min(max(before, 0), 20)
    after = min(max(after, 0), 20)
    db = await _get_db(db_path)

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
    db = await _get_db(db_path)

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


async def list_sources_tool(db_path: Path) -> dict[str, Any]:
    """List all indexed document sources with provenance metadata."""
    db = await _get_db(db_path)

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT doc_id, filename, title, file_type, scope, "
            "upload_date, last_synced, source_ref, owner, version, status "
            "FROM documents ORDER BY upload_date DESC"
        )
        sources = [dict(row) for row in await cursor.fetchall()]

    return {
        "sources": sources,
        "count": len(sources),
        "_metadata": _METADATA_TEMPLATE,
    }


async def check_data_freshness_tool(
    db_path: Path, stale_days: int = 90
) -> dict[str, Any]:
    """Check document freshness — returns age and staleness for each indexed document."""
    db = await _get_db(db_path)
    now = datetime.now()

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT doc_id, filename, upload_date, last_synced, status "
            "FROM documents ORDER BY upload_date ASC"
        )
        rows = [dict(row) for row in await cursor.fetchall()]

    results = []
    stale_count = 0
    for row in rows:
        indexed_at = row.get("upload_date")
        age_days = None
        is_stale = False
        if indexed_at:
            try:
                dt = datetime.fromisoformat(indexed_at)
                age_days = (now - dt).days
                is_stale = age_days > stale_days
            except (ValueError, TypeError):
                pass
        if is_stale:
            stale_count += 1
        results.append({**row, "age_days": age_days, "is_stale": is_stale})

    return {
        "documents": results,
        "total": len(results),
        "stale_count": stale_count,
        "stale_threshold_days": stale_days,
        "checked_at": now.isoformat(),
        "_metadata": _METADATA_TEMPLATE,
    }


async def get_statistics_tool(db_path: Path) -> dict[str, Any]:
    """Aggregate statistics across all indexed documents."""
    db = await _get_db(db_path)

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) as doc_count, "
            "COALESCE(SUM(sections_count), 0) as total_sections, "
            "COALESCE(SUM(page_count), 0) as total_pages "
            "FROM documents"
        )
        stats = dict(await cursor.fetchone())

    return {**stats, "_metadata": _METADATA_TEMPLATE}
