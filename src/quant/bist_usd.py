# -*- coding: utf-8 -*-
"""USD view of TRY-denominated BIST tournament strategies.

TL returns of BIST strategies are inflated by the lira's depreciation, so a TL
Sharpe of 1.0 can still be a real-dollar loss. This module converts each BIST
strategy's net daily TL returns into USD with Yahoo's ``TRY=X`` (TRY per 1 USD)
close and measures them against the same risk-free hurdle as the US strategies
(``BIL``), so BIST and US rows in the tournament are finally comparable.

    r_usd = (1 + r_try) / (1 + r_fx) - 1      where r_fx = USDTRY_t / USDTRY_{t-1} - 1

FX is forward-filled onto the BIST trading calendar, so a lira move during a
Turkish holiday is charged on the next BIST session instead of being lost.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.quant.stats import PerformanceMetrics, compute_performance_metrics

logger = logging.getLogger(__name__)

BIST_FX_SYMBOL = "TRY=X"  # Yahoo quote: TRY per 1 USD
BIST_INDEX_SYMBOL = "XU100.IS"
# A daily USDTRY close move larger than this is treated as a bad Yahoo tick.
# (The largest genuine close-to-close move, Dec 2021, was about -25%.)
MAX_PLAUSIBLE_FX_MOVE = 0.35


def load_bist_usd_reference(
    *,
    start_date: str = "2016-01-01",
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Load USDTRY and XU100 closes; returns an empty frame when unavailable."""
    from src.quant.data_loader import load_universe_closes

    try:
        frame = load_universe_closes(
            "bist_usd_reference",
            (BIST_FX_SYMBOL, BIST_INDEX_SYMBOL),
            start_date=start_date,
            cache_dir=cache_dir,
            force_refresh=force_refresh,
        )
    except Exception as exc:  # noqa: BLE001 - USD view is an overlay, never fatal
        logger.warning("[quant] USDTRY/XU100 reference unavailable: %s", exc)
        return pd.DataFrame()
    return frame if frame is not None else pd.DataFrame()


def clean_usdtry(usdtry: pd.Series) -> pd.Series:
    """Drop non-positive quotes and isolated bad ticks from a USDTRY close series."""
    fx = pd.to_numeric(usdtry, errors="coerce").replace([np.inf, -np.inf], np.nan)
    fx = fx[fx > 0].dropna().sort_index()
    if len(fx) < 3:
        return fx
    # A bad tick jumps and immediately reverts: flag points far from both neighbours.
    prev_move = fx / fx.shift(1) - 1.0
    next_move = fx.shift(-1) / fx - 1.0
    spike = (prev_move.abs() > MAX_PLAUSIBLE_FX_MOVE) & (next_move.abs() > MAX_PLAUSIBLE_FX_MOVE) & (
        np.sign(prev_move) != np.sign(next_move)
    )
    return fx[~spike.fillna(False)]


def try_returns_to_usd(try_returns: pd.Series, usdtry: pd.Series) -> pd.Series:
    """Convert daily TL returns into USD returns on the strategy's own calendar."""
    r = pd.to_numeric(try_returns, errors="coerce").dropna().sort_index()
    fx = clean_usdtry(usdtry)
    if r.empty or fx.empty:
        return pd.Series(dtype=float)
    union = fx.index.union(r.index)
    fx_on_days = fx.reindex(union).ffill().reindex(r.index)
    fx_ret = fx_on_days.pct_change()
    usd = (1.0 + r) / (1.0 + fx_ret) - 1.0
    return usd.replace([np.inf, -np.inf], np.nan).dropna()


def yearly_returns_pct(daily_returns: Optional[pd.Series]) -> Dict[str, float]:
    """Compound daily returns into calendar-year returns (percent)."""
    if daily_returns is None:
        return {}
    r = pd.to_numeric(daily_returns, errors="coerce").dropna()
    if r.empty or not isinstance(r.index, pd.DatetimeIndex):
        return {}
    grouped = (1.0 + r).groupby(r.index.year).prod() - 1.0
    return {str(int(year)): round(float(val) * 100.0, 2) for year, val in grouped.items()}


def usd_oos_metrics(
    try_daily_returns: pd.Series,
    usdtry: pd.Series,
    *,
    oos_start: str,
    rf_returns: Optional[pd.Series] = None,
    turnover_series: Optional[pd.Series] = None,
    n_trials: int = 25,
) -> tuple[Optional[PerformanceMetrics], pd.Series]:
    """USD out-of-sample metrics (vs ``rf_returns``) plus the OOS USD daily return series."""
    usd = try_returns_to_usd(try_daily_returns, usdtry)
    usd_oos = usd.loc[usd.index >= pd.Timestamp(oos_start)]
    if len(usd_oos) < 20:
        return None, usd_oos
    # Seed the curve one day before the first OOS return so no return is dropped.
    equity = 100.0 * (1.0 + usd_oos).cumprod()
    seed_ts = usd_oos.index[0] - pd.Timedelta(days=1)
    equity = pd.concat([pd.Series([100.0], index=[seed_ts]), equity])
    metrics = compute_performance_metrics(
        equity,
        turnover_series=turnover_series,
        rf_returns=rf_returns,
        n_trials=n_trials,
    )
    return metrics, usd_oos


def build_bist_usd_reference(
    reference: pd.DataFrame,
    *,
    oos_start: str,
    rf_returns: Optional[pd.Series] = None,
) -> Dict[str, Any]:
    """Summarize lira depreciation and XU100 in TL vs USD over the OOS window."""
    if reference is None or reference.empty or BIST_FX_SYMBOL not in reference.columns:
        return {}
    fx = clean_usdtry(reference[BIST_FX_SYMBOL])
    fx_oos = fx.loc[fx.index >= pd.Timestamp(oos_start)]
    if len(fx_oos) < 20:
        return {}
    years = max((fx_oos.index[-1] - fx_oos.index[0]).days / 365.25, 1e-9)
    fx_mult = float(fx_oos.iloc[-1]) / float(fx_oos.iloc[0])
    out: Dict[str, Any] = {
        "fx_symbol": BIST_FX_SYMBOL,
        "start_date": fx_oos.index[0].strftime("%Y-%m-%d"),
        "end_date": fx_oos.index[-1].strftime("%Y-%m-%d"),
        "usdtry_start": round(float(fx_oos.iloc[0]), 4),
        "usdtry_end": round(float(fx_oos.iloc[-1]), 4),
        "usdtry_annual_change_pct": round((fx_mult ** (1.0 / years) - 1.0) * 100.0, 2),
    }
    if BIST_INDEX_SYMBOL in reference.columns:
        xu = pd.to_numeric(reference[BIST_INDEX_SYMBOL], errors="coerce").dropna()
        xu_ret = xu.pct_change().dropna()
        xu_oos = xu.loc[xu.index >= pd.Timestamp(oos_start)]
        if len(xu_oos) >= 20:
            tl_metrics = compute_performance_metrics(xu_oos)
            usd_metrics, usd_series = usd_oos_metrics(xu_ret, fx, oos_start=oos_start, rf_returns=rf_returns)
            out["index_symbol"] = BIST_INDEX_SYMBOL
            out["index_try_cagr_pct"] = tl_metrics.cagr_pct
            if usd_metrics is not None:
                out["index_usd"] = usd_metrics.to_dict()
                out["index_usd_yearly_returns_pct"] = yearly_returns_pct(usd_series)
            out["index_try_yearly_returns_pct"] = yearly_returns_pct(xu_ret.loc[xu_ret.index >= pd.Timestamp(oos_start)])
    return out
