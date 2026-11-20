# -*- coding: utf-8 -*-
"""Portable MCP configuration generators for Claude Code CLI and Gemini CLI."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

DSA_MCP_SERVER_NAME = "dsa"


def get_project_root() -> Path:
    """Return the active project/data root directory without hardcoding machine paths."""
    if getattr(sys, "frozen", False):
        override_root = (os.getenv("DSA_DATA_ROOT") or "").strip()
        if override_root:
            return Path(override_root).resolve()
        return Path.cwd().resolve()
    return Path(__file__).resolve().parents[2]


def _venv_python_is_usable(python_path: Path) -> bool:
    """Check whether a virtual-environment Python launcher points to an existing base runtime."""
    if not python_path.is_file():
        return False
    pyvenv_cfg = python_path.parent.parent / "pyvenv.cfg"
    if pyvenv_cfg.is_file():
        try:
            for line in pyvenv_cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip().lower() == "home":
                    base_home = Path(value.strip().strip('"'))
                    if not base_home.exists():
                        return False
                    break
        except OSError:
            return False
    return True


def resolve_python_executable(project_root: Optional[Path] = None) -> str:
    """Resolve the best runnable Python interpreter for spawning ``python -m src.mcp.server``.

    Prefers an explicit ``DSA_MCP_PYTHON`` override, then a healthy repo-local
    ``.venv`` interpreter, and finally ``sys.executable``.
    """
    override = (os.getenv("DSA_MCP_PYTHON") or "").strip()
    if override and Path(override).is_file():
        return str(Path(override).resolve())

    root = Path(project_root or get_project_root()).resolve()
    home = Path.home()
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        home / ".dsa-venv" / "Scripts" / "python.exe",
        home / ".dsa-venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if _venv_python_is_usable(candidate):
            return str(candidate)

    return sys.executable


def build_dsa_mcp_server_entry(
    *,
    project_root: Optional[Path] = None,
    python_executable: Optional[str] = None,
    extra_env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a standard MCP stdio server entry for ``src.mcp.server`` (or frozen ``--mcp-serve``)."""
    root = Path(project_root or get_project_root()).resolve()

    env: Dict[str, str] = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "DSA_MCP_MODE": "1",
        "DSA_DATA_ROOT": str(root),
    }
    if extra_env:
        for key, value in extra_env.items():
            if value is not None:
                env[str(key)] = str(value)

    # Inside a PyInstaller-frozen desktop .exe, invoke the .exe itself with --mcp-serve
    # unless an explicit Python interpreter override is supplied.
    explicit_override = python_executable or (os.getenv("DSA_MCP_PYTHON") or "").strip()
    if getattr(sys, "frozen", False) and not explicit_override:
        return {
            "command": sys.executable,
            "args": ["--mcp-serve"],
            "cwd": str(root),
            "env": env,
        }

    python_exe = python_executable or resolve_python_executable(root)
    env["PYTHONPATH"] = str(root)
    return {
        "command": python_exe,
        "args": ["-m", "src.mcp.server"],
        "cwd": str(root),
        "env": env,
    }


def build_claude_mcp_config(
    *,
    project_root: Optional[Path] = None,
    python_executable: Optional[str] = None,
    server_name: str = DSA_MCP_SERVER_NAME,
    extra_env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a Claude Code ``--mcp-config`` / ``.mcp.json`` payload."""
    return {
        "mcpServers": {
            server_name: build_dsa_mcp_server_entry(
                project_root=project_root,
                python_executable=python_executable,
                extra_env=extra_env,
            )
        }
    }


def write_temp_claude_mcp_config(
    *,
    project_root: Optional[Path] = None,
    python_executable: Optional[str] = None,
    server_name: str = DSA_MCP_SERVER_NAME,
    extra_env: Optional[Dict[str, str]] = None,
) -> Path:
    """Write a temporary Claude ``--mcp-config`` JSON file and return its path."""
    payload = build_claude_mcp_config(
        project_root=project_root,
        python_executable=python_executable,
        server_name=server_name,
        extra_env=extra_env,
    )
    fd, raw_path = tempfile.mkstemp(prefix="dsa-claude-mcp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return Path(raw_path)


def write_temp_gemini_workspace_config(
    *,
    project_root: Optional[Path] = None,
    python_executable: Optional[str] = None,
    server_name: str = DSA_MCP_SERVER_NAME,
    extra_env: Optional[Dict[str, str]] = None,
) -> Path:
    """Create an isolated temp directory containing ``.gemini/settings.json`` for Gemini CLI."""
    temp_dir = Path(tempfile.mkdtemp(prefix="dsa-gemini-mcp-"))
    gemini_dir = temp_dir / ".gemini"
    gemini_dir.mkdir(parents=True, exist_ok=True)
    entry = build_dsa_mcp_server_entry(
        project_root=project_root,
        python_executable=python_executable,
        extra_env=extra_env,
    )
    # Gemini CLI trusts local MCP servers when trust=True is explicitly set.
    entry["trust"] = True
    settings_payload = {
        "mcpServers": {
            server_name: entry,
        }
    }
    (gemini_dir / "settings.json").write_text(
        json.dumps(settings_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return temp_dir


def _merge_json_file(target: Path, update_fn) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if target.is_file():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, ValueError):
            existing = {}
    merged = update_fn(existing)
    target.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def install_project_mcp_configs(
    *,
    project_root: Optional[Path] = None,
    python_executable: Optional[str] = None,
    server_name: str = DSA_MCP_SERVER_NAME,
) -> Dict[str, str]:
    """Write or update project-level ``.mcp.json`` (Claude) and ``.gemini/settings.json`` (Gemini)."""
    root = Path(project_root or get_project_root()).resolve()
    entry = build_dsa_mcp_server_entry(
        project_root=root,
        python_executable=python_executable,
    )

    claude_path = _merge_json_file(
        root / ".mcp.json",
        lambda cur: {
            **cur,
            "mcpServers": {
                **(cur.get("mcpServers") if isinstance(cur.get("mcpServers"), dict) else {}),
                server_name: entry,
            },
        },
    )

    gemini_entry = {**entry, "trust": True}
    gemini_path = _merge_json_file(
        root / ".gemini" / "settings.json",
        lambda cur: {
            **cur,
            "mcpServers": {
                **(cur.get("mcpServers") if isinstance(cur.get("mcpServers"), dict) else {}),
                server_name: gemini_entry,
            },
        },
    )

    return {
        "project_root": str(root),
        "python_executable": entry["command"],
        "claude_mcp_config": str(claude_path),
        "gemini_mcp_config": str(gemini_path),
    }
