# -*- coding: utf-8 -*-
"""Unified BrokerAdapter wrapper around AlpacaClient (Paper-first + audit logged)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from src.brokers.alpaca.client import AlpacaBrokerError, AlpacaClient
from src.brokers.base import BrokerAdapter, BrokerSecurityError


class AlpacaBrokerAdapter(BrokerAdapter):
    """Adapter exposing Alpaca Markets Paper/Live REST under unified BrokerAdapter contract."""

    broker_id = "alpaca"
    display_name = "Alpaca ABD Hisse & ETF (Paper)"

    def __init__(
        self,
        client: Optional[AlpacaClient] = None,
        *,
        auto_execute: bool = False,
        audit_path: Optional[Path] = None,
    ) -> None:
        self.client = client or AlpacaClient()
        self.auto_execute = bool(auto_execute)
        self.audit_path = audit_path

    @classmethod
    def from_config(cls, config: Any = None, *, audit_path: Optional[Path] = None) -> "AlpacaBrokerAdapter":
        if config is None:
            from src.config import get_config

            config = get_config()
        client = AlpacaClient(
            api_key=getattr(config, "alpaca_api_key", None),
            secret_key=getattr(config, "alpaca_secret_key", None),
            paper=bool(getattr(config, "alpaca_paper", True)),
            live_trading_confirmed=bool(getattr(config, "alpaca_live_trading_confirmed", False)),
        )
        return cls(
            client=client,
            auto_execute=bool(getattr(config, "alpaca_auto_execute", False)),
            audit_path=audit_path,
        )

    @property
    def is_sandbox(self) -> bool:
        return bool(self.client.paper)

    @property
    def is_configured(self) -> bool:
        return bool(self.client.is_configured())

    @property
    def read_only_enforced(self) -> bool:
        return (not self.client.paper) and (not self.client.live_trading_confirmed)

    def health_check(self) -> Dict[str, Any]:
        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "configured": self.is_configured,
            "sandbox": self.is_sandbox,
            "auto_execute": self.auto_execute,
            "read_only_enforced": self.read_only_enforced,
            "mode_label": "Paper Sanal" if self.is_sandbox else ("Canlı Kilitli" if self.read_only_enforced else "Canlı"),
            "note": "ABD ETF (BIL, SHY, SPY, UUP) sanal emir önizleme ve kayma doğrulama.",
        }

    def get_account_summary(self) -> Dict[str, Any]:
        if not self.is_configured:
            return {
                "broker_id": self.broker_id,
                "configured": False,
                "currency": "USD",
                "equity": 0.0,
                "cash": 0.0,
            }
        acct = self.client.get_account()
        self._audit("account_summary", "ok", {"equity": acct.get("equity")})
        return {"broker_id": self.broker_id, "configured": True, "currency": "USD", **acct}

    def list_positions(self) -> List[Dict[str, Any]]:
        if not self.is_configured:
            return []
        return self.client.list_positions()

    def preview_rebalance_plan(
        self,
        target_weights: Dict[str, float],
        *,
        capital: Optional[float] = None,
    ) -> Dict[str, Any]:
        equity = float(capital) if capital and capital > 0 else 10000.0
        current_values: Dict[str, float] = {}
        if self.is_configured:
            try:
                acct = self.get_account_summary()
                if not capital:
                    equity = float(acct.get("equity") or equity)
                for pos in self.list_positions():
                    current_values[str(pos.get("symbol", "")).upper()] = float(pos.get("market_value") or 0.0)
            except Exception:
                pass

        orders: List[Dict[str, Any]] = []
        all_syms = sorted(set(k.upper() for k in target_weights) | set(current_values.keys()))
        for sym in all_syms:
            if sym == "CASH":
                continue
            w = float(target_weights.get(sym, target_weights.get(sym.lower(), 0.0)) or 0.0)
            target_notional = equity * (w / 100.0)
            current_notional = current_values.get(sym, 0.0)
            delta = target_notional - current_notional
            if abs(delta) < 10.0:
                continue
            orders.append(
                {
                    "symbol": sym,
                    "side": "BUY" if delta > 0 else "SELL",
                    "target_weight_pct": round(w, 2),
                    "target_notional": round(target_notional, 2),
                    "delta_notional": round(delta, 2),
                    "currency": "USD",
                }
            )
        plan = {
            "broker_id": self.broker_id,
            "sandbox": self.is_sandbox,
            "configured": self.is_configured,
            "currency": "USD",
            "capital": round(equity, 2),
            "orders": orders,
        }
        self._audit("preview_rebalance", "ok", {"order_count": len(orders), "capital": equity})
        return plan

    def submit_paper_order(self, order: Dict[str, Any], *, confirmed: bool = False) -> Dict[str, Any]:
        if not self.client.paper:
            self._audit("submit_paper_order", "blocked_non_paper", {"symbol": order.get("symbol")})
            raise BrokerSecurityError(
                "Unified submit_paper_order refuses non-paper Alpaca endpoints (ALPACA_PAPER=true required)."
            )
        if not confirmed:
            self._audit("submit_paper_order", "blocked_unconfirmed", {"symbol": order.get("symbol")})
            raise BrokerSecurityError("Explicit confirmed=True is required before submitting an Alpaca paper order.")
        if not self.is_configured:
            raise BrokerSecurityError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required for Alpaca Paper orders.")

        symbol = str(order.get("symbol") or "").upper().strip()
        side = str(order.get("side") or "buy").lower()
        qty = float(order.get("qty") or order.get("quantity") or 0.0)
        if not symbol or qty <= 0:
            raise ValueError("Order requires positive 'qty' and valid 'symbol'.")

        try:
            submitted = self.client.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                order_type=str(order.get("order_type") or "market"),
                time_in_force=str(order.get("time_in_force") or "day"),
            )
            self._audit("submit_paper_order", "submitted", {"symbol": symbol, "side": side, "qty": qty})
            return {"broker_id": self.broker_id, "sandbox": True, "order": submitted}
        except AlpacaBrokerError as exc:
            self._audit("submit_paper_order", "error", {"error": str(exc)})
            raise

    def reconcile_fills(self, symbol: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        if not self.is_configured:
            return {"broker_id": self.broker_id, "fills": [], "avg_slippage_bps": None}
        orders = self.client.list_orders(status="closed", limit=limit)
        if symbol:
            target = symbol.upper()
            orders = [o for o in orders if str(o.get("symbol", "")).upper() == target]
        return {"broker_id": self.broker_id, "fills": orders, "avg_slippage_bps": None}
