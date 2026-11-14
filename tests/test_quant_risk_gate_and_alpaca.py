# -*- coding: utf-8 -*-
"""Offline unit & API tests for Phase 2 Quant Risk Guardrails and Phase 3 Alpaca Broker Bridge."""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, List

import pytest

from src.brokers.alpaca import AlpacaClient
from src.config import Config
from src.services.paper_trading_service import PaperTradingService
from src.services.quant_risk_gate import evaluate_market_regime
from src.storage import DatabaseManager, PaperTradeRecord, StockDaily


@pytest.fixture()
def db(tmp_path):
    old_env_file = os.environ.get("ENV_FILE")
    old_database_path = os.environ.get("DATABASE_PATH")
    saved_paper_env = {
        k: os.environ.pop(k)
        for k in list(os.environ.keys())
        if k.startswith(("PAPER_TRADING_", "ALPACA_"))
    }
    env_path = tmp_path / ".env"
    db_path = tmp_path / "risk_alpaca.db"
    env_path.write_text(
        f"STOCK_LIST=NVDA\nADMIN_AUTH_ENABLED=false\nDATABASE_PATH={db_path}\n",
        encoding="utf-8",
    )
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(db_path)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    mgr = DatabaseManager.get_instance()
    try:
        yield mgr
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        for k in list(os.environ.keys()):
            if k.startswith(("PAPER_TRADING_", "ALPACA_")):
                os.environ.pop(k, None)
        os.environ.update(saved_paper_env)
        for key, old in (("ENV_FILE", old_env_file), ("DATABASE_PATH", old_database_path)):
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def test_market_regime_risk_on_caution_and_risk_off() -> None:
    bull = evaluate_market_regime(
        history_fetcher=lambda sym: [100.0 + i * 0.5 for i in range(220)] if sym == "SPY" else [15.0]
    )
    assert bull.regime == "risk_on"
    assert bull.position_scale == 1.0

    caution = evaluate_market_regime(
        history_fetcher=lambda sym: (
            [100.0 + i * 0.5 for i in range(190)] + [180.0 - i * 0.2 for i in range(30)]
            if sym == "SPY"
            else [25.5]
        )
    )
    assert caution.regime == "caution"
    assert caution.position_scale == 0.5

    bear = evaluate_market_regime(
        history_fetcher=lambda sym: [220.0 - i * 0.5 for i in range(220)] if sym == "SPY" else [35.0]
    )
    assert bear.regime == "risk_off"
    assert bear.position_scale == 0.0


def test_paper_trading_risk_gates_and_drawdown_breaker(db) -> None:
    svc = PaperTradingService(
        db,
        enabled=True,
        position_size=2000.0,
        risk_pct=2.0,
        max_open_positions=2,
        max_sector_positions=1,
        max_drawdown_pct=10.0,
        quant_gate_enabled=True,
        quant_min_score=40.0,
    )

    # 1. Quant gate blocks weak quant_score (< 40)
    blocked_q = svc.apply_signal(
        {"id": 1, "stock_code": "NVDA", "market": "us", "action": "buy", "quant_score": 25.0},
        price=100.0,
    )
    assert blocked_q is None

    # 2. High quant_score NVDA passes
    ok_nvda = svc.apply_signal(
        {"id": 2, "stock_code": "NVDA", "market": "us", "action": "buy", "quant_score": 72.0},
        price=100.0,
    )
    assert ok_nvda is not None and ok_nvda["stock_code"] == "NVDA"

    # 3. Sector cap (max_sector_positions=1) blocks 2nd Semiconductor (AMD)
    blocked_sector = svc.apply_signal(
        {"id": 3, "stock_code": "AMD", "market": "us", "action": "buy", "quant_score": 78.0},
        price=100.0,
    )
    assert blocked_sector is None

    # 4. Different sector (LLY, Healthcare) passes
    ok_lly = svc.apply_signal(
        {"id": 4, "stock_code": "LLY", "market": "us", "action": "buy", "quant_score": 68.0},
        price=500.0,
    )
    assert ok_lly is not None and ok_lly["stock_code"] == "LLY"

    # 5. Max open positions (2) blocks 3rd ticker (JPM, Financials)
    blocked_max_pos = svc.apply_signal(
        {"id": 5, "stock_code": "JPM", "market": "us", "action": "buy", "quant_score": 80.0},
        price=200.0,
    )
    assert blocked_max_pos is None

    # 6. Inject a large realized loss (>= 10% drawdown on base=20000) to trip circuit breaker
    with db.session_scope() as session:
        session.add(
            PaperTradeRecord(
                signal_id=99,
                stock_code="XOM",
                market="us",
                currency="USD",
                action="buy",
                side="buy",
                quantity=60.0,
                price=100.0,
                trade_date=date(2026, 11, 1),
            )
        )
        session.add(
            PaperTradeRecord(
                signal_id=100,
                stock_code="XOM",
                market="us",
                currency="USD",
                action="sell",
                side="sell",
                quantity=60.0,
                price=50.0,
                trade_date=date(2026, 11, 2),
            )
        )
    # Increase max_open_positions so only drawdown breaker decides
    svc.max_open_positions = 10
    blocked_dd = svc.apply_signal(
        {"id": 6, "stock_code": "JPM", "market": "us", "action": "buy", "quant_score": 90.0},
        price=200.0,
    )
    assert blocked_dd is None

    summary = svc.get_summary()
    assert summary["risk_status"]["circuit_breaker_triggered"] is True
    assert summary["risk_status"]["current_drawdown_pct"] >= 10.0


