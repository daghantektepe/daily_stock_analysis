# -*- coding: utf-8 -*-
"""Native Gemini CLI + DSA MCP Server AgentBackend."""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.agent.agent_backend import AgentBackend, AgentRunRequest, AgentRunResult
from src.agent.cli_bridge_common import (
    MCP_TOOL_DISPLAY_NAMES,
    build_cli_subprocess_env,
    build_strategic_trading_system_prompt,
    drain_stream_lines,
    format_conversation_prompt,
    normalize_mcp_tool_name,
    resolve_cli_binary,
    spawn_line_reader,
    terminate_process_tree,
)
from src.agent.stream_events import stream_event
from src.mcp.config_gen import (
    DSA_MCP_SERVER_NAME,
    get_project_root,
    write_temp_gemini_workspace_config,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 300.0


class GeminiCliAgentBackend(AgentBackend):
    """Execute one DSA Chat turn through local Gemini CLI wired to the DSA MCP server."""

    backend_id = "gemini_cli"
    runtime_owns_loop = True

    def __init__(
        self,
        config: Any = None,
        *,
        project_root: Optional[Path] = None,
        python_executable: Optional[str] = None,
        page_route: Optional[str] = None,
    ) -> None:
        self.config = config
        self.project_root = Path(project_root or get_project_root()).resolve()
        self.python_executable = python_executable
        self.page_route = page_route

    def _build_command(self, gemini_bin: str) -> List[str]:
        cmd: List[str] = [
            gemini_bin,
            "-p",
            "Follow the DSA instructions and answer the user's request using the connected dsa MCP tools.",
            "--output-format",
            "stream-json",
            "--approval-mode",
            "yolo",
            "--allowed-mcp-server-names",
            DSA_MCP_SERVER_NAME,
            "--skip-trust",
        ]
        model = (
            getattr(self.config, "gemini_cli_model", None)
            or os.getenv("DSA_GEMINI_CLI_MODEL")
            or ""
        ).strip()
        if model:
            cmd.extend(["-m", model])
        return cmd

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        timeout = request.max_wall_clock_seconds
        if timeout is None or timeout <= 0:
            cfg_timeout = float(getattr(self.config, "agent_orchestrator_timeout_s", 0) or 0)
            timeout = cfg_timeout if cfg_timeout > 0 else _DEFAULT_TIMEOUT_SECONDS
        deadline = time.monotonic() + float(timeout)

        if request.cancel_event is not None and request.cancel_event.is_set():
            return self._error_result("cancelled", "Gemini CLI isteği iptal edildi.")

        gemini_bin = resolve_cli_binary("gemini", env_override="DSA_GEMINI_CLI_PATH")
        if not gemini_bin:
            return self._error_result(
                "command_not_found",
                "Gemini CLI (`gemini`) PATH üzerinde bulunamadı. Lütfen `gemini` kurulumunu kontrol edin.",
            )

        if request.progress_callback:
            request.progress_callback(
                stream_event("thinking", step=1, message="Gemini CLI + DSA MCP köprüsü bağlanıyor…")
            )

        temp_workspace: Optional[Path] = None
        proc: Optional[subprocess.Popen] = None
        stderr_chunks: List[str] = []
        stderr_queue: "queue.Queue[Optional[str]]" = queue.Queue()
        stdout_queue: "queue.Queue[Optional[str]]" = queue.Queue()

        tool_calls_log: List[Dict[str, Any]] = []
        pending_tools: Dict[str, Tuple[str, float, Dict[str, Any], int]] = {}
        assistant_chunks: List[str] = []
        plain_fallback_lines: List[str] = []
        final_result_text: Optional[str] = None
        model_name = ""
        usage: Optional[Dict[str, Any]] = None
        diagnostics: Dict[str, Any] = {"provider": "gemini_cli", "mcp_server": DSA_MCP_SERVER_NAME}
        step_counter = 1
        generating_emitted = False
        result_error: Optional[str] = None

        try:
            temp_workspace = write_temp_gemini_workspace_config(
                project_root=self.project_root,
                python_executable=self.python_executable,
                server_name=DSA_MCP_SERVER_NAME,
            )
            system_prompt = build_strategic_trading_system_prompt(
                request.system_prompt,
                stock_scope=request.stock_scope,
                page_route=self.page_route,
            )
            user_block = format_conversation_prompt(request.history_messages, request.user_message)
            stdin_payload = f"{system_prompt}\n\n---\n\n{user_block}\n"

            cmd = self._build_command(gemini_bin)
            popen_kwargs: Dict[str, Any] = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "cwd": str(temp_workspace),
                "env": build_cli_subprocess_env(),
            }
            if os.name != "nt":
                popen_kwargs["start_new_session"] = True

            proc = subprocess.Popen(cmd, **popen_kwargs)
            assert proc.stdin is not None
            assert proc.stdout is not None
            assert proc.stderr is not None

            spawn_line_reader(proc.stdout, stdout_queue)
            spawn_line_reader(proc.stderr, stderr_queue)

            try:
                proc.stdin.write(stdin_payload)
                proc.stdin.close()
            except BrokenPipeError:
                pass

            def _handle_stream_line(line: str) -> None:
                nonlocal final_result_text, model_name, usage, step_counter, generating_emitted, result_error
                if not line.startswith("{"):
                    # Filter noisy startup lines, keep potential plain-text fallback
                    if not line.startswith(("Loaded ", "Warning:", "Error:")):
                        plain_fallback_lines.append(line)
                    return
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    return
                if not isinstance(payload, dict):
                    return

                ev_type = str(payload.get("type") or "").strip().lower()

                if ev_type == "init":
                    if payload.get("model"):
                        model_name = str(payload["model"])
                    if request.progress_callback:
                        request.progress_callback(
                            stream_event(
                                "thinking",
                                step=step_counter,
                                message="Gemini CLI hazır, DSA MCP araçları değerlendiriliyor…",
                            )
                        )
                    return

                if ev_type == "tool_use":
                    step_counter += 1
                    raw_tool = str(payload.get("tool_name") or payload.get("name") or "")
                    clean_tool = normalize_mcp_tool_name(raw_tool)
                    call_id = str(payload.get("tool_id") or payload.get("id") or f"call-{step_counter}")
                    params = payload.get("parameters") or payload.get("args") or {}
                    if not isinstance(params, dict):
                        params = {}
                    pending_tools[call_id] = (clean_tool, time.monotonic(), params, step_counter)
                    if request.progress_callback:
                        request.progress_callback(
                            stream_event(
                                "tool_start",
                                step=step_counter,
                                tool=clean_tool,
                                display_name=MCP_TOOL_DISPLAY_NAMES.get(clean_tool, clean_tool),
                            )
                        )
                    return

                if ev_type == "tool_result":
                    call_id = str(payload.get("tool_id") or payload.get("id") or "")
                    status = str(payload.get("status") or "success").lower()
                    is_success = status not in {"error", "failed", "failure"} and not bool(payload.get("is_error"))
                    meta = pending_tools.pop(call_id, None)
                    if meta is not None:
                        clean_tool, started_at, tool_input, call_step = meta
                        duration = round(max(0.0, time.monotonic() - started_at), 2)
                    else:
                        clean_tool = normalize_mcp_tool_name(str(payload.get("tool_name") or "dsa_mcp_tool"))
                        tool_input, call_step, duration = {}, step_counter, 0.0
                    tool_calls_log.append(
                        {
                            "step": call_step,
                            "tool": clean_tool,
                            "arguments_summary": tool_input,
                            "success": is_success,
                            "duration": duration,
                        }
                    )
                    if request.progress_callback:
                        request.progress_callback(
                            stream_event(
                                "tool_done",
                                step=call_step,
                                tool=clean_tool,
                                display_name=MCP_TOOL_DISPLAY_NAMES.get(clean_tool, clean_tool),
                                success=is_success,
                                duration=duration,
                            )
                        )
                    return

                if ev_type == "message":
                    role = str(payload.get("role") or "").lower()
                    content = payload.get("content")
                    if role == "assistant" and isinstance(content, str) and content:
                        assistant_chunks.append(content)
                        if not generating_emitted and request.progress_callback:
                            generating_emitted = True
                            request.progress_callback(
                                stream_event(
                                    "generating",
                                    step=step_counter,
                                    message="Gemini stratejik yanıtı hazırlıyor…",
                                )
                            )
                    return

                if ev_type == "error":
                    result_error = str(payload.get("message") or payload.get("error") or "Gemini CLI error")
                    return

                if ev_type == "result":
                    status = str(payload.get("status") or "success").lower()
                    if status in {"error", "failed"}:
                        err_obj = payload.get("error")
                        if isinstance(err_obj, dict):
                            result_error = str(err_obj.get("message") or err_obj)
                        else:
                            result_error = str(err_obj or "Gemini CLI failed")
                    if isinstance(payload.get("response"), str) and payload["response"].strip():
                        final_result_text = payload["response"]
                    stats = payload.get("stats")
                    if isinstance(stats, dict):
                        total_tokens = int(stats.get("total_tokens") or 0)
                        if total_tokens > 0:
                            usage = {
                                "prompt_tokens": int(stats.get("input_tokens") or 0),
                                "completion_tokens": int(stats.get("output_tokens") or 0),
                                "total_tokens": total_tokens,
                            }
                        diagnostics["stats"] = stats

            err_code, err_msg = drain_stream_lines(
                proc,
                stdout_queue,
                deadline=deadline,
                cancel_event=request.cancel_event,
                on_line=_handle_stream_line,
            )
            while not stderr_queue.empty():
                item = stderr_queue.get_nowait()
                if item:
                    stderr_chunks.append(item.strip())

            if err_code is not None:
                stderr_tail_early = " | ".join(s for s in stderr_chunks if s)[-600:]
                if stderr_tail_early:
                    diagnostics["stderr_tail"] = stderr_tail_early
                if err_code == "timeout" and any(
                    marker in stderr_tail_early.lower()
                    for marker in ("status: 503", '"code": 503', "service unavailable", "high demand")
                ):
                    err_msg = (
                        "Gemini CLI upstream sunucusu geçici olarak 503 (yoğunluk / Service Unavailable) "
                        "döndürüyor. Şu an Claude CLI (MCP) motoruna geçip hemen devam edebilirsiniz."
                    )
                return self._error_result(
                    err_code,
                    err_msg or "Gemini CLI çalıştırma hatası.",
                    tool_calls_log=tool_calls_log,
                    total_steps=step_counter,
                    diagnostics=diagnostics,
                )

            answer = (
                final_result_text
                if final_result_text is not None and final_result_text.strip()
                else "".join(assistant_chunks).strip()
            )
            if not answer and plain_fallback_lines:
                answer = "\n".join(plain_fallback_lines).strip()

            stderr_summary = " | ".join(s for s in stderr_chunks if s)[-600:]
            if stderr_summary:
                diagnostics["stderr_tail"] = stderr_summary

            if result_error or (proc.returncode != 0 and not answer):
                lower_err = ((result_error or "") + " " + stderr_summary).lower()
                code = (
                    "login_required"
                    if any(k in lower_err for k in ("login", "authenticate", "oauth", "credentials", "api key"))
                    else "unknown_backend_error"
                )
                msg = result_error or stderr_summary or f"Gemini CLI çıkış kodu: {proc.returncode}"
                return self._error_result(
                    code,
                    msg,
                    tool_calls_log=tool_calls_log,
                    total_steps=step_counter,
                    diagnostics=diagnostics,
                )

            return AgentRunResult(
                success=True,
                final_answer=answer or "（Yanıt boş döndü）",
                tool_calls_log=tool_calls_log,
                model=model_name or "gemini-cli",
                backend=self.backend_id,
                usage=usage,
                diagnostics=diagnostics,
                total_steps=max(1, step_counter),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[GeminiCliAgentBackend] unexpected error")
            return self._error_result(
                "unknown_backend_error",
                f"Gemini CLI köprüsü hatası: {exc}",
                tool_calls_log=tool_calls_log,
                total_steps=step_counter,
                diagnostics=diagnostics,
            )
        finally:
            terminate_process_tree(proc)
            if temp_workspace is not None:
                shutil.rmtree(temp_workspace, ignore_errors=True)

    def _error_result(
        self,
        error_code: str,
        error_message: str,
        *,
        tool_calls_log: Optional[List[Dict[str, Any]]] = None,
        total_steps: int = 0,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> AgentRunResult:
        return AgentRunResult(
            success=False,
            final_answer="",
            tool_calls_log=list(tool_calls_log or []),
            model="gemini-cli",
            backend=self.backend_id,
            diagnostics=dict(diagnostics or {"provider": "gemini_cli"}),
            error_code=error_code,
            error_message=error_message,
            total_steps=total_steps,
        )
