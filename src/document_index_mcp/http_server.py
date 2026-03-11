"""FastAPI HTTP server for Document-Index-MCP."""

import base64
import logging
import os
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel

from .tools import (
    MAX_FILE_SIZE,
    about_tool,
    delete_document_tool,
    get_document_overview_tool,
    get_section_tool,
    get_statistics_tool,
    get_surrounding_sections_tool,
    index_document_tool,
    list_documents_tool,
    list_supported_formats_tool,
    search_document_tool,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Document-Index-MCP", version="0.1.0")

DB_PATH = Path(os.getenv("DOCUMENT_INDEX_DB_PATH", "/app/data/documents.db"))
MCP_API_KEY = os.getenv("MCP_API_KEY", "").strip()
MCP_AUTH_DISABLED = os.getenv("MCP_AUTH_DISABLED", "").strip().lower() in {"1", "true", "yes"}


@dataclass(slots=True)
class AccessContext:
    org_id: str
    user_id: str | None = None
    allow_org_write: bool = False


class IndexRequest(BaseModel):
    filename: str
    content_base64: str
    title: str | None = None
    scope: Literal["conversation", "organization"] = "conversation"


class SearchRequest(BaseModel):
    query: str
    doc_id: Optional[str] = None
    limit: int = 10


def _header_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes"}


def require_access_context(
    x_org_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    x_allow_org_write: str | None = Header(default=None),
) -> AccessContext:
    if not MCP_AUTH_DISABLED:
        if not MCP_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MCP_API_KEY is not configured.",
            )
        if x_api_key != MCP_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MCP API key.",
            )

    if x_org_id is None or not x_org_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Org-Id header is required.",
        )

    user_id = x_user_id.strip() if x_user_id and x_user_id.strip() else None
    return AccessContext(
        org_id=x_org_id.strip(),
        user_id=user_id,
        allow_org_write=_header_truthy(x_allow_org_write),
    )


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "server": "Document-Index-MCP",
        "version": "0.1.0",
    }


@app.post("/index")
async def index_document(req: IndexRequest, access: AccessContext = Depends(require_access_context)):
    try:
        max_b64_size = MAX_FILE_SIZE * 4 // 3 + 4  # base64 overhead
        if len(req.content_base64) > max_b64_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {MAX_FILE_SIZE // (1024*1024)} MB)",
            )
        content = base64.b64decode(req.content_base64)
        suffix = Path(req.filename).suffix or ".txt"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(content)
            tmp_path = f.name
        try:
            return await index_document_tool(
                tmp_path,
                DB_PATH,
                org_id=access.org_id,
                scope=req.scope,
                owner_user_id=access.user_id,
                title=req.title,
                filename_override=req.filename,
                allow_org_write=access.allow_org_write,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/search")
async def search(req: SearchRequest, access: AccessContext = Depends(require_access_context)):
    return await search_document_tool(
        req.query,
        DB_PATH,
        org_id=access.org_id,
        user_id=access.user_id,
        doc_id=req.doc_id,
        limit=req.limit,
    )


@app.get("/documents")
async def list_documents(
    limit: int = 100,
    offset: int = 0,
    access: AccessContext = Depends(require_access_context),
):
    return await list_documents_tool(
        DB_PATH,
        org_id=access.org_id,
        user_id=access.user_id,
        limit=limit,
        offset=offset,
    )


@app.get("/documents/{doc_id}")
async def get_document(doc_id: str, access: AccessContext = Depends(require_access_context)):
    try:
        return await get_document_overview_tool(
            doc_id,
            DB_PATH,
            org_id=access.org_id,
            user_id=access.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/documents/{doc_id}/sections/{section_ref}")
async def get_section(doc_id: str, section_ref: str, access: AccessContext = Depends(require_access_context)):
    try:
        return await get_section_tool(
            doc_id,
            section_ref,
            DB_PATH,
            org_id=access.org_id,
            user_id=access.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/documents/{doc_id}/sections/{section_ref}/surrounding")
async def get_surrounding(
    doc_id: str,
    section_ref: str,
    before: int = 1,
    after: int = 1,
    access: AccessContext = Depends(require_access_context),
):
    try:
        return await get_surrounding_sections_tool(
            doc_id,
            section_ref,
            DB_PATH,
            org_id=access.org_id,
            user_id=access.user_id,
            before=before,
            after=after,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, access: AccessContext = Depends(require_access_context)):
    try:
        return await delete_document_tool(
            doc_id,
            DB_PATH,
            org_id=access.org_id,
            user_id=access.user_id,
            allow_org_write=access.allow_org_write,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/statistics")
async def statistics(access: AccessContext = Depends(require_access_context)):
    return await get_statistics_tool(
        DB_PATH,
        org_id=access.org_id,
        user_id=access.user_id,
    )


@app.get("/about")
async def about():
    return await about_tool()


@app.get("/formats")
async def formats():
    return await list_supported_formats_tool()
