#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent Native Windows Desktop Application (.exe) for Daily Stock Analysis.

Runs an embedded FastAPI backend serving the compiled React UI inside a native
Microsoft Edge WebView2 desktop window (via pywebview) — zero external browser
window, zero terminal popup, and zero Electron bloat.

Also supports:
  - ``--mcp-serve``  : run the built-in stdio JSON-RPC 2.0 DSA MCP server
                       (enables Claude CLI & Gemini CLI Copilot even when frozen!)
  - ``--smoke-test`` : verify embedded FastAPI + static UI + quant + MCP headless
  - ``--route /...`` : initial route (default ``/discover``)
  - ``--port N``     : preferred local loopback port (auto-picks free port if busy)
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional

_SPLASH_HTML = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8" />
<title>Daily Stock Analysis</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    height: 100vh; display: flex; align-items: center; justify-content: center;
    background: radial-gradient(circle at top, #0f1f38 0%, #090d16 70%);
    color: #e2e8f0; font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
    user-select: none; overflow: hidden;
  }
  .card {
    text-align: center; padding: 40px 48px; border-radius: 24px;
    border: 1px solid rgba(34, 211, 238, 0.22);
    background: rgba(15, 23, 42, 0.72); box-shadow: 0 24px 64px rgba(0, 0, 0, 0.45);
    max-width: 440px;
  }
  .badge {
    width: 64px; height: 64px; margin: 0 auto 20px; border-radius: 18px;
    background: linear-gradient(135deg, #0ea5e9, #34d399);
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 22px; color: #06131f;
    box-shadow: 0 12px 32px rgba(14, 165, 233, 0.35);
  }
  h1 { font-size: 20px; font-weight: 600; margin-bottom: 8px; letter-spacing: -0.01em; }
  p { font-size: 13px; color: #94a3b8; line-height: 1.5; }
  .bar {
    margin: 22px auto 0; height: 4px; width: 220px; border-radius: 999px;
    background: rgba(148, 163, 184, 0.18); overflow: hidden;
  }
  .bar::after {
    content: ""; display: block; height: 100%; width: 42%; border-radius: 999px;
    background: linear-gradient(90deg, #0ea5e9, #34d399);
    animation: slide 1.1s ease-in-out infinite;
  }
  @keyframes slide {
    0% { transform: translateX(-110%); }
    100% { transform: translateX(260%); }
  }
</style>
</head>
<body>
  <div class="card">
    <div class="badge">DSA</div>
    <h1>Daily Stock Analysis</h1>
    <p>Quant Kokpit, 25 Strateji Turnuvası ve AI MCP Köprüsü başlatılıyor...</p>
    <div class="bar"></div>
  </div>
</body>
</html>
"""


def _bundle_root() -> Path:
    """Return directory containing bundled read-only assets (``static/``, ``strategies/``)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parent


def _resolve_runtime_root() -> Path:
    """Resolve persistent data/config root (shares repo data when launched from dist/, else portable)."""
    override = (os.getenv("DSA_DATA_ROOT") or "").strip()
    if override:
        return Path(override).resolve()

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        # Check whether the .exe lives inside <repo>/dist/DailyStockAnalysis/
        for candidate in (exe_dir.parent.parent, exe_dir.parent):
            if (candidate / ".env").is_file() or (candidate / "data" / "strategy_paper").is_dir():
                return candidate
        # Otherwise run 100% self-contained beside the .exe
        return exe_dir

    return Path(__file__).resolve().parent


def _bootstrap_runtime_dir(runtime_root: Path, bundle_root: Path) -> None:
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "data").mkdir(parents=True, exist_ok=True)
    (runtime_root / "logs").mkdir(parents=True, exist_ok=True)

    env_file = runtime_root / ".env"
    if not env_file.is_file():
        for candidate in (bundle_root / ".env.example", runtime_root / ".env.example"):
            if candidate.is_file():
                try:
                    shutil.copy2(candidate, env_file)
                except OSError:
                    pass
                break

    os.chdir(runtime_root)
    os.environ["DSA_DATA_ROOT"] = str(runtime_root)
    os.environ.setdefault("ENV_FILE", str(env_file))
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    # Avoid runtime scheduler double-starting heavy loops inside quick desktop GUI opens
    os.environ.setdefault("DSA_RUNTIME_SCHEDULER_SUPPRESS_START", "0")


def _configure_desktop_logging(runtime_root: Path) -> Path:
    log_path = runtime_root / "logs" / "desktop_exe.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )
    return log_path


def _find_available_port(preferred: int = 8000, host: str = "127.0.0.1") -> int:
    for port in [preferred, *range(8001, 8099), 0]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return int(sock.getsockname()[1])
            except OSError:
                continue
    return 8000


def _wait_for_health(url: str, timeout_s: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def _start_embedded_server(static_dir: Path, host: str, port: int):
    import uvicorn
    from api.app import create_app

    app = create_app(static_dir=static_dir)
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        log_config=None,
    )
    server = uvicorn.Server(config)
    # Disable uvicorn's signal handlers because it runs on a background thread
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    thread = threading.Thread(target=server.run, name="dsa-embedded-uvicorn", daemon=True)
    thread.start()
    return server, thread


def _run_smoke_test(static_dir: Path, runtime_root: Path) -> int:
    import json
    from src.mcp.server import DsaMcpServer

    port = _find_available_port(preferred=18765)
    server, thread = _start_embedded_server(static_dir, "127.0.0.1", port)
    base = f"http://127.0.0.1:{port}"
    try:
        if not _wait_for_health(f"{base}/api/v1/health", timeout_s=30.0):
            print("SMOKE_ERROR: embedded FastAPI health check timed out", file=sys.stderr)
            return 1
        for path in (
            "/api/v1/health",
            "/api/v1/agent/backends",
            "/api/v1/alpha/tournament?auto_run=false",
            "/api/v1/alpha/quant-paper?auto_step=false",
            "/discover",
        ):
            with urllib.request.urlopen(f"{base}{path}", timeout=15.0) as resp:
                if resp.status != 200:
                    print(f"SMOKE_ERROR: {path} returned {resp.status}", file=sys.stderr)
                    return 1
        mcp = DsaMcpServer()
        if len(mcp.tool_names) < 16:
            print(f"SMOKE_ERROR: expected >=16 MCP tools, got {len(mcp.tool_names)}", file=sys.stderr)
            return 1
        payload = {
            "ok": True,
            "runtime_root": str(runtime_root),
            "static_dir": str(static_dir),
            "port": port,
            "mcp_tools": len(mcp.tool_names),
        }
        print("DESKTOP_EXE_SMOKE_OK", json.dumps(payload, ensure_ascii=False))
        return 0
    finally:
        server.should_exit = True
        thread.join(timeout=4.0)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Daily Stock Analysis Native Desktop App")
    parser.add_argument("--mcp-serve", action="store_true", help="Run built-in DSA MCP stdio server")
    parser.add_argument("--smoke-test", action="store_true", help="Run headless packaged smoke verification")
    parser.add_argument("--port", type=int, default=0, help="Preferred local port (0 = auto-pick)")
    parser.add_argument("--route", default="/discover", help="Initial UI route (default /discover)")
    parser.add_argument("--debug", action="store_true", help="Enable WebView DevTools")
    args = parser.parse_args(argv)

    bundle_root = _bundle_root()
    runtime_root = _resolve_runtime_root()
    _bootstrap_runtime_dir(runtime_root, bundle_root)

    # Headless MCP stdio mode (used when Claude CLI / Gemini CLI connects to the frozen .exe)
    if args.mcp_serve:
        from src.mcp.server import run_stdio_server

        return run_stdio_server()

    log_path = _configure_desktop_logging(runtime_root)
    logger = logging.getLogger("dsa.desktop_exe")
    logger.info("Starting DSA Desktop App (frozen=%s, root=%s, bundle=%s)", getattr(sys, "frozen", False), runtime_root, bundle_root)

    static_dir = bundle_root / "static"
    if not (static_dir / "index.html").is_file():
        fallback_static = runtime_root / "static"
        if (fallback_static / "index.html").is_file():
            static_dir = fallback_static

    if args.smoke_test:
        return _run_smoke_test(static_dir, runtime_root)

    host = "127.0.0.1"
    preferred = args.port if args.port > 0 else 8000
    port = _find_available_port(preferred=preferred, host=host)
    route = args.route if args.route.startswith("/") else f"/{args.route}"
    base_url = f"http://{host}:{port}"
    target_url = f"{base_url}{route}"

    server, server_thread = _start_embedded_server(static_dir, host, port)

    import webview

    window = webview.create_window(
        title="Daily Stock Analysis · Quant Cockpit",
        html=_SPLASH_HTML,
        width=1440,
        height=920,
        min_size=(1024, 680),
        background_color="#090d16",
        text_select=True,
    )

    def _navigate_when_ready() -> None:
        if _wait_for_health(f"{base_url}/api/v1/health", timeout_s=45.0):
            logger.info("Embedded FastAPI ready on %s -> loading %s", base_url, target_url)
            window.load_url(target_url)
        else:
            logger.error("Embedded FastAPI failed to become healthy within 45s. See %s", log_path)
            window.load_html(
                f"<body style='background:#090d16;color:#f87171;font-family:Segoe UI;padding:40px'>"
                f"<h2>Başlatma Hatası</h2><p>Yerel API sunucusu zaman aşımına uğradı. Günlük: {log_path}</p></body>"
            )

    def _on_closed() -> None:
        logger.info("Desktop window closed; shutting down embedded server...")
        server.should_exit = True

    window.events.closed += _on_closed

    storage_dir = runtime_root / "data" / "desktop_webview_cache"
    storage_dir.mkdir(parents=True, exist_ok=True)
    try:
        webview.start(
            func=_navigate_when_ready,
            gui="edgechromium" if sys.platform == "win32" else None,
            debug=bool(args.debug),
            private_mode=False,
            storage_path=str(storage_dir),
        )
    finally:
        server.should_exit = True
        server_thread.join(timeout=3.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
