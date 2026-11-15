# -*- coding: utf-8 -*-
"""SEC Form 4 Executive Insider Buying Event Study (Historical Alpha vs. S&P 500 / IWM).

Measures whether corporate insider purchases filed on SEC Form 4 generate positive
abnormal returns (Alpha) relative to benchmarks (SPY for S&P 500, IWM for Russell 2000).

Methodology (Cohen, Malloy, Pomorski 2012; Lakonishok & Lee 2001):
1. **No Lookahead Bias**: Trade entry is simulated at the *next trading day's close*
   after the Form 4 filing date.
2. **Total Return**: Uses split- and dividend-adjusted closing prices.
3. **Fixed Forward Horizons**: Evaluates 1 month (21 trading days), 3 months (63
   trading days), and 6 months (126 trading days).
4. **Excess Return vs. Benchmark**:
   ``excess_return_pct = stock_return_pct - benchmark_return_pct``.
5. **Statistical Rigor**:
   Reports mean, median, standard deviation, t-statistic (with significance flag),
   and survivorship / delisting counts to avoid survivorship bias distortion.
6. **Dynamic Segmented Hypotheses**:
   - **Cluster purchases** (>= 2 distinct officers/directors buying within 5 days) vs. Single insider.
   - **C-Suite** (CEO / CFO / COO / President / Chair) vs. Board / Other insiders.
   - **Opportunistic** (CMP non-routine / non-10b5-1) vs. Routine calendar or 10b5-1 plans.
   - **Transaction Size Tiers** ($20k-$50k, $50k-$250k, $250k+).
"""

from __future__ import annotations

import bisect
import concurrent.futures
import json
import logging
import math
import statistics
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from data_provider.sec_form4_fetcher import InsiderClusterEvent
from src.services.event_study_stats import clustered_test, delisting_sensitivity, mark_significance

logger = logging.getLogger(__name__)

DEFAULT_BENCHMARK_SYMBOL = "SPY"
# Insider-buying alpha concentrates in small caps; compare against small caps too.
DEFAULT_SECONDARY_BENCHMARK_SYMBOL = "IWM"
DEFAULT_HORIZONS: Tuple[Tuple[str, int, str], ...] = (
    ("21d", 21, "1 Ay (21 İş Günü)"),
    ("63d", 63, "3 Ay (63 İş Günü)"),
    ("126d", 126, "6 Ay (126 İş Günü)"),
)

HistoryProvider = Callable[[str, date, date], Dict[date, float]]
_cache_lock = threading.Lock()
_memory_history_cache: Dict[Tuple[str, str, str], Tuple[float, Dict[date, float]]] = {}
_MEMORY_TTL = 7200.0
_DISK_CACHE_DIR = Path("data") / "cache" / "sec_form4" / "prices"


