"""Entry point for Document-Index MCP server.

Usage:
    python -m document_index_mcp          # MCP server (STDIO)
    python -m document_index_mcp --http   # HTTP server
"""

import asyncio
import sys


def main():
    if "--http" in sys.argv:
        import uvicorn
        import os
        from .http_server import app

        port = int(os.getenv("PORT", "3000"))
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        from .server import main as mcp_main
        asyncio.run(mcp_main())


if __name__ == "__main__":
    main()
