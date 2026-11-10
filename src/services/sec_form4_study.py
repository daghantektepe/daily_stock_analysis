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
import json
import logging
import math
import statistics
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from data_provider.sec_form4_fetcher import InsiderClusterEvent

logger = logging.getLogger(__name__)

DEFAULT_BENCHMARK_SYMBOL = "SPY"
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
) -> Dict[str, Any]:
    """Calculate forward returns vs. benchmark for a sequence of Form 4 events."""
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

    # 1. Fetch benchmark price series
    bench_closes = history(benchmark_symbol, min_date - timedelta(days=10), study_end_date)
    bench_cal = _PriceCalendar(bench_closes)

    # 2. Evaluate each event
    outcomes: List[Form4EventOutcome] = []
    symbol_caches: Dict[str, _PriceCalendar] = {}
    missing_symbols: Set[str] = set()

    for event in filtered_events:
        sym = event.symbol
        if sym not in symbol_caches:
            sym_closes = history(sym, event.filing_date - timedelta(days=5), study_end_date)
            symbol_caches[sym] = _PriceCalendar(sym_closes)
        stock_cal = symbol_caches[sym]

        entry_date, entry_price = stock_cal.next_trading_day_close(event.filing_date)
        if entry_date is None or entry_price is None:
            missing_symbols.add(sym)
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
                is_opportunistic=event.is_opportunistic or (not event.has_10b51 and event.cmp_class != "routine"),
                is_cluster=event.is_cluster,
                cmp_class=event.cmp_class,
                has_10b51=event.has_10b51,
                primary_titles=event.primary_titles,
                horizons=horizon_results,
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
    }

    return {
        "total_events": len(filtered_events),
        "evaluated_events": len(outcomes),
        "missing_events": len(filtered_events) - len(outcomes),
        "missing_symbols": sorted(missing_symbols),
        "benchmark_symbol": benchmark_symbol,
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
    """Aggregate stock returns, benchmark returns, excess alpha and statistical metrics."""
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

        stats_excess = compute_sample_statistics(excess_rets)
        stats_stock = compute_sample_statistics(stock_rets)
        stats_bench = compute_sample_statistics(bench_rets)

        net_mean_excess = round(stats_excess["mean"] - slippage_pct, 2)
        summary[h_key] = {
            "count": count,
            "avg_stock_return_pct": stats_stock["mean"],
            "median_stock_return_pct": stats_stock["median"],
            "avg_benchmark_return_pct": stats_bench["mean"],
            "median_benchmark_return_pct": stats_bench["median"],
            "avg_excess_return_pct": stats_excess["mean"],
            "median_excess_return_pct": stats_excess["median"],
            "net_excess_return_pct": net_mean_excess,
            "stdev_excess_pct": stats_excess["stdev"],
            "t_stat": stats_excess["t_stat"],
            "is_significant": stats_excess["is_significant"],
            "win_rate_pct": round((beats / count) * 100.0, 1),
            "win_count": beats,
        }
    return summary


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

    # 2. Overall Performance & Significance
    d21 = h_data.get("21d", {})
    if d21.get("count", 0) > 0:
        exc_mean = d21.get("avg_excess_return_pct", 0.0)
        exc_med = d21.get("median_excess_return_pct", 0.0)
        t_stat = d21.get("t_stat", 0.0)
        sig = d21.get("is_significant", False)
        net_exc = d21.get("net_excess_return_pct", 0.0)

        sig_text = "istatistiksel olarak anlamlıdır (p < 0.05)" if sig else "istatistiksel olarak tesadüften ayırt edilemez (|t| < 1.96)"
        conclusions.append(
            f"📊 1 Aylık Alfa: Ortalama %{exc_mean:+.2f} (Medyan: %{exc_med:+.2f}), t={t_stat:.2f} ({sig_text}). "
            f"Tahmini kayma/komisyon sonrası net alfa: %{net_exc:+.2f}."
        )

    # 3. Cluster vs. Single Insider Hypothesis Check
    clust = seg.get("cluster_vs_single", {})
    c_21 = clust.get("cluster", {}).get("21d", {})
    s_21 = clust.get("single", {}).get("21d", {})
    if c_21.get("count", 0) >= 3 and s_21.get("count", 0) >= 3:
        c_exc = c_21.get("avg_excess_return_pct", 0.0)
        s_exc = s_21.get("avg_excess_return_pct", 0.0)
        diff = c_exc - s_exc
        if diff > 1.0:
            conclusions.append(
                f"✅ Küme alımı hipotezi DOĞRULANDI: Çoklu yönetici alımı (%{c_exc:+.2f}), "
                f"tek yönetici alımına göre (%{s_exc:+.2f}) %{diff:.2f} daha fazla aşırı getiri sağladı."
            )
        elif diff < -1.0:
            conclusions.append(
                f"❌ Küme alımı hipotezi BU DÖNEMDE ÇALIŞMADI: Çoklu yönetici alımı (%{c_exc:+.2f}), "
                f"tek yöneticiye kıyasla (%{s_exc:+.2f}) %{abs(diff):.2f} daha zayıf kaldı."
            )
        else:
            conclusions.append(
                f"⚖️ Küme alımı ile tek alım arasında belirgin getiri farkı gözlenmedi (Küme: %{c_exc:+.2f} vs Tek: %{s_exc:+.2f})."
            )

    # 4. C-Suite Conviction Hypothesis Check
    role = seg.get("role", {})
    cs_21 = role.get("c_suite", {}).get("21d", {})
    bo_21 = role.get("board_other", {}).get("21d", {})
    if cs_21.get("count", 0) >= 3 and bo_21.get("count", 0) >= 3:
        cs_exc = cs_21.get("avg_excess_return_pct", 0.0)
        bo_exc = bo_21.get("avg_excess_return_pct", 0.0)
        diff_r = cs_exc - bo_exc
        if diff_r > 1.0:
            conclusions.append(
                f"✅ C-Suite hipotezi DOĞRULANDI: CEO/CFO/Başkan alımları (%{cs_exc:+.2f}), "
                f"yönetim kurulu/diğer alımlardan (%{bo_exc:+.2f}) %{diff_r:.2f} daha yüksek getiri üretti."
            )
        else:
            conclusions.append(
                f"ℹ️ C-Suite alımları (%{cs_exc:+.2f}) ile diğer alımlar (%{bo_exc:+.2f}) benzer performans sergiledi."
            )

    # 5. Opportunistic vs Routine / 10b5-1 Check
    opp = seg.get("opportunistic", {})
    non_10b = opp.get("non_10b51", {}).get("21d", {})
    rule_10b = opp.get("rule_10b51", {}).get("21d", {})
    if non_10b.get("count", 0) >= 3 and rule_10b.get("count", 0) >= 3:
        n_exc = non_10b.get("avg_excess_return_pct", 0.0)
        r_exc = rule_10b.get("avg_excess_return_pct", 0.0)
        diff_opp = n_exc - r_exc
        if diff_opp > 1.0:
            conclusions.append(
                f"✅ Fırsatçı alım avantajı DOĞRULANDI: 10b5-1 plansız alımlar (%{n_exc:+.2f}), "
                f"otomatik 10b5-1 program alımlarına kıyasla (%{r_exc:+.2f}) %{diff_opp:.2f} daha karlı oldu."
            )
        else:
            conclusions.append(
                f"ℹ️ 10b5-1 planlı alımlar (%{r_exc:+.2f}) ile plansız alımlar (%{n_exc:+.2f}) arasında fark tespit edilemedi."
            )

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
        f"Kıyas Endeksi: {bench} | Varsayılan Alış-Satış Kayması/Komisyon: %{slip:.2f}",
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
        med_stk = data.get("median_stock_return_pct", 0.0)
        b_ret = data.get("avg_benchmark_return_pct", 0.0)
        exc = data.get("avg_excess_return_pct", 0.0)
        med_exc = data.get("median_excess_return_pct", 0.0)
        net_exc = data.get("net_excess_return_pct", 0.0)
        t_stat = data.get("t_stat", 0.0)
        sig = " (p<0.05)" if data.get("is_significant") else ""
        win = data.get("win_rate_pct", 0.0)
        sign = "+" if exc >= 0 else ""
        lines.append(
            f"• {label:<22}: Hisse %{stk:+.2f} (Medyan %{med_stk:+.2f}) | {bench} %{b_ret:+.2f} | "
            f"Alfa: {sign}%{exc:.2f} (Net: %{net_exc:+.2f}) | Medyan Alfa: %{med_exc:+.2f} | "
            f"t={t_stat:.2f}{sig} | Kazanma: %{win:.1f} ({cnt} işlem)"
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