def disk_cached_yfinance_history(
    symbol: str,
    start: date,
    end: date,
    *,
    cache_dir: Optional[Path] = None,
) -> Dict[date, float]:
    """Fetch dividend/split-adjusted daily closes from yfinance, cached on disk & memory."""
    sym = symbol.strip().upper()
    key = (sym, start.isoformat(), end.isoformat())

    with _cache_lock:
        mem = _memory_history_cache.get(key)
        if mem and (time.monotonic() - mem[0]) < _MEMORY_TTL:
            return mem[1]

    target_dir = Path(cache_dir or _DISK_CACHE_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    cache_file = target_dir / f"{sym}.json"

    file_data: Dict[str, float] = {}
    if cache_file.is_file():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                file_data = json.load(f)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[sec-form4-study] cache read error %s: %s", sym, exc)

    # Check if existing cached range covers [start, end]
    existing_dates = sorted(file_data.keys())
    start_str = start.isoformat()
    end_str = end.isoformat()
    needs_fetch = True
    if existing_dates and existing_dates[0] <= start_str and existing_dates[-1] >= end_str:
        needs_fetch = False

    if needs_fetch:
        try:
            import yfinance as yf

            # Fetch a slightly wider buffer to minimize future fetches
            fetch_start = min(start - timedelta(days=30), date(2022, 1, 1))
            fetch_end = max(end + timedelta(days=10), date.today())
            frame = yf.Ticker(sym).history(
                start=fetch_start.isoformat(),
                end=(fetch_end + timedelta(days=2)).isoformat(),
                interval="1d",
                auto_adjust=True,  # Total return adjusted for splits & dividends
            )
            for idx, row in frame.iterrows():
                px = float(row.get("Close") or 0.0)
                if px > 0:
                    d_str = idx.date().isoformat()
                    file_data[d_str] = round(px, 4)

            # Persist merged cache to disk
            if file_data:
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(file_data, f)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("[sec-form4-study] cache write error %s: %s", sym, exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[sec-form4-study] yfinance %s failed: %s", sym, exc)

    closes: Dict[date, float] = {}
    for d_str, px in file_data.items():
        try:
            d = date.fromisoformat(d_str)
            if start <= d <= end + timedelta(days=5):
                closes[d] = px
        except ValueError:
            pass

    if closes:
        with _cache_lock:
            _memory_history_cache[key] = (time.monotonic(), closes)
    return closes


class _PriceCalendar:
    """Fast trading-day lookup and forward-bar retrieval."""

    def __init__(self, closes: Dict[date, float]) -> None:
        self.dates = sorted(closes)
        self.closes = closes

    def next_trading_day_close(self, after_date: date) -> Tuple[Optional[date], Optional[float]]:
        idx = bisect.bisect_right(self.dates, after_date)
        if idx < len(self.dates):
            d = self.dates[idx]
            return d, self.closes[d]
        return None, None

    def simple_moving_average(self, as_of_date: date, window: int) -> Optional[float]:
        """Compute simple moving average over ``window`` bars on or before ``as_of_date``."""
        idx = bisect.bisect_right(self.dates, as_of_date)
        if idx < window or window <= 0:
            return None
        window_closes = [self.closes[self.dates[i]] for i in range(idx - window, idx)]
        return sum(window_closes) / float(window)

    def close_after_n_bars(self, from_date: date, n_bars: int) -> Tuple[Optional[date], Optional[float]]:
        idx = bisect.bisect_right(self.dates, from_date)
        target_idx = idx + n_bars - 1
        if 0 <= target_idx < len(self.dates):
            d = self.dates[target_idx]
            return d, self.closes[d]
        return None, None


@dataclass
class Form4EventOutcome:
    """Individual event evaluation with forward return vs. benchmark."""

    symbol: str
    company_name: str
    filing_date: date
    entry_date: date
    entry_price: float
    total_value: float
    insider_count: int
    has_c_level: bool
    is_opportunistic: bool
    is_cluster: bool
    cmp_class: str
    has_10b51: bool
    primary_titles: List[str]
    horizons: Dict[str, Dict[str, Any]]
    trend_regime: str = "unclassified"  # uptrend | downtrend | unclassified
    sma200: Optional[float] = None
    sma50: Optional[float] = None


def compute_sample_statistics(values: Sequence[float]) -> Dict[str, Any]:
    """Compute mean, median, stdev, standard error, and t-statistic against null hypothesis 0.0."""
    n = len(values)
    if n == 0:
        return {
            "count": 0,
            "mean": 0.0,
            "median": 0.0,
            "stdev": 0.0,
            "stderr": 0.0,
            "t_stat": 0.0,
            "is_significant": False,
        }
    mean_val = sum(values) / n
    med_val = statistics.median(values) if n > 0 else 0.0
    stdev_val = statistics.stdev(values) if n > 1 else 0.0
    stderr_val = (stdev_val / math.sqrt(n)) if n > 1 else 0.0
    t_stat = (mean_val / stderr_val) if stderr_val > 0 else 0.0
    # Two-tailed 95% significance threshold (|t| >= 1.96 for large N, approx 2.0)
    is_significant = abs(t_stat) >= 1.96 and n >= 15
    return {
        "count": n,
        "mean": round(mean_val, 2),
        "median": round(med_val, 2),
        "stdev": round(stdev_val, 2),
        "stderr": round(stderr_val, 2),
        "t_stat": round(t_stat, 2),
        "is_significant": is_significant,
    }


def run_sec_form4_event_study(
    events: Sequence[InsiderClusterEvent],
    *,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    history: HistoryProvider = disk_cached_yfinance_history,
    horizons: Sequence[Tuple[str, int, str]] = DEFAULT_HORIZONS,
    min_value: float = 20_000.0,
    max_events: Optional[int] = None,
    estimated_slippage_pct: float = 0.5,
    secondary_benchmark_symbol: Optional[str] = DEFAULT_SECONDARY_BENCHMARK_SYMBOL,
) -> Dict[str, Any]:
    """Calculate forward returns vs. benchmark for a sequence of Form 4 events.

    Rigor rules: a stock that stops trading before the horizon exits at its last
    close (``delisted``) instead of being dropped; excess returns are measured
    against both the primary and the small-cap benchmark and the lower of the two
    is used for conclusions; significance uses calendar-month clustered t-stats
    with a Holm correction across every reported cell.
    """
    filtered_events = [e for e in events if e.total_value >= min_value]
    if max_events is not None and len(filtered_events) > max_events:
        filtered_events = filtered_events[:max_events]

    if not filtered_events:
        return {
            "total_events": 0,
            "evaluated_events": 0,
            "missing_events": 0,
            "benchmark_symbol": benchmark_symbol,
            "horizons": {},
            "segments": {},
            "missing_symbols": [],
        }

    min_date = min(e.filing_date for e in filtered_events)
    max_horizon_days = max(bars for _, bars, _ in horizons) * 2 + 30
    study_end_date = max(e.filing_date for e in filtered_events) + timedelta(days=max_horizon_days)

    # 1. Fetch benchmark price series (with 320 days pre-history for moving averages)
    bench_start = min_date - timedelta(days=320)
    bench_closes = history(benchmark_symbol, bench_start, study_end_date)
    bench_cal = _PriceCalendar(bench_closes)
    second_cal: Optional[_PriceCalendar] = None
    if secondary_benchmark_symbol and secondary_benchmark_symbol != benchmark_symbol:
        second_closes = history(secondary_benchmark_symbol, bench_start, study_end_date)
        second_cal = _PriceCalendar(second_closes) if second_closes else None

    # 2. Parallel pre-fetch of unique stock price series
    outcomes: List[Form4EventOutcome] = []
    symbol_caches: Dict[str, _PriceCalendar] = {}
    missing_symbols: Set[str] = set()

    unique_symbols = sorted({e.symbol for e in filtered_events if e.symbol})
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, max(2, len(unique_symbols)))) as executor:
        futures = {
            executor.submit(history, sym, bench_start, study_end_date): sym
            for sym in unique_symbols
        }
        for future in concurrent.futures.as_completed(futures):
            sym = futures[future]
            try:
                closes = future.result()
                if closes:
                    symbol_caches[sym] = _PriceCalendar(closes)
                else:
                    missing_symbols.add(sym)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[sec-form4-study] parallel fetch error %s: %s", sym, exc)
                missing_symbols.add(sym)

    for event in filtered_events:
        sym = event.symbol
        stock_cal = symbol_caches.get(sym)
        if stock_cal is None or not stock_cal.dates:
            missing_symbols.add(sym)
            continue

        entry_date, entry_price = stock_cal.next_trading_day_close(event.filing_date)
        if entry_date is None or entry_price is None:
            missing_symbols.add(sym)
            continue

        _, bench_entry = bench_cal.next_trading_day_close(event.filing_date)
        if bench_entry is None:
            continue

        sma200 = stock_cal.simple_moving_average(entry_date, 200)
        sma50 = stock_cal.simple_moving_average(entry_date, 50)
        if sma200 is not None:
            trend_regime = "uptrend" if entry_price > sma200 else "downtrend"
        else:
            trend_regime = "unclassified"

        second_entry = second_cal.next_trading_day_close(event.filing_date)[1] if second_cal else None
        horizon_results: Dict[str, Dict[str, Any]] = {}
        for h_key, n_bars, h_label in horizons:
            stock_exit_date, stock_exit_price = stock_cal.close_after_n_bars(entry_date, n_bars)
            bench_exit_date, bench_exit_price = bench_cal.close_after_n_bars(entry_date, n_bars)
            delisted = False
            if stock_exit_price is None and bench_exit_date is not None and stock_cal.dates:
                # The market reached the horizon but the stock stopped trading:
                # exit at its last close instead of silently dropping the loser.
                last_day = stock_cal.dates[-1]
                if entry_date < last_day < bench_exit_date:
                    stock_exit_date, stock_exit_price, delisted = last_day, stock_cal.closes[last_day], True

            if (
                stock_exit_price is not None
                and bench_exit_price is not None
                and stock_exit_date is not None
            ):
                stock_ret = (stock_exit_price / entry_price - 1.0) * 100.0
                bench_ret = (bench_exit_price / bench_entry - 1.0) * 100.0
                excess = stock_ret - bench_ret
                result = {
                    "label": h_label,
                    "n_bars": n_bars,
                    "exit_date": stock_exit_date.isoformat(),
                    "stock_return_pct": round(stock_ret, 2),
                    "benchmark_return_pct": round(bench_ret, 2),
                    "excess_return_pct": round(excess, 2),
                    "beat_benchmark": excess > 0,
                    "delisted": delisted,
                }
                if second_cal is not None and second_entry:
                    _, second_exit = second_cal.close_after_n_bars(entry_date, n_bars)
                    if second_exit:
                        second_ret = (second_exit / second_entry - 1.0) * 100.0
                        result["excess_vs_secondary_pct"] = round(stock_ret - second_ret, 2)
                horizon_results[h_key] = result

        if horizon_results:
            outcomes.append(Form4EventOutcome(
                symbol=sym,
                company_name=event.company_name,
                filing_date=event.filing_date,
                entry_date=entry_date,
                entry_price=round(entry_price, 4),
                total_value=event.total_value,
                insider_count=event.insider_count,
                has_c_level=event.has_c_level,
                is_opportunistic=event.is_opportunistic or (not event.has_10b51 and event.cmp_class != "routine"),
                is_cluster=event.is_cluster,
                cmp_class=event.cmp_class,
                has_10b51=event.has_10b51,
                primary_titles=event.primary_titles,
                horizons=horizon_results,
                trend_regime=trend_regime,
                sma200=round(sma200, 4) if sma200 else None,
                sma50=round(sma50, 4) if sma50 else None,
            ))

    # 3. Compute aggregate statistics across horizons and segments
    horizon_aggregates = _aggregate_horizon_metrics(outcomes, [h[0] for h in horizons], estimated_slippage_pct)
    segments = {
        "cluster_vs_single": {
            "cluster": _aggregate_horizon_metrics([o for o in outcomes if o.is_cluster], [h[0] for h in horizons], estimated_slippage_pct),
            "single": _aggregate_horizon_metrics([o for o in outcomes if not o.is_cluster], [h[0] for h in horizons], estimated_slippage_pct),
        },
        "role": {
            "c_suite": _aggregate_horizon_metrics([o for o in outcomes if o.has_c_level], [h[0] for h in horizons], estimated_slippage_pct),
            "board_other": _aggregate_horizon_metrics([o for o in outcomes if not o.has_c_level], [h[0] for h in horizons], estimated_slippage_pct),
        },
        "opportunistic": {
            "cmp_opportunistic": _aggregate_horizon_metrics([o for o in outcomes if o.cmp_class == "opportunistic"], [h[0] for h in horizons], estimated_slippage_pct),
            "cmp_routine": _aggregate_horizon_metrics([o for o in outcomes if o.cmp_class == "routine"], [h[0] for h in horizons], estimated_slippage_pct),
            "non_10b51": _aggregate_horizon_metrics([o for o in outcomes if not o.has_10b51], [h[0] for h in horizons], estimated_slippage_pct),
            "rule_10b51": _aggregate_horizon_metrics([o for o in outcomes if o.has_10b51], [h[0] for h in horizons], estimated_slippage_pct),
        },
        "size_tier": {
            "tier_20k_50k": _aggregate_horizon_metrics([o for o in outcomes if 20_000 <= o.total_value < 50_000], [h[0] for h in horizons], estimated_slippage_pct),
            "tier_50k_250k": _aggregate_horizon_metrics([o for o in outcomes if 50_000 <= o.total_value < 250_000], [h[0] for h in horizons], estimated_slippage_pct),
            "tier_250k_plus": _aggregate_horizon_metrics([o for o in outcomes if o.total_value >= 250_000], [h[0] for h in horizons], estimated_slippage_pct),
        },
        "trend": {
            "uptrend": _aggregate_horizon_metrics([o for o in outcomes if o.trend_regime == "uptrend"], [h[0] for h in horizons], estimated_slippage_pct),
            "downtrend": _aggregate_horizon_metrics([o for o in outcomes if o.trend_regime == "downtrend"], [h[0] for h in horizons], estimated_slippage_pct),
        },
    }

    # Holm correction across every cell reported together (overall + all segments).
    cells: Dict[str, Dict[str, Any]] = {}
    for h_key, cell in horizon_aggregates.items():
        if cell.get("count"):
            cells[f"all:{h_key}"] = cell
    for group, members in segments.items():
        for member, per_horizon in members.items():
            for h_key, cell in per_horizon.items():
                if cell.get("count"):
                    cells[f"{group}.{member}:{h_key}"] = cell
    mark_significance(cells)
    missing_events = len(filtered_events) - len(outcomes)
    for h_key, cell in horizon_aggregates.items():
        if cell.get("count"):
            observed = [o.horizons[h_key]["excess_return_pct"] for o in outcomes if h_key in o.horizons]
            cell["delisting_adjusted_excess_pct"] = delisting_sensitivity(observed, missing_events)

    return {
        "total_events": len(filtered_events),
        "evaluated_events": len(outcomes),
        "missing_events": missing_events,
        "missing_symbols": sorted(missing_symbols),
        "benchmark_symbol": benchmark_symbol,
        "secondary_benchmark_symbol": secondary_benchmark_symbol if second_cal is not None else None,
        "tests_corrected": len(cells),
        "estimated_slippage_pct": estimated_slippage_pct,
        "horizons": horizon_aggregates,
        "segments": segments,
        "sample_events": [
            {
                "symbol": o.symbol,
                "company_name": o.company_name,
                "filing_date": o.filing_date.isoformat(),
                "total_value": o.total_value,
                "insiders": o.insider_count,
                "c_level": o.has_c_level,
                "cmp_class": o.cmp_class,
                "has_10b51": o.has_10b51,
                "horizons": {k: v.get("excess_return_pct") for k, v in o.horizons.items()},
            }
            for o in outcomes[:10]
        ],
    }


