# -*- coding: utf-8 -*-
"""Offline API tests for manual paper trading orders, stops, equity curve, and stock search."""

import os
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_database_manager
from api.v1.endpoints import paper_trading as pt_ep
from api.v1.endpoints import stocks as stocks_ep
from src.config import Config
from src.storage import DatabaseManager, StockDaily


@pytest.fixture()
def paper_client(tmp_path):
    old_env_file = os.environ.get("ENV_FILE")
    old_database_path = os.environ.get("DATABASE_PATH")
    env_path = tmp_path / ".env"
    db_path = tmp_path / "paper_actions.db"
    env_path.write_text(
        f"STOCK_LIST=NVDA,THYAO.IS\nADMIN_AUTH_ENABLED=false\nDATABASE_PATH={db_path}\nPAPER_TRADING_ENABLED=true\n",
        encoding="utf-8",
    )
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(db_path)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    manager = DatabaseManager.get_instance()

    with manager.session_scope() as session:
        session.add(StockDaily(code="NVDA", date=date(2026, 11, 10), open=140.0, high=145.0, low=139.0, close=142.0, volume=1_000_000))
        session.add(StockDaily(code="NVDA", date=date(2026, 11, 11), open=142.0, high=149.0, low=141.0, close=148.0, volume=1_200_000))

    app = FastAPI()
    app.include_router(pt_ep.router, prefix="/api/v1/paper-trading")
    app.include_router(stocks_ep.router, prefix="/api/v1/stocks")
    app.dependency_overrides[get_database_manager] = lambda: manager

    try:
        yield TestClient(app)
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        for key, old in (("ENV_FILE", old_env_file), ("DATABASE_PATH", old_database_path)):
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def test_manual_paper_order_stops_and_equity_curve(paper_client: TestClient) -> None:
    # 1. Place manual BUY order using stored StockDaily close
    buy_res = paper_client.post(
        "/api/v1/paper-trading/orders",
        json={"stock_code": "NVDA", "action": "buy", "quantity": 10, "price": 140.0, "stop_loss": 130.0, "take_profit": 165.0},
    )
    assert buy_res.status_code == 200
    buy_body = buy_res.json()
    assert buy_body["stock_code"] == "NVDA"
    assert buy_body["side"] == "buy"
    assert buy_body["quantity"] == 10.0
    assert buy_body["signal_id"] < -1_000_000

    # 2. Update stop-loss / take-profit
    patch_res = paper_client.patch(
        "/api/v1/paper-trading/positions/NVDA/stops",
        json={"stop_loss": 133.5, "take_profit": 170.0},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["stop_loss"] == 133.5
    assert patch_res.json()["take_profit"] == 170.0

    # 3. Equity curve endpoint returns points
    eq_res = paper_client.get("/api/v1/paper-trading/equity-curve?days=30")
    assert eq_res.status_code == 200
    eq_body = eq_res.json()
    assert len(eq_body["points"]) >= 1
    assert eq_body["currencies"] == ["USD"]

    # 4. Reduce by half, then close remaining position
    red_res = paper_client.post(
        "/api/v1/paper-trading/orders",
        json={"stock_code": "NVDA", "action": "reduce", "price": 148.0},
    )
    assert red_res.status_code == 200
    assert red_res.json()["quantity"] == 5.0

    sell_res = paper_client.post(
        "/api/v1/paper-trading/orders",
        json={"stock_code": "NVDA", "action": "sell", "price": 148.0},
    )
    assert sell_res.status_code == 200
    assert sell_res.json()["quantity"] == 5.0


def test_stock_search_endpoint(paper_client: TestClient) -> None:
    res = paper_client.get("/api/v1/stocks/search?q=AAPL&market=ALL&limit=5")
    assert res.status_code == 200
    body = res.json()
    assert body["query"] == "AAPL"
    assert "items" in body
