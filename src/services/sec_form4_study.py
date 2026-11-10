# -*- coding: utf-8 -*-
"""SEC Form 4 Executive Insider Buying Event Study (Historical Alpha vs. S&P 500).

Measures whether corporate insider purchases filed on SEC Form 4 generate positive
abnormal returns (Alpha) relative to the S&P 500 benchmark (SPY / ^GSPC).

Methodology (Cohen, Malloy, Pomorski 2012; Lakonishok & Lee 2001):
1. **No Lookahead Bias**: Trade entry is simulated at the *next trading day's close*
   after the Form 4 filing date.
2. **Fixed Forward Horizons**: Evaluates 1 month (21 trading days), 3 months (63
   trading days), and 6 months (126 trading days).
3. **Excess Return vs. S&P 500**:
   ``excess_return_pct = stock_return_pct - spy_return_pct`` over the identical
   holding period.
4. **Segmented Hypothesis Testing**:
   - **Cluster purchases** (>= 2 distinct insiders buying within 5 days) vs. Single insider.
   - **C-Suite** (CEO / CFO / COO) vs. Board / Other insiders.
   - **Opportunistic** (non-10b5-1) vs. Routine 10b5-1 pre-planned plans.
   - **Transaction Size Tiers** ($20k-$50k, $50k-$250k, $250k+).
"""

from __future__ import annotations

import bisect
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from data_provider.sec_form4_fetcher import InsiderClusterEvent, SecForm4Fetcher

logger = logging.getLogger(__name__)

DEFAULT_BENCHMARK_SYMBOL = "SPY"
DEFAULT_HORIZONS: Tuple[Tuple[str, int, str], ...] = (
    ("21d", 21, "1 Ay (21 İş Günü)"),
    ("63d", 63, "3 Ay (63 İş Günü)"),
    ("126d", 126, "6 Ay (126 İş Günü)"),
)

HistoryProvider = Callable[[str, date, date], Dict[date, float]]
_cache_lock = threading.Lock()
_history_cache: Dict[Tuple[str, str, str], Tuple[float, Dict[date, float]]] = {}
_HISTORY_TTL = 3600.0


def default_yfinance_history(symbol: str, start: date, end: date) -> Dict[date, float]:
    """Fetch daily closes for a US stock or benchmark via yfinance (cached 1 hour)."""
    key = (symbol.upper(), start.isoformat(), end.isoformat())
    with _cache_lock:
        cached = _history_cache.get(key)
        if cached and (time.monotonic() - cached[0]) < _HISTORY_TTL:
            return cached[1]
    closes: Dict[date, float] = {}
    try:
        import yfinance as yf

        frame = yf.Ticker(symbol).history(
            start=start.isoformat(),
            end=(end + timedelta(days=2)).isoformat(),
            interval="1d",
            auto_adjust=False,
        )
        for idx, row in frame.iterrows():
            px = float(row.get("Close") or 0.0)
            if px > 0:
                closes[idx.date()] = round(px, 4)
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.debug("[sec-form4-study] yfinance %s failed: %s", symbol, exc)
        return {}

    if closes:
        with _cache_lock:
            _history_cache[key] = (time.monotonic(), closes)
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

    def close_after_n_bars(self, from_date: date, n_bars: int) -> Tuple[Optional[date], Optional[float]]:
        idx = bisect.bisect_right(self.dates, from_date)
        target_idx = idx + n_bars - 1
        if 0 <= target_idx < len(self.dates):
            d = self.dates[target_idx]
            return d, self.closes[d]
        return None, None


@dataclass
class Form4EventOutcome:
    """Individual event evaluation with forward return vs. S&P 500."""

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
    primary_titles: List[str]
    horizons: Dict[str, Dict[str, Any]]