def test_market_regime_risk_off_blocks_entry_when_enabled(db) -> None:
    # Seed 220 falling SPY bars so evaluate_market_regime flags risk_off
    start = date(2025, 10, 1)
    with db.session_scope() as session:
        for i in range(220):
            px = 600.0 - i * 0.6
            session.add(
                StockDaily(
                    code="SPY",
                    date=start + timedelta(days=i),
                    open=px,
                    high=px * 1.005,
                    low=px * 0.995,
                    close=px,
                    volume=50_000_000,
                )
            )
    svc = PaperTradingService(
        db,
        enabled=True,
        position_size=2000.0,
        market_regime_filter=True,
    )
    blocked = svc.apply_signal(
        {"id": 10, "stock_code": "MSFT", "market": "us", "action": "buy"},
        price=400.0,
        trade_date=start + timedelta(days=219),
    )
    assert blocked is None
    summary = svc.get_summary()
    assert summary["risk_status"]["market_regime"]["regime"] == "risk_off"


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = "{}"

    def json(self) -> Any:
        return self._payload


class _FakeSession:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs) -> _FakeResponse:
        self.calls.append({"method": method, "url": url, "json": kwargs.get("json"), "params": kwargs.get("params")})
        if url.endswith("/v2/account"):
            return _FakeResponse(200, {"id": "acct-1", "status": "ACTIVE", "currency": "USD", "cash": "100000", "equity": "100000", "portfolio_value": "100000", "buying_power": "200000"})
        if url.endswith("/v2/clock"):
            return _FakeResponse(200, {"is_open": True, "timestamp": "2026-11-14T10:00:00Z"})
        if url.endswith("/v2/positions"):
            return _FakeResponse(200, [{"symbol": "NVDA", "qty": "5", "avg_entry_price": "130", "current_price": "135", "market_value": "675", "unrealized_pl": "25", "unrealized_plpc": "0.0384"}])
        if url.endswith("/v2/orders") and method == "GET":
            return _FakeResponse(200, [])
        if url.endswith("/v2/orders") and method == "POST":
            return _FakeResponse(200, {"id": "ord-123", "status": "accepted", **kwargs.get("json", {})})
        return _FakeResponse(200, {})


def test_alpaca_client_and_auto_mirror_and_api(db, tmp_path, monkeypatch) -> None:
    fake_session = _FakeSession()
    client = AlpacaClient(api_key="PKTEST", secret_key="SKTEST", paper=True, session=fake_session)
    assert client.base_url == "https://paper-api.alpaca.markets"

    svc = PaperTradingService(
        db,
        enabled=True,
        position_size=2000.0,
        alpaca_client=client,
        alpaca_auto_execute=True,
    )
    trade = svc.apply_signal(
        {"id": 501, "stock_code": "NVDA", "market": "us", "action": "buy", "stop_loss": 120.0, "take_profit": 160.0},
        price=135.0,
    )
    assert trade is not None
    post_calls = [c for c in fake_session.calls if c["method"] == "POST"]
    assert len(post_calls) == 1
    body = post_calls[0]["json"]
    assert body["symbol"] == "NVDA"
    assert body["order_class"] == "bracket"
    assert body["stop_loss"] == {"stop_price": "120.00"}
    assert body["take_profit"] == {"limit_price": "160.00"}
    assert body["client_order_id"] == "dsa-sig-501"

    # Verify API endpoints
    from fastapi.testclient import TestClient
    from api.app import create_app

    monkeypatch.setattr(
        "api.v1.endpoints.paper_trading.AlpacaClient",
        lambda: AlpacaClient(api_key="PKTEST", secret_key="SKTEST", paper=True, session=fake_session),
    )
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    api_client = TestClient(create_app(static_dir=static_dir))
    res = api_client.get("/api/v1/paper-trading/alpaca/status")
    assert res.status_code == 200
    data = res.json()
    assert data["configured"] is True
    assert data["paper"] is True
    assert data["account"]["equity"] == 100000.0
    assert data["positions"][0]["symbol"] == "NVDA"

    ord_res = api_client.post(
        "/api/v1/paper-trading/alpaca/orders",
        json={"symbol": "MSFT", "qty": 2, "side": "buy", "stop_loss": 380.0, "take_profit": 460.0},
    )
    assert ord_res.status_code == 200
    assert ord_res.json()["id"] == "ord-123"
