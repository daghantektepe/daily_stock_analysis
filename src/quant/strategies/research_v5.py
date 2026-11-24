# -*- coding: utf-8 -*-
"""Strategy Research v5: does correlation-aware (Min-Corr) sizing beat naive 1/vol? (pre-registered).

Two candidates share one multi-asset trend rule across the 10-asset macro universe
(SPY, QQQ, EFA, EEM, VNQ, TLT, IEF, GLD, DBC, UUP) plus BIL safe cash, and differ
ONLY in ``use_corr_penalty``:
- ``V5_MINCORR_TREND_RISK_PARITY`` (treatment, ``use_corr_penalty=True``): active
  uptrend assets are weighted proportional to ``max(0.10, 1 - avg_pairwise_corr_i) / vol_i``
  so crowded/collinear sleeves (e.g. SPY+QQQ+EFA+EEM moving together) are damped in
  favor of orthogonal diversifiers (GLD, DBC, TLT, IEF, UUP).
- ``V5_INVVOL_TREND_CONTROL`` (control, ``use_corr_penalty=False``): identical
  universe, identical trend filter, identical volatility target and cap, weighted
  by naive diagonal inverse-volatility ``1 / vol_i``.

Parameters below were fixed before any v5 backtest was run (textbook values:
SMA200, 252-day momentum > BIL, 63-day realized vol, 126-day pairwise correlation,
8 % target vol, 30 % single-asset cap, 8 % L1 monthly hysteresis).
This module must not import ``src/quant/strategies/library.py`` so frozen
PAA / Meta-A / v3_trp fingerprints stay untouched.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.quant.strategies.engine import StrategySpec
from src.quant.strategies.research_v3 import ResearchV3Candidate, _v3_month_start_positions

V5_RISK_ASSETS: Tuple[str, ...] = (
    "SPY", "QQQ", "EFA", "EEM", "VNQ", "TLT", "IEF", "GLD", "DBC", "UUP",
)
V5_SAFE_ASSET: str = "BIL"
MACRO_V5_UNIVERSE: Tuple[str, ...] = tuple(dict.fromkeys([*V5_RISK_ASSETS, V5_SAFE_ASSET]))


def compute_v5_mincorr_trend_weights(
    prices: pd.DataFrame,
    *,
    risk_assets: Sequence[str] = V5_RISK_ASSETS,
    safe_asset: str = V5_SAFE_ASSET,
    use_corr_penalty: bool = True,
    sma_window: int = 200,
    lookback: int = 252,
    vol_window: int = 63,
    corr_window: int = 126,
    target_vol: float = 0.08,
    max_single_weight: float = 0.30,
    hysteresis_l1: float = 0.08,
) -> pd.DataFrame:
    """Monthly trend-filtered risk parity with optional pairwise correlation penalty.

    Uptrend rule: ``close > SMA(sma_window)`` AND ``lookback``-day return > BIL's.
    Active assets receive base weights proportional to ``d_i / vol_i``, where
    ``d_i = max(0.10, 1 - mean_{j != i} corr(i, j))`` over trailing ``corr_window``
    days when ``use_corr_penalty=True`` (or ``d_i = 1.0`` for the naive 1/vol control).
    The active basket is capped per asset at ``max_single_weight`` and scaled down
    (never levered) when its trailing covariance volatility exceeds ``target_vol``;
    unused weight sits in ``safe_asset`` (BIL). Strictly causal (uses closes <= t).
    """
    assets = [a for a in risk_assets if a in prices.columns]
    has_safe = safe_asset in prices.columns
    cols = list(dict.fromkeys([*assets, *([safe_asset] if has_safe else [])]))
    if not assets or len(prices) == 0:
        return pd.DataFrame(0.0, index=prices.index, columns=cols)

    px = prices[assets]
    sma = px.rolling(int(sma_window), min_periods=int(sma_window)).mean()
    mom = px.pct_change(int(lookback))
    rf_mom = prices[safe_asset].pct_change(int(lookback)) if has_safe else pd.Series(0.0, index=prices.index)
    daily = prices[cols].pct_change()
    ann_vol = (
        daily[assets]
        .rolling(int(vol_window), min_periods=max(20, int(vol_window) // 2))
        .std(ddof=1)
        * np.sqrt(252.0)
    )

    col_idx = {c: i for i, c in enumerate(cols)}
    w_arr = np.full((len(prices), len(cols)), np.nan, dtype=float)
    warmup = max(int(sma_window), int(lookback), int(corr_window))
    prev_w: Optional[np.ndarray] = None

    for pos in _v3_month_start_positions(prices.index):
        row = np.zeros(len(cols), dtype=float)
        if pos < warmup:
            w_arr[pos, :] = row
            continue
        rf_val = float(rf_mom.iloc[pos]) if pd.notna(rf_mom.iloc[pos]) else 0.0
        eligible = [
            a
            for a in assets
            if pd.notna(sma[a].iloc[pos]) and pd.notna(mom[a].iloc[pos]) and pd.notna(ann_vol[a].iloc[pos])
        ]
        active = [
            a
            for a in eligible
            if float(px[a].iloc[pos]) > float(sma[a].iloc[pos]) and float(mom[a].iloc[pos]) > rf_val
        ]
        if not active:
            if has_safe:
                row[col_idx[safe_asset]] = 1.0
            w_arr[pos, :] = row
            prev_w = row
            continue

        corr_factors: Dict[str, float] = {a: 1.0 for a in active}
        if use_corr_penalty and len(active) >= 2:
            c_win = daily[active].iloc[max(0, pos - int(corr_window) + 1) : pos + 1].dropna(how="any")
            if len(c_win) >= max(20, int(corr_window) // 2):
                corr_mat = c_win.corr().fillna(0.0)
                for a in active:
                    others = [float(corr_mat.loc[a, b]) for b in active if b != a and np.isfinite(corr_mat.loc[a, b])]
                    avg_corr = float(np.mean(others)) if others else 0.0
                    corr_factors[a] = max(0.10, 1.0 - avg_corr)

        raw_scores = {
            a: corr_factors[a] / max(float(ann_vol[a].iloc[pos]), 0.04)
            for a in active
        }
        score_sum = sum(raw_scores.values())
        # Scale by fraction of eligible universe in uptrend so a single lone asset doesn't take 100%
        breadth_scale = len(active) / max(len(eligible), 1)
        sleeves: Dict[str, float] = {
            a: min(float(max_single_weight), (raw_scores[a] / score_sum) * breadth_scale)
            for a in active
            if score_sum > 0.0
        }

        if sleeves:
            names = list(sleeves)
            window = daily[names].iloc[max(0, pos - int(vol_window) + 1) : pos + 1].dropna(how="any")
            if len(window) >= max(10, int(vol_window) // 2):
                wv = np.array([sleeves[n] for n in names], dtype=float)
                port_vol = float(np.std(window.values @ wv, ddof=1)) * np.sqrt(252.0)
                if np.isfinite(port_vol) and port_vol > float(target_vol):
                    scale = float(target_vol) / port_vol
                    sleeves = {n: v * scale for n, v in sleeves.items()}
            gross = sum(sleeves.values())
            if gross > 1.0:
                sleeves = {n: v / gross for n, v in sleeves.items()}
                gross = 1.0
            for n, v in sleeves.items():
                row[col_idx[n]] = v
            if has_safe:
                row[col_idx[safe_asset]] = max(0.0, 1.0 - gross)
        elif has_safe:
            row[col_idx[safe_asset]] = 1.0

        if prev_w is not None and pos != len(prices) - 1 and float(np.abs(row - prev_w).sum()) < float(hysteresis_l1):
            row = prev_w.copy()
        w_arr[pos, :] = row
        prev_w = row

    return pd.DataFrame(w_arr, index=prices.index, columns=cols).ffill().fillna(0.0)


def compute_v5_invvol_trend_control_weights(prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """Same rule with correlation penalty switched off (pure 1/vol control)."""
    kwargs["use_corr_penalty"] = False
    return compute_v5_mincorr_trend_weights(prices, **kwargs)


_PLATEAU: Tuple[Dict[str, object], ...] = tuple(
    {"sma_window": sma, "target_vol": vol} for sma in (160, 200, 240) for vol in (0.065, 0.08, 0.095)
)


def build_v5_research_candidates() -> List[ResearchV3Candidate]:
    """The two pre-registered v5 candidates (Min-Corr treatment and 1/vol control)."""
    return [
        ResearchV3Candidate(
            spec=StrategySpec(
                strategy_id="V5_MINCORR_TREND_RISK_PARITY",
                name="v5 Korelasyon-Duyarlı (Min-Corr) Trend Risk Paritesi (BIL)",
                universe="macro_v3",
                category="Research v5 — Min-Corr Trend",
                description=(
                    "10 makro ETF + BIL: SMA200 ve 12A BIL üstü momentum filtresini geçen varlıkları "
                    "(1 - ort. korelasyon) / volatilite ile ağırlıklandırır (%8 hedef vol, %30 tavan)."
                ),
                cost_bps=5.0,
                builder=compute_v5_mincorr_trend_weights,
            ),
            universe_key="macro_v3",
            builder=compute_v5_mincorr_trend_weights,
            plateau_grid=_PLATEAU,
        ),
        ResearchV3Candidate(
            spec=StrategySpec(
                strategy_id="V5_INVVOL_TREND_CONTROL",
                name="v5 Basit Ters-Volatilite (1/vol) Kontrol (korelasyon cezası kapalı)",
                universe="macro_v3",
                category="Research v5 — Control",
                description=(
                    "Aynı 10 makro ETF, aynı trend kuralı ve aynı %8 hedef volatilite; yalnızca korelasyon "
                    "cezası kapalı (saf 1/vol). Min-Corr ağırlıklandırmanın katkısını ölçmek için kontrol grubu."
                ),
                cost_bps=5.0,
                builder=compute_v5_invvol_trend_control_weights,
            ),
            universe_key="macro_v3",
            builder=compute_v5_invvol_trend_control_weights,
            plateau_grid=_PLATEAU,
        ),
    ]
