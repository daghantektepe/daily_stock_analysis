# -*- coding: utf-8 -*-
"""Hybrid fail-closed signal reliability gate and run-diagnostic summarizer.

Prevents directional BUY/ADD signals from passing downstream when critical safety
conditions are violated:
1. ``RiskAgent`` stage failed, timed out, was skipped, or issued ``veto_buy``;
2. Intraday quote / core context data is explicitly stale or unavailable;
3. Risk plan is incomplete (missing ``stop_loss`` / ``target_price``) or
   ``reward_risk_ratio < min_reward_risk`` (default ``1.5``);
4. Deterministic technical structure explicitly contradicts entry (``is_bullish``
   is ``False`` or ``bias_ma5 > 5.0%`` chasing guardrail).

When triggered, directional entries are downgraded to ``watch`` with an explicit
``metadata["reliability_gate"]`` audit trail (zero prompt mutation, zero schema
changes, reversible via ``SIGNAL_RELIABILITY_GATE_ENABLED``).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Optional

from src.schemas.decision_action import build_action_fields
from src.services.run_diagnostics import sanitize_diagnostic_metadata

_ENTRY_ACTIONS = frozenset({"buy", "add"})
_INTRADAY_PHASES = frozenset({"intraday", "lunch_break", "closing_auction"})
_DEGRADED_DATA_STATUSES = frozenset({"unavailable", "failed"})
_BEARISH_TREND_TOKENS = ("bear", "空头", "düşüş", "下跌")


@dataclass(frozen=True)
class SignalReliabilityDecision:
    passed: bool
    original_action: str
    final_action: str
    reasons: List[str]
    reward_risk_ratio: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _finite_pos(value: Any) -> Optional[float]:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if (math.isfinite(num) and num > 0.0) else None


def summarize_run_diagnostics_for_signal(snapshot: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Build a compact, redacted diagnostic summary for DecisionSignal metadata."""
    if not isinstance(snapshot, Mapping) or not snapshot:
        return None
    provider_runs = snapshot.get("provider_runs") if isinstance(snapshot.get("provider_runs"), list) else []
    llm_runs = snapshot.get("llm_runs") if isinstance(snapshot.get("llm_runs"), list) else []

    failed_providers = [
        {
            "provider": r.get("provider"),
            "data_type": r.get("data_type"),
            "error_type": r.get("error_type"),
        }
        for r in provider_runs
        if isinstance(r, Mapping) and r.get("success") is False
    ]
    stale_quotes = sum(
        1
        for r in provider_runs
        if isinstance(r, Mapping) and (r.get("stale_seconds") or 0) > 0 and r.get("data_type") == "realtime_quote"
    )
    failed_llm = sum(1 for r in llm_runs if isinstance(r, Mapping) and r.get("success") is False)
    summary = {
        "trace_id": snapshot.get("trace_id"),
        "provider_total": len(provider_runs),
        "provider_failures": len(failed_providers),
        "failed_provider_samples": failed_providers[:5],
        "stale_quote_runs": stale_quotes,
        "llm_total": len(llm_runs),
        "llm_failures": failed_llm,
    }
    sanitized = sanitize_diagnostic_metadata(summary)
    return sanitized if isinstance(sanitized, dict) and sanitized else None


def _has_degraded_risk_or_termination(
    result: Any,
    context_snapshot: Optional[Mapping[str, Any]],
) -> Optional[str]:
    dashboard = _as_dict(getattr(result, "dashboard", None))
    explanation = _as_dict(dashboard.get("agent_disagreement_explanation"))
    if explanation.get("pipeline_termination"):
        return "pipeline_timeout_before_completion"

    risk_control = _as_dict(explanation.get("risk_control"))
    if risk_control.get("veto_buy") is True:
        return "risk_agent_veto_buy"

    for ev in explanation.get("degraded_events") or []:
        if isinstance(ev, Mapping) and str(ev.get("stage") or "").strip().lower() == "risk":
            return f"risk_stage_degraded:{ev.get('reason') or 'failed'}"

    snap = _as_dict(context_snapshot)
    diag_snap = _as_dict(getattr(result, "diagnostic_context_snapshot", None))
    for source in (snap, diag_snap):
        for st in source.get("degraded_stages") or []:
            if isinstance(st, Mapping) and str(st.get("stage_name") or "").strip().lower() == "risk":
                return "risk_stage_degraded"
    return None


