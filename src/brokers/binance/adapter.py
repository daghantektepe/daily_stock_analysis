# -*- coding: utf-8 -*-
"""Unified BrokerAdapter wrapper around BinanceClient (Testnet + audit logged)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.brokers.base import BrokerAdapter, BrokerSecurityError
from src.brokers.binance.client import BinanceClient

logger = logging.getLogger(__name__)


class BinanceBrokerAdapter(BrokerAdapter):
    """Adapter exposing Binance Spot/Testnet under unified BrokerAdapter contract."""

    broker_id = "binance"
    display_name = "Binance Spot / Testnet (Kripto)"

    def __init__(
        self,
        client: Optional[BinanceClient] = None,
        *,
        audit_path: Optional[Path] = None,
    ) -> None:
        self.client = client or BinanceClient()
        self.audit_path = audit_path

    @classmethod
    def from_config(cls, config: Any = None, *, audit_path: Optional[Path] = None) -> "BinanceBrokerAdapter":
        return cls(client=BinanceClient.from_config(config), audit_path=audit_path)

    @property
    def is_sandbox(self) -> bool:
        return bool(self.client.testnet)

    @property
    def is_configured(self) -> bool:
        return bool(self.client.is_configured)

    @property
    def read_only_enforced(self) -> bool:
        return (not self.client.testnet) and (not self.client.live_trading_confirmed)

    def health_check(self) -> Dict[str, Any]:
        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "configured": self.is_configured,
            "sandbox": self.is_sandbox,
            "auto_execute": self.client.auto_execute,
            "read_only_enforced": self.read_only_enforced,
            "mode_label": "Testnet Sanal" if self.is_sandbox else ("Canlı Kilitli" if self.read_only_enforced else "Canlı"),
            "note": "Kripto 5-SMA stratejisi için testnet.binance.vision sanal emir ve canlı makas ölçümü.",
        }

    def get_account_summary(self) -> Dict[str, Any]:
        if not self.is_configured:
            return {
                "broker_id": self.broker_id,
                "configured": False,
                "currency": "USDT",
                "equity": 0.0,
                "cash": 0.0,
            }
        acct = self.client.get_account_summary()
        usdt = float((acct.get("balances") or {}).get("USDT", {}).get("total", 0.0))
        self._audit("account_summary", "ok", {"usdt": usdt})
        return {"broker_id": self.broker_id, "configured": True, "currency": "USDT", "cash": usdt, **acct}

    def list_positions(self) -> List[Dict[str, Any]]:
        if not self.is_configured:
            return []
        acct = self.client.get_account_summary()
        return [
            {"symbol": asset, "qty": info["total"], "free": info["free"], "locked": info["locked"]}
            for asset, info in (acct.get("balances") or {}).items()
            if asset != "USDT" and float(info.get("total") or 0) > 0
        ]

    def preview_rebalance_plan(
        self,
        target_weights: Dict[str, float],
        *,
        capital: Optional[float] = None,
    ) -> Dict[str, Any]:
        # Accept weight values either in % (0..100) or fractions (0..1)
        clean_weights: Dict[str, float] = {}
        raw_sum = sum(float(v) for v in (target_weights or {}).values() if v and float(v) > 0)
        scale = 100.0 if raw_sum > 1.5 else 1.0
        for sym, val in (target_weights or {}).items():
            if str(sym).upper() == "CASH":
                continue
            w = float(val) / scale
            if w > 0:
                clean_weights[sym] = w

        fallback_reason: Optional[str] = None
        if self.is_configured:
            try:
                plan = self.client.plan_crypto_trend_rebalance(clean_weights)
                self._audit("preview_rebalance", "ok", {"order_count": len(plan.get("orders", []))})
                return {"broker_id": self.broker_id, "sandbox": self.is_sandbox, "currency": "USDT", **plan}
            except Exception as exc:
                fallback_reason = str(exc)
                logger.warning(
                    "[binance-adapter] rebalance plan fetch failed; falling back to offline estimate: %s",
                    exc,
                )
                self._audit(
                    "preview_rebalance",
                    "error",
                    {"error": fallback_reason, "fallback": "offline_estimate"},
                )

        total_cap = float(capital if capital and capital > 0 else 10000.0)
        orders: List[Dict[str, Any]] = []
        for sym, frac in sorted(clean_weights.items()):
            norm = self.client.normalize_symbol(sym)
            orders.append(
                {
                    "symbol": norm,
                    "side": "BUY",
                    "target_weight_pct": round(frac * 100.0, 2),
                    "notional_usdt": round(total_cap * frac, 2),
                    "currency": "USDT",
                }
            )
        self._audit(
            "preview_rebalance",
            "ok",
            {"order_count": len(orders), "offline_estimate": True, "fallback_reason": fallback_reason},
        )
        out: Dict[str, Any] = {
            "broker_id": self.broker_id,
            "sandbox": self.is_sandbox,
            "configured": self.is_configured,
            "currency": "USDT",
            "capital": total_cap,
            "orders": orders,
        }
        if fallback_reason is not None:
            out["fallback_reason"] = fallback_reason
        return out

    def submit_paper_order(self, order: Dict[str, Any], *, confirmed: bool = False) -> Dict[str, Any]:
        if not self.client.testnet:
            self._audit("submit_paper_order", "blocked_mainnet", {"symbol": order.get("symbol")})
            raise BrokerSecurityError(
                "Unified submit_paper_order refuses Binance Mainnet when BINANCE_TESTNET=false."
            )
        if not confirmed:
            self._audit("submit_paper_order", "blocked_unconfirmed", {"symbol": order.get("symbol")})
            raise BrokerSecurityError("Explicit confirmed=True is required before submitting a Binance Testnet order.")
        if not self.is_configured:
            raise BrokerSecurityError("BINANCE_API_KEY and BINANCE_API_SECRET are required for Testnet orders.")

        res = self.client.place_market_order(
            symbol=str(order["symbol"]),
            side=str(order.get("side") or "BUY"),
            quote_order_qty=order.get("quote_order_qty") or order.get("notional_usdt"),
            quantity=order.get("quantity") or order.get("qty"),
            test_only=bool(order.get("test_only", True)),
            confirmed=True,
        )
        self._audit("submit_paper_order", res["status"], {"symbol": res["symbol"], "side": res["side"]})
        return {"broker_id": self.broker_id, "sandbox": True, **res}

    def reconcile_fills(self, symbol: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        if not self.is_configured or not symbol:
            return {"broker_id": self.broker_id, "fills": [], "avg_slippage_bps": None}
        trades = self.client.get_my_trades(symbol, limit=limit)
        return {"broker_id": self.broker_id, "fills": trades, "avg_slippage_bps": None}
