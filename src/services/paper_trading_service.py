# -*- coding: utf-8 -*-
"""Paper trading: mirror analysis DecisionSignals into a simulated ledger.

The ledger (``paper_trades``) answers one question: *if every new analysis
signal had been followed mechanically, how would it have done?* It is opt-in
(``PAPER_TRADING_ENABLED``), never places orders, and is deliberately separate
from Portfolio so simulated fills cannot leak into real holdings, portfolio
risk, or the holding context that analysis reads.

Fill rules (one fill per signal, idempotent on ``signal_id``):

- ``buy`` / ``add``: open a position when flat; no pyramiding while already
  holding. Position size is scaled down by 14-day ATR volatility (or explicit
  signal ``stop_loss``) so per-trade risk stays within ``PAPER_TRADING_RISK_PCT``
  of ``PAPER_TRADING_POSITION_SIZE``, falling back to ``floor(position_size / price)``
  when no ATR history or signal stop is available.
- ``reduce``: sell half of the open quantity (all of it if that rounds to 0).
- ``sell``: close the open position.
- ``stop_loss`` / ``take_profit``: automatically close the open position when
  subsequent daily ``StockDaily`` low/high (or live price) crosses the position's
  active stop-loss or take-profit level.
- ``hold`` / ``watch`` / ``avoid`` / ``alert``: no new signal trade.

Fills use whole-share quantities and no fees or slippage. Valuation marks open
positions to the latest stored daily close. Amounts are reported per currency;
currencies are never mixed.
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
AUTO_EXIT_ACTIONS = frozenset({"stop_loss", "take_profit"})
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


def compute_atr14(
    stock_code: str,
    *,
    db_manager: Optional[DatabaseManager] = None,
    as_of_date: Optional[date] = None,
    period: int = 14,
    min_bars: int = 5,
) -> Optional[float]:
    """Compute 14-day Average True Range (ATR) from stored ``StockDaily`` bars.

    Returns ``None`` when fewer than ``min_bars`` OHLC bars with non-zero intraday
    range exist on or before ``as_of_date``.
    """
    code = str(stock_code or "").strip().upper()
    if not code:
        return None
    db = db_manager or DatabaseManager.get_instance()
    stmt = select(StockDaily.date, StockDaily.high, StockDaily.low, StockDaily.close).where(
        StockDaily.code == code
    )
    if as_of_date is not None:
        stmt = stmt.where(StockDaily.date <= as_of_date)
    stmt = stmt.order_by(desc(StockDaily.date)).limit(max(period + 5, min_bars + 1))
    with db.session_scope() as session:
        rows = list(reversed(session.execute(stmt).all()))

    valid_bars = []
    has_intraday_range = False
    for row_date, high, low, close in rows:
        c_val = _positive_float(close)
        if c_val is None:
            continue
        h_val = _positive_float(high) or c_val
        l_val = _positive_float(low) or c_val
        if h_val < l_val:
            h_val, l_val = l_val, h_val
        if h_val - l_val > _EPS:
            has_intraday_range = True
        valid_bars.append((row_date, h_val, l_val, c_val))

    if len(valid_bars) < min_bars or not has_intraday_range:
        return None

    true_ranges: List[float] = []
    prev_close: Optional[float] = None
    for _day, h_val, l_val, c_val in valid_bars:
        if prev_close is None:
            tr = h_val - l_val
        else:
            tr = max(h_val - l_val, abs(h_val - prev_close), abs(l_val - prev_close))
        true_ranges.append(max(0.0, tr))
        prev_close = c_val

    window = true_ranges[-period:]
    if not window:
        return None
    atr = sum(window) / len(window)
    return round(atr, 6) if atr > _EPS else None


def compute_atr_risk_plan(
    stock_code: str,
    *,
    price: float,
    position_size: float = 10000.0,
    risk_pct: float = 5.0,
    atr_stop_multiplier: float = 2.0,
    atr_take_profit_multiplier: float = 3.0,
    default_stop_loss_pct: float = 7.0,
    default_take_profit_pct: float = 14.0,
    signal: Optional[Dict[str, Any]] = None,
    atr14: Optional[float] = None,
    db_manager: Optional[DatabaseManager] = None,
    as_of_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Compute ATR-based stop-loss, take-profit, and volatility-adjusted position size."""
    entry_price = _positive_float(price) or 0.0
    if atr14 is None and db_manager is not None and entry_price > 0:
        atr14 = compute_atr14(stock_code, db_manager=db_manager, as_of_date=as_of_date)

    atr_pct = round(atr14 / entry_price * 100.0, 2) if (atr14 and entry_price > 0) else None
    sig = signal if isinstance(signal, dict) else {}

    sig_stop = _positive_float(sig.get("stop_loss"))
    if sig_stop is not None and 0 < sig_stop < entry_price:
        stop_loss = round(sig_stop, 4)
        stop_source = "signal"
    elif atr14 is not None and atr14 > 0 and entry_price > 0:
        stop_loss = round(max(entry_price * 0.5, entry_price - atr_stop_multiplier * atr14), 4)
        stop_source = "atr"
    else:
        stop_loss = round(entry_price * (1.0 - default_stop_loss_pct / 100.0), 4)
        stop_source = "fallback_pct"

    sig_tp = _positive_float(sig.get("take_profit") or sig.get("target_price"))
    if sig_tp is not None and sig_tp > entry_price > 0:
        take_profit = round(sig_tp, 4)
        take_profit_source = "signal"
    elif atr14 is not None and atr14 > 0 and entry_price > 0:
        take_profit = round(entry_price + atr_take_profit_multiplier * atr14, 4)
        take_profit_source = "atr"
    else:
        take_profit = round(entry_price * (1.0 + default_take_profit_pct / 100.0), 4)
        take_profit_source = "fallback_pct"

    max_notional_qty = math.floor(position_size / entry_price) if entry_price > 0 else 0
    risk_budget = position_size * (max(0.1, float(risk_pct)) / 100.0)
    per_share_risk = max(entry_price - stop_loss, entry_price * 0.005) if entry_price > 0 else 0.0

    if stop_source in ("atr", "signal") and per_share_risk > 0:
        risk_qty = math.floor(risk_budget / per_share_risk)
        recommended_quantity = float(min(max_notional_qty, risk_qty))
        sizing_method = "atr_risk" if stop_source == "atr" else "signal_risk"
    else:
        recommended_quantity = float(max_notional_qty)
        sizing_method = "fixed_notional"

    stop_loss_pct = round((stop_loss - entry_price) / entry_price * 100.0, 2) if entry_price > 0 else None
    take_profit_pct = round((take_profit - entry_price) / entry_price * 100.0, 2) if entry_price > 0 else None
    reward_risk = (
        round((take_profit - entry_price) / (entry_price - stop_loss), 2)
        if entry_price > stop_loss > 0
        else None
    )
    return {
        "stock_code": str(stock_code or "").strip().upper(),
        "price": entry_price,
        "atr14": atr14,
        "atr_pct": atr_pct,
        "stop_loss": stop_loss,
        "stop_loss_pct": stop_loss_pct,
        "stop_source": stop_source,
        "take_profit": take_profit,
        "take_profit_pct": take_profit_pct,
        "take_profit_source": take_profit_source,
        "reward_risk_ratio": reward_risk,
        "position_size_budget": round(float(position_size), 2),
        "risk_budget": round(risk_budget, 2),
        "recommended_quantity": recommended_quantity,
        "recommended_notional": round(recommended_quantity * entry_price, 2),
        "max_loss_amount": round(recommended_quantity * max(0.0, entry_price - stop_loss), 2),
        "sizing_method": sizing_method,
    }


