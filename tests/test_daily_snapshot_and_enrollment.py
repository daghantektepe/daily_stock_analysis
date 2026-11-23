# -*- coding: utf-8 -*-
"""Frozen strategies stay on the daily step; /simple snapshots are refreshed daily."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

from src.quant.paper_book import (
    DEFAULT_QUANT_PAPER_STRATEGIES,
    normalize_quant_paper_strategies,
    resolve_active_quant_paper_strategies,
)
from src.quant.snapshot_refresh import format_snapshot_refresh_report, refresh_strategy_snapshots


# ---------------------------------------------------------------------------
# v3_trp enrollment
# ---------------------------------------------------------------------------


def test_v3_trp_is_a_default_strategy() -> None:
    assert DEFAULT_QUANT_PAPER_STRATEGIES == ("paa", "meta_a", "v3_trp")
    assert normalize_quant_paper_strategies(None) == ["paa", "meta_a", "v3_trp"]
    assert normalize_quant_paper_strategies(["all"]) == ["paa", "meta_a", "v3_trp"]


def test_config_default_includes_v3_trp(monkeypatch, tmp_path: Path) -> None:
    from src.config import Config

    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("ENV_FILE", str(env_file))
    monkeypatch.delenv("QUANT_PAPER_STRATEGIES", raising=False)
    Config.reset_instance()
    try:
        assert Config.get_instance().quant_paper_strategies == ["paa", "meta_a", "v3_trp"]
    finally:
        Config.reset_instance()


def _write_registry(book_dir: Path, keys) -> None:
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "forward_validation.json").write_text(
        json.dumps({"strategies": {k: {"frozen_date": "2026-11-20"} for k in keys}, "orders": []}),
        encoding="utf-8",
    )


def test_frozen_strategy_is_kept_even_if_env_lists_only_old_pair(tmp_path: Path) -> None:
    _write_registry(tmp_path, ["paa", "meta_a", "v3_trp", "unknown_key"])
    assert resolve_active_quant_paper_strategies(["paa", "meta_a"], book_dir=tmp_path) == ["paa", "meta_a", "v3_trp"]
    # Explicit config order is preserved; unknown registry keys are ignored
    assert resolve_active_quant_paper_strategies(["meta_a"], book_dir=tmp_path) == ["meta_a", "paa", "v3_trp"]


def test_resolver_without_or_with_corrupt_registry(tmp_path: Path) -> None:
    assert resolve_active_quant_paper_strategies(["paa"], book_dir=tmp_path) == ["paa"]
    (tmp_path / "forward_validation.json").write_text("{not json", encoding="utf-8")
    assert resolve_active_quant_paper_strategies(["paa"], book_dir=tmp_path) == ["paa"]


def test_all_entry_points_use_the_shared_resolver(monkeypatch, tmp_path: Path) -> None:
    """Scheduler, CLI, API and MCP must resolve the same strategy set."""
    import scripts.quant_paper as quant_paper_cli
    from api.v1.endpoints import alpha
    from src.quant import paper_book

    calls = []

    def fake_resolver(configured, *, book_dir=None):
        calls.append(tuple(configured or ()))
        return ["paa", "meta_a", "v3_trp"]

    monkeypatch.setattr(paper_book, "resolve_active_quant_paper_strategies", fake_resolver)
    cfg = SimpleNamespace(
        quant_paper_strategies=["paa", "meta_a"], quant_paper_capital=10000.0,
        quant_paper_cost_bps=5.0, quant_paper_rebalance_mode="monthly",
    )
    assert alpha._active_quant_paper_strategies(cfg) == ("paa", "meta_a", "v3_trp")
    monkeypatch.setattr("src.config.get_config", lambda: cfg)
    assert quant_paper_cli._load_settings("")["strategies"] == ["paa", "meta_a", "v3_trp"]
    assert quant_paper_cli._load_settings("paa")["strategies"] == ["paa"]  # explicit CLI choice wins
    assert calls == [("paa", "meta_a"), ("paa", "meta_a")]


def test_scheduler_steps_frozen_books_and_refreshes_snapshots(monkeypatch) -> None:
    import main
    from src.quant import paper_book, snapshot_refresh

    seen = {}

    def fake_step(**kwargs):
        seen["strategies"] = kwargs["strategies"]
        return {"ok": False, "error": "no prices"}  # even a failed step must still refresh

    monkeypatch.setattr(paper_book, "step_quant_paper_books", fake_step)
    monkeypatch.setattr(paper_book, "resolve_active_quant_paper_strategies", lambda c, **_k: ["paa", "meta_a", "v3_trp"])
    monkeypatch.setattr(snapshot_refresh, "refresh_strategy_snapshots", lambda **_k: seen.setdefault("refreshed", {"results": {}}))
    cfg = SimpleNamespace(quant_paper_enabled=True, quant_paper_strategies=["paa", "meta_a"])
    main._run_quant_allocation_paper_step(cfg)
    assert seen["strategies"] == ("paa", "meta_a", "v3_trp")
    assert "refreshed" in seen

    seen.clear()
    main._run_quant_allocation_paper_step(SimpleNamespace(quant_paper_enabled=False))
    assert seen == {}  # disabled: nothing runs


# ---------------------------------------------------------------------------
# Snapshot refresh
# ---------------------------------------------------------------------------


def _touch(path: Path, hours_ago: float) -> None:
    path.write_text("{}", encoding="utf-8")
    stamp = time.time() - hours_ago * 3600.0
    os.utime(path, (stamp, stamp))


def test_refresh_rebuilds_old_or_missing_and_skips_fresh(tmp_path: Path) -> None:
    _touch(tmp_path / "tournament_latest.json", hours_ago=2)
    _touch(tmp_path / "research_v3_latest.json", hours_ago=30)
    ran = []

    def runner(name):
        def _run(cache_dir, force_refresh):
            ran.append((name, cache_dir, force_refresh))
            return {"latest_date": "2026-11-21"}
        return _run

    result = refresh_strategy_snapshots(
        cache_dir=tmp_path, runners={"tournament": runner("tournament"), "research_v3": runner("research_v3")}
    )
    assert ran == [("research_v3", tmp_path, False)]
    assert result["ok"] is True
    assert result["results"]["tournament"]["status"] == "fresh"
    assert result["results"]["research_v3"]["status"] == "refreshed"

    ran.clear()
    refresh_strategy_snapshots(
        cache_dir=tmp_path, force=True,
        runners={"tournament": runner("tournament"), "research_v3": runner("research_v3")},
    )
    assert [r[0] for r in ran] == ["tournament", "research_v3"]


def test_refresh_failure_keeps_previous_snapshot_and_reports_it(tmp_path: Path) -> None:
    _touch(tmp_path / "tournament_latest.json", hours_ago=48)

    def boom(_cache_dir, _force):
        raise RuntimeError("yahoo down")

    result = refresh_strategy_snapshots(
        cache_dir=tmp_path, runners={"tournament": boom, "research_v3": lambda *_a: {"latest_date": "2026-11-20"}}
    )
    assert result["ok"] is False
    assert result["results"]["tournament"]["status"] == "failed"
    assert (tmp_path / "tournament_latest.json").read_text(encoding="utf-8") == "{}"
    text = format_snapshot_refresh_report(result)
    assert "YENİLENEMEDİ — yahoo down" in text and "önceki veri korunuyor (48.0 saatlik)" in text
    assert "v3 araştırması: yenilendi" in text


def test_daily_refresh_never_writes_tracked_docs(tmp_path: Path, monkeypatch) -> None:
    """The real runners must pass write_report=False so git pull keeps working on E:\\."""
    from src.quant import research_lab, tournament

    captured = {}

    def fake_tournament(**kwargs):
        captured["tournament"] = kwargs
        return {"latest_date": "2026-11-21", "total_strategies": 25}

    def fake_research(**kwargs):
        captured["research"] = kwargs
        return {"candidates": [{"latest_date": "2026-11-20"}], "promoted_ids": []}

    monkeypatch.setattr(tournament, "run_tournament", fake_tournament)
    monkeypatch.setattr(research_lab, "run_strategy_research_v3", fake_research)
    result = refresh_strategy_snapshots(cache_dir=tmp_path)
    assert result["ok"] is True
    assert captured["tournament"]["write_report"] is False
    assert captured["research"]["write_report"] is False
    assert captured["research"]["json_path"] == tmp_path / "research_v3_latest.json"


def test_research_lab_write_report_false_keeps_docs_untouched(tmp_path: Path) -> None:
    from tests.test_strategy_research_v3 import _make_multi_era_prices
    from src.quant.data_loader import MACRO_V3_UNIVERSE, SECTOR_FACTOR_V3_UNIVERSE
    from src.quant.research_lab import run_strategy_research_v3

    report = tmp_path / "report.md"
    json_path = tmp_path / "research.json"
    macro = _make_multi_era_prices(list(MACRO_V3_UNIVERSE))
    run_strategy_research_v3(
        macro_prices=macro,
        sector_prices=_make_multi_era_prices(list(SECTOR_FACTOR_V3_UNIVERSE), seed=7),
        meta_a_returns=macro["SPY"].pct_change().fillna(0.0) * 0.4,
        run_plateau=False,
        json_path=json_path,
        report_path=report,
        write_report=False,
    )
    assert json_path.is_file()
    assert not report.exists()
