# -*- coding: utf-8 -*-
"""Empirical quant engine invariants: zero lookahead, cost deduction, DSR, PAA crash-shield, MCP."""

from __future__ import annotations

import json
import numpy as np
import pandas as pd

from src.mcp.server import DsaMcpServer
from src.quant.portfolio import build_meta_portfolios
from src.quant.stats import (
    classify_strategy_verdict,
    compute_performance_metrics,
    deflated_sharpe_ratio,
)
from src.quant.strategies.engine import StrategySpec, backtest_weight_matrix
from src.quant.strategies.library import (
    build_base_strategy_specs,
    compute_paa_weights,
    run_all_base_strategies,
)


def _synthetic_etf_prices(n_days: int = 420, *, crash_tail: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2021-01-04", periods=n_days)
    risk_cols = ["SPY", "QQQ", "IWM", "VGK", "EWJ", "EEM", "VNQ", "GLD", "DBC", "HYG", "LQD", "TLT"]
    safe_cols = ["IEF", "SHY", "BIL"]
    data = {}
    for col in risk_cols:
        rets = rng.normal(0.0005, 0.011, size=n_days)
        if crash_tail:
            rets[-60:] = -0.012
        data[col] = 100.0 * np.cumprod(1.0 + rets)
    for col in safe_cols:
        rets = rng.normal(0.00015, 0.001, size=n_days)
        data[col] = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame(data, index=dates)


def test_zero_lookahead_future_perturbation_cannot_change_past_returns() -> None:
    """Altering prices strictly after day T must not alter strategy returns on or before day T."""
    prices_base = _synthetic_etf_prices(360)
    prices_shocked = prices_base.copy()
    cut_idx = 310
    # Extreme +500% shock strictly AFTER cut_idx
    prices_shocked.iloc[cut_idx + 1 :] = prices_shocked.iloc[cut_idx + 1 :] * 5.0

    spec = StrategySpec(
        strategy_id="TEST_PAA",
        name="Test PAA",
        universe="us_etf",
        category="TAA",
        description="Lookahead check",
        cost_bps=5.0,
    )
    w_base = compute_paa_weights(prices_base)
    w_shock = compute_paa_weights(prices_shocked)

    # Target weights at cut_idx (and all earlier dates) must be identical
    pd.testing.assert_frame_equal(w_base.iloc[: cut_idx + 1], w_shock.iloc[: cut_idx + 1])

    r_base = backtest_weight_matrix(prices_base, w_base, spec, oos_start="2022-01-01")
    r_shock = backtest_weight_matrix(prices_shocked, w_shock, spec, oos_start="2022-01-01")
    cut_date = prices_base.index[cut_idx]
    pd.testing.assert_series_equal(
        r_base.daily_returns.loc[:cut_date],
        r_shock.daily_returns.loc[:cut_date],
    )


def test_transaction_costs_strictly_reduce_net_equity_when_turnover_positive() -> None:
    prices = _synthetic_etf_prices(360)
    w = compute_paa_weights(prices)
    spec_zero = StrategySpec("PAA_0", "PAA 0bps", "us_etf", "TAA", "", cost_bps=0.0)
    spec_high = StrategySpec("PAA_50", "PAA 50bps", "us_etf", "TAA", "", cost_bps=50.0)
    res_zero = backtest_weight_matrix(prices, w, spec_zero, oos_start="2022-01-01")
    res_high = backtest_weight_matrix(prices, w, spec_high, oos_start="2022-01-01")
    assert res_zero.full.annual_turnover > 0
    assert res_high.full.total_return_pct < res_zero.full.total_return_pct


def test_deflated_sharpe_ratio_decreases_with_more_trials() -> None:
    rng = np.random.default_rng(42)
    raw = rng.normal(0.0, 0.01, size=500)
    # Shift explicitly to positive daily Sharpe (~0.11 daily => ~1.75 annualized)
    rets = pd.Series(raw - raw.mean() + 0.0011)
    dsr_1 = deflated_sharpe_ratio(rets, n_trials=1)
    dsr_25 = deflated_sharpe_ratio(rets, n_trials=25)
    dsr_200 = deflated_sharpe_ratio(rets, n_trials=200)
    assert dsr_1 > dsr_25 > dsr_200 > 0.0


def test_paa_crash_shield_shifts_100_pct_defensive_when_half_assets_below_sma252() -> None:
    prices = _synthetic_etf_prices(360, crash_tail=True)
    w = compute_paa_weights(prices)
    last = w.iloc[-1]
    safe_cols = ("BIL", "SHY", "IEF", "GLD")
    defensive_sum = float(sum(last.get(c, 0.0) for c in safe_cols))
    offensive_sum = float(last.drop(labels=[c for c in safe_cols if c in last.index]).sum())
    assert defensive_sum >= 0.999
    assert offensive_sum <= 0.001


def test_25_strategy_catalog_and_meta_portfolios_run_cleanly_offline() -> None:
    assert len(build_base_strategy_specs()) == 23
    us_etf = _synthetic_etf_prices(420)
    rng = np.random.default_rng(99)
    dates = us_etf.index
    crypto = pd.DataFrame(
        {
            "BTC-USD": 10000.0 * np.cumprod(1.0 + rng.normal(0.001, 0.03, size=len(dates))),
            "ETH-USD": 1000.0 * np.cumprod(1.0 + rng.normal(0.001, 0.035, size=len(dates))),
        },
        index=dates,
    )
    universes = {"us_etf": us_etf, "us_sectors": us_etf, "crypto": crypto, "bist": us_etf[["SPY", "QQQ", "IWM", "GLD", "TLT"]]}
    base = run_all_base_strategies(universes, oos_start="2022-01-01")
    meta = build_meta_portfolios(base, oos_start="2022-01-01")
    assert len(base) + len(meta) == 25
    assert "META_US_ETF_ALL_WEATHER" in meta
    assert "META_GLOBAL_ETF_CRYPTO_TREND" in meta


def test_verdict_classification_enforces_bist_survivorship_caveat() -> None:
    rng = np.random.default_rng(1)
    eq = pd.Series(100.0 * np.cumprod(1.0 + rng.normal(0.002, 0.01, size=300)), index=pd.bdate_range("2022-01-03", periods=300))
    metrics = compute_performance_metrics(eq)
    assert classify_strategy_verdict(metrics, universe="us_etf") == "PASS_ELITE"
    assert classify_strategy_verdict(metrics, universe="bist") == "CAVEAT_SURVIVORSHIP"
    assert classify_strategy_verdict(metrics, universe="us_etf", is_benchmark=True) == "BENCHMARK"


def test_mcp_server_exposes_paa_and_tournament_tools() -> None:
    server = DsaMcpServer()
    names = set(server.tool_names)
    assert "dsa_get_strategy_tournament" in names
    assert "dsa_get_paa_allocation" in names
    res = server.call_tool("dsa_get_strategy_tournament", {})
    assert res["isError"] is False
    body = json.loads(res["content"][0]["text"])
    assert body["ok"] is True
    assert body["data"]["module_present"] is True
    assert body["data"]["total_strategies"] == 25
