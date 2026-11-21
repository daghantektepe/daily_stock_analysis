# -*- coding: utf-8 -*-
"""Tests for PAA & Meta-Portfolio A StrategyPaperBook daily automation, weekly report, and MCP."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.mcp.server import DsaMcpServer
from src.quant.paper_book import (
    get_quant_paper_books_status,
    normalize_quant_paper_strategies,
    step_quant_paper_books,
)
from src.quant.strategies.library import compute_meta_a_weights, compute_paa_weights
from src.services.strategy_paper_book import QuantAllocationPaperBook, format_quant_book_report


def _synthetic_us_etf_prices(n_days: int = 330, *, start: str = "2024-01-02", crash_tail: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(123)
    dates = pd.bdate_range(start, periods=n_days)
    risk_cols = ["SPY", "QQQ", "IWM", "VGK", "EWJ", "EEM", "VNQ", "GLD", "DBC", "HYG", "LQD", "TLT"]
    safe_cols = ["IEF", "SHY", "BIL"]
    data = {}
    for idx, col in enumerate(risk_cols):
        drift = 0.0006 + (idx % 3) * 0.0001
        rets = rng.normal(drift, 0.01, size=n_days)
        if crash_tail:
            rets[-40:] = -0.015
        data[col] = 100.0 * np.cumprod(1.0 + rets)
    for col in safe_cols:
        rets = rng.normal(0.00018, 0.0012, size=n_days)
        data[col] = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame(data, index=dates)


def test_quant_paper_book_initial_deploy_idempotency_and_cost_deduction(tmp_path: Path) -> None:
    prices = _synthetic_us_etf_prices(300, crash_tail=True)
    res1 = step_quant_paper_books(
        strategies=["paa", "meta_a"],
        initial_capital=10_000.0,
        cost_bps=5.0,
        rebalance_mode="monthly",
        prices=prices,
        book_dir=tmp_path,
        today=prices.index[-1].date(),
    )
    assert res1["ok"] is True
    assert len(res1["books"]) == 2
    assert (tmp_path / "quant_paa.json").is_file()
    assert (tmp_path / "quant_meta_a.json").is_file()

    paa_book = next(b for b in res1["books"] if b["strategy_key"] == "paa")
    meta_book = next(b for b in res1["books"] if b["strategy_key"] == "meta_a")

    # Under crash_tail, PAA deploys 100% into defensive bond/cash ETF (IEF or SHY) with 5 bps cost
    assert paa_book["days"] == 1
    assert paa_book["trade_count"] >= 1
    assert paa_book["nav"] < 10_000.0
    assert paa_book["nav"] > 9_990.0
    assert paa_book["cash"] >= 0.0
    assert set(paa_book["weights_pct"].keys()).issubset({"BIL", "IEF", "SHY", "GLD"})

    # Meta-Portfolio A blends PAA + VAA + GTAA-5 + Risk Parity across multiple ETFs
    assert meta_book["days"] == 1
    assert len(meta_book["positions"]) >= 2
    assert meta_book["cash"] >= 0.0

    # Second step on the exact same latest close must be strictly idempotent
    res2 = step_quant_paper_books(
        strategies=["paa", "meta_a"],
        initial_capital=10_000.0,
        cost_bps=5.0,
        rebalance_mode="monthly",
        prices=prices,
        book_dir=tmp_path,
        today=prices.index[-1].date(),
    )
    assert res2["total_new_trades"] == 0
    for b in res2["books"]:
        assert b["processed_days"] == 0
        assert b["days"] == 1


def test_quant_paper_book_advances_daily_and_rebalances_on_new_month(tmp_path: Path) -> None:
    prices_full = _synthetic_us_etf_prices(340, start="2024-01-02", crash_tail=False)
    # Start on a mid-month bar, then advance across a calendar month boundary into crash regime
    start_idx = 290
    prices_day1 = prices_full.iloc[: start_idx + 1].copy()

    book = QuantAllocationPaperBook(
        name="quant_paa",
        strategy_key="paa",
        initial_capital=10_000.0,
        cost_bps=5.0,
        rebalance_mode="monthly",
        book_dir=tmp_path,
    )
    step1 = book.step(prices_day1, compute_paa_weights, today=prices_day1.index[-1].date())
    assert step1["processed_days"] == 1
    assert len(step1["new_trades"]) >= 1
    day1_trades = len(book.state["trades"])

    # Create a severe crash after start_idx crossing into the next month
    prices_next = prices_full.iloc[: start_idx + 30].copy()
    for col in ("SPY", "QQQ", "IWM", "VGK", "EWJ", "EEM", "VNQ", "GLD", "DBC", "HYG", "LQD", "TLT"):
        prices_next.iloc[start_idx + 1 :, prices_next.columns.get_loc(col)] *= 0.55

    step2 = book.step(prices_next, compute_paa_weights, today=prices_next.index[-1].date())
    assert step2["processed_days"] == 29
    # Monthly boundary must have triggered defensive shift trades into SHY/IEF
    assert len(book.state["trades"]) > day1_trades
    summary = book.summary()
    assert summary["days"] == 30
    assert set(summary["weights_pct"].keys()).issubset({"BIL", "IEF", "SHY", "GLD"})
    # Caught-up days older than 3 calendar days are marked late
    assert summary["late_days"] > 0
    report = format_quant_book_report(summary)
    assert "PAA Çöküş Kalkanı" in report
    assert "Sanal işlemdir" in report


def test_quant_paper_book_zero_lookahead_when_future_bars_change(tmp_path: Path) -> None:
    prices_a = _synthetic_us_etf_prices(315)
    prices_b = prices_a.copy()
    cut = 295
    # Perturb strictly future prices after cut
    prices_b.iloc[cut + 1 :] = prices_b.iloc[cut + 1 :] * 4.0

    book_a = QuantAllocationPaperBook(name="meta_a_1", strategy_key="meta_a", book_dir=tmp_path)
    book_b = QuantAllocationPaperBook(name="meta_a_2", strategy_key="meta_a", book_dir=tmp_path)

    book_a.step(prices_a.iloc[: cut + 1], compute_meta_a_weights, today=prices_a.index[cut].date())
    book_b.step(prices_b.iloc[: cut + 1], compute_meta_a_weights, today=prices_b.index[cut].date())
    assert book_a.summary()["nav"] == book_b.summary()["nav"]
    assert book_a.summary()["weights_pct"] == book_b.summary()["weights_pct"]

    # Advancing further cannot rewrite past history entries
    book_a.step(prices_a, compute_meta_a_weights, today=prices_a.index[-1].date())
    book_b.step(prices_b, compute_meta_a_weights, today=prices_b.index[-1].date())
    assert book_a.state["history"][0] == book_b.state["history"][0]


def test_quant_paper_helpers_status_and_mcp_exposure(tmp_path: Path) -> None:
    assert normalize_quant_paper_strategies(["all"]) == ["paa", "meta_a"]
    assert normalize_quant_paper_strategies(["invalid"]) == ["paa", "meta_a"]

    empty_status = get_quant_paper_books_status(strategies=["paa", "meta_a"], book_dir=tmp_path)
    assert empty_status["ok"] is True
    assert all(b["days"] == 0 for b in empty_status["books"])

    server = DsaMcpServer()
    assert "dsa_get_quant_paper_books" in set(server.tool_names)
    assert len(server.tool_names) >= 16
    res = server.call_tool("dsa_get_quant_paper_books", {"step_paper": False})
    assert res["isError"] is False
    body = json.loads(res["content"][0]["text"])
    assert body["ok"] is True
    assert body["data"]["simulated_only"] is True


def test_weekly_report_includes_quant_paper_books(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace
    from src.services import paper_trading_benchmark as ptb

    prices = _synthetic_us_etf_prices(300, crash_tail=True)
    step_quant_paper_books(
        strategies=["paa", "meta_a"],
        initial_capital=10_000.0,
        prices=prices,
        book_dir=tmp_path,
        today=prices.index[-1].date(),
    )

    fake_cfg = SimpleNamespace(
        quant_paper_enabled=True,
        quant_paper_strategies=["paa", "meta_a"],
        quant_paper_capital=10_000.0,
        quant_paper_cost_bps=5.0,
        quant_paper_rebalance_mode="monthly",
    )
    monkeypatch.setattr("src.config.get_config", lambda: fake_cfg)
    monkeypatch.setattr("src.quant.paper_book.DEFAULT_BOOK_DIR", tmp_path)

    weekly_txt = ptb._quant_paper_weekly_text()
    assert "PAA Çöküş Kalkanı" in weekly_txt
    assert "Meta-Portföy A" in weekly_txt
    assert "Sanal işlemdir" in weekly_txt
