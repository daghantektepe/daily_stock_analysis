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

    summary = client.get("/api/v1/paper-trading/summary?benchmark=false&outcomes=true")
    assert summary.status_code == 200
    assert summary.json()["benchmarks"] == {}
    body = summary.json()
    assert body["open_position_count"] == 1
    assert body["positions"][0]["stock_code"] == "THYAO.IS"
    assert body["positions"][0]["stop_loss"] is not None
    assert body["positions"][0]["take_profit"] is not None
    assert "signal_outcomes" in body

    trades = client.get("/api/v1/paper-trading/trades?limit=5")
    assert trades.status_code == 200
    assert trades.json()["items"][0]["signal_id"] == 1

    alerts = client.get("/api/v1/paper-trading/kap-alerts?live=false")
    assert alerts.status_code == 200
    assert isinstance(alerts.json()["items"], list)


# ------------------------------------------------------------- benchmarks
_HISTORY = {
    "XU100.IS": {date(2026, 11, 2): 10000.0, date(2026, 11, 4): 10500.0, date(2026, 11, 6): 11000.0},
    "TRY=X": {date(2026, 11, 2): 40.0, date(2026, 11, 4): 41.0, date(2026, 11, 6): 42.0},
}


def _fake_history(symbol, start, end):
    return {day: close for day, close in _HISTORY.get(symbol, {}).items() if start <= day <= end}


_TRADES = [
    {"id": 1, "stock_code": "THYAO.IS", "market": "tr", "side": "buy", "quantity": 40, "price": 250.0,
     "trade_date": "2026-11-02"},
    {"id": 2, "stock_code": "THYAO.IS", "market": "tr", "side": "sell", "quantity": 40, "price": 300.0,
     "trade_date": "2026-11-04"},
    # Saturday buy: priced at Friday's index close / FX rate.
    {"id": 3, "stock_code": "ASELS.IS", "market": "tr", "side": "buy", "quantity": 10, "price": 100.0,
     "trade_date": "2026-11-05"},
]


def test_benchmark_index_shadow_and_usd_return() -> None:
    from src.services.paper_trading_benchmark import compute_market_benchmark

    result = compute_market_benchmark(
        _TRADES, market="tr", mark_prices={"ASELS.IS": 110.0}, today=date(2026, 11, 6), history=_fake_history,
    )
    invested = 10000 + 1000
    strategy = (12000 + 1100 - invested) / invested * 100
    index = (10500 + 1000 / 10500 * 11000 - invested) / invested * 100
    usd_in = 10000 / 40 + 1000 / 41
    usd = (12000 / 41 + 1100 / 42 - usd_in) / usd_in * 100
    assert result["benchmark_name"] == "BIST 100"
    assert result["capital_deployed"] == 11000
    assert result["strategy_return_pct"] == pytest.approx(strategy, abs=0.01)
    assert result["benchmark_return_pct"] == pytest.approx(index, abs=0.01)
    assert result["excess_return_pct"] == pytest.approx(strategy - index, abs=0.02)
    assert result["usd_return_pct"] == pytest.approx(usd, abs=0.01)
    assert result["fx_change_pct"] == pytest.approx(5.0)


def test_benchmark_fails_open_without_history_and_skips_other_markets() -> None:
    from src.services.paper_trading_benchmark import compute_benchmarks, compute_market_benchmark

    result = compute_market_benchmark(
        _TRADES, market="tr", mark_prices={"ASELS.IS": 110.0}, today=date(2026, 11, 6),
        history=lambda *_args: {},
    )
    assert result["strategy_return_pct"] is not None
    assert result["benchmark_return_pct"] is None and result["usd_return_pct"] is None
    hk_trades = [dict(trade, market="hk") for trade in _TRADES]
    assert compute_benchmarks(hk_trades, mark_prices={}, history=_fake_history) == {}

    def broken(*_args):
        raise RuntimeError("down")

    assert compute_benchmarks(_TRADES, mark_prices={}, history=broken) == {}


def test_us_benchmark_index_and_return() -> None:
    from src.services.paper_trading_benchmark import compute_market_benchmark

    us_history = {
        "SPY": {date(2026, 11, 2): 500.0, date(2026, 11, 4): 520.0, date(2026, 11, 6): 525.0},
    }

    def _us_history(symbol, start, end):
        return {d: c for d, c in us_history.get(symbol, {}).items() if start <= d <= end}

    us_trades = [
        {"id": 1, "stock_code": "AAPL", "market": "us", "side": "buy", "quantity": 10, "price": 150.0,
         "trade_date": "2026-11-02"},
        {"id": 2, "stock_code": "AAPL", "market": "us", "side": "sell", "quantity": 10, "price": 180.0,
         "trade_date": "2026-11-04"},
    ]
    result = compute_market_benchmark(
        us_trades, market="us", mark_prices={"AAPL": 180.0}, today=date(2026, 11, 6), history=_us_history
    )
    assert result is not None
    assert result["benchmark_name"] == "S&P 500 (SPY)"
    assert result["strategy_return_pct"] == pytest.approx(20.0)
    assert result["benchmark_return_pct"] == pytest.approx(4.0)
    assert result["excess_return_pct"] == pytest.approx(16.0)
    assert result["usd_return_pct"] == pytest.approx(20.0)
    assert result["fx_change_pct"] == 0.0


