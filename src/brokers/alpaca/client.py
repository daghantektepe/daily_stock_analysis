# -*- coding: utf-8 -*-
"""Lightweight Alpaca Trading API v2 client supporting Paper and Live endpoints."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

import requests

from src.config import get_config

logger = logging.getLogger(__name__)

ALPACA_PAPER_BASE_URL = "https://paper-api.alpaca.markets"
ALPACA_LIVE_BASE_URL = "https://api.alpaca.markets"
ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"


class AlpacaBrokerError(RuntimeError):
    """Raised when an Alpaca API request fails or returns an error status."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AlpacaClient:
    """Alpaca US stock execution & market data adapter (paper endpoint by default)."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: Optional[bool] = None,
        session: Optional[requests.Session] = None,
        timeout: float = 10.0,
    ) -> None:
        if api_key is None or secret_key is None or paper is None:
            cfg = get_config()
            if api_key is None:
                api_key = getattr(cfg, "alpaca_api_key", None)
            if secret_key is None:
                secret_key = getattr(cfg, "alpaca_secret_key", None)
            if paper is None:
                paper = bool(getattr(cfg, "alpaca_paper", True))

        self.api_key = (api_key or "").strip()
        self.secret_key = (secret_key or "").strip()
        self.paper = bool(True if paper is None else paper)
        self.base_url = ALPACA_PAPER_BASE_URL if self.paper else ALPACA_LIVE_BASE_URL
        self.data_url = ALPACA_DATA_BASE_URL
        self.timeout = float(timeout)
        self.session = session or requests.Session()

    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

    @staticmethod
    def is_us_equity_symbol(symbol: str) -> bool:
        clean = str(symbol or "").strip().upper()
        return bool(clean) and "." not in clean and not clean.isdigit()

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        data_api: bool = False,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if not self.is_configured():
            raise AlpacaBrokerError("Alpaca API credentials are not configured (ALPACA_API_KEY / ALPACA_SECRET_KEY).")
        root = self.data_url if data_api else self.base_url
        url = f"{root}{path}"
        resp = self.session.request(
            method=method.upper(),
            url=url,
            headers=self._headers(),
            params=params,
            json=json_body,
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            detail = ""
            try:
                body = resp.json()
                detail = body.get("message") or str(body)
            except Exception:
                detail = resp.text[:300]
            raise AlpacaBrokerError(
                f"Alpaca {method.upper()} {path} failed ({resp.status_code}): {detail}",
                status_code=resp.status_code,
            )
        if not resp.text.strip():
            return {}
        return resp.json()

    # ------------------------------------------------------------------ read
    def get_account(self) -> Dict[str, Any]:
        raw = self._request("GET", "/v2/account")
        return {
            "id": raw.get("id"),
            "status": raw.get("status"),
            "currency": raw.get("currency", "USD"),
            "cash": _f(raw.get("cash")),
            "buying_power": _f(raw.get("buying_power")),
            "equity": _f(raw.get("equity")),
            "portfolio_value": _f(raw.get("portfolio_value")),
            "pattern_day_trader": bool(raw.get("pattern_day_trader", False)),
            "trading_blocked": bool(raw.get("trading_blocked", False)),
            "paper": self.paper,
        }

    def get_market_clock(self) -> Dict[str, Any]:
        raw = self._request("GET", "/v2/clock")
        return {
            "is_open": bool(raw.get("is_open", False)),
            "timestamp": raw.get("timestamp"),
            "next_open": raw.get("next_open"),
            "next_close": raw.get("next_close"),
        }

    def list_positions(self) -> List[Dict[str, Any]]:
        rows = self._request("GET", "/v2/positions") or []
        return [
            {
                "symbol": str(item.get("symbol", "")).upper(),
                "qty": _f(item.get("qty")),
                "side": item.get("side", "long"),
                "avg_entry_price": _f(item.get("avg_entry_price")),
                "current_price": _f(item.get("current_price")),
                "market_value": _f(item.get("market_value")),
                "unrealized_pl": _f(item.get("unrealized_pl")),
                "unrealized_plpc": round(_f(item.get("unrealized_plpc")) * 100.0, 2)
                if item.get("unrealized_plpc") is not None
                else None,
            }
            for item in rows
        ]

    def list_orders(self, *, status: str = "open", limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._request("GET", "/v2/orders", params={"status": status, "limit": int(limit)}) or []
        return [
            {
                "id": item.get("id"),
                "client_order_id": item.get("client_order_id"),
                "symbol": str(item.get("symbol", "")).upper(),
                "side": item.get("side"),
                "type": item.get("type"),
                "order_class": item.get("order_class"),
                "qty": _f(item.get("qty")),
                "filled_qty": _f(item.get("filled_qty")),
                "filled_avg_price": _f(item.get("filled_avg_price")) if item.get("filled_avg_price") else None,
                "limit_price": _f(item.get("limit_price")) if item.get("limit_price") else None,
                "stop_price": _f(item.get("stop_price")) if item.get("stop_price") else None,
                "status": item.get("status"),
                "submitted_at": item.get("submitted_at"),
            }
            for item in rows
        ]

    def get_latest_trades(self, symbols: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        clean = [str(s or "").strip().upper() for s in symbols if self.is_us_equity_symbol(s)]
        if not clean:
            return {}
        payload = self._request("GET", "/v2/stocks/trades/latest", data_api=True, params={"symbols": ",".join(clean)})
        return payload.get("trades") or {}

    # ------------------------------------------------------------------ write
    def submit_order(
        self,
        *,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
        limit_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit a US equity order (supports bracket stop_loss + take_profit for buy entries)."""
        sym = str(symbol or "").strip().upper()
        if not self.is_us_equity_symbol(sym):
            raise AlpacaBrokerError(f"Unsupported non-US symbol for Alpaca: {symbol}")
        side_norm = str(side or "").strip().lower()
        if side_norm not in {"buy", "sell"}:
            raise AlpacaBrokerError(f"Unsupported order side: {side}")
        qty_val = float(qty)
        if qty_val <= 0:
            raise AlpacaBrokerError("Order quantity must be positive.")

        body: Dict[str, Any] = {
            "symbol": sym,
            "qty": str(int(qty_val)) if qty_val.is_integer() else f"{qty_val:.4f}",
            "side": side_norm,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if limit_price is not None and order_type == "limit":
            body["limit_price"] = f"{float(limit_price):.2f}"
        if client_order_id:
            body["client_order_id"] = str(client_order_id)[:48]

        if side_norm == "buy" and stop_loss is not None and take_profit is not None:
            body["order_class"] = "bracket"
            body["time_in_force"] = "gtc"
            body["take_profit"] = {"limit_price": f"{float(take_profit):.2f}"}
            body["stop_loss"] = {"stop_price": f"{float(stop_loss):.2f}"}
        elif side_norm == "buy" and stop_loss is not None:
            body["order_class"] = "oto"
            body["time_in_force"] = "gtc"
            body["stop_loss"] = {"stop_price": f"{float(stop_loss):.2f}"}

        raw = self._request("POST", "/v2/orders", json_body=body)
        logger.info(
            "[alpaca] submitted %s %s x%s (%s, paper=%s, id=%s)",
            side_norm,
            sym,
            body["qty"],
            body.get("order_class", "simple"),
            self.paper,
            raw.get("id"),
        )
        return raw

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        self._request("DELETE", f"/v2/orders/{order_id}")
        return {"canceled": True, "order_id": order_id}

    def close_position(self, symbol: str) -> Dict[str, Any]:
        sym = str(symbol or "").strip().upper()
        return self._request("DELETE", f"/v2/positions/{sym}")


def _f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
