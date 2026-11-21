# -*- coding: utf-8 -*-
"""Forward (live paper) validation: freeze, invalidation, gate verdicts, Alpaca paper slippage."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.quant import forward_validation as fv
from src.quant.forward_validation import (
    STATUS_COLLECTING,
    STATUS_FAIL,
    STATUS_INVALIDATED,
    STATUS_NOT_FROZEN,
    STATUS_PASS,
    STATUS_PASS_PENDING_SLIPPAGE,
    ForwardGate,
    ForwardRegistry,
    evaluate_forward_record,
    format_forward_report,
    plan_alpaca_orders,
    reconcile_paper_fills,
    strategy_fingerprint,
    submit_paper_orders,
)

LIB_CONST = 0.35


def _helper(prices):
    return prices * LIB_CONST


def weight_fn_a(prices):
    return _helper(prices)


def weight_fn_b(prices):
    return prices


def _book(days: int, daily_ret: float = 0.0008, start: date = date(2026, 1, 2), dd_day: int = -1,
          late_every: int = 0) -> dict:
    history, nav, bench = [], 10_000.0, 10_000.0
    day = start
    rng = np.random.default_rng(1)
    for i in range(days + 1):
        if i:
            nav *= 1 + daily_ret + rng.normal(0, 0.004)
            bench *= 1 + 0.0004 + rng.normal(0, 0.008)
            if i == dd_day:
                nav *= 0.75
        history.append({"date": day.isoformat(), "nav": round(nav, 2), "benchmark_nav": round(bench, 2),
                        "late": bool(late_every and i and i % late_every == 0)})
        day += timedelta(days=1)
    return {"strategy_key": "meta_a", "label": "Meta-A", "history": history}


def _frozen(fp: dict, day: date = date(2026, 1, 2)) -> dict:
    return {"strategy_key": "meta_a", "frozen_date": day.isoformat(), "fingerprint": fp}


def _fills(n: int, bps: float) -> list:
    return [{"strategy_key": "meta_a", "status": "filled", "slippage_bps": bps, "filled_notional": 1000.0}
            for _ in range(n)]


def test_fingerprint_follows_the_code_path_and_settings() -> None:
    settings = {"cost_bps": 5.0}
    fp = strategy_fingerprint(weight_fn_a, settings)
    assert fp["functions"] == ["_helper", "weight_fn_a"]
    assert fp["constants"] == ["LIB_CONST"]
    assert strategy_fingerprint(weight_fn_a, settings)["sha256"] == fp["sha256"]
    assert strategy_fingerprint(weight_fn_a, {"cost_bps": 10.0})["sha256"] != fp["sha256"]
    assert strategy_fingerprint(weight_fn_b, settings)["sha256"] != fp["sha256"]


def test_real_meta_a_fingerprint_covers_all_sleeves() -> None:
    from src.quant.strategies.library import compute_meta_a_weights

    fp = strategy_fingerprint(compute_meta_a_weights, {"cost_bps": 5.0})
    assert {"compute_meta_a_weights", "compute_paa_weights"} <= set(fp["functions"])
    assert len(fp["functions"]) >= 4


def test_gate_verdicts() -> None:
    fp = {"sha256": "a" * 64, "functions": ["f"], "settings": {}}
    gate = ForwardGate()
    assert evaluate_forward_record(_book(10), None, fp)["status"] == STATUS_NOT_FROZEN

    collecting = evaluate_forward_record(_book(40), _frozen(fp), fp)
    assert collecting["status"] == STATUS_COLLECTING and collecting["forward_days"] == 40
    assert collecting["excess_sharpe_se"] == pytest.approx((252 / 40) ** 0.5, abs=0.01)

    crashed = evaluate_forward_record(_book(40, dd_day=20), _frozen(fp), fp)
    assert crashed["status"] == STATUS_FAIL and "düşüş" in crashed["reasons"][0]  # fails early

    pending = evaluate_forward_record(_book(130), _frozen(fp), fp, gate=gate)
    assert pending["status"] == STATUS_PASS_PENDING_SLIPPAGE
    assert evaluate_forward_record(_book(130), _frozen(fp), fp, orders=_fills(6, 8.0))["status"] == STATUS_PASS

    costly = evaluate_forward_record(_book(130), _frozen(fp), fp, orders=_fills(6, 35.0))
    assert costly["status"] == STATUS_FAIL and "kayma" in costly["reasons"][0]
    weak = evaluate_forward_record(_book(130, daily_ret=-0.0002), _frozen(fp), fp, orders=_fills(6, 8.0))
    assert weak["status"] == STATUS_FAIL and "Sharpe" in weak["reasons"][0]
    late = evaluate_forward_record(_book(130, late_every=5), _frozen(fp), fp, orders=_fills(6, 8.0))
    assert late["status"] == STATUS_FAIL and "sonradan" in late["reasons"][0]


def test_days_before_freeze_do_not_count_and_code_change_invalidates() -> None:
    fp = {"sha256": "a" * 64, "functions": ["f"], "settings": {}}
    book = _book(130)
    late_freeze = evaluate_forward_record(book, _frozen(fp, date(2026, 4, 1)), fp)
    assert late_freeze["status"] == STATUS_COLLECTING and late_freeze["forward_days"] == 41

    changed = {"sha256": "b" * 64, "functions": ["f", "g"], "settings": {}}
    result = evaluate_forward_record(book, _frozen(fp), changed)
    assert result["status"] == STATUS_INVALIDATED and "g" in result["reasons"][0]
    assert "geçersiz" in format_forward_report([result])


def test_registry_keeps_freeze_unless_reset(tmp_path) -> None:
    reg = ForwardRegistry(tmp_path / "fwd.json")
    fp1 = {"sha256": "1" * 64, "functions": [], "settings": {}}
    fp2 = {"sha256": "2" * 64, "functions": [], "settings": {}}
    reg.freeze("meta_a", fp1, date(2026, 11, 20))
    assert reg.freeze("meta_a", fp2, date(2026, 12, 1))["fingerprint"]["sha256"] == "1" * 64
    entry = ForwardRegistry(tmp_path / "fwd.json").freeze("meta_a", fp2, date(2026, 12, 1), reset=True)
    assert entry["frozen_date"] == "2026-12-01" and entry["previous"][0]["fingerprint"]["sha256"] == "1" * 64


def test_backtest_percentile_flags_forward_underperformance() -> None:
    returns = pd.Series(np.full(500, 0.001), index=pd.bdate_range("2023-01-02", periods=500))
    assert fv.forward_percentile(returns, -5.0, 60) == 0.0
    assert fv.forward_percentile(returns, 50.0, 60) == 100.0
    fp = {"sha256": "a" * 64, "functions": ["f"], "settings": {}}
    bad = evaluate_forward_record(_book(40, daily_ret=-0.002), _frozen(fp), fp, expectation_returns=returns)
    assert bad["backtest_percentile"] == 0.0 and "aşırı uyum" in bad["warnings"][0]


def test_run_forward_validation_freezes_and_evaluates_real_strategies(tmp_path) -> None:
    from src.quant.data_loader import US_ETF_UNIVERSE

    idx = pd.bdate_range("2019-01-02", periods=900)
    rng = np.random.default_rng(3)
    prices = pd.DataFrame({sym: 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, len(idx))) for sym in US_ETF_UNIVERSE},
                          index=idx)
    prices["BIL"] = 100 * np.cumprod(np.full(len(idx), 1.00015))
    registry = ForwardRegistry(tmp_path / "fwd.json")
    results = fv.run_forward_validation(strategies=["meta_a"], prices=prices, registry=registry,
                                        book_dir=tmp_path, today=idx[-1].date())
    assert results[0]["status"] == STATUS_COLLECTING
    entry = registry.get("meta_a")
    assert entry["expectation"]["window_return_pct"]["60"]["p5"] < entry["expectation"]["window_return_pct"]["60"]["p95"]
    assert "_daily_returns" not in entry["expectation"]


class _FakeAlpaca:
    def __init__(self, paper=True):
        self.paper = paper
        self.sent = []

    def submit_order(self, **kwargs):
        self.sent.append(kwargs)
        return {"id": f"ord-{len(self.sent)}"}

    def list_orders(self, status="closed", limit=500):
        return [
            {"client_order_id": self.sent[0]["client_order_id"], "status": "filled", "filled_avg_price": 100.10, "filled_qty": 10},
            {"client_order_id": self.sent[1]["client_order_id"], "status": "filled", "filled_avg_price": 49.95, "filled_qty": 4},
        ]


def test_alpaca_plan_submit_reconcile_paper_only(tmp_path) -> None:
    orders = plan_alpaca_orders(
        {"SPY": 50.0, "GLD": 20.0}, account_equity=100_000.0,
        positions=[{"symbol": "TLT", "qty": 4}, {"symbol": "SPY", "qty": 10}],
        last_prices={"SPY": 100.0, "GLD": 50.0, "TLT": 50.0}, capital=2_000.0,
    )
    assert orders == [
        {"symbol": "TLT", "side": "sell", "qty": 4, "reference_price": 50.0, "notional": 200.0},
        {"symbol": "GLD", "side": "buy", "qty": 8, "reference_price": 50.0, "notional": 400.0},
    ]  # SPY already at target (10 x 100 = 50% of 2,000)

    registry = ForwardRegistry(tmp_path / "fwd.json")
    with pytest.raises(RuntimeError, match="paper"):
        submit_paper_orders(_FakeAlpaca(paper=False), orders, strategy_key="meta_a", registry=registry)

    plan = [{"symbol": "SPY", "side": "buy", "qty": 10, "reference_price": 100.0, "notional": 1000.0},
            {"symbol": "TLT", "side": "sell", "qty": 4, "reference_price": 50.0, "notional": 200.0}]
    client = _FakeAlpaca()
    submit_paper_orders(client, plan, strategy_key="meta_a", registry=registry, today=date(2026, 11, 23))
    submit_paper_orders(client, plan, strategy_key="meta_a", registry=registry, today=date(2026, 11, 23))
    assert len(client.sent) == 2  # same day is never sent twice
    filled = reconcile_paper_fills(client, registry)
    assert [o["slippage_bps"] for o in filled] == [10.0, 10.0]  # paid 0.10% more / sold 0.10% lower
    assert fv.slippage_summary(registry.data["orders"])["fills"] == 2


def test_mcp_exposes_read_only_forward_validation_tool() -> None:
    from src.mcp.tools import build_dsa_mcp_tools

    spec = {tool.name: tool for tool in build_dsa_mcp_tools()}["dsa_get_forward_validation"]
    assert spec.read_only is True


def test_daily_step_reports_forward_gate(tmp_path, monkeypatch) -> None:
    from src.quant import paper_book
    from src.quant.data_loader import US_ETF_UNIVERSE

    monkeypatch.setattr("src.quant.ai_council.step_active_council_books", lambda **_k: [], raising=False)
    idx = pd.bdate_range("2019-01-02", periods=700)
    rng = np.random.default_rng(5)
    prices = pd.DataFrame({sym: 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, len(idx))) for sym in US_ETF_UNIVERSE},
                          index=idx)
    res = paper_book.step_quant_paper_books(strategies=["meta_a"], prices=prices, book_dir=tmp_path,
                                            today=idx[-1].date())
    assert res["ok"] and res["forward_validation"][0]["status"] == STATUS_COLLECTING
    assert "İleri doğrulama" in res["report_text"]
    assert (tmp_path / "forward_validation.json").exists()  # stored next to the books
