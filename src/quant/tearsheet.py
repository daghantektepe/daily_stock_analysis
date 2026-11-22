# -*- coding: utf-8 -*-
"""QuantStats-style visual tearsheet builder (Monthly Heatmap + Underwater + TL/USD/TÜFE)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from data_provider.evds_fetcher import EvdsMacroFetcher, compute_real_purchase_power_tr
from src.quant.data_loader import DEFAULT_CACHE_DIR
from src.quant.portfolio import build_meta_portfolios
from src.quant.strategies.engine import DEFAULT_OOS_START, StrategyResult, StrategySpec, backtest_weight_matrix
from src.quant.strategies.library import (
    compute_paa_weights,
    run_all_base_strategies,
)
from src.quant.strategies.research_v3 import compute_v3_trend_risk_parity_bil_weights

logger = logging.getLogger(__name__)

_DEFAULT_BOOK_DIR = Path("data") / "strategy_paper"
_TEARSHEET_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}


def _load_cached_closes(filename: str) -> pd.DataFrame:
    path = DEFAULT_CACHE_DIR / filename
    if not path.is_file():
        return pd.DataFrame()
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def compute_monthly_returns_matrix(equity: pd.Series) -> Tuple[List[Dict[str, Any]], Dict[str, Optional[float]]]:
    """Build year-by-month return matrix (%) and summary monthly stats from daily equity curve."""
    eq = pd.to_numeric(equity, errors="coerce").dropna()
    if len(eq) < 2:
        return [], {"win_months_pct": None, "best_month_pct": None, "worst_month_pct": None, "months_count": 0}

    eq = eq.sort_index()
    monthly_end = eq.resample("ME").last().dropna()
    # Prepend initial equity before the first month-end so month 1 return is captured accurately
    first_val = float(eq.iloc[0])
    monthly_rets = monthly_end.pct_change()
    if len(monthly_end) >= 1 and first_val > 0:
        monthly_rets.iloc[0] = (float(monthly_end.iloc[0]) / first_val) - 1.0
    monthly_rets = monthly_rets.dropna()

    years_map: Dict[int, Dict[str, Any]] = {}
    all_pcts: List[float] = []
    for ts, ret in monthly_rets.items():
        pct = round(float(ret) * 100.0, 2)
        all_pcts.append(pct)
        yr = int(ts.year)
        mo = str(int(ts.month))
        if yr not in years_map:
            years_map[yr] = {"year": yr, "months": {}, "ytd_pct": None}
        years_map[yr]["months"][mo] = pct

    rows: List[Dict[str, Any]] = []
    for yr in sorted(years_map.keys(), reverse=True):
        row = years_map[yr]
        comp = 1.0
        for m_val in row["months"].values():
            comp *= 1.0 + (float(m_val) / 100.0)
        row["ytd_pct"] = round((comp - 1.0) * 100.0, 2)
        rows.append(row)

    wins = sum(1 for p in all_pcts if p > 0)
    stats = {
        "win_months_pct": round((wins / len(all_pcts)) * 100.0, 1) if all_pcts else None,
        "best_month_pct": round(max(all_pcts), 2) if all_pcts else None,
        "worst_month_pct": round(min(all_pcts), 2) if all_pcts else None,
        "months_count": len(all_pcts),
    }
    return rows, stats


def build_underwater_series(
    equity: pd.Series,
    benchmark: Optional[pd.Series] = None,
    *,
    max_points: int = 240,
) -> List[Dict[str, Any]]:
    """Compute underwater drawdown series (%) and normalized NAV aligned against SPY benchmark."""
    eq = pd.to_numeric(equity, errors="coerce").dropna()
    if eq.empty:
        return []
    eq_norm = (eq / float(eq.iloc[0])) * 100.0
    dd = ((eq_norm / eq_norm.cummax()) - 1.0) * 100.0

    spy_dd: Optional[pd.Series] = None
    if benchmark is not None and not benchmark.empty:
        bench_aligned = pd.to_numeric(benchmark, errors="coerce").reindex(eq.index).ffill().bfill()
        if not bench_aligned.dropna().empty and float(bench_aligned.iloc[0]) > 0:
            b_norm = (bench_aligned / float(bench_aligned.iloc[0])) * 100.0
            spy_dd = ((b_norm / b_norm.cummax()) - 1.0) * 100.0

    n = len(eq_norm)
    if n > max_points:
        step = max(1, n // max_points)
        indices = list(range(0, n, step))
        if indices[-1] != n - 1:
            indices.append(n - 1)
    else:
        indices = list(range(n))

    points: List[Dict[str, Any]] = []
    for idx in indices:
        ts = eq_norm.index[idx]
        points.append(
            {
                "date": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10],
                "nav_idx": round(float(eq_norm.iloc[idx]), 2),
                "drawdown_pct": round(float(dd.iloc[idx]), 2),
                "benchmark_dd_pct": round(float(spy_dd.iloc[idx]), 2) if spy_dd is not None else None,
            }
        )
    return points


def _build_backtest_equity(strategy_key: str) -> Tuple[str, pd.Series, Optional[pd.Series], Dict[str, Any]]:
    key = (strategy_key or "meta_a").strip().lower()
    us_etf = _load_cached_closes("closes_us_etf.csv")
    macro_v3 = _load_cached_closes("closes_macro_v3.csv")

    if key == "v3_trp":
        prices = macro_v3 if not macro_v3.empty else us_etf
        if prices.empty:
            return "v3_trp", pd.Series(dtype=float), None, {}
        rf = prices["BIL"].pct_change().fillna(0.0) if "BIL" in prices.columns else None
        weights = compute_v3_trend_risk_parity_bil_weights(prices)
        spec = StrategySpec(
            strategy_id="V3_TREND_RISK_PARITY_BIL",
            name="v3 Vol-Frenli Trend Risk Paritesi (BIL)",
            universe="macro_v3",
            category="Trend & Risk Parity",
            description="6 varlık sınıfında BIL nakit korumalı risk paritesi.",
            cost_bps=5.0,
        )
        res = backtest_weight_matrix(prices, weights, spec, oos_start="2008-01-01", rf_returns=rf)
        spy = prices["SPY"] if "SPY" in prices.columns else None
        eq = res.equity_curve if res.equity_curve is not None else pd.Series(dtype=float)
        return "v3 Vol-Frenli Trend Risk Paritesi (BIL)", eq, spy, res.oos.to_dict()

    if us_etf.empty:
        return key.upper(), pd.Series(dtype=float), None, {}

    rf = us_etf["BIL"].pct_change().fillna(0.0) if "BIL" in us_etf.columns else None
    spy = us_etf["SPY"] if "SPY" in us_etf.columns else None

    if key == "paa":
        weights = compute_paa_weights(us_etf)
        spec = StrategySpec(
            strategy_id="PROTECTIVE_ASSET_ALLOCATION_PAA",
            name="PAA Çöküş Kalkanı (v2)",
            universe="us_etf",
            category="Defensive TAA",
            description="252g momentum + genişlik koruma kalkanı.",
            cost_bps=5.0,
        )
        res = backtest_weight_matrix(us_etf, weights, spec, oos_start=DEFAULT_OOS_START, rf_returns=rf)
        eq = res.equity_curve if res.equity_curve is not None else pd.Series(dtype=float)
        return "PAA Çöküş Kalkanı (v2)", eq, spy, res.oos.to_dict()

    # Default: Meta-Portfolio A v2 across full cached history
    base = run_all_base_strategies({"us_etf": us_etf})
    metas = build_meta_portfolios(base, oos_start=DEFAULT_OOS_START, n_trials=25, rf_returns=rf)
    meta_a: StrategyResult = metas["META_US_ETF_ALL_WEATHER"]
    eq = meta_a.equity_curve if meta_a.equity_curve is not None else pd.Series(dtype=float)
    return "Meta-Portföy A v2 (ABD ETF Şampiyonu)", eq, spy, meta_a.oos.to_dict()


def build_quant_tearsheet(
    strategy_key: str = "meta_a",
    *,
    mode: str = "backtest",
    book_dir: Optional[Path] = None,
    macro_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble QuantStats tearsheet payload: monthly matrix, underwater DD, KPIs, and TRY/USD/CPI check."""
    key = (strategy_key or "meta_a").strip().lower()
    src_mode = (mode or "backtest").strip().lower()
    b_dir = Path(book_dir or _DEFAULT_BOOK_DIR)

    label = key.upper()
    eq = pd.Series(dtype=float)
    spy_eq: Optional[pd.Series] = None
    kpis: Dict[str, Any] = {}

    if src_mode == "paper":
        book_path = b_dir / f"quant_{key}.json"
        if book_path.is_file():
            raw = json.loads(book_path.read_text(encoding="utf-8"))
            label = str(raw.get("label") or key)
            hist = raw.get("history") or []
            if hist:
                dates = pd.to_datetime([h["date"] for h in hist])
                eq = pd.Series([float(h.get("nav") or 10000.0) for h in hist], index=dates)
                if all(h.get("benchmark_nav") is not None for h in hist):
                    spy_eq = pd.Series([float(h["benchmark_nav"]) for h in hist], index=dates)
                if len(eq) >= 2:
                    tot = round(((float(eq.iloc[-1]) / float(eq.iloc[0])) - 1.0) * 100.0, 2)
                    kpis = {
                        "total_return_pct": tot,
                        "cagr_pct": tot,
                        "max_drawdown_pct": round(float(((eq / eq.cummax()) - 1.0).min() * 100.0), 2),
                        "trading_days": len(eq),
                    }
    else:
        cached = _TEARSHEET_CACHE.get((key, src_mode))
        if cached is not None:
            label, eq, spy_eq, kpis = cached["label"], cached["eq"], cached["spy_eq"], cached["kpis"]
        else:
            label, eq, spy_eq, kpis = _build_backtest_equity(key)
            if not eq.empty:
                _TEARSHEET_CACHE[(key, src_mode)] = {"label": label, "eq": eq, "spy_eq": spy_eq, "kpis": kpis}

    monthly_rows, month_stats = compute_monthly_returns_matrix(eq)
    underwater = build_underwater_series(eq, spy_eq)

    # Trailing 1Y return in USD vs TRY & TÜFE comparison using local/cached macro snapshot
    if macro_snapshot is None:
        try:
            macro_snapshot = EvdsMacroFetcher.from_config().get_macro_snapshot()
        except Exception:
            macro_snapshot = {}

    usd_1y_ret: Optional[float] = None
    if len(eq) >= 2:
        lookback_idx = max(0, len(eq) - 252)
        base_v = float(eq.iloc[lookback_idx])
        if base_v > 0:
            usd_1y_ret = round(((float(eq.iloc[-1]) / base_v) - 1.0) * 100.0, 2)

    fx_1y = macro_snapshot.get("usd_try_1y_change_pct") if isinstance(macro_snapshot, dict) else None
    cpi_yoy = macro_snapshot.get("cpi_yoy_pct") if isinstance(macro_snapshot, dict) else None
    try_equiv_ret: Optional[float] = None
    real_tufe_ret: Optional[float] = None
    if usd_1y_ret is not None and fx_1y is not None:
        try_equiv_ret = round((((1.0 + usd_1y_ret / 100.0) * (1.0 + float(fx_1y) / 100.0)) - 1.0) * 100.0, 2)
        if cpi_yoy is not None:
            pp = compute_real_purchase_power_tr(
                nominal_return_pct=try_equiv_ret,
                usd_try_change_pct=float(fx_1y),
                cpi_yoy_pct=float(cpi_yoy),
            )
            real_tufe_ret = pp.get("real_tufe_return_pct")

    return {
        "ok": True,
        "strategy_key": key,
        "label": label,
        "mode": src_mode,
        "metrics": {**kpis, **month_stats},
        "monthly_matrix": monthly_rows,
        "underwater": underwater,
        "currency_comparison": {
            "usd_1y_return_pct": usd_1y_ret,
            "usd_try_spot": macro_snapshot.get("usd_try") if isinstance(macro_snapshot, dict) else None,
            "usd_try_1y_change_pct": fx_1y,
            "try_equivalent_1y_return_pct": try_equiv_ret,
            "cpi_yoy_pct": cpi_yoy,
            "real_tufe_1y_return_pct": real_tufe_ret,
            "cpi_source": macro_snapshot.get("cpi_source") if isinstance(macro_snapshot, dict) else "unavailable",
        },
    }
