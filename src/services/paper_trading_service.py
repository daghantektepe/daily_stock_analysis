# -*- coding: utf-8 -*-
"""Paper trading: mirror analysis DecisionSignals into a simulated ledger.

The ledger (``paper_trades``) answers one question: *if every new analysis
signal had been followed mechanically, how would it have done?* It is opt-in
(``PAPER_TRADING_ENABLED``), never places orders, and is deliberately separate
from Portfolio so simulated fills cannot leak into real holdings, portfolio
risk, or the holding context that analysis reads.

Fill rules (one fill per signal, idempotent on ``signal_id``):

- ``buy`` / ``add``: open a position of ``PAPER_TRADING_POSITION_SIZE`` (in the
  stock's quote currency) when flat; no pyramiding while already holding.
- ``reduce``: sell half of the open quantity (all of it if that rounds to 0).
- ``sell``: close the open position.
- ``hold`` / ``watch`` / ``avoid`` / ``alert``: no trade.

Fills use the analysis-time current price with whole-share quantities and no
fees or slippage. Valuation marks open positions to the latest stored daily
close. Amounts are reported per currency; currencies are never mixed.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from src.config import get_config
from src.storage import DatabaseManager, PaperTradeRecord, StockDaily

logger = logging.getLogger(__name__)

BUY_ACTIONS = frozenset({"buy", "add"})
SELL_ALL_ACTIONS = frozenset({"sell"})
REDUCE_ACTIONS = frozenset({"reduce"})
_MARKET_CURRENCY = {
    "cn": "CNY",
    "hk": "HKD",
    "us": "USD",
    "jp": "JPY",
    "kr": "KRW",
    "tw": "TWD",
    "tr": "TRY",
}
_EPS = 1e-9


class PaperTradingService:
    """Apply DecisionSignals to the paper ledger and summarize performance."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        *,
        enabled: Optional[bool] = None,
        position_size: Optional[float] = None,
    ) -> None:
        self.db = db_manager or DatabaseManager.get_instance()
        if enabled is None or position_size is None:
            config = get_config()
            if enabled is None:
                enabled = bool(getattr(config, "paper_trading_enabled", False))
            if position_size is None:
                position_size = float(getattr(config, "paper_trading_position_size", 10000.0))
        self.enabled = bool(enabled)
        self.position_size = float(position_size)

    # ------------------------------------------------------------------ write
    def apply_signal(
        self,
        signal: Dict[str, Any],
        *,
        price: Any,
        trade_date: Optional[date] = None,
    ) -> Optional[Dict[str, Any]]:
        """Record the simulated fill for one signal; ``None`` when nothing trades.

        Never raises for unsupported input: disabled service, non-trading
        actions, missing price, or an already-filled signal all return ``None``.
        """
        if not self.enabled or not isinstance(signal, dict):
            return None
        action = str(signal.get("action") or "").strip().lower()
        signal_id = signal.get("id")
        stock_code = str(signal.get("stock_code") or "").strip().upper()
        fill_price = _positive_float(price)
        if not isinstance(signal_id, int) or not stock_code or fill_price is None:
            return None
        if action not in BUY_ACTIONS | SELL_ALL_ACTIONS | REDUCE_ACTIONS:
            return None

        held = self.open_quantity(stock_code)
        if action in BUY_ACTIONS:
            if held > _EPS:
                return None
            side = "buy"
            quantity = float(math.floor(self.position_size / fill_price))
        else:
            if held <= _EPS:
                return None
            side = "sell"
            if action in REDUCE_ACTIONS:
                quantity = float(math.floor(held / 2)) or held
            else:
                quantity = held
        if quantity <= 0:
            logger.info(
                "[paper] skip %s %s: position size %.2f below one share at %.4f",
                action, stock_code, self.position_size, fill_price,
            )
            return None

        market = str(signal.get("market") or "").strip().lower() or None
        record = PaperTradeRecord(
            signal_id=signal_id,
            stock_code=stock_code,
            stock_name=(str(signal.get("stock_name") or "").strip() or None),
            market=market,
            currency=_MARKET_CURRENCY.get(market or "", None),
            action=action,
            side=side,
            quantity=quantity,
            price=fill_price,
            trade_date=trade_date or date.today(),
        )
        try:
            with self.db.session_scope() as session:
                session.add(record)
                session.flush()
                payload = _trade_to_dict(record)
        except IntegrityError:
            logger.info("[paper] signal %s already filled; skipping", signal_id)
            return None
        logger.info(
            "[paper] %s %s x%s @ %s (signal %s)",
            side, stock_code, quantity, fill_price, signal_id,
        )
        return payload

    # ------------------------------------------------------------------- read
    def open_quantity(self, stock_code: str) -> float:
        code = str(stock_code or "").strip().upper()
        with self.db.session_scope() as session:
            rows = session.execute(
                select(PaperTradeRecord.side, PaperTradeRecord.quantity).where(
                    PaperTradeRecord.stock_code == code
                )
            ).all()
        quantity = 0.0
        for side, qty in rows:
            quantity += qty if side == "buy" else -qty
        return max(0.0, quantity)

    def list_trades(self, *, limit: int = 200) -> List[Dict[str, Any]]:
        with self.db.session_scope() as session:
            rows = session.execute(
                select(PaperTradeRecord)
                .order_by(desc(PaperTradeRecord.trade_date), desc(PaperTradeRecord.id))
                .limit(max(1, int(limit)))
            ).scalars().all()
            return [_trade_to_dict(row) for row in rows]

    def get_summary(
        self,
        *,
        include_benchmarks: bool = False,
        benchmark_history: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Positions, realized/unrealized P&L and win rate, grouped per currency.

        ``include_benchmarks`` adds per-market index-shadow and USD-based returns
        (``benchmarks``; Borsa Istanbul vs BIST 100 / USD-TRY), fetched fail-open.
        """
        with self.db.session_scope() as session:
            trades = session.execute(
                select(PaperTradeRecord).order_by(PaperTradeRecord.trade_date, PaperTradeRecord.id)
            ).scalars().all()
            trade_dicts = [_trade_to_dict(row) for row in trades]

        books: Dict[str, Dict[str, Any]] = {}
        closed_results: List[float] = []
        for trade in trade_dicts:
            book = books.setdefault(
                trade["stock_code"],
                {
                    "stock_code": trade["stock_code"],
                    "stock_name": trade["stock_name"],
                    "market": trade["market"],
                    "currency": trade["currency"],
                    "quantity": 0.0,
                    "cost": 0.0,
                    "realized_pnl": 0.0,
                    "trade_count": 0,
                },
            )
            book["trade_count"] += 1
            if trade["side"] == "buy":
                book["quantity"] += trade["quantity"]
                book["cost"] += trade["quantity"] * trade["price"]
                continue
            if book["quantity"] <= _EPS:
                continue
            avg_cost = book["cost"] / book["quantity"]
            sold = min(trade["quantity"], book["quantity"])
            pnl = (trade["price"] - avg_cost) * sold
            book["realized_pnl"] += pnl
            book["cost"] -= avg_cost * sold
            book["quantity"] -= sold
            closed_results.append(pnl)

        positions: List[Dict[str, Any]] = []
        totals: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"cost": 0.0, "market_value": 0.0, "realized_pnl": 0.0, "unrealized_pnl": 0.0}
        )
        for book in books.values():
            currency = book["currency"] or "UNKNOWN"
            totals[currency]["realized_pnl"] += book["realized_pnl"]
            if book["quantity"] <= _EPS:
                continue
            last_close, last_date = self._latest_close(book["stock_code"])
            avg_cost = book["cost"] / book["quantity"]
            mark = last_close if last_close is not None else avg_cost
            market_value = mark * book["quantity"]
            unrealized = market_value - book["cost"]
            totals[currency]["cost"] += book["cost"]
            totals[currency]["market_value"] += market_value
            totals[currency]["unrealized_pnl"] += unrealized
            positions.append({
                "stock_code": book["stock_code"],
                "stock_name": book["stock_name"],
                "market": book["market"],
                "currency": book["currency"],
                "quantity": book["quantity"],
                "avg_cost": round(avg_cost, 6),
                "last_close": last_close,
                "last_close_date": last_date.isoformat() if last_date else None,
                "price_stale": last_close is None,
                "market_value": round(market_value, 6),
                "unrealized_pnl": round(unrealized, 6),
                "unrealized_pnl_pct": round(unrealized / book["cost"] * 100, 4) if book["cost"] > _EPS else None,
                "realized_pnl": round(book["realized_pnl"], 6),
            })
        positions.sort(key=lambda item: item["stock_code"])

        wins = sum(1 for pnl in closed_results if pnl > 0)
        benchmarks: Dict[str, Any] = {}
        if include_benchmarks and trade_dicts:
            from src.services.paper_trading_benchmark import compute_benchmarks, yfinance_history

            mark_prices = {
                position["stock_code"]: (
                    position["last_close"] if position["last_close"] is not None else position["avg_cost"]
                )
                for position in positions
            }
            benchmarks = compute_benchmarks(
                trade_dicts, mark_prices=mark_prices, history=benchmark_history or yfinance_history,
            )
        return {
            "enabled": self.enabled,
            "position_size": self.position_size,
            "trade_count": len(trade_dicts),
            "open_position_count": len(positions),
            "closed_trade_count": len(closed_results),
            "win_rate_pct": round(wins / len(closed_results) * 100, 2) if closed_results else None,
            "positions": positions,
            "totals_by_currency": {
                currency: {key: round(value, 6) for key, value in values.items()}
                for currency, values in sorted(totals.items())
            },
            "benchmarks": benchmarks,
        }

    def _latest_close(self, stock_code: str) -> tuple[Optional[float], Optional[date]]:
        with self.db.session_scope() as session:
            row = session.execute(
                select(StockDaily.close, StockDaily.date)
                .where(StockDaily.code == stock_code)
                .order_by(desc(StockDaily.date))
                .limit(1)
            ).first()
        if row is None:
            return None, None
        close = _positive_float(row[0])
        return close, row[1] if close is not None else None


def _positive_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number) or number <= 0:
        return None
    return number


def _trade_to_dict(row: PaperTradeRecord) -> Dict[str, Any]:
    return {
        "id": row.id,
        "signal_id": row.signal_id,
        "stock_code": row.stock_code,
        "stock_name": row.stock_name,
        "market": row.market,
        "currency": row.currency,
        "action": row.action,
        "side": row.side,
        "quantity": row.quantity,
        "price": row.price,
        "trade_date": row.trade_date.isoformat() if row.trade_date else None,
    }


def apply_paper_trade_for_signal(signal_result: Any, *, price: Any) -> Optional[Dict[str, Any]]:
    """Best-effort pipeline hook: fill newly created analysis signals.

    ``signal_result`` is the ``{"item": ..., "created": ...}`` payload returned by
    ``DecisionSignalService.create_signal``. Duplicates/refreshes do not trade.
    Fail-open: errors are logged and never reach the analysis flow.
    """
    try:
        if not isinstance(signal_result, dict) or not signal_result.get("created"):
            return None
        service = PaperTradingService()
        if not service.enabled:
            return None
        return service.apply_signal(signal_result.get("item") or {}, price=price)
    except Exception as exc:  # noqa: BLE001 - optional sidecar, fail-open
        logger.warning("[paper] apply failed: %s", exc)
        return None
