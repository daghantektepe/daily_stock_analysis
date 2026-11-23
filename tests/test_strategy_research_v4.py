# -*- coding: utf-8 -*-
"""Strategy Research v4: inverse-ETF short sleeve vs long-only control."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd

from src.quant.research_v4_lab import (
    _compare_short_vs_control,
    run_strategy_research_v4,
    short_sleeve_diagnostics,
)
from src.quant.strategies.research_v4 import (
    LONGSHORT_V4_UNIVERSE,
    V4_INVERSE_ETFS,
    build_v4_research_candidates,
    compute_v4_trend_long_only_control_weights,
    compute_v4_trend_long_short_weights,
)

INVERSE_OF = {"SH": "SPY", "PSQ": "QQQ", "EFZ": "EFA", "TBF": "TLT"}


def _prices(periods: int = 1500, seed: int = 3, crash_from: int | None = None) -> pd.DataFrame:
    """Synthetic universe; inverse ETFs are built from their underlying's daily returns (with decay)."""
    dates = pd.bdate_range("2007-01-02", periods=periods)
    rng = np.random.default_rng(seed)
    data = {"BIL": 100.0 * np.cumprod(np.full(periods, 1.0 + 0.02 / 252.0))}
    for idx, sym in enumerate(("SPY", "QQQ", "EFA", "TLT", "IEF", "GLD", "DBC")):
        drift = 0.0004 + 0.0004 * np.sin(np.linspace(0.0, 9.0, periods) + idx)
        rets = drift + rng.normal(0.0, 0.01, periods)
        if crash_from is not None and sym in ("SPY", "QQQ", "EFA"):
            rets[crash_from:] = -0.002 + rng.normal(0.0, 0.01, periods - crash_from)
        data[sym] = 100.0 * np.cumprod(1.0 + rets)
    frame = pd.DataFrame(data, index=dates)
    for inv, under in INVERSE_OF.items():
        r = -frame[under].pct_change().fillna(0.0) - 0.009 / 252.0
        frame[inv] = 50.0 * np.cumprod(1.0 + r.values)
    return frame


