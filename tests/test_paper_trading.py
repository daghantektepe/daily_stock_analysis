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
    saved_paper_env = {
        k: os.environ.pop(k)
        for k in list(os.environ.keys())
        if k.startswith(("PAPER_TRADING_", "ALPACA_"))
    }
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
        for k in list(os.environ.keys()):
            if k.startswith(("PAPER_TRADING_", "ALPACA_")):
                os.environ.pop(k, None)
        os.environ.update(saved_paper_env)
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


def test_paper_trading_costs_and_time_stop(db) -> None:
    service = PaperTradingService(
        db,
        enabled=True,
        position_size=10_000.0,
        risk_pct=5.0,
        commission_bps=10.0,
        slippage_bps=10.0,
        max_holding_days=5,
    )
    buy = service.apply_signal(
        _signal(201, "buy", code="AAPL", market="us"),
        price=100.0,
        trade_date=date(2026, 11, 2),
    )
    assert buy is not None
    # 20 bps total cost on entry -> fill price = 100 * 1.002 = 100.20
    assert buy["price"] == pytest.approx(100.20)

    # Bar 6 days later triggers time_stop even without stop_loss/take_profit breach
    with db.session_scope() as session:
        session.add(
            StockDaily(
                code="AAPL",
                date=date(2026, 11, 9),
                open=102.0,
                high=103.0,
                low=101.0,
                close=102.0,
                volume=1_000_000,
            )
        )
    exits = service.check_stops_and_targets()
    assert len(exits) == 1
    assert exits[0]["action"] == "time_stop"
    # 20 bps exit cost -> 102 * 0.998 = 101.796
    assert exits[0]["price"] == pytest.approx(101.796)




def _add_signal(db, code: str, session_date: str, action: str = "buy", *, market: str = "tr") -> int:
    import json
    import uuid

    from src.storage import DecisionSignalRecord

    with db.session_scope() as session:
        row = DecisionSignalRecord(
            stock_code=code,
            stock_name=code,
            market=market,
            source_type="analysis",
            source_report_id=900,
            trace_id=f"trace-{code}-{action}-{session_date}-{uuid.uuid4().hex[:8]}",
            market_phase="postmarket",
            trigger_source="cli",
            action=action,
            action_label=action,
            horizon="3d",
            reason="test",
            data_quality_summary_json='{"level": "good"}',
            metadata_json=json.dumps({"market_phase_summary": {"session_date": session_date}}),
            plan_quality="complete",
            status="active",
        )
        session.add(row)
        session.flush()
        return int(row.id)


def test_outcomes_refill_missing_daily_bars_for_stock_analysed_once(db) -> None:
    """A stock analysed once has no stored forward closes; the report path must fetch them."""
    from datetime import timedelta

    from src.services.paper_trading_benchmark import evaluate_signal_outcomes

    _add_signal(db, "ASELS.IS", "2026-11-03", action="buy")
    calls = []

    def filler(*, code, start_date, end_date):
        calls.append((code, start_date, end_date))
        for offset in range(0, 16):
            _add_close(db, code, date(2026, 11, 3) + timedelta(days=offset), 100.0 + 3.0 * offset)
        return 16

    outcomes = evaluate_signal_outcomes(market="tr", db_manager=db, bar_filler=filler)
    assert outcomes["completed"] == 4 and outcomes["hit"] == 4  # 1d/3d/5d/10d all scored
    assert len(calls) == 1  # one fetch per (stock, signal day), not per horizon
    code, start, end = calls[0]
    assert code == "ASELS.IS" and start == date(2026, 10, 27) and end > date(2026, 11, 13)


def test_outcomes_without_refill_stay_unscored_and_report_explains_why(db) -> None:
    from src.services.paper_trading_benchmark import evaluate_signal_outcomes, format_paper_trading_report

    _add_signal(db, "ASELS.IS", "2026-11-03", action="buy")
    _add_signal(db, "THYAO.IS", "2026-11-03", action="watch")
    outcomes = evaluate_signal_outcomes(market="tr", db_manager=db, refill_missing_bars=False)
    assert outcomes["completed"] == 0
    assert outcomes["unable_reasons"]["missing_anchor_price"] == 4

    text = format_paper_trading_report(_service(db).get_summary(), outcome_stats=outcomes)
    assert "bekleyen kontrol" not in text  # the old message called unscorable checks "pending"
    assert "kontrolün hiçbiri henüz sonuçlanmadı" in text
    assert "değerlendirilemedi (sinyal günü fiyatı yok 4" in text


