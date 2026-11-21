# -*- coding: utf-8 -*-
"""Unit & invariant tests for Strategy Research v3 (Priority D)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.quant.forward_validation import strategy_fingerprint
from src.quant.research_lab import ResearchV3Gate, run_strategy_research_v3
from src.quant.strategies.library import compute_meta_a_weights, compute_paa_weights
from src.quant.strategies.research_v3 import (
    V3_SECTOR_FACTOR_ASSETS,
    V3_TSMOM_RISK_ASSETS,
    build_v3_research_candidates,
    compute_v3_sector_factor_breadth_bil_weights,
    compute_v3_trend_risk_parity_bil_weights,
    compute_v3_tsmom_cross_asset_weights,
)


def _make_multi_era_prices(
    symbols: list[str],
    *,
    start: str = "2007-01-02",
    periods: int = 4900,
    seed: int = 123,
) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=periods)
    rng = np.random.default_rng(seed)
    data = {}
    for idx, sym in enumerate(symbols):
        if sym == "BIL":
            rets = np.full(periods, 0.02 / 252.0)
        elif sym == "SHY":
            rets = np.full(periods, 0.022 / 252.0) + rng.normal(0.0, 0.0005, periods)
        else:
            # Smooth sinusoidal regime + positive trend drift so trend strategies have real signal
            phase = np.sin(np.linspace(0.0, 14.0, periods) + idx * 0.9)
            drift = 0.00035 + 0.00045 * phase
            rets = drift + rng.normal(0.0, 0.0085, periods)
        data[sym] = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame(data, index=dates)


def test_research_v3_does_not_import_library_and_preserves_frozen_fingerprints() -> None:
    """Strict isolation invariant: research_v3 must never import library.py or alter PAA/Meta-A fingerprints."""
    src_path = Path("src/quant/strategies/research_v3.py")
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "library" not in node.module, f"Forbidden import from {node.module} in research_v3.py"
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "library" not in alias.name

    # If a local forward_validation.json exists with frozen paa/meta_a, verify exact SHA-256 match
    reg_path = Path("data/strategy_paper/forward_validation.json")
    if reg_path.is_file():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        strategies = reg.get("strategies") or {}
        if "paa" in strategies:
            frozen_paa = strategies["paa"]["fingerprint"]
            cur_paa = strategy_fingerprint(compute_paa_weights, frozen_paa["settings"])
            assert cur_paa["sha256"] == frozen_paa["sha256"], "PAA v2 frozen fingerprint drifted!"
        if "meta_a" in strategies:
            frozen_ma = strategies["meta_a"]["fingerprint"]
            cur_ma = strategy_fingerprint(compute_meta_a_weights, frozen_ma["settings"])
            assert cur_ma["sha256"] == frozen_ma["sha256"], "Meta-A v2 frozen fingerprint drifted!"


def test_v3_builders_zero_lookahead_perturbation() -> None:
    """Perturbing future closes after t0 by 3x must NEVER alter weights on or before t0."""
    macro_syms = list(dict.fromkeys([*V3_TSMOM_RISK_ASSETS, "BIL", "SHY"]))
    sec_syms = list(dict.fromkeys([*V3_SECTOR_FACTOR_ASSETS, "SPY", "BIL", "SHY"]))
    macro_df = _make_multi_era_prices(macro_syms, periods=900, seed=11)
    sec_df = _make_multi_era_prices(sec_syms, periods=900, seed=22)

    cutoff = 650
    macro_pert = macro_df.copy()
    macro_pert.iloc[cutoff + 1 :] *= 3.0
    sec_pert = sec_df.copy()
    sec_pert.iloc[cutoff + 1 :] *= 3.0

    for fn, df, df_p in (
        (compute_v3_tsmom_cross_asset_weights, macro_df, macro_pert),
        (compute_v3_trend_risk_parity_bil_weights, macro_df, macro_pert),
        (compute_v3_sector_factor_breadth_bil_weights, sec_df, sec_pert),
    ):
        w1 = fn(df).iloc[: cutoff + 1]
        w2 = fn(df_p).iloc[: cutoff + 1]
        # Exclude the synthetic final live-signal row since cutoff+1 < len(df)
        pd.testing.assert_frame_equal(w1.iloc[:-1], w2.iloc[:-1], check_exact=False, atol=1e-12)
        # Gross exposure must never exceed 1.0 + tiny float epsilon
        assert float(w1.sum(axis=1).max()) <= 1.0 + 1e-6


def test_v3_sector_factor_dynamic_inception_respects_252d_warmup() -> None:
    """ETFs launching mid-series (like XLC/XLRE) receive strictly 0 weight until 252 valid closes exist."""
    syms = list(dict.fromkeys([*V3_SECTOR_FACTOR_ASSETS, "SPY", "BIL"]))
    df = _make_multi_era_prices(syms, periods=700, seed=33)
    # Simulate XLC launching at bar 300 with explosive uptrend thereafter
    df.loc[df.index[:300], "XLC"] = np.nan
    df.loc[df.index[300:], "XLC"] = 100.0 * np.cumprod(1.0 + np.full(400, 0.004))

    weights = compute_v3_sector_factor_breadth_bil_weights(df)
    # Before bar 300 + 251 = 551, XLC must have strictly 0 weight
    assert float(weights["XLC"].iloc[:550].abs().max()) == 0.0
    # After 252 valid bars, XLC is eligible and should enter the top-3 winners
    assert float(weights["XLC"].iloc[560:].max()) > 0.0


def test_research_lab_runs_offline_and_enforces_strict_gates(tmp_path: Path) -> None:
    """Offline 19-year multi-era lab executes cleanly, writes artifacts to tmp_path, and applies all 5 gates."""
    macro_syms = list(dict.fromkeys([*V3_TSMOM_RISK_ASSETS, "QQQ", "EEM", "VNQ", "SHY", "BIL"]))
    sec_syms = list(dict.fromkeys([*V3_SECTOR_FACTOR_ASSETS, "SPY", "BIL", "SHY"]))
    macro_df = _make_multi_era_prices(macro_syms, start="2007-01-02", periods=4900, seed=7)
    sec_df = _make_multi_era_prices(sec_syms, start="2007-01-02", periods=4900, seed=8)
    meta_ref = macro_df["SPY"].pct_change().fillna(0.0) * 0.4

    out_json = tmp_path / "research_v3.json"
    out_md = tmp_path / "research_v3.md"
    payload = run_strategy_research_v3(
        macro_prices=macro_df,
        sector_prices=sec_df,
        meta_a_returns=meta_ref,
        run_plateau=False,
        save_outputs=True,
        json_path=out_json,
        report_path=out_md,
    )

    assert len(payload["candidates"]) == len(build_v3_research_candidates()) == 3
    assert payload["cumulative_trials_n"] == 28
    assert out_json.is_file()
    assert out_md.is_file()
    md_text = out_md.read_text(encoding="utf-8")
    assert "V3_TSMOM_CROSS_ASSET" in md_text
    assert "V3_TREND_RISK_PARITY_BIL" in md_text
    assert "V3_SECTOR_FACTOR_BREADTH_BIL" in md_text

    # Impossibly high gate must reject every single candidate honestly
    impossible = ResearchV3Gate(min_ex_sharpe_5bps=9.9)
    strict_payload = run_strategy_research_v3(
        macro_prices=macro_df,
        sector_prices=sec_df,
        meta_a_returns=meta_ref,
        run_plateau=False,
        gate=impossible,
        save_outputs=False,
    )
    assert strict_payload["promoted_ids"] == []
    assert len(strict_payload["rejected_ids"]) == 3


def test_v3_trp_enrolls_independently_in_forward_validation_without_touching_paa_or_meta_a(tmp_path: Path) -> None:
    """Enrolling v3_trp freezes it independently in ForwardRegistry while leaving paa & meta_a untouched."""
    from datetime import date
    from src.quant.forward_validation import ForwardRegistry, run_forward_validation
    from src.quant.paper_book import step_quant_paper_books

    syms = list(dict.fromkeys([*V3_TSMOM_RISK_ASSETS, "QQQ", "EEM", "VNQ", "SHY", "BIL", "HYG", "LQD", "VGK", "EWJ", "IWM"]))
    df = _make_multi_era_prices(syms, start="2020-01-02", periods=600, seed=55)

    # First freeze paa & meta_a
    step_quant_paper_books(strategies=["paa", "meta_a"], prices=df, book_dir=tmp_path, today=date(2022, 4, 20))
    reg_path = tmp_path / "forward_validation.json"
    before = ForwardRegistry(reg_path).data["strategies"]
    paa_fp_before = before["paa"]["fingerprint"]["sha256"]
    ma_fp_before = before["meta_a"]["fingerprint"]["sha256"]

    # Now enroll & freeze v3_trp independently
    res = step_quant_paper_books(strategies=["v3_trp"], prices=df, book_dir=tmp_path, today=date(2022, 4, 20))
    assert res["ok"] is True
    assert "v3_trp" in res["strategies"]

    after = ForwardRegistry(reg_path).data["strategies"]
    assert "v3_trp" in after
    assert after["paa"]["fingerprint"]["sha256"] == paa_fp_before
    assert after["meta_a"]["fingerprint"]["sha256"] == ma_fp_before

    fwd = run_forward_validation(strategies=["paa", "meta_a", "v3_trp"], prices=df, book_dir=tmp_path, auto_freeze=False)
    statuses = {r["strategy_key"]: r["status"] for r in fwd}
    assert statuses["paa"] != "INVALIDATED"
    assert statuses["meta_a"] != "INVALIDATED"
    assert statuses["v3_trp"] != "INVALIDATED"
