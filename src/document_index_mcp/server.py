"""MCP STDIO server for Document-Index-MCP."""

import os
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .tools import (
    index_document_tool,
    search_document_tool,
    get_section_tool,
    get_document_overview_tool,
    list_documents_tool,
    delete_document_tool,
    get_statistics_tool,
    get_surrounding_sections_tool,
)

DB_PATH = Path(os.getenv("DOCUMENT_INDEX_DB_PATH", "data/documents.db"))

server = Server("document-index-mcp")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="search_document",
            description=(
                "Full-text search across indexed documents. Returns BM25-ranked "
                "results with text snippets. Use to find relevant sections in large "
                "documents. Supports scoping to a single document via doc_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text"},
                    "doc_id": {"type": "string", "description": "Optional: scope to one document"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_section",
            description=(
                "Retrieve the full text of a specific document section by its "
                "reference (e.g. 's2.1', 'page-3'). Use after search to read "
                "complete section content."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "section_ref": {"type": "string"},
                },
                "required": ["doc_id", "section_ref"],
            },
        ),
        Tool(
            name="get_document_overview",
            description=(
                "Get document metadata and table of contents (all section titles). "
                "Use to understand document structure before searching."
            ),
            inputSchema={
                "type": "object",
                "properties": {"doc_id": {"type": "string"}},
                "required": ["doc_id"],
            },
        ),
        Tool(
            name="list_documents",
            description="List all indexed documents with section counts and metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 100},
                    "offset": {"type": "integer", "default": 0},
                },
            },
        ),
        Tool(
            name="get_surrounding_sections",
            description=(
                "Get sections before and after a given section for reading context. "
                "Useful when a search result needs more surrounding text."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "section_ref": {"type": "string"},
                    "before": {"type": "integer", "default": 1},
                    "after": {"type": "integer", "default": 1},
                },
                "required": ["doc_id", "section_ref"],
            },
        ),
        Tool(
            name="index_document",
            description=(
                "Parse and index a document file into the search database. "
                "Supports PDF, TXT, MD. Returns doc_id for subsequent queries."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to file"},
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="delete_document",
            description="Delete a document and all its indexed sections.",
            inputSchema={
                "type": "object",
                "properties": {"doc_id": {"type": "string"}},
                "required": ["doc_id"],
            },
        ),
        Tool(
            name="get_statistics",
            description="Get aggregate statistics: document count, total sections, total pages.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    import json

    handlers = {
        "search_document": lambda args: search_document_tool(
            args["query"], DB_PATH, doc_id=args.get("doc_id"), limit=args.get("limit", 10)
        ),
        "get_section": lambda args: get_section_tool(
            args["doc_id"], args["section_ref"], DB_PATH
        ),
        "get_document_overview": lambda args: get_document_overview_tool(
            args["doc_id"], DB_PATH
        ),
        "list_documents": lambda args: list_documents_tool(
            DB_PATH, limit=args.get("limit", 100), offset=args.get("offset", 0)
        ),
        "get_surrounding_sections": lambda args: get_surrounding_sections_tool(
            args["doc_id"], args["section_ref"], DB_PATH,
            before=args.get("before", 1), after=args.get("after", 1)
        ),
        "index_document": lambda args: index_document_tool(args["file_path"], DB_PATH),
        "delete_document": lambda args: delete_document_tool(args["doc_id"], DB_PATH),
        "get_statistics": lambda args: get_statistics_tool(DB_PATH),
    }

    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    try:
        result = await handler(arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except (ValueError, FileNotFoundError) as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
