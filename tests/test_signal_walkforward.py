# -*- coding: utf-8 -*-
"""Offline unit tests for Signal Walk-Forward & 80% Acceptance Gate (REQ-05 & REQ-06)."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd

from src.quant.signal_walkforward import (
    SignalAcceptanceGate,
    generate_causal_signal_trades,
    run_signal_walkforward,
    summarize_walkforward_trades,
)


def _synthetic_universe(periods: int = 2200, seed: int = 42) -> pd.DataFrame:
    dates = pd.bdate_range("2017-01-02", periods=periods)
    rng = np.random.default_rng(seed)
    spy_rets = 0.00045 + rng.normal(0.0, 0.009, periods)
    data = {"SPY": 100.0 * np.cumprod(1.0 + spy_rets)}
    for sym in ("AAPL", "MSFT", "NVDA", "GLD"):
        rets = 0.00055 + rng.normal(0.0, 0.012, periods)
        data[sym] = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame(data, index=dates)


def test_signal_walkforward_isolated_and_zero_lookahead(tmp_path: Path) -> None:
    """REQ-06 & causality: isolated from frozen library.py and zero future-bar leakage."""
    src_path = Path(__file__).resolve().parents[1] / "src" / "quant" / "signal_walkforward.py"
    for node in ast.walk(ast.parse(src_path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "library" not in node.module
            assert "research_v3" not in node.module

    prices = _synthetic_universe()
    cut = 1200
    base = generate_causal_signal_trades(prices.iloc[: cut + 1])
    shocked = prices.copy()
    shocked.iloc[cut + 1 :] *= 0.25
    alt = generate_causal_signal_trades(shocked.iloc[: cut + 1])
    assert base == alt

    payload = run_signal_walkforward(
        prices=prices,
        json_path=tmp_path / "wf.json",
        report_path=tmp_path / "wf.md",
    )
    assert "out_of_sample" in payload and "in_sample" in payload
    assert (tmp_path / "wf.json").is_file()
    assert (tmp_path / "wf.md").is_file()


def test_80pct_acceptance_gate_requires_sample_ci_pf_and_dd() -> None:
    """REQ-05: verdict stays INSUFFICIENT_SAMPLE (<30) or UNPROVEN unless ALL thresholds pass."""
    gate = SignalAcceptanceGate()

    # 1. Sample size < 30 -> INSUFFICIENT_SAMPLE
    small = [
        {"signal_date": "2024-01-02", "net_return_pct": 5.0, "excess_return_pct": 2.0, "beat_benchmark": True, "outcome": "hit"}
        for _ in range(15)
    ]
    assert summarize_walkforward_trades(small, gate=gate)["verdict"] == "INSUFFICIENT_SAMPLE"

    # 2. High precision (82%) but weak net profit factor (1.1 < 1.50) -> UNPROVEN
    weak_pf_trades = [
        {"signal_date": f"2024-02-{(i % 28) + 1:02d}", "net_return_pct": 2.2, "excess_return_pct": 1.0, "beat_benchmark": True, "outcome": "hit"}
        for i in range(25)
    ] + [
        {"signal_date": f"2024-03-{(i % 28) + 1:02d}", "net_return_pct": -10.0, "excess_return_pct": -11.0, "beat_benchmark": False, "outcome": "miss"}
        for i in range(5)
    ]
    res_weak = summarize_walkforward_trades(weak_pf_trades, gate=gate)
    assert res_weak["precision_10d_pct"] > 80.0
    assert res_weak["verdict"] == "UNPROVEN"
    assert any("profit_factor_net" in c for c in res_weak["failed_checks"])

    # 3. All criteria met (27 hits, 3 small misses -> 90% precision, strong CI90, high PF, low DD) -> PROVEN
    strong_trades = [
        {"signal_date": f"2024-04-{(i % 28) + 1:02d}", "net_return_pct": 4.5, "excess_return_pct": 2.5, "beat_benchmark": True, "outcome": "hit"}
        for i in range(27)
    ] + [
        {"signal_date": f"2024-05-0{i + 1}", "net_return_pct": -2.5, "excess_return_pct": -1.5, "beat_benchmark": False, "outcome": "miss"}
        for i in range(3)
    ]
    res_strong = summarize_walkforward_trades(strong_trades, gate=gate)
    assert res_strong["verdict"] == "PROVEN"
    assert res_strong["failed_checks"] == []
