"""FastAPI HTTP server for Document-Index-MCP."""

import base64
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .tools import (
    MAX_FILE_SIZE,
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

logger = logging.getLogger(__name__)

app = FastAPI(title="Document-Index-MCP", version="0.1.0")

DB_PATH = Path(os.getenv("DOCUMENT_INDEX_DB_PATH", "/app/data/documents.db"))


class IndexRequest(BaseModel):
    filename: str
    content_base64: str


class IndexFileRequest(BaseModel):
    object_key: str
    filename: str
    title: str | None = None


SHARED_FILES_PATH = Path(os.getenv("SHARED_FILES_PATH", "/data/uploads"))


class SearchRequest(BaseModel):
    query: str
    doc_id: Optional[str] = None
    limit: int = 10


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "server": "Document-Index-MCP",
        "version": "0.1.0",
    }


@app.post("/index")
async def index_document(req: IndexRequest):
    try:
        max_b64_size = MAX_FILE_SIZE * 4 // 3 + 4  # base64 overhead
        if len(req.content_base64) > max_b64_size:
            raise HTTPException(status_code=413, detail=f"File too large (max {MAX_FILE_SIZE // (1024*1024)} MB)")
        content = base64.b64decode(req.content_base64)
        suffix = Path(req.filename).suffix or ".txt"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(content)
            tmp_path = f.name
        try:
            result = await index_document_tool(tmp_path, DB_PATH)
            from .tools import _get_db
            db = await _get_db(DB_PATH)
            async with db.connection() as conn:
                await conn.execute(
                    "UPDATE documents SET filename = ? WHERE doc_id = ?",
                    (req.filename, result["doc_id"]),
                )
                await conn.commit()
            result["filename"] = req.filename
            return result
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/index-file")
async def index_file(req: IndexFileRequest):
    """Index a document from the shared filesystem by object_key."""
    resolved = (SHARED_FILES_PATH / req.object_key).resolve()
    if not resolved.is_relative_to(SHARED_FILES_PATH.resolve()):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.object_key}")

    try:
        result = await index_document_tool(str(resolved), DB_PATH)
        from .tools import _get_db
        db = await _get_db(DB_PATH)
        async with db.connection() as conn:
            await conn.execute(
                "UPDATE documents SET filename = ? WHERE doc_id = ?",
                (req.filename, result["doc_id"]),
            )
            await conn.commit()
        result["filename"] = req.filename
        return result
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/search")
async def search(req: SearchRequest):
    return await search_document_tool(req.query, DB_PATH, doc_id=req.doc_id, limit=req.limit)


@app.get("/documents")
async def list_documents(limit: int = 100, offset: int = 0):
    return await list_documents_tool(DB_PATH, limit=limit, offset=offset)


@app.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    try:
        return await get_document_overview_tool(doc_id, DB_PATH)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/documents/{doc_id}/sections/{section_ref}")
async def get_section(doc_id: str, section_ref: str):
    try:
        return await get_section_tool(doc_id, section_ref, DB_PATH)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/documents/{doc_id}/sections/{section_ref}/surrounding")
async def get_surrounding(doc_id: str, section_ref: str, before: int = 1, after: int = 1):
    try:
        return await get_surrounding_sections_tool(doc_id, section_ref, DB_PATH, before, after)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    try:
        return await delete_document_tool(doc_id, DB_PATH)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/statistics")
async def statistics():
    return await get_statistics_tool(DB_PATH)


@app.get("/about")
async def about():
    return await about_tool()


@app.get("/formats")
async def formats():
    return await list_supported_formats_tool()
