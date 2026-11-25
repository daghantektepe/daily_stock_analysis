# -*- coding: utf-8 -*-
"""Safety-lock, audit-log, and simple 3-line notification tests for Phase 8."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi.testclient import TestClient
import pytest

from api.app import create_app
from src.brokers.algolab import AlgoLabBrokerAdapter
from src.brokers.alpaca.adapter import AlpacaBrokerAdapter
from src.brokers.alpaca.client import AlpacaClient
from src.brokers.base import BrokerSecurityError, read_broker_audit_tail
from src.brokers.binance.adapter import BinanceBrokerAdapter
from src.brokers.binance.client import BinanceClient
from src.brokers.ibkr import IbkrBrokerAdapter
from src.brokers.registry import get_broker_registry, resolve_strategy_target_weights
from src.services.simple_notification import (
    dispatch_simple_morning_summary,
    format_simple_morning_summary,
)


def test_all_adapters_block_unconfirmed_or_non_sandbox_writes(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"

    # 1. Alpaca refuses non-paper AND refuses paper without confirmed=True
    alpaca_live = AlpacaBrokerAdapter(
        client=AlpacaClient(api_key="k", secret_key="s", paper=False, live_trading_confirmed=False),
        audit_path=audit,
    )
    with pytest.raises(BrokerSecurityError, match="ALPACA_PAPER=true"):
        alpaca_live.submit_paper_order({"symbol": "SPY", "side": "buy", "qty": 1}, confirmed=True)

    alpaca_paper = AlpacaBrokerAdapter(
        client=AlpacaClient(api_key="k", secret_key="s", paper=True),
        audit_path=audit,
    )
    with pytest.raises(BrokerSecurityError, match="confirmed=True"):
        alpaca_paper.submit_paper_order({"symbol": "SPY", "side": "buy", "qty": 1}, confirmed=False)

    # 2. Binance refuses mainnet AND refuses testnet without confirmed=True
    bnc_main = BinanceBrokerAdapter(
        client=BinanceClient(api_key="k", api_secret="s", testnet=False, live_trading_confirmed=False),
        audit_path=audit,
    )
    with pytest.raises(BrokerSecurityError, match="BINANCE_TESTNET=false"):
        bnc_main.submit_paper_order({"symbol": "BTCUSDT", "side": "BUY", "quote_order_qty": 50}, confirmed=True)

    bnc_test = BinanceBrokerAdapter(
        client=BinanceClient(api_key="k", api_secret="s", testnet=True),
        audit_path=audit,
    )
    with pytest.raises(BrokerSecurityError, match="confirmed=True"):
        bnc_test.submit_paper_order({"symbol": "BTCUSDT", "side": "BUY", "quote_order_qty": 50}, confirmed=False)

    # 3. AlgoLab is strictly read-only
    algolab = AlgoLabBrokerAdapter(api_key="k", username="u", read_only=True, audit_path=audit)
    with pytest.raises(BrokerSecurityError, match="read-only"):
        algolab.submit_paper_order({"symbol": "THYAO.IS", "side": "BUY", "qty": 10}, confirmed=True)

    # 4. IBKR blocks live ports and read-only default
    ibkr_live_port = IbkrBrokerAdapter(port=7496, read_only=False, audit_path=audit)
    with pytest.raises(BrokerSecurityError, match="live ports"):
        ibkr_live_port.submit_paper_order({"symbol": "SPY", "side": "BUY", "qty": 1}, confirmed=True)

    ibkr_ro = IbkrBrokerAdapter(port=7497, read_only=True, audit_path=audit)
    with pytest.raises(BrokerSecurityError, match="IBKR_READ_ONLY=true"):
        ibkr_ro.submit_paper_order({"symbol": "SPY", "side": "BUY", "qty": 1}, confirmed=True)

    # Every blocked attempt was written to the audit log without exposing secrets
    tail = read_broker_audit_tail(limit=20, audit_path=audit)
    assert len(tail) == 7
    assert all("api_secret" not in json.dumps(entry) for entry in tail)


def test_rebalance_preview_and_audit_across_registry(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    reg = get_broker_registry(audit_path=audit)
    assert set(reg.keys()) == {"alpaca", "binance", "algolab", "ibkr"}

    weights = resolve_strategy_target_weights("meta_a")
    assert sum(weights.values()) > 0

    plan_alpaca = reg["alpaca"].preview_rebalance_plan({"BIL": 80.0, "SHY": 20.0}, capital=10000.0)
    assert plan_alpaca["sandbox"] is True
    assert len(plan_alpaca["orders"]) == 2

    plan_algolab = reg["algolab"].preview_rebalance_plan({"THYAO.IS": 50.0}, capital=50000.0)
    assert plan_algolab["currency"] == "TRY"
    assert plan_algolab["orders"][0]["target_notional"] == pytest.approx(25000.0)


def test_dry_run_reconciliation_and_binance_fallback_error_audit(tmp_path: Path) -> None:
    """REQ-04 / Step 5: Binance fallback logs error and dry-run reconciliation writes audit without orders."""
    from src.brokers.registry import run_broker_dry_run_reconciliation

    audit = tmp_path / "audit.jsonl"

    class _FailingBinanceClient(BinanceClient):
        def plan_crypto_trend_rebalance(self, target_weights):
            raise RuntimeError("binance testnet timeout")

    bnc = BinanceBrokerAdapter(
        client=_FailingBinanceClient(api_key="k", api_secret="s", testnet=True),
        audit_path=audit,
    )
    plan = bnc.preview_rebalance_plan({"BTC-USD": 50.0}, capital=10000.0)
    assert "binance testnet timeout" in str(plan.get("fallback_reason"))
    assert len(plan["orders"]) == 1

    dry = run_broker_dry_run_reconciliation("algolab", strategy_key="v3_trp", capital=100000.0, audit_path=audit)
    assert dry["ok"] is True
    assert dry["dry_run_only"] is True
    assert dry["broker_id"] == "algolab"
    assert len(dry["plan"]["orders"]) >= 1

    tail = read_broker_audit_tail(limit=10, audit_path=audit)
    assert any(e["action"] == "preview_rebalance" and e["status"] == "error" for e in tail)
    assert any(e["action"] == "dry_run_reconciliation" and e["broker_id"] == "algolab" for e in tail)


def test_bridges_adapters_api_preview_and_forbidden_submit() -> None:
    app = create_app()
    client = TestClient(app)

    res = client.get("/api/v1/bridges/adapters")
    assert res.status_code == 200
    ids = {a["broker_id"] for a in res.json()["adapters"]}
    assert {"alpaca", "binance", "algolab", "ibkr", "midas_csv"} <= ids

    prev = client.post(
        "/api/v1/bridges/adapters/preview",
        json={"broker_id": "algolab", "strategy_key": "v3_trp", "capital": 100000},
    )
    assert prev.status_code == 200
    body = prev.json()
    assert body["broker_id"] == "algolab"
    assert body["read_only_enforced"] is True
    assert len(body["orders"]) >= 1
    assert "Otomatik" not in body["copy_text"] or "manuel" in body["copy_text"].lower()

    blocked = client.post(
        "/api/v1/bridges/adapters/algolab/paper-order",
        json={"symbol": "THYAO.IS", "side": "BUY", "quantity": 5, "confirmed": True},
    )
    assert blocked.status_code == 403


def test_simple_morning_notification_three_lines_and_change_guard(tmp_path: Path) -> None:
    sample_brief: Dict[str, Any] = {
        "as_of_date": "2026-11-22",
        "weather": {"emoji": "⛈️", "headline": "Piyasalar Fırtınalı", "protection_pct": 100.0},
        "profiles": [
            {
                "id": "balanced",
                "title": "Dengeli Kalkan",
                "assets": [{"symbol": "BIL", "weight_pct": 90.0}, {"symbol": "SHY", "weight_pct": 10.0}],
            }
        ],
    }
    text = format_simple_morning_summary(sample_brief, weights_changed=False)
    lines = text.splitlines()
    assert len(lines) == 3
    assert "hiçbir işlem yapmana gerek yok" in lines[1]
    assert "otomatik alım-satım yapılmamıştır" in lines[2]

    class _FakeNotifier:
        def __init__(self) -> None:
            self.sent: List[str] = []

        def send(self, msg: str, **kwargs: Any) -> bool:
            self.sent.append(msg)
            return True

    state_file = tmp_path / "simple_notify.json"
    notifier = _FakeNotifier()

    first = dispatch_simple_morning_summary(notifier=notifier, brief=sample_brief, state_path=state_file)
    assert first["sent"] is True
    assert len(notifier.sent) == 1

    # Repeat call with identical weights skips notification cleanly
    second = dispatch_simple_morning_summary(notifier=notifier, brief=sample_brief, state_path=state_file)
    assert second["sent"] is False
    assert second["skipped_reason"] == "allocation_unchanged"
    assert len(notifier.sent) == 1

    # Mutate allocation -> dispatches calm update
    sample_brief["profiles"][0]["assets"][0]["weight_pct"] = 70.0
    third = dispatch_simple_morning_summary(notifier=notifier, brief=sample_brief, state_path=state_file)
    assert third["sent"] is True
    assert len(notifier.sent) == 2
