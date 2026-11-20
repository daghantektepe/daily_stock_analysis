# -*- coding: utf-8 -*-
"""Tests for the native Windows Desktop App (.exe) entrypoint, icon generator, and frozen MCP."""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.windows.generate_icon import generate_ico
from src.mcp.config_gen import build_dsa_mcp_server_entry


def test_generate_ico_writes_valid_multi_res_ico_header(tmp_path: Path) -> None:
    ico = generate_ico(tmp_path / "dsa.ico")
    raw = ico.read_bytes()
    # Standard ICO header: reserved=0x0000, type=0x0001 (icon), count=4 resolutions
    assert raw[:6] == b"\x00\x00\x01\x00\x04\x00"
    assert len(raw) > 2000


def test_frozen_exe_mcp_config_uses_self_mcp_serve_flag(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "DailyStockAnalysis.exe"))
    monkeypatch.delenv("DSA_MCP_PYTHON", raising=False)

    entry = build_dsa_mcp_server_entry(project_root=tmp_path)
    assert entry["command"].endswith("DailyStockAnalysis.exe")
    assert entry["args"] == ["--mcp-serve"]
    assert entry["env"]["DSA_DATA_ROOT"] == str(tmp_path.resolve())


def test_desktop_app_mcp_serve_invokes_run_stdio_server(monkeypatch, tmp_path: Path) -> None:
    import desktop_app

    called = {"count": 0}

    def _fake_stdio() -> int:
        called["count"] += 1
        return 0

    monkeypatch.setenv("DSA_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr("src.mcp.server.run_stdio_server", _fake_stdio)
    rc = desktop_app.main(["--mcp-serve"])
    assert rc == 0
    assert called["count"] == 1
