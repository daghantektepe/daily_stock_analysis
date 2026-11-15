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

from src.services.event_study_stats import clustered_test, mark_significance
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
    secondary_benchmark_symbol: Optional[str] = "IWM",
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
    second_series: Optional[_PriceCalendar] = None
    if secondary_benchmark_symbol and secondary_benchmark_symbol != benchmark_symbol:
        second_closes = px_fn(secondary_benchmark_symbol, fetch_start, fetch_end)
        second_series = _PriceCalendar(second_closes) if second_closes else None

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
            if second_series is not None:
                second_entry = second_series.closes.get(day0)
                _, second_exit = second_series.close_after_n_bars(day0, n_bars)
                if second_entry and second_exit:
                    horizon_results[h_key]["excess_vs_secondary_pct"] = round(
                        stock_ret - (second_exit / second_entry - 1.0) * 100.0, 2
                    )

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
    result = {
        "total_events": len(raw_events),
        "evaluated_events": len(outcomes),
        "benchmark_symbol": benchmark_symbol,
        "secondary_benchmark_symbol": secondary_benchmark_symbol if second_series is not None else None,
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
    # Holm correction across every reported cell (overall + segments).
    cells: Dict[str, Dict[str, Any]] = {
        f"all:{key}": cell for key, cell in result["horizons"].items() if cell.get("count")
    }
    for group, members in result["segments"].items():
        for member, per_horizon in members.items():
            for key, cell in per_horizon.items():
                if cell.get("count"):
                    cells[f"{group}.{member}:{key}"] = cell
    mark_significance(cells)
    result["tests_corrected"] = len(cells)
    return result


def _aggregate_pead_metrics(
    outcomes: Sequence[PeadEventOutcome],
    horizon_keys: Sequence[str],
    slippage_pct: float = 0.25,
) -> Dict[str, Dict[str, Any]]:
    """Per-horizon drift with calendar-month clustered statistics.

    ``net_excess_return_pct`` uses the harder of the primary / small-cap
    benchmark minus slippage; ``is_significant`` is set by :func:`mark_significance`.
    """
    summary: Dict[str, Dict[str, Any]] = {}
    for h_key in horizon_keys:
        rows = [(o.entry_date, o.horizons[h_key]) for o in outcomes if h_key in o.horizons]
        if not rows:
            summary[h_key] = {"count": 0}
            continue
        n = len(rows)
        primary = clustered_test((day, v["excess_return_pct"]) for day, v in rows)
        second_rows = [(day, v["excess_vs_secondary_pct"]) for day, v in rows if "excess_vs_secondary_pct" in v]
        secondary = clustered_test(second_rows) if len(second_rows) == n else None
        test = primary if secondary is None or primary["monthly_mean"] <= secondary["monthly_mean"] else secondary
        conservative = min(primary["mean"], secondary["mean"]) if secondary else primary["mean"]
        stock_stats = compute_sample_statistics([v["stock_return_pct"] for _, v in rows])
        naive = compute_sample_statistics([v["excess_return_pct"] for _, v in rows])
        summary[h_key] = {
            "count": n,
            "months": test["months"],
            "avg_stock_return_pct": stock_stats["mean"],
            "avg_excess_return_pct": primary["mean"],
            "avg_excess_vs_secondary_pct": secondary["mean"] if secondary else None,
            "conservative_excess_pct": round(conservative, 2),
            "net_excess_return_pct": round(conservative - slippage_pct, 2),
            "median_excess_return_pct": primary["median"],
            "win_rate_pct": round(sum(1 for _, v in rows if v["stock_return_pct"] > 0) / n * 100.0, 1),
            "beat_benchmark_rate_pct": round(sum(1 for _, v in rows if v["beat_benchmark"]) / n * 100.0, 1),
            "t_stat": test["t_stat"],
            "t_stat_naive": naive["t_stat"],
            "net_t_stat": naive["t_stat"],
            "p_value": test["p_value"],
            "p_holm": test["p_value"],
            "is_significant": False,
        }
    return summary


_PEAD_SEGMENT_LABELS = {
    "surprise_bucket": {
        "strong_beat_10pct_plus": "Güçlü sürpriz (≥%10)",
        "positive_beat": "Beklentiyi aşan",
        "negative_miss": "Beklentinin altında",
    },
    "trend": {"uptrend": "SMA200 üstü", "downtrend": "SMA200 altı"},
}


def _pead_cell_line(label: str, cell: Dict[str, Any], second: Optional[str]) -> str:
    if not cell.get("count"):
        return f"• {label}: veri yok"
    second_text = (
        f", {second}'ye göre %{cell['avg_excess_vs_secondary_pct']:+.2f}"
        if second and cell.get("avg_excess_vs_secondary_pct") is not None else ""
    )
    verdict = "✅ anlamlı" if cell.get("is_significant") else "tesadüften ayırt edilemiyor"
    return (
        f"• {label}: fazla getiri %{cell.get('avg_excess_return_pct', 0.0):+.2f}{second_text} | "
        f"net (zor kıyas, maliyet sonrası) %{cell.get('net_excess_return_pct', 0.0):+.2f} | "
        f"endeksi geçen %{cell.get('beat_benchmark_rate_pct', 0.0):.0f} | n={cell['count']}, "
        f"{cell.get('months', 0)} ay, t={cell.get('t_stat', 0.0):.2f}, p_holm={cell.get('p_holm', 1.0):.3f} → {verdict}"
    )


def format_pead_study_report(result: Dict[str, Any]) -> str:
    """Turkish text report for :func:`run_pead_event_study` results."""
    bench = result.get("benchmark_symbol", "SPY")
    second = result.get("secondary_benchmark_symbol")
    lines = [
        "📈 Bilanço Sonrası Sürüklenme (PEAD) Geçmiş Testi",
        "=" * 60,
        f"Olay: {result.get('total_events', 0)} bilanço | değerlendirilen: {result.get('evaluated_events', 0)} | "
        f"kıyas: {bench}" + (f" + {second}" if second else "")
        + f" | kayma/komisyon: %{result.get('estimated_slippage_pct', 0.0):.2f}",
        "Giriş: açıklama tepkisinin gerçekleştiği günün kapanışı (ilk gün sıçraması hariç, yalnızca sonraki sürüklenme).",
        f"İstatistik: ay bazlı t; {result.get('tests_corrected', 0)} test birlikte Holm düzeltmesinden geçer.",
        "",
        "Tüm olaylar:",
    ]
    for key, cell in (result.get("horizons") or {}).items():
        lines.append(_pead_cell_line(key, cell, second))
    for group, members in (result.get("segments") or {}).items():
        for member, per_horizon in members.items():
            label = _PEAD_SEGMENT_LABELS.get(group, {}).get(member, member)
            lines.append("")
            lines.append(f"{label}:")
            for key, cell in per_horizon.items():
                lines.append(_pead_cell_line(key, cell, second))
    significant = [
        f"{key}" for key, cell in (result.get("horizons") or {}).items()
        if cell.get("is_significant") and cell.get("net_excess_return_pct", 0) > 0
    ]
    lines.append("")
    lines.append(
        "Sonuç: maliyet sonrası pozitif ve anlamlı ufuk: " + ", ".join(significant) if significant
        else "Sonuç: maliyet sonrası anlamlı pozitif sürüklenme bulunamadı; bu strateji şu haliyle kanıtlanmadı."
    )
    lines.append("Not: yfinance yalnızca son ~3 yılın bilanço tarihlerini verir; geçmiş getiri geleceği garanti etmez.")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_PEAD_HORIZONS",
    "PeadEventOutcome",
    "format_pead_study_report",
    "run_pead_event_study",
]
