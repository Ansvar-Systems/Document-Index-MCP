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
    about_tool,
    list_supported_formats_tool,
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
                    "org_id": {"type": "string", "description": "Tenant/organisation identifier"},
                    "user_id": {"type": "string", "description": "Optional user identifier for conversation-scoped docs"},
                    "query": {"type": "string", "description": "Search query text"},
                    "doc_id": {"type": "string", "description": "Optional: scope to one document"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["org_id", "query"],
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
                    "org_id": {"type": "string"},
                    "user_id": {"type": "string", "description": "Optional user identifier for conversation-scoped docs"},
                    "doc_id": {"type": "string"},
                    "section_ref": {"type": "string"},
                },
                "required": ["org_id", "doc_id", "section_ref"],
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
                "properties": {
                    "org_id": {"type": "string"},
                    "user_id": {"type": "string", "description": "Optional user identifier for conversation-scoped docs"},
                    "doc_id": {"type": "string"},
                },
                "required": ["org_id", "doc_id"],
            },
        ),
        Tool(
            name="list_documents",
            description="List all indexed documents with section counts and metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "org_id": {"type": "string"},
                    "user_id": {"type": "string", "description": "Optional user identifier for conversation-scoped docs"},
                    "limit": {"type": "integer", "default": 100},
                    "offset": {"type": "integer", "default": 0},
                },
                "required": ["org_id"],
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
                    "org_id": {"type": "string"},
                    "user_id": {"type": "string", "description": "Optional user identifier for conversation-scoped docs"},
                    "doc_id": {"type": "string"},
                    "section_ref": {"type": "string"},
                    "before": {"type": "integer", "default": 1},
                    "after": {"type": "integer", "default": 1},
                },
                "required": ["org_id", "doc_id", "section_ref"],
            },
        ),
        Tool(
            name="index_document",
            description=(
                "Parse and index a document file into the search database. "
                "Supports PDF, DOCX, XLSX, CSV, PPTX, HTML, TXT, MD, and image files. "
                "Returns doc_id for subsequent queries."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to file"},
                    "org_id": {"type": "string", "description": "Tenant/organisation identifier"},
                    "scope": {
                        "type": "string",
                        "enum": ["conversation", "organization"],
                        "default": "conversation",
                    },
                    "owner_user_id": {
                        "type": "string",
                        "description": "Required for conversation-scoped documents",
                    },
                    "title": {"type": "string", "description": "Optional human-readable title"},
                    "allow_org_write": {
                        "type": "boolean",
                        "default": False,
                        "description": "Required when creating organization-scoped documents",
                    },
                },
                "required": ["file_path", "org_id"],
            },
        ),
        Tool(
            name="delete_document",
            description="Delete a document and all its indexed sections.",
            inputSchema={
                "type": "object",
                "properties": {
                    "org_id": {"type": "string"},
                    "user_id": {"type": "string", "description": "Optional user identifier for conversation-scoped docs"},
                    "doc_id": {"type": "string"},
                    "allow_org_write": {
                        "type": "boolean",
                        "default": False,
                        "description": "Required to delete organization-scoped documents",
                    },
                },
                "required": ["org_id", "doc_id"],
            },
        ),
        Tool(
            name="get_statistics",
            description="Get aggregate statistics: document count, total sections, total pages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "org_id": {"type": "string"},
                    "user_id": {"type": "string", "description": "Optional user identifier for conversation-scoped docs"},
                },
                "required": ["org_id"],
            },
        ),
        Tool(
            name="about",
            description="Get information about this MCP server: version, capabilities, supported formats.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_supported_formats",
            description="List all file formats this MCP can parse and index, with descriptions.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    import json

    handlers = {
        "search_document": lambda args: search_document_tool(
            args["query"],
            DB_PATH,
            org_id=args["org_id"],
            user_id=args.get("user_id"),
            doc_id=args.get("doc_id"),
            limit=args.get("limit", 10),
        ),
        "get_section": lambda args: get_section_tool(
            args["doc_id"],
            args["section_ref"],
            DB_PATH,
            org_id=args["org_id"],
            user_id=args.get("user_id"),
        ),
        "get_document_overview": lambda args: get_document_overview_tool(
            args["doc_id"],
            DB_PATH,
            org_id=args["org_id"],
            user_id=args.get("user_id"),
        ),
        "list_documents": lambda args: list_documents_tool(
            DB_PATH,
            org_id=args["org_id"],
            user_id=args.get("user_id"),
            limit=args.get("limit", 100),
            offset=args.get("offset", 0),
        ),
        "get_surrounding_sections": lambda args: get_surrounding_sections_tool(
            args["doc_id"], args["section_ref"], DB_PATH,
            org_id=args["org_id"],
            user_id=args.get("user_id"),
            before=args.get("before", 1),
            after=args.get("after", 1),
        ),
        "index_document": lambda args: index_document_tool(
            args["file_path"],
            DB_PATH,
            org_id=args["org_id"],
            scope=args.get("scope", "conversation"),
            owner_user_id=args.get("owner_user_id"),
            title=args.get("title"),
            allow_org_write=args.get("allow_org_write", False),
        ),
        "delete_document": lambda args: delete_document_tool(
            args["doc_id"],
            DB_PATH,
            org_id=args["org_id"],
            user_id=args.get("user_id"),
            allow_org_write=args.get("allow_org_write", False),
        ),
        "get_statistics": lambda args: get_statistics_tool(
            DB_PATH,
            org_id=args["org_id"],
            user_id=args.get("user_id"),
        ),
        "about": lambda args: about_tool(),
        "list_supported_formats": lambda args: list_supported_formats_tool(),
    }

    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    try:
        result = await handler(arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except (PermissionError, ValueError, FileNotFoundError) as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
