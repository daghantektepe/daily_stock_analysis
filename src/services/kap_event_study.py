# -*- coding: utf-8 -*-
"""Historical event study for Borsa Istanbul KAP disclosures.

Answers the question: *after a material KAP filing (contract, buyback, bonus
issue, dividend, earnings, ...), what did the stock do over the next 1, 5 and
20 trading days, and how much did it beat or lag BIST 100?*

Entry convention (no look-ahead bias):

- Filings published **before 18:00** Istanbul time enter at that trading day's
  close (or the next trading day's close if published on a weekend/holiday).
- Filings published **at or after 18:00** (after the BIST continuous session
  closes) enter at the **next** trading day's close, because the current day's
  close was already set before the disclosure existed.
- Multiple filings for the same ``(stock, tag, entry_date)`` are counted once
  so duplicate notices on the same day do not skew the averages.

Fail-open: missing disclosures or price history return empty buckets rather than
raising.
"""

from __future__ import annotations

import bisect
import logging
import statistics
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.services.kap_watch_service import MATERIAL_TAGS, _TAG_LABELS_TR
from src.services.market_symbol_utils import is_tr_suffix_symbol
from src.services.paper_trading_benchmark import BENCHMARKS, HistoryProvider, _Series, yfinance_history

logger = logging.getLogger(__name__)

DEFAULT_HORIZONS: Tuple[int, ...] = (1, 5, 20)
DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_AFTER_HOURS_CUTOFF = 18


def _entry_index(
    trading_dates: Sequence[date],
    published_at: datetime,
    *,
    after_hours_cutoff_hour: int = DEFAULT_AFTER_HOURS_CUTOFF,
) -> Optional[int]:
    """Index in ``trading_dates`` of the first tradable daily close after ``published_at``."""
    pub_day = published_at.date()
    if published_at.hour >= int(after_hours_cutoff_hour):
        idx = bisect.bisect_right(trading_dates, pub_day)
    else:
        idx = bisect.bisect_left(trading_dates, pub_day)
    if idx >= len(trading_dates):
        return None
    return idx


def _summarize_bucket(
    tag: str,
    events: Sequence[Dict[str, Any]],
    horizons: Sequence[int],
) -> Dict[str, Any]:
    day0_returns = [e["day0_return_pct"] for e in events if e.get("day0_return_pct") is not None]
    day0_excess = [e["day0_excess_return_pct"] for e in events if e.get("day0_excess_return_pct") is not None]
    horizon_stats: Dict[str, Dict[str, Any]] = {}
    for h in horizons:
        key = f"{h}d"
        stock_rets = [
            e["horizons"][key]["stock_return_pct"]
            for e in events
            if key in e.get("horizons", {}) and e["horizons"][key].get("stock_return_pct") is not None
        ]
        bench_rets = [
            e["horizons"][key]["benchmark_return_pct"]
            for e in events
            if key in e.get("horizons", {}) and e["horizons"][key].get("benchmark_return_pct") is not None
        ]
        excess_rets = [
            e["horizons"][key]["excess_return_pct"]
            for e in events
            if key in e.get("horizons", {}) and e["horizons"][key].get("excess_return_pct") is not None
        ]
        n = len(stock_rets)
        wins = sum(1 for r in stock_rets if r > 0)
        beat_idx = sum(1 for r in excess_rets if r > 0)
        horizon_stats[key] = {
            "horizon_days": int(h),
            "sample_size": n,
            "avg_return_pct": round(sum(stock_rets) / n, 2) if n else None,
            "median_return_pct": round(float(statistics.median(stock_rets)), 2) if n else None,
            "avg_benchmark_return_pct": round(sum(bench_rets) / len(bench_rets), 2) if bench_rets else None,
            "avg_excess_return_pct": round(sum(excess_rets) / len(excess_rets), 2) if excess_rets else None,
            "win_rate_pct": round(wins / n * 100, 1) if n else None,
            "beat_index_rate_pct": round(beat_idx / len(excess_rets) * 100, 1) if excess_rets else None,
        }
    return {
        "tag": tag,
        "label_tr": _TAG_LABELS_TR.get(tag, "tüm önemli bildirimler" if tag == "all" else tag),
        "event_count": len(events),
        "avg_day0_return_pct": round(sum(day0_returns) / len(day0_returns), 2) if day0_returns else None,
        "avg_day0_excess_return_pct": round(sum(day0_excess) / len(day0_excess), 2) if day0_excess else None,
        "horizons": horizon_stats,
    }