def test_refill_failure_is_fail_open_and_retried_next_run(db) -> None:
    from src.services.paper_trading_benchmark import evaluate_signal_outcomes

    _add_signal(db, "ASELS.IS", "2026-11-03", action="buy")

    def broken(**_kwargs):
        raise RuntimeError("provider down")

    first = evaluate_signal_outcomes(market="tr", db_manager=db, bar_filler=broken)
    assert first["completed"] == 0 and first["unable_reasons"]["missing_anchor_price"] == 4

    def working(*, code, start_date, end_date):
        from datetime import timedelta

        for offset in range(0, 16):
            _add_close(db, code, date(2026, 11, 3) + timedelta(days=offset), 100.0 - 3.0 * offset)
        return 16

    second = evaluate_signal_outcomes(market="tr", db_manager=db, bar_filler=working)
    assert second["completed"] == 4 and second["miss"] == 4  # retryable reasons are re-evaluated


def test_refill_skipped_until_horizon_can_have_elapsed(db) -> None:
    from src.services.decision_signal_outcome_service import DecisionSignalOutcomeService

    _add_signal(db, "ASELS.IS", "2026-11-03", action="buy")
    calls = []
    service = DecisionSignalOutcomeService(
        db_manager=db,
        bar_filler=lambda **kw: calls.append(kw) or 0,
        today=date(2026, 11, 3),  # same day as the signal: nothing can have closed yet
    )
    service.run_outcomes(market="tr", limit=10)
    assert calls == []


def test_service_default_stays_offline(db) -> None:
    from src.services.decision_signal_outcome_service import DecisionSignalOutcomeService

    assert DecisionSignalOutcomeService(db_manager=db)._bar_filler is None
    assert DecisionSignalOutcomeService(db_manager=db, refill_missing_bars=True)._bar_filler is not None


def test_low_sample_hit_rate_is_flagged() -> None:
    from src.services.paper_trading_benchmark import _format_signal_outcomes_section

    lines = _format_signal_outcomes_section(
        {"completed": 6, "total": 10, "hit": 4, "miss": 2, "neutral": 0, "hit_rate_pct": 66.7,
         "avg_stock_return_pct": 1.2, "unable_reasons": {"insufficient_forward_bars": 3, "non_directional_action": 1}}
    )
    text = "\n".join(lines)
    assert "yönlü sonuç sayısı 6 (< 30)" in text
    assert "3 ileri kapanış bekliyor" in text and "1 değerlendirilemedi (yönsüz sinyal (izle) 1)" in text


def test_signal_details_show_action_mix_weekday_and_stored_closes(db) -> None:
    from datetime import timedelta

    from src.services.paper_trading_benchmark import describe_signal_outcome_details, evaluate_signal_outcomes

    _add_signal(db, "ASELS.IS", "2026-11-03", action="buy")
    _add_signal(db, "THYAO.IS", "2026-11-03", action="watch")
    _add_signal(db, "THYAO.IS", "2026-11-08", action="sell")  # a Sunday: no close can exist that day
    for offset in range(0, 4):
        _add_close(db, "ASELS.IS", date(2026, 11, 3) + timedelta(days=offset), 100.0 + 3.0 * offset)
    evaluate_signal_outcomes(market="tr", db_manager=db, refill_missing_bars=False)

    lines = describe_signal_outcome_details(market="tr", db_manager=db)
    text = "\n".join(lines)
    assert lines[0].startswith("Sinyal dağılımı:") and "izle 1" in lines[0] and "al 1" in lines[0]
    assert "ASELS.IS al · sinyal günü 2026-11-03 (Sal) · o günün fiyatı var · ileri kapanış 3/10" in text
    assert "1d isabet" in text and "10d ileri kapanış bekleniyor" in text
    assert "THYAO.IS sat · sinyal günü 2026-11-08 (Paz) · o günün fiyatı YOK" in text
    assert "THYAO.IS izle" not in text  # non-directional signals are only counted


def test_weekend_signal_uses_friday_close_as_start_price(db) -> None:
    from datetime import timedelta

    from src.services.paper_trading_benchmark import evaluate_signal_outcomes

    _add_signal(db, "588200", "2026-11-22", action="buy")  # Sunday, like the real E:\\ case
    _add_close(db, "588200", date(2026, 11, 20), 100.0)  # Friday
    for offset in range(0, 14):  # Monday 23 Nov onward (weekend bars harmless for the test)
        _add_close(db, "588200", date(2026, 11, 23) + timedelta(days=offset), 104.0 + offset)
    outcomes = evaluate_signal_outcomes(market="tr", db_manager=db, refill_missing_bars=False)
    assert outcomes["completed"] == 4 and outcomes["hit"] == 4
    assert "missing_anchor_price" not in outcomes["unable_reasons"]


