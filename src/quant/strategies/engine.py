# -*- coding: utf-8 -*-
"""Strictly zero-lookahead vectorized backtest engine with explicit transaction costs.

Invariant
---------
Weights decided at close of day ``t`` using only data ``<= t`` are shifted by
exactly 1 trading bar (``weights.shift(1)``) before multiplying against day
``t+1`` asset returns. Transaction costs are deducted on both buys and sells
(``|w_t - w_{t-1}| * cost_bps / 10_000``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from src.quant.stats import PerformanceMetrics, compute_performance_metrics

DEFAULT_OOS_START = "2022-01-01"


@dataclass(frozen=True)
class StrategySpec:
    """Declarative metadata for one tournament strategy."""

    strategy_id: str
    name: str
    universe: str  # us_etf | us_sectors | crypto | bist | meta
    category: str
    description: str
    cost_bps: float = 5.0
    trading_days_per_year: int = 252
    is_benchmark: bool = False
    currency: str = "USD"
    builder: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = None


@dataclass
class StrategyResult:
    """Full empirical output for one evaluated strategy."""

    strategy_id: str
    name: str
    universe: str
    category: str
    description: str
    currency: str
    cost_bps: float
    is_benchmark: bool
    verdict: str = "PENDING"
    oos: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    full: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    current_weights: Dict[str, float] = field(default_factory=dict)
    cash_weight_pct: float = 100.0
    latest_date: Optional[str] = None
    signal_summary: str = ""
    equity_oos_points: List[Dict[str, Any]] = field(default_factory=list)
    # Calendar-year OOS returns in the strategy currency (filled by the tournament)
    yearly_returns_pct: Dict[str, float] = field(default_factory=dict)
    # USD view of TRY strategies (BIST): OOS metrics vs BIL and USD calendar-year returns
    usd: Optional[PerformanceMetrics] = None
    usd_yearly_returns_pct: Dict[str, float] = field(default_factory=dict)
    # Non-serialized internal series used for meta-portfolio construction & cross-sectional DSR
    daily_returns: Optional[pd.Series] = field(default=None, repr=False)
    oos_returns: Optional[pd.Series] = field(default=None, repr=False)
    turnover_series: Optional[pd.Series] = field(default=None, repr=False)
    equity_curve: Optional[pd.Series] = field(default=None, repr=False)
    usd_oos_returns: Optional[pd.Series] = field(default=None, repr=False)

    def to_public_dict(self, *, include_curve: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "universe": self.universe,
            "category": self.category,
            "description": self.description,
            "currency": self.currency,
            "cost_bps": self.cost_bps,
            "is_benchmark": self.is_benchmark,
            "verdict": self.verdict,
            "oos": self.oos.to_dict(),
            "full": self.full.to_dict(),
            "current_weights": dict(self.current_weights),
            "cash_weight_pct": self.cash_weight_pct,
            "latest_date": self.latest_date,
            "signal_summary": self.signal_summary,
        }
        if self.yearly_returns_pct:
            payload["yearly_returns_pct"] = dict(self.yearly_returns_pct)
        if self.usd is not None:
            payload["usd"] = self.usd.to_dict()
            payload["usd_yearly_returns_pct"] = dict(self.usd_yearly_returns_pct)
        if include_curve:
            payload["equity_oos_points"] = list(self.equity_oos_points)
        return payload


def _downsample_equity_curve(equity: pd.Series, max_points: int = 240) -> List[Dict[str, Any]]:
    eq = pd.to_numeric(equity, errors="coerce").dropna()
    if eq.empty:
        return []
    rebased = (eq / float(eq.iloc[0])) * 100.0
    running_max = rebased.cummax()
    dd = ((rebased / running_max) - 1.0) * 100.0

    n = len(rebased)
    if n > max_points:
        step = max(1, n // max_points)
        indices = list(range(0, n, step))
        if indices[-1] != n - 1:
            indices.append(n - 1)
    else:
        indices = list(range(n))

    points: List[Dict[str, Any]] = []
    for idx in indices:
        ts = rebased.index[idx]
        points.append(
            {
                "date": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts),
                "equity": round(float(rebased.iloc[idx]), 2),
                "drawdown_pct": round(float(dd.iloc[idx]), 2),
            }
        )
    return points


def _summarize_weights(weights: Dict[str, float]) -> tuple[Dict[str, float], float, str]:
    clean: Dict[str, float] = {}
    for sym, w in weights.items():
        val = float(w)
        if val > 0.001:
            clean[str(sym)] = round(val * 100.0, 1)
    invested_pct = round(sum(clean.values()), 1)
    cash_pct = round(max(0.0, 100.0 - invested_pct), 1)
    if not clean:
        return {}, 100.0, "%100 Nakit (savunma/trend dışı)"
    top_parts = [f"{sym} %{pct:g}" for sym, pct in sorted(clean.items(), key=lambda kv: kv[1], reverse=True)[:5]]
    if cash_pct >= 1.0:
        top_parts.append(f"Nakit %{cash_pct:g}")
    return clean, cash_pct, " · ".join(top_parts)


def backtest_weight_matrix(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    spec: StrategySpec,
    *,
    oos_start: str = DEFAULT_OOS_START,
    n_trials: int = 25,
    rf_returns: Optional[pd.Series] = None,
) -> StrategyResult:
    """Execute a strictly zero-lookahead backtest from close-of-day ``target_weights``."""
    clean_prices = prices.sort_index().ffill()
    cols = [c for c in target_weights.columns if c in clean_prices.columns]
    if not cols or len(clean_prices) < 30:
        return StrategyResult(
            strategy_id=spec.strategy_id,
            name=spec.name,
            universe=spec.universe,
            category=spec.category,
            description=spec.description,
            currency=spec.currency,
            cost_bps=spec.cost_bps,
            is_benchmark=spec.is_benchmark,
            verdict="FAIL_WEAK",
            signal_summary="Yetersiz fiyat geçmişi",
        )

    w = target_weights.reindex(index=clean_prices.index, columns=cols).fillna(0.0).clip(lower=0.0)
    # Enforce no leverage (>100% total weight scaled down cleanly)
    row_sums = w.sum(axis=1)
    over = row_sums > 1.0
    if bool(over.any()):
        w.loc[over] = w.loc[over].div(row_sums[over], axis=0)

    # Strict T -> T+1 execution shift (zero lookahead!)
    held = w.shift(1).fillna(0.0)
    asset_returns = clean_prices[cols].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    gross_returns = (held * asset_returns).sum(axis=1)

    # Transaction cost charged on both buys and sells (per-side bps)
    turnover = held.diff().abs().sum(axis=1).fillna(0.0)
    cost_rate = float(spec.cost_bps) / 10_000.0
    net_returns = (gross_returns - turnover * cost_rate).clip(lower=-0.95)

    # Trim warm-up period before first non-zero target weight or OOS start
    active_mask = w.sum(axis=1) > 0
    if bool(active_mask.any()):
        first_active = active_mask.idxmax()
        net_returns = net_returns.loc[first_active:]
        turnover = turnover.loc[first_active:]
    equity = 100.0 * (1.0 + net_returns).cumprod()

    oos_ts = pd.Timestamp(oos_start)
    oos_equity = equity.loc[equity.index >= oos_ts]
    if len(oos_equity) < 20:
        oos_equity = equity
    oos_returns = net_returns.loc[oos_equity.index]
    oos_turnover = turnover.loc[oos_equity.index]

    effective_rf = rf_returns if spec.currency == "USD" else None
    full_metrics = compute_performance_metrics(
        equity,
        trading_days_per_year=spec.trading_days_per_year,
        turnover_series=turnover,
        rf_returns=effective_rf,
        n_trials=n_trials,
    )
    oos_metrics = compute_performance_metrics(
        oos_equity,
        trading_days_per_year=spec.trading_days_per_year,
        turnover_series=oos_turnover,
        rf_returns=effective_rf,
        n_trials=n_trials,
    )

    latest_weights_raw = {col: float(w[col].iloc[-1]) for col in cols}
    clean_weights, cash_pct, summary = _summarize_weights(latest_weights_raw)
    latest_ts = w.index[-1]
    latest_date = latest_ts.strftime("%Y-%m-%d") if hasattr(latest_ts, "strftime") else str(latest_ts)

    return StrategyResult(
        strategy_id=spec.strategy_id,
        name=spec.name,
        universe=spec.universe,
        category=spec.category,
        description=spec.description,
        currency=spec.currency,
        cost_bps=spec.cost_bps,
        is_benchmark=spec.is_benchmark,
        oos=oos_metrics,
        full=full_metrics,
        current_weights=clean_weights,
        cash_weight_pct=cash_pct,
        latest_date=latest_date,
        signal_summary=summary,
        equity_oos_points=_downsample_equity_curve(oos_equity),
        daily_returns=net_returns,
        oos_returns=oos_returns,
        turnover_series=turnover,
        equity_curve=equity,
    )


def combine_strategy_returns(
    components: Sequence[tuple[StrategyResult, float]],
    spec: StrategySpec,
    *,
    oos_start: str = DEFAULT_OOS_START,
    n_trials: int = 25,
    rf_returns: Optional[pd.Series] = None,
) -> StrategyResult:
    """Combine already net-of-cost strategy return streams into a Meta-Portfolio ensemble."""
    valid = [(res, float(weight)) for res, weight in components if res.daily_returns is not None and not res.daily_returns.empty and weight > 0]
    if not valid:
        return StrategyResult(
            strategy_id=spec.strategy_id,
            name=spec.name,
            universe=spec.universe,
            category=spec.category,
            description=spec.description,
            currency=spec.currency,
            cost_bps=spec.cost_bps,
            is_benchmark=spec.is_benchmark,
            verdict="FAIL_WEAK",
            signal_summary="Bileşen strateji verisi eksik",
        )

    total_w = sum(w for _, w in valid)
    norm_components = [(res, w / total_w) for res, w in valid]

    # Align on union of trading dates (crypto trades weekends, ETFs trade weekdays -> 0 return on closed days)
    all_index = norm_components[0][0].daily_returns.index
    for res, _ in norm_components[1:]:
        all_index = all_index.union(res.daily_returns.index)
    all_index = all_index.sort_values()

    # Keep only dates where all components have started
    common_start = max(res.daily_returns.index[0] for res, _ in norm_components)
    all_index = all_index[all_index >= common_start]

    combined_ret = pd.Series(0.0, index=all_index)
    combined_to = pd.Series(0.0, index=all_index)
    for res, weight in norm_components:
        r = res.daily_returns.reindex(all_index).fillna(0.0)
        combined_ret = combined_ret + weight * r
        if res.turnover_series is not None:
            combined_to = combined_to + weight * res.turnover_series.reindex(all_index).fillna(0.0)

    # Small monthly rebalance friction across sleeve weights
    equity = 100.0 * (1.0 + combined_ret).cumprod()
    oos_ts = pd.Timestamp(oos_start)
    oos_equity = equity.loc[equity.index >= oos_ts]
    if len(oos_equity) < 20:
        oos_equity = equity
    oos_returns = combined_ret.loc[oos_equity.index]
    oos_turnover = combined_to.loc[oos_equity.index]

    effective_rf = rf_returns if spec.currency == "USD" else None
    full_metrics = compute_performance_metrics(
        equity,
        trading_days_per_year=spec.trading_days_per_year,
        turnover_series=combined_to,
        rf_returns=effective_rf,
        n_trials=n_trials,
    )
    oos_metrics = compute_performance_metrics(
        oos_equity,
        trading_days_per_year=spec.trading_days_per_year,
        turnover_series=oos_turnover,
        rf_returns=effective_rf,
        n_trials=n_trials,
    )

    # Aggregate live current asset weights across component sleeves
    blended_weights: Dict[str, float] = {}
    for res, sleeve_w in norm_components:
        for sym, pct in res.current_weights.items():
            blended_weights[sym] = blended_weights.get(sym, 0.0) + sleeve_w * (pct / 100.0)
    clean_weights, cash_pct, summary = _summarize_weights(blended_weights)
    latest_ts = all_index[-1]
    latest_date = latest_ts.strftime("%Y-%m-%d") if hasattr(latest_ts, "strftime") else str(latest_ts)

    return StrategyResult(
        strategy_id=spec.strategy_id,
        name=spec.name,
        universe=spec.universe,
        category=spec.category,
        description=spec.description,
        currency=spec.currency,
        cost_bps=spec.cost_bps,
        is_benchmark=spec.is_benchmark,
        oos=oos_metrics,
        full=full_metrics,
        current_weights=clean_weights,
        cash_weight_pct=cash_pct,
        latest_date=latest_date,
        signal_summary=summary,
        equity_oos_points=_downsample_equity_curve(oos_equity),
        daily_returns=combined_ret,
        oos_returns=oos_returns,
        turnover_series=combined_to,
        equity_curve=equity,
    )
