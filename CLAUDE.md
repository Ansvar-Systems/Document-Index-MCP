# Document-Index-MCP

FTS5-indexed document search MCP for large documents (30+ pages).

## Architecture
- SQLite + FTS5 full-text search (same pattern as Law MCPs)
- No LLM processing — deterministic parse + index
- Parsers copied from Document-Logic-MCP (pdfplumber, python-docx, etc.)

## Key Files
- `src/document_index_mcp/database.py` — Schema + FTS5 setup
- `src/document_index_mcp/parsers/` — Document parsers (PDF, DOCX, etc.)
- `src/document_index_mcp/tools.py` — MCP tool implementations
- `src/document_index_mcp/fts.py` — FTS5 query builder (safe tokenization)
- `src/document_index_mcp/http_server.py` — FastAPI HTTP server
- `src/document_index_mcp/server.py` — MCP STDIO server

## Dev Commands
- `uv run pytest` — run tests
- `uv run python -m document_index_mcp --http` — run HTTP server
- `docker build -t document-index-mcp .` — build container

## Design Doc
See `docs/plans/2026-02-24-document-index-mcp-design.md` in the architecture repo.