def run_sec_form4_event_study(
    events: Sequence[InsiderClusterEvent],
    *,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    history: HistoryProvider = default_yfinance_history,
    horizons: Sequence[Tuple[str, int, str]] = DEFAULT_HORIZONS,
    min_value: float = 20_000.0,
    max_events: Optional[int] = None,
) -> Dict[str, Any]:
    """Calculate forward returns vs. S&P 500 for a sequence of Form 4 events."""
    filtered_events = [e for e in events if e.total_value >= min_value]
    if max_events is not None and len(filtered_events) > max_events:
        filtered_events = filtered_events[:max_events]

    if not filtered_events:
        return {
            "total_events": 0,
            "evaluated_events": 0,
            "benchmark_symbol": benchmark_symbol,
            "horizons": {},
            "segments": {},
        }

    min_date = min(e.filing_date for e in filtered_events)
    max_horizon_days = max(bars for _, bars, _ in horizons) * 2 + 30
    study_end_date = max(e.filing_date for e in filtered_events) + timedelta(days=max_horizon_days)

    # 1. Fetch benchmark price series
    bench_closes = history(benchmark_symbol, min_date - timedelta(days=10), study_end_date)
    bench_cal = _PriceCalendar(bench_closes)

    # 2. Evaluate each event
    outcomes: List[Form4EventOutcome] = []
    symbol_caches: Dict[str, _PriceCalendar] = {}

    for event in filtered_events:
        sym = event.symbol
        if sym not in symbol_caches:
            sym_closes = history(sym, event.filing_date - timedelta(days=5), study_end_date)
            symbol_caches[sym] = _PriceCalendar(sym_closes)
        stock_cal = symbol_caches[sym]

        entry_date, entry_price = stock_cal.next_trading_day_close(event.filing_date)
        if entry_date is None or entry_price is None:
            continue

        _, bench_entry = bench_cal.next_trading_day_close(event.filing_date)
        if bench_entry is None:
            continue

        horizon_results: Dict[str, Dict[str, Any]] = {}
        for h_key, n_bars, h_label in horizons:
            stock_exit_date, stock_exit_price = stock_cal.close_after_n_bars(entry_date, n_bars)
            bench_exit_date, bench_exit_price = bench_cal.close_after_n_bars(entry_date, n_bars)

            if (
                stock_exit_price is not None
                and bench_exit_price is not None
                and stock_exit_date is not None
            ):
                stock_ret = (stock_exit_price / entry_price - 1.0) * 100.0
                bench_ret = (bench_exit_price / bench_entry - 1.0) * 100.0
                excess = stock_ret - bench_ret
                horizon_results[h_key] = {
                    "label": h_label,
                    "n_bars": n_bars,
                    "exit_date": stock_exit_date.isoformat(),
                    "stock_return_pct": round(stock_ret, 2),
                    "benchmark_return_pct": round(bench_ret, 2),
                    "excess_return_pct": round(excess, 2),
                    "beat_benchmark": excess > 0,
                }

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
                is_opportunistic=event.is_opportunistic,
                is_cluster=event.is_cluster,
                primary_titles=event.primary_titles,
                horizons=horizon_results,
            ))

    # 3. Compute aggregate statistics across horizons and segments
    horizon_aggregates = _aggregate_horizon_metrics(outcomes, [h[0] for h in horizons])
    segments = {
        "cluster_vs_single": {
            "cluster": _aggregate_horizon_metrics([o for o in outcomes if o.is_cluster], [h[0] for h in horizons]),
            "single": _aggregate_horizon_metrics([o for o in outcomes if not o.is_cluster], [h[0] for h in horizons]),
        },
        "role": {
            "c_suite": _aggregate_horizon_metrics([o for o in outcomes if o.has_c_level], [h[0] for h in horizons]),
            "board_other": _aggregate_horizon_metrics([o for o in outcomes if not o.has_c_level], [h[0] for h in horizons]),
        },
        "opportunistic": {
            "non_10b51": _aggregate_horizon_metrics([o for o in outcomes if o.is_opportunistic], [h[0] for h in horizons]),
            "rule_10b51": _aggregate_horizon_metrics([o for o in outcomes if not o.is_opportunistic], [h[0] for h in horizons]),
        },
        "size_tier": {
            "tier_20k_50k": _aggregate_horizon_metrics([o for o in outcomes if 20_000 <= o.total_value < 50_000], [h[0] for h in horizons]),
            "tier_50k_250k": _aggregate_horizon_metrics([o for o in outcomes if 50_000 <= o.total_value < 250_000], [h[0] for h in horizons]),
            "tier_250k_plus": _aggregate_horizon_metrics([o for o in outcomes if o.total_value >= 250_000], [h[0] for h in horizons]),
        },
    }

    return {
        "total_events": len(filtered_events),
        "evaluated_events": len(outcomes),
        "benchmark_symbol": benchmark_symbol,
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
                "opportunistic": o.is_opportunistic,
                "horizons": {k: v.get("excess_return_pct") for k, v in o.horizons.items()},
            }
            for o in outcomes[:10]
        ],
    }


