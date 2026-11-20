# -*- coding: utf-8 -*-
"""Shared utilities for CLI-native MCP Agent backends (Claude Code CLI & Gemini CLI)."""

from __future__ import annotations

import logging
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

CLI_NATIVE_BACKEND_IDS = frozenset({"claude_cli", "gemini_cli"})

_PROBE_TTL_SECONDS = 30.0
_PROBE_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_PROBE_CACHE_LOCK = threading.Lock()

# DSA secrets that should never leak into spawned third-party CLI processes.
_STRIPPED_DSA_SECRET_PREFIXES = (
    "ALPACA_",
    "TUSHARE_",
    "FEISHU_",
    "WECHAT_",
    "WECOM_",
    "TELEGRAM_",
    "DINGTALK_",
    "PUSHOVER_",
    "PUSHPLUS_",
    "SERVERCHAN",
    "ADMIN_AUTH_",
    "SERPAPI_",
    "TAVILY_",
    "BOCHA_",
    "BRAVE_",
    "ANSPIRE_",
    "LONGBRIDGE_",
)
_STRIPPED_DSA_SECRET_EXACT = frozenset(
    {
        "AIHUBMIX_KEY",
        "WEBHOOK_URL",
        "CUSTOM_WEBHOOK_URLS",
    }
)

# Friendly bilingual display labels for MCP tool progress timelines.
MCP_TOOL_DISPLAY_NAMES: Dict[str, str] = {
    "dsa_get_system_overview": "Sistem ve Portföy Özeti Alınıyor",
    "dsa_get_strategic_trading_brief": "Stratejik Trading Özeti & Risk Rejimi Hazırlanıyor",
    "dsa_get_market_regime": "SPY / VIX Piyasa Rejimi Kontrol Ediliyor",
    "dsa_get_crypto_trend_signal": "Kripto 5-SMA Trend Sinyali Hesaplanıyor",
    "dsa_screen_us_alpha": "ABD Yüksek Alfa Çok Faktörlü Tarama Çalıştırılıyor",
    "dsa_screen_bist_stocks": "BIST Teknik & KAP Taraması Çalıştırılıyor",
    "dsa_scan_sec_form4_live": "SEC Form 4 Canlı Yönetici Alımları Taranıyor",
    "dsa_scan_pead_candidates": "ABD PEAD Bilanço Sürprizleri Taranıyor",
    "dsa_scan_kap_contracts": "BIST KAP İhale/Sözleşme Bildirimleri Taranıyor",
    "dsa_get_paper_portfolio": "Sanal Portföy ve Açık Pozisyonlar Okunuyor",
    "dsa_place_paper_order": "Sanal İşlem Defterine Emir Kaydediliyor",
    "dsa_analyze_stock": "Hisse Teknik & Risk Kapısı Analizi Yapılıyor",
    "dsa_get_decision_signals": "Son AI Karar Sinyalleri Okunuyor",
    "dsa_get_strategy_tournament": "Strateji Turnuva Liderlik Tablosu Okunuyor",
    "dsa_get_paa_allocation": "PAA Çöküş Kalkanı Canlı Dağılımı Hesaplanıyor",
}