def test_summary_includes_benchmarks_and_report_text(db) -> None:
    from src.services.paper_trading_benchmark import format_paper_trading_report

    service = _service(db)
    service.apply_signal(_signal(1, "buy"), price=250.0, trade_date=date(2026, 11, 2))
    _add_close(db, "THYAO.IS", date(2026, 11, 6), 275.0)
    summary = service.get_summary(include_benchmarks=True, benchmark_history=_fake_history)

    benchmark = summary["benchmarks"]["tr"]
    assert benchmark["benchmark"] == "XU100.IS"
    assert benchmark["strategy_return_pct"] == pytest.approx(10.0)
    text = format_paper_trading_report(summary)
    assert "Kıyas (BIST 100): strateji +10.00%" in text
    assert "THYAO.IS" in text and "komisyon" in text
    assert service.get_summary()["benchmarks"] == {}


def test_evaluate_signal_outcomes_and_weekly_report(db, tmp_path) -> None:
    import json
    from datetime import datetime, timedelta, timezone

    from src.services.paper_trading_benchmark import (
        evaluate_signal_outcomes,
        format_paper_trading_report,
        maybe_send_weekly_performance_report,
    )
    from src.storage import DecisionSignalRecord

    with db.session_scope() as session:
        row = DecisionSignalRecord(
            stock_code="THYAO.IS",
            stock_name="Türk Hava Yolları",
            market="tr",
            source_type="analysis",
            source_report_id=101,
            trace_id="trace-tr-thyao-buy-2026-11-02",
            market_phase="postmarket",
            trigger_source="cli",
            action="buy",
            action_label="buy",
            horizon="3d",
            reason="Güçlü bilanço",
            data_quality_summary_json='{"level": "good"}',
            metadata_json=json.dumps({"market_phase_summary": {"session_date": "2026-11-02"}}),
            plan_quality="complete",
            status="active",
        )
        session.add(row)
        session.flush()
        sig_id = int(row.id)

    service = _service(db)
    service.apply_signal(_signal(sig_id, "buy"), price=250.0, trade_date=date(2026, 11, 2))

    # Seed anchor bar (2026-11-02) + 5 forward trading days with +6% gain -> hit across 1d/3d/5d.
    for offset, close in enumerate([250.0, 258.0, 260.0, 262.5, 264.0, 265.0]):
        _add_close(db, "THYAO.IS", date(2026, 11, 2) + timedelta(days=offset), close)

    outcomes = evaluate_signal_outcomes(market="tr", db_manager=db)
    assert outcomes["completed"] == 3  # 1d, 3d, 5d completed; 10d still unable
    assert outcomes["hit"] == 3
    assert outcomes["hit_rate_pct"] == 100.0
    assert outcomes["by_horizon"]["1d"]["hit_rate_pct"] == 100.0
    assert outcomes["by_horizon"]["5d"]["hit_rate_pct"] == 100.0
    assert outcomes["by_action"]["buy"]["hit"] == 3

    summary = service.get_summary(include_benchmarks=True, benchmark_history=_fake_history)
    report = format_paper_trading_report(summary, outcome_stats=outcomes)
    assert "🎯 Sinyal isabeti (±%2 nötr bant): 3 değerlendirme | isabet %100" in report
    assert "Ufuklar: 1g %100" in report and "3g %100" in report and "5g %100" in report
    assert "Yön bazında: al %100 (3/3)" in report

    sent = []

    class _FakeNotifier:
        def send(self, text, **kwargs):
            sent.append((text, kwargs))
            return True

    state_file = tmp_path / "weekly_state.json"
    # Thursday 19:00 Istanbul (16:00 UTC) -> not Friday, does not send.
    thursday = datetime(2026, 11, 5, 16, 0, tzinfo=timezone.utc)
    assert (
        maybe_send_weekly_performance_report(
            notifier=_FakeNotifier(),
            db_manager=db,
            state_path=state_file,
            now=thursday,
            history=_fake_history,
        )
        is False
    )
    assert sent == []

    # Friday 18:30 Istanbul (15:30 UTC) -> sends once and records the ISO week.
    friday_evening = datetime(2026, 11, 6, 15, 30, tzinfo=timezone.utc)
    assert (
        maybe_send_weekly_performance_report(
            notifier=_FakeNotifier(),
            db_manager=db,
            state_path=state_file,
            now=friday_evening,
            history=_fake_history,
        )
        is True
    )
    assert len(sent) == 1
    assert "🎯 Sinyal isabeti" in sent[0][0]
    assert sent[0][1]["dedup_key"] == "weekly-performance:2026-W45"

    # Second run on the same Friday evening is skipped (idempotent per ISO week).
    assert (
        maybe_send_weekly_performance_report(
            notifier=_FakeNotifier(),
            db_manager=db,
            state_path=state_file,
            now=friday_evening,
            history=_fake_history,
        )
        is False
    )
    assert len(sent) == 1