def test_weekend_signal_without_recent_friday_close_stays_unscored(db) -> None:
    from src.services.paper_trading_benchmark import evaluate_signal_outcomes

    _add_signal(db, "588200", "2026-11-22", action="buy")
    _add_close(db, "588200", date(2026, 11, 13), 100.0)  # 9 days earlier: too stale to stand in
    _add_close(db, "588200", date(2026, 11, 23), 104.0)
    outcomes = evaluate_signal_outcomes(market="tr", db_manager=db, refill_missing_bars=False)
    assert outcomes["completed"] == 0 and outcomes["unable_reasons"]["missing_anchor_price"] == 4


def test_repeated_same_day_signals_are_counted_once(db) -> None:
    from datetime import timedelta

    from src.services.paper_trading_benchmark import evaluate_signal_outcomes, format_paper_trading_report

    for _ in range(3):  # analysis run three times on the same day
        _add_signal(db, "URI", "2026-11-03", action="reduce")
    _add_signal(db, "AMD", "2026-11-03", action="reduce")
    for code in ("URI", "AMD"):
        for offset in range(0, 16):
            _add_close(db, code, date(2026, 11, 3) + timedelta(days=offset), 100.0 - 3.0 * offset)
    outcomes = evaluate_signal_outcomes(market="tr", db_manager=db, refill_missing_bars=False)
    assert outcomes["completed"] == 8  # 2 distinct stocks x 4 horizons, not 4 x 4
    assert outcomes["duplicate_checks_merged"] == 8
    text = format_paper_trading_report(_service(db).get_summary(), outcome_stats=outcomes)
    assert "Aynı gün tekrarlanan sinyaller tek sayıldı (8 kontrol birleştirildi)" in text


def test_signal_benchmark_comparison_buy_sell_weekend_and_dedupe(db) -> None:
    from datetime import timedelta

    from src.services.paper_trading_benchmark import evaluate_signal_outcomes, format_paper_trading_report

    # Weekend Sunday buy in TR: Friday anchor (Nov 6) close = 100 -> 10th trading bar (Nov 16) close = 115 (+15%)
    _add_signal(db, "THYAO.IS", "2026-11-08", action="buy", market="tr")
    _add_close(db, "THYAO.IS", date(2026, 11, 6), 100.0)
    for offset in range(1, 12):
        _add_close(db, "THYAO.IS", date(2026, 11, 8) + timedelta(days=offset), 100.0 + offset * (15.0 / 10.0))

    # Duplicate US sell signals on Nov 2 (Monday): AAPL drops -8% over 10 bars while SPY rises +5% -> beat (excess = -13%)
    _add_signal(db, "AAPL", "2026-11-02", action="reduce", market="us")
    _add_signal(db, "AAPL", "2026-11-02", action="sell", market="us")
    for offset in range(0, 12):
        _add_close(db, "AAPL", date(2026, 11, 2) + timedelta(days=offset), 100.0 - offset * 0.8)

    idx_prices = {
        "XU100.IS": {
            date(2026, 11, 6): 10000.0,   # Friday close before Nov 8 Sunday
            date(2026, 11, 18): 10500.0,  # 10th forward bar after Nov 8 -> +5% index gain (THYAO +15% -> +10% excess)
        },
        "SPY": {
            date(2026, 11, 2): 500.0,
            date(2026, 11, 12): 525.0,    # 10th forward bar after Nov 2 -> +5% SPY gain (AAPL -8% -> -13% excess)
        },
    }

    def fake_hist(symbol, start, end):
        return {d: v for d, v in idx_prices.get(symbol, {}).items() if start <= d <= end}

    outcomes = evaluate_signal_outcomes(db_manager=db, refill_missing_bars=False, history_provider=fake_hist)
    bench = outcomes["benchmark_comparison"]
    assert bench["groups"]["buy"]["n"] == 1
    assert bench["groups"]["buy"]["beat_rate_pct"] == 100.0
    assert bench["groups"]["buy"]["avg_excess_pct"] == pytest.approx(10.0, abs=0.1)
    assert bench["groups"]["buy"]["sample_sufficient"] is False
    assert bench["groups"]["sell"]["n"] == 1  # repeated Nov 2 signals counted once
    assert bench["groups"]["sell"]["beat_rate_pct"] == 100.0
    assert bench["groups"]["sell"]["avg_excess_pct"] == pytest.approx(-13.0, abs=0.1)

    report = format_paper_trading_report(_service(db).get_summary(), outcome_stats=outcomes)
    assert "Endekse göre: al sinyallerinin %100'i 10 günde endeksi geçti (n=1, ort. fark +10.00%, örnek yetersiz)" in report
    assert "Endekse göre: azalt/sat sinyallerinin %100'i 10 günde endeksi geçti (n=1, ort. fark -13.00%, örnek yetersiz)" in report