def _has_stale_or_unavailable_data(
    payload: Mapping[str, Any],
    context_snapshot: Optional[Mapping[str, Any]],
) -> Optional[str]:
    dq = _as_dict(payload.get("data_quality_summary"))
    level = str(dq.get("level") or dq.get("overall_status") or dq.get("status") or "").strip().lower()
    if level in _DEGRADED_DATA_STATUSES:
        return f"data_quality_{level}"

    snap = _as_dict(context_snapshot)
    phase = str(payload.get("market_phase") or "").strip().lower()
    rt = _as_dict(snap.get("realtime_quote"))
    if rt and phase in _INTRADAY_PHASES:
        if rt.get("is_stale") is True:
            return "realtime_quote_stale_intraday"
        rt_dq = str(rt.get("data_quality") or "").strip().lower()
        if rt_dq in _DEGRADED_DATA_STATUSES:
            return f"realtime_quote_{rt_dq}"
    return None


def _has_contradicting_trend(
    result: Any,
    context_snapshot: Optional[Mapping[str, Any]],
) -> Optional[str]:
    dashboard = _as_dict(getattr(result, "dashboard", None))
    dp = _as_dict(dashboard.get("data_perspective"))
    trend_status = _as_dict(dp.get("trend_status"))
    price_pos = _as_dict(dp.get("price_position"))
    snap = _as_dict(context_snapshot)
    trend_snap = _as_dict(snap.get("trend_result"))

    is_bullish = trend_status.get("is_bullish")
    if is_bullish is False:
        return "trend_not_bullish"

    raw_trend = str(
        trend_status.get("ma_alignment") or trend_snap.get("trend_status") or ""
    ).strip().lower()
    if any(tok in raw_trend for tok in _BEARISH_TREND_TOKENS):
        return f"bearish_trend:{raw_trend[:32]}"

    bias_raw = price_pos.get("bias_ma5")
    if bias_raw is None:
        bias_raw = trend_snap.get("bias_ma5")
    try:
        if bias_raw is not None and isinstance(bias_raw, (int, float)) and float(bias_raw) > 5.0:
            return f"bias_ma5_chasing_guard:{float(bias_raw):.2f}%"
    except (TypeError, ValueError):
        pass
    return None


def _resolve_reference_price(
    payload: Mapping[str, Any],
    result: Any,
    context_snapshot: Optional[Mapping[str, Any]],
) -> Optional[float]:
    evidence = _as_dict(payload.get("evidence"))
    snap = _as_dict(context_snapshot)
    rt = _as_dict(snap.get("realtime_quote"))
    daily = _as_dict(snap.get("daily"))
    for candidate in (
        evidence.get("current_price"),
        getattr(result, "current_price", None),
        rt.get("price"),
        daily.get("close"),
        daily.get("last_close"),
    ):
        val = _finite_pos(candidate)
        if val is not None:
            return val
    return None


def _has_scale_mismatch(
    payload: Mapping[str, Any],
    reference_price: Optional[float],
    *,
    min_ratio: float = 0.25,
    max_ratio: float = 4.0,
) -> Optional[str]:
    """Detect wildly mis-scaled price levels (e.g. x100 decimal-comma slippage)."""
    if reference_price is None or reference_price <= 0:
        return None
    for field_name in ("entry_low", "entry_high", "stop_loss", "target_price"):
        val = _finite_pos(payload.get(field_name))
        if val is None:
            continue
        ratio = val / reference_price
        if ratio > max_ratio or ratio < min_ratio:
            return f"price_plan_scale_mismatch:{field_name}={val:.4g}_vs_ref={reference_price:.4g}"
    return None


