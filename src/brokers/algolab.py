# -*- coding: utf-8 -*-
"""Deniz Yatırım AlgoLab BIST broker adapter (read-only by default)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from src.brokers.base import BrokerAdapter, BrokerSecurityError


class AlgoLabBrokerAdapter(BrokerAdapter):
    """BIST AlgoLab REST skeleton strictly locked to ``read_only=True`` by default."""

    broker_id = "algolab"
    display_name = "Deniz Yatırım AlgoLab (BIST)"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        read_only: bool = True,
        audit_path: Optional[Path] = None,
    ) -> None:
        self.api_key = (api_key or "").strip() or None
        self.username = (username or "").strip() or None
        self._read_only = bool(read_only)
        self.audit_path = audit_path

    @classmethod
    def from_config(cls, config: Any = None, *, audit_path: Optional[Path] = None) -> "AlgoLabBrokerAdapter":
        if config is None:
            from src.config import get_config

            config = get_config()
        return cls(
            api_key=getattr(config, "algolab_api_key", None),
            username=getattr(config, "algolab_username", None),
            read_only=bool(getattr(config, "algolab_read_only", True)),
            audit_path=audit_path,
        )

    @property
    def is_sandbox(self) -> bool:
        return True

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.username)

    @property
    def read_only_enforced(self) -> bool:
        return self._read_only

    def health_check(self) -> Dict[str, Any]:
        return {
            "broker_id": self.broker_id,
            "display_name": self.display_name,
            "configured": self.is_configured,
            "sandbox": True,
            "read_only_enforced": self.read_only_enforced,
            "mode_label": "Salt-Okunur (BIST)",
            "note": "AlgoLab yalnızca portföy görüntüleme ve Midas/BIST manuel emir planı içindir (otomatik emir kapalı).",
        }

    def get_account_summary(self) -> Dict[str, Any]:
        self._audit("account_summary", "ok", {"configured": self.is_configured})
        return {
            "broker_id": self.broker_id,
            "configured": self.is_configured,
            "currency": "TRY",
            "equity": 0.0,
            "cash": 0.0,
            "read_only": self.read_only_enforced,
            "message": (
                "AlgoLab oturum doğrulaması için SMS 2FA token gerekir; yalnızca planlama / salt-okunur mod aktiftir."
                if self.is_configured
                else "ALGOLAB_API_KEY ve ALGOLAB_USERNAME tanımlı değil."
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
        total_cap = float(capital if capital and capital > 0 else 100000.0)
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
                    "currency": "TRY",
                    "execution": "manual_preview_only",
                }
            )
        plan = {
            "broker_id": self.broker_id,
            "sandbox": True,
            "read_only_enforced": True,
            "currency": "TRY",
            "capital": total_cap,
            "orders": orders,
        }
        self._audit("preview_rebalance", "ok", {"order_count": len(orders), "capital": total_cap})
        return plan

    def submit_paper_order(self, order: Dict[str, Any], *, confirmed: bool = False) -> Dict[str, Any]:
        self._audit("submit_paper_order", "blocked_read_only", {"symbol": order.get("symbol")})
        raise BrokerSecurityError(
            "AlgoLab bridge is strictly read-only (ALGOLAB_READ_ONLY=true); automated order submission is blocked."
        )

    def reconcile_fills(self, symbol: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        return {"broker_id": self.broker_id, "fills": [], "avg_slippage_bps": None}
