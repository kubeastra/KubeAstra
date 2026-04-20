"""Shared MCP server bootstrap helpers."""

from __future__ import annotations

import logging

from mcp.server import Server
import mcp.types as types

from config.settings import settings
from mcp_server.tools import register_tools


def log_runtime_settings(logger: logging.Logger) -> None:
    """Validate config and log the effective runtime settings."""
    settings.validate_settings()
    logger.info("Allowed namespaces: %s", settings.allowed_namespaces_list)
    logger.info("Kubectl timeout: %ss", settings.kubectl_timeout_seconds)
    logger.info("AI enabled: %s", settings.ai_enabled)
    logger.info("Recovery ops: %s", settings.enable_recovery_operations)


async def build_server(name: str) -> tuple[Server, int]:
    """Create an MCP server instance and return it with the registered tool count."""
    server = Server(name)
    register_tools(server)
    tool_count = len(await list_registered_tools(server))
    return server, tool_count


async def list_registered_tools(server: Server) -> list[types.Tool]:
    """Return the registered tool definitions from the MCP server."""
    if types.ListToolsRequest in server.request_handlers:
        await server.request_handlers[types.ListToolsRequest](None)
    return list(server._tool_cache.values())
