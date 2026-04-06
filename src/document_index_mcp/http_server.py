"""FastAPI HTTP server for Document-Index-MCP."""

import base64
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
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
    list_sources_tool,
    check_data_freshness_tool,
)

logger = logging.getLogger(__name__)

# --- Authentication ---
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(_api_key_header)):
    """Verify API key if MCP_API_KEY is configured. Skip auth if unset (dev mode)."""
    required_key = os.getenv("MCP_API_KEY")
    if not required_key:
        return  # No key configured — allow (dev mode)
    if api_key != required_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return api_key


# Initialize FastAPI app — all endpoints require API key when MCP_API_KEY is set
app = FastAPI(
    title="Document-Index-MCP",
    version="0.1.0",
    dependencies=[Depends(verify_api_key)],
)

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


# --- Unauthenticated health check (override removes app-level auth dependency) ---
from fastapi import APIRouter as _APIRouter

_health_router = _APIRouter(dependencies=[])


@_health_router.get("/health")
async def health():
    return {
        "status": "healthy",
        "server": "Document-Index-MCP",
        "version": "0.1.0",
    }


app.include_router(_health_router)


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


@app.get("/sources")
async def sources():
    return await list_sources_tool()


@app.get("/freshness")
async def freshness():
    return await check_data_freshness_tool(DB_PATH)