def test_atr_risk_sizing_and_stop_take_profit_enforcement(db) -> None:
    from datetime import timedelta
    from src.services.paper_trading_benchmark import format_paper_trading_report
    from src.services.paper_trading_service import compute_atr14, compute_atr_risk_plan

    # Seed 10 OHLC bars for THYAO.IS up to 2026-11-02 with True Range = 12.5 TRY (high volatility: 5% ATR at 250 TRY).
    base_day = date(2026, 10, 20)
    with db.session_scope() as session:
        for idx in range(10):
            session.add(
                StockDaily(
                    code="THYAO.IS",
                    date=base_day + timedelta(days=idx),
                    open=250.0,
                    high=256.25,
                    low=243.75,
                    close=250.0,
                    volume=1_000_000,
                )
            )

    atr = compute_atr14("THYAO.IS", db_manager=db, as_of_date=date(2026, 11, 2))
    assert atr == pytest.approx(12.5)

    plan = compute_atr_risk_plan(
        "THYAO.IS",
        price=250.0,
        position_size=10000.0,
        risk_pct=5.0,
        db_manager=db,
        as_of_date=date(2026, 11, 2),
    )
    # Stop = 250 - 2*12.5 = 225.0 (-10%); TP = 250 + 3*12.5 = 287.5 (+15%)
    # Risk budget = 5% of 10000 = 500 TRY; per-share risk = 25 TRY -> 20 shares (instead of 40)
    assert plan["stop_loss"] == pytest.approx(225.0)
    assert plan["take_profit"] == pytest.approx(287.5)
    assert plan["recommended_quantity"] == 20.0
    assert plan["max_loss_amount"] == pytest.approx(500.0)
    assert plan["sizing_method"] == "atr_risk"

    service = _service(db, size=10000.0)
    buy = service.apply_signal(_signal(101, "buy"), price=250.0, trade_date=date(2026, 11, 2))
    assert buy["quantity"] == 20.0
    assert buy["stop_loss"] == pytest.approx(225.0)
    assert buy["take_profit"] == pytest.approx(287.5)

    # Next trading day drops to low=222.0 (breaches stop_loss=225.0) -> auto stop_loss fill at 225.0.
    with db.session_scope() as session:
        session.add(
            StockDaily(
                code="THYAO.IS",
                date=date(2026, 11, 3),
                open=240.0,
                high=242.0,
                low=222.0,
                close=224.0,
                volume=1_500_000,
            )
        )

    summary = service.get_summary()
    assert summary["open_position_count"] == 0
    assert summary["closed_trade_count"] == 1
    assert summary["stop_loss_count"] == 1
    assert summary["take_profit_count"] == 0
    assert summary["totals_by_currency"]["TRY"]["realized_pnl"] == pytest.approx(-500.0)

    # Now open a second position with explicit signal stop_loss / target_price on ASELS.IS.
    sig2 = _signal(102, "buy", code="ASELS.IS")
    sig2["stop_loss"] = 95.0
    sig2["target_price"] = 115.0
    buy2 = service.apply_signal(sig2, price=100.0, trade_date=date(2026, 11, 4))
    # Risk budget = 500 TRY, per-share risk = 5 TRY -> min(100, 100) = 100 shares
    assert buy2["quantity"] == 100.0
    assert buy2["stop_loss"] == pytest.approx(95.0)
    assert buy2["take_profit"] == pytest.approx(115.0)

    # Next day rallies to high=118.0 (hits take_profit=115.0) -> auto take_profit fill at 115.0.
    with db.session_scope() as session:
        session.add(
            StockDaily(
                code="ASELS.IS",
                date=date(2026, 11, 5),
                open=105.0,
                high=118.0,
                low=104.0,
                close=116.0,
                volume=2_000_000,
            )
        )

    summary2 = service.get_summary()
    assert summary2["open_position_count"] == 0
    assert summary2["closed_trade_count"] == 2
    assert summary2["stop_loss_count"] == 1
    assert summary2["take_profit_count"] == 1
    # -500 + (115 - 100)*100 = +1000 TRY net realized P&L
    assert summary2["totals_by_currency"]["TRY"]["realized_pnl"] == pytest.approx(1000.0)
    report_text = format_paper_trading_report(summary2)
    assert "ZK/KA: 1/1" in report_text

