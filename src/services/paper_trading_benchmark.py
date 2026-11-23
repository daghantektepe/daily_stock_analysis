# -*- coding: utf-8 -*-
"""Benchmarks for the paper trading ledger: index shadow and USD-based return.

In a high-inflation market a positive nominal return can still lose to the
index or to the dollar. For each supported market this module replays the
paper trades twice:

- **Index shadow**: every buy puts the same amount into the benchmark index on
  the same day, every sell takes out the same fraction, open positions are
  marked to the latest index close. ``excess_return_pct`` = strategy - index.
- **USD view**: every cash flow is converted at that day's USD rate, so the
  result is the return a dollar-based investor would have seen.

Returns are on capital deployed (sum of buy amounts). Prices are daily closes
on or before the trade date. Fail-open: missing history yields ``None``
metrics, never an exception.
"""

from __future__ import annotations

import bisect
import json
import logging
import os
import random
import tempfile
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_ISTANBUL_TZ = timezone(timedelta(hours=3))
DEFAULT_WEEKLY_REPORT_STATE_PATH = Path("data") / "weekly_report_state.json"
_HORIZON_LABELS_TR = {"1d": "1g", "3d": "3g", "5d": "5g", "10d": "10g"}
_ACTION_LABELS_TR = {
    "buy": "al",
    "add": "ekle",
    "hold": "tut",
    "reduce": "azalt",
    "sell": "sat",
    "avoid": "uzak dur",
    "watch": "izle",
    "alert": "uyarı",
}

# market -> benchmark index and USD rate (quote currency per 1 USD).
BENCHMARKS: Dict[str, Dict[str, str]] = {
    "tr": {"index": "XU100.IS", "index_name": "BIST 100", "fx": "TRY=X", "currency": "TRY"},
    "us": {"index": "SPY", "index_name": "S&P 500 (SPY)", "fx": "", "currency": "USD"},
}

HistoryProvider = Callable[[str, date, date], Dict[date, float]]
_HISTORY_TTL_SECONDS = 3600
_history_cache: Dict[tuple, tuple] = {}
_history_lock = threading.Lock()


def yfinance_history(symbol: str, start: date, end: date) -> Dict[date, float]:
    """Daily closes from Yahoo Finance (cached for an hour, ``{}`` on failure)."""
    key = (symbol, start.isoformat(), end.isoformat())
    with _history_lock:
        cached = _history_cache.get(key)
        if cached and time.monotonic() - cached[0] < _HISTORY_TTL_SECONDS:
            return cached[1]
    closes: Dict[date, float] = {}
    try:
        import yfinance as yf

        frame = yf.Ticker(symbol).history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                                          interval="1d", auto_adjust=False)
        for index, row in frame.iterrows():
            value = float(row.get("Close"))
            if value > 0:
                closes[index.date()] = value
    except Exception as exc:  # noqa: BLE001 - optional benchmark, fail-open
        logger.info("[paper-benchmark] history failed symbol=%s: %s", symbol, exc)
        return {}
    if closes:
        with _history_lock:
            _history_cache[key] = (time.monotonic(), closes)
    return closes


class _Series:
    """Close on or before a date (handles weekends / holidays)."""

    def __init__(self, closes: Dict[date, float]) -> None:
        self._dates = sorted(closes)
        self._closes = closes

    def at(self, day: date) -> Optional[float]:
        position = bisect.bisect_right(self._dates, day)
        if position == 0:
            return None
        return self._closes[self._dates[position - 1]]


