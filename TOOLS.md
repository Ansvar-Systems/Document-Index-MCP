# Document-Index-MCP — Tools Reference

**Version:** 0.1.0
**Transport:** STDIO (MCP protocol) + HTTP (FastAPI on port 3000)
**Database:** SQLite + FTS5

---

## index_document

Parse and index a document file into the SQLite FTS5 search database.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `file_path` | string | yes | Absolute path to file (STDIO only). HTTP uses `content_base64` + `filename`. |

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `doc_id` | string | UUID for subsequent queries |
| `filename` | string | Original filename |
| `sections_count` | integer | Number of sections extracted |
| `page_count` | integer | Number of pages (PDF/PPTX) or null |
| `status` | string | Always `"indexed"` |
| `sections_preview` | array | First 5 section titles |

**Supported formats:** `.pdf`, `.docx`, `.xlsx`, `.csv`, `.pptx`, `.html`, `.htm`, `.txt`, `.md`, `.png`, `.jpg`, `.jpeg`, `.tiff`, `.tif`, `.bmp`, `.gif`, `.webp`

**Limits:** Max file size configurable via `MAX_FILE_SIZE_MB` env var (default: 50 MB). STDIO path restricted to `ALLOWED_UPLOAD_DIR` if set.

**HTTP:** `POST /index` with JSON body `{"filename": "report.pdf", "content_base64": "...", "scope": "conversation|organization"}` and headers `X-API-Key`, `X-Org-Id`, optional `X-User-Id`, and `X-Allow-Org-Write: true` for organisation-scoped writes.

---

## search_document

Full-text search across all indexed documents with BM25 ranking and text snippets.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `query` | string | yes | — | Search query text |
| `doc_id` | string | no | null | Scope search to one document |
| `limit` | integer | no | 10 | Max results (clamped 1-100) |

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `results` | array | Matching sections with BM25 relevance |
| `results[].doc_id` | string | Document UUID |
| `results[].filename` | string | Source filename |
| `results[].section_ref` | string | Section reference (e.g. `s2.1`, `page-3`) |
| `results[].title` | string | Section heading |
| `results[].snippet` | string | Matching text with `>>>highlight<<<` markers |
| `results[].relevance` | float | BM25 score (lower = more relevant) |
| `results[].page_start` | integer | Starting page number |
| `results[].page_end` | integer | Ending page number |
| `query` | string | Original query echoed back |
| `match_count` | integer | Number of results returned |

**Search behavior:** Query is tokenized (Unicode NFC normalized, single-char tokens stripped). Primary search uses AND semantics with prefix matching. If zero results and multiple tokens, falls back to OR semantics.

**HTTP:** `POST /search` with JSON body `{"query": "risk assessment", "doc_id": "optional-uuid", "limit": 10}` plus headers `X-API-Key`, `X-Org-Id`, optional `X-User-Id`.

---

## get_section

Retrieve the full text of a specific document section.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `doc_id` | string | yes | Document UUID |
| `section_ref` | string | yes | Section reference (e.g. `s2.1`, `page-3`, `sheet-1`) |

**Returns:** Full section row including `title`, `content`, `page_start`, `page_end`, `parent_ref`, `filename`.

**HTTP:** `GET /documents/{doc_id}/sections/{section_ref}` plus headers `X-API-Key`, `X-Org-Id`, optional `X-User-Id`

---

## get_document_overview

Get document metadata and table of contents (all section titles and refs).

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `doc_id` | string | yes | Document UUID |

**Returns:** Document metadata (`filename`, `upload_date`, `page_count`, `sections_count`, `file_type`, `file_size_bytes`) plus `sections` array with `section_ref`, `title`, `page_start`, `page_end` for each section.

**HTTP:** `GET /documents/{doc_id}` plus headers `X-API-Key`, `X-Org-Id`, optional `X-User-Id`

---

## list_documents

List all indexed documents with metadata.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `limit` | integer | no | 100 | Max documents (clamped 1-100) |
| `offset` | integer | no | 0 | Pagination offset |

**Returns:** `documents` array, `count` (returned), `total` (in database).

**HTTP:** `GET /documents?limit=100&offset=0` plus headers `X-API-Key`, `X-Org-Id`, optional `X-User-Id`

---

## get_surrounding_sections

Get N sections before and after a given section for reading context.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `doc_id` | string | yes | — | Document UUID |
| `section_ref` | string | yes | — | Target section reference |
| `before` | integer | no | 1 | Sections before (clamped 0-20) |
| `after` | integer | no | 1 | Sections after (clamped 0-20) |

**Returns:** `target_ref` and `sections` array with full content for the range.

**HTTP:** `GET /documents/{doc_id}/sections/{section_ref}/surrounding?before=1&after=1` plus headers `X-API-Key`, `X-Org-Id`, optional `X-User-Id`

---

## delete_document

Delete a document and all its indexed sections (cascades to FTS5).

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `doc_id` | string | yes | Document UUID |

**Returns:** `deleted` (doc_id), `filename`, `status: "deleted"`.

**HTTP:** `DELETE /documents/{doc_id}` plus headers `X-API-Key`, `X-Org-Id`, optional `X-User-Id`; deleting organisation-scoped docs also requires `X-Allow-Org-Write: true`

---

## get_statistics

Aggregate statistics across all indexed documents.

**Parameters:** None.

**Returns:** `doc_count`, `total_sections`, `total_pages`.

**HTTP:** `GET /statistics` plus headers `X-API-Key`, `X-Org-Id`, optional `X-User-Id`

---

## about

Get information about this MCP server.

**Parameters:** None.

**Returns:** `name`, `version`, `description`, `supported_formats` (array of extensions), `max_file_size_mb`, `capabilities` (array of feature descriptions).

**HTTP:** `GET /about`

---

## list_supported_formats

List all file formats this MCP can parse and index.

**Parameters:** None.

**Returns:** `formats` (object mapping extension to description), `count`.

**HTTP:** `GET /formats`

---

## Response Metadata

Every tool response includes a `_metadata` object:

```json
{
  "_metadata": {
    "source": "Document-Index-MCP",
    "processing_mode": "indexed",
    "disclaimer": "Indexed document content. No AI extraction applied."
  }
}
```
