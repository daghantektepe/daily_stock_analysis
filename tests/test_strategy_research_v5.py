# -*- coding: utf-8 -*-
"""Strategy Research v5: correlation-aware (Min-Corr) sizing vs naive 1/vol control."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd

from src.quant.research_v5_lab import (
    _compare_mincorr_vs_control,
    concentration_diagnostics,
    run_strategy_research_v5,
)
from src.quant.strategies.research_v5 import (
    MACRO_V5_UNIVERSE,
    V5_RISK_ASSETS,
    build_v5_research_candidates,
    compute_v5_invvol_trend_control_weights,
    compute_v5_mincorr_trend_weights,
)


def _prices(periods: int = 1600, seed: int = 7) -> pd.DataFrame:
    """Synthetic macro universe where equities (SPY/QQQ/EFA/EEM/VNQ) share a common factor
    while diversifiers (TLT/IEF/GLD/DBC/UUP) are independent."""
    dates = pd.bdate_range("2007-01-02", periods=periods)
    rng = np.random.default_rng(seed)
    data = {"BIL": 100.0 * np.cumprod(np.full(periods, 1.0 + 0.015 / 252.0))}
    common_eq = 0.0005 + rng.normal(0.0, 0.011, periods)
    for sym in ("SPY", "QQQ", "EFA", "EEM", "VNQ"):
        rets = 0.85 * common_eq + rng.normal(0.0, 0.003, periods)
        data[sym] = 100.0 * np.cumprod(1.0 + rets)
    for idx, sym in enumerate(("TLT", "IEF", "GLD", "DBC", "UUP")):
        rets = 0.00045 + rng.normal(0.0, 0.009, periods)
        data[sym] = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame(data, index=dates)


def test_v5_module_is_isolated_from_frozen_library_and_preserves_fingerprints() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "quant" / "strategies" / "research_v5.py"
    for node in ast.walk(ast.parse(src.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "library" not in node.module
    assert set(MACRO_V5_UNIVERSE) == set(V5_RISK_ASSETS) | {"BIL"}

    from src.quant.forward_validation import _book_settings, strategy_fingerprint
    from src.quant.paper_book import build_quant_paper_book

    expected = {"paa": "87e22a6b3559", "meta_a": "37a7ab36a0d9", "v3_trp": "ae4754108564"}
    for key, sha in expected.items():
        book, fn = build_quant_paper_book(key, book_dir=None, initial_capital=10000.0, cost_bps=5.0, rebalance_mode="monthly")
        assert strategy_fingerprint(fn, _book_settings(book))["sha256"][:12] == sha


def test_mincorr_downweights_collinear_equity_cluster_relative_to_control() -> None:
    prices = _prices()
    w_mc = compute_v5_mincorr_trend_weights(prices)
    w_ctrl = compute_v5_invvol_trend_control_weights(prices)

    assert float(w_mc.min().min()) >= 0.0
    active_mc = w_mc.iloc[300:]
    assert np.allclose(active_mc.sum(axis=1), 1.0, atol=1e-6)

    diag_mc = concentration_diagnostics(w_mc)
    diag_ctrl = concentration_diagnostics(w_ctrl)
    assert diag_mc["available"] is True and diag_ctrl["available"] is True
    # Because SPY/QQQ/EFA/EEM/VNQ are ~0.95 correlated in _prices(), Min-Corr must give a lower
    # share of active risk to the equity cluster and a higher share to orthogonal diversifiers.
    assert diag_mc["equity_cluster_share_of_risk_pct"] < diag_ctrl["equity_cluster_share_of_risk_pct"]
    assert diag_mc["diversifier_cluster_share_of_risk_pct"] > diag_ctrl["diversifier_cluster_share_of_risk_pct"]


def test_v5_zero_lookahead() -> None:
    prices = _prices()
    cut = 1100
    shocked = prices.copy()
    shocked.iloc[cut + 1 :] *= 2.5
    base = compute_v5_mincorr_trend_weights(prices.iloc[: cut + 1])
    alt = compute_v5_mincorr_trend_weights(shocked.iloc[: cut + 1])
    pd.testing.assert_frame_equal(base, alt)


def test_v5_lab_runs_offline_and_increments_cumulative_trials_to_32(tmp_path: Path) -> None:
    prices = _prices(periods=4900, seed=19)
    meta_ref = prices["SPY"].pct_change().fillna(0.0) * 0.4
    payload = run_strategy_research_v5(
        prices=prices,
        meta_a_returns=meta_ref,
        run_plateau=False,
        json_path=tmp_path / "v5.json",
        report_path=tmp_path / "v5.md",
    )
    ids = [c["strategy_id"] for c in payload["candidates"]]
    assert ids == [c.spec.strategy_id for c in build_v5_research_candidates()]
    assert payload["cumulative_trials_n"] == 32  # 25 tournament + 3 v3 + 2 v4 + 2 v5
    assert "mincorr_adds_value" in payload["mincorr_vs_control"]
    assert (tmp_path / "v5.json").is_file()
    text = (tmp_path / "v5.md").read_text(encoding="utf-8")
    assert "Min-Corr ağırlıklandırma 1/vol kontrol grubuna göre değer katıyor mu?" in text

    cmp_fail = _compare_mincorr_vs_control(
        {
            "verdict": "PROMOTE_TO_FORWARD_PAPER",
            "full_2008_plus": {"cagr_pct": 5.0, "max_drawdown_pct": -7.0},
            "cost_stress": {"5bps": {"excess_sharpe": 0.62}, "25bps": {"excess_sharpe": 0.48}},
            "calendar_years": {"yearly": {"2008": {"return_pct": 4.0}, "2022": {"return_pct": 1.0}}},
        },
        {
            "verdict": "PROMOTE_TO_FORWARD_PAPER",
            "full_2008_plus": {"cagr_pct": 4.8, "max_drawdown_pct": -7.5},
            "cost_stress": {"5bps": {"excess_sharpe": 0.60}, "25bps": {"excess_sharpe": 0.46}},
            "calendar_years": {"yearly": {"2008": {"return_pct": 3.5}, "2022": {"return_pct": 0.8}}},
        },
    )
    assert cmp_fail["mincorr_adds_value"] is False  # +0.02 edge < required +0.05
