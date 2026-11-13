# -*- coding: utf-8 -*-
"""Historical Post-Earnings Announcement Drift (PEAD) Event Study.

Empirically validates whether earnings surprises produce statistically
significant post-announcement excess returns (Alpha) relative to a U.S.
benchmark (`SPY` or `IWM`) net of estimated slippage, accounting for
BMO vs. AMC announcement timing via :func:`resolve_event_day0`.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.services.pead_screener import resolve_event_day0
from src.services.sec_form4_study import (
    DEFAULT_BENCHMARK_SYMBOL,
    _PriceCalendar,
    compute_sample_statistics,
    disk_cached_yfinance_history,
)

logger = logging.getLogger(__name__)

DEFAULT_PEAD_HORIZONS: Tuple[Tuple[str, int], ...] = (
    ("1d", 1),
    ("5d", 5),
    ("20d", 20),
    ("40d", 40),
)


@dataclass
class PeadEventOutcome:
    """Measured post-earnings drift for one historical earnings release."""

    symbol: str
    earnings_date: date
    entry_date: date
    entry_price: float
    eps_surprise_pct: float
    day1_return_pct: float
    trend_regime: str
    session: str
    horizons: Dict[str, Dict[str, Any]]


def run_pead_event_study(
    symbols: Sequence[str],
    *,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    horizons: Sequence[Tuple[str, int]] = DEFAULT_PEAD_HORIZONS,
    min_surprise_pct: Optional[float] = None,
    min_dollar_volume: float = 2_000_000.0,
    estimated_slippage_pct: float = 0.25,
    max_events_per_symbol: int = 12,
    earnings_fetcher: Optional[Callable[[str], Optional[pd.DataFrame]]] = None,
    price_fetcher: Optional[Callable[[str, date, date], Dict[date, float]]] = None,
    volume_fetcher: Optional[Callable[[str, date, date], Dict[date, float]]] = None,
) -> Dict[str, Any]:
    """Run an offline/online historical PEAD event study across ``symbols``.

    Entry is assumed at the close of announcement Day 0 (after BMO/AMC alignment)
    so the announcement-day gap is excluded and only tradeable *post-earnings drift*
    is measured.
    """
    clean_symbols = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if not clean_symbols:
        return {
            "total_events": 0,
            "evaluated_events": 0,
            "benchmark_symbol": benchmark_symbol,
            "estimated_slippage_pct": estimated_slippage_pct,
            "horizons": {},
            "segments": {},
        }

    def _default_earnings(sym: str) -> Optional[pd.DataFrame]:
        import yfinance as yf
        return yf.Ticker(sym).get_earnings_dates(limit=max_events_per_symbol + 4)

    def _default_prices(sym: str, start: date, end: date) -> Dict[date, float]:
        return disk_cached_yfinance_history(sym, start, end)

    ed_fn = earnings_fetcher or _default_earnings
    px_fn = price_fetcher or _default_prices

    raw_events: List[Tuple[str, Any, date, float]] = []
    min_date: Optional[date] = None
    max_date: Optional[date] = None

    for sym in clean_symbols:
        try:
            ed_df = ed_fn(sym)
            if ed_df is None or ed_df.empty:
                continue
            count = 0
            for idx_ts, row in ed_df.iterrows():
                rep = row.get("Reported EPS")
                est = row.get("EPS Estimate")
                surp = row.get("Surprise(%)")
                if pd.isna(rep):
                    continue
                e_dt = idx_ts.date() if hasattr(idx_ts, "date") else idx_ts
                surp_val = float(surp) if not pd.isna(surp) else (
                    round((float(rep) - float(est)) / abs(float(est)) * 100.0, 2)
                    if est is not None and not pd.isna(est) and float(est) != 0 else 0.0
                )
                if min_surprise_pct is not None and surp_val < min_surprise_pct:
                    continue
                raw_events.append((sym, idx_ts, e_dt, surp_val))
                min_date = e_dt if min_date is None else min(min_date, e_dt)
                max_date = e_dt if max_date is None else max(max_date, e_dt)
                count += 1
                if count >= max_events_per_symbol:
                    break
        except Exception as exc:  # noqa: BLE001
            logger.debug("[pead-study] earnings lookup failed for %s: %s", sym, exc)

    if not raw_events or min_date is None or max_date is None:
        return {
            "total_events": 0,
            "evaluated_events": 0,
            "benchmark_symbol": benchmark_symbol,
            "estimated_slippage_pct": estimated_slippage_pct,
            "horizons": {},
            "segments": {},
        }

    max_bars = max(h[1] for h in horizons) if horizons else 40
    fetch_start = min_date - timedelta(days=320)
    fetch_end = max_date + timedelta(days=int(max_bars * 1.8) + 15)

    bench_closes = px_fn(benchmark_symbol, fetch_start, fetch_end)
    bench_series = _PriceCalendar(bench_closes)

    series_cache: Dict[str, _PriceCalendar] = {}
    vol_cache: Dict[str, Dict[date, float]] = {}
    for sym in {ev[0] for ev in raw_events}:
        series_cache[sym] = _PriceCalendar(px_fn(sym, fetch_start, fetch_end))
        if volume_fetcher is not None:
            vol_cache[sym] = volume_fetcher(sym, fetch_start, fetch_end)

    outcomes: List[PeadEventOutcome] = []
    for sym, earn_ts, earn_dt, surp_val in raw_events:
        stock_series = series_cache[sym]
        trading_days = stock_series.dates
        if len(trading_days) < 25:
            continue

        day0, base_day, session_label = resolve_event_day0(earn_ts, trading_days)
        if day0 is None or base_day is None:
            continue

        entry_price = stock_series.closes.get(day0)
        base_price = stock_series.closes.get(base_day)
        bench_entry = bench_series.closes.get(day0) or bench_series.next_trading_day_close(day0 - timedelta(days=1))[1]
        if not entry_price or not base_price or not bench_entry or entry_price <= 0 or base_price <= 0 or bench_entry <= 0:
            continue

        # Optional liquidity filter when volume_fetcher is provided
        if min_dollar_volume > 0 and sym in vol_cache and vol_cache[sym]:
            d0_idx = trading_days.index(day0)
            prior_days = trading_days[max(0, d0_idx - 20): d0_idx]
            dv_vals = [
                stock_series.closes[d] * vol_cache[sym].get(d, 0.0)
                for d in prior_days
                if d in stock_series.closes and d in vol_cache[sym]
            ]
            if dv_vals and (sum(dv_vals) / len(dv_vals)) < min_dollar_volume:
                continue

        day1_ret = round((entry_price / base_price - 1.0) * 100.0, 2)
        sma200 = stock_series.simple_moving_average(day0, 200)
        trend_regime = "uptrend" if (sma200 and entry_price > sma200) else ("downtrend" if sma200 else "neutral")

        horizon_results: Dict[str, Dict[str, Any]] = {}
        for h_key, n_bars in horizons:
            exit_dt, exit_px = stock_series.close_after_n_bars(day0, n_bars)
            _, bench_exit_px = bench_series.close_after_n_bars(day0, n_bars)
            if exit_dt is None or not exit_px or not bench_exit_px:
                continue
            stock_ret = (exit_px / entry_price - 1.0) * 100.0
            bench_ret = (bench_exit_px / bench_entry - 1.0) * 100.0
            excess = stock_ret - bench_ret
            horizon_results[h_key] = {
                "n_bars": n_bars,
                "exit_date": exit_dt.isoformat(),
                "stock_return_pct": round(stock_ret, 2),
                "benchmark_return_pct": round(bench_ret, 2),
                "excess_return_pct": round(excess, 2),
                "beat_benchmark": excess > 0,
            }

        if horizon_results:
            outcomes.append(PeadEventOutcome(
                symbol=sym,
                earnings_date=earn_dt,
                entry_date=day0,
                entry_price=round(entry_price, 4),
                eps_surprise_pct=round(surp_val, 2),
                day1_return_pct=day1_ret,
                trend_regime=trend_regime,
                session=session_label,
                horizons=horizon_results,
            ))

    h_keys = [h[0] for h in horizons]
    return {
        "total_events": len(raw_events),
        "evaluated_events": len(outcomes),
        "benchmark_symbol": benchmark_symbol,
        "estimated_slippage_pct": estimated_slippage_pct,
        "horizons": _aggregate_pead_metrics(outcomes, h_keys, estimated_slippage_pct),
        "segments": {
            "surprise_bucket": {
                "strong_beat_10pct_plus": _aggregate_pead_metrics(
                    [o for o in outcomes if o.eps_surprise_pct >= 10.0], h_keys, estimated_slippage_pct
                ),
                "positive_beat": _aggregate_pead_metrics(
                    [o for o in outcomes if o.eps_surprise_pct > 0.0], h_keys, estimated_slippage_pct
                ),
                "negative_miss": _aggregate_pead_metrics(
                    [o for o in outcomes if o.eps_surprise_pct < 0.0], h_keys, estimated_slippage_pct
                ),
            },
            "trend": {
                "uptrend": _aggregate_pead_metrics(
                    [o for o in outcomes if o.trend_regime == "uptrend"], h_keys, estimated_slippage_pct
                ),
                "downtrend": _aggregate_pead_metrics(
                    [o for o in outcomes if o.trend_regime == "downtrend"], h_keys, estimated_slippage_pct
                ),
            },
        },
    }


def _aggregate_pead_metrics(
    outcomes: Sequence[PeadEventOutcome],
    horizon_keys: Sequence[str],
    slippage_pct: float = 0.25,
) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}
    for h_key in horizon_keys:
        valid = [o.horizons[h_key] for o in outcomes if h_key in o.horizons]
        if not valid:
            summary[h_key] = {"count": 0}
            continue
        excess_vals = [v["excess_return_pct"] for v in valid]
        net_excess_vals = [x - slippage_pct for x in excess_vals]
        stock_stats = compute_sample_statistics([v["stock_return_pct"] for v in valid])
        excess_stats = compute_sample_statistics(excess_vals)
        net_stats = compute_sample_statistics(net_excess_vals)
        n = len(valid)
        summary[h_key] = {
            "count": n,
            "avg_stock_return_pct": stock_stats["mean"],
            "avg_excess_return_pct": excess_stats["mean"],
            "net_excess_return_pct": net_stats["mean"],
            "median_excess_return_pct": excess_stats["median"],
            "win_rate_pct": round(sum(1 for v in valid if v["stock_return_pct"] > 0) / n * 100.0, 1),
            "beat_benchmark_rate_pct": round(sum(1 for v in valid if v["beat_benchmark"]) / n * 100.0, 1),
            "t_stat": excess_stats["t_stat"],
            "net_t_stat": net_stats["t_stat"],
            "is_significant": excess_stats["is_significant"],
        }
    return summary


__all__ = [
    "DEFAULT_PEAD_HORIZONS",
    "PeadEventOutcome",
    "run_pead_event_study",
]
