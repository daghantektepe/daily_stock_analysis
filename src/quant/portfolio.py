# -*- coding: utf-8 -*-
"""Meta-portfolio construction and simulated PAA/Champion forward paper book."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.quant.strategies.engine import (
    DEFAULT_OOS_START,
    StrategyResult,
    StrategySpec,
    combine_strategy_returns,
)

DEFAULT_QUANT_PAPER_PATH = Path("data") / "strategy_paper" / "quant_champion.json"


def build_meta_portfolios(
    base_results: Dict[str, StrategyResult],
    *,
    oos_start: str = DEFAULT_OOS_START,
    n_trials: int = 25,
    rf_returns: Optional[pd.Series] = None,
) -> Dict[str, StrategyResult]:
    """Construct Meta-Portfolio A (US Orthogonal ETF Ensemble) & Meta-Portfolio B (Global ETF + Crypto Trend)."""
    meta_results: Dict[str, StrategyResult] = {}

    # Meta-Portfolio A v2: Orthogonal Positive-Excess-Sharpe US ETF Ensemble
    # (35% PAA v2 + 25% QQQ Dual-SMA Hysteresis + 20% Safe-Haven Rotation + 20% Vol-Target Trend)
    meta_a_spec = StrategySpec(
        strategy_id="META_US_ETF_ALL_WEATHER",
        name="Meta-Portföy A v2 (ABD Ortogonal ETF Ensemble)",
        universe="meta",
        category="Meta-Portfolio",
        description="PAA v2 (%35) + QQQ Çift-SMA Histerezis (%25) + Safe-Haven Altın/Tahvil (%20) + Vol-Target Trend (%20) ortogonal ETF birleşimi.",
        cost_bps=5.0,
        trading_days_per_year=252,
    )
    meta_a_components = [
        (base_results[sid], w)
        for sid, w in (
            ("PROTECTIVE_ASSET_ALLOCATION_PAA", 0.35),
            ("QQQ_DUAL_SMA_50_200", 0.25),
            ("SAFE_HAVEN_ROTATION", 0.20),
            ("ETF_VOL_TARGET_TREND", 0.20),
        )
        if sid in base_results
    ]
    meta_a = combine_strategy_returns(
        meta_a_components,
        meta_a_spec,
        oos_start=oos_start,
        n_trials=n_trials,
        rf_returns=rf_returns,
    )
    meta_results[meta_a.strategy_id] = meta_a

    # Meta-Portfolio B: 80% Meta-Portfolio A + 20% Crypto 5-SMA Trend Ensemble
    meta_b_spec = StrategySpec(
        strategy_id="META_GLOBAL_ETF_CRYPTO_TREND",
        name="Meta-Portföy B (Küresel ETF + Kripto Trend)",
        universe="meta",
        category="Meta-Portfolio",
        description="%80 Meta-Portföy A (ABD Ortogonal ETF) + %20 Kripto 5-SMA Trend Ensemble (BTC+ETH).",
        cost_bps=7.0,
        trading_days_per_year=252,
    )
    meta_b_components = [(meta_a, 0.80)]
    if "CRYPTO_5SMA_ENSEMBLE" in base_results:
        meta_b_components.append((base_results["CRYPTO_5SMA_ENSEMBLE"], 0.20))
    meta_b = combine_strategy_returns(
        meta_b_components,
        meta_b_spec,
        oos_start=oos_start,
        n_trials=n_trials,
        rf_returns=rf_returns,
    )
    meta_results[meta_b.strategy_id] = meta_b

    return meta_results


def save_champion_paper_snapshot(
    champion: StrategyResult,
    *,
    meta_a: Optional[StrategyResult] = None,
    meta_b: Optional[StrategyResult] = None,
    initial_capital: float = 10_000.0,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist the latest simulated target allocation snapshot for the tournament champion (never real orders)."""
    target_path = Path(path or DEFAULT_QUANT_PAPER_PATH)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    existing: Dict[str, Any] = {}
    if target_path.is_file():
        try:
            loaded = json.loads(target_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, ValueError):
            existing = {}

    history: List[Dict[str, Any]] = list(existing.get("history") or [])
    entry = {
        "date": champion.latest_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "as_of_date": champion.latest_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "nav": round(float(existing.get("initial_capital_usd", initial_capital)), 2),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "champion_id": champion.strategy_id,
        "champion_weights_pct": dict(champion.current_weights),
        "champion_cash_pct": champion.cash_weight_pct,
        "meta_a_weights_pct": dict(meta_a.current_weights) if meta_a else {},
        "meta_b_weights_pct": dict(meta_b.current_weights) if meta_b else {},
    }
    if not history or history[-1].get("as_of_date") != entry["as_of_date"]:
        history.append(entry)
    else:
        history[-1] = entry

    state = {
        "simulated_only": True,
        "initial_capital_usd": float(existing.get("initial_capital_usd", initial_capital)),
        "champion_id": champion.strategy_id,
        "champion_name": champion.name,
        "latest": entry,
        "history": history[-365:],
    }

    fd, tmp_name = tempfile.mkstemp(dir=str(target_path.parent), prefix=".quant_champ_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_name, target_path)
    return state
