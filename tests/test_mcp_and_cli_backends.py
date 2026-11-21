# -*- coding: utf-8 -*-
"""Unit & protocol tests for DSA MCP Server, Claude/Gemini CLI backends, and CLI launcher."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.agent.agent_backend import (
    AGENT_BACKEND_IDS,
    AgentRunRequest,
    resolve_agent_backend_id,
)
from src.agent.claude_cli_backend import ClaudeCliAgentBackend
from src.agent.cli_bridge_common import (
    build_strategic_trading_system_prompt,
    format_conversation_prompt,
    normalize_mcp_tool_name,
    resolve_cli_binary,
)
from src.agent.gemini_cli_backend import GeminiCliAgentBackend
from src.mcp.config_gen import (
    build_claude_mcp_config,
    build_dsa_mcp_server_entry,
    install_project_mcp_configs,
)
from src.mcp.server import DsaMcpServer, run_stdio_server
from src.mcp.tools import McpToolSpec, build_dsa_mcp_tools, safe_json_dumps


def _make_request(**overrides) -> AgentRunRequest:
    defaults = {
        "system_prompt": "DSA base system prompt",
        "history_messages": [{"role": "user", "content": "Önceki soru"}],
        "user_message": "Şu an en güvenli stratejik trading önerini ver",
        "session_id": "test-session-1",
        "stock_scope": None,
        "max_steps": 8,
        "max_wall_clock_seconds": 30.0,
        "progress_callback": None,
        "cancel_event": None,
    }
    defaults.update(overrides)
    return AgentRunRequest(**defaults)


class _FakePopen:
    """Minimal Popen double that emits deterministic stream-json lines."""

    def __init__(self, stdout_lines: list[str], *, returncode: int = 0, stderr_text: str = "") -> None:
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("\n".join(stdout_lines) + ("\n" if stdout_lines else ""))
        self.stderr = io.StringIO(stderr_text)
        self.returncode = returncode
        self.pid = 424242
        self._polled = False

    def poll(self):
        return self.returncode if self._polled else None

    def wait(self, timeout=None):
        self._polled = True
        return self.returncode

    def terminate(self):
        self._polled = True

    def kill(self):
        self._polled = True


# ---------------------------------------------------------------------------
# MCP Protocol Tests
# ---------------------------------------------------------------------------


def test_mcp_server_lists_expected_quant_tools() -> None:
    server = DsaMcpServer()
    names = set(server.tool_names)
    expected = {
        "dsa_get_system_overview",
        "dsa_get_strategic_trading_brief",
        "dsa_get_market_regime",
        "dsa_get_crypto_trend_signal",
        "dsa_screen_us_alpha",
        "dsa_screen_bist_stocks",
        "dsa_scan_sec_form4_live",
        "dsa_scan_pead_candidates",
        "dsa_scan_kap_contracts",
        "dsa_get_paper_portfolio",
        "dsa_place_paper_order",
        "dsa_analyze_stock",
        "dsa_get_decision_signals",
        "dsa_get_strategy_tournament",
    }
    assert expected.issubset(names)


def test_mcp_stdio_roundtrip_newline_and_content_length_framing() -> None:
    echo_tool = McpToolSpec(
        name="dsa_echo_test",
        description="Echo test tool",
        input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
        handler=lambda args: {"ok": True, "echo": args.get("x")},
    )
    server = DsaMcpServer(tools=[echo_tool])

    # 1. Newline-delimited JSON-RPC (Claude Code / Gemini CLI default)
    line_requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "dsa_echo_test", "arguments": {"x": "SPY"}}},
    ]
    in_buf = io.BytesIO(("\n".join(json.dumps(m) for m in line_requests) + "\n").encode("utf-8"))
    out_buf = io.BytesIO()
    assert run_stdio_server(server=server, stdin=in_buf, stdout=out_buf) == 0

    responses = [json.loads(line) for line in out_buf.getvalue().decode("utf-8").splitlines() if line.strip()]
    assert len(responses) == 3
    assert responses[0]["result"]["protocolVersion"] == "2025-03-26"
    assert responses[1]["result"]["tools"][0]["name"] == "dsa_echo_test"
    call_body = json.loads(responses[2]["result"]["content"][0]["text"])
    assert call_body == {"ok": True, "echo": "SPY"}
    assert responses[2]["result"]["isError"] is False

    # 2. Content-Length LSP-style framing
    ping_bytes = json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}).encode("utf-8")
    cl_in = io.BytesIO(f"Content-Length: {len(ping_bytes)}\r\n\r\n".encode("ascii") + ping_bytes)
    cl_out = io.BytesIO()
    assert run_stdio_server(server=server, stdin=cl_in, stdout=cl_out) == 0
    raw_cl = cl_out.getvalue().decode("utf-8")
    assert raw_cl.startswith("Content-Length:")
    assert json.loads(raw_cl.split("\r\n\r\n", 1)[1]) == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_mcp_server_diverts_tool_stdout_prints_away_from_jsonrpc() -> None:
    def noisy_handler(_args):
        print("STRAY PRINT FROM YFINANCE")
        return {"ok": True, "clean": 1}

    server = DsaMcpServer(
        tools=[McpToolSpec(name="noisy", description="noisy", input_schema={"type": "object"}, handler=noisy_handler)]
    )
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "noisy", "arguments": {}}})
    out_buf = io.BytesIO()
    run_stdio_server(server=server, stdin=io.BytesIO((req + "\n").encode("utf-8")), stdout=out_buf)
    lines = out_buf.getvalue().decode("utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert json.loads(parsed["result"]["content"][0]["text"]) == {"ok": True, "clean": 1}


def test_mcp_config_generation_and_install(tmp_path: Path) -> None:
    entry = build_dsa_mcp_server_entry(project_root=tmp_path, python_executable="/usr/bin/python3")
    assert entry["command"] == "/usr/bin/python3"
    assert entry["args"] == ["-m", "src.mcp.server"]
    assert entry["env"]["DSA_MCP_MODE"] == "1"

    cfg = build_claude_mcp_config(project_root=tmp_path, python_executable="/usr/bin/python3")
    assert "dsa" in cfg["mcpServers"]

    # Pre-existing unrelated MCP server must be preserved during install
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"other": {"command": "echo"}}}),
        encoding="utf-8",
    )
    installed = install_project_mcp_configs(project_root=tmp_path, python_executable="/usr/bin/python3")
    claude_json = json.loads(Path(installed["claude_mcp_config"]).read_text(encoding="utf-8"))
    gemini_json = json.loads(Path(installed["gemini_mcp_config"]).read_text(encoding="utf-8"))
    assert "other" in claude_json["mcpServers"]
    assert "dsa" in claude_json["mcpServers"]
    assert gemini_json["mcpServers"]["dsa"]["trust"] is True


def test_safe_json_dumps_truncates_large_payload() -> None:
    huge = {"items": ["x" * 1000] * 10}
    encoded = safe_json_dumps(huge, max_bytes=1024)
    parsed = json.loads(encoded)
    assert parsed["truncated"] is True


# ---------------------------------------------------------------------------
# Backend Selection & Helpers Tests
# ---------------------------------------------------------------------------


def test_agent_backend_ids_support_claude_and_gemini_cli_without_breaking_auto() -> None:
    assert {"claude_cli", "gemini_cli"}.issubset(AGENT_BACKEND_IDS)
    assert resolve_agent_backend_id(SimpleNamespace(agent_backend="auto")) == "litellm"
    assert resolve_agent_backend_id(SimpleNamespace(agent_backend="claude_cli")) == "claude_cli"
    assert resolve_agent_backend_id(SimpleNamespace(agent_backend="gemini_cli")) == "gemini_cli"


def test_cli_bridge_helpers() -> None:
    assert normalize_mcp_tool_name("mcp__dsa__dsa_get_market_regime") == "dsa_get_market_regime"
    assert normalize_mcp_tool_name("dsa__dsa_screen_bist_stocks") == "dsa_screen_bist_stocks"
    prompt = format_conversation_prompt(
        [{"role": "user", "content": "Merhaba"}, {"role": "assistant", "content": "Selam"}],
        "Bugün ne alalım?",
    )
    assert "Previous Conversation History" in prompt
    assert "Bugün ne alalım?" in prompt

    sys_prompt = build_strategic_trading_system_prompt("Base", page_route="/discover")
    assert "dsa_get_strategic_trading_brief" in sys_prompt
    assert "/discover" in sys_prompt


# ---------------------------------------------------------------------------
# Claude CLI & Gemini CLI Stream-JSON Parsing Tests
# ---------------------------------------------------------------------------


def test_claude_cli_backend_parses_mcp_tool_events_and_result(tmp_path: Path) -> None:
    stream_lines = [
        json.dumps({"type": "system", "subtype": "init", "model": "claude-sonnet-4-6", "mcp_servers": [{"name": "dsa", "status": "connected"}]}),
        json.dumps({
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-6",
                "content": [
                    {"type": "tool_use", "id": "tu_1", "name": "mcp__dsa__dsa_get_strategic_trading_brief", "input": {"include_crypto_trend": True}},
                ],
            },
        }),
        json.dumps({
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_1", "content": "{\"ok\":true}", "is_error": False},
                ],
            },
        }),
        json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "SPY risk_off, %100 nakit önerilir."}],
            },
        }),
        json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "SPY risk_off, %100 nakit önerilir.",
            "usage": {"input_tokens": 120, "output_tokens": 45},
        }),
    ]
    fake_proc = _FakePopen(stream_lines, returncode=0)
    captured_cmd = []
    progress_events = []

    def _fake_popen(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return fake_proc

    backend = ClaudeCliAgentBackend(project_root=tmp_path)
    with patch("src.agent.claude_cli_backend.resolve_cli_binary", return_value="claude.cmd"), \
         patch("src.agent.claude_cli_backend.subprocess.Popen", side_effect=_fake_popen):
        res = backend.run(_make_request(progress_callback=progress_events.append))

    assert res.success is True
    assert res.backend == "claude_cli"
    assert res.model == "claude-sonnet-4-6"
    assert "risk_off" in res.final_answer
    assert res.usage == {"prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165}
    assert len(res.tool_calls_log) == 1
    assert res.tool_calls_log[0]["tool"] == "dsa_get_strategic_trading_brief"
    assert res.tool_calls_log[0]["success"] is True
    assert "--mcp-config" in captured_cmd
    assert "--strict-mcp-config" in captured_cmd
    assert "--allowedTools" in captured_cmd
    assert any(ev.get("type") == "tool_start" and ev.get("tool") == "dsa_get_strategic_trading_brief" for ev in progress_events)
    assert any(ev.get("type") == "tool_done" and ev.get("tool") == "dsa_get_strategic_trading_brief" for ev in progress_events)


def test_gemini_cli_backend_parses_mcp_tool_events_and_result(tmp_path: Path) -> None:
    stream_lines = [
        json.dumps({"type": "init", "model": "gemini-2.5-pro"}),
        json.dumps({"type": "tool_use", "tool_id": "g_1", "tool_name": "mcp__dsa__dsa_get_crypto_trend_signal", "parameters": {"step_paper": False}}),
        json.dumps({"type": "tool_result", "tool_id": "g_1", "status": "success"}),
        json.dumps({"type": "message", "role": "assistant", "content": "BTC ve ETH 0/5 SMA altında, %100 nakit."}),
        json.dumps({"type": "result", "status": "success", "stats": {"input_tokens": 90, "output_tokens": 30, "total_tokens": 120}}),
    ]
    fake_proc = _FakePopen(stream_lines, returncode=0)
    captured_cmd = []
    progress_events = []

    def _fake_popen(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return fake_proc

    backend = GeminiCliAgentBackend(project_root=tmp_path)
    with patch("src.agent.gemini_cli_backend.resolve_cli_binary", return_value="gemini.cmd"), \
         patch("src.agent.gemini_cli_backend.subprocess.Popen", side_effect=_fake_popen):
        res = backend.run(_make_request(progress_callback=progress_events.append))

    assert res.success is True
    assert res.backend == "gemini_cli"
    assert res.model == "gemini-2.5-pro"
    assert "%100 nakit" in res.final_answer
    assert res.usage == {"prompt_tokens": 90, "completion_tokens": 30, "total_tokens": 120}
    assert len(res.tool_calls_log) == 1
    assert res.tool_calls_log[0]["tool"] == "dsa_get_crypto_trend_signal"
    assert "--allowed-mcp-server-names" in captured_cmd
    assert any(ev.get("type") == "tool_start" and ev.get("tool") == "dsa_get_crypto_trend_signal" for ev in progress_events)
    assert any(ev.get("type") == "tool_done" and ev.get("tool") == "dsa_get_crypto_trend_signal" for ev in progress_events)


def test_cli_backends_respect_pre_cancelled_event(tmp_path: Path) -> None:
    cancel = threading.Event()
    cancel.set()
    for backend in (ClaudeCliAgentBackend(project_root=tmp_path), GeminiCliAgentBackend(project_root=tmp_path)):
        res = backend.run(_make_request(cancel_event=cancel))
        assert res.success is False
        assert res.error_code == "cancelled"


def test_mcp_server_subprocess_smoke() -> None:
    """Spawn the real ``python -m src.mcp.server`` process and verify clean JSON-RPC handshake."""
    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.mcp.server"],
        cwd=str(repo_root),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        ]
    ) + "\n"
    out, err = proc.communicate(payload, timeout=10)
    assert proc.returncode == 0
    assert "RuntimeWarning" not in err
    lines = [json.loads(x) for x in out.splitlines() if x.strip()]
    assert len(lines) == 2
    assert lines[0]["result"]["serverInfo"]["name"] == "dsa-quant-mcp"
    assert len(lines[1]["result"]["tools"]) == len(build_dsa_mcp_tools())


def test_strategy_tournament_tool_gracefully_handles_missing_v03_module(monkeypatch) -> None:
    # No cached results here must not trigger a live tournament (network + docs report rewrite).
    monkeypatch.setattr("src.quant.tournament.load_latest_tournament_results", lambda **_kwargs: None)
    server = DsaMcpServer()
    res = server.call_tool("dsa_get_strategy_tournament", {})
    assert res["isError"] is False
    body = json.loads(res["content"][0]["text"])
    assert body["ok"] is True
    assert "module_present" in body["data"]