def evaluate_signal_reliability(
    payload: Mapping[str, Any],
    *,
    result: Any = None,
    context_snapshot: Optional[Mapping[str, Any]] = None,
    min_reward_risk: float = 1.5,
) -> SignalReliabilityDecision:
    """Evaluate reliability gates for directional entry signals (``buy`` / ``add``)."""
    action = str(payload.get("action") or "").strip().lower()
    if action not in _ENTRY_ACTIONS:
        return SignalReliabilityDecision(
            passed=True,
            original_action=action,
            final_action=action,
            reasons=[],
        )

    reasons: List[str] = []
    risk_reason = _has_degraded_risk_or_termination(result, context_snapshot)
    if risk_reason:
        reasons.append(risk_reason)

    data_reason = _has_stale_or_unavailable_data(payload, context_snapshot)
    if data_reason:
        reasons.append(data_reason)

    trend_reason = _has_contradicting_trend(result, context_snapshot)
    if trend_reason:
        reasons.append(trend_reason)

    reference_price = _resolve_reference_price(payload, result, context_snapshot)
    scale_reason = _has_scale_mismatch(payload, reference_price)
    if scale_reason:
        reasons.append(scale_reason)

    stop_loss = _finite_pos(payload.get("stop_loss"))
    target_price = _finite_pos(payload.get("target_price"))
    entry_ref = (
        _finite_pos(payload.get("entry_low"))
        or _finite_pos(payload.get("entry_high"))
        or _finite_pos(_as_dict(payload.get("evidence")).get("current_price"))
        or _finite_pos(getattr(result, "current_price", None))
    )
    rr_ratio: Optional[float] = None
    if stop_loss is None or target_price is None:
        reasons.append("incomplete_price_plan")
    elif entry_ref is not None:
        if stop_loss >= entry_ref or target_price <= entry_ref:
            reasons.append("invalid_stop_or_target_levels")
        else:
            rr_ratio = round((target_price - entry_ref) / (entry_ref - stop_loss), 3)
            if rr_ratio < float(min_reward_risk):
                reasons.append(f"reward_risk_below_min:{rr_ratio:.2f}<{float(min_reward_risk):.2f}")

    passed = len(reasons) == 0
    return SignalReliabilityDecision(
        passed=passed,
        original_action=action,
        final_action=action if passed else "watch",
        reasons=reasons,
        reward_risk_ratio=rr_ratio,
    )


def apply_signal_reliability_gate(
    payload: Dict[str, Any],
    *,
    result: Any = None,
    context_snapshot: Optional[Mapping[str, Any]] = None,
    min_reward_risk: float = 1.5,
    enabled: bool = True,
) -> Dict[str, Any]:
    """Enforce fail-closed reliability gate on a DecisionSignal payload."""
    decision = evaluate_signal_reliability(
        payload,
        result=result,
        context_snapshot=context_snapshot,
        min_reward_risk=min_reward_risk,
    )
    meta = dict(payload.get("metadata") or {})
    meta["reliability_gate"] = decision.to_dict()
    updated = dict(payload)
    updated["metadata"] = meta

    if enabled and not decision.passed and decision.final_action != decision.original_action:
        watch_fields = build_action_fields(
            operation_advice="watch",
            explicit_action="watch",
            report_type=str(meta.get("report_type") or "simple"),
            report_language=updated.get("report_language"),
            sentiment_score=updated.get("score"),
            guardrail_reason="; ".join(decision.reasons),
            align_with_score=False,
        )
        updated["action"] = "watch"
        if watch_fields.get("action_label"):
            updated["action_label"] = watch_fields["action_label"]
        meta["raw_action"] = meta.get("raw_action") or decision.original_action
        meta["final_action"] = "watch"
        meta["guardrail_reason"] = "; ".join(decision.reasons)
    return updated