def _parse_day(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def compute_market_benchmark(
    trades: Sequence[Dict[str, Any]],
    *,
    market: str,
    mark_prices: Dict[str, float],
    today: Optional[date] = None,
    history: HistoryProvider = yfinance_history,
) -> Optional[Dict[str, Any]]:
    """Index-shadow and USD returns for one market's paper trades (``None`` if not applicable)."""
    spec = BENCHMARKS.get(market)
    rows = [trade for trade in trades if trade.get("market") == market and _parse_day(trade.get("trade_date"))]
    if spec is None or not rows:
        return None
    today = today or date.today()
    start = min(_parse_day(trade["trade_date"]) for trade in rows) - timedelta(days=10)
    index = _Series(history(spec["index"], start, today))
    fx = _Series(history(spec["fx"], start, today)) if spec.get("fx") else None

    invested = proceeds = 0.0
    index_proceeds = 0.0
    usd_invested = usd_proceeds = 0.0
    index_ok = fx_ok = True
    books: Dict[str, Dict[str, float]] = {}
    for trade in sorted(rows, key=lambda item: (str(item["trade_date"]), item.get("id") or 0)):
        day = _parse_day(trade["trade_date"])
        quantity = float(trade.get("quantity") or 0)
        price = float(trade.get("price") or 0)
        book = books.setdefault(trade["stock_code"], {"quantity": 0.0, "index_units": 0.0})
        index_close = index.at(day)
        fx_rate = 1.0 if spec.get("currency") == "USD" else (fx.at(day) if fx else None)
        index_ok = index_ok and index_close is not None
        fx_ok = fx_ok and fx_rate is not None
        if trade.get("side") == "buy":
            amount = quantity * price
            invested += amount
            book["quantity"] += quantity
            if index_close:
                book["index_units"] += amount / index_close
            if fx_rate:
                usd_invested += amount / fx_rate
            continue
        if book["quantity"] <= 0:
            continue
        sold = min(quantity, book["quantity"])
        fraction = sold / book["quantity"]
        amount = sold * price
        proceeds += amount
        if index_close:
            index_proceeds += book["index_units"] * fraction * index_close
        book["index_units"] *= 1 - fraction
        book["quantity"] -= sold
        if fx_rate:
            usd_proceeds += amount / fx_rate

    if invested <= 0:
        return None
    index_today = index.at(today)
    fx_today = 1.0 if spec.get("currency") == "USD" else (fx.at(today) if fx else None)
    open_value = sum(book["quantity"] * mark_prices.get(code, 0.0) for code, book in books.items())
    strategy_return = (proceeds + open_value - invested) / invested * 100
    result: Dict[str, Any] = {
        "benchmark": spec["index"],
        "benchmark_name": spec["index_name"],
        "currency": spec["currency"],
        "capital_deployed": round(invested, 2),
        "strategy_return_pct": round(strategy_return, 2),
        "benchmark_return_pct": None,
        "excess_return_pct": None,
        "usd_return_pct": None,
        "fx_change_pct": None,
    }
    if index_ok and index_today:
        index_value = sum(book["index_units"] for book in books.values()) * index_today
        benchmark_return = (index_proceeds + index_value - invested) / invested * 100
        result["benchmark_return_pct"] = round(benchmark_return, 2)
        result["excess_return_pct"] = round(strategy_return - benchmark_return, 2)
    if fx_ok and fx_today and usd_invested > 0:
        if spec.get("currency") == "USD":
            result["usd_return_pct"] = round(strategy_return, 2)
            result["fx_change_pct"] = 0.0
        else:
            usd_value = open_value / fx_today
            result["usd_return_pct"] = round((usd_proceeds + usd_value - usd_invested) / usd_invested * 100, 2)
            first_rate = fx.at(min(_parse_day(trade["trade_date"]) for trade in rows)) if fx else None
            if first_rate:
                result["fx_change_pct"] = round((fx_today / first_rate - 1) * 100, 2)
    return result


def compute_benchmarks(
    trades: Sequence[Dict[str, Any]],
    *,
    mark_prices: Dict[str, float],
    today: Optional[date] = None,
    history: HistoryProvider = yfinance_history,
) -> Dict[str, Dict[str, Any]]:
    """Benchmarks for every supported market present in the ledger."""
    results: Dict[str, Dict[str, Any]] = {}
    for market in sorted({str(trade.get("market") or "") for trade in trades}):
        try:
            summary = compute_market_benchmark(
                trades, market=market, mark_prices=mark_prices, today=today, history=history,
            )
        except Exception as exc:  # noqa: BLE001 - optional benchmark, fail-open
            logger.info("[paper-benchmark] market=%s failed: %s", market, exc)
            summary = None
        if summary:
            results[market] = summary
    return results


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:+.2f}%"