def _aggregate_horizon_metrics(
    outcomes: Sequence[Form4EventOutcome],
    horizon_keys: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    """Aggregate stock returns, benchmark returns, excess alpha and win rate for a slice."""
    summary: Dict[str, Dict[str, Any]] = {}
    for h_key in horizon_keys:
        valid = [o.horizons[h_key] for o in outcomes if h_key in o.horizons]
        count = len(valid)
        if count == 0:
            summary[h_key] = {"count": 0}
            continue

        stock_rets = [item["stock_return_pct"] for item in valid]
        bench_rets = [item["benchmark_return_pct"] for item in valid]
        excess_rets = [item["excess_return_pct"] for item in valid]
        beats = sum(1 for item in valid if item["beat_benchmark"])

        summary[h_key] = {
            "count": count,
            "avg_stock_return_pct": round(sum(stock_rets) / count, 2),
            "avg_benchmark_return_pct": round(sum(bench_rets) / count, 2),
            "avg_excess_return_pct": round(sum(excess_rets) / count, 2),
            "win_rate_pct": round((beats / count) * 100.0, 1),
            "win_count": beats,
        }
    return summary


def format_sec_form4_study_report(results: Dict[str, Any]) -> str:
    """Format academic event study findings into clean Turkish text."""
    total = results.get("total_events", 0)
    evaluated = results.get("evaluated_events", 0)
    bench = results.get("benchmark_symbol", "SPY")

    lines = [
        "🏛️ ABD Yönetici Alımları (SEC Form 4) Geçmiş Etki ve Alfa Raporu",
        "=" * 66,
        f"Örneklem: {total} incelenen alım olayı | {evaluated} tamamlanan getiri penceresi | Kıyas: S&P 500 ({bench})",
        "Kural: Bildirimin ertesi işlem günü kapanışında alım; önceden bilme yanılgısı (lookahead) sıfırdır.",
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
        b_ret = data.get("avg_benchmark_return_pct", 0.0)
        exc = data.get("avg_excess_return_pct", 0.0)
        win = data.get("win_rate_pct", 0.0)
        sign = "+" if exc >= 0 else ""
        lines.append(
            f"• {label:<22}: Hisse %{stk:+.2f} | S&P 500 %{b_ret:+.2f} | Alfa: {sign}%{exc:.2f} | Endeksi Geçme: %{win:.1f} ({cnt} işlem)"
        )

    # Segments
    seg = results.get("segments", {})
    lines.extend([
        "",
        "🔬 2. AKADEMİK HİPOTEZ SINAMALARI (Cohen-Malloy-Pomorski & Lakonishok)",
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
            f"(Kazanma %{c_21.get('win_rate_pct', 0):.0f})  vs.  Tek Yönetici %{s_21.get('avg_excess_return_pct', 0):+.2f}"
        )
    if c_63.get("count", 0) > 0 and s_63.get("count", 0) > 0:
        lines.append(
            f"   - 3 Ay (63g) Alfa: Küme Alımı %{c_63.get('avg_excess_return_pct', 0):+.2f} "
            f"(Kazanma %{c_63.get('win_rate_pct', 0):.0f})  vs.  Tek Yönetici %{s_63.get('avg_excess_return_pct', 0):+.2f}"
        )

    # B. C-Suite vs Board
    role = seg.get("role", {})
    cs_21 = role.get("c_suite", {}).get("21d", {})
    bo_21 = role.get("board_other", {}).get("21d", {})
    lines.append("B) Üst Yönetim (CEO / CFO / COO) vs. Yönetim Kurulu / Diğer:")
    if cs_21.get("count", 0) > 0 and bo_21.get("count", 0) > 0:
        lines.append(
            f"   - 1 Ay (21g) Alfa: C-Suite %{cs_21.get('avg_excess_return_pct', 0):+.2f} "
            f"vs.  Diğer %{bo_21.get('avg_excess_return_pct', 0):+.2f}"
        )

    # C. Opportunistic vs 10b5-1
    opp = seg.get("opportunistic", {})
    no_10b_21 = opp.get("non_10b51", {}).get("21d", {})
    yes_10b_21 = opp.get("rule_10b51", {}).get("21d", {})
    lines.append("C) Fırsatçı Alım vs. Rutin Önceden Planlı Alım (Rule 10b5-1):")
    if no_10b_21.get("count", 0) > 0:
        yes_str = f"vs.  10b5-1 Planlı %{yes_10b_21.get('avg_excess_return_pct', 0):+.2f}" if yes_10b_21.get("count", 0) > 0 else "(Yeterli 10b5-1 alım yok)"
        lines.append(
            f"   - 1 Ay (21g) Alfa: Fırsatçı (10b5-1 Yok) %{no_10b_21.get('avg_excess_return_pct', 0):+.2f} {yes_str}"
        )

    lines.extend([
        "",
        "💡 SONUÇ VE KULLANIM REHBERİ:",
        "1. Rastgele yönetici alımı yerine 'Küme Alımı (aynı günlerde birden fazla yönetici)' şartı aranmalı.",
        "2. CEO ve CFO alımları en yüksek bilgi içeriğine sahiptir.",
        "3. Önceden planlanmış otomatik 10b5-1 alımları elenmeli, yalnızca anlık/fırsatçı alımlar taranmalıdır.",
        "4. Bu çalışma geçmiş veriye dayalı akademik ölçümdür; işlem komisyonu ve kayma hariçtir.",
    ])
    return "\n".join(lines)


__all__ = [
    "DEFAULT_BENCHMARK_SYMBOL",
    "DEFAULT_HORIZONS",
    "Form4EventOutcome",
    "default_yfinance_history",
    "format_sec_form4_study_report",
    "run_sec_form4_event_study",
]
