# -*- coding: utf-8 -*-
"""Tests for the Gemini CLI generation preset and ordered fallback chains."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.llm.backend_registry import (  # noqa: E402
    GEMINI_CLI_BACKEND_ID,
    LOCAL_CLI_GENERATION_BACKEND_IDS,
    SUPPORTED_GENERATION_FALLBACK_BACKENDS,
    parse_generation_fallback_chain,
    resolve_generation_fallback_backend_id,
    resolve_generation_fallback_backend_ids,
)
from src.llm.generation_backend import GenerationError, GenerationErrorCode  # noqa: E402
from src.llm.local_cli_backend import (  # noqa: E402
    GEMINI_CLI_PRESET,
    LocalCliExecutionResult,
    LocalCliExtractionError,
    LocalCliGenerationBackend,
    LocalCliPreset,
    _extract_gemini_cli_json,
    resolve_local_cli_preset,
)


def _cli_config(**overrides):
    defaults = {
        "generation_backend_timeout_seconds": 5,
        "generation_backend_max_output_bytes": 1024 * 1024,
        "generation_backend_max_concurrency": 1,
        "local_cli_backend_max_concurrency": 1,
        "generation_backend": "gemini_cli",
        "generation_fallback_backend": "",
        "report_language": "tr",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _result(stdout: str, returncode: int = 0) -> LocalCliExecutionResult:
    return LocalCliExecutionResult(stdout=stdout, stderr="", returncode=returncode)


# --------------------------------------------------------------- Gemini preset
def test_gemini_preset_is_registered_read_only_and_generation_only() -> None:
    assert GEMINI_CLI_BACKEND_ID in LOCAL_CLI_GENERATION_BACKEND_IDS
    assert resolve_local_cli_preset("gemini_cli") is GEMINI_CLI_PRESET
    argv = list(GEMINI_CLI_PRESET.argv)
    assert GEMINI_CLI_PRESET.executable == "gemini"
    assert argv[argv.index("--approval-mode") + 1] == "plan"
    assert argv[argv.index("--extensions") + 1] == "none"
    assert argv[argv.index("--output-format") + 1] == "json"
    # Untrusted temp cwd would silently downgrade approval mode.
    assert "--skip-trust" in argv
    assert "--allowed-mcp-server-names" in argv
    assert "-p" in argv
    assert GEMINI_CLI_PRESET.prompt_transport == "stdin"


def test_gemini_extractor_returns_response_text() -> None:
    stdout = json.dumps({"session_id": "s1", "response": ' {"sentiment_score": 64} ', "stats": {}})
    assert _extract_gemini_cli_json(_result(stdout)) == '{"sentiment_score": 64}'


@pytest.mark.parametrize(
    "stdout, code, reason",
    [
        ("", GenerationErrorCode.EMPTY_OUTPUT, "empty_output"),
        ("not json", GenerationErrorCode.INVALID_JSON, "invalid_json"),
        ("[1, 2]", GenerationErrorCode.SCHEMA_VALIDATION_FAILED, "schema_validation_failed"),
        (json.dumps({"session_id": "s1", "response": "  "}), GenerationErrorCode.EMPTY_OUTPUT, "empty_result"),
        (
            json.dumps({"error": {"type": "Error", "message": "Please set an Auth method", "code": 41}}),
            GenerationErrorCode.LOGIN_REQUIRED,
            "login_required",
        ),
        (
            json.dumps({"error": {"type": "QuotaError", "message": "Quota exceeded"}}),
            GenerationErrorCode.UNKNOWN_BACKEND_ERROR,
            "cli_result_error",
        ),
    ],
)
def test_gemini_extractor_maps_failures(stdout: str, code: GenerationErrorCode, reason: str) -> None:
    with pytest.raises(LocalCliExtractionError) as exc_info:
        _extract_gemini_cli_json(_result(stdout))
    assert exc_info.value.error_code is code
    assert exc_info.value.reason == reason


def test_gemini_preset_runs_with_contract_args_and_stdin_prompt(tmp_path: Path) -> None:
    argv_path = tmp_path / "argv.json"
    script = tmp_path / "mock_gemini.py"
    script.write_text(
        f"""
