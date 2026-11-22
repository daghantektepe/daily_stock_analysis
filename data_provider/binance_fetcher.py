# -*- coding: utf-8 -*-
"""Binance Spot public market data fetcher (OHLCV daily closes + live spread).

Primary data bridge for cryptocurrency assets (``BTC-USD``, ``ETH-USD``, etc.)
with zero API-key requirement for public read-only market endpoints. Designed
to integrate seamlessly with ``crypto_trend_strategy.load_daily_closes`` while
preserving Yahoo Finance (``yfinance``) as an automatic per-asset fallback.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from src.brokers.binance.client import BinanceBrokerError, BinanceClient

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path("data/cache")


def _asset_to_binance_symbol(asset: str) -> Optional[str]:
    raw = str(asset or "").strip().upper()
    if not raw:
        return None
    # Only convert known crypto tickers (e.g. BTC-USD, ETH-USD, SOL-USD, BTCUSDT, BTC/USDT)
    if raw.endswith(".IS") or raw.endswith("=X") or raw.endswith(".SS") or raw.endswith(".SZ"):
        return None
    cleaned = raw.replace("/", "").replace("-", "")
    if cleaned.endswith("USDT"):
        return cleaned
    if raw.endswith("-USD") or raw.endswith("/USD"):
        return f"{cleaned[:-3]}USDT"
    if cleaned in {"BTC", "ETH", "SOL", "BNB", "XRP", "AVAX", "ADA", "DOGE", "LINK"}:
        return f"{cleaned}USDT"
    return None


class BinanceFetcher:
    """Fetches public daily OHLCV closes and live book-ticker quotes from Binance Spot."""

    def __init__(
        self,
        client: Optional[BinanceClient] = None,
        *,
        cache_dir: Optional[Path] = None,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self.client = client or BinanceClient()
        self.cache_dir = Path(cache_dir) if cache_dir is not None else _DEFAULT_CACHE_DIR
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))

    def _cache_path(self, symbol: str, interval: str = "1d") -> Path:
        return self.cache_dir / f"binance_{symbol.lower()}_{interval}.json"

    def _read_cache(self, symbol: str, interval: str = "1d") -> Optional[List[Dict[str, Any]]]:
        if self.cache_ttl_seconds <= 0:
            return None
        path = self._cache_path(symbol, interval)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = float(payload.get("fetched_at", 0))
            if (time.time() - fetched_at) > self.cache_ttl_seconds:
                return None
            rows = payload.get("rows")
            return rows if isinstance(rows, list) else None
        except Exception:
            return None

    def _write_cache(self, symbol: str, interval: str, rows: List[Dict[str, Any]]) -> None:
        if self.cache_ttl_seconds <= 0:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path = self._cache_path(symbol, interval)
            path.write_text(
                json.dumps({"fetched_at": time.time(), "symbol": symbol, "interval": interval, "rows": rows}),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("[binance-fetcher] cache write skipped for %s: %s", symbol, exc)

    def fetch_daily_series(
        self,
        asset: str,
        *,
        start: str = "2015-01-01",
        use_cache: bool = True,
    ) -> Optional[pd.Series]:
        """Fetch paginated daily UTC close series for ``asset`` (up to start date)."""
        symbol = _asset_to_binance_symbol(asset)
        if not symbol:
            return None

        start_ts = pd.Timestamp(start, tz="UTC")
        start_ms = int(start_ts.timestamp() * 1000)

        rows: Optional[List[Dict[str, Any]]] = self._read_cache(symbol) if use_cache else None
        if rows is None:
            collected: List[Dict[str, Any]] = []
            cursor_ms = start_ms
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            for _ in range(12):  # 12 * 1000 days (~32 years ceiling)
                batch = self.client.get_klines(
                    symbol,
                    interval="1d",
                    limit=1000,
                    start_time_ms=cursor_ms,
                )
                if not batch:
                    break
                collected.extend(batch)
                last_open_ms = int(batch[-1]["open_time_ms"])
                if len(batch) < 1000 or last_open_ms + 86_400_000 >= now_ms:
                    break
                cursor_ms = last_open_ms + 86_400_000
            if not collected:
                return None
            rows = collected
            if use_cache:
                self._write_cache(symbol, "1d", rows)

        dates = [pd.Timestamp(int(r["open_time_ms"]), unit="ms", tz="UTC").tz_localize(None).normalize() for r in rows]
        closes = [float(r["close"]) for r in rows]
        series = pd.Series(closes, index=pd.DatetimeIndex(dates), name=asset)
        series = series[~series.index.duplicated(keep="last")].sort_index()
        return series[series.index >= pd.Timestamp(start).normalize()]

    def fetch_live_snapshot(self, assets: Sequence[str] = ("BTC-USD", "ETH-USD", "SOL-USD")) -> List[Dict[str, Any]]:
        """Fetch live Spot bid/ask/spread + 24h stats for a list of crypto assets."""
        out: List[Dict[str, Any]] = []
        for asset in assets:
            symbol = _asset_to_binance_symbol(asset)
            if not symbol:
                continue
            try:
                book = self.client.get_book_ticker(symbol)
                stats = self.client.get_24h_ticker(symbol)
                out.append(
                    {
                        "asset": asset,
                        "symbol": symbol,
                        "last_price": stats["last_price"],
                        "bid": book["bid"],
                        "ask": book["ask"],
                        "spread_bps": book["spread_bps"],
                        "price_change_pct_24h": stats["price_change_pct"],
                        "quote_volume_usdt_24h": stats["quote_volume_usdt"],
                        "source": "binance_public",
                    }
                )
            except BinanceBrokerError as exc:
                logger.warning("[binance-fetcher] snapshot skipped for %s (%s): %s", asset, symbol, exc)
                out.append(
                    {
                        "asset": asset,
                        "symbol": symbol,
                        "last_price": None,
                        "bid": None,
                        "ask": None,
                        "spread_bps": None,
                        "price_change_pct_24h": None,
                        "quote_volume_usdt_24h": None,
                        "source": "unavailable",
                        "error": str(exc),
                    }
                )
        return out
