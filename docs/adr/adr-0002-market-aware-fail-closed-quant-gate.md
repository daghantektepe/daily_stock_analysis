# ADR-0002: Market-Aware Benchmark Separation and Fail-Closed Quant Gate

- **Status:** Accepted
- **Date:** 2026-11-25
- **Scope:** `src/services/quant_risk_gate.py`, `src/quant/signal_walkforward.py`

## Context
`evaluate_entry_risk_gate()` in `src/services/quant_risk_gate.py` previously:
1. Hardcoded US `SPY` / `^VIX` regime checks even for BIST (`*.IS`) equities, causing cross-market regime mismatches.
2. Logged `quant_score_unavailable_fail_open` and allowed `buy` entries when `quant_gate_enabled=True` but historical bars in SQLite were missing or insufficient.

## Decision
1. Route BIST (`*.IS`) symbols to `XU100.IS` (suppressing US-only `^VIX` threshold dependency when evaluating BIST) while keeping `SPY` + `^VIX` for US/non-BIST symbols via `_benchmark_symbol_for_stock()`.
2. Fail closed (`blocked=True`, reason `quant_score_unavailable_fail_closed`) whenever `quant_gate_enabled=True` and a valid quant score cannot be computed from stored bars.
3. Isolate AI-signal precision evaluation in a separate module (`src/quant/signal_walkforward.py`) enforcing strict walk-forward OOS validation (`N >= 30`, `precision_10d >= 80%`, Wilson 90% lower bound `> 65%`, benchmark-beat 90% lower bound `> 50%`, `PF_net >= 1.50`, `MaxDD >= -12%`).

## Consequences
- **Positive:** Eliminates silent fail-open bypasses in the quantitative risk gate and separates BIST vs US benchmark semantics without modifying frozen quantitative strategy files (`src/quant/strategies/library.py`, `src/quant/strategies/research_v3.py`).
- **Negative / Trade-off:** Requires local daily bars for both the target ticker and its market benchmark (`XU100.IS` or `SPY`) before `quant_gate_enabled=True` permits entries.