class PaperTradingService:
    """Apply DecisionSignals to the paper ledger, enforce stops/targets, and summarize performance."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        *,
        enabled: Optional[bool] = None,
        position_size: Optional[float] = None,
        risk_pct: Optional[float] = None,
        atr_stop_mult: Optional[float] = None,
        atr_tp_mult: Optional[float] = None,
        commission_bps: Optional[float] = None,
        slippage_bps: Optional[float] = None,
        vol_target_pct: Optional[float] = None,
        max_holding_days: Optional[int] = None,
    ) -> None:
        self.db = db_manager or DatabaseManager.get_instance()
        config = None
        if (
            enabled is None
            or position_size is None
            or risk_pct is None
            or atr_stop_mult is None
            or atr_tp_mult is None
            or commission_bps is None
            or slippage_bps is None
            or vol_target_pct is None
            or max_holding_days is None
        ):
            config = get_config()
        if enabled is None:
            enabled = bool(getattr(config, "paper_trading_enabled", False))
        if position_size is None:
            position_size = float(getattr(config, "paper_trading_position_size", 10000.0))
        if risk_pct is None:
            risk_pct = float(getattr(config, "paper_trading_risk_pct", 5.0))
        if atr_stop_mult is None:
            atr_stop_mult = float(getattr(config, "paper_trading_atr_stop_mult", 2.0))
        if atr_tp_mult is None:
            atr_tp_mult = float(getattr(config, "paper_trading_atr_tp_mult", 3.0))
        if commission_bps is None:
            commission_bps = float(getattr(config, "paper_trading_commission_bps", 0.0) or 0.0)
        if slippage_bps is None:
            slippage_bps = float(getattr(config, "paper_trading_slippage_bps", 0.0) or 0.0)
        if vol_target_pct is None:
            raw_vt = getattr(config, "paper_trading_vol_target_pct", None)
            vol_target_pct = float(raw_vt) if raw_vt is not None else None
        if max_holding_days is None:
            raw_mhd = getattr(config, "paper_trading_max_holding_days", None)
            max_holding_days = int(raw_mhd) if raw_mhd is not None else None

        self.enabled = bool(enabled)
        self.position_size = float(position_size)
        self.risk_pct = float(risk_pct)
        self.atr_stop_mult = float(atr_stop_mult)
        self.atr_tp_mult = float(atr_tp_mult)
        self.commission_bps = max(0.0, float(commission_bps))
        self.slippage_bps = max(0.0, float(slippage_bps))
        self.vol_target_pct = float(vol_target_pct) if (vol_target_pct and float(vol_target_pct) > 0) else None
        self.max_holding_days = int(max_holding_days) if (max_holding_days and int(max_holding_days) > 0) else None

    def recommend_position(
        self,
        stock_code: str,
        *,
        price: Any = None,
        signal: Optional[Dict[str, Any]] = None,
        as_of_date: Optional[date] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return ATR-based position sizing and stop-loss / take-profit recommendation."""
        code = str(stock_code or "").strip().upper()
        if not code:
            return None
        resolved_price = _positive_float(price)
        if resolved_price is None:
            resolved_price, _ = self._latest_close(code)
        if resolved_price is None:
            return None
        return compute_atr_risk_plan(
            code,
            price=resolved_price,
            position_size=self.position_size,
            risk_pct=self.risk_pct,
            atr_stop_multiplier=self.atr_stop_mult,
            atr_take_profit_multiplier=self.atr_tp_mult,
            signal=signal,
            db_manager=self.db,
            as_of_date=as_of_date,
        )

    # ------------------------------------------------------------------ write
    def check_stops_and_targets(
        self,
        *,
        stock_code: Optional[str] = None,
        current_price: Any = None,
        as_of_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Check open positions against active stop-loss and take-profit levels and record exits.

        Inspects ``StockDaily`` bars strictly after the latest trade date of each
        open position (plus ``current_price`` when provided). Uses negative
        ``signal_id = -opening_buy_trade_id`` so each position cycle can auto-exit
        at most once without colliding with positive ``DecisionSignal`` IDs.
        """
        target_code = str(stock_code or "").strip().upper() or None
        with self.db.session_scope() as session:
            stmt = select(PaperTradeRecord).order_by(PaperTradeRecord.trade_date, PaperTradeRecord.id)
            if target_code:
                stmt = stmt.where(PaperTradeRecord.stock_code == target_code)
            trades = session.execute(stmt).scalars().all()
            trade_dicts = [_trade_to_dict(row) for row in trades]

        if not trade_dicts:
            return []

        open_books: Dict[str, Dict[str, Any]] = {}
        for trade in trade_dicts:
            code = trade["stock_code"]
            book = open_books.setdefault(
                code,
                {
                    "stock_code": code,
                    "stock_name": trade["stock_name"],
                    "market": trade["market"],
                    "currency": trade["currency"],
                    "quantity": 0.0,
                    "last_buy_id": None,
                    "last_trade_date": None,
                    "stop_loss": None,
                    "take_profit": None,
                },
            )
            t_date = _parse_iso_date(trade.get("trade_date"))
            if t_date and (book["last_trade_date"] is None or t_date > book["last_trade_date"]):
                book["last_trade_date"] = t_date

            if trade["side"] == "buy":
                if book["quantity"] <= _EPS:
                    book["last_buy_id"] = trade["id"]
                    book["stop_loss"] = _positive_float(trade.get("stop_loss"))
                    book["take_profit"] = _positive_float(trade.get("take_profit"))
                book["quantity"] += float(trade["quantity"])
            else:
                sold = min(float(trade["quantity"]), book["quantity"])
                book["quantity"] -= sold
                if book["quantity"] <= _EPS:
                    book["quantity"] = 0.0
                    book["last_buy_id"] = None
                    book["stop_loss"] = None
                    book["take_profit"] = None

        triggered: List[Dict[str, Any]] = []
        for code, book in open_books.items():
            if book["quantity"] <= _EPS or not book["last_buy_id"]:
                continue
            stop_loss = book["stop_loss"]
            take_profit = book["take_profit"]
            if stop_loss is None and take_profit is None and self.max_holding_days is None:
                continue

            exit_action: Optional[str] = None
            exit_price: Optional[float] = None
            exit_date: Optional[date] = None

            last_t_date = book["last_trade_date"]
            if last_t_date is not None:
                bar_stmt = select(
                    StockDaily.date, StockDaily.open, StockDaily.high, StockDaily.low, StockDaily.close
                ).where(
                    StockDaily.code == code,
                    StockDaily.date > last_t_date,
                )
                if as_of_date is not None:
                    bar_stmt = bar_stmt.where(StockDaily.date <= as_of_date)
                bar_stmt = bar_stmt.order_by(StockDaily.date)
                with self.db.session_scope() as session:
                    bars = session.execute(bar_stmt).all()

                for bar_date, b_open, b_high, b_low, b_close in bars:
                    c_val = _positive_float(b_close)
                    o_val = _positive_float(b_open)
                    h_val = _positive_float(b_high) or c_val
                    l_val = _positive_float(b_low) or c_val
                    if stop_loss is not None and l_val is not None and l_val <= stop_loss:
                        exit_action = "stop_loss"
                        exit_price = min(o_val, stop_loss) if (o_val is not None and o_val < stop_loss) else stop_loss
                        exit_date = bar_date
                        break
                    if take_profit is not None and h_val is not None and h_val >= take_profit:
                        exit_action = "take_profit"
                        exit_price = (
                            max(o_val, take_profit)
                            if (o_val is not None and o_val > take_profit)
                            else take_profit
                        )
                        exit_date = bar_date
                        break
                    if (
                        self.max_holding_days is not None
                        and book["last_trade_date"] is not None
                        and c_val is not None
                        and (bar_date - book["last_trade_date"]).days >= self.max_holding_days
                    ):
                        exit_action = "time_stop"
                        exit_price = c_val
                        exit_date = bar_date
                        break

            if exit_action is None and target_code == code and current_price is not None:
                live_price = _positive_float(current_price)
                if live_price is not None:
                    if stop_loss is not None and live_price <= stop_loss:
                        exit_action = "stop_loss"
                        exit_price = live_price
                        exit_date = as_of_date or date.today()
                    elif take_profit is not None and live_price >= take_profit:
                        exit_action = "take_profit"
                        exit_price = live_price
                        exit_date = as_of_date or date.today()

            if exit_action is None or exit_price is None:
                continue

            total_cost_bps = self.commission_bps + self.slippage_bps
            if total_cost_bps > 0:
                exit_price = round(exit_price * max(0.0, 1.0 - total_cost_bps / 10000.0), 6)

            synthetic_signal_id = -int(book["last_buy_id"])
            record = PaperTradeRecord(
                signal_id=synthetic_signal_id,
                stock_code=code,
                stock_name=book["stock_name"],
                market=book["market"],
                currency=book["currency"],
                action=exit_action,
                side="sell",
                quantity=book["quantity"],
                price=round(float(exit_price), 6),
                stop_loss=stop_loss,
                take_profit=take_profit,
                trade_date=exit_date or date.today(),
            )
            try:
                with self.db.session_scope() as session:
                    session.add(record)
                    session.flush()
                    payload = _trade_to_dict(record)
            except IntegrityError:
                continue
            logger.info(
                "[paper] %s triggered for %s x%s @ %s (buy trade %s)",
                exit_action, code, book["quantity"], exit_price, book["last_buy_id"],
            )
            triggered.append(payload)

        return triggered

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

        effective_date = trade_date or date.today()
        # Settle any pending stop-loss / take-profit on open position first.
        self.check_stops_and_targets(
            stock_code=stock_code,
            current_price=fill_price,
            as_of_date=effective_date,
        )

        if action not in BUY_ACTIONS | SELL_ALL_ACTIONS | REDUCE_ACTIONS:
            return None

        held = self.open_quantity(stock_code)
        stop_loss: Optional[float] = None
        take_profit: Optional[float] = None
        if action in BUY_ACTIONS:
            if held > _EPS:
                return None
            side = "buy"
            effective_pos_size = self._vol_scaled_position_size(stock_code, effective_date)
            plan = compute_atr_risk_plan(
                stock_code,
                price=fill_price,
                position_size=effective_pos_size,
                risk_pct=self.risk_pct,
                atr_stop_multiplier=self.atr_stop_mult,
                atr_take_profit_multiplier=self.atr_tp_mult,
                signal=signal,
                db_manager=self.db,
                as_of_date=effective_date,
            )
            quantity = float(plan["recommended_quantity"])
            if plan["stop_source"] in ("atr", "signal"):
                stop_loss = plan["stop_loss"]
            if plan["take_profit_source"] in ("atr", "signal"):
                take_profit = plan["take_profit"]
            # If stop came from signal/ATR, also pair it with the plan's take-profit (and vice versa)
            if stop_loss is not None and take_profit is None:
                take_profit = plan["take_profit"]
            elif take_profit is not None and stop_loss is None:
                stop_loss = plan["stop_loss"]
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

        total_cost_bps = self.commission_bps + self.slippage_bps
        if total_cost_bps > 0:
            adj = 1.0 + (total_cost_bps / 10000.0) if side == "buy" else max(0.0, 1.0 - (total_cost_bps / 10000.0))
            fill_price = round(fill_price * adj, 6)

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
            stop_loss=stop_loss,
            take_profit=take_profit,
            trade_date=effective_date,
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
            "[paper] %s %s x%s @ %s (signal %s, stop=%s, tp=%s)",
            side, stock_code, quantity, fill_price, signal_id, stop_loss, take_profit,
        )
        return payload

    def _vol_scaled_position_size(self, stock_code: str, as_of_date: date) -> float:
        """Apply Barroso-Santa-Clara volatility scaling when ``vol_target_pct`` is set."""
        if not self.vol_target_pct:
            return self.position_size
        try:
            with self.db.session_scope() as session:
                stmt = (
                    select(StockDaily.close)
                    .where(StockDaily.code == stock_code)
                    .where(StockDaily.date <= as_of_date)
                    .order_by(desc(StockDaily.date))
                    .limit(130)
                )
                closes = [float(r[0]) for r in session.execute(stmt).all() if r[0] and float(r[0]) > 0]
            if len(closes) < 21:
                return self.position_size
            closes.reverse()
            rets = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))]
            mean_r = sum(rets) / len(rets)
            var_r = sum((r - mean_r) ** 2 for r in rets) / max(1, len(rets) - 1)
            realized_vol_pct = math.sqrt(var_r) * math.sqrt(252.0) * 100.0
            if realized_vol_pct <= 1e-6:
                return self.position_size
            scale = max(0.25, min(2.0, self.vol_target_pct / realized_vol_pct))
            return round(self.position_size * scale, 2)
        except Exception as exc:
            logger.debug("[paper] vol scaling fallback for %s: %s", stock_code, exc)
            return self.position_size

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

        Automatically settles any open positions whose ``StockDaily`` bars have
        crossed their active ``stop_loss`` or ``take_profit`` level.
        ``include_benchmarks`` adds per-market index-shadow and USD-based returns
        (``benchmarks``; Borsa Istanbul vs BIST 100 / USD-TRY), fetched fail-open.
        """
        self.check_stops_and_targets()

        with self.db.session_scope() as session:
            trades = session.execute(
                select(PaperTradeRecord).order_by(PaperTradeRecord.trade_date, PaperTradeRecord.id)
            ).scalars().all()
            trade_dicts = [_trade_to_dict(row) for row in trades]

        books: Dict[str, Dict[str, Any]] = {}
        closed_results: List[float] = []
        stop_loss_count = 0
        take_profit_count = 0
        for trade in trade_dicts:
            if trade.get("action") == "stop_loss":
                stop_loss_count += 1
            elif trade.get("action") == "take_profit":
                take_profit_count += 1
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
                    "stop_loss": None,
                    "take_profit": None,
                },
            )
            book["trade_count"] += 1
            if trade["side"] == "buy":
                if book["quantity"] <= _EPS:
                    book["stop_loss"] = _positive_float(trade.get("stop_loss"))
                    book["take_profit"] = _positive_float(trade.get("take_profit"))
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
            if book["quantity"] <= _EPS:
                book["stop_loss"] = None
                book["take_profit"] = None
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

            risk_plan = compute_atr_risk_plan(
                book["stock_code"],
                price=avg_cost,
                position_size=self.position_size,
                risk_pct=self.risk_pct,
                atr_stop_multiplier=self.atr_stop_mult,
                atr_take_profit_multiplier=self.atr_tp_mult,
                db_manager=self.db,
                as_of_date=last_date,
            )
            effective_stop = book["stop_loss"] if book["stop_loss"] is not None else risk_plan["stop_loss"]
            effective_tp = book["take_profit"] if book["take_profit"] is not None else risk_plan["take_profit"]
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
                "stop_loss": effective_stop,
                "take_profit": effective_tp,
                "stops_enforced": book["stop_loss"] is not None or book["take_profit"] is not None,
                "atr14": risk_plan["atr14"],
                "atr_pct": risk_plan["atr_pct"],
                "recommended_quantity": risk_plan["recommended_quantity"],
                "max_loss_amount": round(book["quantity"] * max(0.0, avg_cost - effective_stop), 2)
                if effective_stop is not None
                else None,
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
            "risk_pct": self.risk_pct,
            "trade_count": len(trade_dicts),
            "open_position_count": len(positions),
            "closed_trade_count": len(closed_results),
            "stop_loss_count": stop_loss_count,
            "take_profit_count": take_profit_count,
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


