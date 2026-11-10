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
}

# market -> benchmark index and USD rate (quote currency per 1 USD).
BENCHMARKS: Dict[str, Dict[str, str]] = {
    "tr": {"index": "XU100.IS", "index_name": "BIST 100", "fx": "TRY=X", "currency": "TRY"},
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
    fx = _Series(history(spec["fx"], start, today))

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
        index_close, fx_rate = index.at(day), fx.at(day)
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
    index_today, fx_today = index.at(today), fx.at(today)
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
        usd_value = open_value / fx_today
        result["usd_return_pct"] = round((usd_proceeds + usd_value - usd_invested) / usd_invested * 100, 2)
        first_rate = fx.at(min(_parse_day(trade["trade_date"]) for trade in rows))
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
) -> Dict[str, Any]:
    """Run pending DecisionSignal outcome evaluations (1/3/5/10d) and summarize hit rates.

    Fail-open: returns ``{}`` on any database or evaluation error.
    """
    try:
        from src.services.decision_signal_outcome_service import (
            DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
            DEFAULT_STATS_STATUSES,
            SUPPORTED_OUTCOME_HORIZONS,
            DecisionSignalOutcomeService,
        )

        service = DecisionSignalOutcomeService(db_manager=db_manager)
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
            "by_horizon": by_horizon,
            "by_action": by_action,
        }
    except Exception as exc:  # noqa: BLE001 - optional reporting helper, fail-open
        logger.info("[paper-benchmark] signal outcome evaluation failed: %s", exc)
        return {}


def _format_signal_outcomes_section(outcomes: Dict[str, Any]) -> List[str]:
    if not isinstance(outcomes, dict) or not outcomes:
        return []
    completed = int(outcomes.get("completed") or 0)
    total = int(outcomes.get("total") or 0)
    if completed <= 0:
        if total > 0:
            return [f"🎯 Sinyal isabeti: henüz yeterli ileri gün kapanışı birikmedi ({total} bekleyen kontrol)"]
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

        summary = PaperTradingService(db_manager=db_manager).get_summary(
            include_benchmarks=True,
            benchmark_history=history,
        )
        if summary.get("trade_count", 0) == 0 and int(outcomes.get("total") or 0) == 0:
            return False
        text = format_paper_trading_report(summary, outcome_stats=outcomes)
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
