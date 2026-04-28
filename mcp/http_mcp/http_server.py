"""Run the Kubeastra MCP server over Streamable HTTP.

This exposes the same shared MCP toolset over a spec-compliant Streamable HTTP
transport (MCP March 2025+ protocol) that Cursor v1.0+ and other MCP clients
can connect to directly.

Highlights over the old SSE/WebSocket implementation:
  - Uses the official MCP SDK StreamableHTTPSessionManager for proper session tracking
  - Optional bearer-token auth for team/shared deployments
  - /debug/tools and /debug/call endpoints for local smoke tests
  - Configurable MCP path, JSON-response mode, and stateless mode
  - Shares tool registrations, schemas, and runtime.py bootstrap with the stdio server
    (no second tool implementation)
"""

from __future__ import annotations

import logging
import os
import secrets
import sys
from argparse import ArgumentParser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.responses import Response

# Add MCP root to path
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

try:
    from mcp.server import Server
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    import mcp.types as types
    from mcp_server.runtime import build_server, list_registered_tools, log_runtime_settings
except ImportError as e:
    print(f"Error importing MCP modules: {e}")
    print("Make sure to run: pip install -r requirements.txt")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

class HTTPConfig(BaseModel):
    """Runtime settings for the HTTP MCP server.

    All fields can be set via environment variables so the server can be
    configured without rebuilding the container image.
    """

    host: str = Field(default_factory=lambda: os.getenv("MCP_HTTP_HOST", "127.0.0.1"))
    port: int = Field(default_factory=lambda: int(os.getenv("MCP_HTTP_PORT", "8001")))
    mcp_path: str = Field(default_factory=lambda: os.getenv("MCP_HTTP_PATH", "/mcp"))
    auth_token: str | None = Field(default_factory=lambda: os.getenv("MCP_HTTP_AUTH_TOKEN") or None)
    json_response: bool = False   # set True to get JSON bodies instead of SSE streams
    stateless: bool = False       # set True to disable server-side session tracking


class DebugToolCallRequest(BaseModel):
    """Request body for the /debug/call smoke-test endpoint."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_mcp_path(path: str) -> str:
    """Ensure the MCP path starts with / and ends with / for mount compatibility."""
    if not path.startswith("/"):
        path = f"/{path}"
    path = path.rstrip("/")
    if not path:
        path = "/mcp"
    return f"{path}/"


def _authorize_request(request: Request, auth_token: str | None) -> None:
    """Raise HTTP 401 if a bearer token is configured and the request doesn't supply it."""
    if not auth_token:
        return
    auth_header = request.headers.get("authorization", "")
    expected = f"Bearer {auth_token}"
    if not secrets.compare_digest(auth_header, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")


# ── ASGI mount for the MCP transport ──────────────────────────────────────────

class StreamableHTTPMount:
    """Thin ASGI shim that forwards MCP-path requests to the session manager."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # pragma: no cover
        request = Request(scope, receive)
        _authorize_request(request, self.app.state.auth_token)
        manager: StreamableHTTPSessionManager | None = self.app.state.session_manager
        if manager is None:
            resp = JSONResponse({"detail": "MCP session manager not initialized"}, status_code=503)
            await resp(scope, receive, send)
            return
        await manager.handle_request(scope, receive, send)


# ── App factory ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the shared MCP server and HTTP session manager on app startup."""
    try:
        log_runtime_settings(logger)
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        raise

    server, tool_count = await build_server("mcp-http")
    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=app.state.http_config.json_response,
        stateless=app.state.http_config.stateless,
    )

    app.state.mcp_server = server
    app.state.tool_count = tool_count
    app.state.session_manager = session_manager

    logger.info(
        "HTTP MCP server ready — %s:%s%s — %s tools registered",
        app.state.http_config.host,
        app.state.http_config.port,
        app.state.http_config.mcp_path,
        tool_count,
    )

    async with session_manager.run():
        yield