_CLI_STRATEGIC_PROMPT_ADDENDUM = """
## DSA Live MCP Bridge Instructions

You are directly connected to the user's **Daily Stock Analysis (DSA)** quantitative trading platform via the `dsa` MCP server.
Always prefer calling live `dsa_*` MCP tools over guessing or giving generic textbook advice.

### Recommended Tool Selection
- **Safest high-probability strategic trading recommendation / "bugün ne yapmalıyım" / "para kazandırma ihtimali yüksek en güvenli stratejik trading önerisi"**:
  1. Call `dsa_get_strategic_trading_brief` first (set `include_crypto_trend=true`, and when the user asks for fresh actionable picks also enable `include_us_screen=true` / `include_form4=true` / `include_pead=true` or follow up with dedicated scanners).
  2. Check `dsa_get_strategy_tournament` if available to reference empirical out-of-sample winners.
  3. Synthesize a **risk-first, disciplined strategic trading plan** covering:
     - **Piyasa Rejimi & Risk Kalkanı** (SPY SMA50/SMA200, VIX, önerilen nakit / pozisyon ölçeği)
     - **Mevcut Sanal Portföy & Kripto 5-SMA Trend Durumu**
     - **En Güçlü Adaylar / Fırsatlar** (somut metrikler, giriş bölgesi, ATR/stop-loss, hedef ve risk/ödül)
     - **Risk Uyarıları & Yürütme Planı** (simülasyon/sanal defter vurgusu; gerçek yatırım tavsiyesi değildir uyarısı)
- **Single stock analysis** (`NVDA`, `AAPL`, `THYAO.IS`, `SPY`, etc.): call `dsa_analyze_stock`.
- **US Alpha / Insider / Earnings Drift**: call `dsa_screen_us_alpha`, `dsa_scan_sec_form4_live`, `dsa_scan_pead_candidates`.
- **BIST & KAP Catalysts**: call `dsa_screen_bist_stocks`, `dsa_scan_kap_contracts`.
- **Crypto Trend**: call `dsa_get_crypto_trend_signal` (use `step_paper=true` only if the user asks to update the crypto paper book).
- **Simulated Paper Orders**: ONLY call `dsa_place_paper_order` when the user explicitly requests recording a simulated paper order.

### Response Discipline
- Reply in the **same language** as the user's message (Turkish if the user writes in Turkish, English if in English, etc.).
- Never invent live prices, scores, or signals. If a tool returns a partial error or empty list, report it transparently.
- Format outputs cleanly with Markdown tables and concise bullet points suitable for a trading cockpit.
""".strip()


def normalize_mcp_tool_name(raw_name: str) -> str:
    """Normalize MCP-prefixed tool names such as ``mcp__dsa__dsa_get_market_regime``."""
    cleaned = str(raw_name or "").strip()
    for prefix in ("mcp__dsa__", "dsa__", "dsa:"):
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :]
    return cleaned


def resolve_cli_binary(binary_name: str, *, env_override: Optional[str] = None) -> Optional[str]:
    """Resolve a local CLI binary cross-platform, preferring ``.cmd``/``.exe`` over ``.ps1`` on Windows."""
    if env_override:
        override_val = (os.getenv(env_override) or "").strip()
        if override_val:
            override_path = Path(override_val)
            if override_path.is_file():
                return str(override_path)
            found_override = shutil.which(override_val)
            if found_override:
                return found_override

    is_windows = os.name == "nt"
    if is_windows:
        for ext in (".cmd", ".exe", ".bat"):
            candidate = shutil.which(f"{binary_name}{ext}")
            if candidate:
                return candidate

    resolved = shutil.which(binary_name)
    if resolved and is_windows and resolved.lower().endswith(".ps1"):
        base = Path(resolved)
        for ext in (".cmd", ".exe", ".bat"):
            sibling = base.with_suffix(ext)
            if sibling.is_file():
                return str(sibling)
    return resolved


