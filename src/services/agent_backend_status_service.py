# -*- coding: utf-8 -*-
"""Side-effect-free compatibility status for Agent Chat backends."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from typing import Any, Dict, Optional

from src.agent.agent_backend import resolve_agent_backend_id
from src.agent.codex_app_server_transport import (
    CodexAppServerError,
    controlled_environment,
    is_native_windows,
    resolve_command,
)
from src.config import Config, parse_env_bool, parse_env_int
from src.services.generation_backend_status_service import GenerationBackendStatusService


_PROBE_TERM_GRACE_SECONDS = 0.5
_PROBE_KILL_GRACE_SECONDS = 2.0


def _probe_process_group_alive(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_probe_process_group(process: subprocess.Popen) -> None:
    """Synchronously reclaim the CLI launcher and its native Codex child."""
    process_group_id = process.pid
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        if process.poll() is None:
            process.terminate()

    term_deadline = time.monotonic() + _PROBE_TERM_GRACE_SECONDS
    if process.poll() is None:
        try:
            process.wait(timeout=max(0.0, term_deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    while _probe_process_group_alive(process_group_id) and time.monotonic() < term_deadline:
        time.sleep(0.02)

    if process.poll() is None or _probe_process_group_alive(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            if process.poll() is None:
                process.kill()
        kill_deadline = time.monotonic() + _PROBE_KILL_GRACE_SECONDS
        if process.poll() is None:
            try:
                process.wait(timeout=max(0.0, kill_deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        while _probe_process_group_alive(process_group_id) and time.monotonic() < kill_deadline:
            time.sleep(0.02)

    if process.poll() is None or _probe_process_group_alive(process_group_id):
        raise CodexAppServerError(
            "resource_cleanup_failed",
            "Codex compatibility-check process group could not be reclaimed",
        )


def _run_codex_probe(
    command: list[str],
    *,
    timeout: float,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    """Run one bounded CLI probe without orphaning the native Codex child."""
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture_output else subprocess.DEVNULL,
        text=capture_output,
        env=controlled_environment(),
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            _terminate_probe_process_group(process)
        finally:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        raise
    if _probe_process_group_alive(process.pid):
        _terminate_probe_process_group(process)
    return subprocess.CompletedProcess(
        command,
        process.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _schema_contains_literal(value: Any, literal: str) -> bool:
    if isinstance(value, dict):
        return literal in value or any(
            _schema_contains_literal(item, literal) for item in value.values()
        )
    if isinstance(value, list):
        return any(_schema_contains_literal(item, literal) for item in value)
    return value == literal


def _codex_protocol_schema_is_capable(schema_dir: Path) -> bool:
    requirements = {
        Path("v2", "ThreadStartParams.json"): {"dynamicTools", "runtimeWorkspaceRoots"},
        Path("v2", "ThreadStartResponse.json"): {
            "activePermissionProfile",
            "runtimeWorkspaceRoots",
        },
        Path("ClientRequest.json"): {
            "thread/inject_items",
            "turn/start",
            "turn/interrupt",
            "config/read",
            "mcpServerStatus/list",
        },
        Path("ServerRequest.json"): {"item/tool/call"},
        Path("ServerNotification.json"): {"item/completed", "turn/completed"},
    }
    for relative_path, literals in requirements.items():
        path = schema_dir / relative_path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not all(_schema_contains_literal(payload, literal) for literal in literals):
            return False
    return True


def evaluate_agent_backend_config(
    config: Config,
    *,
    backend_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Select the backend and evaluate only request-time configuration invariants."""
    from src.agent.agent_backend import AGENT_BACKEND_IDS

    if backend_override is not None and str(backend_override).strip():
        requested = str(backend_override).strip().lower()
        if requested not in AGENT_BACKEND_IDS:
            return {
                "backend": requested or "unknown",
                "available": False,
                "error_code": "capability_unsupported",
                "message": f"Unsupported AGENT_BACKEND: {requested}",
            }
        selected = "litellm" if requested == "auto" else requested
    else:
        requested = str(getattr(config, "agent_backend", "auto") or "auto").strip().lower()
        try:
            selected = resolve_agent_backend_id(config)
        except ValueError as exc:
            return {
                "backend": requested or "unknown",
                "available": False,
                "error_code": getattr(exc, "code", "capability_unsupported"),
                "message": str(exc),
            }

    if selected in {"claude_cli", "gemini_cli"}:
        from src.agent.cli_bridge_common import probe_cli_backend

        probe = probe_cli_backend(selected)
        return {
            "backend": selected,
            "available": bool(probe.get("available")),
            "error_code": probe.get("error_code"),
            "message": probe.get("message"),
        }

    if getattr(config, "_agent_mode_explicit", False) and not getattr(config, "agent_mode", False):
        return {
            "backend": selected,
            "available": False,
            "error_code": "agent_mode_disabled",
            "message": "Agent mode is disabled",
        }
    if selected == "codex_app_server" and getattr(config, "agent_arch", "single") != "single":
        return {
            "backend": selected,
            "available": False,
            "error_code": "unsupported_agent_arch",
            "message": "Codex Agent currently supports single-agent Chat only",
        }
    if (
        selected == "codex_app_server"
        and int(getattr(config, "agent_orchestrator_timeout_s", 0) or 0) <= 0
    ):
        return {
            "backend": selected,
            "available": False,
            "error_code": "invalid_timeout",
            "message": "Codex Agent requires AGENT_ORCHESTRATOR_TIMEOUT_S greater than 0",
        }
    if selected == "litellm" and not config.is_agent_available():
        return {
            "backend": selected,
            "available": False,
            "error_code": "capability_unsupported",
            "message": "no_agent_primary",
        }
    return {
        "backend": selected,
        "available": True,
        "error_code": None,
        "message": None,
    }


