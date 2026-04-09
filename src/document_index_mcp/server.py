"""MCP STDIO server for Document-Index-MCP."""

import os
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .tools import (
    index_document_tool,
    search_document_tool,
    search_company_policies_tool,
    update_policy_metadata_tool,
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
            name="search_company_policies",
            description=(
                "Search the client's authoritative policy library with GRC-aware "
                "filters. Returns section-level results with control references "
                "(e.g. A.8.1), framework context, and parent policy metadata. "
                "Only searches documents explicitly added to the policy library — "
                "never returns ad-hoc uploads. Use for compliance gap analysis, "
                "policy review, and framework mapping. Combine filters for "
                'precision: doc_type="policy" + framework="DORA" returns only '
                "DORA-related policy sections."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": 'Search query (e.g., "ICT change management", "encryption at rest")',
                    },
                    "doc_type": {
                        "type": "string",
                        "enum": ["policy", "procedure", "guideline", "standard",
                                 "control_matrix", "risk_register", "asset_inventory",
                                 "soa", "evidence", "report", "other"],
                        "description": "Filter by document type",
                    },
                    "framework": {
                        "type": "string",
                        "description": 'Filter by framework (e.g., "DORA", "ISO 27001", "NIS2")',
                    },
                    "classification": {
                        "type": "string",
                        "enum": ["public", "internal", "confidential", "restricted"],
                        "description": "Filter by classification level",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["draft", "active", "under_review", "superseded", "retired"],
                        "description": "Filter by policy status",
                    },
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="update_policy_metadata",
            description=(
                "Update GRC metadata on a document: scope, doc_type, classification, "
                "status, framework_refs, owner, version, review_date, effective_date. "
                "Use to promote a document to the policy library (scope='policy_library') "
                "or correct auto-detected metadata. Only include fields to change."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string", "description": "Document ID to update"},
                    "scope": {
                        "type": "string",
                        "enum": ["general", "policy_library"],
                        "description": "Set to 'policy_library' to include in company policy searches",
                    },
                    "doc_type": {
                        "type": "string",
                        "enum": ["policy", "procedure", "guideline", "standard",
                                 "control_matrix", "risk_register", "asset_inventory",
                                 "soa", "evidence", "report", "other"],
                    },
                    "classification": {
                        "type": "string",
                        "enum": ["public", "internal", "confidential", "restricted"],
                    },
                    "status": {
                        "type": "string",
                        "enum": ["draft", "active", "under_review", "superseded", "retired"],
                    },
                    "framework_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": 'Framework identifiers (e.g., ["ISO 27001:A.8", "DORA:Art.9"])',
                    },
                    "owner": {"type": "string"},
                    "version": {"type": "string"},
                    "review_date": {"type": "string", "description": "ISO 8601 date"},
                    "effective_date": {"type": "string", "description": "ISO 8601 date"},
                },
                "required": ["doc_id"],
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
                "Supports PDF, DOCX, XLSX, CSV, PPTX, HTML, TXT, MD, and image files. "
                "Returns doc_id for subsequent queries."
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
        Tool(
            name="list_sources",
            description=(
                "List data sources and provenance: describes user-uploaded document "
                "ingestion and the parser library used for each file format."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="check_data_freshness",
            description=(
                "Report data freshness: returns the most recent upload date and "
                "document count. Notes that no scheduled refresh applies — data "
                "currency depends on manual uploads."
            ),
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
        "search_company_policies": lambda args: search_company_policies_tool(
            args["query"], DB_PATH,
            doc_type=args.get("doc_type"),
            framework=args.get("framework"),
            classification=args.get("classification"),
            status=args.get("status"),
            limit=args.get("limit", 20),
        ),
        "update_policy_metadata": lambda args: update_policy_metadata_tool(
            args["doc_id"], DB_PATH,
            scope=args.get("scope"),
            doc_type=args.get("doc_type"),
            classification=args.get("classification"),
            status=args.get("status"),
            framework_refs=args.get("framework_refs"),
            owner=args.get("owner"),
            version=args.get("version"),
            review_date=args.get("review_date"),
            effective_date=args.get("effective_date"),
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
        "about": lambda args: about_tool(),
        "list_supported_formats": lambda args: list_supported_formats_tool(),
        "list_sources": lambda args: list_sources_tool(),
        "check_data_freshness": lambda args: check_data_freshness_tool(DB_PATH),
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