def _aggregate_horizon_metrics(
    outcomes: Sequence[Form4EventOutcome],
    horizon_keys: Sequence[str],
    slippage_pct: float = 0.5,
) -> Dict[str, Dict[str, Any]]:
    """Aggregate returns per horizon with calendar-month clustered statistics.

    ``conservative_excess_pct`` is the lower of the excess returns against the
    primary and secondary (small-cap) benchmark; ``net_excess_return_pct`` is
    that minus estimated slippage. ``is_significant`` is set later by
    :func:`mark_significance` (Holm across all cells).
    """
    summary: Dict[str, Dict[str, Any]] = {}
    for h_key in horizon_keys:
        rows = [(o.entry_date, o.horizons[h_key]) for o in outcomes if h_key in o.horizons]
        count = len(rows)
        if count == 0:
            summary[h_key] = {"count": 0}
            continue
        stock_rets = [item["stock_return_pct"] for _, item in rows]
        bench_rets = [item["benchmark_return_pct"] for _, item in rows]
        primary = clustered_test((day, item["excess_return_pct"]) for day, item in rows)
        secondary_rows = [(day, item["excess_vs_secondary_pct"]) for day, item in rows
                          if "excess_vs_secondary_pct" in item]
        secondary = clustered_test(secondary_rows) if len(secondary_rows) == count else None
        # Conclusions rest on the benchmark that is harder to beat.
        test = primary if secondary is None or primary["monthly_mean"] <= secondary["monthly_mean"] else secondary
        conservative = min(primary["mean"], secondary["mean"]) if secondary else primary["mean"]
        naive = compute_sample_statistics([item["excess_return_pct"] for _, item in rows])
        beats = sum(1 for _, item in rows if item["beat_benchmark"])
        summary[h_key] = {
            "count": count,
            "months": test["months"],
            "delisted_count": sum(1 for _, item in rows if item.get("delisted")),
            "avg_stock_return_pct": compute_sample_statistics(stock_rets)["mean"],
            "median_stock_return_pct": compute_sample_statistics(stock_rets)["median"],
            "avg_benchmark_return_pct": compute_sample_statistics(bench_rets)["mean"],
            "median_benchmark_return_pct": compute_sample_statistics(bench_rets)["median"],
            "avg_excess_return_pct": primary["mean"],
            "median_excess_return_pct": primary["median"],
            "avg_excess_vs_secondary_pct": secondary["mean"] if secondary else None,
            "conservative_excess_pct": round(conservative, 2),
            "net_excess_return_pct": round(conservative - slippage_pct, 2),
            "stdev_excess_pct": naive["stdev"],
            "t_stat": test["t_stat"],
            "t_stat_naive": naive["t_stat"],
            "p_value": test["p_value"],
            "p_holm": test["p_value"],
            "is_significant": False,
            "win_rate_pct": round((beats / count) * 100.0, 1),
            "win_count": beats,
        }
    return summary