def run_kap_event_study(
    stocks: Iterable[str],
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    after_hours_cutoff_hour: int = DEFAULT_AFTER_HOURS_CUTOFF,
    max_items_per_stock: int = 500,
    fetcher: Any = None,
    history: HistoryProvider = yfinance_history,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Compute forward 1/5/20-trading-day returns and BIST 100 excess returns by KAP event tag."""
    bist_stocks = [
        str(code).strip().upper()
        for code in stocks
        if str(code or "").strip() and is_tr_suffix_symbol(str(code).strip())
    ]
    clean_horizons = tuple(sorted({int(h) for h in horizons if int(h) > 0})) or DEFAULT_HORIZONS
    end_date = today or date.today()
    lookback_days = max(1, int(days))
    start_date = end_date - timedelta(days=lookback_days)
    history_start = start_date - timedelta(days=15)

    if fetcher is None:
        from data_provider.kap_fetcher import KapDisclosureFetcher

        fetcher = KapDisclosureFetcher()

    tr_spec = BENCHMARKS["tr"]
    try:
        index_closes = history(tr_spec["index"], history_start, end_date)
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.info("[kap-study] benchmark history failed: %s", exc)
        index_closes = {}
    index_series = _Series(index_closes)

    events_by_tag: Dict[str, List[Dict[str, Any]]] = {}
    all_events: List[Dict[str, Any]] = []
    seen_stock_tag_entry: set = set()
    seen_stock_any_entry: set = set()

    for code in bist_stocks:
        try:
            disclosures = fetcher.get_recent_disclosures(
                code,
                days=lookback_days,
                max_items=max_items_per_stock,
                today=end_date,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("[kap-study] disclosures failed code=%s: %s", code, exc)
            continue
        if not disclosures:
            continue
        try:
            stock_closes = history(code, history_start, end_date)
        except Exception as exc:  # noqa: BLE001
            logger.info("[kap-study] price history failed code=%s: %s", code, exc)
            continue
        if not stock_closes:
            continue
        trading_dates = sorted(stock_closes)

        # Process oldest first so the first filing on a session anchors the event record.
        for item in sorted(disclosures, key=lambda row: row.get("published_at") or datetime.min):
            tags = [tag for tag in (item.get("tags") or []) if tag in MATERIAL_TAGS]
            published_at = item.get("published_at")
            if not tags or not isinstance(published_at, datetime):
                continue
            i0 = _entry_index(
                trading_dates,
                published_at,
                after_hours_cutoff_hour=after_hours_cutoff_hour,
            )
            if i0 is None:
                continue
            entry_date = trading_dates[i0]
            entry_close = stock_closes[entry_date]
            if not entry_close or entry_close <= 0:
                continue

            day0_ret: Optional[float] = None
            day0_excess: Optional[float] = None
            if i0 > 0:
                prev_date = trading_dates[i0 - 1]
                prev_close = stock_closes.get(prev_date)
                if prev_close and prev_close > 0:
                    day0_ret = round((entry_close / prev_close - 1) * 100, 4)
                    idx_prev, idx_entry = index_series.at(prev_date), index_series.at(entry_date)
                    if idx_prev and idx_entry and idx_prev > 0:
                        idx_day0 = (idx_entry / idx_prev - 1) * 100
                        day0_excess = round(day0_ret - idx_day0, 4)

            forward: Dict[str, Dict[str, Optional[float]]] = {}
            idx_t0 = index_series.at(entry_date)
            for h in clean_horizons:
                if i0 + h >= len(trading_dates):
                    continue
                exit_date = trading_dates[i0 + h]
                exit_close = stock_closes.get(exit_date)
                if not exit_close or exit_close <= 0:
                    continue
                stock_ret = (exit_close / entry_close - 1) * 100
                idx_th = index_series.at(exit_date)
                bench_ret: Optional[float] = None
                excess_ret: Optional[float] = None
                if idx_t0 and idx_th and idx_t0 > 0:
                    bench_ret = (idx_th / idx_t0 - 1) * 100
                    excess_ret = stock_ret - bench_ret
                forward[f"{h}d"] = {
                    "exit_date": exit_date.isoformat(),
                    "stock_return_pct": round(stock_ret, 4),
                    "benchmark_return_pct": round(bench_ret, 4) if bench_ret is not None else None,
                    "excess_return_pct": round(excess_ret, 4) if excess_ret is not None else None,
                }

            event_record = {
                "stock_code": code,
                "index": item.get("index"),
                "published_date": item.get("published_date"),
                "entry_date": entry_date.isoformat(),
                "entry_close": entry_close,
                "title": item.get("title"),
                "tags": tags,
                "day0_return_pct": day0_ret,
                "day0_excess_return_pct": day0_excess,
                "horizons": forward,
            }
            if (code, entry_date) not in seen_stock_any_entry:
                seen_stock_any_entry.add((code, entry_date))
                all_events.append(event_record)
            for tag in tags:
                dedup_key = (code, tag, entry_date)
                if dedup_key in seen_stock_tag_entry:
                    continue
                seen_stock_tag_entry.add(dedup_key)
                events_by_tag.setdefault(tag, []).append(event_record)

    by_tag = [
        _summarize_bucket(tag, tag_events, clean_horizons)
        for tag, tag_events in events_by_tag.items()
    ]
    primary_key = f"{clean_horizons[min(1, len(clean_horizons) - 1)]}d"
    by_tag.sort(
        key=lambda bucket: (
            -(
                bucket["horizons"].get(primary_key, {}).get("avg_excess_return_pct")
                if bucket["horizons"].get(primary_key, {}).get("avg_excess_return_pct") is not None
                else -999.0
            ),
            -bucket["event_count"],
            bucket["tag"],
        )
    )
    return {
        "benchmark": tr_spec["index"],
        "benchmark_name": tr_spec["index_name"],
        "days": lookback_days,
        "horizons": list(clean_horizons),
        "after_hours_cutoff_hour": int(after_hours_cutoff_hour),
        "stock_count": len(bist_stocks),
        "stocks": bist_stocks,
        "event_count": len(all_events),
        "overall": _summarize_bucket("all", all_events, clean_horizons),
        "by_tag": by_tag,
        "events": all_events,
    }


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:+.2f}%"


def _rate(value: Optional[float]) -> str:
    return "n/a" if value is None else f"%{value:.0f}"


def format_kap_event_study_report(study: Dict[str, Any]) -> str:
    """Plain-text (Turkish) summary of historical KAP event returns vs BIST 100."""
    days = study.get("days", DEFAULT_LOOKBACK_DAYS)
    bench_name = study.get("benchmark_name", "BIST 100")
    cutoff = study.get("after_hours_cutoff_hour", DEFAULT_AFTER_HOURS_CUTOFF)
    lines = [
        f"📊 KAP Olay Etkisi Analizi (son {days} gün, {bench_name} kıyasıyla)",
        f"İncelenen hisse: {study.get('stock_count', 0)} | Tekil olay: {study.get('event_count', 0)} | "
        f"Giriş: bildirim sonrası ilk kapanış ({cutoff:02d}:00 sonrası -> ertesi işlem günü)",
    ]
    by_tag = study.get("by_tag") or []
    if not by_tag:
        lines.append("Değerlendirilecek geçmiş KAP olayı veya fiyat serisi bulunamadı.")
        return "\n".join(lines)

    for bucket in by_tag:
        day0_ex = bucket.get("avg_day0_excess_return_pct")
        day0_ret = bucket.get("avg_day0_return_pct")
        day0_part = f", ilk gün {_pct(day0_ret)}" if day0_ret is not None else ""
        if day0_ex is not None:
            day0_part += f" ({bench_name} fark {_pct(day0_ex)})"
        lines.append(f"• {bucket['label_tr']} (n={bucket['event_count']}{day0_part}):")
        horizon_parts: List[str] = []
        for h_key, h_stats in (bucket.get("horizons") or {}).items():
            n = int(h_stats.get("sample_size") or 0)
            if n <= 0:
                continue
            h_days = h_stats.get("horizon_days") or h_key.rstrip("d")
            horizon_parts.append(
                f"{h_days}g: ort. {_pct(h_stats.get('avg_return_pct'))}, "
                f"{bench_name} fark {_pct(h_stats.get('avg_excess_return_pct'))}, "
                f"endeksi geçen {_rate(h_stats.get('beat_index_rate_pct'))} (n={n})"
            )
        if horizon_parts:
            lines.append("  " + " | ".join(horizon_parts))

    lines.append(
        "Not: Geçmiş olay etkisi gelecekteki getiriyi garanti etmez; komisyon, kayma ve vergi dahil değildir."
    )
    return "\n".join(lines)


__all__ = [
    "DEFAULT_AFTER_HOURS_CUTOFF",
    "DEFAULT_HORIZONS",
    "DEFAULT_LOOKBACK_DAYS",
    "format_kap_event_study_report",
    "run_kap_event_study",
]

