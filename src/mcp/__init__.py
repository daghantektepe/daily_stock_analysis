# -*- coding: utf-8 -*-
"""DSA native Model Context Protocol (MCP) server and CLI configuration helpers.

Exposes live quantitative screening, market regime / risk guardrails, crypto trend
signals, SEC Form 4 / PEAD / KAP event catalysts, simulated paper trading, and
individual stock technical analysis over standard MCP stdio JSON-RPC 2.0.
"""

from __future__ import annotations

from src.mcp.config_gen import (
    DSA_MCP_SERVER_NAME,
    build_claude_mcp_config,
    build_dsa_mcp_server_entry,
    get_project_root,
    install_project_mcp_configs,
    resolve_python_executable,
    write_temp_claude_mcp_config,
    write_temp_gemini_workspace_config,
)
from src.mcp.tools import McpToolSpec, build_dsa_mcp_tools

__all__ = [
    "DSA_MCP_SERVER_NAME",
    "DsaMcpServer",
    "McpToolSpec",
    "build_claude_mcp_config",
    "build_dsa_mcp_server_entry",
    "build_dsa_mcp_tools",
    "get_project_root",
    "install_project_mcp_configs",
    "resolve_python_executable",
    "run_stdio_server",
    "write_temp_claude_mcp_config",
    "write_temp_gemini_workspace_config",
]


def __getattr__(name: str):
    if name in {"DsaMcpServer", "run_stdio_server"}:
        from src.mcp import server as _server

        return getattr(_server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
