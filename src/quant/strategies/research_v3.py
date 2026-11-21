# -*- coding: utf-8 -*-
"""Pre-registered Strategy Research v3 (Priority D) orthogonal ETF sleeves.

STRICT ISOLATION INVARIANT:
- This module MUST NOT import from or modify ``src/quant/strategies/library.py``
  so the SHA-256 fingerprints of frozen ``PAA v2`` and ``Meta-Portfolio A v2``
  in ``src/quant/forward_validation.py`` remain 100% untouched.
- Every strategy here uses pre-registered textbook academic parameters (zero
  in-sample parameter optimization) and strictly causal trailing closes ``<= t``
  (the backtest engine applies the 1-bar execution shift).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.quant.strategies.engine import StrategySpec

V3_TSMOM_RISK_ASSETS: tuple[str, ...] = ("SPY", "EFA", "TLT", "IEF", "GLD", "DBC", "UUP")
V3_TRP_RISK_ASSETS: tuple[str, ...] = ("SPY", "TLT", "IEF", "GLD", "DBC", "UUP")
V3_SECTOR_FACTOR_ASSETS: tuple[str, ...] = (
    "XLK", "XLV", "XLF", "XLE", "XLI", "XLP", "XLU", "XLY", "XLB", "XLC", "XLRE",
    "MTUM", "QUAL", "USMV", "VLUE",
)
V3_SAFE_ASSET: str = "BIL"


def _v3_month_start_positions(index: pd.DatetimeIndex) -> List[int]:
    """Causal first trading day of each calendar month (+ final row for live signal)."""
    if len(index) == 0:
        return []
    periods = pd.Series(index.to_period("M"), index=index)
    mask = periods.ne(periods.shift(1)).fillna(False)
    positions = list(np.flatnonzero(mask.values))
    if not positions or positions[-1] != len(index) - 1:
        positions.append(len(index) - 1)
    return positions


# ---------------------------------------------------------------------------
# V3-1: Cross-Asset Time-Series Momentum / Managed Futures Proxy
# Academic basis: Moskowitz, Ooi & Pedersen (2012, JFE); Hurst et al. (2017, AQR)
# ---------------------------------------------------------------------------


def compute_v3_tsmom_cross_asset_weights(
    prices: pd.DataFrame,
    *,
    risk_assets: Sequence[str] = V3_TSMOM_RISK_ASSETS,
    safe_asset: str = V3_SAFE_ASSET,
    lookbacks: Sequence[int] = (21, 63, 126, 252),
    vol_window: int = 63,
    target_vol: float = 0.10,
    max_single_weight: float = 0.30,
) -> pd.DataFrame:
    """Long-only cross-asset multi-horizon TSMOM across 5 asset classes + BIL cash.

    Pre-registered rules (zero tuning):
    - 5 asset classes: Equities (SPY, EFA), Sovereign Bonds (TLT, IEF),
      Gold (GLD), Broad Commodities (DBC), and US Dollar (UUP).
    - Signal strength = fraction of lookbacks (1M/3M/6M/12M) where trailing asset
      return exceeds trailing BIL T-Bill return (continuous in [0, 1]).
    - Equal risk-budget inverse-volatility sizing (63d realized vol, 4% floor),
      scaled to ``target_vol`` (10%), capped at ``max_single_weight`` (30%) and
      100% gross exposure; unused risk budget earns BIL yield.
    """
    risk_cols = [c for c in risk_assets if c in prices.columns]
    has_safe = safe_asset in prices.columns
    all_cols = list(dict.fromkeys([*risk_cols, *([safe_asset] if has_safe else [])]))
    if not risk_cols or len(prices) == 0:
        return pd.DataFrame(0.0, index=prices.index, columns=all_cols)

    max_lb = max(int(lb) for lb in lookbacks)
    daily_rets = prices[all_cols].pct_change()
    ann_vol = daily_rets[risk_cols].rolling(int(vol_window), min_periods=max(20, int(vol_window) // 2)).std(ddof=1) * np.sqrt(252.0)

    # Multi-horizon excess-over-BIL signal matrix in [0, 1]
    sig_sum = pd.DataFrame(0.0, index=prices.index, columns=risk_cols)
    sig_cnt = pd.DataFrame(0.0, index=prices.index, columns=risk_cols)
    for lb in lookbacks:
        h = max(5, int(lb))
        r_assets = prices[risk_cols].pct_change(h)
        if has_safe:
            r_rf = prices[safe_asset].pct_change(h)
            ex = r_assets.sub(r_rf, axis=0)
        else:
            ex = r_assets
        valid = ex.notna()
        sig_sum = sig_sum.add((ex > 0.0).astype(float).where(valid, 0.0), fill_value=0.0)
        sig_cnt = sig_cnt.add(valid.astype(float), fill_value=0.0)
    signal = (sig_sum / sig_cnt.replace(0.0, np.nan)).fillna(0.0)

    col_idx = {c: i for i, c in enumerate(all_cols)}
    w_arr = np.full((len(prices), len(all_cols)), np.nan, dtype=float)
    positions = _v3_month_start_positions(prices.index)

    for pos in positions:
        if pos < max_lb:
            w_arr[pos, :] = 0.0
            continue
        row_sig = signal.iloc[pos]
        row_vol = ann_vol.iloc[pos]
        eligible = [c for c in risk_cols if pd.notna(row_vol[c]) and pd.notna(prices[c].iloc[pos])]
        row_w = np.zeros(len(all_cols), dtype=float)
        if len(eligible) < 3:
            if has_safe and pd.notna(prices[safe_asset].iloc[pos]):
                row_w[col_idx[safe_asset]] = 1.0
            w_arr[pos, :] = row_w
            continue

        n_elig = float(len(eligible))
        per_asset_vol_budget = float(target_vol) / np.sqrt(n_elig)
        # Conservative equal-risk allocation scaled by 1/N (no leverage)
        raw_risky: Dict[str, float] = {}
        for sym in eligible:
            s_val = float(row_sig[sym])
            if s_val <= 0.0:
                continue
            v_val = max(float(row_vol[sym]), 0.04)
            # Standard equal-risk-budget TSMOM weight: signal * (target_vol / N) / vol_i
            w_i = s_val * (per_asset_vol_budget / v_val)
            raw_risky[sym] = min(float(max_single_weight), max(0.0, w_i))

        gross = sum(raw_risky.values())
        if gross > 1.0:
            scale = 1.0 / gross
            raw_risky = {k: v * scale for k, v in raw_risky.items()}
            gross = 1.0

        for sym, wt in raw_risky.items():
            row_w[col_idx[sym]] = wt
        if has_safe and pd.notna(prices[safe_asset].iloc[pos]):
            row_w[col_idx[safe_asset]] = max(0.0, 1.0 - gross)
        w_arr[pos, :] = row_w

    return pd.DataFrame(w_arr, index=prices.index, columns=all_cols).ffill().fillna(0.0)


# ---------------------------------------------------------------------------
# V3-2: Volatility-Managed Trend-Filtered Risk Parity + BIL
# Academic basis: Moreira & Muir (2017, JF) + Baltas & Kosowski (2020)
# ---------------------------------------------------------------------------


def compute_v3_trend_risk_parity_bil_weights(
    prices: pd.DataFrame,
    *,
    risk_assets: Sequence[str] = V3_TRP_RISK_ASSETS,
    safe_asset: str = V3_SAFE_ASSET,
    sma_window: int = 200,
    vol_window: int = 63,
    fast_vol_window: int = 21,
    target_vol: float = 0.08,
    max_single_weight: float = 0.35,
    hysteresis_l1: float = 0.10,
) -> pd.DataFrame:
    """Trend-gated inverse-volatility Risk Parity with Moreira-Muir 21d vol brake & BIL cash.

    Pre-registered rules (zero tuning):
    - Macro pillars: SPY, TLT, IEF, GLD, DBC, UUP.
    - Asset qualifies only if ``close > SMA(sma_window)`` AND ``252d return > BIL``.
    - Qualifying assets receive inverse-63d-vol weights scaled by breadth
      (``n_pass / n_eligible``) and capped at ``max_single_weight`` (35%).
    - Moreira-Muir realized-variance brake: if trailing 21d portfolio vol exceeds
      ``target_vol`` (8%), scale risky sleeve by ``target_vol / port_vol_21d``.
    - Unused capital parks in BIL; 10% L1 drift hysteresis avoids tiny rebalances.
    """
    risk_cols = [c for c in risk_assets if c in prices.columns]
    has_safe = safe_asset in prices.columns
    all_cols = list(dict.fromkeys([*risk_cols, *([safe_asset] if has_safe else [])]))
    if not risk_cols or len(prices) == 0:
        return pd.DataFrame(0.0, index=prices.index, columns=all_cols)

    sma = prices[risk_cols].rolling(int(sma_window), min_periods=int(sma_window)).mean()
    ret252 = prices[risk_cols].pct_change(252)
    rf252 = prices[safe_asset].pct_change(252) if has_safe else pd.Series(0.0, index=prices.index)
    daily_rets = prices[risk_cols].pct_change()
    ann_vol = daily_rets.rolling(int(vol_window), min_periods=max(20, int(vol_window) // 2)).std(ddof=1) * np.sqrt(252.0)

    col_idx = {c: i for i, c in enumerate(all_cols)}
    w_arr = np.full((len(prices), len(all_cols)), np.nan, dtype=float)
    positions = _v3_month_start_positions(prices.index)
    warmup = max(252, int(sma_window))
    prev_w: Optional[np.ndarray] = None

    for pos in positions:
        if pos < warmup:
            w_arr[pos, :] = 0.0
            continue
        eligible = [
            c for c in risk_cols
            if pd.notna(sma[c].iloc[pos]) and pd.notna(ret252[c].iloc[pos]) and pd.notna(ann_vol[c].iloc[pos])
        ]
        row_w = np.zeros(len(all_cols), dtype=float)
        if not eligible:
            if has_safe and pd.notna(prices[safe_asset].iloc[pos]):
                row_w[col_idx[safe_asset]] = 1.0
            w_arr[pos, :] = row_w
            prev_w = row_w
            continue

        rf_val = float(rf252.iloc[pos]) if pd.notna(rf252.iloc[pos]) else 0.0
        passing = [
            c for c in eligible
            if float(prices[c].iloc[pos]) > float(sma[c].iloc[pos])
            and float(ret252[c].iloc[pos]) > rf_val
        ]

        if passing:
            breadth = len(passing) / float(len(eligible))
            inv_vols = {c: 1.0 / max(float(ann_vol[c].iloc[pos]), 0.04) for c in passing}
            inv_sum = sum(inv_vols.values())
            cand = {c: min(float(max_single_weight), breadth * (v / inv_sum)) for c, v in inv_vols.items()}

            # Moreira-Muir 21-day realized portfolio volatility brake
            win_rets = daily_rets[passing].iloc[max(0, pos - int(fast_vol_window) + 1) : pos + 1].dropna(how="any")
            if len(win_rets) >= max(10, int(fast_vol_window) // 2):
                w_vec = np.array([cand[c] for c in passing], dtype=float)
                port_daily = win_rets.values @ w_vec
                port_vol_ann = float(np.std(port_daily, ddof=1)) * np.sqrt(252.0)
                if np.isfinite(port_vol_ann) and port_vol_ann > float(target_vol):
                    scale = float(target_vol) / port_vol_ann
                    cand = {c: wt * scale for c, wt in cand.items()}

            gross = sum(cand.values())
            if gross > 1.0:
                cand = {c: wt / gross for c, wt in cand.items()}
                gross = 1.0
            for c, wt in cand.items():
                row_w[col_idx[c]] = wt
            if has_safe and pd.notna(prices[safe_asset].iloc[pos]):
                row_w[col_idx[safe_asset]] = max(0.0, 1.0 - gross)
        elif has_safe and pd.notna(prices[safe_asset].iloc[pos]):
            row_w[col_idx[safe_asset]] = 1.0

        # Apply L1 hysteresis band (except on final live signal row)
        if prev_w is not None and pos != len(prices) - 1:
            l1_diff = float(np.abs(row_w - prev_w).sum())
            if l1_diff < float(hysteresis_l1):
                row_w = prev_w.copy()

        w_arr[pos, :] = row_w
        prev_w = row_w

    return pd.DataFrame(w_arr, index=prices.index, columns=all_cols).ffill().fillna(0.0)


# ---------------------------------------------------------------------------
# V3-3: Breadth-Adaptive Sector + Factor Risk-Adjusted Momentum + BIL
# Academic basis: Blitz, Huij & Martens (2011) + Keller & Keuning (2016)
# ---------------------------------------------------------------------------


def compute_v3_sector_factor_breadth_bil_weights(
    prices: pd.DataFrame,
    *,
    risk_assets: Sequence[str] = V3_SECTOR_FACTOR_ASSETS,
    safe_asset: str = V3_SAFE_ASSET,
    sma_window: int = 200,
    mom_lookback: int = 126,
    skip_days: int = 21,
    vol_window: int = 63,
    top_n: int = 3,
    protection_factor: float = 1.0,
) -> pd.DataFrame:
    """Inception-aware US Sector + Factor volatility-adjusted momentum with breadth shield & BIL.

    Pre-registered rules (zero tuning):
    - Dynamic inception: at each monthly rebalance date ``t``, only ETFs with at least
      252 valid trailing closes enter the eligible pool (zero survivorship / lookahead).
    - Trend filter: ``close > SMA(200)`` AND ``mom_lookback return > BIL``.
    - Breadth shield: ``bf = min(1.0, protection_factor * n_bad / n_eligible)``.
    - Ranking score: risk-adjusted 6-1M momentum ``(P_{t-21}/P_{t-126} - 1) / sigma_63d``.
    - Remaining ``(1 - bf)`` allocated equally to ``top_n=3`` leaders; ``bf`` parked in BIL.
    """
    risk_cols = [c for c in risk_assets if c in prices.columns]
    has_safe = safe_asset in prices.columns
    all_cols = list(dict.fromkeys([*risk_cols, *([safe_asset] if has_safe else [])]))
    if not risk_cols or len(prices) == 0:
        return pd.DataFrame(0.0, index=prices.index, columns=all_cols)

    sma = prices[risk_cols].rolling(int(sma_window), min_periods=int(sma_window)).mean()
    # Dynamic inception eligibility: require >= 252 valid closes up to t
    valid_hist = prices[risk_cols].notna().rolling(252, min_periods=252).sum() >= 252
    ret_mom = prices[risk_cols].pct_change(int(mom_lookback))
    rf_mom = prices[safe_asset].pct_change(int(mom_lookback)) if has_safe else pd.Series(0.0, index=prices.index)
    # 6-1M skip-month return: P_{t - skip} / P_{t - mom_lookback} - 1
    skip_k = max(1, min(int(skip_days), int(mom_lookback) - 20))
    ret_6_1 = (prices[risk_cols].shift(skip_k) / prices[risk_cols].shift(int(mom_lookback))) - 1.0
    ann_vol = prices[risk_cols].pct_change().rolling(int(vol_window), min_periods=max(20, int(vol_window) // 2)).std(ddof=1) * np.sqrt(252.0)

    col_idx = {c: i for i, c in enumerate(all_cols)}
    w_arr = np.full((len(prices), len(all_cols)), np.nan, dtype=float)
    positions = _v3_month_start_positions(prices.index)
    warmup = max(252, int(sma_window), int(mom_lookback) + 5)

    for pos in positions:
        if pos < warmup:
            w_arr[pos, :] = 0.0
            continue
        eligible = [
            c for c in risk_cols
            if bool(valid_hist[c].iloc[pos])
            and pd.notna(sma[c].iloc[pos])
            and pd.notna(ret_mom[c].iloc[pos])
            and pd.notna(ret_6_1[c].iloc[pos])
            and pd.notna(ann_vol[c].iloc[pos])
        ]
        row_w = np.zeros(len(all_cols), dtype=float)
        if len(eligible) < 3:
            if has_safe and pd.notna(prices[safe_asset].iloc[pos]):
                row_w[col_idx[safe_asset]] = 1.0
            w_arr[pos, :] = row_w
            continue

        rf_val = float(rf_mom.iloc[pos]) if pd.notna(rf_mom.iloc[pos]) else 0.0
        good: List[Tuple[str, float]] = []
        for c in eligible:
            px = float(prices[c].iloc[pos])
            if px > float(sma[c].iloc[pos]) and float(ret_mom[c].iloc[pos]) > rf_val:
                vol_c = max(float(ann_vol[c].iloc[pos]), 0.05)
                score = float(ret_6_1[c].iloc[pos]) / vol_c
                good.append((c, score))

        n_bad = len(eligible) - len(good)
        bf = min(1.0, (float(protection_factor) * n_bad) / float(len(eligible)))
        if bf >= 0.999 or not good:
            if has_safe and pd.notna(prices[safe_asset].iloc[pos]):
                row_w[col_idx[safe_asset]] = 1.0
        else:
            good.sort(key=lambda kv: kv[1], reverse=True)
            chosen = good[: min(int(top_n), len(good))]
            each = (1.0 - bf) / float(len(chosen))
            for sym, _ in chosen:
                row_w[col_idx[sym]] = each
            if has_safe and pd.notna(prices[safe_asset].iloc[pos]):
                row_w[col_idx[safe_asset]] = bf
        w_arr[pos, :] = row_w

    return pd.DataFrame(w_arr, index=prices.index, columns=all_cols).ffill().fillna(0.0)


@dataclass(frozen=True)
class ResearchV3Candidate:
    """Pre-registered v3 strategy candidate with its plateau neighbor grid."""

    spec: StrategySpec
    universe_key: str  # "macro_v3" | "sector_factor_v3"
    builder: Callable[..., pd.DataFrame]
    plateau_grid: Tuple[Dict[str, object], ...]


def build_v3_research_candidates() -> List[ResearchV3Candidate]:
    """Return all 3 pre-registered v3 candidates with fixed ±20% plateau stability grids."""
    return [
        ResearchV3Candidate(
            spec=StrategySpec(
                strategy_id="V3_TSMOM_CROSS_ASSET",
                name="v3 Çapraz-Varlık TSMOM / Managed Futures Vekili (BIL)",
                universe="macro_v3",
                category="Research v3 — Cross-Asset Trend",
                description=(
                    "5 varlık sınıfında (SPY/EFA, TLT/IEF, GLD, DBC, UUP) 1-3-6-12A BIL üstü "
                    "sürekli zaman serisi momentum + 63G ters-volatilite (%10 hedef vol) + BIL nakit."
                ),
                cost_bps=5.0,
                builder=compute_v3_tsmom_cross_asset_weights,
            ),
            universe_key="macro_v3",
            builder=compute_v3_tsmom_cross_asset_weights,
            plateau_grid=(
                {"lookbacks": (17, 50, 100, 200), "target_vol": 0.08},
                {"lookbacks": (17, 50, 100, 200), "target_vol": 0.10},
                {"lookbacks": (17, 50, 100, 200), "target_vol": 0.12},
                {"lookbacks": (21, 63, 126, 252), "target_vol": 0.08},
                {"lookbacks": (21, 63, 126, 252), "target_vol": 0.10},
                {"lookbacks": (21, 63, 126, 252), "target_vol": 0.12},
                {"lookbacks": (25, 76, 151, 302), "target_vol": 0.08},
                {"lookbacks": (25, 76, 151, 302), "target_vol": 0.10},
                {"lookbacks": (25, 76, 151, 302), "target_vol": 0.12},
            ),
        ),
        ResearchV3Candidate(
            spec=StrategySpec(
                strategy_id="V3_TREND_RISK_PARITY_BIL",
                name="v3 Vol-Yönetimli Trend-Frenli Risk Paritesi (BIL)",
                universe="macro_v3",
                category="Research v3 — Vol-Managed Risk Parity",
                description=(
                    "SPY/TLT/IEF/GLD/DBC/UUP makro havuzunda SMA200 + BIL trend filtresi, "
                    "ters-volatilite ağırlığı, Moreira-Muir 21G volatilite freni (%8) ve %10 histerezis."
                ),
                cost_bps=5.0,
                builder=compute_v3_trend_risk_parity_bil_weights,
            ),
            universe_key="macro_v3",
            builder=compute_v3_trend_risk_parity_bil_weights,
            plateau_grid=(
                {"sma_window": 160, "target_vol": 0.064},
                {"sma_window": 160, "target_vol": 0.080},
                {"sma_window": 160, "target_vol": 0.096},
                {"sma_window": 200, "target_vol": 0.064},
                {"sma_window": 200, "target_vol": 0.080},
                {"sma_window": 200, "target_vol": 0.096},
                {"sma_window": 240, "target_vol": 0.064},
                {"sma_window": 240, "target_vol": 0.080},
                {"sma_window": 240, "target_vol": 0.096},
            ),
        ),
        ResearchV3Candidate(
            spec=StrategySpec(
                strategy_id="V3_SECTOR_FACTOR_BREADTH_BIL",
                name="v3 Genişlik-Kalkanlı Sektör & Faktör Risk-Ayarlı Momentum (BIL)",
                universe="sector_factor_v3",
                category="Research v3 — Equity Sector/Factor",
                description=(
                    "Dinamik kuruluş filtreli 11 S&P sektörü + 4 faktör (MTUM/QUAL/USMV/VLUE) "
                    "havuzunda SMA200 + 6-1A risk-ayarlı momentum Top-3 + doğrusal genişlik kalkanı (BIL)."
                ),
                cost_bps=6.0,
                builder=compute_v3_sector_factor_breadth_bil_weights,
            ),
            universe_key="sector_factor_v3",
            builder=compute_v3_sector_factor_breadth_bil_weights,
            plateau_grid=(
                {"sma_window": 160, "protection_factor": 0.8},
                {"sma_window": 160, "protection_factor": 1.0},
                {"sma_window": 160, "protection_factor": 1.2},
                {"sma_window": 200, "protection_factor": 0.8},
                {"sma_window": 200, "protection_factor": 1.0},
                {"sma_window": 200, "protection_factor": 1.2},
                {"sma_window": 240, "protection_factor": 0.8},
                {"sma_window": 240, "protection_factor": 1.0},
                {"sma_window": 240, "protection_factor": 1.2},
            ),
        ),
    ]