import json, pathlib, sys
pathlib.Path({str(argv_path)!r}).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
prompt = sys.stdin.read()
print(json.dumps({{"session_id": "s1", "response": json.dumps({{"echo": prompt}}), "stats": {{}}}}))
""",
        encoding="utf-8",
    )
    preset = LocalCliPreset(
        preset_id=GEMINI_CLI_BACKEND_ID,
        executable=sys.executable,
        argv=(str(script), *GEMINI_CLI_PRESET.argv),
        display_name="Mock Gemini CLI",
        extractor=GEMINI_CLI_PRESET.extractor,
        contract_args=GEMINI_CLI_PRESET.contract_args,
    )
    backend = LocalCliGenerationBackend(_cli_config(), preset=preset)

    result = backend.generate("THYAO.IS analizi", {}, response_validator=lambda text: json.loads(text))

    assert json.loads(result.text) == {"echo": "THYAO.IS analizi"}
    runtime_argv = json.loads(argv_path.read_text(encoding="utf-8"))
    for contract_arg in GEMINI_CLI_PRESET.contract_args:
        assert contract_arg in runtime_argv
    assert result.usage["usage_available"] is False


def test_gemini_auth_failure_exit_is_login_required(tmp_path: Path) -> None:
    script = tmp_path / "mock_gemini_auth.py"
    script.write_text(
        "import sys, json\n"
        "sys.stdin.read()\n"
        "sys.stderr.write(json.dumps({'error': {'message': 'Please set an Auth method in settings.json'}}))\n"
        "sys.exit(41)\n",
        encoding="utf-8",
    )
    preset = LocalCliPreset(
        preset_id=GEMINI_CLI_BACKEND_ID,
        executable=sys.executable,
        argv=(str(script), *GEMINI_CLI_PRESET.argv),
        display_name="Mock Gemini CLI",
        extractor=GEMINI_CLI_PRESET.extractor,
        contract_args=GEMINI_CLI_PRESET.contract_args,
    )
    backend = LocalCliGenerationBackend(_cli_config(), preset=preset)

    with pytest.raises(GenerationError) as exc_info:
        backend.generate("prompt", {})

    assert exc_info.value.error_code is GenerationErrorCode.LOGIN_REQUIRED
    assert exc_info.value.fallbackable is True


# ------------------------------------------------------------ chain resolution
def _chain_config(primary: str, fallback):
    return SimpleNamespace(generation_backend=primary, generation_fallback_backend=fallback)


def test_parse_chain_keeps_order_and_dedupes() -> None:
    assert parse_generation_fallback_chain(None) == ("litellm",)
    assert parse_generation_fallback_chain("") == ()
    assert parse_generation_fallback_chain(" Gemini_CLI, codex_cli ,,litellm,gemini_cli") == (
        "gemini_cli",
        "codex_cli",
        "litellm",
    )


def test_resolve_chain_skips_primary_and_validates_entries() -> None:
    config = _chain_config("claude_code_cli", "claude_code_cli,gemini_cli,codex_cli,litellm")
    assert resolve_generation_fallback_backend_ids(config) == ("gemini_cli", "codex_cli", "litellm")
    assert resolve_generation_fallback_backend_id(config) == "gemini_cli"
    assert resolve_generation_fallback_backend_ids(_chain_config("litellm", "litellm")) == ()
    assert resolve_generation_fallback_backend_ids(_chain_config("claude_code_cli", "")) == ()
    assert set(SUPPORTED_GENERATION_FALLBACK_BACKENDS) >= {"litellm", "gemini_cli", "codex_cli"}

    with pytest.raises(GenerationError) as exc_info:
        resolve_generation_fallback_backend_ids(_chain_config("claude_code_cli", "gemini_cli,grok_cli"))
    assert exc_info.value.details["requested_backend"] == "grok_cli"


def test_config_validation_accepts_chain_and_reports_unknown_items() -> None:
    from tests.test_config_validate_structured import _make_config

    def _issues(fallback: str):
        cfg = _make_config(generation_backend="claude_code_cli", generation_fallback_backend=fallback)
        return [i for i in cfg.validate_structured() if i.field == "GENERATION_FALLBACK_BACKEND"]

    assert _issues("gemini_cli,codex_cli,litellm") == []
    assert _issues("claude_code_cli,litellm") == []
    bad = _issues("gemini_cli,grok_cli")
    assert len(bad) == 1
    assert bad[0].severity == "error"
    assert "grok_cli" in bad[0].message


# ------------------------------------------------------------- analyzer chain
def _analyzer(primary: str, fallback: str, *, litellm_available: bool = True):
    from src.analyzer import GeminiAnalyzer

    cfg = MagicMock()
    cfg.litellm_model = "gemini/gemini-2.5-flash"
    cfg.litellm_fallback_models = []
    cfg.llm_model_list = []
    cfg.generation_backend = primary
    cfg.generation_fallback_backend = fallback
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer._router = None
    analyzer._litellm_available = litellm_available
    analyzer._config_override = cfg
    return analyzer


def _failing_backend(backend_id: str, *, fallbackable: bool = True) -> MagicMock:
    backend = MagicMock()
    backend.generate.side_effect = GenerationError(
        error_code=GenerationErrorCode.LOGIN_REQUIRED,
        stage="execution",
        retryable=False,
        fallbackable=fallbackable,
        backend=backend_id,
        provider=backend_id,
        details={"reason": f"{backend_id}_down"},
    )
    backend.get_config_error.return_value = None
    return backend


def _ok_backend(text: str) -> MagicMock:
    backend = MagicMock()
    backend.generate.return_value = SimpleNamespace(text=text, model=text, usage={})
    backend.get_config_error.return_value = None
    return backend


def test_chain_tries_each_fallback_in_order_until_success() -> None:
    analyzer = _analyzer("claude_code_cli", "gemini_cli,codex_cli,litellm")
    backends = {
        "claude_code_cli": _failing_backend("claude_code_cli"),
        "gemini_cli": _failing_backend("gemini_cli"),
        "codex_cli": _ok_backend("codex-answer"),
        "litellm": _ok_backend("litellm-answer"),
    }

    with patch.object(analyzer, "_get_generation_backend", side_effect=backends.__getitem__):
        text, model, _usage = analyzer._call_litellm("prompt", {"max_tokens": 64})

    assert text == "codex-answer"
    backends["gemini_cli"].generate.assert_called_once()
    backends["litellm"].generate.assert_not_called()


def test_chain_reports_last_failure_with_attempted_fallbacks() -> None:
    analyzer = _analyzer("claude_code_cli", "gemini_cli,codex_cli")
    backends = {
        "claude_code_cli": _failing_backend("claude_code_cli"),
        "gemini_cli": _failing_backend("gemini_cli"),
        "codex_cli": _failing_backend("codex_cli"),
    }

    with patch.object(analyzer, "_get_generation_backend", side_effect=backends.__getitem__):
        with pytest.raises(GenerationError) as exc_info:
            analyzer._call_litellm("prompt", {"max_tokens": 64})

    error = exc_info.value
    assert error.stage == "fallback"
    assert error.backend == "codex_cli"
    assert error.details["primary_error"]["backend"] == "claude_code_cli"
    assert error.details["fallback_error"]["backend"] == "codex_cli"
    assert [item["backend"] for item in error.details["attempted_fallbacks"]] == ["gemini_cli", "codex_cli"]


def test_non_fallbackable_fallback_error_stops_the_chain() -> None:
    analyzer = _analyzer("claude_code_cli", "gemini_cli,litellm")
    backends = {
        "claude_code_cli": _failing_backend("claude_code_cli"),
        "gemini_cli": _failing_backend("gemini_cli", fallbackable=False),
        "litellm": _ok_backend("litellm-answer"),
    }

    with patch.object(analyzer, "_get_generation_backend", side_effect=backends.__getitem__):
        with pytest.raises(GenerationError) as exc_info:
            analyzer._call_litellm("prompt", {"max_tokens": 64})

    assert exc_info.value.backend == "gemini_cli"
    backends["litellm"].generate.assert_not_called()


def test_cli_only_chain_counts_as_usable_fallback_without_api_keys() -> None:
    analyzer = _analyzer("claude_code_cli", "gemini_cli", litellm_available=False)
    primary_error = GenerationError(
        error_code=GenerationErrorCode.COMMAND_NOT_FOUND,
        stage="configuration",
        retryable=False,
        fallbackable=True,
        backend="claude_code_cli",
        provider="claude_code_cli",
        details={},
    )
    available = _ok_backend("x")
    missing = _ok_backend("x")
    missing.get_config_error.return_value = primary_error

    with patch.object(analyzer, "_get_generation_backend", return_value=available):
        assert analyzer._can_use_generation_fallback(primary_error) is True
    with patch.object(analyzer, "_get_generation_backend", return_value=missing):
        assert analyzer._can_use_generation_fallback(primary_error) is False


def test_status_service_lists_full_chain() -> None:
    from src.services.generation_backend_status_service import GenerationBackendStatusService

    service = GenerationBackendStatusService(
        effective_map={
            "GENERATION_BACKEND": "claude_code_cli",
            "GENERATION_FALLBACK_BACKEND": "gemini_cli,codex_cli,litellm",
        }
    )
    status = service.get_status()

    assert status["fallback_backend_id"] == "gemini_cli"
    assert status["fallback_backend_ids"] == ["gemini_cli", "codex_cli", "litellm"]
    assert [item["backend_id"] for item in status["backends"]] == [
        "claude_code_cli",
        "gemini_cli",
        "codex_cli",
        "litellm",
    ]
    assert status["backends"][1]["fallback_target"] == "codex_cli"
    assert status["backends"][-1]["fallback_target"] is None