def _compare_segments(name: str, left_label: str, left: Dict[str, Any],
                      right_label: str, right: Dict[str, Any]) -> Optional[str]:
    """Describe a segment difference without claiming more than the data supports."""
    if left.get("count", 0) < 3 or right.get("count", 0) < 3:
        return None
    left_exc = left.get("conservative_excess_pct", left.get("avg_excess_return_pct", 0.0))
    right_exc = right.get("conservative_excess_pct", right.get("avg_excess_return_pct", 0.0))
    diff = left_exc - right_exc
    if abs(diff) <= 1.0:
        return f"⚖️ {name}: {left_label} %{left_exc:+.2f} vs {right_label} %{right_exc:+.2f} — belirgin fark yok."
    better_label, better = (left_label, left) if diff > 0 else (right_label, right)
    if better.get("is_significant"):
        return (f"✅ {name}: {better_label} daha iyi ({left_label} %{left_exc:+.2f} vs {right_label} %{right_exc:+.2f}) "
                f"ve bu grup çoklu test düzeltmesinden sonra da anlamlı (p_holm={better.get('p_holm', 1.0):.3f}).")
    return (f"🟡 {name}: {left_label} %{left_exc:+.2f} vs {right_label} %{right_exc:+.2f}; fark var ama "
            f"istatistiksel olarak kanıtlanmadı (p_holm={better.get('p_holm', 1.0):.3f}). Karar için yeterli değil.")


