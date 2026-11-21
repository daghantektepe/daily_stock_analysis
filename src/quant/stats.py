# -*- coding: utf-8 -*-
"""Institutional quantitative performance metrics and Bailey-Lopez de Prado DSR.

Zero external scientific dependencies beyond numpy/pandas (uses math.erf and
Acklam's rational approximation for the inverse standard normal CDF).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Sequence

import numpy as np
import pandas as pd

_EULER_MASCHERONI = 0.5772156649015329


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam approximation, max error < 1.15e-9)."""
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0
    if p == 0.5:
        return 0.0

    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    p_low = 0.02425
    p_high = 1.0 - p_low

    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
            ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


@dataclass
class PerformanceMetrics:
    """Normalized strategy return, risk, risk-free excess, and multiple-testing diagnostics."""

    start_date: Optional[str] = None
    end_date: Optional[str] = None
    trading_days: int = 0
    total_return_pct: float = 0.0
    cagr_pct: float = 0.0
    rf_cagr_pct: float = 0.0
    excess_cagr_pct: float = 0.0
    vol_pct: float = 0.0
    sharpe: float = 0.0
    excess_sharpe: float = 0.0
    sortino: float = 0.0
    max_drawdown_pct: float = 0.0
    calmar: float = 0.0
    recovery_factor: float = 0.0
    win_rate_pct: float = 0.0
    annual_turnover: float = 0.0
    dsr_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def expected_max_sharpe(n_trials: int, sr_std: float) -> float:
    """Expected maximum Sharpe under ``n_trials`` independent tests (Bailey & Lopez de Prado 2014)."""
    n = max(1, int(n_trials))
    if n <= 1 or sr_std <= 0:
        return 0.0
    z1 = norm_ppf(1.0 - 1.0 / n)
    z2 = norm_ppf(1.0 - 1.0 / (n * math.e))
    return sr_std * ((1.0 - _EULER_MASCHERONI) * z1 + _EULER_MASCHERONI * z2)


def deflated_sharpe_ratio(
    returns: pd.Series,
    *,
    n_trials: int = 25,
    sr_variance: Optional[float] = None,
) -> float:
    """Compute Deflated Sharpe Ratio probability in ``[0.0, 100.0]`` (%).

    Corrects observed Sharpe for sample length ``T``, skewness, kurtosis, and
    multiple-testing selection bias across ``n_trials`` candidate strategies.
    """
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    t = len(clean)
    if t < 20:
        return 0.0

    std = float(clean.std(ddof=1))
    if std <= 1e-12:
        return 0.0

    sr_hat = float(clean.mean()) / std
    skew = float(clean.skew())
    if not math.isfinite(skew):
        skew = 0.0
    # pandas .kurt() returns excess kurtosis; raw kurtosis = excess + 3
    kurt_excess = float(clean.kurt())
    if not math.isfinite(kurt_excess):
        kurt_excess = 0.0
    kurt_raw = max(1.0, kurt_excess + 3.0)

    # Cross-sectional variance of non-annualized Sharpes across trials.
    # Conservative fallback: variance of SR under null ~ 1 / (T - 1).
    var_sr = float(sr_variance) if (sr_variance is not None and sr_variance > 0) else (1.0 / max(t - 1, 1))
    sr_star = expected_max_sharpe(n_trials, math.sqrt(var_sr))

    denom_inner = 1.0 - skew * sr_hat + ((kurt_raw - 1.0) / 4.0) * (sr_hat ** 2)
    if denom_inner <= 1e-9:
        denom_inner = 1e-9
    se_sr = math.sqrt(denom_inner / max(t - 1, 1))
    z_stat = (sr_hat - sr_star) / max(se_sr, 1e-12)
    return round(norm_cdf(z_stat) * 100.0, 1)


