# -*- coding: utf-8 -*-
"""Library of 25 empirically grounded multi-universe quantitative strategies.

All weight builders compute target allocations using strictly trailing closes
``<= t``; the backtest engine shifts them by 1 bar (zero lookahead).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from src.quant.data_loader import US_ETF_RISK_ASSETS, US_ETF_SAFE_ASSETS
from src.quant.strategies.engine import (
    DEFAULT_OOS_START,
    StrategyResult,
    StrategySpec,
    backtest_weight_matrix,
)


def _month_end_mask(index: pd.DatetimeIndex) -> pd.Series:
    """True on the last trading day of each calendar month (computed causally by next-day month jump? No—causal!).

    To stay 100% causal (zero lookahead about tomorrow's calendar), we rebalance
    on the FIRST trading day of each new month using the previous bar's close
    (which is equivalent to end-of-month close execution on the first trading
    day of the new month!).
    """
    periods = pd.Series(index.to_period("M"), index=index)
    return periods.ne(periods.shift(1)).fillna(False)


def _causal_rebalance(weights: pd.DataFrame, freq: str = "M") -> pd.DataFrame:
    """Hold weights constant between causal rebalance dates (month-start or week-start)."""
    if weights.empty:
        return weights
    idx = weights.index
    if freq == "W":
        periods = pd.Series(idx.to_period("W"), index=idx)
    else:
        periods = pd.Series(idx.to_period("M"), index=idx)
    rebal = periods.ne(periods.shift(1)).fillna(True)
    # Keep only rows on rebalance days, forward-fill until next rebalance
    out = weights.where(rebal, np.nan).ffill().fillna(0.0)
    # Also compute live signal for the final row so current_weights reflects today's live close
    if len(weights) > 0:
        out.iloc[-1] = weights.iloc[-1]
    return out


def _momentum_13612w(prices: pd.DataFrame) -> pd.DataFrame:
    """Keller-Keuning 13612W weighted momentum score: 12*r1m + 4*r3m + 2*r6m + 1*r12m."""
    r1 = prices.pct_change(21)
    r3 = prices.pct_change(63)
    r6 = prices.pct_change(126)
    r12 = prices.pct_change(252)
    return 12.0 * r1 + 4.0 * r3 + 2.0 * r6 + 1.0 * r12


def _rsi(series: pd.Series, period: int = 2) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0).rolling(period, min_periods=period).mean()
    loss = (-delta.clip(upper=0.0)).rolling(period, min_periods=period).mean()
    rs = gain / loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


# ---------------------------------------------------------------------------
# 1. Protective Asset Allocation (PAA — Keller & Keuning 2016)
# ---------------------------------------------------------------------------


def compute_paa_weights(
    prices: pd.DataFrame,
    *,
    risk_assets: Sequence[str] = US_ETF_RISK_ASSETS,
    safe_assets: Sequence[str] = ("IEF", "SHY"),
    lookback_days: int = 252,
    top_n: int = 6,
    protection_factor: float = 2.0,
) -> pd.DataFrame:
    """Protective Asset Allocation (PAA) crash-shield strategy.

    At each monthly rebalance (and latest close):
    - Momentum of each risk asset = ``close / SMA(252) - 1``.
    - Breadth crash shield: count ``n_bad`` of risky assets with momentum <= 0.
    - Crash protection fraction ``bf = min(1.0, protection_factor * n_bad / n_risk)``.
      With 12 risk ETFs and ``protection_factor=2.0``, >=6 risky ETFs below SMA252
      triggers 100% defensive shift into the strongest safe bond/cash ETF (``IEF``/``SHY``).
    - Remaining ``(1 - bf)`` is allocated equally across the top ``top_n`` positive-momentum risky ETFs.
    """
    risk_cols = [c for c in risk_assets if c in prices.columns]
    safe_cols = [c for c in safe_assets if c in prices.columns]
    all_cols = list(dict.fromkeys([*risk_cols, *safe_cols]))
    w = pd.DataFrame(0.0, index=prices.index, columns=all_cols)
    if not risk_cols or not safe_cols:
        return w

    sma = prices[all_cols].rolling(lookback_days, min_periods=lookback_days).mean()
    mom = (prices[all_cols] / sma) - 1.0
    rebal_mask = _month_end_mask(prices.index)
    rebal_positions = list(np.flatnonzero(rebal_mask.values))
    if len(prices) > 0 and (not rebal_positions or rebal_positions[-1] != len(prices) - 1):
        rebal_positions.append(len(prices) - 1)

    n_risk = len(risk_cols)
    w_arr = np.full((len(prices), len(all_cols)), np.nan, dtype=float)
    col_idx = {c: i for i, c in enumerate(all_cols)}

    for pos in rebal_positions:
        row_mom = mom.iloc[pos]
        risk_vals = {c: float(row_mom[c]) for c in risk_cols if pd.notna(row_mom[c])}
        if len(risk_vals) < max(3, n_risk // 2):
            w_arr[pos, :] = 0.0
            continue
        good = [(c, v) for c, v in risk_vals.items() if v > 0.0]
        n_bad = len(risk_vals) - len(good)
        bf = min(1.0, (protection_factor * n_bad) / float(len(risk_vals)))

        # Pick best safe asset by momentum (or SHY/first safe if all NaN)
        safe_vals = [(c, float(row_mom[c])) for c in safe_cols if pd.notna(row_mom[c])]
        best_safe = max(safe_vals, key=lambda kv: kv[1])[0] if safe_vals else safe_cols[0]

        row_w = np.zeros(len(all_cols), dtype=float)
        if bf >= 0.999 or not good:
            row_w[col_idx[best_safe]] = 1.0
        else:
            row_w[col_idx[best_safe]] = bf
            good.sort(key=lambda kv: kv[1], reverse=True)
            chosen = good[: min(top_n, len(good))]
            each = (1.0 - bf) / float(len(chosen))
            for sym, _ in chosen:
                row_w[col_idx[sym]] += each
        w_arr[pos, :] = row_w

    out = pd.DataFrame(w_arr, index=prices.index, columns=all_cols).ffill().fillna(0.0)
    return out


# ---------------------------------------------------------------------------
# 2. Vigilant Asset Allocation (VAA-G4 — Keller & Keuning 2017)
# ---------------------------------------------------------------------------


def _build_vaa_weights(prices: pd.DataFrame) -> pd.DataFrame:
    offensive = [c for c in ("SPY", "VGK", "EEM", "LQD") if c in prices.columns]
    defensive = [c for c in ("SHY", "IEF", "LQD") if c in prices.columns]
    cols = list(dict.fromkeys([*offensive, *defensive]))
    if not offensive or not defensive:
        return pd.DataFrame(0.0, index=prices.index, columns=cols)
    score = _momentum_13612w(prices[cols])
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    for idx in range(252, len(prices)):
        row = score.iloc[idx]
        off_vals = {c: float(row[c]) for c in offensive if pd.notna(row[c])}
        def_vals = {c: float(row[c]) for c in defensive if pd.notna(row[c])}
        if not off_vals or not def_vals:
            continue
        if all(v > 0.0 for v in off_vals.values()):
            best = max(off_vals.items(), key=lambda kv: kv[1])[0]
        else:
            best = max(def_vals.items(), key=lambda kv: kv[1])[0]
        w.iat[idx, cols.index(best)] = 1.0
    return _causal_rebalance(w, "M")


# ---------------------------------------------------------------------------
# 3. Defensive Asset Allocation (DAA — Canary EEM + LQD)
# ---------------------------------------------------------------------------


def _build_daa_weights(prices: pd.DataFrame) -> pd.DataFrame:
    canaries = [c for c in ("EEM", "LQD") if c in prices.columns]
    offensive = [c for c in ("SPY", "QQQ", "IWM", "VGK", "EWJ", "VNQ", "GLD", "DBC", "HYG", "TLT") if c in prices.columns]
    defensive = [c for c in ("SHY", "IEF", "BIL") if c in prices.columns]
    cols = list(dict.fromkeys([*offensive, *defensive, *canaries]))
    if not offensive or not defensive:
        return pd.DataFrame(0.0, index=prices.index, columns=cols)
    score = _momentum_13612w(prices[cols])
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    for idx in range(252, len(prices)):
        row = score.iloc[idx]
        bad_canaries = sum(1 for c in canaries if pd.notna(row[c]) and float(row[c]) <= 0.0)
        def_vals = [(c, float(row[c])) for c in defensive if pd.notna(row[c])]
        best_def = max(def_vals, key=lambda kv: kv[1])[0] if def_vals else defensive[0]
        off_vals = [(c, float(row[c])) for c in offensive if pd.notna(row[c])]
        off_vals.sort(key=lambda kv: kv[1], reverse=True)
        if bad_canaries >= len(canaries) and canaries:
            w.iat[idx, cols.index(best_def)] = 1.0
        elif bad_canaries == 1:
            w.iat[idx, cols.index(best_def)] = 0.5
            top2 = off_vals[:2]
            for sym, _ in top2:
                w.iat[idx, cols.index(sym)] += 0.5 / len(top2)
        else:
            top2 = off_vals[:2]
            for sym, _ in top2:
                w.iat[idx, cols.index(sym)] += 1.0 / len(top2)
    return _causal_rebalance(w, "M")


# ---------------------------------------------------------------------------
# 4. Accelerated Dual Momentum & 5. Antonacci GEM
# ---------------------------------------------------------------------------


def _build_adm_weights(prices: pd.DataFrame) -> pd.DataFrame:
    risky = [c for c in ("SPY", "QQQ", "VGK") if c in prices.columns]
    safe = [c for c in ("TLT", "IEF", "SHY") if c in prices.columns]
    cols = list(dict.fromkeys([*risky, *safe]))
    score = (prices[cols].pct_change(21) + prices[cols].pct_change(63) + prices[cols].pct_change(126)) / 3.0
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    for idx in range(130, len(prices)):
        row = score.iloc[idx]
        r_vals = [(c, float(row[c])) for c in risky if pd.notna(row[c])]
        if not r_vals:
            continue
        best_r, best_v = max(r_vals, key=lambda kv: kv[1])
        if best_v > 0.0:
            w.iat[idx, cols.index(best_r)] = 1.0
        elif safe:
            s_vals = [(c, float(row[c])) for c in safe if pd.notna(row[c])]
            best_s = max(s_vals, key=lambda kv: kv[1])[0] if s_vals else safe[0]
            w.iat[idx, cols.index(best_s)] = 1.0
    return _causal_rebalance(w, "M")


def _build_gem_weights(prices: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ("SPY", "VGK", "EEM", "IEF", "SHY") if c in prices.columns]
    ret12 = prices[cols].pct_change(252)
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    for idx in range(252, len(prices)):
        row = ret12.iloc[idx]
        spy = float(row["SPY"]) if "SPY" in row and pd.notna(row["SPY"]) else np.nan
        shy = float(row["SHY"]) if "SHY" in row and pd.notna(row["SHY"]) else 0.0
        intl_candidates = [c for c in ("VGK", "EEM") if c in row and pd.notna(row[c])]
        best_intl = max(intl_candidates, key=lambda c: float(row[c])) if intl_candidates else None
        if np.isnan(spy):
            continue
        if spy > shy:
            if best_intl and float(row[best_intl]) > spy:
                w.iat[idx, cols.index(best_intl)] = 1.0
            else:
                w.iat[idx, cols.index("SPY")] = 1.0
        elif "IEF" in cols:
            w.iat[idx, cols.index("IEF")] = 1.0
    return _causal_rebalance(w, "M")


# ---------------------------------------------------------------------------
# 6-15. Risk Parity, Faber GTAA, Vol-Target, Sectors, Factors, Safe Haven, Timing, RSI(2)
# ---------------------------------------------------------------------------


def _build_risk_parity_weights(prices: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ("SPY", "TLT", "IEF", "GLD", "DBC") if c in prices.columns]
    vol = prices[cols].pct_change().rolling(63, min_periods=30).std()
    inv_vol = (1.0 / vol.replace(0.0, np.nan)).fillna(0.0)
    w = inv_vol.div(inv_vol.sum(axis=1).replace(0.0, np.nan), axis=0).fillna(0.0)
    return _causal_rebalance(w, "M")


def _build_gtaa5_weights(prices: pd.DataFrame) -> pd.DataFrame:
    risky = [c for c in ("SPY", "VGK", "IEF", "VNQ", "DBC") if c in prices.columns]
    safe = "SHY" if "SHY" in prices.columns else None
    cols = list(dict.fromkeys([*risky, *([safe] if safe else [])]))
    sma200 = prices[risky].rolling(200, min_periods=200).mean()
    above = prices[risky] > sma200
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    slot = 1.0 / max(1, len(risky))
    for c in risky:
        w[c] = np.where(above[c], slot, 0.0)
    if safe:
        w[safe] = (1.0 - w[risky].sum(axis=1)).clip(lower=0.0)
    return _causal_rebalance(w, "M")


def compute_meta_a_weights(prices: pd.DataFrame) -> pd.DataFrame:
    """Compute causal target weight matrix for Meta-Portfolio A (US Orthogonal ETF Ensemble).

    Linear blend matching ``META_US_ETF_ALL_WEATHER`` in ``src/quant/portfolio.py``:
      - 40% Protective Asset Allocation (PAA)
      - 20% Vigilant Asset Allocation (VAA-G4)
      - 20% Faber GTAA-5 (200D SMA Trend)
      - 20% All-Weather Risk Parity (63D Inverse-Vol)
    """
    components = [
        (compute_paa_weights(prices), 0.40),
        (_build_vaa_weights(prices), 0.20),
        (_build_gtaa5_weights(prices), 0.20),
        (_build_risk_parity_weights(prices), 0.20),
    ]
    all_cols = list(dict.fromkeys(col for df, _ in components for col in df.columns))
    combined = pd.DataFrame(0.0, index=prices.index, columns=all_cols)
    for df, weight in components:
        if df.empty:
            continue
        aligned = df.reindex(index=prices.index, columns=all_cols).fillna(0.0)
        combined = combined + aligned * float(weight)
    return combined


def _build_vol_target_trend_weights(prices: pd.DataFrame) -> pd.DataFrame:
    risky = [c for c in ("SPY", "QQQ", "GLD", "TLT") if c in prices.columns]
    safe = "SHY" if "SHY" in prices.columns else None
    cols = list(dict.fromkeys([*risky, *([safe] if safe else [])]))
    sma150 = prices[risky].rolling(150, min_periods=150).mean()
    ann_vol = prices[risky].pct_change().rolling(42, min_periods=21).std() * np.sqrt(252.0)
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    target_per_sleeve = 0.10 / max(1, len(risky))
    for c in risky:
        raw_w = (target_per_sleeve / ann_vol[c].replace(0.0, np.nan)).clip(upper=0.35).fillna(0.0)
        w[c] = np.where(prices[c] > sma150[c], raw_w, 0.0)
    total = w[risky].sum(axis=1)
    over = total > 1.0
    if bool(over.any()):
        w.loc[over, risky] = w.loc[over, risky].div(total[over], axis=0)
    if safe:
        w[safe] = (1.0 - w[risky].sum(axis=1)).clip(lower=0.0)
    return _causal_rebalance(w, "W")


def _build_sector_momentum_top3(prices: pd.DataFrame) -> pd.DataFrame:
    sectors = [c for c in ("XLK", "XLV", "XLF", "XLE", "XLI", "XLP", "XLU", "XLY", "XLB", "XLC", "XLRE") if c in prices.columns]
    safe = "SHY" if "SHY" in prices.columns else None
    cols = list(dict.fromkeys([*sectors, *([safe] if safe else [])]))
    mom6_1 = (prices[sectors].shift(21) / prices[sectors].shift(147)) - 1.0
    sma200 = prices[sectors].rolling(200, min_periods=200).mean()
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    for idx in range(200, len(prices)):
        elig = [
            (c, float(mom6_1[c].iloc[idx]))
            for c in sectors
            if pd.notna(mom6_1[c].iloc[idx]) and pd.notna(sma200[c].iloc[idx]) and prices[c].iloc[idx] > sma200[c].iloc[idx]
        ]
        elig.sort(key=lambda kv: kv[1], reverse=True)
        chosen = elig[:3]
        if chosen:
            each = 1.0 / len(chosen)
            for sym, _ in chosen:
                w.iat[idx, cols.index(sym)] = each
        elif safe:
            w.iat[idx, cols.index(safe)] = 1.0
    return _causal_rebalance(w, "M")


def _build_sector_low_vol_trend(prices: pd.DataFrame) -> pd.DataFrame:
    sectors = [c for c in ("XLK", "XLV", "XLF", "XLE", "XLI", "XLP", "XLU", "XLY", "XLB", "XLC", "XLRE") if c in prices.columns]
    safe = "SHY" if "SHY" in prices.columns else None
    cols = list(dict.fromkeys([*sectors, *([safe] if safe else [])]))
    vol = prices[sectors].pct_change().rolling(63, min_periods=40).std()
    sma100 = prices[sectors].rolling(100, min_periods=100).mean()
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    for idx in range(100, len(prices)):
        elig = [
            (c, float(vol[c].iloc[idx]))
            for c in sectors
            if pd.notna(vol[c].iloc[idx]) and pd.notna(sma100[c].iloc[idx]) and prices[c].iloc[idx] > sma100[c].iloc[idx]
        ]
        elig.sort(key=lambda kv: kv[1])
        chosen = elig[:4]
        if chosen:
            each = 1.0 / len(chosen)
            for sym, _ in chosen:
                w.iat[idx, cols.index(sym)] = each
        elif safe:
            w.iat[idx, cols.index(safe)] = 1.0
    return _causal_rebalance(w, "M")


def _build_factor_rotation(prices: pd.DataFrame) -> pd.DataFrame:
    factors = [c for c in ("MTUM", "QUAL", "USMV", "VLUE") if c in prices.columns]
    safe = "SHY" if "SHY" in prices.columns else ("IEF" if "IEF" in prices.columns else None)
    cols = list(dict.fromkeys([*factors, *([safe] if safe else [])]))
    mom6 = prices[factors].pct_change(126)
    sma200 = prices[factors].rolling(200, min_periods=200).mean()
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    for idx in range(200, len(prices)):
        elig = [
            (c, float(mom6[c].iloc[idx]))
            for c in factors
            if pd.notna(mom6[c].iloc[idx]) and pd.notna(sma200[c].iloc[idx]) and prices[c].iloc[idx] > sma200[c].iloc[idx]
        ]
        elig.sort(key=lambda kv: kv[1], reverse=True)
        chosen = elig[:2]
        if chosen:
            for sym, _ in chosen:
                w.iat[idx, cols.index(sym)] = 1.0 / len(chosen)
        elif safe:
            w.iat[idx, cols.index(safe)] = 1.0
    return _causal_rebalance(w, "M")


def _build_safe_haven_rotation(prices: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ("GLD", "TLT", "IEF", "SHY") if c in prices.columns]
    mom3 = prices[cols].pct_change(63)
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    for idx in range(65, len(prices)):
        vals = [(c, float(mom3[c].iloc[idx])) for c in cols if pd.notna(mom3[c].iloc[idx])]
        if vals:
            best = max(vals, key=lambda kv: kv[1])[0]
            w.iat[idx, cols.index(best)] = 1.0
    return _causal_rebalance(w, "M")


def _build_single_sma_timing(prices: pd.DataFrame, ticker: str, sma_days: int = 200, safe: str = "SHY") -> pd.DataFrame:
    cols = [c for c in (ticker, safe) if c in prices.columns]
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    if ticker not in prices.columns:
        return w
    sma = prices[ticker].rolling(sma_days, min_periods=sma_days).mean()
    in_trend = prices[ticker] > sma
    w[ticker] = np.where(in_trend, 1.0, 0.0)
    if safe in cols and safe != ticker:
        w[safe] = np.where(in_trend, 0.0, 1.0)
    return w


def _build_qqq_dual_sma(prices: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ("QQQ", "SHY") if c in prices.columns]
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    if "QQQ" not in prices.columns:
        return w
    sma50 = prices["QQQ"].rolling(50, min_periods=50).mean()
    sma200 = prices["QQQ"].rolling(200, min_periods=200).mean()
    in_trend = (prices["QQQ"] > sma50) & (prices["QQQ"] > sma200)
    w["QQQ"] = np.where(in_trend, 1.0, 0.0)
    if "SHY" in cols:
        w["SHY"] = np.where(in_trend, 0.0, 1.0)
    return w


def _build_spy_rsi2(prices: pd.DataFrame) -> pd.DataFrame:
    if "SPY" not in prices.columns:
        return pd.DataFrame(index=prices.index)
    close = prices["SPY"]
    sma200 = close.rolling(200, min_periods=200).mean()
    sma5 = close.rolling(5, min_periods=5).mean()
    rsi2 = _rsi(close, 2)
    pos = np.zeros(len(close), dtype=float)
    holding = False
    for i in range(200, len(close)):
        if not holding and close.iloc[i] > sma200.iloc[i] and rsi2.iloc[i] < 10.0:
            holding = True
        elif holding and close.iloc[i] > sma5.iloc[i]:
            holding = False
        pos[i] = 1.0 if holding else 0.0
    return pd.DataFrame({"SPY": pos}, index=prices.index)


def _build_buy_hold(prices: pd.DataFrame, weights_map: Dict[str, float]) -> pd.DataFrame:
    cols = [c for c in weights_map if c in prices.columns]
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    total = sum(weights_map[c] for c in cols) or 1.0
    for c in cols:
        w[c] = weights_map[c] / total
    return _causal_rebalance(w, "M") if len(cols) > 1 else w


# ---------------------------------------------------------------------------
# Crypto & BIST Strategies
# ---------------------------------------------------------------------------


def _build_crypto_5sma_ensemble(prices: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ("BTC-USD", "ETH-USD") if c in prices.columns]
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    if not cols:
        return w
    windows = (50, 100, 150, 200, 250)
    asset_cap = 1.0 / len(cols)
    for c in cols:
        above_count = sum(
            (prices[c] > prices[c].rolling(n, min_periods=n).mean()).astype(float)
            for n in windows
        )
        w[c] = asset_cap * (above_count / float(len(windows)))
    return w


def _build_crypto_dual_momentum(prices: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ("BTC-USD", "ETH-USD") if c in prices.columns]
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    if not cols:
        return w
    sma100 = prices[cols].rolling(100, min_periods=100).mean()
    mom60 = prices[cols].pct_change(60)
    for idx in range(100, len(prices)):
        elig = [
            (c, float(mom60[c].iloc[idx]))
            for c in cols
            if pd.notna(mom60[c].iloc[idx]) and pd.notna(sma100[c].iloc[idx]) and prices[c].iloc[idx] > sma100[c].iloc[idx]
        ]
        if elig:
            best = max(elig, key=lambda kv: kv[1])[0]
            w.iat[idx, cols.index(best)] = 1.0
    return _causal_rebalance(w, "W")


def _build_bist_52w_lowvol_top5(prices: pd.DataFrame) -> pd.DataFrame:
    cols = list(prices.columns)
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    if len(cols) < 3:
        return w
    high252 = prices.rolling(252, min_periods=120).max()
    near_high = prices / high252.replace(0.0, np.nan)
    vol60 = prices.pct_change().rolling(60, min_periods=40).std()
    sma100 = prices.rolling(100, min_periods=100).mean()
    for idx in range(120, len(prices)):
        elig = []
        for c in cols:
            nh = near_high[c].iloc[idx]
            v = vol60[c].iloc[idx]
            s100 = sma100[c].iloc[idx]
            px = prices[c].iloc[idx]
            if pd.notna(nh) and pd.notna(v) and pd.notna(s100) and px > s100 and v > 0:
                # High 52W proximity divided by volatility
                elig.append((c, float(nh) / float(v)))
        elig.sort(key=lambda kv: kv[1], reverse=True)
        chosen = elig[:5]
        if chosen:
            each = 1.0 / len(chosen)
            for sym, _ in chosen:
                w.iat[idx, cols.index(sym)] = each
    return _causal_rebalance(w, "M")


def _build_bist_momentum_top5(prices: pd.DataFrame) -> pd.DataFrame:
    cols = list(prices.columns)
    w = pd.DataFrame(0.0, index=prices.index, columns=cols)
    if len(cols) < 3:
        return w
    mom6_1 = (prices.shift(21) / prices.shift(147)) - 1.0
    sma200 = prices.rolling(200, min_periods=150).mean()
    for idx in range(150, len(prices)):
        elig = [
            (c, float(mom6_1[c].iloc[idx]))
            for c in cols
            if pd.notna(mom6_1[c].iloc[idx]) and pd.notna(sma200[c].iloc[idx]) and prices[c].iloc[idx] > sma200[c].iloc[idx] and float(mom6_1[c].iloc[idx]) > 0.0
        ]
        elig.sort(key=lambda kv: kv[1], reverse=True)
        chosen = elig[:5]
        if chosen:
            each = 1.0 / len(chosen)
            for sym, _ in chosen:
                w.iat[idx, cols.index(sym)] = each
    return _causal_rebalance(w, "M")


# ---------------------------------------------------------------------------
# Strategy Catalog (23 Base Strategies + 2 Meta-Portfolios = 25 Total)
# ---------------------------------------------------------------------------


def build_base_strategy_specs() -> List[StrategySpec]:
    return [
        StrategySpec(
            strategy_id="PROTECTIVE_ASSET_ALLOCATION_PAA",
            name="Protective Asset Allocation (PAA Çöküş Kalkanı)",
            universe="us_etf",
            category="Tactical Asset Allocation",
            description="Keller-Keuning (2016) 12 riskli ETF genişlik çöküş kalkanı: SMA252 altındaki varlık sayısı arttıkça IEF/SHY korumasına geçer.",
            cost_bps=5.0,
            builder=compute_paa_weights,
        ),
        StrategySpec(
            strategy_id="VIGILANT_ASSET_ALLOCATION_VAA",
            name="Vigilant Asset Allocation (VAA Kanarya Kalkanı)",
            universe="us_etf",
            category="Tactical Asset Allocation",
            description="4 saldırgan kanarya (SPY/VGK/EEM/LQD) 13612W momentumu; biri bile negatifse %100 en güçlü savunma tahviline (SHY/IEF) geçer.",
            cost_bps=5.0,
            builder=_build_vaa_weights,
        ),
        StrategySpec(
            strategy_id="DEFENSIVE_ASSET_ALLOCATION_DAA",
            name="Defensive Asset Allocation (DAA Kanarya)",
            universe="us_etf",
            category="Tactical Asset Allocation",
            description="EEM + LQD kanarya göstergeleriyle kademeli %0/%50/%100 nakit-tahvil korumalı 13612W rotasyon.",
            cost_bps=5.0,
            builder=_build_daa_weights,
        ),
        StrategySpec(
            strategy_id="ACCELERATED_DUAL_MOMENTUM",
            name="Accelerated Dual Momentum (ADM)",
            universe="us_etf",
            category="Momentum",
            description="SPY / QQQ / VGK 1-3-6 ay bileşik momentum lideri; negatifse TLT/IEF/SHY tahvil rotasyonu.",
            cost_bps=5.0,
            builder=_build_adm_weights,
        ),
        StrategySpec(
            strategy_id="DUAL_MOMENTUM_GEM",
            name="Dual Momentum (Antonacci GEM)",
            universe="us_etf",
            category="Momentum",
            description="Klasik 12 aylık mutlak & göreceli momentum (SPY vs VGK/EEM vs SHY, negatifse IEF).",
            cost_bps=5.0,
            builder=_build_gem_weights,
        ),
        StrategySpec(
            strategy_id="ALL_WEATHER_RISK_PARITY",
            name="All-Weather Risk Parity (Vol-Weighted)",
            universe="us_etf",
            category="Risk Parity",
            description="SPY, TLT, IEF, GLD ve DBC arasında 63 günlük ters-volatilite ağırlıklı aylık dengeleme.",
            cost_bps=5.0,
            builder=_build_risk_parity_weights,
        ),
        StrategySpec(
            strategy_id="ETF_TREND_10M_SMA",
            name="Faber GTAA-5 (200G Trend Takibi)",
            universe="us_etf",
            category="Trend Following",
            description="SPY, VGK, IEF, VNQ, DBC eşit ağırlık; 200G SMA altında kalan her dilim SHY nakde geçer.",
            cost_bps=5.0,
            builder=_build_gtaa5_weights,
        ),
        StrategySpec(
            strategy_id="ETF_VOL_TARGET_TREND",
            name="Vol-Target Multi-Asset Trend (%10 Hedef Vol)",
            universe="us_etf",
            category="Trend Following",
            description="SPY/QQQ/GLD/TLT 150G trend filtresi + %10 yıllık hedef volatilite ölçeklemesi.",
            cost_bps=5.0,
            builder=_build_vol_target_trend_weights,
        ),
        StrategySpec(
            strategy_id="SAFE_HAVEN_ROTATION",
            name="Safe-Haven Altın & Tahvil Rotasyonu",
            universe="us_etf",
            category="Defensive",
            description="GLD, TLT, IEF, SHY arasında 3 aylık momentum liderine aylık geçiş.",
            cost_bps=5.0,
            builder=_build_safe_haven_rotation,
        ),
        StrategySpec(
            strategy_id="SPY_200SMA_TIMING",
            name="S&P 500 (SPY) 200G SMA Zamanlama",
            universe="us_etf",
            category="Trend Following",
            description="SPY > SMA200 iken hissede, altındayken SHY kısa tahvilde.",
            cost_bps=5.0,
            builder=lambda df: _build_single_sma_timing(df, "SPY", 200, "SHY"),
        ),
        StrategySpec(
            strategy_id="QQQ_DUAL_SMA_50_200",
            name="Nasdaq-100 (QQQ) 50/200G Çift Trend",
            universe="us_etf",
            category="Trend Following",
            description="QQQ hem SMA50 hem SMA200 üstündeyken pozisyonda, aksi halde SHY.",
            cost_bps=5.0,
            builder=_build_qqq_dual_sma,
        ),
        StrategySpec(
            strategy_id="SPY_RSI2_MEAN_REVERSION",
            name="SPY RSI(2) Ortalamaya Dönüş",
            universe="us_etf",
            category="Mean Reversion",
            description="SPY > SMA200 iken RSI(2)<10 giriş, kapanış > SMA5 çıkış (kısa vadeli geri çekilme).",
            cost_bps=5.0,
            builder=_build_spy_rsi2,
        ),
        StrategySpec(
            strategy_id="US_SECTOR_MOMENTUM_TOP3",
            name="ABD Sektör Momentum Top-3 (Trend Filtreli)",
            universe="us_sectors",
            category="Sector Rotation",
            description="11 S&P sektörü içinde SMA200 üstündeki en güçlü 3 sektör (6-1 ay momentum); yoksa SHY.",
            cost_bps=6.0,
            builder=_build_sector_momentum_top3,
        ),
        StrategySpec(
            strategy_id="US_SECTOR_LOW_VOL_TREND",
            name="ABD Düşük Volatilite Sektör Top-4",
            universe="us_sectors",
            category="Defensive Equity",
            description="SMA100 üstündeki en düşük 63G volatiliteli 4 ABD sektörü; yoksa SHY.",
            cost_bps=6.0,
            builder=_build_sector_low_vol_trend,
        ),
        StrategySpec(
            strategy_id="US_FACTOR_ROTATION",
            name="ABD Faktör ETF Rotasyonu (MTUM/QUAL/USMV/VLUE)",
            universe="us_sectors",
            category="Factor Rotation",
            description="SMA200 üstündeki en güçlü 2 faktör ETF'ine aylık rotasyon; aksi halde SHY.",
            cost_bps=5.0,
            builder=_build_factor_rotation,
        ),
        StrategySpec(
            strategy_id="BENCHMARK_SPY_BUY_HOLD",
            name="Referans: Buy & Hold S&P 500 (SPY)",
            universe="us_etf",
            category="Benchmark",
            description="S&P 500 (SPY) pasif al-tut kıyaslama ölçütü.",
            cost_bps=0.0,
            is_benchmark=True,
            builder=lambda df: _build_buy_hold(df, {"SPY": 1.0}),
        ),
        StrategySpec(
            strategy_id="BENCHMARK_60_40",
            name="Referans: Klasik 60/40 (SPY/IEF)",
            universe="us_etf",
            category="Benchmark",
            description="Klasik %60 S&P 500 + %40 ABD 7-10Y Hazine tahvili aylık dengeli portföy.",
            cost_bps=2.0,
            is_benchmark=True,
            builder=lambda df: _build_buy_hold(df, {"SPY": 0.60, "IEF": 0.40}),
        ),
        StrategySpec(
            strategy_id="CRYPTO_5SMA_ENSEMBLE",
            name="Kripto 5-SMA Trend Ensemble (BTC+ETH)",
            universe="crypto",
            category="Crypto Trend",
            description="BTC ve ETH için 50/100/150/200/250G SMA eşit dilimli çöküş kalkanı (maliyet %0.15/yön).",
            cost_bps=15.0,
            trading_days_per_year=365,
            builder=_build_crypto_5sma_ensemble,
        ),
        StrategySpec(
            strategy_id="CRYPTO_BTC_200SMA",
            name="Kripto BTC-USD 200G SMA Trend",
            universe="crypto",
            category="Crypto Trend",
            description="BTC-USD kapanış > SMA200 iken BTC, altındayken %100 nakit.",
            cost_bps=15.0,
            trading_days_per_year=365,
            builder=lambda df: _build_single_sma_timing(df, "BTC-USD", 200, ""),
        ),
        StrategySpec(
            strategy_id="CRYPTO_DUAL_MOMENTUM",
            name="Kripto BTC/ETH Dual Momentum (100G Trend)",
            universe="crypto",
            category="Crypto Momentum",
            description="SMA100 üstündeki daha güçlü coin'e haftalık geçiş, ikisi de altındaysa %100 nakit.",
            cost_bps=15.0,
            trading_days_per_year=365,
            builder=_build_crypto_dual_momentum,
        ),
        StrategySpec(
            strategy_id="BENCHMARK_CRYPTO_BUY_HOLD",
            name="Referans: Kripto Al-Tut (50/50 BTC+ETH)",
            universe="crypto",
            category="Benchmark",
            description="BTC-USD ve ETH-USD eşit ağırlıklı pasif al-tut kıyaslaması.",
            cost_bps=0.0,
            trading_days_per_year=365,
            is_benchmark=True,
            builder=lambda df: _build_buy_hold(df, {"BTC-USD": 0.50, "ETH-USD": 0.50}),
        ),
        StrategySpec(
            strategy_id="BIST_52W_HIGH_LOWVOL_TOP5",
            name="BIST 52H Zirve + Düşük-Vol Trend Top-5 (TL)",
            universe="bist",
            category="BIST Equity",
            description="Likit BIST-30 evreninde SMA100 üstü 52H zirve yakınlığı / volatilite Top-5 (hayatta kalma & TL enflasyon uyarılı).",
            cost_bps=20.0,
            currency="TRY",
            builder=_build_bist_52w_lowvol_top5,
        ),
        StrategySpec(
            strategy_id="BIST_MOMENTUM_TOP5",
            name="BIST 6-1A Momentum Trend Top-5 (TL)",
            universe="bist",
            category="BIST Equity",
            description="Likit BIST-30 evreninde SMA200 üstü pozitif 6-1A momentum Top-5 (hayatta kalma & TL enflasyon uyarılı).",
            cost_bps=20.0,
            currency="TRY",
            builder=_build_bist_momentum_top5,
        ),
    ]


def run_all_base_strategies(
    universes: Dict[str, pd.DataFrame],
    *,
    oos_start: str = DEFAULT_OOS_START,
    n_trials: int = 25,
    rf_returns: Optional[pd.Series] = None,
) -> Dict[str, StrategyResult]:
    """Run all 23 base strategies on their respective loaded price universes."""
    results: Dict[str, StrategyResult] = {}
    for spec in build_base_strategy_specs():
        frame = universes.get(spec.universe)
        if frame is None or frame.empty or spec.builder is None:
            results[spec.strategy_id] = StrategyResult(
                strategy_id=spec.strategy_id,
                name=spec.name,
                universe=spec.universe,
                category=spec.category,
                description=spec.description,
                currency=spec.currency,
                cost_bps=spec.cost_bps,
                is_benchmark=spec.is_benchmark,
                verdict="FAIL_WEAK",
                signal_summary="Evren verisi yüklenemedi",
            )
            continue
        weights = spec.builder(frame)
        results[spec.strategy_id] = backtest_weight_matrix(
            frame,
            weights,
            spec,
            oos_start=oos_start,
            n_trials=n_trials,
            rf_returns=rf_returns,
        )
    return results