def _generate_dynamic_conclusions(results: Dict[str, Any]) -> List[str]:
    """Generate dynamic findings based strictly on measured event study data (No static claims)."""
    conclusions: List[str] = []
    evaluated = results.get("evaluated_events", 0)
    missing = results.get("missing_events", 0)
    bench = results.get("benchmark_symbol", "SPY")
    h_data = results.get("horizons", {})
    seg = results.get("segments", {})

    # 1. Sample Size & Survivorship Warning
    if evaluated < 30:
        conclusions.append(
            f"⚠️ Örneklem uyarısı: Yalnızca {evaluated} işlem tamamlandı. Güvenilir istatistiksel sonuç "
            f"için en az 30-50 işlem gerekir (N={evaluated} için hata payı yüksektir)."
        )
    if missing > 0:
        conclusions.append(
            f"ℹ️ Hayatta kalma takibi: {missing} işlem borsa kotundan çıkmış veya fiyatı bulunamamıştır. "
            f"Bu şirketler çoğunlukla iflas/satın alma riski taşıyan mikro ölçekli hisselerdir."
        )

    # 2. Overall Performance & Significance (clustered by month, Holm-corrected)
    d21 = h_data.get("21d", {})
    if d21.get("count", 0) > 0:
        second = results.get("secondary_benchmark_symbol")
        vs_second = d21.get("avg_excess_vs_secondary_pct")
        second_text = f", {second}'ye göre %{vs_second:+.2f}" if second and vs_second is not None else ""
        sig_text = (
            "çoklu test düzeltmesinden sonra anlamlı" if d21.get("is_significant")
            else "tesadüften ayırt edilemiyor"
        )
        conclusions.append(
            f"📊 1 Aylık fazla getiri: {bench}'ye göre %{d21.get('avg_excess_return_pct', 0.0):+.2f}{second_text} "
            f"(medyan %{d21.get('median_excess_return_pct', 0.0):+.2f}). Ay bazlı t={d21.get('t_stat', 0.0):.2f}, "
            f"{d21.get('months', 0)} ay, p_holm={d21.get('p_holm', 1.0):.3f} → {sig_text}. "
            f"Zor kıyasa göre, maliyet sonrası net: %{d21.get('net_excess_return_pct', 0.0):+.2f}."
        )
        adjusted = d21.get("delisting_adjusted_excess_pct")
        if missing > 0 and adjusted is not None:
            conclusions.append(
                f"🧮 Hayatta kalma duyarlılığı: fiyatı bulunamayan {missing} olay %-30 kaybetmiş sayılırsa "
                f"1 aylık ortalama fazla getiri %{adjusted:+.2f} olur."
            )

    comparisons = (
        ("Küme alımı", "cluster_vs_single", ("Küme", "cluster"), ("Tek", "single")),
        ("Rol", "role", ("C-Suite", "c_suite"), ("Kurul/Diğer", "board_other")),
        ("10b5-1", "opportunistic", ("Plansız", "non_10b51"), ("10b5-1 planlı", "rule_10b51")),
        ("CMP sınıfı", "opportunistic", ("Fırsatçı", "cmp_opportunistic"), ("Rutin", "cmp_routine")),
        ("Trend", "trend", ("SMA200 üstü", "uptrend"), ("SMA200 altı", "downtrend")),
    )
    for name, group, (left_label, left_key), (right_label, right_key) in comparisons:
        members = seg.get(group, {})
        line = _compare_segments(
            name, left_label, members.get(left_key, {}).get("21d", {}),
            right_label, members.get(right_key, {}).get("21d", {}),
        )
        if line:
            conclusions.append(line)

    return conclusions


