# ADR-0001: Fail-Closed Hybrid Signal Reliability Gate

- **Status:** Accepted
- **Date:** 2026-11-25
- **Scope:** `src/services/signal_reliability_gate.py`, `src/services/decision_signal_extractor.py`, `src/config.py`

## Context
AI-generated trading decisions (`DecisionSignal` extracted from `AgentOrchestrator` / LLM pipeline outputs) can still emit `buy` or `add` actions even when:
1. The `risk` pipeline stage degraded or timed out,
2. Intraday quote context is missing or stale,
3. Price plan targets (`stop_loss`, `take_profit`, `ideal_buy`) are missing or offer `< 1.5` reward-to-risk ratio, or
4. Deterministic technical trend/bias conflicts with a bullish entry.

## Decision
Introduce a deterministic, side-effect-free `apply_signal_reliability_gate()` post-processor behind `SIGNAL_RELIABILITY_GATE_ENABLED` (`Config.signal_reliability_gate_enabled`, default `False` for backward-compatible rollout). When active (either explicitly via parameter or config), `buy`/`add` actions that violate any of the reliability checks are downgraded fail-closed to `watch`, and a sanitized `diagnostic_summary` (via `run_diagnostics.sanitize_diagnostic_metadata`) is attached to `metadata`.

## Consequences
- **Positive:** Prevents silent fallback/degraded runs or incomplete price plans from emitting actionable entry signals without altering frozen strategy cores (`library.py`, `research_v3.py`).
- **Negative / Trade-off:** Strict fail-closed gating increases `watch` rate when live intraday feeds or full sniper-point plans are unavailable, requiring opt-in activation (`SIGNAL_RELIABILITY_GATE_ENABLED=true`) in production profiles until data feeds meet completeness SLAs.
