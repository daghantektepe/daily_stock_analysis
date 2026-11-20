# -*- coding: utf-8 -*-
"""Tests for the 3-AI Quantitative Strategy Council (Claude · Codex · Gemini) & daily paper league."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.quant.ai_council import (
    ALLOWED_RULE_ENGINES,
    _extract_json_object,
    compile_council_weight_fn,
    evaluate_and_register_charter,
    load_council_charters,
    save_council_charters,
)
from src.quant.paper_book import get_quant_paper_books_status, step_quant_paper_books


def _synthetic_council_prices(n_days: int = 340) -> pd.DataFrame:
    rng = np.random.default_rng(77)
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    cols = [
        "SPY", "QQQ", "IWM", "VGK", "EWJ", "EEM", "VNQ", "GLD", "DBC", "HYG", "LQD", "TLT",
        "IEF", "SHY", "BIL", "XLE", "XLV", "XLF", "XLK", "XLU", "XLP", "USMV", "QUAL",
    ]
    data = {}
    for col in cols:
        if col in ("SHY", "BIL", "IEF"):
            rets = rng.normal(0.00018, 0.001, size=n_days)
        else:
            rets = rng.normal(0.00045, 0.011, size=n_days)
        data[col] = 100.0 * np.cumprod(1.0 + rets)
    return pd.DataFrame(data, index=dates)


@pytest.mark.parametrize("rule_engine", sorted(ALLOWED_RULE_ENGINES))
def test_all_council_rule_engines_compile_and_obey_zero_lookahead(rule_engine: str) -> None:
    prices = _synthetic_council_prices(300)
    prices_shocked = prices.copy()
    cut = 270
    prices_shocked.iloc[cut + 1 :] = prices_shocked.iloc[cut + 1 :] * 5.0

    charter = {
        "rule_engine": rule_engine,
        "params": {
            "assets": ["SPY", "QQQ", "GLD", "DBC", "XLV", "USMV"],
            "risk_assets": ["SPY", "QQQ", "GLD", "DBC", "TLT", "VNQ"],
            "offensive_assets": ["GLD", "DBC", "XLE", "XLV", "USMV"],
            "tactical_assets": ["DBC", "GLD", "XLE", "XLV"],
            "safe_assets": ["SHY", "IEF"],
            "safe_asset": "SHY",
            "rebalance_freq": "M",
        },
    }
    fn = compile_council_weight_fn(charter)
    w_base = fn(prices.iloc[: cut + 1])
    w_shock = fn(prices_shocked.iloc[: cut + 1])
    pd.testing.assert_frame_equal(w_base, w_shock)
    # Weights must stay within [0, 1] and total <= 1.001
    assert float(w_base.min().min()) >= -1e-9
    assert float(w_base.sum(axis=1).max()) <= 1.001


def test_council_charter_registration_and_unified_paper_book_stepping(tmp_path: Path) -> None:
    prices = _synthetic_council_prices(310)
    raw = {
        "strategy_name": "Kalkan Vol-Target Test",
        "rule_engine": "vol_target_trend",
        "rebalance_mode": "monthly",
        "params": {"risk_assets": ["SPY", "GLD", "DBC", "XLV"], "safe_asset": "SHY", "target_vol_pct": 10},
        "thesis": "Volatilite kontrollü savunma ve trend.",
        "risk_rules": "SMA150 altında SHY.",
    }
    evaluated = evaluate_and_register_charter(
        "claude",
        raw,
        prices,
        model="claude-test",
        initial_capital=10_000.0,
        book_dir=tmp_path,
        today=prices.index[-1].date(),
    )
    assert evaluated["charter"]["rule_engine"] == "vol_target_trend"
    assert evaluated["book_summary"]["days"] == 1
    assert (tmp_path / "council_claude.json").is_file()

    save_council_charters({"members": {"claude": evaluated["charter"]}}, tmp_path)
    loaded = load_council_charters(tmp_path)
    assert "claude" in loaded["members"]

    # Unified quant paper status/step must automatically include registered council books
    status = get_quant_paper_books_status(strategies=["paa"], book_dir=tmp_path)
    keys = [b["strategy_key"] for b in status["books"]]
    assert "paa" in keys
    assert "council_claude" in keys

    stepped = step_quant_paper_books(
        strategies=["paa"],
        prices=prices,
        book_dir=tmp_path,
        today=prices.index[-1].date(),
    )
    assert stepped["ok"] is True
    assert "council_claude" in stepped["strategies"]


def test_extract_json_object_handles_fenced_and_prose_wrapped_payloads() -> None:
    assert _extract_json_object('{"a": 1}') == {"a": 1}
    assert _extract_json_object('```json\n{"strategy_name": "Test"}\n```') == {"strategy_name": "Test"}
    assert _extract_json_object('Özet:\n{"rule_engine": "paa_custom"}\nBitti.') == {"rule_engine": "paa_custom"}
