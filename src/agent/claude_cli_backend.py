# -*- coding: utf-8 -*-
"""Native Claude Code CLI + DSA MCP Server AgentBackend."""

from __future__ import annotations

import json
import logging
import os
import queue
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
from src.mcp.config_gen import DSA_MCP_SERVER_NAME, get_project_root, write_temp_claude_mcp_config

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 300.0


class ClaudeCliAgentBackend(AgentBackend):
    """Execute one DSA Chat turn through local Claude Code CLI wired to the DSA MCP server."""

    backend_id = "claude_cli"
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

    def _build_command(
        self,
        claude_bin: str,
        mcp_config_path: Path,
        system_prompt: str,
    ) -> List[str]:
        cmd: List[str] = [
            claude_bin,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--mcp-config",
            str(mcp_config_path),
            "--strict-mcp-config",
            "--tools",
            "",
            "--allowedTools",
            f"mcp__{DSA_MCP_SERVER_NAME}__*",
            "--permission-mode",
            "dontAsk",
            "--no-session-persistence",
            "--append-system-prompt",
            system_prompt,
        ]
        model = (
            getattr(self.config, "claude_cli_model", None)
            or os.getenv("DSA_CLAUDE_CLI_MODEL")
            or ""
        ).strip()
        if model:
            cmd.extend(["--model", model])
        return cmd

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        timeout = request.max_wall_clock_seconds
        if timeout is None or timeout <= 0:
            cfg_timeout = float(getattr(self.config, "agent_orchestrator_timeout_s", 0) or 0)
            timeout = cfg_timeout if cfg_timeout > 0 else _DEFAULT_TIMEOUT_SECONDS
        deadline = time.monotonic() + float(timeout)

        if request.cancel_event is not None and request.cancel_event.is_set():
            return self._error_result("cancelled", "Claude CLI isteği iptal edildi.")

        claude_bin = resolve_cli_binary("claude", env_override="DSA_CLAUDE_CLI_PATH")
        if not claude_bin:
            return self._error_result(
                "command_not_found",
                "Claude Code CLI (`claude`) PATH üzerinde bulunamadı. Lütfen `claude` kurulumunu kontrol edin.",
            )

        if request.progress_callback:
            request.progress_callback(
                stream_event("thinking", step=1, message="Claude CLI + DSA MCP köprüsü bağlanıyor…")
            )

        mcp_config_path: Optional[Path] = None
        proc: Optional[subprocess.Popen] = None
        stderr_chunks: List[str] = []
        stderr_queue: "queue.Queue[Optional[str]]" = queue.Queue()
        stdout_queue: "queue.Queue[Optional[str]]" = queue.Queue()

        tool_calls_log: List[Dict[str, Any]] = []
        pending_tools: Dict[str, Tuple[str, float, Dict[str, Any], int]] = {}
        assistant_text_parts: List[str] = []
        final_result_text: Optional[str] = None
        model_name = ""
        usage: Optional[Dict[str, Any]] = None
        diagnostics: Dict[str, Any] = {"provider": "claude_cli", "mcp_server": DSA_MCP_SERVER_NAME}
        step_counter = 1
        generating_emitted = False
        result_is_error = False

        try:
            mcp_config_path = write_temp_claude_mcp_config(
                project_root=self.project_root,
                python_executable=self.python_executable,
                server_name=DSA_MCP_SERVER_NAME,
            )
            system_prompt = build_strategic_trading_system_prompt(
                request.system_prompt,
                stock_scope=request.stock_scope,
                page_route=self.page_route,
            )
            prompt_text = format_conversation_prompt(request.history_messages, request.user_message)
            cmd = self._build_command(claude_bin, mcp_config_path, system_prompt)

            popen_kwargs: Dict[str, Any] = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "cwd": str(self.project_root),
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
                proc.stdin.write(prompt_text)
                proc.stdin.close()
            except BrokenPipeError:
                pass

            def _handle_stream_line(line: str) -> None:
                nonlocal final_result_text, model_name, usage, step_counter, generating_emitted, result_is_error
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    return
                if not isinstance(payload, dict):
                    return

                ev_type = payload.get("type")

                if ev_type == "system":
                    if payload.get("model"):
                        model_name = str(payload["model"])
                    mcp_servers = payload.get("mcp_servers")
                    if mcp_servers is not None:
                        diagnostics["mcp_servers"] = mcp_servers
                    if payload.get("subtype") == "init" and request.progress_callback:
                        request.progress_callback(
                            stream_event(
                                "thinking",
                                step=step_counter,
                                message="Claude CLI hazır, DSA MCP araçları değerlendiriliyor…",
                            )
                        )
                    return

                if ev_type == "assistant":
                    msg = payload.get("message")
                    if not isinstance(msg, dict):
                        return
                    if msg.get("model") and not model_name:
                        model_name = str(msg["model"])
                    content_blocks = msg.get("content")
                    if not isinstance(content_blocks, list):
                        return
                    for block in content_blocks:
                        if not isinstance(block, dict):
                            continue
                        b_type = block.get("type")
                        if b_type == "tool_use":
                            step_counter += 1
                            raw_tool = str(block.get("name") or "")
                            clean_tool = normalize_mcp_tool_name(raw_tool)
                            call_id = str(block.get("id") or f"call-{step_counter}")
                            tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                            pending_tools[call_id] = (clean_tool, time.monotonic(), tool_input, step_counter)
                            if request.progress_callback:
                                request.progress_callback(
                                    stream_event(
                                        "tool_start",
                                        step=step_counter,
                                        tool=clean_tool,
                                        display_name=MCP_TOOL_DISPLAY_NAMES.get(clean_tool, clean_tool),
                                    )
                                )
                        elif b_type == "thinking":
                            if request.progress_callback:
                                request.progress_callback(
                                    stream_event(
                                        "thinking",
                                        step=step_counter,
                                        message="Claude stratejik verileri yorumluyor…",
                                    )
                                )
                        elif b_type == "text":
                            text_chunk = str(block.get("text") or "")
                            if text_chunk.strip():
                                assistant_text_parts.append(text_chunk)
                                if not generating_emitted and request.progress_callback:
                                    generating_emitted = True
                                    request.progress_callback(
                                        stream_event(
                                            "generating",
                                            step=step_counter,
                                            message="Claude stratejik yanıtı hazırlıyor…",
                                        )
                                    )
                    return

                if ev_type == "user":
                    msg = payload.get("message")
                    if not isinstance(msg, dict):
                        return
                    content_blocks = msg.get("content")
                    if not isinstance(content_blocks, list):
                        return
                    for block in content_blocks:
                        if not isinstance(block, dict) or block.get("type") != "tool_result":
                            continue
                        call_id = str(block.get("tool_use_id") or "")
                        is_err = bool(block.get("is_error", False))
                        meta = pending_tools.pop(call_id, None)
                        if meta is not None:
                            clean_tool, started_at, tool_input, call_step = meta
                            duration = round(max(0.0, time.monotonic() - started_at), 2)
                        else:
                            clean_tool, tool_input, call_step, duration = "dsa_mcp_tool", {}, step_counter, 0.0
                        tool_calls_log.append(
                            {
                                "step": call_step,
                                "tool": clean_tool,
                                "arguments_summary": tool_input,
                                "success": not is_err,
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
                                    success=not is_err,
                                    duration=duration,
                                )
                            )
                    return

                if ev_type == "result":
                    if payload.get("is_error"):
                        result_is_error = True
                    res_text = payload.get("result")
                    if isinstance(res_text, str):
                        final_result_text = res_text
                    if isinstance(payload.get("usage"), dict):
                        raw_usage = payload["usage"]
                        in_tok = int(raw_usage.get("input_tokens") or 0)
                        out_tok = int(raw_usage.get("output_tokens") or 0)
                        cache_read = int(raw_usage.get("cache_read_input_tokens") or 0)
                        cache_create = int(raw_usage.get("cache_creation_input_tokens") or 0)
                        usage = {
                            "prompt_tokens": in_tok + cache_read + cache_create,
                            "completion_tokens": out_tok,
                            "total_tokens": in_tok + out_tok + cache_read + cache_create,
                        }
                    if payload.get("total_cost_usd") is not None:
                        diagnostics["total_cost_usd"] = payload["total_cost_usd"]
                    if payload.get("subtype"):
                        diagnostics["result_subtype"] = payload["subtype"]

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
                return self._error_result(
                    err_code,
                    err_msg or "Claude CLI çalıştırma hatası.",
                    tool_calls_log=tool_calls_log,
                    total_steps=step_counter,
                    diagnostics=diagnostics,
                )

            answer = (
                final_result_text
                if final_result_text is not None and final_result_text.strip()
                else "\n\n".join(assistant_text_parts).strip()
            )
            stderr_summary = " | ".join(s for s in stderr_chunks if s)[-600:]
            if stderr_summary:
                diagnostics["stderr_tail"] = stderr_summary

            if result_is_error or (proc.returncode != 0 and not answer):
                lower_err = (answer + " " + stderr_summary).lower()
                code = (
                    "login_required"
                    if any(k in lower_err for k in ("not logged in", "login", "authenticate", "unauthorized"))
                    else "unknown_backend_error"
                )
                msg = answer or stderr_summary or f"Claude CLI çıkış kodu: {proc.returncode}"
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
                model=model_name or "claude-cli",
                backend=self.backend_id,
                usage=usage,
                diagnostics=diagnostics,
                total_steps=max(1, step_counter),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[ClaudeCliAgentBackend] unexpected error")
            return self._error_result(
                "unknown_backend_error",
                f"Claude CLI köprüsü hatası: {exc}",
                tool_calls_log=tool_calls_log,
                total_steps=step_counter,
                diagnostics=diagnostics,
            )
        finally:
            terminate_process_tree(proc)
            if mcp_config_path is not None:
                try:
                    mcp_config_path.unlink(missing_ok=True)
                except OSError:
                    pass

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
            model="claude-cli",
            backend=self.backend_id,
            diagnostics=dict(diagnostics or {"provider": "claude_cli"}),
            error_code=error_code,
            error_message=error_message,
            total_steps=total_steps,
        )