def _parse_iso_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


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
        "stop_loss": row.stop_loss,
        "take_profit": row.take_profit,
        "trade_date": row.trade_date.isoformat() if row.trade_date else None,
    }


def apply_paper_trade_for_signal(signal_result: Any, *, price: Any) -> Optional[Dict[str, Any]]:
    """Best-effort pipeline hook: check stops/targets and fill newly created analysis signals.

    ``signal_result`` is the ``{"item": ..., "created": ...}`` payload returned by
    ``DecisionSignalService.create_signal``. Duplicates/refreshes do not open new
    signal trades, but open positions are still checked against their stop-loss and
    take-profit levels. Fail-open: errors are logged and never reach the analysis flow.
    """
    try:
        if not isinstance(signal_result, dict):
            return None
        service = PaperTradingService()
        if not service.enabled:
            return None
        item = signal_result.get("item") if isinstance(signal_result.get("item"), dict) else {}
        stock_code = str(item.get("stock_code") or "").strip().upper() or None
        service.check_stops_and_targets(stock_code=stock_code, current_price=price)
        if not signal_result.get("created"):
            return None
        return service.apply_signal(item, price=price)
    except Exception as exc:  # noqa: BLE001 - optional sidecar, fail-open
        logger.warning("[paper] apply failed: %s", exc)
        return None
