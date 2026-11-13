# -*- coding: utf-8 -*-
"""Unit tests for Post-Earnings Announcement Drift (PEAD) Screener."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import pandas as pd
import pytest

from src.services.pead_screener import (
    PeadCandidate,
    evaluate_pead_for_symbol,
    format_pead_report,
    score_pead_candidate,
)


def test_score_pead_candidate() -> None:
    # 1. High surprise, positive reaction, volume surge, uptrend
    score_hi, tier_hi, reasons_hi = score_pead_candidate(
        eps_surprise_pct=30.0,
        day1_return_pct=5.5,
        volume_surge_ratio=2.2,
        trend_regime="uptrend",
        days_since_earnings=10,
    )
    assert tier_hi == "HIGH"
    assert score_hi >= 85  # 40 (eps) + 20 (day1) + 15 (vol) + 15 (trend) + 10 (window) = 100
    assert any("Çok Yüksek Kâr Sürprizi" in r for r in reasons_hi)
    assert any("Kurumsal Hacim Patlaması" in r for r in reasons_hi)
    assert any("Trend Onayı" in r for r in reasons_hi)

    # 2. Negative surprise penalty
    score_neg, tier_neg, reasons_neg = score_pead_candidate(
        eps_surprise_pct=-15.0,
        day1_return_pct=-4.0,
        volume_surge_ratio=1.0,
        trend_regime="downtrend",
        days_since_earnings=15,
    )
    assert tier_neg == "NEGATIVE"
    assert score_neg <= 20
    assert any("Negatif Kâr Sürprizi" in r for r in reasons_neg)


def test_evaluate_pead_for_symbol_mocked() -> None:
    today_dt = date(2026, 11, 10)
    earn_dt = date(2026, 10, 25)

    # Mock earnings dates dataframe
    ed_data = {
        "EPS Estimate": [1.50, 1.20],
        "Reported EPS": [1.95, 1.30],  # 30% surprise on 2026-10-25
        "Surprise(%)": [30.0, 8.33],
    }
    ed_index = [
        pd.Timestamp("2026-10-25"),
        pd.Timestamp("2026-07-25"),
    ]
    mock_ed_df = pd.DataFrame(ed_data, index=ed_index)

    # Mock historical price & volume dataframe
    hist_dates = [earn_dt - timedelta(days=i) for i in range(250, 0, -1)] + [
        earn_dt + timedelta(days=i) for i in range(18)
    ]
    hist_closes = [100.0 + i * 0.2 for i in range(len(hist_dates))]
    hist_vols = [1_000_000 for _ in range(len(hist_dates))]
    # Spike on earnings date
    earn_idx = [d for d in hist_dates if d >= earn_dt][0]
    hist_idx_int = hist_dates.index(earn_idx)
    hist_closes[hist_idx_int] = hist_closes[hist_idx_int - 1] * 1.05  # +5% gap
    hist_vols[hist_idx_int] = 2_500_000  # 2.5x volume

    mock_hist_df = pd.DataFrame(
        {"Close": hist_closes, "Volume": hist_vols},
        index=[pd.Timestamp(d) for d in hist_dates],
    )

    class MockTicker:
        def __init__(self, sym: str):
            self.symbol = sym
            self.info = {"shortName": "Test Tech Inc"}

        def get_earnings_dates(self, limit: int = 8):
            return mock_ed_df

        def history(self, start: str, end: str):
            return mock_hist_df

    candidate = evaluate_pead_for_symbol(
        "TECH",
        today=today_dt,
        max_days=45,
        min_score=40,
        ticker_fetcher=lambda sym: MockTicker(sym),
    )

    assert candidate is not None
    assert candidate.symbol == "TECH"
    assert candidate.company_name == "Test Tech Inc"
    assert candidate.eps_surprise_pct == 30.0
    assert candidate.eps_reported == 1.95
    assert candidate.eps_estimate == 1.50
    assert candidate.volume_surge_ratio >= 2.0
    assert candidate.trend_regime == "uptrend"
    assert candidate.score >= 70

    report = format_pead_report([candidate])
    assert "TECH - Test Tech Inc" in report
    assert "+%30.0" in report
    assert "python main.py --stocks TECH" in report


def test_resolve_event_day0_bmo_vs_amc() -> None:
    from src.services.pead_screener import resolve_event_day0

    trading_days = [
        date(2026, 11, 2),
        date(2026, 11, 3),
        date(2026, 11, 4),
        date(2026, 11, 5),
    ]
    # Before market open (08:30) on Nov 3 -> Day 0 is Nov 3
    d_bmo, _, sess_bmo = resolve_event_day0(pd.Timestamp("2026-11-03 08:30:00"), trading_days)
    assert d_bmo == date(2026, 11, 3)
    assert sess_bmo == "BMO"

    # After market close (16:05) on Nov 3 -> Day 0 is Nov 4
    d_amc, _, sess_amc = resolve_event_day0(pd.Timestamp("2026-11-03 16:05:00"), trading_days)
    assert d_amc == date(2026, 11, 4)
    assert sess_amc == "AMC"


def test_pead_event_study_offline() -> None:
    from src.services.pead_event_study import run_pead_event_study

    dates = pd.bdate_range("2026-01-02", periods=90)
    spy_closes = {d.date(): 100.0 * ((1.0005) ** i) for i, d in enumerate(dates)}
    stock_closes = {
        d.date(): (100.0 if i < 20 else 105.0 * ((1.005) ** (i - 20)))
        for i, d in enumerate(dates)
    }

    earnings_df = pd.DataFrame(
        {
            "EPS Estimate": [1.00],
            "Reported EPS": [1.25],
            "Surprise(%)": [25.0],
        },
        index=[pd.Timestamp(dates[20].date()) + pd.Timedelta(hours=8)],
    )

    report = run_pead_event_study(
        ["BEAT"],
        min_surprise_pct=5.0,
        horizons=(("1d", 1), ("5d", 5), ("20d", 20)),
        earnings_fetcher=lambda sym: earnings_df if sym == "BEAT" else pd.DataFrame(),
        price_fetcher=lambda sym, s, e: spy_closes if sym == "SPY" else stock_closes,
    )
    assert report["evaluated_events"] == 1
    assert report["horizons"]["20d"]["count"] == 1
    assert report["horizons"]["20d"]["avg_excess_return_pct"] > 5.0

