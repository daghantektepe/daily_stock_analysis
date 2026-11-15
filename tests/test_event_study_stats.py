# -*- coding: utf-8 -*-
"""Rigor rules for the event studies: clustering, multiple testing, survivorship."""

from datetime import date, timedelta

import pytest

from data_provider.sec_form4_fetcher import InsiderClusterEvent
from src.services.event_study_stats import (
    clustered_test,
    delisting_sensitivity,
    holm_adjust,
    mark_significance,
)
from src.services.sec_form4_study import run_sec_form4_event_study


def test_clustered_test_counts_months_not_events() -> None:
    # 50 events in one month are one observation; the naive t would look huge.
    same_month = [(date(2026, 3, 1) + timedelta(days=i % 20), 5.0 + (i % 3)) for i in range(50)]
    result = clustered_test(same_month)
    assert result["count"] == 50 and result["months"] == 1
    assert result["t_stat"] == 0.0 and result["p_value"] == 1.0

    spread = [(date(2024 + i // 12, i % 12 + 1, 10), 2.0 + (i % 4) * 0.5) for i in range(24)]
    strong = clustered_test(spread)
    assert strong["months"] == 24 and strong["t_stat"] > 5 and strong["p_value"] < 0.001


def test_holm_and_significance_require_correction_and_months() -> None:
    adjusted = holm_adjust({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted == {"a": 0.03, "c": 0.06, "b": 0.06}

    cells = {
        "a": {"p_value": 0.03, "months": 30},
        "b": {"p_value": 0.03, "months": 30},
        "short": {"p_value": 0.0001, "months": 6},
    }
    mark_significance(cells)
    # Each would pass alone (0.03 < 0.05) but not after correcting for 3 tests.
    assert cells["a"]["is_significant"] is False and cells["b"]["is_significant"] is False
    assert cells["short"]["is_significant"] is False  # too few months
    strong = {"x": {"p_value": 0.001, "months": 30}, "y": {"p_value": 0.5, "months": 30}}
    mark_significance(strong)
    assert strong["x"]["is_significant"] is True and strong["y"]["is_significant"] is False


def test_delisting_sensitivity() -> None:
    assert delisting_sensitivity([10.0, 10.0], 2) == pytest.approx(-10.0)
    assert delisting_sensitivity([], 0) is None


def _event(symbol: str, day: date) -> InsiderClusterEvent:
    return InsiderClusterEvent(
        symbol=symbol, company_name=symbol, filing_date=day, insider_count=2, total_value=100_000.0,
        has_c_level=True, is_opportunistic=True, is_cluster=True, cmp_class="opportunistic",
    )


def test_form4_study_keeps_delisted_losers_and_uses_harder_benchmark() -> None:
    start = date(2025, 1, 1)
    days = [start + timedelta(days=i) for i in range(400) if (start + timedelta(days=i)).weekday() < 5]
    spy = {d: 100.0 * (1.0005 ** i) for i, d in enumerate(days)}
    iwm = {d: 100.0 * (1.001 ** i) for i, d in enumerate(days)}  # small caps rallied more
    winner = {d: 50.0 * (1.002 ** i) for i, d in enumerate(days)}
    # Loser stops trading 30 bars after the event at -60%.
    loser = {d: (20.0 if i <= 40 else 8.0) for i, d in enumerate(days[:71])}
    prices = {"SPY": spy, "IWM": iwm, "WIN": winner, "LOSE": loser}

    def history(symbol, _start, _end):
        return prices.get(symbol, {})

    result = run_sec_form4_event_study(
        [_event("WIN", days[30]), _event("LOSE", days[30]), _event("GONE", days[30])],
        history=history, estimated_slippage_pct=0.0,
    )
    h63 = result["horizons"]["63d"]
    assert h63["count"] == 2  # the delisted loser is kept, not dropped
    assert h63["delisted_count"] == 1
    assert result["missing_events"] == 1  # no prices at all
    assert h63["delisting_adjusted_excess_pct"] < h63["avg_excess_return_pct"]
    assert h63["avg_excess_vs_secondary_pct"] < h63["avg_excess_return_pct"]
    assert h63["conservative_excess_pct"] == h63["avg_excess_vs_secondary_pct"]
    assert h63["is_significant"] is False  # one month of events proves nothing
    assert result["secondary_benchmark_symbol"] == "IWM" and result["tests_corrected"] > 0
