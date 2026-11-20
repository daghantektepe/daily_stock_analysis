#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CLI-native launcher & MCP bridge for Daily Stock Analysis (DSA).

Allows speaking directly to DSA through local Claude Code CLI or Gemini CLI
wired to the live ``dsa`` MCP server, or running an interactive terminal chatbox.

Examples::

    python scripts/dsa_cli.py status
    python scripts/dsa_cli.py install-mcp
    python scripts/dsa_cli.py claude
    python scripts/dsa_cli.py gemini
    python scripts/dsa_cli.py ask "Şu an en güvenli stratejik trading önerini ver"
    python scripts/dsa_cli.py chat --engine claude
    python scripts/dsa_cli.py mcp-serve
    python scripts/dsa_cli.py serve --port 8000
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.agent_backend import AgentRunRequest  # noqa: E402
from src.agent.claude_cli_backend import ClaudeCliAgentBackend  # noqa: E402
from src.agent.cli_bridge_common import (  # noqa: E402
    build_cli_subprocess_env,
    build_strategic_trading_system_prompt,
    probe_cli_backend,
    resolve_cli_binary,
)
from src.agent.gemini_cli_backend import GeminiCliAgentBackend  # noqa: E402
from src.mcp.config_gen import (  # noqa: E402
    DSA_MCP_SERVER_NAME,
    install_project_mcp_configs,
    resolve_python_executable,
)
from src.mcp.tools import build_dsa_mcp_tools  # noqa: E402

DEFAULT_STRATEGIC_PROMPT = (
    "Para kazandırma ihtimali yüksek, şu an piyasa rejimine göre en güvenli stratejik "
    "trading önerini istiyorum. Canlı piyasa rejimini (SPY/VIX), Kripto 5-SMA trendini, "
    "sanal portföy durumunu ve canlı fırsat taramalarını DSA MCP araçlarıyla kontrol edip "
    "nakit oranı, pozisyon dağılımı ve stop-loss seviyeleriyle somut aksiyon planı çıkar."
)


def _configure_stdio_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _resolve_engine_id(engine: str) -> str:
    norm = (engine or "auto").strip().lower()
    if norm in {"claude", "claude_cli"}:
        return "claude_cli"
    if norm in {"gemini", "gemini_cli"}:
        return "gemini_cli"
    # Auto: pick Claude CLI first, then Gemini CLI
    if probe_cli_backend("claude_cli").get("available"):
        return "claude_cli"
    if probe_cli_backend("gemini_cli").get("available"):
        return "gemini_cli"
    return "claude_cli"


def _make_backend(engine_id: str):
    if engine_id == "gemini_cli":
        return GeminiCliAgentBackend(project_root=PROJECT_ROOT)
    return ClaudeCliAgentBackend(project_root=PROJECT_ROOT)


def _print_progress(event: Dict[str, Any]) -> None:
    ev_type = event.get("type")
    if ev_type == "thinking":
        msg = event.get("message") or "Düşünüyor..."
        print(f"  [·] {msg}", file=sys.stderr, flush=True)
    elif ev_type == "tool_start":
        label = event.get("display_name") or event.get("tool") or "mcp_tool"
        tool = event.get("tool") or ""
        print(f"  [MCP ->] {label} ({tool})", file=sys.stderr, flush=True)
    elif ev_type == "tool_done":
        label = event.get("display_name") or event.get("tool") or "mcp_tool"
        ok = "OK" if event.get("success", True) else "HATA"
        dur = event.get("duration")
        dur_str = f" · {dur}s" if dur is not None else ""
        print(f"  [MCP <-] {label} [{ok}{dur_str}]", file=sys.stderr, flush=True)
    elif ev_type == "generating":
        msg = event.get("message") or "Yanıt hazırlanıyor..."
        print(f"  [*] {msg}", file=sys.stderr, flush=True)