def format_sec_form4_study_report(results: Dict[str, Any]) -> str:
    """Format academic event study findings into clean Turkish text with statistical rigor."""
    total = results.get("total_events", 0)
    evaluated = results.get("evaluated_events", 0)
    missing = results.get("missing_events", 0)
    bench = results.get("benchmark_symbol", "SPY")
    slip = results.get("estimated_slippage_pct", 0.5)

    survival_pct = (evaluated / total * 100.0) if total > 0 else 0.0
    lines = [
        "🏛️ ABD Yönetici Alımları (SEC Form 4) Geçmiş Etki ve Alfa Raporu",
        "=" * 66,
        f"Örneklem: {total} incelenen alım olayı | {evaluated} tamamlanan getiri penceresi (%{survival_pct:.1f} kapsama)",
        f"Kıyas Endeksi: {bench}"
        + (f" + küçük şirket kıyası {results['secondary_benchmark_symbol']} (sonuçlar zor olana göre)"
           if results.get("secondary_benchmark_symbol") else "")
        + f" | Varsayılan Alış-Satış Kayması/Komisyon: %{slip:.2f}",
        "Kural: Bildirimin ertesi işlem günü kapanışında alım; önceden bilme yanılgısı (lookahead) sıfırdır.",
        "İstatistik: aynı aydaki olaylar tek gözlem sayılır (ay bazlı t); "
        f"{results.get('tests_corrected', 0)} test birlikte Holm düzeltmesinden geçer. "
        "Borsadan çıkan hisseler son fiyatından çıkış yapar.",
        "",
        "📊 1. GENEL PERFORMANS (Tüm Yönetici Alımları)",
        "-" * 66,
    ]

    h_data = results.get("horizons", {})
    for h_key, _, label in DEFAULT_HORIZONS:
        data = h_data.get(h_key, {})
        cnt = data.get("count", 0)
        if cnt == 0:
            lines.append(f"• {label}: Yeterli ileri gün kapanış verisi henüz oluşmadı")
            continue
        stk = data.get("avg_stock_return_pct", 0.0)
        med_stk = data.get("median_stock_return_pct", 0.0)
        b_ret = data.get("avg_benchmark_return_pct", 0.0)
        exc = data.get("avg_excess_return_pct", 0.0)
        med_exc = data.get("median_excess_return_pct", 0.0)
        net_exc = data.get("net_excess_return_pct", 0.0)
        t_stat = data.get("t_stat", 0.0)
        sig = " ✅anlamlı" if data.get("is_significant") else ""
        win = data.get("win_rate_pct", 0.0)
        sign = "+" if exc >= 0 else ""
        second = data.get("avg_excess_vs_secondary_pct")
        second_text = f" | {results.get('secondary_benchmark_symbol')}'ye göre %{second:+.2f}" if second is not None else ""
        lines.append(
            f"• {label:<22}: Hisse %{stk:+.2f} (Medyan %{med_stk:+.2f}) | {bench} %{b_ret:+.2f} | "
            f"Alfa: {sign}%{exc:.2f}{second_text} (Net, zor kıyas: %{net_exc:+.2f}) | Medyan Alfa: %{med_exc:+.2f} | "
            f"ay bazlı t={t_stat:.2f}, {data.get('months', 0)} ay, p_holm={data.get('p_holm', 1.0):.3f}{sig} | "
            f"Kazanma: %{win:.1f} ({cnt} işlem, {data.get('delisted_count', 0)} borsadan çıkan)"
        )

    # Segments
    seg = results.get("segments", {})
    lines.extend([
        "",
        "🔬 2. AKADEMİK HİPOTEZ VE SEGMENT SINAMALARI",
        "-" * 66,
    ])

    # A. Cluster vs Single
    clust = seg.get("cluster_vs_single", {})
    c_21 = clust.get("cluster", {}).get("21d", {})
    s_21 = clust.get("single", {}).get("21d", {})
    c_63 = clust.get("cluster", {}).get("63d", {})
    s_63 = clust.get("single", {}).get("63d", {})
    lines.append("A) Küme Alımı (>= 2 Yönetici Aynı Anda) vs. Tek Yönetici:")
    if c_21.get("count", 0) > 0 and s_21.get("count", 0) > 0:
        lines.append(
            f"   - 1 Ay (21g) Alfa: Küme Alımı %{c_21.get('avg_excess_return_pct', 0):+.2f} "
            f"(Kazanma %{c_21.get('win_rate_pct', 0):.0f}, N={c_21.get('count', 0)}) vs. "
            f"Tek Yönetici %{s_21.get('avg_excess_return_pct', 0):+.2f} (N={s_21.get('count', 0)})"
        )
    if c_63.get("count", 0) > 0 and s_63.get("count", 0) > 0:
        lines.append(
            f"   - 3 Ay (63g) Alfa: Küme Alımı %{c_63.get('avg_excess_return_pct', 0):+.2f} vs. "
            f"Tek Yönetici %{s_63.get('avg_excess_return_pct', 0):+.2f}"
        )

    # B. C-Suite vs Board
    role = seg.get("role", {})
    cs_21 = role.get("c_suite", {}).get("21d", {})
    bo_21 = role.get("board_other", {}).get("21d", {})
    lines.append("B) Üst Yönetim (CEO / CFO / Başkan) vs. Yönetim Kurulu / Diğer:")
    if cs_21.get("count", 0) > 0 and bo_21.get("count", 0) > 0:
        lines.append(
            f"   - 1 Ay (21g) Alfa: C-Suite %{cs_21.get('avg_excess_return_pct', 0):+.2f} (N={cs_21.get('count', 0)}) vs. "
            f"Diğer %{bo_21.get('avg_excess_return_pct', 0):+.2f} (N={bo_21.get('count', 0)})"
        )

    # C. Opportunistic vs 10b5-1
    opp = seg.get("opportunistic", {})
    no_10b_21 = opp.get("non_10b51", {}).get("21d", {})
    yes_10b_21 = opp.get("rule_10b51", {}).get("21d", {})
    lines.append("C) Fırsatçı Alım vs. Rutin Önceden Planlı Alım (Rule 10b5-1):")
    if no_10b_21.get("count", 0) > 0:
        yes_str = f"vs. 10b5-1 Planlı %{yes_10b_21.get('avg_excess_return_pct', 0):+.2f} (N={yes_10b_21.get('count', 0)})" if yes_10b_21.get("count", 0) > 0 else "(Yeterli 10b5-1 alım yok)"
        lines.append(
            f"   - 1 Ay (21g) Alfa: Plansız/Fırsatçı %{no_10b_21.get('avg_excess_return_pct', 0):+.2f} (N={no_10b_21.get('count', 0)}) {yes_str}"
        )

    # D. Transaction Size Tiers
    size_t = seg.get("size_tier", {})
    t1 = size_t.get("tier_20k_50k", {}).get("21d", {})
    t2 = size_t.get("tier_50k_250k", {}).get("21d", {})
    t3 = size_t.get("tier_250k_plus", {}).get("21d", {})
    if any(item.get("count", 0) > 0 for item in (t1, t2, t3)):
        lines.append("D) Tutar Ölçeği ($20k-$50k / $50k-$250k / $250k+):")
        lines.append(
            f"   - 1 Ay (21g) Alfa: $20k-$50k: %{t1.get('avg_excess_return_pct', 0):+.2f} | "
            f"$50k-$250k: %{t2.get('avg_excess_return_pct', 0):+.2f} | "
            f"$250k+: %{t3.get('avg_excess_return_pct', 0):+.2f}"
        )

    # E. Trend / Momentum Confluence (SMA 200)
    trend_seg = seg.get("trend", {})
    up_21 = trend_seg.get("uptrend", {}).get("21d", {})
    down_21 = trend_seg.get("downtrend", {}).get("21d", {})
    if up_21.get("count", 0) > 0 or down_21.get("count", 0) > 0:
        lines.append("E) Trend / Momentum Kesişimi (Fiyat > SMA 200 vs. SMA 200 Altı):")
        up_str = f"SMA200 Üstü (Yükseliş Trendi): %{up_21.get('avg_excess_return_pct', 0):+.2f} (N={up_21.get('count', 0)}, Kazanma: %{up_21.get('win_rate_pct', 0):.0f})" if up_21.get("count", 0) > 0 else "SMA200 Üstü: Yetersiz veri"
        down_str = f"SMA200 Altı (Düşüş Trendi): %{down_21.get('avg_excess_return_pct', 0):+.2f} (N={down_21.get('count', 0)}, Kazanma: %{down_21.get('win_rate_pct', 0):.0f})" if down_21.get("count", 0) > 0 else "SMA200 Altı: Yetersiz veri"
        lines.append(f"   - 1 Ay (21g) Alfa: {up_str} vs. {down_str}")

    # 3. Dynamic Findings / Conclusions
    lines.extend([
        "",
        "💡 VERİYE DAYALI BULGULAR VE ANALİZ:",
    ])
    dynamic_notes = _generate_dynamic_conclusions(results)
    for note in dynamic_notes:
        lines.append(note)

    return "\n".join(lines)


__all__ = [
    "DEFAULT_BENCHMARK_SYMBOL",
    "DEFAULT_HORIZONS",
    "Form4EventOutcome",
    "compute_sample_statistics",
    "disk_cached_yfinance_history",
    "format_sec_form4_study_report",
    "run_sec_form4_event_study",
]
