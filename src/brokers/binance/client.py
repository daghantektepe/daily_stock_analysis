# -*- coding: utf-8 -*-
"""Lightweight Binance Spot / Testnet REST client (pure ``requests`` + HMAC-SHA256).

Safety locks:
- ``testnet=True`` by default -> ``https://testnet.binance.vision``
- Writing (``POST`` / ``DELETE``) to mainnet (``https://api.binance.com``) is blocked
  unless ``live_trading_confirmed=True`` is explicitly set alongside ``testnet=False``.
- Uses standard ``requests`` so both the ``.venv`` and the PyInstaller desktop
  bundle work without optional third-party SDK bloat, while still detecting if
  ``ccxt`` is installed for diagnostics.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import time
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlencode

import requests

BINANCE_SPOT_MAINNET_URL = "https://api.binance.com"
BINANCE_SPOT_TESTNET_URL = "https://testnet.binance.vision"


class BinanceBrokerError(RuntimeError):
    """Raised on Binance Spot API or safety-lock failures."""


def _f(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def ccxt_available() -> bool:
    """Return True if optional ``ccxt`` package is importable."""
    return importlib.util.find_spec("ccxt") is not None


class BinanceClient:
    """Minimal, auditable Binance Spot REST v3 client (Mainnet public data + Testnet orders)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        *,
        testnet: bool = True,
        auto_execute: bool = False,
        live_trading_confirmed: bool = False,
        timeout: float = 12.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = (api_key or "").strip() or None
        self.api_secret = (api_secret or "").strip() or None
        self.testnet = bool(testnet)
        self.auto_execute = bool(auto_execute)
        self.live_trading_confirmed = bool(live_trading_confirmed)
        self.timeout = float(timeout)
        self.base_url = BINANCE_SPOT_TESTNET_URL if self.testnet else BINANCE_SPOT_MAINNET_URL
        self.session = session or requests.Session()

    @classmethod
    def from_config(cls, config: Any = None) -> "BinanceClient":
        """Build a client using global Config settings."""
        if config is None:
            from src.config import get_config

            config = get_config()
        return cls(
            api_key=getattr(config, "binance_api_key", None),
            api_secret=getattr(config, "binance_api_secret", None),
            testnet=bool(getattr(config, "binance_testnet", True)),
            auto_execute=bool(getattr(config, "binance_auto_execute", False)),
            live_trading_confirmed=bool(getattr(config, "binance_live_trading_confirmed", False)),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    @staticmethod
    def normalize_symbol(asset: str) -> str:
        """Map ``BTC-USD``, ``BTC/USDT``, ``ETH-USDT``, or ``BTC`` -> Binance ``BTCUSDT``."""
        raw = str(asset or "").strip().upper()
        if not raw:
            raise BinanceBrokerError("Empty Binance symbol.")
        cleaned = raw.replace("/", "").replace("-", "")
        if cleaned.endswith("USD") and not cleaned.endswith("USDT") and not cleaned.endswith("BUSD"):
            return f"{cleaned[:-3]}USDT"
        if len(cleaned) <= 5 and not (cleaned.endswith("USDT") or cleaned.endswith("BTC") or cleaned.endswith("TRY")):
            return f"{cleaned}USDT"
        return cleaned

    def _sign_params(self, params: Dict[str, Any]) -> str:
        if not self.api_secret:
            raise BinanceBrokerError("BINANCE_API_SECRET is required for signed endpoints.")
        payload = dict(params)
        payload.setdefault("recvWindow", 5000)
        payload["timestamp"] = int(time.time() * 1000)
        query = urlencode(payload)
        sig = hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{query}&signature={sig}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
        market_data_mainnet: bool = False,
    ) -> Any:
        upper_method = method.upper()
        if upper_method != "GET" and not self.testnet and not self.live_trading_confirmed:
            raise BinanceBrokerError(
                "Real-money Binance Spot writes are disabled: keep BINANCE_TESTNET=true "
                "or explicitly set BINANCE_LIVE_TRADING_CONFIRMED=true."
            )

        base = BINANCE_SPOT_MAINNET_URL if market_data_mainnet else self.base_url
        url = f"{base}{path}"
        headers: Dict[str, str] = {"Accept": "application/json"}
        req_params = dict(params or {})

        if signed:
            if not self.is_configured:
                raise BinanceBrokerError(
                    "BINANCE_API_KEY and BINANCE_API_SECRET must be set to use signed Binance endpoints."
                )
            headers["X-MBX-APIKEY"] = str(self.api_key)
            signed_qs = self._sign_params(req_params)
            full_url = f"{url}?{signed_qs}"
            req_kwargs: Dict[str, Any] = {"headers": headers, "timeout": self.timeout}
        else:
            full_url = url
            req_kwargs = {"headers": headers, "params": req_params or None, "timeout": self.timeout}

        try:
            resp = self.session.request(upper_method, full_url, **req_kwargs)
        except requests.RequestException as exc:
            raise BinanceBrokerError(f"Binance network error ({upper_method} {path}): {exc}") from exc

        if resp.status_code >= 400:
            raise BinanceBrokerError(f"Binance {upper_method} {path} -> HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise BinanceBrokerError(f"Binance returned non-JSON response for {path}") from exc

    # --- Public market data (uses mainnet public read-only API for accurate spot prices) ---

    def get_server_time(self) -> int:
        data = self._request("GET", "/api/v3/time", market_data_mainnet=True)
        return int(data.get("serverTime", 0))

    def get_ticker_price(self, symbol: str) -> Dict[str, Any]:
        norm = self.normalize_symbol(symbol)
        raw = self._request("GET", "/api/v3/ticker/price", params={"symbol": norm}, market_data_mainnet=True)
        return {"symbol": norm, "price": _f(raw.get("price"))}

    def get_book_ticker(self, symbol: str) -> Dict[str, Any]:
        norm = self.normalize_symbol(symbol)
        raw = self._request("GET", "/api/v3/ticker/bookTicker", params={"symbol": norm}, market_data_mainnet=True)
        bid = _f(raw.get("bidPrice"))
        ask = _f(raw.get("askPrice"))
        mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else max(bid, ask)
        spread_bps = ((ask - bid) / mid * 10000.0) if mid > 0 else 0.0
        return {
            "symbol": norm,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "bid_qty": _f(raw.get("bidQty")),
            "ask_qty": _f(raw.get("askQty")),
            "spread_bps": round(spread_bps, 2),
        }

    def get_24h_ticker(self, symbol: str) -> Dict[str, Any]:
        norm = self.normalize_symbol(symbol)
        raw = self._request("GET", "/api/v3/ticker/24hr", params={"symbol": norm}, market_data_mainnet=True)
        return {
            "symbol": norm,
            "last_price": _f(raw.get("lastPrice")),
            "price_change_pct": _f(raw.get("priceChangePercent")),
            "high_24h": _f(raw.get("highPrice")),
            "low_24h": _f(raw.get("lowPrice")),
            "volume_base": _f(raw.get("volume")),
            "quote_volume_usdt": _f(raw.get("quoteVolume")),
        }

    def get_klines(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        limit: int = 1000,
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        norm = self.normalize_symbol(symbol)
        params: Dict[str, Any] = {
            "symbol": norm,
            "interval": interval,
            "limit": max(1, min(int(limit), 1000)),
        }
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        rows = self._request("GET", "/api/v3/klines", params=params, market_data_mainnet=True)
        parsed: List[Dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            parsed.append(
                {
                    "open_time_ms": int(row[0]),
                    "open": _f(row[1]),
                    "high": _f(row[2]),
                    "low": _f(row[3]),
                    "close": _f(row[4]),
                    "volume": _f(row[5]),
                    "close_time_ms": int(row[6]) if len(row) > 6 else int(row[0]),
                }
            )
        return parsed

    # --- Signed Spot / Testnet Account & Order endpoints ---

    def get_account_summary(self, assets: Sequence[str] = ("USDT", "BTC", "ETH", "SOL", "BNB")) -> Dict[str, Any]:
        raw = self._request("GET", "/api/v3/account", signed=True)
        wanted = {a.upper() for a in assets}
        balances: Dict[str, Dict[str, float]] = {}
        for item in raw.get("balances", []) or []:
            asset = str(item.get("asset", "")).upper()
            free = _f(item.get("free"))
            locked = _f(item.get("locked"))
            total = free + locked
            if total > 0 or asset in wanted:
                balances[asset] = {"free": free, "locked": locked, "total": total}
        return {
            "testnet": self.testnet,
            "can_trade": bool(raw.get("canTrade", False)),
            "account_type": raw.get("accountType", "SPOT"),
            "balances": balances,
        }

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = self.normalize_symbol(symbol)
        rows = self._request("GET", "/api/v3/openOrders", params=params, signed=True)
        return [dict(r) for r in (rows or [])]

    def get_my_trades(self, symbol: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        norm = self.normalize_symbol(symbol)
        rows = self._request(
            "GET",
            "/api/v3/myTrades",
            params={"symbol": norm, "limit": max(1, min(int(limit), 1000))},
            signed=True,
        )
        return [dict(r) for r in (rows or [])]

    def plan_crypto_trend_rebalance(
        self,
        target_weights: Dict[str, float],
        *,
        quote_asset: str = "USDT",
        min_notional_usdt: float = 15.0,
    ) -> Dict[str, Any]:
        """Compute delta orders against live Testnet/Spot balances without placing any trade."""
        tracked_bases = []
        norm_targets: Dict[str, float] = {}
        for asset, weight in target_weights.items():
            sym = self.normalize_symbol(asset)
            base = sym[:-len(quote_asset)] if sym.endswith(quote_asset) else sym
            tracked_bases.append(base)
            norm_targets[sym] = max(0.0, float(weight))

        account = self.get_account_summary(assets=[quote_asset, *tracked_bases])
        balances = account["balances"]
        cash = _f(balances.get(quote_asset, {}).get("free"))

        quotes: Dict[str, Dict[str, Any]] = {}
        holdings_value = 0.0
        current_qty: Dict[str, float] = {}
        for sym in norm_targets:
            base = sym[:-len(quote_asset)] if sym.endswith(quote_asset) else sym
            qty = _f(balances.get(base, {}).get("total"))
            tick = self.get_book_ticker(sym)
            quotes[sym] = tick
            holdings_value += qty * _f(tick.get("mid"))
            current_qty[sym] = qty

        total_equity = cash + holdings_value
        orders: List[Dict[str, Any]] = []
        for sym, weight in sorted(norm_targets.items()):
            mid = _f(quotes[sym].get("mid"))
            if mid <= 0:
                continue
            target_notional = total_equity * weight
            current_notional = current_qty.get(sym, 0.0) * mid
            delta_notional = target_notional - current_notional
            if abs(delta_notional) < min_notional_usdt:
                continue
            side = "BUY" if delta_notional > 0 else "SELL"
            qty_delta = round(abs(delta_notional) / mid, 6)
            orders.append(
                {
                    "symbol": sym,
                    "side": side,
                    "quantity": qty_delta,
                    "notional_usdt": round(abs(delta_notional), 2),
                    "reference_mid": mid,
                    "spread_bps": quotes[sym]["spread_bps"],
                }
            )

        return {
            "testnet": self.testnet,
            "quote_asset": quote_asset,
            "cash_free": round(cash, 2),
            "holdings_value": round(holdings_value, 2),
            "total_equity": round(total_equity, 2),
            "orders": orders,
        }

    def place_market_order(
        self,
        symbol: str,
        side: str,
        *,
        quote_order_qty: Optional[float] = None,
        quantity: Optional[float] = None,
        test_only: bool = True,
        confirmed: bool = False,
    ) -> Dict[str, Any]:
        """Submit a Testnet market order or validate via ``/api/v3/order/test``."""
        if not test_only and not self.testnet:
            if not (self.live_trading_confirmed and confirmed):
                raise BinanceBrokerError(
                    "Live mainnet order blocked: BINANCE_TESTNET=true is required, or both "
                    "BINANCE_LIVE_TRADING_CONFIRMED=true and confirmed=True must be supplied."
                )
        if not test_only and self.testnet and not (self.auto_execute or confirmed):
            raise BinanceBrokerError(
                "Order submission blocked while BINANCE_AUTO_EXECUTE=false without explicit confirmed=True."
            )

        norm = self.normalize_symbol(symbol)
        upper_side = side.upper()
        if upper_side not in {"BUY", "SELL"}:
            raise BinanceBrokerError(f"Unsupported side '{side}'; expected BUY or SELL.")
        if quote_order_qty is None and quantity is None:
            raise BinanceBrokerError("Specify either quote_order_qty or quantity.")

        params: Dict[str, Any] = {
            "symbol": norm,
            "side": upper_side,
            "type": "MARKET",
        }
        if quote_order_qty is not None:
            params["quoteOrderQty"] = f"{float(quote_order_qty):.2f}"
        if quantity is not None:
            params["quantity"] = f"{float(quantity):.6f}"

        endpoint = "/api/v3/order/test" if test_only else "/api/v3/order"
        result = self._request("POST", endpoint, params=params, signed=True)
        return {
            "status": "validated" if test_only else "submitted",
            "testnet": self.testnet,
            "symbol": norm,
            "side": upper_side,
            "raw": result,
        }
