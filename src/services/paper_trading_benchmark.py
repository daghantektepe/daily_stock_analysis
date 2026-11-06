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
import logging
import threading
import time
from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

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


def format_paper_trading_report(summary: Dict[str, Any]) -> str:
    """Plain-text (Turkish) paper trading summary for notifications / console."""
    lines = ["📒 Sanal işlem özeti"]
    win_rate = summary.get("win_rate_pct")
    lines.append(
        f"İşlem: {summary.get('trade_count', 0)} | Açık pozisyon: {summary.get('open_position_count', 0)} | "
        f"Kapanan: {summary.get('closed_trade_count', 0)} | Kazanma oranı: "
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
        lines.append(
            f"- {position['stock_code']}: {position['quantity']:g} adet, maliyet {position['avg_cost']:,.2f}, "
            f"son {position['last_close'] if position['last_close'] is not None else 'n/a'}, "
            f"K/Z {_pct(position.get('unrealized_pnl_pct'))}"
        )
    lines.append("Not: sanal işlemdir; komisyon, kayma ve vergi dahil değildir.")
    return "\n".join(lines)


__all__: List[str] = [
    "BENCHMARKS",
    "compute_benchmarks",
    "compute_market_benchmark",
    "format_paper_trading_report",
    "yfinance_history",
]