def evaluate_signal_outcomes(
    *,
    market: Optional[str] = None,
    db_manager: Optional[Any] = None,
    limit: int = 500,
    refill_missing_bars: bool = True,
    bar_filler: Optional[Callable[..., int]] = None,
    history_provider: Optional[HistoryProvider] = None,
) -> Dict[str, Any]:
    """Run pending DecisionSignal outcome evaluations (1/3/5/10d) and summarize hit rates.

    Missing anchor / forward daily closes are fetched from the data providers
    (``refill_missing_bars``); otherwise a stock analysed only once could never
    be scored. Directional outcomes are also compared against the market index
    (``tr`` -> ``XU100.IS``, ``us`` -> ``SPY``) via ``history_provider``.
    Fail-open: returns ``{}`` on any database or evaluation error.
    """
    try:
        from src.services.decision_signal_outcome_service import (
            DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
            DEFAULT_STATS_STATUSES,
            SUPPORTED_OUTCOME_HORIZONS,
            DecisionSignalOutcomeService,
        )

        service = DecisionSignalOutcomeService(
            db_manager=db_manager,
            refill_missing_bars=refill_missing_bars,
            bar_filler=bar_filler,
        )
        horizons = list(SUPPORTED_OUTCOME_HORIZONS.keys())
        run_result = service.run_outcomes(
            horizons=horizons,
            market=market,
            limit=limit,
        )
        stats_rows = service.repo.list_stats_rows(
            engine_version=DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
            horizons=horizons,
            statuses=list(DEFAULT_STATS_STATUSES),
        )
        rows = [
            stats_row.outcome
            for stats_row in stats_rows
            if not market or str(stats_row.outcome.market or "").strip().lower() == market.strip().lower()
        ]
        signal_codes = _signal_stock_codes(service, rows)
        rows, duplicates = _dedupe_repeated_signal_outcomes(service, rows, signal_codes=signal_codes)
        overall = service._aggregate(rows)
        by_horizon: Dict[str, Dict[str, Any]] = {}
        for horizon in horizons:
            h_rows = [row for row in rows if row.horizon == horizon]
            if h_rows:
                by_horizon[horizon] = service._aggregate(h_rows)
        by_action: Dict[str, Dict[str, Any]] = {}
        for bucket in service._breakdown(rows, "action"):
            if int(bucket.get("completed") or 0) > 0:
                by_action[str(bucket["value"])] = bucket
        active_history = yfinance_history if history_provider is None else history_provider
        benchmark_comparison = _evaluate_signal_benchmark_comparison(
            service,
            rows,
            signal_codes=signal_codes,
            history=active_history,
        )
        return {
            "evaluated": int(run_result.get("evaluated") or 0),
            "total": int(overall.get("total") or 0),
            "completed": int(overall.get("completed") or 0),
            "unable": int(overall.get("unable") or 0),
            "hit": int(overall.get("hit") or 0),
            "miss": int(overall.get("miss") or 0),
            "neutral": int(overall.get("neutral") or 0),
            "hit_rate_pct": overall.get("hit_rate_pct"),
            "avg_stock_return_pct": overall.get("avg_stock_return_pct"),
            "unable_reasons": dict(overall.get("unable_reasons") or {}),
            "duplicate_checks_merged": duplicates,
            "by_horizon": by_horizon,
            "by_action": by_action,
            "benchmark_comparison": benchmark_comparison,
        }
    except Exception as exc:  # noqa: BLE001 - optional reporting helper, fail-open
        logger.info("[paper-benchmark] signal outcome evaluation failed: %s", exc)
        return {}


# Outcomes waiting for forward closes vs. outcomes that cannot be scored at all.
_WAITING_UNABLE_REASONS = frozenset({"insufficient_forward_bars", "missing_end_close"})
_UNABLE_REASON_LABELS_TR = {
    "insufficient_forward_bars": "ileri kapanış bekleniyor",
    "missing_end_close": "ileri kapanış bekleniyor",
    "missing_anchor_price": "sinyal günü fiyatı yok",
    "invalid_anchor_price": "sinyal günü fiyatı geçersiz",
    "invalid_end_close": "kapanış fiyatı geçersiz",
    "non_directional_action": "yönsüz sinyal (izle)",
    "missing_anchor_date": "sinyal tarihi yok",
    "unsupported_horizon": "desteklenmeyen ufuk",
}
MIN_SIGNAL_SAMPLE = 30


def _signal_outcome_status_line(outcomes: Dict[str, Any]) -> Optional[str]:
    """Explain the checks that have no result yet: waiting for closes vs. not scorable."""
    reasons = {str(k): int(v) for k, v in (outcomes.get("unable_reasons") or {}).items() if int(v or 0) > 0}
    if not reasons:
        return None
    waiting = sum(v for k, v in reasons.items() if k in _WAITING_UNABLE_REASONS)
    blocked: Dict[str, int] = {}
    for key, count in reasons.items():
        if key in _WAITING_UNABLE_REASONS:
            continue
        label = _UNABLE_REASON_LABELS_TR.get(key, key)
        blocked[label] = blocked.get(label, 0) + count
    parts = []
    if waiting:
        parts.append(f"{waiting} ileri kapanış bekliyor")
    if blocked:
        detail = ", ".join(f"{label} {count}" for label, count in sorted(blocked.items(), key=lambda kv: -kv[1]))
        parts.append(f"{sum(blocked.values())} değerlendirilemedi ({detail})")
    return "Sonuçlanmayan kontroller: " + " · ".join(parts)


_WEEKDAYS_TR = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")


