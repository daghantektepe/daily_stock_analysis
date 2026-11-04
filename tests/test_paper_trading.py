# -*- coding: utf-8 -*-
"""Tests for the opt-in paper trading ledger."""

import os
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config import Config
from src.services.paper_trading_service import PaperTradingService, apply_paper_trade_for_signal
from src.storage import DatabaseManager, PortfolioTrade, StockDaily


@pytest.fixture()
def db(tmp_path):
    old_env_file = os.environ.get("ENV_FILE")
    old_database_path = os.environ.get("DATABASE_PATH")
    env_path = tmp_path / ".env"
    db_path = tmp_path / "paper.db"
    env_path.write_text(
        f"STOCK_LIST=THYAO.IS\nADMIN_AUTH_ENABLED=false\nDATABASE_PATH={db_path}\n",
        encoding="utf-8",
    )
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(db_path)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    manager = DatabaseManager.get_instance()
    try:
        yield manager
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        for key, old in (("ENV_FILE", old_env_file), ("DATABASE_PATH", old_database_path)):
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _signal(signal_id, action, code="THYAO.IS", market="tr"):
    return {"id": signal_id, "stock_code": code, "stock_name": "Türk Hava Yolları", "market": market, "action": action}


def _service(db, size=10000.0):
    return PaperTradingService(db, enabled=True, position_size=size)


def _add_close(db, code, day, close):
    with db.session_scope() as session:
        session.add(StockDaily(code=code, date=day, open=close, high=close, low=close, close=close, volume=1))


def test_disabled_service_never_trades(db) -> None:
    service = PaperTradingService(db, enabled=False, position_size=10000)
    assert service.apply_signal(_signal(1, "buy"), price=250.0) is None
    assert service.list_trades() == []


def test_buy_reduce_sell_cycle_and_summary(db) -> None:
    service = _service(db)

    buy = service.apply_signal(_signal(1, "buy"), price=250.0, trade_date=date(2026, 11, 2))
    assert buy["side"] == "buy" and buy["quantity"] == 40.0 and buy["currency"] == "TRY"

    # No pyramiding while holding; non-trading actions are ignored.
    assert service.apply_signal(_signal(2, "add"), price=255.0) is None
    assert service.apply_signal(_signal(3, "watch"), price=255.0) is None

    reduce = service.apply_signal(_signal(4, "reduce"), price=300.0, trade_date=date(2026, 11, 3))
    assert reduce["side"] == "sell" and reduce["quantity"] == 20.0
    assert service.open_quantity("THYAO.IS") == 20.0

    _add_close(db, "THYAO.IS", date(2026, 11, 4), 290.0)
    summary = service.get_summary()
    position = summary["positions"][0]
    assert position["quantity"] == 20.0
    assert position["avg_cost"] == 250.0
    assert position["last_close"] == 290.0
    assert position["unrealized_pnl"] == pytest.approx(800.0)
    assert position["unrealized_pnl_pct"] == pytest.approx(16.0)
    assert summary["totals_by_currency"]["TRY"]["realized_pnl"] == pytest.approx(1000.0)
    assert summary["win_rate_pct"] == 100.0

    sell = service.apply_signal(_signal(5, "sell"), price=240.0)
    assert sell["quantity"] == 20.0
    summary = service.get_summary()
    assert summary["open_position_count"] == 0
    assert summary["closed_trade_count"] == 2
    assert summary["win_rate_pct"] == 50.0
    assert summary["totals_by_currency"]["TRY"]["realized_pnl"] == pytest.approx(800.0)


def test_sell_without_position_and_bad_prices_do_not_trade(db) -> None:
    service = _service(db)
    assert service.apply_signal(_signal(1, "sell"), price=250.0) is None
    assert service.apply_signal(_signal(2, "buy"), price=None) is None
    assert service.apply_signal(_signal(3, "buy"), price="nan") is None
    assert service.apply_signal(_signal(4, "buy"), price=-1) is None
    # Position size smaller than one share at this price.
    assert _service(db, size=100.0).apply_signal(_signal(5, "buy"), price=250.0) is None
    assert service.list_trades() == []


def test_each_signal_fills_once(db) -> None:
    service = _service(db)
    assert service.apply_signal(_signal(7, "buy"), price=250.0) is not None
    assert service.apply_signal(_signal(7, "sell"), price=260.0) is None
    assert len(service.list_trades()) == 1


def test_currencies_are_not_mixed_and_missing_close_marks_at_cost(db) -> None:
    service = _service(db)
    service.apply_signal(_signal(1, "buy"), price=250.0)
    service.apply_signal(_signal(2, "buy", code="AAPL", market="us"), price=200.0)

    summary = service.get_summary()
    assert set(summary["totals_by_currency"]) == {"TRY", "USD"}
    assert all(item["price_stale"] for item in summary["positions"])
    assert summary["totals_by_currency"]["USD"]["unrealized_pnl"] == 0.0


def test_paper_ledger_is_separate_from_portfolio(db) -> None:
    _service(db).apply_signal(_signal(1, "buy"), price=250.0)
    with db.session_scope() as session:
        assert session.query(PortfolioTrade).count() == 0


def test_pipeline_hook_only_fills_newly_created_signals(db, monkeypatch) -> None:
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    monkeypatch.setenv("PAPER_TRADING_POSITION_SIZE", "5000")
    Config.reset_instance()

    assert apply_paper_trade_for_signal({"item": _signal(1, "buy"), "created": False}, price=250.0) is None
    filled = apply_paper_trade_for_signal({"item": _signal(2, "buy"), "created": True}, price=250.0)
    assert filled["quantity"] == 20.0
    assert apply_paper_trade_for_signal(None, price=250.0) is None


def test_pipeline_hook_is_noop_when_disabled(db, monkeypatch) -> None:
    monkeypatch.delenv("PAPER_TRADING_ENABLED", raising=False)
    Config.reset_instance()
    assert apply_paper_trade_for_signal({"item": _signal(1, "buy"), "created": True}, price=250.0) is None


def test_config_parses_paper_trading_settings(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("PAPER_TRADING_ENABLED=true\nPAPER_TRADING_POSITION_SIZE=2500\n", encoding="utf-8")
    monkeypatch.setenv("ENV_FILE", str(env_path))
    monkeypatch.setenv("PAPER_TRADING_ENABLED", "true")
    monkeypatch.setenv("PAPER_TRADING_POSITION_SIZE", "2500")
    Config.reset_instance()
    try:
        config = Config.get_instance()
        assert config.paper_trading_enabled is True
        assert config.paper_trading_position_size == 2500.0
    finally:
        Config.reset_instance()


def test_paper_trading_api_returns_summary_and_trades(db, tmp_path) -> None:
    from api.app import create_app

    _service(db).apply_signal(_signal(1, "buy"), price=250.0)
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    client = TestClient(create_app(static_dir=Path(static_dir)))

    summary = client.get("/api/v1/paper-trading/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["open_position_count"] == 1
    assert body["positions"][0]["stock_code"] == "THYAO.IS"

    trades = client.get("/api/v1/paper-trading/trades?limit=5")
    assert trades.status_code == 200
    assert trades.json()["items"][0]["signal_id"] == 1
