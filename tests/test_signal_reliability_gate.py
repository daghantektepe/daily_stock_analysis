# -*- coding: utf-8 -*-
"""Spec-Kit verification tests for the fail-closed AI signal reliability gate."""

from __future__ import annotations

from types import SimpleNamespace

from src.services.decision_signal_extractor import build_decision_signal_payload_from_report
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    record_provider_run,
    reset_run_diagnostic_context,
)
from src.services.signal_reliability_gate import apply_signal_reliability_gate


def _strong_result(**overrides):
    res = SimpleNamespace(
        code="THYAO.IS",
        name="Türk Hava Yolları",
        sentiment_score=82,
        trend_prediction="Yükseliş",
        operation_advice="buy",
        decision_type="buy",
        confidence_level="high",
        report_language="tr",
        action="buy",
        current_price=300.0,
        analysis_summary="Güçlü teknik kırılım",
        buy_reason="Hacim onaylı",
        key_points=["MA üzerinde"],
        risk_warning="Stop altı çıkış",
        dashboard={
            "battle_plan": {
                "sniper_points": {
                    "ideal_buy": "300",
                    "stop_loss": "280",
                    "take_profit": "340",  # R/R = 40 / 20 = 2.0 >= 1.5
                }
            },
            "data_perspective": {
                "trend_status": {"ma_alignment": "bullish", "is_bullish": True},
                "price_position": {"bias_ma5": 1.8},
            },
            "agent_disagreement_explanation": {
                "degraded_events": [],
                "risk_control": {"veto_buy": False},
            },
        },
        success=True,
    )
    for k, v in overrides.items():
        setattr(res, k, v)
    return res


def test_degraded_risk_stage_vetoes_buy_to_watch() -> None:
    """REQ-01: degraded/skipped RiskAgent forces directional BUY -> WATCH."""
    res = _strong_result()
    res.dashboard["agent_disagreement_explanation"]["degraded_events"] = [
        {"stage": "risk", "reason": "budget_skip", "boundary": "before_stage"}
    ]
    payload = build_decision_signal_payload_from_report(
        res,
        trace_id="trace-risk-degraded",
        query_source="api",
        report_type="full",
        profile_source="auto_default",
        reliability_gate_enabled=True,
    )
    assert payload is not None
    assert payload["action"] == "watch"
    gate = payload["metadata"]["reliability_gate"]
    assert gate["passed"] is False
    assert gate["original_action"] == "buy"
    assert "risk_stage_degraded:budget_skip" in gate["reasons"]


def test_incomplete_stop_or_low_rr_downgrades_buy() -> None:
    """REQ-02: missing stop/target or R/R < 1.5 downgrades BUY -> WATCH."""
    res_missing = _strong_result()
    res_missing.dashboard["battle_plan"]["sniper_points"] = {"ideal_buy": "300"}
    p_missing = build_decision_signal_payload_from_report(
        res_missing,
        trace_id="trace-no-plan",
        query_source="api",
        report_type="full",
        profile_source="auto_default",
        reliability_gate_enabled=True,
    )
    assert p_missing is not None
    assert p_missing["action"] == "watch"
    assert "incomplete_price_plan" in p_missing["metadata"]["reliability_gate"]["reasons"]

    res_low_rr = _strong_result()
    res_low_rr.dashboard["battle_plan"]["sniper_points"] = {
        "ideal_buy": "300",
        "stop_loss": "270",     # risk = 30
        "take_profit": "330",   # reward = 30 -> R/R = 1.0 < 1.5
    }
    p_low = build_decision_signal_payload_from_report(
        res_low_rr,
        trace_id="trace-low-rr",
        query_source="api",
        report_type="full",
        profile_source="auto_default",
        reliability_gate_enabled=True,
    )
    assert p_low is not None
    assert p_low["action"] == "watch"
    assert any(r.startswith("reward_risk_below_min") for r in p_low["metadata"]["reliability_gate"]["reasons"])


def test_stale_intraday_quote_and_healthy_signal_with_diagnostics() -> None:
    """Healthy setup passes with diagnostic_summary attached; stale intraday quote blocks BUY."""
    token = activate_run_diagnostic_context(trace_id="trace-diag-01", stock_code="THYAO.IS")
    try:
        record_provider_run(
            data_type="realtime_quote",
            provider="yfinance",
            operation="quote",
            success=False,
            error_type="TimeoutError",
        )
        ok_payload = build_decision_signal_payload_from_report(
            _strong_result(),
            context_snapshot={"market_phase_summary": {"phase": "postmarket"}},
            trace_id="trace-diag-01",
            query_source="api",
            report_type="full",
            profile_source="auto_default",
            reliability_gate_enabled=True,
        )
        assert ok_payload is not None
        assert ok_payload["action"] == "buy"
        assert ok_payload["metadata"]["reliability_gate"]["passed"] is True
        diag = ok_payload["metadata"]["diagnostic_summary"]
        assert diag["provider_failures"] == 1
        assert diag["trace_id"] == "trace-diag-01"
    finally:
        reset_run_diagnostic_context(token)

    stale_payload = apply_signal_reliability_gate(
        {"action": "buy", "market_phase": "intraday", "entry_low": 300.0, "stop_loss": 280.0, "target_price": 340.0},
        context_snapshot={"realtime_quote": {"is_stale": True, "data_quality": "partial"}},
        enabled=True,
    )
    assert stale_payload["action"] == "watch"
    assert "realtime_quote_stale_intraday" in stale_payload["metadata"]["reliability_gate"]["reasons"]
