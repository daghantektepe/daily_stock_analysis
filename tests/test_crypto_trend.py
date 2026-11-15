# -*- coding: utf-8 -*-
"""Crypto trend strategy: sleeve rule, backtest, signal and paper book (offline)."""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.services.crypto_trend_strategy import (
    Sleeve,
    TrendConfig,
    current_targets,
    robustness_grid,
    run_backtest,
    trend_flags,
)
from src.services.strategy_paper_book import StrategyPaperBook, format_book_report


def _prices(days: int = 400) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=days, freq="D")
    t = np.arange(days)
    # Rally, crash, recovery: the trend rule should sit out most of the crash.
    btc = np.concatenate([np.linspace(100, 300, 150), np.linspace(300, 90, 120), np.linspace(90, 200, days - 270)])
    eth = btc * (1 + 0.05 * np.sin(t / 10))
    return pd.DataFrame({"BTC-USD": btc, "ETH-USD": eth}, index=index)


def test_sleeve_trades_only_on_flips_and_charges_costs() -> None:
    sleeve = Sleeve(asset="BTC-USD", cash=1000.0)
    assert sleeve.step(date(2024, 1, 1), 100.0, True, 1.0)["side"] == "buy"
    assert sleeve.units == pytest.approx(9.9)
    assert sleeve.step(date(2024, 1, 2), 110.0, True, 1.0) is None  # no flip, no trade
    assert sleeve.step(date(2024, 1, 3), 120.0, False, 1.0)["side"] == "sell"
    assert sleeve.cash == pytest.approx(9.9 * 120 * 0.99)


def test_trend_flags_use_only_past_data() -> None:
    closes = pd.Series([1.0, 2.0, 3.0, 2.0, 1.0])
    assert trend_flags(closes, 3).tolist() == [False, False, True, False, False]


def test_backtest_beats_buy_and_hold_drawdown_in_a_crash() -> None:
    result = run_backtest(_prices(), TrendConfig(sma_windows=(20, 40), cost_pct=0.15))
    assert result["strategy"]["max_drawdown_pct"] > result["buy_hold"]["max_drawdown_pct"]
    assert result["trade_count"] > 0 and 0 < result["exposure_pct"] < 100
    assert result["start"] == "2024-02-10"  # waits for the longest average
    assert {"year", "strategy_pct", "buy_hold_pct"} <= set(result["yearly"][0])
    grid = robustness_grid(_prices(), (20, 40), cost_pct=0.15)
    assert [row["label"] for row in grid] == ["SMA20", "SMA40", "topluluk"]
    assert len({row["start"] for row in grid}) == 1  # same window for every row


def test_current_targets_weight_is_share_of_averages_above() -> None:
    prices = _prices()
    # Price falls at the end: above the 300-day average, below the 5-day one.
    prices.iloc[-3:, prices.columns.get_loc("BTC-USD")] = [260.0, 230.0, 205.0]
    targets = current_targets(prices, TrendConfig(sma_windows=(5, 300)))
    btc = targets["BTC-USD"]
    expected = [n for n in (5, 300) if prices["BTC-USD"].iloc[-1] > prices["BTC-USD"].rolling(n).mean().iloc[-1]]
    assert btc["date"] == "2025-02-03"
    assert btc["above"] == expected == [300] and btc["weight"] == 0.5
    short = current_targets(prices.iloc[:50], TrendConfig(sma_windows=(10, 300)))
    assert short["BTC-USD"]["reason"] == "insufficient_history"


def test_paper_book_steps_forward_idempotently_and_matches_backtest(tmp_path) -> None:
    prices = _prices()
    config = TrendConfig(sma_windows=(20, 40), cost_pct=0.15)
    book = StrategyPaperBook(config=config, book_dir=tmp_path)
    first = book.step(prices.iloc[:100], today=date(2024, 4, 10))
    assert first["processed_days"] == 1  # starts on the last available close
    assert book.state["start_date"] == "2024-04-09"

    step = book.step(prices, today=date(2025, 2, 4))
    assert step["processed_days"] == 300
    again = book.step(prices, today=date(2025, 2, 4))
    assert again["processed_days"] == 0  # same closes are never applied twice

    reloaded = StrategyPaperBook(config=config, book_dir=tmp_path)
    summary = reloaded.summary()
    assert summary["days"] == 301 and summary["trade_count"] == len(book.state["trades"])
    # Same rule as the backtest over the same window.
    backtest = run_backtest(prices, config, start=date(2024, 4, 9))
    assert summary["nav"] == pytest.approx(float(backtest["equity"].iloc[-1]), rel=1e-6)
    assert summary["late_days"] == 299  # caught up long after the fact
    text = format_book_report(summary, current_targets(prices, config))
    assert "Kripto trend sanal portföyü" in text and "gerçek emir verilmez" in text
    json.loads((tmp_path / "crypto_trend.json").read_text(encoding="utf-8"))


def test_weekly_report_includes_crypto_book(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    from src.services import paper_trading_benchmark as weekly

    config = TrendConfig(sma_windows=(20, 40))
    book = StrategyPaperBook(config=config, book_dir=tmp_path)
    book.step(_prices(), today=date(2025, 2, 4))
    monkeypatch.setattr("src.services.strategy_paper_book.DEFAULT_BOOK_DIR", tmp_path)
    monkeypatch.setattr("src.config.get_config", lambda: SimpleNamespace(
        crypto_trend_enabled=True, crypto_trend_assets=["BTC-USD", "ETH-USD"], crypto_trend_capital=10000.0))
    monkeypatch.setattr("src.services.crypto_trend_strategy.TrendConfig",
                        lambda assets: TrendConfig(assets=assets, sma_windows=(20, 40)))
    text = weekly._crypto_trend_weekly_text()
    assert text.startswith("🪙 Kripto trend sanal portföyü")
    monkeypatch.setattr("src.config.get_config", lambda: SimpleNamespace(crypto_trend_enabled=False))
    assert weekly._crypto_trend_weekly_text() == ""