def _check_webui(port: int = 8000) -> bool:
    url = f"http://127.0.0.1:{port}/api/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:  # noqa: S310
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def cmd_status(args: argparse.Namespace) -> int:
    claude = probe_cli_backend("claude_cli", use_cache=False)
    gemini = probe_cli_backend("gemini_cli", use_cache=False)
    tools = build_dsa_mcp_tools()
    py_exe = resolve_python_executable(PROJECT_ROOT)
    mcp_json = PROJECT_ROOT / ".mcp.json"
    gemini_json = PROJECT_ROOT / ".gemini" / "settings.json"
    webui_up = _check_webui(args.port)

    payload = {
        "project_root": str(PROJECT_ROOT),
        "python_executable": py_exe,
        "mcp_server": {"name": DSA_MCP_SERVER_NAME, "tool_count": len(tools)},
        "claude_cli": claude,
        "gemini_cli": gemini,
        "configs": {
            "claude_mcp_json_exists": mcp_json.is_file(),
            "gemini_settings_json_exists": gemini_json.is_file(),
        },
        "webui_running": webui_up,
        "webui_url": f"http://127.0.0.1:{args.port}",
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("=== Daily Stock Analysis · CLI-Native & MCP Durumu ===")
    print(f"Proje Dizini      : {PROJECT_ROOT}")
    print(f"Python (MCP)      : {py_exe}")
    print(f"DSA MCP Sunucusu  : {DSA_MCP_SERVER_NAME} ({len(tools)} canlı quant/trading aracı)")
    print(
        f"Claude Code CLI   : {'HAZIR' if claude['available'] else 'YOK'}"
        + (f" ({claude['version']})" if claude.get("version") else "")
    )
    print(
        f"Gemini CLI        : {'HAZIR' if gemini['available'] else 'YOK'}"
        + (f" ({gemini['version']})" if gemini.get("version") else "")
    )
    print(f".mcp.json         : {'Kurulu' if mcp_json.is_file() else 'Henüz yok (dsa install-mcp çalıştırın)'}")
    print(f".gemini/settings  : {'Kurulu' if gemini_json.is_file() else 'Henüz yok (dsa install-mcp çalıştırın)'}")
    print(f"Web UI ({args.port})     : {'AKTİF -> http://127.0.0.1:' + str(args.port) if webui_up else 'Kapalı (dsa serve ile başlatılabilir)'}")
    return 0


def cmd_install_mcp(args: argparse.Namespace) -> int:
    result = install_project_mcp_configs(
        project_root=PROJECT_ROOT,
        python_executable=args.python or None,
    )
    print("DSA MCP köprü yapılandırmaları güncellendi:")
    print(f"  - Python      : {result['python_executable']}")
    print(f"  - Claude CLI  : {result['claude_mcp_config']}")
    print(f"  - Gemini CLI  : {result['gemini_mcp_config']}")
    print("\nArtık bu klasörde doğrudan `claude` veya `gemini` (ya da `dsa claude` / `dsa gemini`) çalıştırabilirsin.")
    return 0


def cmd_mcp_serve(_args: argparse.Namespace) -> int:
    from src.mcp.server import run_stdio_server

    return run_stdio_server()


def cmd_launch_native_claude(args: argparse.Namespace) -> int:
    claude_bin = resolve_cli_binary("claude", env_override="DSA_CLAUDE_CLI_PATH")
    if not claude_bin:
        print("Hata: `claude` CLI PATH üzerinde bulunamadı.", file=sys.stderr)
        return 1

    installed = install_project_mcp_configs(project_root=PROJECT_ROOT)
    system_prompt = build_strategic_trading_system_prompt(page_route="terminal:claude")
    cmd = [
        claude_bin,
        "--mcp-config",
        installed["claude_mcp_config"],
        "--append-system-prompt",
        system_prompt,
    ]
    if args.prompt:
        cmd.append(" ".join(args.prompt))

    print(f"[DSA] Native Claude Code CLI başlatılıyor (MCP: {DSA_MCP_SERVER_NAME})...", file=sys.stderr)
    return subprocess.call(cmd, cwd=str(PROJECT_ROOT), env=build_cli_subprocess_env())


def cmd_launch_native_gemini(args: argparse.Namespace) -> int:
    gemini_bin = resolve_cli_binary("gemini", env_override="DSA_GEMINI_CLI_PATH")
    if not gemini_bin:
        print("Hata: `gemini` CLI PATH üzerinde bulunamadı.", file=sys.stderr)
        return 1

    install_project_mcp_configs(project_root=PROJECT_ROOT)
    cmd = [
        gemini_bin,
        "--allowed-mcp-server-names",
        DSA_MCP_SERVER_NAME,
    ]
    if args.prompt:
        cmd.extend(["-i", " ".join(args.prompt)])

    print(f"[DSA] Native Gemini CLI başlatılıyor (MCP: {DSA_MCP_SERVER_NAME})...", file=sys.stderr)
    return subprocess.call(cmd, cwd=str(PROJECT_ROOT), env=build_cli_subprocess_env())


def cmd_ask(args: argparse.Namespace) -> int:
    prompt = " ".join(args.prompt).strip() if args.prompt else DEFAULT_STRATEGIC_PROMPT
    engine_id = _resolve_engine_id(args.engine)
    backend = _make_backend(engine_id)
    print(f"[DSA] Motor: {engine_id} · MCP: {DSA_MCP_SERVER_NAME}", file=sys.stderr, flush=True)

    result = backend.run(
        AgentRunRequest(
            system_prompt="",
            history_messages=[],
            user_message=prompt,
            session_id="cli-oneshot",
            stock_scope=None,
            max_steps=12,
            max_wall_clock_seconds=float(args.timeout),
            progress_callback=_print_progress if not args.quiet else None,
        )
    )
    if not result.success:
        print(f"Hata ({result.error_code}): {result.error_message}", file=sys.stderr)
        return 1
    print(result.final_answer)
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    engine_id = _resolve_engine_id(args.engine)
    history: List[Dict[str, str]] = []
    print("=== Daily Stock Analysis · CLI-Native Copilot ===")
    print(f"Aktif motor: {engine_id} (MCP sunucusu: {DSA_MCP_SERVER_NAME})")
    print("Komutlar: /strategy (en güvenli öneri), /switch claude|gemini, /new, /status, /exit\n")

    while True:
        try:
            user_text = input(f"dsa[{engine_id}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nÇıkılıyor.")
            return 0

        if not user_text:
            continue
        lower = user_text.lower()
        if lower in {"/exit", "/quit", "exit", "quit"}:
            return 0
        if lower == "/new":
            history.clear()
            print("Sohbet geçmişi temizlendi.\n")
            continue
        if lower == "/status":
            cmd_status(argparse.Namespace(json=False, port=8000))
            print()
            continue
        if lower.startswith("/switch"):
            parts = lower.split()
            if len(parts) >= 2 and parts[1] in {"claude", "claude_cli", "gemini", "gemini_cli"}:
                engine_id = _resolve_engine_id(parts[1])
                print(f"Aktif motor değiştirildi -> {engine_id}\n")
            else:
                print("Kullanım: /switch claude  veya  /switch gemini\n")
            continue
        if lower == "/strategy":
            user_text = DEFAULT_STRATEGIC_PROMPT
            print(f"> {user_text}\n")

        backend = _make_backend(engine_id)
        result = backend.run(
            AgentRunRequest(
                system_prompt="",
                history_messages=history,
                user_message=user_text,
                session_id="cli-repl",
                stock_scope=None,
                max_steps=12,
                max_wall_clock_seconds=float(args.timeout),
                progress_callback=_print_progress,
            )
        )
        print()
        if not result.success:
            print(f"[HATA · {result.error_code}] {result.error_message}\n", file=sys.stderr)
            continue

        print(result.final_answer)
        print()
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": result.final_answer})


def cmd_serve(args: argparse.Namespace) -> int:
    py_exe = resolve_python_executable(PROJECT_ROOT)
    cmd = [
        py_exe,
        "-m",
        "uvicorn",
        "server:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    print(f"[DSA] Web UI + API başlatılıyor: http://{args.host}:{args.port}", file=sys.stderr)
    return subprocess.call(cmd, cwd=str(PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dsa",
        description="Daily Stock Analysis CLI-Native Copilot & MCP Bridge",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="CLI, MCP ve Web UI durumunu kontrol et")
    p_status.add_argument("--json", action="store_true", help="JSON çıktı ver")
    p_status.add_argument("--port", type=int, default=8000, help="Web UI portu (varsayılan: 8000)")
    p_status.set_defaults(func=cmd_status)

    p_install = sub.add_parser("install-mcp", help=".mcp.json ve .gemini/settings.json dosyalarını kur/güncelle")
    p_install.add_argument("--python", default="", help="İsteğe bağlı Python yolu override")
    p_install.set_defaults(func=cmd_install_mcp)

    p_mcp = sub.add_parser("mcp-serve", help="Standart stdio MCP sunucusunu başlat")
    p_mcp.set_defaults(func=cmd_mcp_serve)

    p_claude = sub.add_parser("claude", help="DSA MCP bağlı native Claude Code CLI oturumu aç")
    p_claude.add_argument("prompt", nargs="*", help="İsteğe bağlı başlangıç sorusu")
    p_claude.set_defaults(func=cmd_launch_native_claude)

    p_gemini = sub.add_parser("gemini", help="DSA MCP bağlı native Gemini CLI oturumu aç")
    p_gemini.add_argument("prompt", nargs="*", help="İsteğe bağlı başlangıç sorusu")
    p_gemini.set_defaults(func=cmd_launch_native_gemini)

    p_ask = sub.add_parser("ask", help="Tek seferlik CLI+MCP stratejik analiz çalıştır")
    p_ask.add_argument("prompt", nargs="*", help="Soru (boş bırakılırsa en güvenli stratejik öneri sorulur)")
    p_ask.add_argument("--engine", default="auto", choices=["auto", "claude", "gemini"], help="CLI motoru")
    p_ask.add_argument("--timeout", type=int, default=300, help="Zaman aşımı (saniye)")
    p_ask.add_argument("--quiet", action="store_true", help="Canlı MCP araç ilerlemesini gizle")
    p_ask.set_defaults(func=cmd_ask)

    p_chat = sub.add_parser("chat", help="Terminal içinde etkileşimli DSA Copilot sohbeti başlat")
    p_chat.add_argument("--engine", default="auto", choices=["auto", "claude", "gemini"], help="CLI motoru")
    p_chat.add_argument("--timeout", type=int, default=300, help="Turn başına zaman aşımı (saniye)")
    p_chat.set_defaults(func=cmd_chat)

    p_serve = sub.add_parser("serve", help="DSA Web UI ve FastAPI sunucusunu başlat")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _configure_stdio_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
