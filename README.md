# Document-Index-MCP

FTS5-indexed document search MCP server for large documents (30+ pages).

Part of the [Ansvar](https://ansvar.ai) platform. Complements Document-Logic-MCP which uses LLM extraction for smaller documents requiring deep analysis.

## What It Does

Indexes uploaded documents into SQLite with FTS5 full-text search. Documents are parsed into structural sections (headings, slides, sheets) and made searchable with BM25 ranking. No AI/LLM processing — deterministic parse and index.

**Use when:** Documents are 30+ pages and need fast, reliable search over structure.
**Use Document-Logic-MCP instead when:** Documents are <30 pages and need deep LLM-extracted insights.

## Supported Formats

| Format | Parser | Section Strategy |
|--------|--------|-----------------|
| PDF | pdfplumber | Cross-page heading detection + merging |
| DOCX | python-docx | Heading styles, numbered patterns, table extraction |
| XLSX | openpyxl | One section per sheet |
| CSV | stdlib csv | Single section with full content |
| PPTX | python-pptx | One section per slide |
| HTML | BeautifulSoup | Heading-based splitting |
| TXT/MD | stdlib | Heading detection (numbered, all-caps) |
| Images | pytesseract + Pillow | OCR to text, then heading detection |

## Quick Start

### Docker (recommended)

```bash
docker build -t document-index-mcp .
docker run -p 8320:3000 \
  -e MCP_API_KEY=change-me \
  -v docindex-data:/app/data \
  document-index-mcp
```

### Local Development

```bash
uv sync
uv run python -m document_index_mcp --http    # HTTP server on port 3000
uv run python -m document_index_mcp            # STDIO MCP server
uv run pytest                                   # Run tests
```

## 10 MCP Tools

| Tool | Description |
|------|-------------|
| `index_document` | Parse and index a document file |
| `search_document` | Full-text search with BM25 ranking + snippets |
| `get_section` | Retrieve full text of a section by ref |
| `get_document_overview` | Document metadata + section TOC |
| `list_documents` | List all indexed documents |
| `get_surrounding_sections` | Context window around a section |
| `delete_document` | Remove document and all sections |
| `get_statistics` | Aggregate stats |
| `about` | Server info and capabilities |
| `list_supported_formats` | All supported file formats |

See [TOOLS.md](TOOLS.md) for complete parameter and response documentation.

## HTTP API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/index` | Index document (base64 content) |
| POST | `/search` | Full-text search |
| GET | `/documents` | List documents |
| GET | `/documents/{id}` | Document overview |
| GET | `/documents/{id}/sections/{ref}` | Get section |
| GET | `/documents/{id}/sections/{ref}/surrounding` | Context sections |
| DELETE | `/documents/{id}` | Delete document |
| GET | `/statistics` | Aggregate stats |
| GET | `/about` | Server info |
| GET | `/formats` | Supported formats |

## Architecture

```
Document File
    │
    ▼
Parser (PDF/DOCX/XLSX/...)
    │  Detects headings, splits into sections
    │  Cross-page merging for PDFs
    ▼
SQLite + FTS5
    │  One row per section
    │  Auto-sync triggers keep FTS5 in sync
    ▼
MCP Tools (STDIO) / HTTP API
    │  BM25 search with snippet()
    │  Section-level retrieval
    ▼
Agent (Intelligence Portal)
```

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `DOCUMENT_INDEX_DB_PATH` | `data/documents.db` | SQLite database path |
| `MAX_FILE_SIZE_MB` | `50` | Maximum file size in MB |
| `ALLOWED_UPLOAD_DIR` | (empty = no restriction) | Restrict STDIO file paths to this directory |
| `MCP_API_KEY` | required for HTTP unless auth disabled | Shared service key for HTTP callers |
| `MCP_AUTH_DISABLED` | `false` | Set to `true` only for isolated local development |

## Security

- **HTTP authentication:** All tenant data endpoints require `X-API-Key` unless `MCP_AUTH_DISABLED=true`
- **Tenant isolation:** HTTP and STDIO data operations now require `org_id`; conversation-scoped documents are further filtered by `user_id`
- **Scoped writes:** Organization-scoped create/delete operations require explicit org-write approval from the caller
- **Path traversal protection:** STDIO `index_document` validates resolved paths against `ALLOWED_UPLOAD_DIR`
- **SQL injection prevention:** All queries use parameterized statements; FTS5 MATCH uses safe tokenized queries (never raw user input)
- **File size limits:** Enforced before parsing (configurable via env var)
- **Base64 validation:** HTTP endpoint checks encoded size before decoding
- **Non-root Docker:** Runs as `appuser` (UID 1000)
- **ON DELETE CASCADE:** Foreign key cascade ensures FTS5 cleanup on document deletion

## License

Proprietary - Ansvar Systems. Internal use only.
