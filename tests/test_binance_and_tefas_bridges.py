# -*- coding: utf-8 -*-
"""Offline unit & API tests for Binance Spot/Testnet client, BinanceFetcher, and TefasFetcher."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
import pandas as pd
import pytest

from api.app import create_app
from data_provider.binance_fetcher import BinanceFetcher
from data_provider.tefas_fetcher import TefasFetcher
from src.brokers.binance.client import BinanceBrokerError, BinanceClient


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> Any:
        return self._payload


class _RecordingSession:
    def __init__(self, routes: Dict[str, Any]) -> None:
        self.routes = routes
        self.calls: List[Dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": method, "url": url, "kwargs": kwargs})
        parsed = urlparse(url)
        key = f"{method.upper()} {parsed.path}"
        handler = self.routes.get(key)
        if callable(handler):
            return _FakeResponse(200, handler(parsed, kwargs))
        if key in self.routes:
            return _FakeResponse(200, self.routes[key])
        return _FakeResponse(404, {"msg": f"unmocked {key}"})

    def post(self, url: str, json: Any = None, headers: Any = None, timeout: float = 8.0) -> _FakeResponse:
        self.calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
        parsed = urlparse(url)
        handler = self.routes.get(f"POST {parsed.path}")
        if callable(handler):
            return _FakeResponse(200, handler(json or {}))
        return _FakeResponse(404, {"error": "not mocked"})


def test_binance_client_safety_locks_block_mainnet_writes() -> None:
    mainnet_unlocked = BinanceClient(
        api_key="k",
        api_secret="s",
        testnet=False,
        auto_execute=True,
        live_trading_confirmed=False,
    )
    with pytest.raises(BinanceBrokerError, match="BINANCE_LIVE_TRADING_CONFIRMED"):
        mainnet_unlocked.place_market_order("BTCUSDT", "BUY", quote_order_qty=50.0, test_only=False, confirmed=True)

    testnet_manual = BinanceClient(
        api_key="k",
        api_secret="s",
        testnet=True,
        auto_execute=False,
    )
    with pytest.raises(BinanceBrokerError, match="BINANCE_AUTO_EXECUTE=false"):
        testnet_manual.place_market_order("BTCUSDT", "BUY", quote_order_qty=50.0, test_only=False, confirmed=False)


def test_binance_hmac_signing_and_rebalance_plan() -> None:
    secret = "super-secret-key"
    routes = {
        "GET /api/v3/account": {
            "canTrade": True,
            "accountType": "SPOT",
            "balances": [
                {"asset": "USDT", "free": "1000.0", "locked": "0.0"},
                {"asset": "BTC", "free": "0.01", "locked": "0.0"},
            ],
        },
        "GET /api/v3/ticker/bookTicker": lambda parsed, kw: (
            {"symbol": "BTCUSDT", "bidPrice": "99990", "askPrice": "100010", "bidQty": "1", "askQty": "1"}
            if "BTCUSDT" in parsed.query or (kw.get("params") or {}).get("symbol") == "BTCUSDT"
            else {"symbol": "ETHUSDT", "bidPrice": "2999", "askPrice": "3001", "bidQty": "1", "askQty": "1"}
        ),
        "POST /api/v3/order/test": {},
    }
    sess = _RecordingSession(routes)
    client = BinanceClient(api_key="pub-key", api_secret=secret, testnet=True, session=sess)

    plan = client.plan_crypto_trend_rebalance({"BTC-USD": 0.5, "ETH-USD": 0.25})
    assert plan["testnet"] is True
    # 1000 cash + 0.01 * 100000 = 2000 total -> BTC target 1000 (0 delta), ETH target 500 (+500 BUY)
    assert plan["total_equity"] == pytest.approx(2000.0)
    assert len(plan["orders"]) == 1
    assert plan["orders"][0]["symbol"] == "ETHUSDT"
    assert plan["orders"][0]["side"] == "BUY"
    assert plan["orders"][0]["notional_usdt"] == pytest.approx(500.0)

    # Verify HMAC signature matches server calculation
    acct_call = sess.calls[0]
    qs = urlparse(acct_call["url"]).query
    params = {k: v[0] for k, v in parse_qs(qs).items()}
    sig = params.pop("signature")
    raw_query_without_sig = "&".join(part for part in qs.split("&") if not part.startswith("signature="))
    expected_sig = hmac.new(secret.encode("utf-8"), raw_query_without_sig.encode("utf-8"), hashlib.sha256).hexdigest()
    assert sig == expected_sig
    assert acct_call["kwargs"]["headers"]["X-MBX-APIKEY"] == "pub-key"

    # Dry-run validation endpoint uses /order/test cleanly
    res = client.place_market_order("ETH-USD", "BUY", quote_order_qty=500.0, test_only=True)
    assert res["status"] == "validated"


def test_binance_fetcher_klines_cache_and_crypto_trend_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    klines = [
        [1704067200000 + i * 86_400_000, "40000", "41000", "39500", str(40000 + i * 100), "1200", 1704153599999]
        for i in range(5)
    ]
    sess = _RecordingSession({"GET /api/v3/klines": klines})
    client = BinanceClient(session=sess)
    fetcher = BinanceFetcher(client=client, cache_dir=tmp_path, cache_ttl_seconds=3600)

    s1 = fetcher.fetch_daily_series("BTC-USD", start="2024-01-01")
    assert s1 is not None and len(s1) == 5
    assert s1.iloc[-1] == pytest.approx(40400.0)
    assert len(sess.calls) == 1

    # Second read hits disk cache without network call
    s2 = fetcher.fetch_daily_series("BTC-USD", start="2024-01-01")
    assert s2 is not None and len(s2) == 5
    assert len(sess.calls) == 1

    # Crypto trend load_daily_closes falls back cleanly if Binance returns None
    from src.services import crypto_trend_strategy

    class _EmptyBinance:
        def fetch_daily_series(self, asset: str, start: str = "2015-01-01"):
            return None

    class _FakeTicker:
        def __init__(self, sym: str):
            self.sym = sym

        def history(self, start: str = "2015-01-01", auto_adjust: bool = True):
            return pd.DataFrame(
                {"Close": [101.0, 102.0]},
                index=pd.DatetimeIndex(["2025-01-01", "2025-01-02"]),
            )

    monkeypatch.setattr("data_provider.binance_fetcher.BinanceFetcher", lambda *a, **k: _EmptyBinance())
    monkeypatch.setattr("yfinance.Ticker", lambda sym: _FakeTicker(sym))
    df = crypto_trend_strategy.load_daily_closes(["BTC-USD"])
    assert list(df.columns) == ["BTC-USD"]
    assert float(df["BTC-USD"].iloc[-1]) == pytest.approx(102.0)


def test_tefas_fetcher_caches_and_falls_back_honestly(tmp_path: Path) -> None:
    def _tefas_handler(body: Dict[str, Any]) -> Dict[str, Any]:
        if body.get("fonKodu") == "PPZ":
            return {
                "errorCode": None,
                "resultList": [
                    {
                        "fonKodu": "PPZ",
                        "fonUnvan": "AZİMUT PORTFÖY PARA PİYASASI FONU",
                        "sonFiyat": 7.21,
                        "gunlukGetiri": 0.11,
                        "portBuyukluk": 9_900_000_000.0,
                        "fonKategori": "Para Piyasası Fonu",
                        "kategoriDerece": 12,
                        "kategoriFonSay": 86,
                        "yatirimciSayi": 7100,
                        "pazarPayi": 0.65,
                    }
                ],
            }
        return {"errorCode": "ERR", "resultList": []}

    sess = _RecordingSession({"POST /api/funds/fonBilgiGetir": _tefas_handler})
    cache_file = tmp_path / "tefas.json"
    fetcher = TefasFetcher(cache_path=cache_file, cache_ttl_seconds=3600, session=sess)

    rows = fetcher.fetch_curated_funds(codes=["PPZ", "TCA"])
    assert len(rows) == 2
    assert rows[0]["code"] == "PPZ" and rows[0]["source"] == "tefas_live"
    assert rows[0]["price_try"] == pytest.approx(7.21)
    assert rows[1]["code"] == "TCA" and rows[1]["source"] == "curated_fallback"
    assert rows[1]["price_try"] is None

    # Second call returns cached PPZ without calling session for PPZ again
    calls_before = len(sess.calls)
    rows_cached = fetcher.fetch_curated_funds(codes=["PPZ"])
    assert rows_cached[0]["source"] == "tefas_cached"
    assert len(sess.calls) == calls_before


def test_bridges_api_endpoints_status_and_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    client = TestClient(app)

    res = client.get("/api/v1/bridges/status")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    bridge_ids = {item["id"] for item in body["bridges"]}
    assert {"binance", "tefas", "evds", "alpaca", "csv_imports"} <= bridge_ids
    binance_row = next(item for item in body["bridges"] if item["id"] == "binance")
    assert binance_row["details"]["testnet"] is True
    assert binance_row["details"]["auto_execute"] is False

    monkeypatch.setattr(
        "api.v1.endpoints.bridges.BinanceFetcher.fetch_live_snapshot",
        lambda self, assets: [
            {
                "asset": "BTC-USD",
                "symbol": "BTCUSDT",
                "last_price": 90000.0,
                "bid": 89995.0,
                "ask": 90005.0,
                "spread_bps": 1.11,
                "price_change_pct_24h": 1.5,
                "quote_volume_usdt_24h": 500000000.0,
                "source": "binance_public",
            }
        ],
    )
    b_res = client.get("/api/v1/bridges/binance/preview?assets=BTC-USD")
    assert b_res.status_code == 200
    assert b_res.json()["tickers"][0]["symbol"] == "BTCUSDT"