def create_app(http_config: HTTPConfig | None = None) -> FastAPI:
    """Return a configured FastAPI app exposing the MCP toolset over Streamable HTTP."""
    http_config = http_config or HTTPConfig()
    http_config.mcp_path = _normalize_mcp_path(http_config.mcp_path)

    app = FastAPI(
        title="Kubeastra MCP Server (HTTP)",
        description="Streamable HTTP transport for the shared Kubeastra MCP toolset.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.http_config = http_config
    app.state.auth_token = http_config.auth_token
    app.state.mcp_server = None
    app.state.tool_count = 0
    app.state.session_manager = None

    # ── Informational root ────────────────────────────────────────────────────

    @app.get("/")
    async def root():
        cfg = app.state.http_config
        return {
            "name": "Kubeastra MCP Server (HTTP)",
            "transport": "streamable-http",
            "protocol": "MCP March 2025+",
            "mcp_endpoint": cfg.mcp_path,
            "endpoints": {
                "GET /health": "Health check",
                "GET /debug/tools": "List all registered tools (smoke test)",
                "POST /debug/call": "Call a tool directly (smoke test)",
                f"GET|POST {cfg.mcp_path}": "MCP Streamable HTTP transport",
            },
            "auth_enabled": bool(cfg.auth_token),
            "cursor_config_example": {
                "mcpServers": {
                    "kubeastra-http": {
                        "type": "http",
                        "url": f"http://{cfg.host}:{cfg.port}{cfg.mcp_path}",
                    }
                }
            },
        }

    # ── Health check ──────────────────────────────────────────────────────────

    @app.get("/health")
    async def health_check():
        cfg = app.state.http_config
        return {
            "status": "ok",
            "transport": "streamable-http",
            "protocol": "MCP March 2025+",
            "mcp_server": "running" if app.state.mcp_server else "not initialized",
            "tools_count": app.state.tool_count,
            "mcp_endpoint": cfg.mcp_path,
            "auth_enabled": bool(cfg.auth_token),
        }

    # ── Debug endpoints (not part of MCP protocol) ────────────────────────────

    @app.get("/debug/tools")
    async def debug_list_tools(request: Request):
        """List all registered tools — useful for local smoke tests."""
        _authorize_request(request, app.state.auth_token)
        server: Server | None = app.state.mcp_server
        if server is None:
            return {"tools": []}
        tools = await list_registered_tools(server)
        return {
            "tools_count": len(tools),
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema,
                }
                for t in tools
            ],
        }

    @app.post("/debug/call")
    async def debug_call_tool(request: Request, body: DebugToolCallRequest):
        """Call a tool directly without going through the MCP protocol — useful for smoke tests."""
        _authorize_request(request, app.state.auth_token)
        server: Server | None = app.state.mcp_server
        if server is None:
            raise HTTPException(status_code=503, detail="MCP server not initialized")
        try:
            handler = server.request_handlers.get(types.CallToolRequest)
            if handler is None:
                raise RuntimeError("MCP call handler is not registered")
            mcp_request = types.CallToolRequest(
                params=types.CallToolRequestParams(
                    name=body.tool_name,
                    arguments=body.arguments,
                )
            )
            server_result = await handler(mcp_request)
            result = server_result.root
        except Exception as e:
            logger.error("Error calling tool %s: %s", body.tool_name, e, exc_info=True)
            return JSONResponse(
                {"success": False, "tool": body.tool_name, "error": str(e)},
                status_code=500,
            )

        return {
            "success": not getattr(result, "isError", False),
            "tool": body.tool_name,
            "isError": getattr(result, "isError", False),
            "results": [
                block.model_dump(mode="json") if hasattr(block, "model_dump") else block
                for block in getattr(result, "content", [])
            ],
            "structuredContent": getattr(result, "structuredContent", None),
        }

    # ── Mount MCP transport ───────────────────────────────────────────────────
    app.mount(http_config.mcp_path, StreamableHTTPMount(app))

    return app


# Module-level app instance (used by uvicorn when launched via `python http_server.py`)
app = create_app()


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    """Parse CLI args and start the HTTP MCP server."""
    defaults = HTTPConfig()

    parser = ArgumentParser(description="Kubeastra MCP Server — Streamable HTTP transport")
    parser.add_argument("--host", default=defaults.host,
                        help="Host to bind to (default: 127.0.0.1; use 0.0.0.0 for network access)")
    parser.add_argument("--port", type=int, default=defaults.port,
                        help="Port to listen on (default: 8001)")
    parser.add_argument("--mcp-path", default=defaults.mcp_path,
                        help="HTTP path for the MCP transport (default: /mcp)")
    parser.add_argument("--auth-token", default=defaults.auth_token,
                        help="Optional bearer token — clients must send Authorization: Bearer <token>")
    parser.add_argument("--json-response", action="store_true",
                        help="Return JSON bodies instead of SSE streams")
    parser.add_argument("--stateless", action="store_true",
                        help="Disable server-side session tracking (one-shot requests)")
    parser.add_argument("--reload", action="store_true",
                        help="Enable uvicorn auto-reload (development only)")
    args = parser.parse_args()

    cfg = HTTPConfig(
        host=args.host,
        port=args.port,
        mcp_path=args.mcp_path,
        auth_token=args.auth_token,
        json_response=args.json_response,
        stateless=args.stateless,
    )

    logger.info("Starting Kubeastra MCP HTTP server")
    logger.info("  Health:      http://%s:%s/health", cfg.host, cfg.port)
    logger.info("  Debug tools: http://%s:%s/debug/tools", cfg.host, cfg.port)
    logger.info("  MCP (HTTP):  http://%s:%s%s", cfg.host, cfg.port, _normalize_mcp_path(cfg.mcp_path))
    logger.info("  Auth:        %s", "enabled" if cfg.auth_token else "disabled")

    uvicorn.run(
        create_app(cfg),
        host=cfg.host,
        port=cfg.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