def describe_signal_outcome_details(
    *,
    market: Optional[str] = None,
    db_manager: Optional[Any] = None,
    limit: int = 50,
) -> List[str]:
    """Read-only per-signal diagnosis: why each directional signal is (not yet) scored.

    Shows the action mix of all signals, then for every directional signal its
    signal day (with weekday, to spot weekend/holiday anchors), whether that day's
    close and how many forward closes are stored, the latest stored close and the
    status of each horizon.
    """
    try:
        from collections import Counter
        from datetime import date as _date

        from src.services.decision_signal_outcome_service import (
            DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
            DEFAULT_STATS_STATUSES,
            SUPPORTED_OUTCOME_HORIZONS,
            DecisionSignalOutcomeService,
        )

        service = DecisionSignalOutcomeService(db_manager=db_manager)
        signals = service.repo.list_candidate_signals(
            market=market, statuses=list(DEFAULT_STATS_STATUSES), limit=max(1, min(int(limit), 500))
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        return [f"Ayrıntı okunamadı: {exc}"]
    if not signals:
        return ["Kayıtlı sinyal yok."]

    mix = Counter(_ACTION_LABELS_TR.get(str(sig.action), str(sig.action)) for sig in signals)
    lines = ["Sinyal dağılımı: " + ", ".join(f"{label} {count}" for label, count in mix.most_common())]
    status_tr = {"hit": "isabet", "miss": "ıska", "neutral": "nötr"}
    for sig in signals:
        if service._direction_for_action(sig.action) is None:
            continue
        anchor = service._anchor_date(sig)
        if anchor is None:
            lines.append(f"- #{sig.id} {sig.stock_code} {sig.action}: sinyal tarihi yok")
            continue
        has_anchor = service.stock_repo.get_daily_on_date(code=sig.stock_code, target_date=anchor) is not None
        forward = service.stock_repo.get_forward_bars(code=sig.stock_code, analysis_date=anchor, eval_window_days=10)
        latest = service.stock_repo.get_start_daily(code=sig.stock_code, analysis_date=_date.today())
        horizon_parts = []
        for horizon in SUPPORTED_OUTCOME_HORIZONS:
            row = service.repo.get_outcome(
                signal_id=sig.id, horizon=horizon, engine_version=DECISION_SIGNAL_OUTCOME_ENGINE_VERSION
            )
            if row is None:
                horizon_parts.append(f"{horizon} kayıt yok")
            elif row.eval_status == "completed":
                horizon_parts.append(f"{horizon} {status_tr.get(str(row.outcome), row.outcome)}")
            else:
                reason = _UNABLE_REASON_LABELS_TR.get(str(row.unable_reason), str(row.unable_reason))
                horizon_parts.append(f"{horizon} {reason}")
        lines.append(
            f"- #{sig.id} {sig.stock_code} {_ACTION_LABELS_TR.get(str(sig.action), sig.action)} · "
            f"sinyal günü {anchor.isoformat()} ({_WEEKDAYS_TR[anchor.weekday()]}) · "
            f"o günün fiyatı {'var' if has_anchor else 'YOK'} · ileri kapanış {len(forward)}/10 · "
            f"son kayıtlı kapanış {latest.date.isoformat() if latest is not None else 'yok'} · "
            + ", ".join(horizon_parts)
        )
    return lines


def _signal_stock_codes(service: Any, rows: Sequence[Any]) -> Dict[int, str]:
    ids = sorted({int(row.signal_id) for row in rows if getattr(row, "signal_id", None) is not None})
    if not ids:
        return {}
    codes: Dict[int, str] = {}
    try:
        from src.storage import DecisionSignalRecord

        with service.repo.db.get_session() as session:
            for sig_id, code in session.query(DecisionSignalRecord.id, DecisionSignalRecord.stock_code).filter(
                DecisionSignalRecord.id.in_(ids)
            ):
                codes[int(sig_id)] = str(code)
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.info("[paper-benchmark] signal stock code lookup skipped: %s", exc)
    return codes


def _dedupe_repeated_signal_outcomes(
    service: Any,
    rows: List[Any],
    *,
    signal_codes: Optional[Dict[int, str]] = None,
) -> tuple:
    """Count one stock / signal day / direction / horizon once.

    Running the analysis several times a day stores several identical signals;
    scoring each would count one price move many times. The latest signal wins.
    """
    codes = signal_codes if signal_codes is not None else _signal_stock_codes(service, rows)
    if not codes:
        return rows, 0
    latest: Dict[tuple, Any] = {}
    for row in rows:
        key = (
            codes.get(int(row.signal_id), f"#{row.signal_id}"),
            row.anchor_date,
            row.direction_expected or row.action,
            row.horizon,
        )
        kept = latest.get(key)
        if kept is None or int(row.signal_id) > int(kept.signal_id):
            latest[key] = row
    deduped = list(latest.values())
    return deduped, len(rows) - len(deduped)


_BUY_ACTIONS = frozenset({"buy", "add"})
_SELL_ACTIONS = frozenset({"reduce", "sell", "avoid"})
_PRIMARY_BENCHMARK_HORIZON = "10d"


def _bootstrap_ci90(
    values: Sequence[float],
    *,
    iterations: int = 1000,
    seed: int = 42,
) -> Optional[List[float]]:
    """Simple percentile bootstrap 90% confidence interval for the mean."""
    n = len(values)
    if n < MIN_SIGNAL_SAMPLE:
        return None
    rng = random.Random(seed)
    vals = list(values)
    means: List[float] = []
    for _ in range(iterations):
        sample = [vals[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    low_idx = max(0, int(0.05 * (iterations - 1)))
    high_idx = min(iterations - 1, int(0.95 * (iterations - 1)))
    return [round(means[low_idx], 2), round(means[high_idx], 2)]


def _summarize_benchmark_bucket(samples: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(samples)
    if n == 0:
        return {
            "n": 0,
            "beat_count": 0,
            "beat_rate_pct": None,
            "beat_rate_ci90_pct": None,
            "avg_excess_pct": None,
            "avg_excess_ci90_pct": None,
            "sample_sufficient": False,
        }
    beats = [100.0 if item["beat"] else 0.0 for item in samples]
    excesses = [float(item["excess_pct"]) for item in samples]
    beat_count = sum(1 for item in samples if item["beat"])
    beat_rate = round(beat_count / n * 100.0, 2)
    avg_excess = round(sum(excesses) / n, 2)
    return {
        "n": n,
        "beat_count": beat_count,
        "beat_rate_pct": beat_rate,
        "beat_rate_ci90_pct": _bootstrap_ci90(beats),
        "avg_excess_pct": avg_excess,
        "avg_excess_ci90_pct": _bootstrap_ci90(excesses),
        "sample_sufficient": n >= MIN_SIGNAL_SAMPLE,
    }


def _evaluate_signal_benchmark_comparison(
    service: Any,
    rows: Sequence[Any],
    *,
    signal_codes: Dict[int, str],
    history: HistoryProvider,
) -> Dict[str, Any]:
    """Compare completed directional signal returns to the market index over the exact window."""
    directional = [
        row
        for row in rows
        if getattr(row, "eval_status", None) == "completed"
        and getattr(row, "anchor_date", None) is not None
        and getattr(row, "eval_window_days", None)
        and getattr(row, "stock_return_pct", None) is not None
        and (str(row.action or "") in _BUY_ACTIONS or str(row.action or "") in _SELL_ACTIONS)
    ]
    empty_bucket = _summarize_benchmark_bucket([])
    if not directional:
        return {
            "primary_horizon": _PRIMARY_BENCHMARK_HORIZON,
            "min_sample": MIN_SIGNAL_SAMPLE,
            "groups": {"buy": dict(empty_bucket), "sell": dict(empty_bucket)},
            "combined_10d": dict(empty_bucket),
            "by_horizon": {},
            "no_benchmark_markets": [],
            "no_benchmark_count": 0,
            "missing_index_data_count": 0,
        }

    window_cache: Dict[tuple, Optional[date]] = {}
    market_spans: Dict[str, List[date]] = {}
    no_benchmark_markets_all: List[str] = []
    no_benchmark_count_primary = 0
    prepared: List[Dict[str, Any]] = []

    for row in directional:
        market_key = str(row.market or "").strip().lower()
        horizon = str(row.horizon or "").strip()
        if market_key not in BENCHMARKS:
            label = market_key or "bilinmiyor"
            if horizon == _PRIMARY_BENCHMARK_HORIZON:
                no_benchmark_count_primary += 1
                if label not in no_benchmark_markets_all:
                    no_benchmark_markets_all.append(label)
            continue

        code = signal_codes.get(int(row.signal_id))
        if not code:
            continue
        eval_days = int(row.eval_window_days)
        w_key = (code, row.anchor_date, eval_days)
        if w_key not in window_cache:
            bars = service.stock_repo.get_forward_bars(
                code=code, analysis_date=row.anchor_date, eval_window_days=eval_days
            )
            window_cache[w_key] = bars[eval_days - 1].date if len(bars) >= eval_days else None
        end_date = window_cache[w_key]
        if end_date is None:
            continue
        span = market_spans.setdefault(market_key, [row.anchor_date, end_date])
        if row.anchor_date < span[0]:
            span[0] = row.anchor_date
        if end_date > span[1]:
            span[1] = end_date
        group = "buy" if str(row.action or "") in _BUY_ACTIONS else "sell"
        prepared.append({
            "market": market_key,
            "horizon": horizon,
            "group": group,
            "anchor_date": row.anchor_date,
            "end_date": end_date,
            "stock_return_pct": float(row.stock_return_pct),
        })

    series_by_market: Dict[str, _Series] = {}
    for market_key, (min_start, max_end) in market_spans.items():
        index_sym = BENCHMARKS[market_key]["index"]
        try:
            closes = history(index_sym, min_start - timedelta(days=10), max_end) or {}
        except Exception as exc:  # noqa: BLE001 - fail-open
            logger.info("[paper-benchmark] signal index fetch failed market=%s: %s", market_key, exc)
            closes = {}
        series_by_market[market_key] = _Series(closes)

    samples_by_horizon: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    missing_index_primary = 0
    for item in prepared:
        series = series_by_market.get(item["market"])
        start_idx = series.at(item["anchor_date"]) if series else None
        end_idx = series.at(item["end_date"]) if series else None
        if not start_idx or not end_idx or start_idx <= 0 or end_idx <= 0:
            if item["horizon"] == _PRIMARY_BENCHMARK_HORIZON:
                missing_index_primary += 1
            continue
        index_ret = (end_idx - start_idx) / start_idx * 100.0
        excess = item["stock_return_pct"] - index_ret
        beat = excess > 0.0 if item["group"] == "buy" else excess < 0.0
        bucket = samples_by_horizon.setdefault(item["horizon"], {"buy": [], "sell": []})
        bucket[item["group"]].append({
            "excess_pct": excess,
            "beat": beat,
        })

    by_horizon_summary = {
        horizon: {
            "buy": _summarize_benchmark_bucket(groups["buy"]),
            "sell": _summarize_benchmark_bucket(groups["sell"]),
        }
        for horizon, groups in samples_by_horizon.items()
    }
    primary_raw = samples_by_horizon.get(_PRIMARY_BENCHMARK_HORIZON, {"buy": [], "sell": []})
    primary_groups = {
        "buy": _summarize_benchmark_bucket(primary_raw["buy"]),
        "sell": _summarize_benchmark_bucket(primary_raw["sell"]),
    }
    combined_10d = _summarize_benchmark_bucket([*primary_raw["buy"], *primary_raw["sell"]])
    return {
        "primary_horizon": _PRIMARY_BENCHMARK_HORIZON,
        "min_sample": MIN_SIGNAL_SAMPLE,
        "groups": primary_groups,
        "combined_10d": combined_10d,
        "by_horizon": by_horizon_summary,
        "no_benchmark_markets": sorted(no_benchmark_markets_all),
        "no_benchmark_count": no_benchmark_count_primary,
        "missing_index_data_count": missing_index_primary,
    }


def _format_benchmark_group_line(label: str, bucket: Dict[str, Any]) -> str:
    n = int(bucket.get("n") or 0)
    beat_rate = bucket.get("beat_rate_pct")
    avg_excess = bucket.get("avg_excess_pct")
    rate_str = "n/a" if beat_rate is None else f"%{beat_rate:.0f}"
    excess_str = _pct(avg_excess)
    ci90 = bucket.get("beat_rate_ci90_pct")
    if bucket.get("sample_sufficient") and isinstance(ci90, (list, tuple)) and len(ci90) == 2:
        sample_note = f"%90 GA %{ci90[0]:.0f}–%{ci90[1]:.0f}"
    else:
        sample_note = "örnek yetersiz"
    return f"Endekse göre: {label} sinyallerinin {rate_str}'i 10 günde endeksi geçti (n={n}, ort. fark {excess_str}, {sample_note})"


def _format_signal_outcomes_section(outcomes: Dict[str, Any]) -> List[str]:
    if not isinstance(outcomes, dict) or not outcomes:
        return []
    completed = int(outcomes.get("completed") or 0)
    total = int(outcomes.get("total") or 0)
    status_line = _signal_outcome_status_line(outcomes)
    merged = int(outcomes.get("duplicate_checks_merged") or 0)
    merged_line = (
        f"Aynı gün tekrarlanan sinyaller tek sayıldı ({merged} kontrol birleştirildi)." if merged > 0 else None
    )
    if completed <= 0:
        if total > 0:
            lines = [f"🎯 Sinyal isabeti: {total} kontrolün hiçbiri henüz sonuçlanmadı."]
            if status_line:
                lines.append(status_line)
            if merged_line:
                lines.append(merged_line)
            return lines
        return []
    hit = int(outcomes.get("hit") or 0)
    miss = int(outcomes.get("miss") or 0)
    neutral = int(outcomes.get("neutral") or 0)
    hit_rate = outcomes.get("hit_rate_pct")
    avg_ret = outcomes.get("avg_stock_return_pct")
    rate_str = "n/a" if hit_rate is None else f"%{hit_rate:.0f}"
    lines = [
        f"🎯 Sinyal isabeti (±%2 nötr bant): {completed} değerlendirme | isabet {rate_str} "
        f"({hit} doğru / {miss} yanlış / {neutral} nötr) | ort. getiri {_pct(avg_ret)}"
    ]
    if hit + miss < MIN_SIGNAL_SAMPLE:
        lines.append(
            f"Not: yönlü sonuç sayısı {hit + miss} (< {MIN_SIGNAL_SAMPLE}); isabet oranı henüz istatistiksel olarak anlamlı değil."
        )
    if status_line:
        lines.append(status_line)
    if merged_line:
        lines.append(merged_line)
    horizon_parts: List[str] = []
    for horizon, label in _HORIZON_LABELS_TR.items():
        bucket = (outcomes.get("by_horizon") or {}).get(horizon)
        if not bucket or int(bucket.get("completed") or 0) <= 0:
            continue
        h_rate = bucket.get("hit_rate_pct")
        h_rate_str = "n/a" if h_rate is None else f"%{h_rate:.0f}"
        h_denom = int(bucket.get("hit") or 0) + int(bucket.get("miss") or 0)
        horizon_parts.append(
            f"{label} {h_rate_str} ({bucket.get('hit', 0)}/{h_denom}, ort. {_pct(bucket.get('avg_stock_return_pct'))})"
        )
    if horizon_parts:
        lines.append("Ufuklar: " + " | ".join(horizon_parts))
    action_parts: List[str] = []
    for action, bucket in (outcomes.get("by_action") or {}).items():
        if int(bucket.get("completed") or 0) <= 0:
            continue
        a_rate = bucket.get("hit_rate_pct")
        a_rate_str = "n/a" if a_rate is None else f"%{a_rate:.0f}"
        a_denom = int(bucket.get("hit") or 0) + int(bucket.get("miss") or 0)
        label = _ACTION_LABELS_TR.get(action, action)
        action_parts.append(f"{label} {a_rate_str} ({bucket.get('hit', 0)}/{a_denom})")
    if action_parts:
        lines.append("Yön bazında: " + " | ".join(action_parts))
    bench = outcomes.get("benchmark_comparison") or {}
    groups = bench.get("groups") or {}
    for key, label in (("buy", "al"), ("sell", "azalt/sat")):
        bucket = groups.get(key) or {}
        if int(bucket.get("n") or 0) > 0:
            lines.append(_format_benchmark_group_line(label, bucket))
    no_bench_markets = bench.get("no_benchmark_markets") or []
    no_bench_count = int(bench.get("no_benchmark_count") or 0)
    if no_bench_count > 0:
        markets_str = ", ".join(str(m) for m in no_bench_markets)
        lines.append(f"Endekse göre: {markets_str} pazarı için endeks yok (n={no_bench_count})")
    missing_idx = int(bench.get("missing_index_data_count") or 0)
    if missing_idx > 0:
        lines.append(f"Endekse göre: 10g karşılaştırma için endeks fiyat verisi bulunamadı (n={missing_idx})")
    return lines


def format_paper_trading_report(
    summary: Dict[str, Any],
    *,
    outcome_stats: Optional[Dict[str, Any]] = None,
) -> str:
    """Plain-text (Turkish) paper trading summary for notifications / console."""
    lines = ["📒 Sanal işlem özeti"]
    win_rate = summary.get("win_rate_pct")
    sl_count = int(summary.get("stop_loss_count") or 0)
    tp_count = int(summary.get("take_profit_count") or 0)
    extra_stops = f" | ZK/KA: {sl_count}/{tp_count}" if (sl_count or tp_count) else ""
    lines.append(
        f"İşlem: {summary.get('trade_count', 0)} | Açık pozisyon: {summary.get('open_position_count', 0)} | "
        f"Kapanan: {summary.get('closed_trade_count', 0)}{extra_stops} | Kazanma oranı: "
        f"{'n/a' if win_rate is None else f'%{win_rate:.0f}'}"
    )
    for currency, totals in (summary.get("totals_by_currency") or {}).items():
        lines.append(
            f"{currency}: gerçekleşen {totals.get('realized_pnl', 0):,.2f} | gerçekleşmeyen "
            f"{totals.get('unrealized_pnl', 0):,.2f} | piyasa değeri {totals.get('market_value', 0):,.2f}"
        )
    for benchmark in (summary.get("benchmarks") or {}).values():
        lines.append(
            f"Kıyas ({benchmark['benchmark_name']}): strateji {_pct(benchmark['strategy_return_pct'])} | "
            f"endeks {_pct(benchmark['benchmark_return_pct'])} | fark {_pct(benchmark['excess_return_pct'])} | "
            f"dolar bazında {_pct(benchmark['usd_return_pct'])} (USD/TRY {_pct(benchmark['fx_change_pct'])})"
        )
    for position in summary.get("positions") or []:
        stop_val = position.get("stop_loss")
        tp_val = position.get("take_profit")
        atr_pct = position.get("atr_pct")
        risk_parts: List[str] = []
        if stop_val is not None and tp_val is not None:
            risk_parts.append(f"ZK {stop_val:,.2f} / KA {tp_val:,.2f}")
        if atr_pct is not None:
            risk_parts.append(f"ATR %{atr_pct:.1f}")
        risk_suffix = f" ({', '.join(risk_parts)})" if risk_parts else ""
        lines.append(
            f"- {position['stock_code']}: {position['quantity']:g} adet, maliyet {position['avg_cost']:,.2f}, "
            f"son {position['last_close'] if position['last_close'] is not None else 'n/a'}, "
            f"K/Z {_pct(position.get('unrealized_pnl_pct'))}{risk_suffix}"
        )
    effective_outcomes = outcome_stats if outcome_stats is not None else summary.get("signal_outcomes")
    lines.extend(_format_signal_outcomes_section(effective_outcomes or {}))
    lines.append("Not: sanal işlemdir; komisyon, kayma ve vergi dahil değildir.")
    return "\n".join(lines)


def _load_weekly_state(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (FileNotFoundError, OSError, ValueError):
        return {}


def _save_weekly_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=0)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".weekly_report_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(payload)
    os.replace(tmp_name, path)


def _crypto_trend_weekly_text() -> str:
    """Crypto trend paper book summary for the weekly report ("" when disabled / not started)."""
    try:
        from src.config import get_config

        config = get_config()
        if not getattr(config, "crypto_trend_enabled", False):
            return ""
        from src.services.crypto_trend_strategy import TrendConfig
        from src.services.strategy_paper_book import StrategyPaperBook, format_book_report

        book = StrategyPaperBook(config=TrendConfig(assets=tuple(config.crypto_trend_assets)),
                                 initial_capital=float(config.crypto_trend_capital))
        summary = book.summary()
        return format_book_report(summary) if summary.get("days") else ""
    except Exception as exc:  # noqa: BLE001 - optional section, fail-open
        logger.info("[weekly-report] crypto trend section skipped: %s", exc)
        return ""


def _quant_paper_weekly_text() -> str:
    """PAA & Meta-Portfolio A StrategyPaperBook summary for the weekly report."""
    try:
        from src.config import get_config

        config = get_config()
        if not getattr(config, "quant_paper_enabled", False):
            return ""
        from src.quant.paper_book import get_quant_paper_books_status, resolve_active_quant_paper_strategies

        res = get_quant_paper_books_status(
            strategies=tuple(resolve_active_quant_paper_strategies(getattr(config, "quant_paper_strategies", None))),
            initial_capital=float(getattr(config, "quant_paper_capital", 10000.0)),
            cost_bps=float(getattr(config, "quant_paper_cost_bps", 5.0)),
            rebalance_mode=str(getattr(config, "quant_paper_rebalance_mode", "monthly")),
        )
        active = [b.get("report_text") for b in (res.get("books") or []) if b.get("days") and b.get("report_text")]
        return "\n\n".join(active)
    except Exception as exc:  # noqa: BLE001 - optional section, fail-open
        logger.info("[weekly-report] quant paper section skipped: %s", exc)
        return ""


def maybe_send_weekly_performance_report(
    *,
    notifier: Any = None,
    db_manager: Optional[Any] = None,
    state_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    history: HistoryProvider = yfinance_history,
    market: Optional[str] = None,
    force: bool = False,
    after_hour: int = 18,
) -> bool:
    """Evaluate signal outcomes and, on Friday after close (Istanbul), send the weekly report once.

    Always runs :func:`evaluate_signal_outcomes` so forward outcomes stay fresh
    after daily runs. Sends the notification at most once per ISO week unless
    ``force=True``. Fail-open: never raises.
    """
    outcomes = evaluate_signal_outcomes(market=market, db_manager=db_manager)
    local_now = (now or datetime.now(timezone.utc)).astimezone(_ISTANBUL_TZ)
    if not force and (local_now.weekday() != 4 or local_now.hour < int(after_hour)):
        return False

    iso = local_now.isocalendar()
    iso_week = f"{iso.year}-W{iso.week:02d}"
    target_state = Path(state_path or DEFAULT_WEEKLY_REPORT_STATE_PATH)
    state = _load_weekly_state(target_state)
    if not force and state.get("last_sent_week") == iso_week:
        return False

    try:
        from src.services.paper_trading_service import PaperTradingService
        from src.config import get_config

        cfg = get_config()
        if bool(getattr(cfg, "notification_simple_mode", False)):
            from src.services.simple_notification import format_simple_morning_summary

            text = format_simple_morning_summary()
            if notifier is None:
                from src.notification import NotificationService

                notifier = NotificationService()
            delivered = bool(notifier.send(text, dedup_key=f"weekly-performance:{iso_week}:simple"))
            if delivered:
                _save_weekly_state(
                    target_state,
                    {"last_sent_week": iso_week, "sent_at": local_now.isoformat(), "mode": "simple"},
                )
            return delivered

        summary = PaperTradingService(db_manager=db_manager).get_summary(
            include_benchmarks=True,
            benchmark_history=history,
        )
        crypto_text = _crypto_trend_weekly_text()
        quant_text = _quant_paper_weekly_text()
        stock_activity = summary.get("trade_count", 0) or int(outcomes.get("total") or 0)
        if not stock_activity and not crypto_text and not quant_text:
            return False
        text = format_paper_trading_report(summary, outcome_stats=outcomes) if stock_activity else ""
        if crypto_text:
            text = f"{text}\n\n{crypto_text}" if text else crypto_text
        if quant_text:
            text = f"{text}\n\n{quant_text}" if text else quant_text
        if notifier is None:
            from src.notification import NotificationService

            notifier = NotificationService()
        delivered = bool(notifier.send(text, dedup_key=f"weekly-performance:{iso_week}"))
        if delivered:
            _save_weekly_state(
                target_state,
                {"last_sent_week": iso_week, "sent_at": local_now.isoformat()},
            )
        return delivered
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.warning("[paper-benchmark] weekly report failed: %s", exc)
        return False


__all__: List[str] = [
    "BENCHMARKS",
    "DEFAULT_WEEKLY_REPORT_STATE_PATH",
    "compute_benchmarks",
    "compute_market_benchmark",
    "evaluate_signal_outcomes",
    "format_paper_trading_report",
    "maybe_send_weekly_performance_report",
    "yfinance_history",
]
