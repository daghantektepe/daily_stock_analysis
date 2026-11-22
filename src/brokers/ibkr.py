# -*- coding: utf-8 -*-
"""Interactive Brokers (IBKR TWS / Gateway Paper Port 7497) optional adapter."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.brokers.base import BrokerAdapter, BrokerSecurityError


def ibkr_driver_available() -> bool:
    return (
        importlib.util.find_spec("ib_async") is not None
        or importlib.util.find_spec("ib_insync") is not None
    )


class IbkrBrokerAdapter(BrokerAdapter):
    """Optional IBKR adapter pinned to Paper Gateway port 7497 and read-only default."""

    broker_id = "ibkr"
    display_name = "Interactive Brokers (IBKR Paper)"

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 17,
        read_only: bool = True,
        audit_path: Optional[Path] = None,
    ) -> None:
        self.host = (host or "127.0.0.1").strip()
        self.port = int(port or 7497)
        self.client_id = int(client_id or 17)
        self._read_only = bool(read_only)
        self.audit_path = audit_path

    @classmethod
    def from_config(cls, config: Any = None, *, audit_path: Optional[Path] = None) -> "IbkrBrokerAdapter":
        if config is None:
            from src.config import get_config

            config = get_config()
        return cls(
            host=str(getattr(config, "ibkr_host", "127.0.0.1")),
            port=int(getattr(config, "ibkr_port", 7497)),
            client_id=int(getattr(config, "ibkr_client_id", 17)),
            read_only=bool(getattr(config, "ibkr_read_only", True)),
            audit_path=audit_path,
        )

    @property
    def is_sandbox(self) -> bool:
        return self.port in {7497, 4002}

    @property
    def is_configured(self) -> bool:
        return ibkr_driver_available() and bool(self.host)

    @property
    def read_only_enforced(self) -> bool:
        return self._read_only or not self.is_sandbox

    def health_check(self) -> Dict[str, Any]:
        driver_ok = ibkr_driver_available()
        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "configured": driver_ok,
            "driver_installed": driver_ok,
            "sandbox": self.is_sandbox,
            "port": self.port,
            "read_only_enforced": self.read_only_enforced,
            "mode_label": "Paper 7497 (Kilitli)" if self.is_sandbox else "Canlı Port ENGELİ",
            "note": (
                f"IBKR TWS/Gateway {self.host}:{self.port} hedefleniyor (varsayılan salt-okunur)."
                if driver_ok
                else "Opsiyonel `ib_async` kurulu değil; yalnızca güvenli önizleme modunda."
            ),
        }

    def get_account_summary(self) -> Dict[str, Any]:
        self._audit("account_summary", "ok", {"driver_installed": ibkr_driver_available(), "port": self.port})
        return {
            "broker_id": self.broker_id,
            "configured": self.is_configured,
            "driver_installed": ibkr_driver_available(),
            "currency": "USD",
            "equity": 0.0,
            "cash": 0.0,
            "port": self.port,
            "read_only": self.read_only_enforced,
            "message": (
                "IBKR Gateway aktif dinleme yalnızca açık kullanıcı oturumunda yapılır."
                if ibkr_driver_available()
                else "Opsiyonel `ib_async` paketi yüklü değil (pip install ib_async)."
            ),
        }

    def list_positions(self) -> List[Dict[str, Any]]:
        return []

    def preview_rebalance_plan(
        self,
        target_weights: Dict[str, float],
        *,
        capital: Optional[float] = None,
    ) -> Dict[str, Any]:
        total_cap = float(capital if capital and capital > 0 else 10000.0)
        orders: List[Dict[str, Any]] = []
        for sym, w_pct in sorted((target_weights or {}).items()):
            w = float(w_pct)
            if w <= 0:
                continue
            orders.append(
                {
                    "symbol": str(sym).upper(),
                    "side": "BUY",
                    "target_weight_pct": round(w, 2),
                    "target_notional": round(total_cap * (w / 100.0), 2),
                    "currency": "USD",
                    "execution": "manual_preview_only",
                }
            )
        plan = {
            "broker_id": self.broker_id,
            "sandbox": self.is_sandbox,
            "read_only_enforced": self.read_only_enforced,
            "currency": "USD",
            "capital": total_cap,
            "orders": orders,
        }
        self._audit("preview_rebalance", "ok", {"order_count": len(orders), "capital": total_cap})
        return plan

    def submit_paper_order(self, order: Dict[str, Any], *, confirmed: bool = False) -> Dict[str, Any]:
        self._audit("submit_paper_order", "blocked_read_only", {"port": self.port, "symbol": order.get("symbol")})
        if not self.is_sandbox:
            raise BrokerSecurityError("IBKR live ports (7496/4001) are strictly blocked.")
        if self.read_only_enforced:
            raise BrokerSecurityError(
                "IBKR adapter defaults to IBKR_READ_ONLY=true; automated TWS order submission is disabled."
            )
        raise BrokerSecurityError("Direct synchronous TWS socket execution is disabled without an active Gateway session.")

    def reconcile_fills(self, symbol: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        return {"broker_id": self.broker_id, "fills": [], "avg_slippage_bps": None}
