# -*- coding: utf-8 -*-
"""Strategy Research v4: does a short sleeve add value? (pre-registered).

Short exposure is taken ONLY by buying inverse ETFs (SH, PSQ, EFZ, TBF):
- no margin account, no share borrowing, no options;
- the maximum loss of a position is the money put into it (unlike a real short);
- real inverse-ETF prices already include daily-reset decay and the ~0.9 %/yr fee,
  so the backtest does not flatter the short side.

Two candidates share one rule and differ only in ``allow_short``:
- ``V4_TREND_LONG_SHORT_INVERSE``: uptrend -> hold the asset, downtrend -> hold its
  inverse ETF (if one exists), otherwise BIL.
- ``V4_TREND_LONG_ONLY_CONTROL``: identical, but a downtrend always means BIL.
The difference between them is the honest answer to "does shorting help?".

Parameters below were fixed before any v4 backtest was run (textbook values:
SMA200, 12-month absolute momentum vs BIL, 63-day inverse volatility, 10 % vol
target, 30 % position cap, 10 % L1 hysteresis). This module must not import
``src/quant/strategies/library.py`` so the frozen PAA / Meta-A fingerprints stay
untouched.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.quant.strategies.engine import StrategySpec
from src.quant.strategies.research_v3 import ResearchV3Candidate, _v3_month_start_positions

# (asset, inverse ETF or None). Inverse ETFs: SH -1x S&P 500, PSQ -1x Nasdaq-100,
# EFZ -1x MSCI EAFE, TBF -1x 20+ year Treasuries. Gold, commodities and 7-10y
# Treasuries have no liquid long-lived -1x ETF, so they can only be long or flat.
V4_PILLARS: Tuple[Tuple[str, Optional[str]], ...] = (
    ("SPY", "SH"),
    ("QQQ", "PSQ"),
    ("EFA", "EFZ"),
    ("TLT", "TBF"),
    ("IEF", None),
    ("GLD", None),
    ("DBC", None),
)
V4_SAFE_ASSET = "BIL"
V4_INVERSE_ETFS: Tuple[str, ...] = tuple(inv for _, inv in V4_PILLARS if inv)
LONGSHORT_V4_UNIVERSE: Tuple[str, ...] = tuple(
    dict.fromkeys([*(a for a, _ in V4_PILLARS), *V4_INVERSE_ETFS, V4_SAFE_ASSET])
)


def compute_v4_trend_long_short_weights(
    prices: pd.DataFrame,
    *,
    pillars: Sequence[Tuple[str, Optional[str]]] = V4_PILLARS,
    safe_asset: str = V4_SAFE_ASSET,
    allow_short: bool = True,
    sma_window: int = 200,
    lookback: int = 252,
    vol_window: int = 63,
    target_vol: float = 0.10,
    max_single_weight: float = 0.30,
    hysteresis_l1: float = 0.10,
) -> pd.DataFrame:
    """Monthly trend rule that goes long the asset in uptrends and long its inverse ETF in downtrends.

    Uptrend: close > SMA(sma_window) AND ``lookback``-day return > BIL's.
    Downtrend: close < SMA AND return < BIL (both must agree, to limit whipsaw).
    Each active sleeve gets inverse-volatility weight over all pillars with data,
    capped at ``max_single_weight``; the book is scaled down (never levered) when
    its trailing ``vol_window`` volatility exceeds ``target_vol``. The rest is BIL.
    Uses only closes <= t; the engine executes at t+1.
    """
    assets = [a for a, _ in pillars if a in prices.columns]
    inverse_of: Dict[str, Optional[str]] = {
        a: (inv if (allow_short and inv and inv in prices.columns) else None) for a, inv in pillars if a in assets
    }
    has_safe = safe_asset in prices.columns
    cols = list(dict.fromkeys([*assets, *(v for v in inverse_of.values() if v), *([safe_asset] if has_safe else [])]))
    if not assets or len(prices) == 0:
        return pd.DataFrame(0.0, index=prices.index, columns=cols)

    px = prices[assets]
    sma = px.rolling(int(sma_window), min_periods=int(sma_window)).mean()
    mom = px.pct_change(int(lookback))
    rf_mom = prices[safe_asset].pct_change(int(lookback)) if has_safe else pd.Series(0.0, index=prices.index)
    daily = prices[cols].pct_change()
    ann_vol = daily[assets].rolling(int(vol_window), min_periods=max(20, int(vol_window) // 2)).std(ddof=1) * np.sqrt(252.0)

    col_idx = {c: i for i, c in enumerate(cols)}
    w_arr = np.full((len(prices), len(cols)), np.nan, dtype=float)
    warmup = max(int(sma_window), int(lookback))
    prev_w: Optional[np.ndarray] = None

    for pos in _v3_month_start_positions(prices.index):
        row = np.zeros(len(cols), dtype=float)
        if pos < warmup:
            w_arr[pos, :] = row
            continue
        rf_val = float(rf_mom.iloc[pos]) if pd.notna(rf_mom.iloc[pos]) else 0.0
        eligible = [
            a for a in assets
            if pd.notna(sma[a].iloc[pos]) and pd.notna(mom[a].iloc[pos]) and pd.notna(ann_vol[a].iloc[pos])
        ]
        if not eligible:
            if has_safe:
                row[col_idx[safe_asset]] = 1.0
            w_arr[pos, :] = row
            prev_w = row
            continue

        inv_vol = {a: 1.0 / max(float(ann_vol[a].iloc[pos]), 0.04) for a in eligible}
        inv_sum = sum(inv_vol.values())
        sleeves: Dict[str, float] = {}
        for a in eligible:
            price = float(px[a].iloc[pos])
            up = price > float(sma[a].iloc[pos]) and float(mom[a].iloc[pos]) > rf_val
            down = price < float(sma[a].iloc[pos]) and float(mom[a].iloc[pos]) < rf_val
            base = min(float(max_single_weight), inv_vol[a] / inv_sum)
            if up:
                sleeves[a] = base
            elif down and inverse_of.get(a) and pd.notna(prices[inverse_of[a]].iloc[pos]):
                sleeves[inverse_of[a]] = base

        if sleeves:
            names = list(sleeves)
            window = daily[names].iloc[max(0, pos - int(vol_window) + 1): pos + 1].dropna(how="any")
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


def compute_v4_trend_long_only_control_weights(prices: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """Same rule with the short sleeve switched off (downtrend -> BIL)."""
    kwargs["allow_short"] = False
    return compute_v4_trend_long_short_weights(prices, **kwargs)


_PLATEAU: Tuple[Dict[str, object], ...] = tuple(
    {"sma_window": sma, "target_vol": vol} for sma in (160, 200, 240) for vol in (0.08, 0.10, 0.12)
)


def build_v4_research_candidates() -> List[ResearchV3Candidate]:
    """The two pre-registered v4 candidates (long/short and its long-only control)."""
    return [
        ResearchV3Candidate(
            spec=StrategySpec(
                strategy_id="V4_TREND_LONG_SHORT_INVERSE",
                name="v4 Trend Long/Short (Ters ETF ile, kaldıraçsız)",
                universe="longshort_v4",
                category="Research v4 — Long/Short Trend",
                description=(
                    "SPY/QQQ/EFA/TLT/IEF/GLD/DBC: yükselişte varlığın kendisi, düşüşte ters ETF'i "
                    "(SH/PSQ/EFZ/TBF), aksi halde BIL. SMA200 + 12A BIL üstü momentum, ters-volatilite, %10 hedef vol."
                ),
                cost_bps=5.0,
                builder=compute_v4_trend_long_short_weights,
            ),
            universe_key="longshort_v4",
            builder=compute_v4_trend_long_short_weights,
            plateau_grid=_PLATEAU,
        ),
        ResearchV3Candidate(
            spec=StrategySpec(
                strategy_id="V4_TREND_LONG_ONLY_CONTROL",
                name="v4 Trend Long-Only Kontrol (short kapalı)",
                universe="longshort_v4",
                category="Research v4 — Control",
                description="Aynı kural; düşüş trendinde ters ETF yerine BIL. Short'un katkısını ölçmek için kontrol grubu.",
                cost_bps=5.0,
                builder=compute_v4_trend_long_only_control_weights,
            ),
            universe_key="longshort_v4",
            builder=compute_v4_trend_long_only_control_weights,
            plateau_grid=_PLATEAU,
        ),
    ]