def test_module_is_isolated_from_frozen_library() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "quant" / "strategies" / "research_v4.py"
    for node in ast.walk(ast.parse(src.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "library" not in node.module
    assert set(V4_INVERSE_ETFS) == set(INVERSE_OF)
    assert set(LONGSHORT_V4_UNIVERSE) >= set(INVERSE_OF) | set(INVERSE_OF.values()) | {"BIL"}


def test_frozen_fingerprints_unchanged() -> None:
    from src.quant.forward_validation import _book_settings, strategy_fingerprint
    from src.quant.paper_book import build_quant_paper_book

    expected = {"paa": "87e22a6b3559", "meta_a": "37a7ab36a0d9", "v3_trp": "ae4754108564"}
    for key, sha in expected.items():
        book, fn = build_quant_paper_book(key, book_dir=None, initial_capital=10000.0, cost_bps=5.0, rebalance_mode="monthly")
        assert strategy_fingerprint(fn, _book_settings(book))["sha256"][:12] == sha


def test_weights_are_long_only_unlevered_and_fully_allocated() -> None:
    w = compute_v4_trend_long_short_weights(_prices(crash_from=900))
    assert float(w.min().min()) >= 0.0
    active = w.iloc[260:]
    assert float(active.sum(axis=1).max()) <= 1.0 + 1e-9
    assert np.allclose(active.sum(axis=1), 1.0, atol=1e-6)


def test_inverse_etf_used_only_in_downtrend_and_never_with_its_underlying() -> None:
    prices = _prices(crash_from=900)
    w = compute_v4_trend_long_short_weights(prices)
    late = w.iloc[1200:]
    assert float(late[["SH", "PSQ", "EFZ"]].sum(axis=1).max()) > 0.0  # equities crashing -> short sleeve
    for inv, under in INVERSE_OF.items():
        both = (w[inv] > 0) & (w[under] > 0)
        assert not bool(both.any()), f"{inv} and {under} held together"
    control = compute_v4_trend_long_only_control_weights(prices)
    assert float(control.reindex(columns=list(INVERSE_OF), fill_value=0.0).to_numpy().sum()) == 0.0


def test_zero_lookahead() -> None:
    prices = _prices()
    cut = 1100
    shocked = prices.copy()
    shocked.iloc[cut + 1:] *= 3.0
    base = compute_v4_trend_long_short_weights(prices.iloc[: cut + 1])
    alt = compute_v4_trend_long_short_weights(shocked.iloc[: cut + 1])
    pd.testing.assert_frame_equal(base, alt)


def test_short_sleeve_diagnostics_reports_activity_and_contribution() -> None:
    prices = _prices(crash_from=900)
    diag = short_sleeve_diagnostics(prices, compute_v4_trend_long_short_weights(prices))
    assert diag["available"] is True
    assert 0.0 < diag["share_of_days_with_short_pct"] <= 100.0
    assert set(diag["annual_contribution_by_etf_pct"]) == set(INVERSE_OF)
    assert diag["annual_contribution_pct"] > 0.0  # a persistent crash pays the short sleeve
    none = short_sleeve_diagnostics(prices, compute_v4_trend_long_only_control_weights(prices))
    assert none == {"available": False}  # control never holds an inverse ETF


def _res(verdict: str, ex5: float, ex25: float) -> dict:
    return {
        "verdict": verdict,
        "failed_gates": [] if verdict == "PROMOTE_TO_FORWARD_PAPER" else ["gate5_orthogonality_vs_meta_a"],
        "full_2008_plus": {"cagr_pct": 4.0, "max_drawdown_pct": -8.0},
        "cost_stress": {"5bps": {"excess_sharpe": ex5}, "25bps": {"excess_sharpe": ex25}},
        "calendar_years": {"yearly": {"2008": {"return_pct": 10.0}, "2022": {"return_pct": 1.0}}},
    }


def test_short_must_beat_control_even_when_it_passes_gates() -> None:
    # The real-data case: long/short passes the gates only via lower correlation, but loses to the control
    cmp_ = _compare_short_vs_control(_res("PROMOTE_TO_FORWARD_PAPER", 0.51, 0.38), _res("REJECTED", 0.68, 0.56))
    assert cmp_["short_adds_value"] is False
    assert cmp_["excess_sharpe_edge_5bps"] == -0.17
    assert any("5 bps" in r for r in cmp_["reasons"])

    good = _compare_short_vs_control(_res("PROMOTE_TO_FORWARD_PAPER", 0.80, 0.60), _res("REJECTED", 0.68, 0.50))
    assert good["short_adds_value"] is True and good["reasons"] == []

    failed = _compare_short_vs_control(_res("REJECTED", 0.90, 0.80), _res("REJECTED", 0.68, 0.50))
    assert failed["short_adds_value"] is False


def test_lab_runs_offline_and_writes_report(tmp_path: Path) -> None:
    prices = _prices(periods=4900, seed=11, crash_from=3000)
    meta_ref = prices["SPY"].pct_change().fillna(0.0) * 0.4
    payload = run_strategy_research_v4(
        prices=prices,
        meta_a_returns=meta_ref,
        run_plateau=False,
        json_path=tmp_path / "v4.json",
        report_path=tmp_path / "v4.md",
    )
    ids = [c["strategy_id"] for c in payload["candidates"]]
    assert ids == [c.spec.strategy_id for c in build_v4_research_candidates()]
    assert payload["cumulative_trials_n"] == 30
    assert "short_adds_value" in payload["short_vs_control"]
    assert (tmp_path / "v4.json").is_file()
    text = (tmp_path / "v4.md").read_text(encoding="utf-8")
    assert "Short değer katıyor mu?" in text and "Long-Only Kontrol" in text

    run_strategy_research_v4(
        prices=prices, meta_a_returns=meta_ref, run_plateau=False,
        json_path=tmp_path / "v4b.json", report_path=tmp_path / "v4b.md", write_report=False,
    )
    assert not (tmp_path / "v4b.md").exists()


def test_report_scripts_default_to_data_reports_without_touching_docs(monkeypatch, tmp_path, capsys) -> None:
    import sys
    import scripts.run_strategy_research_v3 as s_v3
    import scripts.run_strategy_research_v4 as s_v4
    import scripts.run_strategy_tournament as s_t

    assert str(s_t.DEFAULT_LOCAL_TOURNAMENT_REPORT).replace("\\", "/") == "data/reports/STRATEGY_TOURNAMENT_REPORT.md"
    assert str(s_v3.DEFAULT_LOCAL_RESEARCH_V3_REPORT).replace("\\", "/") == "data/reports/STRATEGY_RESEARCH_V3_REPORT.md"
    assert str(s_v4.DEFAULT_LOCAL_RESEARCH_V4_REPORT).replace("\\", "/") == "data/reports/STRATEGY_RESEARCH_V4_REPORT.md"

    local_t = tmp_path / "data" / "reports" / "STRATEGY_TOURNAMENT_REPORT.md"
    monkeypatch.setattr(s_t, "DEFAULT_LOCAL_TOURNAMENT_REPORT", local_t)
    called_write = []

    def fake_tournament(**kwargs):
        called_write.append(kwargs.get("write_report"))
        return {
            "total_strategies": 1,
            "total_assets": 1,
            "total_asset_days": 10,
            "oos_start": "2022-01-01",
            "latest_date": "2026-11-20",
            "pass_elite_count": 1,
            "pass_solid_count": 0,
            "champion": {
                "name": "Test Champ",
                "oos": {"cagr_pct": 6.0, "sharpe": 0.9, "excess_sharpe": 0.72, "max_drawdown_pct": -5.0, "dsr_pct": 95.0},
                "signal_summary": "BIL %100",
            },
            "strategies": [],
        }

    monkeypatch.setattr(s_t, "run_tournament", fake_tournament)
    monkeypatch.setattr(s_t, "format_tournament_markdown", lambda _p: "# report\n")
    monkeypatch.setattr(sys, "argv", ["run_strategy_tournament.py"])
    assert s_t.main() == 0
    out = capsys.readouterr().out
    assert "BIL üstü Sharpe +0.72" in out
    assert called_write == [False]
    assert local_t.is_file()
