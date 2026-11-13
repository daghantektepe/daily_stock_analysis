# -*- coding: utf-8 -*-
"""Offline unit tests for US High-Alpha Quantitative Multi-Factor Screener."""

import math
import numpy as np
import pandas as pd

from src.services.us_quant_screener import (
    compute_52w_high_proximity,
    compute_frog_in_the_pan,
    compute_residual_momentum,
    compute_vol_scale_weight,
    score_us_quant_candidate,
    screen_us_quant,
)


def _make_price_df(daily_returns: np.ndarray, start_price: float = 100.0, volume: float = 2_000_000.0) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=len(daily_returns) + 1)
    prices = [start_price]
    for r in daily_returns:
        prices.append(prices[-1] * (1.0 + float(r)))
    s = pd.Series(prices, index=dates)
    return pd.DataFrame(
        {
            "Open": s * 0.998,
            "High": s * 1.005,
            "Low": s * 0.995,
            "Close": s,
            "Volume": volume,
        },
        index=dates,
    )


def test_residual_momentum_52w_fip_and_vol_scale() -> None:
    rng = np.random.default_rng(42)
    n = 280
    mkt_rets = rng.normal(0.0003, 0.008, size=n)
    # Smooth steady outperformance (+0.002/day alpha)
    alpha_rets = mkt_rets + 0.002 + rng.normal(0.0, 0.004, size=n)

    mkt_df = _make_price_df(mkt_rets)
    alpha_df = _make_price_df(alpha_rets)

    resid_z, raw_12_1m = compute_residual_momentum(alpha_df["Close"], mkt_df["Close"])
    assert resid_z is not None and resid_z > 2.0
    assert raw_12_1m is not None and raw_12_1m > 20.0

    near_52w = compute_52w_high_proximity(alpha_df["Close"], alpha_df["High"])
    assert near_52w is not None and near_52w > 0.90

    fip_id = compute_frog_in_the_pan(alpha_df["Close"])
    assert fip_id is not None and fip_id < 0.0  # smooth positive drift

    realized_vol, vol_w = compute_vol_scale_weight(alpha_df["Close"], target_vol_ann=0.12)
    assert realized_vol is not None and realized_vol > 0
    assert vol_w is not None and 0.25 <= vol_w <= 2.0


def test_score_and_screen_us_quant_ranks_quality_momentum_higher() -> None:
    rng = np.random.default_rng(7)
    n = 280
    mkt_rets = rng.normal(0.0002, 0.008, size=n)
    winner_rets = mkt_rets + 0.0025 + rng.normal(0.0, 0.004, size=n)
    loser_rets = mkt_rets - 0.0020 + rng.normal(0.0, 0.015, size=n)

    frames = {
        "SPY": _make_price_df(mkt_rets, volume=50_000_000.0),
        "WIN": _make_price_df(winner_rets, volume=1_000_000.0),
        "LOSE": _make_price_df(loser_rets, volume=1_000_000.0),
    }

    cand_win = score_us_quant_candidate(
        "WIN",
        frames["WIN"],
        frames["SPY"],
        cash_op_profitability=0.22,
        accruals_ratio=-0.04,
    )
    cand_lose = score_us_quant_candidate(
        "LOSE",
        frames["LOSE"],
        frames["SPY"],
        cash_op_profitability=0.01,
        accruals_ratio=0.10,
    )
    assert cand_win is not None
    assert cand_lose is not None
    assert cand_win.score > cand_lose.score + 40.0

    ranked = screen_us_quant(
        symbols=["LOSE", "WIN"],
        top_n=5,
        min_score=20.0,
        history_fetcher=lambda sym: frames[sym],
        quality_fetcher=lambda sym: (0.22, -0.04) if sym == "WIN" else (0.01, 0.10),
        use_sec_xbrl=False,
    )
    assert [c.symbol for c in ranked] == ["WIN"]


def test_screen_us_alpha_candidates_applies_pead_bonus(monkeypatch) -> None:
    from src.services.pead_screener import PeadCandidate
    from src.services.us_quant_screener import screen_us_alpha_candidates

    rng = np.random.default_rng(11)
    n = 280
    mkt_rets = rng.normal(0.0002, 0.008, size=n)
    winner_rets = mkt_rets + 0.0020 + rng.normal(0.0, 0.004, size=n)
    frames = {
        "SPY": _make_price_df(mkt_rets, volume=50_000_000.0),
        "WIN": _make_price_df(winner_rets, volume=1_500_000.0),
    }

    fake_pead = [
        PeadCandidate(
            symbol="WIN",
            company_name="Winner Corp",
            earnings_date="2026-11-01",
            days_since_earnings=5,
            eps_estimate=1.0,
            eps_reported=1.25,
            eps_surprise_pct=25.0,
            day1_return_pct=4.5,
            total_drift_pct=6.0,
            volume_surge_ratio=2.4,
            trend_regime="uptrend",
            conviction_tier="HIGH",
            score=80,
            reasons=["EPS beat +25%"],
            near_52w_high=0.97,
            avg_dollar_volume=150_000_000.0,
        ),
        PeadCandidate(
            symbol="NEWCO",
            company_name="New Co",
            earnings_date="2026-11-02",
            days_since_earnings=4,
            eps_estimate=0.5,
            eps_reported=0.7,
            eps_surprise_pct=40.0,
            day1_return_pct=6.0,
            total_drift_pct=8.0,
            volume_surge_ratio=3.0,
            trend_regime="uptrend",
            conviction_tier="HIGH",
            score=76,
            reasons=["EPS beat +40%"],
            near_52w_high=0.95,
            avg_dollar_volume=90_000_000.0,
        ),
    ]

    monkeypatch.setattr(
        "src.services.pead_screener.screen_pead_candidates",
        lambda **kwargs: fake_pead,
    )

    candidates = screen_us_alpha_candidates(
        symbols=["WIN"],
        top_n=5,
        include_pead=True,
        include_form4=False,
        history_fetcher=lambda sym: frames[sym],
        quality_fetcher=lambda sym: (0.20, -0.03),
        use_sec_xbrl=False,
    )
    by_sym = {c.symbol: c for c in candidates}
    assert "WIN" in by_sym and by_sym["WIN"].pead_score == 20.0
    assert any("PEAD=80 (EPS +25.0%)" in r for r in by_sym["WIN"].reasons)
    assert "NEWCO" in by_sym and by_sym["NEWCO"].pead_score == 19.0