def test_signal_benchmark_comparison_unknown_market_reports_no_index(db) -> None:
    from datetime import timedelta

    from src.services.paper_trading_benchmark import evaluate_signal_outcomes, format_paper_trading_report

    _add_signal(db, "588200", "2026-11-02", action="buy", market="cn")
    for offset in range(0, 12):
        _add_close(db, "588200", date(2026, 11, 2) + timedelta(days=offset), 1.0 + 0.01 * offset)

    outcomes = evaluate_signal_outcomes(db_manager=db, refill_missing_bars=False, history_provider=lambda *_: {})
    bench = outcomes["benchmark_comparison"]
    assert bench["no_benchmark_count"] == 1
    assert bench["no_benchmark_markets"] == ["cn"]
    report = format_paper_trading_report(_service(db).get_summary(), outcome_stats=outcomes)
    assert "Endekse göre: cn pazarı için endeks yok (n=1)" in report


def test_signal_benchmark_comparison_bootstrap_ci90_when_sample_reaches_30(db) -> None:
    from datetime import timedelta

    from src.services.paper_trading_benchmark import evaluate_signal_outcomes, format_paper_trading_report

    base = date(2026, 9, 1)
    idx_closes = {}
    for day_offset in range(0, 80):
        idx_closes[base + timedelta(days=day_offset)] = 500.0  # flat index (+0%)

    # 30 distinct stock signals -> 20 beat (+10%), 10 lag (-5%)
    for i in range(30):
        code = f"STK{i:02d}"
        sig_day = base + timedelta(days=i)
        _add_signal(db, code, sig_day.isoformat(), action="buy", market="us")
        _add_close(db, code, sig_day, 100.0)
        end_px = 110.0 if i < 20 else 95.0
        for fwd in range(1, 11):
            _add_close(db, code, sig_day + timedelta(days=fwd), 100.0 + (end_px - 100.0) * fwd / 10.0)

    outcomes = evaluate_signal_outcomes(
        db_manager=db,
        refill_missing_bars=False,
        history_provider=lambda sym, start, end: (
            {d: c for d, c in idx_closes.items() if start <= d <= end} if sym == "SPY" else {}
        ),
    )
    buy_stats = outcomes["benchmark_comparison"]["groups"]["buy"]
    assert buy_stats["n"] == 30
    assert buy_stats["sample_sufficient"] is True
    assert buy_stats["beat_rate_pct"] == pytest.approx(66.67, abs=0.1)
    assert buy_stats["beat_rate_ci90_pct"] is not None
    low, high = buy_stats["beat_rate_ci90_pct"]
    assert 40.0 <= low <= buy_stats["beat_rate_pct"] <= high <= 90.0

    report = format_paper_trading_report(_service(db).get_summary(), outcome_stats=outcomes)
    assert "Endekse göre: al sinyallerinin %67'i 10 günde endeksi geçti (n=30, ort. fark +5.00%, %90 GA" in report
    assert "örnek yetersiz" not in report


def test_weekly_watch_ratio_and_four_week_over_70_alert(db, tmp_path) -> None:
    from datetime import datetime, timedelta, timezone

    from src.services.paper_trading_benchmark import (
        evaluate_weekly_watch_ratio,
        maybe_send_weekly_performance_report,
    )
    from src.storage import DecisionSignalRecord

    now = datetime(2026, 11, 20, 16, 0, tzinfo=timezone.utc)  # Friday 19:00 Istanbul
    created = now.replace(tzinfo=None) - timedelta(days=1)
    with db.session_scope() as session:
        for idx, action in enumerate(["watch", "watch", "watch", "watch", "buy"]):
            session.add(
                DecisionSignalRecord(
                    stock_code=f"W{idx}.IS",
                    stock_name=f"W{idx}",
                    market="tr",
                    source_type="analysis",
                    source_report_id=100 + idx,
                    trace_id=f"trace-watch-{idx}",
                    market_phase="postmarket",
                    trigger_source="cli",
                    action=action,
                    action_label=action,
                    horizon="3d",
                    reason="test",
                    plan_quality="complete",
                    status="active",
                    created_at=created,
                )
            )

    prior = [
        {"week": "2026-W44", "total": 10, "watch": 8, "watch_pct": 80.0},
        {"week": "2026-W45", "total": 10, "watch": 8, "watch_pct": 80.0},
        {"week": "2026-W46", "total": 10, "watch": 8, "watch_pct": 80.0},
    ]
    state_file = tmp_path / "weekly_watch_state.json"
    import json

    state_file.write_text(json.dumps({"watch_history": prior}), encoding="utf-8")

    watch_res = evaluate_weekly_watch_ratio(
        db_manager=db,
        market="tr",
        now=now,
        state_history=prior,
        current_week="2026-W47",
    )
    assert watch_res["total"] == 5 and watch_res["watch"] == 4
    assert watch_res["watch_pct"] == pytest.approx(80.0)
    assert "Bu hafta: 5 sinyal, %80'si izle" == watch_res["line"]
    assert watch_res["alert_four_weeks_over_70"] is True
    assert "onayınız gerekir" in watch_res["alert_line"]

    sent = []

    class _FakeNotifier:
        def send(self, text, **_kwargs):
            sent.append(text)
            return True

    assert (
        maybe_send_weekly_performance_report(
            notifier=_FakeNotifier(),
            db_manager=db,
            state_path=state_file,
            now=now,
            market="tr",
            history=_fake_history,
        )
        is True
    )
    assert "Bu hafta: 5 sinyal, %80'si izle" in sent[0]
    assert "4 hafta üst üste %70'in üzerinde" in sent[0]
    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert len(saved_state["watch_history"]) == 4


