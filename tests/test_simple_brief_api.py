# -*- coding: utf-8 -*-
"""Tests for plain-Turkish simple-investor brief service & API endpoint."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import alpha
from src.services import simple_investor_brief as sib
from src.services.simple_investor_brief import build_simple_investor_brief
from src.services.simple_notification import dispatch_simple_morning_summary, format_simple_morning_summary

FRESH_DAY = date(2026, 11, 21)


def _write_snapshots(tmp_path: Path) -> None:
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



def _brief(tmp_path: Path, today: date = FRESH_DAY) -> dict:
    return build_simple_investor_brief(
        tournament_path=tmp_path / "tournament_latest.json",
        research_v3_path=tmp_path / "research_v3_latest.json",
        forward_path=tmp_path / "forward_validation.json",
        book_dir=tmp_path,
        today=today,
    )


def test_build_simple_investor_brief_from_isolated_snapshots(tmp_path: Path) -> None:
    _write_snapshots(tmp_path)
    brief = _brief(tmp_path)
    assert brief["ok"] is True
    assert brief["data_status"]["state"] == "ok"
    assert brief["as_of_date"] == "2026-11-20"
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


def _patch_default_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sib, "DEFAULT_TOURNAMENT_JSON", tmp_path / "tournament_latest.json")
    monkeypatch.setattr(sib, "DEFAULT_RESEARCH_V3_JSON", tmp_path / "research_v3_latest.json")
    monkeypatch.setattr(sib, "DEFAULT_FORWARD_JSON", tmp_path / "forward_validation.json")
    monkeypatch.setattr(sib, "DEFAULT_BOOK_DIR", tmp_path)


def test_simple_brief_http_endpoint(monkeypatch, tmp_path: Path) -> None:
    _write_snapshots(tmp_path)
    _patch_default_paths(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(alpha.router, prefix="/api/v1/alpha")
    resp = TestClient(app).get("/api/v1/alpha/simple-brief")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["simulated_only"] is True
    assert len(body["profiles"]) == 3
    assert body["weather"]["status"] in {"stormy", "cloudy", "sunny"}
    assert body["data_status"]["sources"][0]["as_of_date"] == "2026-11-20"
    assert "ALPACA_PAPER=true" in body["disclaimer"]
    assert "2026-11-20" in body["disclaimer"]


def test_missing_snapshots_never_invent_an_allocation(monkeypatch, tmp_path: Path) -> None:
    brief = _brief(tmp_path)
    assert brief["ok"] is False
    assert brief["data_status"]["state"] == "missing"
    assert brief["weather"]["status"] == "unknown"
    assert brief["weather"]["protection_pct"] is None
    assert brief["profiles"] == []
    assert brief["as_of_date"] == ""
    assert brief["usdtry_rate"] is None
    assert "henüz başlamadı" in brief["disclaimer"]

    _patch_default_paths(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(alpha.router, prefix="/api/v1/alpha")
    body = TestClient(app).get("/api/v1/alpha/simple-brief").json()
    assert body["data_status"]["state"] == "missing" and body["usdtry_rate"] is None


def test_partial_snapshot_hides_only_dependent_baskets(tmp_path: Path) -> None:
    _write_snapshots(tmp_path)
    (tmp_path / "research_v3_latest.json").unlink()
    brief = _brief(tmp_path)
    assert brief["data_status"]["state"] == "partial"
    assert "v3 araştırması" in brief["data_status"]["message"]
    assert [p["id"] for p in brief["profiles"]] == ["growth"]  # cautious & balanced need v3_trp
    assert brief["weather"]["status"] == "stormy"  # PAA / Meta-A are still real


def test_stale_snapshot_is_flagged(tmp_path: Path) -> None:
    _write_snapshots(tmp_path)
    brief = _brief(tmp_path, today=date(2026, 12, 15))
    assert brief["data_status"]["state"] == "stale"
    assert brief["data_status"]["sources"][0]["age_days"] == 25
    assert "güncel değil" in brief["data_status"]["message"]
    assert len(brief["profiles"]) == 3  # still shown, but labelled


def test_max_drawdowns_come_from_snapshots(tmp_path: Path) -> None:
    _write_snapshots(tmp_path)
    v3_path = tmp_path / "research_v3_latest.json"
    data = json.loads(v3_path.read_text(encoding="utf-8"))
    data["candidates"][0]["full_2008_plus"] = {"max_drawdown_pct": -7.35}
    data["candidates"][0]["orthogonality_vs_meta_a"] = {"blend_50_50_max_dd_pct": -5.4}
    v3_path.write_text(json.dumps(data), encoding="utf-8")
    dd = {p["id"]: p["historical_max_dd_pct"] for p in _brief(tmp_path)["profiles"]}
    assert dd == {"cautious": -7.35, "balanced": -5.4, "growth": None}


def test_morning_summary_does_not_announce_without_data(tmp_path: Path) -> None:
    class Notifier:
        def __init__(self) -> None:
            self.sent = []

        def send(self, message, dedup_key=None):
            self.sent.append(message)
            return True

    notifier = Notifier()
    empty = _brief(tmp_path)
    res = dispatch_simple_morning_summary(notifier=notifier, brief=empty, state_path=tmp_path / "s.json")
    assert res["sent"] is False and res["skipped_reason"] == "no_strategy_data"
    assert notifier.sent == []
    assert "BIL %100" not in res["message"] and "Strateji verisi yok" in res["message"]

    _write_snapshots(tmp_path)
    text = format_simple_morning_summary(_brief(tmp_path, today=date(2026, 12, 15)))
    assert "Dikkat: Veriler güncel değil" in text
    assert "BIL %" in text


@pytest.mark.parametrize("fresh", [True, False])
def test_morning_summary_sends_real_allocation(tmp_path: Path, fresh: bool) -> None:
    _write_snapshots(tmp_path)
    brief = _brief(tmp_path, today=FRESH_DAY if fresh else date(2026, 12, 15))
    text = format_simple_morning_summary(brief)
    assert text.startswith("⛈️ 2026-11-20 Özeti")
    assert ("Dikkat" in text) is (not fresh)


def test_simple_brief_signal_accuracy_states_and_morning_3_lines(tmp_path: Path, monkeypatch) -> None:
    _write_snapshots(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "nonexistent.db"))
    from src.config import Config

    Config.reset_instance()
    try:
        missing_brief = build_simple_investor_brief(
            tournament_path=tmp_path / "tournament_latest.json",
            research_v3_path=tmp_path / "research_v3_latest.json",
            forward_path=tmp_path / "forward_validation.json",
            book_dir=tmp_path,
            today=FRESH_DAY,
        )
        assert missing_brief["signal_accuracy"]["data_status"] == "missing"
        assert "veri yok" in missing_brief["signal_accuracy"]["summary_line"].lower()
    finally:
        Config.reset_instance()

    insufficient_brief = build_simple_investor_brief(
        tournament_path=tmp_path / "tournament_latest.json",
        research_v3_path=tmp_path / "research_v3_latest.json",
        forward_path=tmp_path / "forward_validation.json",
        book_dir=tmp_path,
        today=FRESH_DAY,
        signal_summary_loader=lambda: {
            "data_status": "insufficient",
            "n": 4,
            "min_sample": 30,
            "summary_line": "Yapay zekâ önerilerinin başarısı henüz ölçülüyor (4/30)",
        },
    )
    text_ins = format_simple_morning_summary(insufficient_brief, weekly_watch={"total": 10, "line": "Bu hafta: 10 sinyal, %80'si izle"})
    assert len(text_ins.splitlines()) == 3
    assert "4/30" in text_ins and "Bu hafta: 10 sinyal" in text_ins

    ok_brief = build_simple_investor_brief(
        tournament_path=tmp_path / "tournament_latest.json",
        research_v3_path=tmp_path / "research_v3_latest.json",
        forward_path=tmp_path / "forward_validation.json",
        book_dir=tmp_path,
        today=FRESH_DAY,
        signal_summary_loader=lambda: {
            "data_status": "ok",
            "n": 30,
            "min_sample": 30,
            "beat_rate_pct": 70.0,
            "proven_vs_benchmark": True,
            "summary_line": "Son 30 al/sat önerisinden %70'i 10 günde endeksten iyi çıktı.",
        },
    )
    text_ok = format_simple_morning_summary(ok_brief)
    assert len(text_ok.splitlines()) == 3
    assert "Son 30 al/sat önerisinden %70'i 10 günde endeksten iyi çıktı." in text_ok


def test_paper_exam_ignores_pre_freeze_history_rows(tmp_path: Path) -> None:
    _write_snapshots(tmp_path)
    (tmp_path / "quant_meta_a.json").write_text(
        json.dumps({
            "initial_capital": 10000.0,
            "nav": 10025.42,
            "history": [
                {"date": "2026-11-18", "nav": 10000.0, "benchmark_nav": 10000.0},
                {"date": "2026-11-20", "nav": 10009.81, "benchmark_nav": 9800.0},
                {"date": "2026-11-23", "nav": 10025.42, "benchmark_nav": 10261.58},
            ],
        }),
        encoding="utf-8",
    )
    brief = _brief(tmp_path)
    meta_exam = next(item for item in brief["paper_exam"] if item["strategy_key"] == "meta_a")
    assert meta_exam["forward_days"] == 1
    assert meta_exam["return_pct"] == pytest.approx(0.16, abs=0.01)
    assert meta_exam["benchmark_return_pct"] == pytest.approx(4.71, abs=0.01)

