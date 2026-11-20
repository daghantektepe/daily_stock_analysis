# -*- coding: utf-8 -*-
"""Zero-dependency standard MCP stdio JSON-RPC 2.0 server for Daily Stock Analysis.

Supports both newline-delimited JSON-RPC (standard MCP stdio framing used by
Claude Code CLI and Gemini CLI) and Content-Length framing (LSP-style framing),
automatically echoing the client's framing format.

Run directly::

    python -m src.mcp.server
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import traceback
from typing import Any, BinaryIO, Dict, Iterable, List, Optional, Tuple

from src.mcp.tools import MAX_MCP_RESULT_BYTES, McpToolSpec, build_dsa_mcp_tools, safe_json_dumps

logger = logging.getLogger(__name__)

SERVER_NAME = "dsa-quant-mcp"
SERVER_VERSION = "1.0.0"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2024-11-05", "2025-03-26", "2025-06-18"})


class DsaMcpServer:
    """Pure-Python MCP JSON-RPC 2.0 protocol dispatcher."""

    def __init__(self, tools: Optional[Iterable[McpToolSpec]] = None) -> None:
        tool_list = list(tools) if tools is not None else build_dsa_mcp_tools()
        self._tools: Dict[str, McpToolSpec] = {spec.name: spec for spec in tool_list}

    @property
    def tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def list_tools_payload(self) -> List[Dict[str, Any]]:
        return [spec.to_mcp_descriptor() for spec in self._tools.values()]

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        spec = self._tools.get(name)
        if spec is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": safe_json_dumps(
                            {
                                "ok": False,
                                "error": f"Unknown tool: {name}",
                                "available_tools": self.tool_names,
                            }
                        ),
                    }
                ],
                "isError": True,
            }

        args = arguments if isinstance(arguments, dict) else {}
        try:
            # Always divert accidental print() calls inside data providers to stderr
            # so stdout remains strictly valid JSON-RPC frames.
            with contextlib.redirect_stdout(sys.stderr):
                result = spec.handler(args)
            text = safe_json_dumps(result, max_bytes=MAX_MCP_RESULT_BYTES)
            is_error = isinstance(result, dict) and result.get("ok") is False
            return {
                "content": [{"type": "text", "text": text}],
                "isError": is_error,
            }
        except Exception as exc:  # noqa: BLE001 - never crash the MCP transport loop
            logger.warning("[DSA-MCP] tool %s failed: %s", name, exc)
            err_payload = {
                "ok": False,
                "tool": name,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
            if os.getenv("DSA_MCP_DEBUG") == "1":
                err_payload["traceback"] = traceback.format_exc()
            return {
                "content": [{"type": "text", "text": safe_json_dumps(err_payload)}],
                "isError": True,
            }

    def handle_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle one decoded JSON-RPC 2.0 request/notification. Returns None for notifications."""
        if not isinstance(message, dict):
            return self._error_response(None, -32600, "Invalid Request: expected JSON object")

        method = message.get("method")
        req_id = message.get("id")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        is_notification = "id" not in message

        if not isinstance(method, str) or not method:
            if is_notification:
                return None
            return self._error_response(req_id, -32600, "Invalid Request: missing method")

        if method == "initialize":
            client_version = str(params.get("protocolVersion") or "").strip()
            protocol_version = (
                client_version
                if client_version in SUPPORTED_PROTOCOL_VERSIONS
                else DEFAULT_PROTOCOL_VERSION
            )
            return self._ok_response(
                req_id,
                {
                    "protocolVersion": protocol_version,
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    },
                    "instructions": (
                        "Daily Stock Analysis (DSA) Quantitative Trading & Research MCP Server. "
                        "Use these tools to inspect live market regimes, run empirical US/BIST/Crypto "
                        "quant strategies, scan SEC Form 4 executive buying, PEAD earnings drift, "
                        "KAP contract catalysts, and manage the simulated paper portfolio. "
                        "All paper trading operations are strictly simulated and never submit real orders."
                    ),
                },
            )

        if method in ("notifications/initialized", "notifications/cancelled"):
            return None

        if method == "ping":
            return self._ok_response(req_id, {})

        if method == "tools/list":
            return self._ok_response(req_id, {"tools": self.list_tools_payload()})

        if method == "tools/call":
            tool_name = str(params.get("name") or "").strip()
            arguments = params.get("arguments")
            if not tool_name:
                return self._error_response(req_id, -32602, "Invalid params: missing tool name")
            result = self.call_tool(tool_name, arguments if isinstance(arguments, dict) else {})
            return self._ok_response(req_id, result)

        if method in ("resources/list", "prompts/list"):
            key = "resources" if method.startswith("resources") else "prompts"
            return self._ok_response(req_id, {key: []})

        if is_notification:
            return None

        return self._error_response(req_id, -32601, f"Method not found: {method}")

    @staticmethod
    def _ok_response(req_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    @staticmethod
    def _error_response(req_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _read_framed_message(stream: BinaryIO) -> Tuple[Optional[bytes], str]:
    """Read one JSON-RPC message supporting both newline-delimited and Content-Length framing.

    Returns ``(payload_bytes, framing)`` where ``framing`` is ``"line"`` or ``"content-length"``,
    or ``(None, "eof")`` on EOF.
    """
    while True:
        first_line = stream.readline()
        if not first_line:
            return None, "eof"
        stripped = first_line.strip()
        if not stripped:
            continue

        # Newline-delimited JSON-RPC (standard MCP stdio transport)
        if stripped.startswith(b"{") or stripped.startswith(b"["):
            return stripped, "line"

        # Content-Length header framing (LSP / legacy MCP clients)
        headers: Dict[str, str] = {}
        line = first_line
        while line and line.strip():
            decoded = line.decode("ascii", errors="ignore")
            if ":" in decoded:
                k, v = decoded.split(":", 1)
                headers[k.strip().lower()] = v.strip()
            line = stream.readline()

        content_length_raw = headers.get("content-length")
        if content_length_raw is None:
            continue
        try:
            content_length = int(content_length_raw)
        except ValueError:
            continue
        if content_length <= 0:
            continue
        payload = stream.read(content_length)
        if not payload:
            return None, "eof"
        return payload, "content-length"


def _write_framed_message(stream: BinaryIO, response: Dict[str, Any], framing: str) -> None:
    encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if framing == "content-length":
        header = f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii")
        stream.write(header)
        stream.write(encoded)
    else:
        stream.write(encoded + b"\n")
    stream.flush()


def run_stdio_server(
    *,
    server: Optional[DsaMcpServer] = None,
    stdin: Optional[BinaryIO] = None,
    stdout: Optional[BinaryIO] = None,
) -> int:
    """Run the MCP JSON-RPC loop over stdio until EOF."""
    # Ensure all logging goes to stderr, never stdout.
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(asctime)s [DSA-MCP] %(levelname)s %(message)s",
        force=True,
    )

    in_stream = stdin or sys.stdin.buffer
    out_stream = stdout or sys.stdout.buffer
    mcp = server or DsaMcpServer()

    while True:
        payload, framing = _read_framed_message(in_stream)
        if payload is None:
            break
        try:
            message = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            err = DsaMcpServer._error_response(None, -32700, f"Parse error: {exc}")
            _write_framed_message(out_stream, err, framing)
            continue

        if isinstance(message, list):
            responses = []
            for item in message:
                resp = mcp.handle_message(item)
                if resp is not None:
                    responses.append(resp)
            if responses:
                encoded = json.dumps(responses, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                if framing == "content-length":
                    out_stream.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii") + encoded)
                else:
                    out_stream.write(encoded + b"\n")
                out_stream.flush()
            continue

        response = mcp.handle_message(message)
        if response is not None:
            _write_framed_message(out_stream, response, framing)

    return 0


def main() -> int:
    return run_stdio_server()


if __name__ == "__main__":
    raise SystemExit(main())
