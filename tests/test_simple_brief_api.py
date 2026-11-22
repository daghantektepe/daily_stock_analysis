# -*- coding: utf-8 -*-
"""Tests for plain-Turkish simple-investor brief service & API endpoint."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import alpha
from src.services.simple_investor_brief import build_simple_investor_brief


def test_build_simple_investor_brief_from_isolated_snapshots(tmp_path: Path) -> None:
    t_path = tmp_path / "tournament_latest.json"
    v3_path = tmp_path / "research_v3_latest.json"
    fwd_path = tmp_path / "forward_validation.json"

    t_path.write_text(
        json.dumps({
            "latest_date": "2026-11-20",
            "paa": {"current_weights": {"BIL": 100.0}},
            "meta_portfolio_a": {"latest_date": "2026-11-20", "current_weights": {"BIL": 80.0, "SHY": 20.0}},
            "meta_portfolio_b": {"current_weights": {"BIL": 64.0, "SHY": 16.0}, "cash_weight_pct": 20.0},
            "bist_usd_reference": {"usdtry_end": 50.56},
        }),
        encoding="utf-8",
    )
    v3_path.write_text(
        json.dumps({
            "candidates": [{
                "strategy_id": "V3_TREND_RISK_PARITY_BIL",
                "latest_date": "2026-11-20",
                "current_weights": {"BIL": 83.3, "UUP": 16.7},
            }],
        }),
        encoding="utf-8",
    )
    fwd_path.write_text(
        json.dumps({
            "strategies": {
                "v3_trp": {"frozen_date": "2026-11-20", "fingerprint": {"sha256": "ae4754108564abcdef"}},
                "meta_a": {"frozen_date": "2026-11-20", "fingerprint": {"sha256": "37a7ab36a0d9abcdef"}},
            }
        }),
        encoding="utf-8",
    )
    (tmp_path / "quant_v3_trp.json").write_text(
        json.dumps({"initial_capital": 10000.0, "nav": 10012.5, "history": [{"date": "2026-11-20", "nav": 10000.0, "benchmark_nav": 10000.0}, {"date": "2026-11-21", "nav": 10012.5, "benchmark_nav": 9900.0}]}),
        encoding="utf-8",
    )

    brief = build_simple_investor_brief(
        tournament_path=t_path,
        research_v3_path=v3_path,
        forward_path=fwd_path,
        book_dir=tmp_path,
    )
    assert brief["ok"] is True
    assert brief["simulated_only"] is True
    assert brief["usdtry_rate"] == 50.56
    assert brief["weather"]["status"] == "stormy"
    assert len(brief["decision_steps"]) == 3
    assert len(brief["profiles"]) == 3

    for profile in brief["profiles"]:
        total_w = round(sum(a["weight_pct"] for a in profile["assets"]), 1)
        assert total_w == 100.0, f"Profile {profile['id']} weights must sum to 100%, got {total_w}"
        assert all(a["tr_equivalent"] and a["plain_name"] for a in profile["assets"])

    assert any(item["strategy_key"] == "v3_trp" and item["forward_days"] == 1 for item in brief["paper_exam"])


def test_simple_brief_http_endpoint() -> None:
    app = FastAPI()
    app.include_router(alpha.router, prefix="/api/v1/alpha")
    resp = TestClient(app).get("/api/v1/alpha/simple-brief")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["simulated_only"] is True
    assert len(body["profiles"]) == 3
    assert body["weather"]["status"] in {"stormy", "cloudy", "sunny"}
    assert "ALPACA_PAPER=true" in body["disclaimer"]