class AgentBackendStatusService:
    """Evaluate whether the selected Chat backend can be attempted."""

    def __init__(self, *, effective_map: Optional[Dict[str, str]] = None, config: Optional[Config] = None) -> None:
        self._effective_map = {
            str(key).upper(): "" if value is None else str(value)
            for key, value in (effective_map or {}).items()
        }
        self._config = config

    def get_status(self) -> Dict[str, Any]:
        config = self._build_config()
        evaluation = evaluate_agent_backend_config(config)
        if not evaluation["available"]:
            return self._response(
                backend=evaluation["backend"],
                available=False,
                error_code=evaluation["error_code"],
                message=evaluation["message"],
            )
        if evaluation["backend"] in {"claude_cli", "gemini_cli"}:
            from src.agent.cli_bridge_common import probe_cli_backend

            probe = probe_cli_backend(evaluation["backend"])
            return self._response(
                backend=evaluation["backend"],
                available=bool(probe.get("available")),
                version=probe.get("version"),
                error_code=probe.get("error_code"),
                message=probe.get("message"),
            )
        if evaluation["backend"] == "litellm":
            return self._response(backend="litellm", available=True)
        return self._codex_cheap_status()

    def list_backends(self) -> Dict[str, Any]:
        """Return availability metadata for all Chat backends (Claude CLI, Gemini CLI, LiteLLM, Codex)."""
        from src.agent.cli_bridge_common import probe_cli_backend

        config = self._build_config()
        configured_default = "litellm"
        try:
            configured_default = resolve_agent_backend_id(config)
        except ValueError:
            configured_default = "litellm"

        claude_probe = probe_cli_backend("claude_cli")
        gemini_probe = probe_cli_backend("gemini_cli")
        litellm_eval = evaluate_agent_backend_config(config, backend_override="litellm")

        backends = [
            {
                "id": "claude_cli",
                "label": "Claude CLI (MCP)",
                "available": bool(claude_probe.get("available")),
                "version": claude_probe.get("version"),
                "mcp_enabled": True,
                "is_default": configured_default == "claude_cli",
                "error_code": claude_probe.get("error_code"),
                "message": claude_probe.get("message"),
                "description": "Yerel Claude Code CLI + canlı DSA MCP araç köprüsü (API anahtarı gerekmez)",
            },
            {
                "id": "gemini_cli",
                "label": "Gemini CLI (MCP)",
                "available": bool(gemini_probe.get("available")),
                "version": gemini_probe.get("version"),
                "mcp_enabled": True,
                "is_default": configured_default == "gemini_cli",
                "error_code": gemini_probe.get("error_code"),
                "message": gemini_probe.get("message"),
                "description": "Yerel Gemini CLI + canlı DSA MCP araç köprüsü (API anahtarı gerekmez)",
            },
            {
                "id": "litellm",
                "label": "LiteLLM API",
                "available": bool(litellm_eval.get("available")),
                "version": None,
                "mcp_enabled": False,
                "is_default": configured_default == "litellm",
                "error_code": litellm_eval.get("error_code"),
                "message": litellm_eval.get("message"),
                "description": "Yapılandırılmış API anahtarı üzerinden yerleşik DSA Agent motoru",
            },
        ]

        # Recommend Claude CLI first when installed, then Gemini CLI, then LiteLLM.
        recommended = configured_default
        if not any(b["id"] == recommended and b["available"] for b in backends):
            for candidate_id in ("claude_cli", "gemini_cli", "litellm"):
                if any(b["id"] == candidate_id and b["available"] for b in backends):
                    recommended = candidate_id
                    break
        elif configured_default == "litellm":
            # In native CLI setups, highlight claude_cli if installed as the recommended MCP bridge.
            if claude_probe.get("available"):
                recommended = "claude_cli"
            elif gemini_probe.get("available"):
                recommended = "gemini_cli"

        return {
            "configured_default": configured_default,
            "recommended_backend": recommended,
            "mcp_server_name": "dsa",
            "backends": backends,
        }

    def _codex_cheap_status(self) -> Dict[str, Any]:
        if is_native_windows():
            return self._response(
                backend="codex_app_server",
                available=False,
                error_code="platform_unsupported",
                message="Codex App Server Agent is not supported on native Windows in this phase",
            )
        try:
            command = resolve_command()
        except CodexAppServerError as exc:
            return self._response(
                backend="codex_app_server",
                available=False,
                error_code=getattr(exc, "code", "command_not_found"),
                message="Codex was not found on the DSA process PATH",
            )
        try:
            with tempfile.TemporaryDirectory(prefix="dsa-codex-protocol-") as schema_dir:
                schema_result = _run_codex_probe(
                    [
                        command[0],
                        "app-server",
                        "generate-json-schema",
                        "--experimental",
                        "--out",
                        schema_dir,
                    ],
                    timeout=5,
                )
                protocol_capable = (
                    schema_result.returncode == 0
                    and _codex_protocol_schema_is_capable(Path(schema_dir))
                )
        except CodexAppServerError as exc:
            return self._response(
                backend="codex_app_server",
                available=False,
                error_code=exc.code,
                message="Codex compatibility check could not reclaim its background process",
            )
        except (OSError, subprocess.SubprocessError):
            return self._response(
                backend="codex_app_server",
                available=False,
                error_code="capability_unsupported",
                message="Codex App Server capability check failed",
            )
        if not protocol_capable:
            return self._response(
                backend="codex_app_server",
                available=False,
                error_code="capability_unsupported",
                message="This Codex installation does not expose the required dynamic-tool protocol",
            )
        version = None
        try:
            version_result = _run_codex_probe(
                [command[0], "--version"],
                timeout=5,
                capture_output=True,
            )
            if version_result.returncode == 0:
                version = version_result.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            pass
        return self._response(
            backend="codex_app_server",
            available=True,
            version=version,
        )

    def _response(
        self,
        *,
        backend: str,
        available: bool,
        error_code: Optional[str] = None,
        message: Optional[str] = None,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "backend": backend,
            "available": available,
            "experimental": backend == "codex_app_server",
            "version": version,
            "error_code": error_code,
            "message": message,
        }

    def _build_config(self) -> Config:
        if self._config is not None:
            return self._config
        generation_service = GenerationBackendStatusService(effective_map=self._effective_map)
        config = generation_service.build_effective_config()
        config.agent_backend = (self._effective_map.get("AGENT_BACKEND") or "auto").strip().lower()
        config.agent_generation_backend = (
            self._effective_map.get("AGENT_GENERATION_BACKEND") or "auto"
        ).strip().lower()
        config.agent_litellm_model = (self._effective_map.get("AGENT_LITELLM_MODEL") or "").strip()
        config.agent_arch = (self._effective_map.get("AGENT_ARCH") or "single").strip().lower()
        config.agent_mode = parse_env_bool(self._effective_map.get("AGENT_MODE"), default=False)
        config._agent_mode_explicit = "AGENT_MODE" in self._effective_map
        config.agent_orchestrator_timeout_s = parse_env_int(
            self._effective_map.get("AGENT_ORCHESTRATOR_TIMEOUT_S"),
            600,
            field_name="AGENT_ORCHESTRATOR_TIMEOUT_S",
            minimum=0,
        )
        return config
