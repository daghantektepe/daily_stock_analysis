# -*- coding: utf-8 -*-
"""BIST USD-based tournament metrics and the AI Council v2 robustness gate."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.quant import ai_council as ac
from src.quant.bist_usd import (
    build_bist_usd_reference,
    clean_usdtry,
    try_returns_to_usd,
    usd_oos_metrics,
    yearly_returns_pct,
)
from src.quant.stats import PerformanceMetrics, classify_strategy_verdict
from src.quant.tournament import format_tournament_markdown


# ---------------------------------------------------------------------------
# BIST -> USD conversion
# ---------------------------------------------------------------------------


def test_flat_lira_return_becomes_dollar_loss_when_lira_weakens() -> None:
    days = pd.bdate_range("2024-01-01", periods=5)
    try_ret = pd.Series(0.0, index=days)
    usdtry = pd.Series([30.0, 30.3, 30.603, 30.90903, 31.2181203], index=days)  # +1%/day
    usd = try_returns_to_usd(try_ret, usdtry)
    assert len(usd) == 4  # first day has no FX change to apply
    assert np.allclose(usd.values, 1.0 / 1.01 - 1.0)


def test_lira_move_on_a_bist_holiday_is_charged_on_the_next_session() -> None:
    fx_days = pd.bdate_range("2024-04-08", periods=5)  # Mon..Fri
    usdtry = pd.Series([32.0, 32.0, 33.6, 33.6, 33.6], index=fx_days)  # +5% on Wednesday
    bist_days = fx_days.delete(2)  # BIST closed on Wednesday (bayram)
    try_ret = pd.Series(0.0, index=bist_days)
    usd = try_returns_to_usd(try_ret, usdtry)
    thursday = fx_days[3]
    assert usd.loc[thursday] == pytest.approx(1.0 / 1.05 - 1.0)
    # Total USD loss equals the full lira move, nothing is lost over the holiday
    assert float((1.0 + usd).prod() - 1.0) == pytest.approx(1.0 / 1.05 - 1.0)


def test_isolated_bad_fx_tick_is_dropped_but_real_jumps_are_kept() -> None:
    days = pd.bdate_range("2021-12-13", periods=6)
    glitch = pd.Series([14.0, 14.1, 140.0, 14.2, 14.3, 14.4], index=days)
    assert days[2] not in clean_usdtry(glitch).index
    crash = pd.Series([18.0, 18.2, 13.5, 13.4, 13.3, 13.2], index=days)  # Dec 2021-style real move
    assert len(clean_usdtry(crash)) == 6


def test_yearly_returns_compound_by_calendar_year() -> None:
    days = pd.DatetimeIndex(["2022-12-30", "2023-01-02", "2023-01-03"])
    r = pd.Series([0.10, 0.10, -0.10], index=days)
    yearly = yearly_returns_pct(r)
    assert yearly == {"2022": 10.0, "2023": pytest.approx(-1.0)}


def _bist_fixture(n_days: int = 900):
    days = pd.bdate_range("2021-01-04", periods=n_days)
    rng = np.random.default_rng(3)
    try_ret = pd.Series(rng.normal(0.0012, 0.015, n_days), index=days)  # ~+35%/yr in TL
    usdtry = pd.Series(10.0 * np.cumprod(np.full(n_days, 1.0011)), index=days)  # ~+32%/yr lira loss
    rf = pd.Series(0.00015, index=days)  # ~3.8%/yr BIL
    return try_ret, usdtry, rf


def test_usd_oos_metrics_strip_lira_depreciation_and_use_bil_hurdle() -> None:
    try_ret, usdtry, rf = _bist_fixture()
    tl_cagr = ((1 + try_ret[try_ret.index >= "2022-01-01"]).prod()) ** (252 / (try_ret.index >= "2022-01-01").sum()) - 1
    metrics, usd_series = usd_oos_metrics(try_ret, usdtry, oos_start="2022-01-01", rf_returns=rf)
    assert metrics is not None
    assert metrics.trading_days == len(usd_series)  # no OOS day dropped
    assert metrics.cagr_pct < tl_cagr * 100.0 - 20.0
    assert metrics.rf_cagr_pct > 3.0
    assert metrics.excess_cagr_pct == pytest.approx(metrics.cagr_pct - metrics.rf_cagr_pct, abs=0.02)


def test_bist_usd_reference_reports_fx_and_index_in_both_currencies() -> None:
    try_ret, usdtry, rf = _bist_fixture()
    xu100 = 1000.0 * (1.0 + try_ret).cumprod()
    ref = build_bist_usd_reference(
        pd.DataFrame({"TRY=X": usdtry, "XU100.IS": xu100}),
        oos_start="2022-01-01",
        rf_returns=rf,
    )
    assert ref["usdtry_end"] > ref["usdtry_start"]
    assert 25.0 < ref["usdtry_annual_change_pct"] < 40.0
    assert ref["index_usd"]["cagr_pct"] < ref["index_try_cagr_pct"]
    assert build_bist_usd_reference(pd.DataFrame(), oos_start="2022-01-01") == {}


def test_bist_verdict_uses_dollar_excess_sharpe_not_tl_sharpe() -> None:
    tl = PerformanceMetrics(trading_days=1200, sharpe=1.6, cagr_pct=60.0)
    real_loss = PerformanceMetrics(trading_days=1200, excess_sharpe=-0.2, excess_cagr_pct=-3.0)
    real_gain = PerformanceMetrics(trading_days=1200, excess_sharpe=0.5, excess_cagr_pct=12.0)
    assert classify_strategy_verdict(tl, universe="bist", usd_oos=real_loss) == "FAIL_WEAK"
    assert classify_strategy_verdict(tl, universe="bist", usd_oos=real_gain) == "CAVEAT_SURVIVORSHIP"
    # Without FX data the legacy TL rule still applies
    assert classify_strategy_verdict(tl, universe="bist") == "CAVEAT_SURVIVORSHIP"


def test_tournament_markdown_shows_bist_in_dollars() -> None:
    payload = {
        "generated_at": "2026-11-21",
        "oos_start": "2022-01-01",
        "latest_date": "2026-11-20",
        "total_strategies": 1,
        "total_assets": 20,
        "total_asset_days": 1000,
        "strategies": [
            {
                "strategy_id": "BIST_MOMENTUM_TOP5",
                "name": "BIST Momentum",
                "universe": "bist",
                "currency": "TRY",
                "verdict": "CAVEAT_SURVIVORSHIP",
                "oos": {"cagr_pct": 50.5, "sharpe": 1.39, "max_drawdown_pct": -30.0},
                "usd": {"cagr_pct": 15.4, "excess_cagr_pct": 11.6, "excess_sharpe": 0.33, "max_drawdown_pct": -39.8},
                "usd_yearly_returns_pct": {"2025": 2.1, "2026": -1.2},
            }
        ],
        "bist_usd_reference": {
            "usdtry_start": 13.36,
            "usdtry_end": 50.56,
            "usdtry_annual_change_pct": 31.4,
            "start_date": "2022-01-03",
            "end_date": "2026-11-20",
            "index_symbol": "XU100.IS",
            "index_try_cagr_pct": 43.7,
            "index_usd": {"cagr_pct": 9.8, "excess_sharpe": 0.17, "max_drawdown_pct": -36.4},
        },
    }
    md = format_tournament_markdown(payload)
    assert "+11.6% (USD)" in md and "+0.33 (USD)" in md
    assert "Gerçek Dolar (USD) Karşılığı" in md
    assert "13.36 → 50.56" in md
    assert "| +2.1% | -1.2% |" in md


def test_mcp_tournament_summary_carries_bil_and_usd_metrics() -> None:
    from src.mcp.tools import _compact_tournament_summary

    raw = {
        "strategies": [
            {"strategy_id": "A", "currency": "USD", "oos": {"sharpe": 0.9, "excess_sharpe": 0.1, "excess_cagr_pct": -0.3}},
            {"strategy_id": "B", "currency": "TRY", "oos": {"sharpe": 1.4}, "usd": {"excess_sharpe": 0.33, "cagr_pct": 15.4}},
        ],
        "bist_usd_reference": {"usdtry_end": 50.56},
    }
    out = _compact_tournament_summary(raw)
    usd_row, try_row = out["leaderboard"]
    assert usd_row["oos_excess_sharpe"] == 0.1 and usd_row["usd_excess_sharpe"] is None
    assert try_row["oos_excess_sharpe"] is None and try_row["usd_excess_sharpe"] == 0.33
    assert out["bist_usd_reference"] == {"usdtry_end": 50.56}


# ---------------------------------------------------------------------------
# AI Council v2
# ---------------------------------------------------------------------------

COUNCIL_COLS = [
    "SPY", "QQQ", "IWM", "VGK", "EWJ", "EEM", "VNQ", "GLD", "DBC", "HYG", "LQD", "TLT",
    "IEF", "SHY", "BIL", "XLE", "XLV", "XLF", "XLK", "XLU", "XLP", "USMV", "QUAL",
]


def _prices_with_2022_bear(start: str = "2018-01-02", end: str = "2024-06-28") -> pd.DataFrame:
    rng = np.random.default_rng(11)
    days = pd.bdate_range(start, end)
    in_2022 = np.asarray(days.year == 2022)
    data = {}
    for col in COUNCIL_COLS:
        if col == "BIL":
            rets = np.full(len(days), 0.00012)
        elif col in ("SHY", "IEF"):
            rets = rng.normal(0.00015, 0.001, len(days))
        else:
            drift = np.where(in_2022, -0.0012, 0.0006)  # every risk asset falls ~25% in 2022
            rets = drift + rng.normal(0.0, 0.009, len(days))
        data[col] = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame(data, index=days)


def _charter(rule_engine: str = "vol_target_trend") -> dict:
    return {
        "member_key": "claude",
        "strategy_id": "COUNCIL_CLAUDE",
        "strategy_name": "Test Kalkan",
        "rule_engine": rule_engine,
        "rebalance_mode": "monthly",
        "params": {"risk_assets": ["SPY", "QQQ", "GLD"], "safe_asset": "SHY", "target_vol_pct": 10},
        "thesis": "t",
        "risk_rules": "r",
        "model": "m",
    }


def test_council_v2_reports_cost_stress_and_2022_bear_check() -> None:
    prices = _prices_with_2022_bear()
    evaluated = ac._backtest_charter(_charter(), prices, name="x", cost_bps=5.0)
    v2 = evaluated["council_v2"]
    assert v2["version"] == 2
    assert set(v2["cost_stress"]) == {"5", "25", "50"}
    s5, s25, s50 = (v2["cost_stress"][k]["excess_cagr_pct"] for k in ("5", "25", "50"))
    assert s5 >= s25 >= s50  # higher costs can only hurt
    bear = v2["bear_market"]
    assert bear["year"] == 2022 and bear["strategy"] and bear["benchmark"]
    assert bear["benchmark"]["return_pct"] < -15.0
    keys = {c["key"]: c for c in v2["checks"]}
    assert set(keys) == {"oos_verdict", "cost_stress", "bear_market"}
    assert keys["bear_market"]["ok"] == (bear["strategy"]["return_pct"] > bear["benchmark"]["return_pct"])
    assert v2["verdict"] == ("PASS" if all(c["ok"] for c in v2["checks"]) else "FAIL")


def test_council_v2_fails_without_a_full_2022() -> None:
    prices = _prices_with_2022_bear(start="2023-01-02", end="2024-12-31")
    v2 = ac._backtest_charter(_charter(), prices, name="x", cost_bps=5.0)["council_v2"]
    bear_check = next(c for c in v2["checks"] if c["key"] == "bear_market")
    assert bear_check["ok"] is False and bear_check["value"] is None
    assert v2["verdict"] == "FAIL"


def test_reevaluate_updates_only_evaluation_fields_and_never_calls_cli(tmp_path: Path, monkeypatch) -> None:
    def _no_cli(*_args, **_kwargs):
        raise AssertionError("reevaluate must not call AI CLIs")

    monkeypatch.setattr(ac, "invoke_council_cli", _no_cli)
    charter = _charter("paa_custom")
    charter["verdict"] = "PASS_SOLID"  # stale Rf=0-era verdict
    ac.save_council_charters({"members": {"claude": dict(charter)}}, tmp_path)

    res = ac.reevaluate_council_charters(prices=_prices_with_2022_bear(), book_dir=tmp_path)
    assert res["ok"] is True
    item = res["results"][0]
    assert item["previous_verdict"] == "PASS_SOLID"
    stored = ac.load_council_charters(tmp_path)["members"]["claude"]
    for key in ("rule_engine", "params", "rebalance_mode", "strategy_name"):
        assert stored[key] == charter[key]
    assert stored["council_v2"]["verdict"] in ("PASS", "FAIL")
    assert "excess_sharpe" in stored["oos_backtest"]
    report = ac.format_council_v2_report(res["results"])
    assert "Konsey v2" in report and "25 bps" in report

    empty = ac.reevaluate_council_charters(prices=_prices_with_2022_bear(), book_dir=tmp_path / "none")
    assert empty["ok"] is False


def test_council_meta_exposes_v2_to_paper_books(tmp_path: Path) -> None:
    prices = _prices_with_2022_bear()
    raw = {k: v for k, v in _charter().items() if k not in ("member_key", "strategy_id", "model")}
    evaluated = ac.evaluate_and_register_charter(
        "claude", raw, prices, model="m", book_dir=tmp_path, today=prices.index[-1].date()
    )
    assert evaluated["charter"]["council_v2"]["version"] == 2
    assert evaluated["book_summary"]["council_meta"]["council_v2"] == evaluated["charter"]["council_v2"]
    ac.save_council_charters({"members": {"claude": evaluated["charter"]}}, tmp_path)
    status = ac.get_active_council_books_status(book_dir=tmp_path)
    assert status[0]["council_meta"]["council_v2"]["verdict"] == evaluated["charter"]["council_v2"]["verdict"]


def test_council_prompt_states_v2_gate() -> None:
    prompt = ac._build_council_prompt("gemini", {"as_of_date": "2026-11-20"})
    assert "Konsey v2" in prompt and "25 bps" in prompt and "2022" in prompt


def test_run_tournament_attaches_usd_view_to_bist_and_ranks_on_it(tmp_path: Path, monkeypatch) -> None:
    from src.quant import tournament as tour
    from src.quant.data_loader import BIST_LIQUID_UNIVERSE, CRYPTO_UNIVERSE, US_ETF_UNIVERSE, US_SECTOR_FACTOR_UNIVERSE

    days = pd.bdate_range("2020-01-02", "2023-12-29")
    rng = np.random.default_rng(5)

    def frame(cols, drift, vol):
        return pd.DataFrame(
            {c: 100.0 * np.cumprod(1.0 + rng.normal(drift, vol, len(days))) for c in cols}, index=days
        )

    us = frame(US_ETF_UNIVERSE, 0.0004, 0.01)
    us["BIL"] = 100.0 * np.cumprod(np.full(len(days), 1.00012))
    universes = {
        "us_etf": us,
        "us_sectors": frame(US_SECTOR_FACTOR_UNIVERSE, 0.0004, 0.01),
        "crypto": frame(CRYPTO_UNIVERSE, 0.001, 0.03),
        "bist": frame(BIST_LIQUID_UNIVERSE, 0.0015, 0.02),  # strong TL trend
    }
    usdtry = pd.Series(10.0 * np.cumprod(np.full(len(days), 1.0016)), index=days)  # lira loses ~50%/yr
    monkeypatch.setattr(tour, "load_all_tournament_universes", lambda **_k: universes)
    monkeypatch.setattr(
        tour, "load_bist_usd_reference",
        lambda **_k: pd.DataFrame({"TRY=X": usdtry, "XU100.IS": universes["bist"].mean(axis=1)}),
    )

    payload = tour.run_tournament(
        oos_start="2022-01-01", cache_dir=tmp_path, write_report=False, update_paper_snapshot=False
    )
    bist_rows = [r for r in payload["strategies"] if r["universe"] == "bist"]
    assert bist_rows and all("usd" in r for r in bist_rows)
    for row in bist_rows:
        assert row["usd"]["cagr_pct"] < row["oos"]["cagr_pct"]
        assert row["usd"]["rf_cagr_pct"] > 0  # judged over BIL
        assert set(row["usd_yearly_returns_pct"]) == {"2022", "2023"}
    assert all("usd" not in r for r in payload["strategies"] if r["currency"] == "USD")
    assert payload["bist_usd_reference"]["usdtry_end"] > payload["bist_usd_reference"]["usdtry_start"]

    # Without FX data the tournament still runs and BIST falls back to the TL rule
    monkeypatch.setattr(tour, "load_bist_usd_reference", lambda **_k: pd.DataFrame())
    fallback = tour.run_tournament(
        oos_start="2022-01-01", cache_dir=tmp_path, write_report=False, update_paper_snapshot=False
    )
    assert fallback["bist_usd_reference"] is None
    assert all("usd" not in r for r in fallback["strategies"])


def test_tournament_api_keeps_usd_fields(monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.v1.endpoints import alpha
    from src.quant import tournament as tour

    payload = {
        "oos_start": "2022-01-01",
        "strategies": [{"strategy_id": "BIST_MOMENTUM_TOP5", "usd": {"excess_sharpe": 0.33}, "usd_yearly_returns_pct": {"2026": -1.2}}],
        "bist_usd_reference": {"usdtry_start": 13.36, "usdtry_end": 50.56},
    }
    monkeypatch.setattr(tour, "load_latest_tournament_results", lambda **_k: payload)
    app = FastAPI()
    app.include_router(alpha.router, prefix="/api/v1/alpha")
    body = TestClient(app).get("/api/v1/alpha/tournament?auto_run=false").json()
    assert body["bist_usd_reference"]["usdtry_end"] == 50.56
    assert body["strategies"][0]["usd"]["excess_sharpe"] == 0.33
