"""HTTP MCP transport package.

Exposes the shared Kubeastra MCP server over Streamable HTTP.

Usage:
    from http_mcp.http_server import app, main

    # Or run directly:
    python -m http_mcp.http_server --port 8001
"""

__version__ = "1.0.0"
__author__ = "Kubeastra"

__all__ = ["http_server", "http_client"]