def build_cli_subprocess_env(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Construct a clean environment for local CLI agents that keeps CLI auth intact."""
    env: Dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if upper in _STRIPPED_DSA_SECRET_EXACT:
            continue
        if any(upper.startswith(prefix) for prefix in _STRIPPED_DSA_SECRET_PREFIXES):
            continue
        env[key] = value

    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["NO_COLOR"] = "1"
    if extra_env:
        for key, value in extra_env.items():
            if value is not None:
                env[str(key)] = str(value)
    return env


def terminate_process_tree(proc: Optional[subprocess.Popen]) -> None:
    """Forcefully reclaim a spawned CLI process and any child MCP server processes."""
    if proc is None:
        return
    if proc.poll() is not None:
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        try:
            proc.wait(timeout=3)
        except subprocess.SubprocessError:
            pass
        return

    # POSIX process group reclamation
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        try:
            proc.terminate()
        except OSError:
            pass
    try:
        proc.wait(timeout=2)
        return
    except subprocess.SubprocessError:
        pass
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=2)
    except subprocess.SubprocessError:
        pass


def spawn_line_reader(stream: Any, out_queue: "queue.Queue[Optional[str]]") -> threading.Thread:
    """Read lines from a subprocess pipe into a queue in a daemon thread (Windows-safe)."""

    def _worker() -> None:
        try:
            for line in iter(stream.readline, ""):
                out_queue.put(line)
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass
            out_queue.put(None)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread


def drain_stream_lines(
    proc: subprocess.Popen,
    stdout_queue: "queue.Queue[Optional[str]]",
    *,
    deadline: float,
    cancel_event: Optional[threading.Event],
    on_line: Callable[[str], None],
) -> Tuple[Optional[str], Optional[str]]:
    """Consume queued stdout lines until EOF, cancellation, or deadline.

    Returns ``(error_code, error_message)`` where both are ``None`` on normal EOF.
    """
    eof = False
    while not eof:
        if cancel_event is not None and cancel_event.is_set():
            terminate_process_tree(proc)
            return "cancelled", "CLI Agent request was cancelled by user."
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            terminate_process_tree(proc)
            return "timeout", "CLI Agent exceeded the overall timeout."
        try:
            line = stdout_queue.get(timeout=min(0.15, max(0.02, remaining)))
        except queue.Empty:
            if proc.poll() is not None and stdout_queue.empty():
                break
            continue
        if line is None:
            eof = True
            break
        stripped = line.strip()
        if stripped:
            on_line(stripped)

    # Wait briefly for process exit after stdout closes
    remaining = max(0.2, min(5.0, deadline - time.monotonic()))
    try:
        proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        terminate_process_tree(proc)
        return "timeout", "CLI Agent did not exit cleanly before timeout."

    return None, None


def build_strategic_trading_system_prompt(
    base_system_prompt: str = "",
    *,
    stock_scope: Any = None,
    page_route: Optional[str] = None,
) -> str:
    """Combine DSA system prompt with live MCP strategic trading guidance."""
    parts: List[str] = []
    if base_system_prompt and base_system_prompt.strip():
        parts.append(base_system_prompt.strip())
    parts.append(_CLI_STRATEGIC_PROMPT_ADDENDUM)

    context_hints: List[str] = []
    if stock_scope is not None:
        code = getattr(stock_scope, "stock_code", None)
        name = getattr(stock_scope, "stock_name", None)
        if code:
            context_hints.append(f"- Active stock focus: `{code}`" + (f" ({name})" if name else ""))
    if page_route:
        context_hints.append(f"- Active DSA Web UI page: `{page_route}`")
    if context_hints:
        parts.append("## Current UI Context\n" + "\n".join(context_hints))

    return "\n\n".join(parts)


def format_conversation_prompt(
    history_messages: Iterable[Dict[str, Any]],
    user_message: str,
    *,
    max_history_messages: int = 12,
    max_message_chars: int = 2500,
) -> str:
    """Render recent conversation turns plus the active user request for single-turn CLI runs."""
    cleaned_history: List[Tuple[str, str]] = []
    for msg in list(history_messages or [])[-max_history_messages:]:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        text = content.strip()
        if len(text) > max_message_chars:
            text = text[:max_message_chars] + " ...[truncated]"
        cleaned_history.append((role, text))

    if not cleaned_history:
        return user_message.strip()

    lines = ["## Previous Conversation History"]
    for role, text in cleaned_history:
        label = "User" if role == "user" else "Assistant"
        lines.append(f"### {label}\n{text}")
    lines.append("## Current User Request")
    lines.append(user_message.strip())
    return "\n\n".join(lines)


def _extract_version_line(stdout: str, stderr: str) -> Optional[str]:
    for text in (stdout, stderr):
        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lower = line.lower()
            if lower.startswith(("critical failure", "early cleanup", "tool output cleanup", "at ", "errno", "code:", "syscall:", "path:", "{", "}")):
                continue
            if any(ch.isdigit() for ch in line) and len(line) <= 80:
                return line
    return None


def _read_npm_shim_version(executable: str, package_rel_paths: Iterable[str]) -> Optional[str]:
    """Fast-path version detection for npm-installed Windows/POSIX CLI shims (<1 ms)."""
    try:
        bin_dir = Path(executable).resolve().parent
    except OSError:
        return None
    for rel in package_rel_paths:
        pkg_json = bin_dir / rel
        if pkg_json.is_file():
            try:
                import json

                data = json.loads(pkg_json.read_text(encoding="utf-8"))
                ver = str(data.get("version") or "").strip()
                if ver:
                    return ver
            except (OSError, ValueError):
                continue
    return None


def probe_cli_backend(backend_id: str, *, use_cache: bool = True) -> Dict[str, Any]:
    """Check whether ``claude_cli`` or ``gemini_cli`` is installed and runnable."""
    if backend_id not in CLI_NATIVE_BACKEND_IDS:
        return {
            "backend": backend_id,
            "available": False,
            "experimental": False,
            "version": None,
            "executable": None,
            "mcp_enabled": False,
            "error_code": "capability_unsupported",
            "message": f"Unsupported CLI backend: {backend_id}",
        }

    now = time.monotonic()
    if use_cache:
        with _PROBE_CACHE_LOCK:
            cached = _PROBE_CACHE.get(backend_id)
            if cached and (now - cached[0]) < _PROBE_TTL_SECONDS:
                return dict(cached[1])

    if backend_id == "claude_cli":
        binary_name = "claude"
        env_override = "DSA_CLAUDE_CLI_PATH"
        display = "Claude Code CLI"
        pkg_rels = (
            "node_modules/@anthropic-ai/claude-code/package.json",
            "../lib/node_modules/@anthropic-ai/claude-code/package.json",
        )
    else:
        binary_name = "gemini"
        env_override = "DSA_GEMINI_CLI_PATH"
        display = "Gemini CLI"
        pkg_rels = (
            "node_modules/@google/gemini-cli/package.json",
            "../lib/node_modules/@google/gemini-cli/package.json",
        )

    executable = resolve_cli_binary(binary_name, env_override=env_override)
    if not executable:
        result = {
            "backend": backend_id,
            "available": False,
            "experimental": False,
            "version": None,
            "executable": None,
            "mcp_enabled": True,
            "error_code": "command_not_found",
            "message": f"{display} (`{binary_name}`) PATH üzerinde bulunamadı.",
        }
    else:
        version: Optional[str] = _read_npm_shim_version(executable, pkg_rels)
        available = version is not None
        if not available:
            try:
                proc = subprocess.run(
                    [executable, "--version"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=build_cli_subprocess_env(),
                    timeout=15,
                    check=False,
                )
                version = _extract_version_line(proc.stdout or "", proc.stderr or "")
                available = proc.returncode == 0 or version is not None
            except subprocess.TimeoutExpired:
                # Binary exists on PATH; treat slow cold-start as available with unknown version.
                available = True
                version = None
            except (OSError, subprocess.SubprocessError) as exc:
                available = False
                version = None
                logger.debug("CLI probe failed for %s: %s", backend_id, exc)

        result = {
            "backend": backend_id,
            "available": available,
            "experimental": False,
            "version": version,
            "executable": executable,
            "mcp_enabled": True,
            "error_code": None if available else "capability_unsupported",
            "message": (
                f"{display} hazır (MCP bağlı)"
                if available
                else f"{display} çalıştırılamadı."
            ),
        }

    with _PROBE_CACHE_LOCK:
        _PROBE_CACHE[backend_id] = (now, dict(result))
    return result


def clear_cli_probe_cache() -> None:
    """Reset the CLI availability probe cache (useful in tests)."""
    with _PROBE_CACHE_LOCK:
        _PROBE_CACHE.clear()