def compute_performance_metrics(
    equity: pd.Series,
    *,
    trading_days_per_year: int = 252,
    turnover_series: Optional[pd.Series] = None,
    rf_returns: Optional[pd.Series] = None,
    n_trials: int = 25,
    sr_variance: Optional[float] = None,
) -> PerformanceMetrics:
    """Compute full return/risk/risk-free-excess/DSR summary from a daily equity curve."""
    eq = pd.to_numeric(equity, errors="coerce").dropna()
    if len(eq) < 5 or float(eq.iloc[0]) <= 0:
        return PerformanceMetrics()

    returns = eq.pct_change().dropna()
    if returns.empty:
        return PerformanceMetrics()

    n_obs = len(returns)
    years = max(n_obs / float(trading_days_per_year), 1e-9)
    total_mult = float(eq.iloc[-1]) / float(eq.iloc[0])
    total_ret = total_mult - 1.0
    cagr = (total_mult ** (1.0 / years) - 1.0) if total_mult > 0 else -1.0

    vol = float(returns.std(ddof=1)) * math.sqrt(trading_days_per_year)
    ann_mean = float(returns.mean()) * trading_days_per_year
    sharpe = ann_mean / vol if vol > 1e-12 else 0.0

    # Risk-free excess return & true Excess Sharpe (above BIL / T-Bill) when provided
    rf_cagr = 0.0
    excess_cagr = cagr
    excess_sharpe = sharpe
    dsr_series = returns
    if rf_returns is not None and not rf_returns.empty:
        aligned_rf = pd.to_numeric(rf_returns.reindex(returns.index), errors="coerce").dropna()
        if len(aligned_rf) >= 20:
            aligned_s = returns.reindex(aligned_rf.index).dropna()
            aligned_rf = aligned_rf.reindex(aligned_s.index).fillna(0.0)
            if len(aligned_s) >= 20:
                rf_mult = float((1.0 + aligned_rf).prod())
                rf_years = max(len(aligned_rf) / float(trading_days_per_year), 1e-9)
                rf_cagr = (rf_mult ** (1.0 / rf_years) - 1.0) if rf_mult > 0 else 0.0
                excess_cagr = cagr - rf_cagr
                ex_daily = aligned_s - aligned_rf
                ex_vol = float(ex_daily.std(ddof=1)) * math.sqrt(trading_days_per_year)
                ex_mean = float(ex_daily.mean()) * trading_days_per_year
                excess_sharpe = ex_mean / ex_vol if ex_vol > 1e-12 else 0.0
                dsr_series = ex_daily

    downside = returns[returns < 0]
    down_std = float(np.sqrt(np.mean(np.square(downside)))) * math.sqrt(trading_days_per_year) if len(downside) > 0 else 0.0
    sortino = ann_mean / down_std if down_std > 1e-12 else 0.0

    running_max = eq.cummax()
    drawdown = (eq / running_max) - 1.0
    max_dd = float(drawdown.min())
    calmar = (cagr / abs(max_dd)) if max_dd < -1e-9 else 0.0
    recovery = (total_ret / abs(max_dd)) if max_dd < -1e-9 else 0.0

    active_days = returns[returns != 0]
    win_rate = float((active_days > 0).mean()) if len(active_days) > 0 else 0.0

    ann_turnover = 0.0
    if turnover_series is not None and not turnover_series.empty:
        aligned_to = pd.to_numeric(turnover_series.reindex(returns.index).fillna(0.0), errors="coerce").fillna(0.0)
        ann_turnover = float(aligned_to.mean()) * trading_days_per_year

    dsr_pct = deflated_sharpe_ratio(dsr_series, n_trials=n_trials, sr_variance=sr_variance)

    start_str = eq.index[0].strftime("%Y-%m-%d") if hasattr(eq.index[0], "strftime") else str(eq.index[0])
    end_str = eq.index[-1].strftime("%Y-%m-%d") if hasattr(eq.index[-1], "strftime") else str(eq.index[-1])

    return PerformanceMetrics(
        start_date=start_str,
        end_date=end_str,
        trading_days=n_obs,
        total_return_pct=round(total_ret * 100.0, 2),
        cagr_pct=round(cagr * 100.0, 2),
        rf_cagr_pct=round(rf_cagr * 100.0, 2),
        excess_cagr_pct=round(excess_cagr * 100.0, 2),
        vol_pct=round(vol * 100.0, 2),
        sharpe=round(sharpe, 2),
        excess_sharpe=round(excess_sharpe, 2),
        sortino=round(sortino, 2),
        max_drawdown_pct=round(max_dd * 100.0, 2),
        calmar=round(calmar, 2),
        recovery_factor=round(recovery, 2),
        win_rate_pct=round(win_rate * 100.0, 1),
        annual_turnover=round(ann_turnover, 2),
        dsr_pct=dsr_pct,
    )


def classify_strategy_verdict(
    oos: PerformanceMetrics,
    *,
    universe: str,
    is_benchmark: bool = False,
    min_oos_days: int = 0,
) -> str:
    """Assign an objective out-of-sample verdict badge anchored on risk-free excess alpha."""
    if is_benchmark:
        return "BENCHMARK"
    if min_oos_days > 0 and oos.trading_days < min_oos_days:
        return "FAIL_WEAK"
    if universe == "bist":
        # Current-constituent BIST universe carries survivorship & TRY-inflation caveat
        return "CAVEAT_SURVIVORSHIP" if oos.sharpe >= 0.5 else "FAIL_WEAK"

    has_rf_benchmark = oos.rf_cagr_pct > 0.05
    if has_rf_benchmark:
        # Strict risk-free hurdle: must beat T-Bills (BIL) with meaningful Excess Sharpe
        if oos.excess_sharpe >= 0.40 and oos.excess_cagr_pct >= 2.5 and oos.max_drawdown_pct >= -35.0:
            return "PASS_ELITE"
        if oos.excess_sharpe >= 0.15 and oos.excess_cagr_pct > 0.0 and oos.max_drawdown_pct >= -35.0:
            return "PASS_SOLID"
        return "FAIL_WEAK"

    if oos.sharpe >= 0.65 and oos.cagr_pct >= 6.0 and oos.max_drawdown_pct >= -35.0:
        return "PASS_ELITE"
    if oos.sharpe >= 0.45 and oos.cagr_pct > 0.0:
        return "PASS_SOLID"
    return "FAIL_WEAK"


def compute_cross_sectional_sr_variance(return_series_list: Sequence[pd.Series]) -> Optional[float]:
    """Compute cross-sectional variance of non-annualized Sharpes across tournament trials."""
    srs = []
    for series in return_series_list:
        clean = pd.to_numeric(series, errors="coerce").dropna()
        if len(clean) < 20:
            continue
        std = float(clean.std(ddof=1))
        if std > 1e-12:
            srs.append(float(clean.mean()) / std)
    if len(srs) < 3:
        return None
    var = float(np.var(srs, ddof=1))
    return var if var > 1e-12 else None