def test_signal_details_and_weekly_watch_dedupe_same_day_repeats_and_1d_benchmark_preview(db) -> None:
    from datetime import datetime, timedelta, timezone

    from src.services.paper_trading_benchmark import (
        describe_signal_outcome_details,
        evaluate_signal_outcomes,
        evaluate_weekly_watch_ratio,
        format_paper_trading_report,
    )
    from src.storage import DecisionSignalRecord

    # 3 repeated same-day reduce signals for URI and 3 repeated same-day watch signals for AAPL on 2026-11-20
    created = datetime(2026, 11, 20, 14, 0)
    with db.session_scope() as session:
        for idx in range(3):
            session.add(
                DecisionSignalRecord(
                    stock_code="URI",
                    stock_name="URI",
                    market="us",
                    source_type="analysis",
                    source_report_id=200 + idx,
                    trace_id=f"trace-uri-{idx}",
                    market_phase="postmarket",
                    trigger_source="cli",
                    action="reduce",
                    action_label="azalt",
                    horizon="3d",
                    reason="test",
                    plan_quality="complete",
                    status="active",
                    created_at=created + timedelta(minutes=idx),
                )
            )
            session.add(
                DecisionSignalRecord(
                    stock_code="AAPL",
                    stock_name="AAPL",
                    market="us",
                    source_type="analysis",
                    source_report_id=300 + idx,
                    trace_id=f"trace-aapl-{idx}",
                    market_phase="postmarket",
                    trigger_source="cli",
                    action="watch",
                    action_label="izle",
                    horizon="3d",
                    reason="test",
                    plan_quality="complete",
                    status="active",
                    created_at=created + timedelta(minutes=idx),
                )
            )

    # Only 1 forward bar available (2026-11-23), so 1d completes while 3d/5d/10d are still waiting
    _add_close(db, "URI", date(2026, 11, 20), 100.0)
    _add_close(db, "URI", date(2026, 11, 23), 97.0)  # -3% on 1d
    spy_closes = {
        date(2026, 11, 20): 500.0,
        date(2026, 11, 23): 505.0,  # +1% on 1d -> sell beat (excess = -4%)
    }

    outcomes = evaluate_signal_outcomes(
        db_manager=db,
        refill_missing_bars=False,
        history_provider=lambda sym, start, end: (
            {d: c for d, c in spy_closes.items() if start <= d <= end} if sym == "SPY" else {}
        ),
    )
    report = format_paper_trading_report(_service(db).get_summary(), outcome_stats=outcomes)
    assert (
        "Endekse göre (10g henüz dolmadı · 1g ön izleme): azalt/sat sinyallerinin %100'i 1g ufukta endeksi geçti "
        "(n=1, ort. fark -4.00%, örnek yetersiz)"
    ) in report

    details = describe_signal_outcome_details(db_manager=db)
    assert "aynı gün tekrarlanan 4 kayıt birleştirildi" in details[0]
    uri_lines = [line for line in details if "URI azalt" in line]
    assert len(uri_lines) == 1
    assert "(aynı gün ×3 tekrar)" in uri_lines[0]

    watch_res = evaluate_weekly_watch_ratio(
        db_manager=db,
        now=datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc),
    )
    assert watch_res["total"] == 2 and watch_res["watch"] == 1
    assert watch_res["watch_pct"] == pytest.approx(50.0)
