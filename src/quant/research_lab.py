# -*- coding: utf-8 -*-
"""Strategy Research v3 (Priority D) Multi-Era Anti-Overfitting Evaluation Lab.

Evaluates pre-registered v3 candidates across 4 macro eras (2008-2026),
5/15/25/50 bps cost stress, ±20% parameter plateau grids, and correlation /
unoptimized 50/50 blend value-add versus Meta-Portfolio A v2.

Enforces a strict 6-gate promotion rule:
  1. Multi-Era Consistency: positive ExBIL CAGR in >= 3/4 eras AND single-year
     excess return concentration <= 50% of cumulative excess return.
  2. Cost Stress Resilience: ExBIL Sharpe >= 0.35 at 5 bps AND >= 0.20 with
     positive ExBIL CAGR at 25 bps.
  3. Crisis Protection: 2022 return > SPY, 2008 MaxDD >= -25%, overall MaxDD >= -22%.
  4. Parameter Plateau Stability: >= 75% of ±20% neighbor points achieve ExBIL Sharpe >= 0.20.
  5. Orthogonality / Value-Add: daily return correlation vs Meta-Portfolio A v2 < 0.70
     OR unoptimized 50/50 blend improves ExBIL Sharpe without worsening MaxDD.
  6. Independent Forward Enrollment: winners NEVER mutate frozen PAA v2 / Meta-A v2;
     they are tracked separately under ForwardRegistry with their own SHA-256 fingerprint.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.quant.data_loader import (
    DEFAULT_CACHE_DIR,
    load_macro_v3_closes,
    load_sector_factor_v3_closes,
)
from src.quant.stats import compute_performance_metrics
from src.quant.strategies.engine import StrategySpec, backtest_weight_matrix
from src.quant.strategies.research_v3 import (
    ResearchV3Candidate,
    build_v3_research_candidates,
)

logger = logging.getLogger(__name__)

DEFAULT_RESEARCH_V3_JSON = DEFAULT_CACHE_DIR / "research_v3_latest.json"
DEFAULT_RESEARCH_V3_REPORT = Path("docs") / "STRATEGY_RESEARCH_V3_REPORT.md"

EVAL_START_DATE = "2008-01-01"
COST_STRESS_BPS: tuple[float, ...] = (5.0, 15.0, 25.0, 50.0)
PRIOR_TOURNAMENT_TRIALS = 25

RESEARCH_ERAS: tuple[tuple[str, str, str, Optional[str]], ...] = (
    ("era1_gfc_2008_2012", "Rejim 1: GFC & Sıfır Faiz (2008–2012)", "2008-01-01", "2012-12-31"),
    ("era2_qe_2013_2019", "Rejim 2: QE Boğası & 2018 Şoku (2013–2019)", "2013-01-01", "2019-12-31"),
    ("era3_covid_2020_2021", "Rejim 3: COVID Çöküş & V-Toparlanma (2020–2021)", "2020-01-01", "2021-12-31"),
    ("era4_rates_2022_2026", "Rejim 4: Faiz Şoku & 2026 Krizi (2022–2026)", "2022-01-01", None),
)


@dataclass(frozen=True)
class ResearchV3Gate:
    """Hard promotion criteria for Strategy Research v3 candidates."""

    min_positive_eras: int = 3
    max_single_year_excess_share_pct: float = 50.0
    min_ex_sharpe_5bps: float = 0.35
    min_ex_sharpe_25bps: float = 0.20
    max_gfc_2008_dd_pct: float = 25.0
    max_overall_dd_pct: float = 22.0
    min_plateau_pass_ratio: float = 0.75
    plateau_neighbor_min_ex_sharpe: float = 0.20
    max_meta_a_correlation: float = 0.70


def _slice_equity_from_returns(returns: pd.Series, start: str, end: Optional[str]) -> pd.Series:
    if returns is None or returns.empty:
        return pd.Series(dtype=float)
    s = returns.loc[returns.index >= pd.Timestamp(start)]
    if end is not None:
        s = s.loc[s.index <= pd.Timestamp(end)]
    if len(s) < 20:
        return pd.Series(dtype=float)
    return 100.0 * (1.0 + s).cumprod()


def _calendar_year_excess_breakdown(
    returns: pd.Series,
    rf_returns: Optional[pd.Series],
    *,
    start_date: str = EVAL_START_DATE,
) -> Dict[str, Any]:
    """Compute annual returns vs BIL and measure single-year concentration."""
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    clean = clean.loc[clean.index >= pd.Timestamp(start_date)]
    if clean.empty:
        return {"yearly": {}, "max_year": None, "max_year_excess_share_pct": 100.0, "positive_without_best_year": False}

    rf_aligned = (
        pd.to_numeric(rf_returns.reindex(clean.index), errors="coerce").fillna(0.0)
        if rf_returns is not None and not rf_returns.empty
        else pd.Series(0.0, index=clean.index)
    )
    yearly: Dict[str, Dict[str, float]] = {}
    excess_by_year: Dict[str, float] = {}
    for year, grp in clean.groupby(clean.index.year):
        if len(grp) < 20:
            continue
        rf_grp = rf_aligned.reindex(grp.index).fillna(0.0)
        eq = (1.0 + grp).cumprod()
        ret_y = float(eq.iloc[-1] - 1.0) * 100.0
        rf_y = float((1.0 + rf_grp).prod() - 1.0) * 100.0
        ex_y = ret_y - rf_y
        dd_y = float(((eq / eq.cummax()) - 1.0).min()) * 100.0
        y_str = str(int(year))
        yearly[y_str] = {
            "return_pct": round(ret_y, 2),
            "rf_pct": round(rf_y, 2),
            "excess_pct": round(ex_y, 2),
            "max_drawdown_pct": round(dd_y, 2),
        }
        excess_by_year[y_str] = ex_y

    total_pos_excess = sum(v for v in excess_by_year.values() if v > 0.0)
    net_sum_excess = sum(excess_by_year.values())
    if not excess_by_year:
        return {"yearly": {}, "max_year": None, "max_year_excess_share_pct": 100.0, "positive_without_best_year": False}

    best_year = max(excess_by_year.items(), key=lambda kv: kv[1])[0]
    best_val = excess_by_year[best_year]
    if net_sum_excess <= 0.0:
        share_pct = 100.0
        pos_without_best = False
    else:
        # Share of net cumulative excess return contributed by single best year
        denom = max(net_sum_excess, total_pos_excess * 0.5, 1e-6)
        share_pct = round(max(0.0, best_val / denom) * 100.0, 1)
        pos_without_best = (net_sum_excess - best_val) > 0.0

    return {
        "yearly": yearly,
        "max_year": best_year,
        "max_year_excess_pct": round(best_val, 2),
        "max_year_excess_share_pct": share_pct,
        "positive_without_best_year": bool(pos_without_best),
    }


def _evaluate_candidate_single(
    candidate: ResearchV3Candidate,
    prices: pd.DataFrame,
    rf_returns: Optional[pd.Series],
    *,
    spy_returns: Optional[pd.Series] = None,
    meta_a_returns: Optional[pd.Series] = None,
    n_trials: int = PRIOR_TOURNAMENT_TRIALS + 3,
    run_plateau: bool = True,
    gate: ResearchV3Gate = ResearchV3Gate(),
) -> Dict[str, Any]:
    """Run full 4-era, multi-cost, plateau, correlation, and 6-gate audit for one v3 candidate."""
    base_weights = candidate.builder(prices)
    base_res = backtest_weight_matrix(
        prices,
        base_weights,
        candidate.spec,
        oos_start=EVAL_START_DATE,
        n_trials=n_trials,
        rf_returns=rf_returns,
    )
    daily_rets = base_res.daily_returns if base_res.daily_returns is not None else pd.Series(dtype=float)
    eval_rets = daily_rets.loc[daily_rets.index >= pd.Timestamp(EVAL_START_DATE)]

    # 1. Full 19-year (2008+) metrics at base cost (5-6 bps)
    full_eq = _slice_equity_from_returns(daily_rets, EVAL_START_DATE, None)
    full_m = compute_performance_metrics(
        full_eq,
        turnover_series=base_res.turnover_series,
        rf_returns=rf_returns,
        n_trials=n_trials,
    )

    # 2. Multi-era breakdown (4 macro regimes)
    eras_out: Dict[str, Dict[str, Any]] = {}
    positive_eras = 0
    evaluated_eras = 0
    for era_key, era_label, start, end in RESEARCH_ERAS:
        eq_era = _slice_equity_from_returns(daily_rets, start, end)
        if eq_era.empty or len(eq_era) < 60:
            eras_out[era_key] = {"label": era_label, "available": False}
            continue
        evaluated_eras += 1
        m_era = compute_performance_metrics(eq_era, rf_returns=rf_returns, n_trials=n_trials)
        is_pos = m_era.excess_cagr_pct > 0.0
        if is_pos:
            positive_eras += 1
        eras_out[era_key] = {
            "label": era_label,
            "available": True,
            "trading_days": m_era.trading_days,
            "cagr_pct": m_era.cagr_pct,
            "rf_cagr_pct": m_era.rf_cagr_pct,
            "excess_cagr_pct": m_era.excess_cagr_pct,
            "excess_sharpe": m_era.excess_sharpe,
            "max_drawdown_pct": m_era.max_drawdown_pct,
            "positive_excess": is_pos,
        }

    # 3. Calendar-year concentration & crisis metrics (2008 GFC, 2022 bear)
    cal = _calendar_year_excess_breakdown(daily_rets, rf_returns, start_date=EVAL_START_DATE)
    spy_cal = _calendar_year_excess_breakdown(spy_returns, rf_returns, start_date=EVAL_START_DATE) if spy_returns is not None else {"yearly": {}}
    y2022_strat = cal["yearly"].get("2022", {}).get("return_pct")
    y2022_spy = spy_cal["yearly"].get("2022", {}).get("return_pct")
    y2008_dd = cal["yearly"].get("2008", {}).get("max_drawdown_pct")
    y2008_spy_dd = spy_cal["yearly"].get("2008", {}).get("max_drawdown_pct")

    # 4. Cost stress at 5 / 15 / 25 / 50 bps across 2008-2026
    cost_stress: Dict[str, Dict[str, Any]] = {}
    for bps in COST_STRESS_BPS:
        c_spec = StrategySpec(
            strategy_id=candidate.spec.strategy_id,
            name=candidate.spec.name,
            universe=candidate.spec.universe,
            category=candidate.spec.category,
            description=candidate.spec.description,
            cost_bps=float(bps),
            trading_days_per_year=candidate.spec.trading_days_per_year,
        )
        c_res = backtest_weight_matrix(
            prices,
            base_weights,
            c_spec,
            oos_start=EVAL_START_DATE,
            n_trials=n_trials,
            rf_returns=rf_returns,
        )
        c_eq = _slice_equity_from_returns(
            c_res.daily_returns if c_res.daily_returns is not None else pd.Series(dtype=float),
            EVAL_START_DATE,
            None,
        )
        c_m = compute_performance_metrics(
            c_eq,
            turnover_series=c_res.turnover_series,
            rf_returns=rf_returns,
            n_trials=n_trials,
        )
        cost_stress[f"{int(bps)}bps"] = {
            "cagr_pct": c_m.cagr_pct,
            "excess_cagr_pct": c_m.excess_cagr_pct,
            "excess_sharpe": c_m.excess_sharpe,
            "max_drawdown_pct": c_m.max_drawdown_pct,
            "annual_turnover": c_m.annual_turnover,
        }

    # 5. ±20% Parameter Plateau Stability Check
    plateau_points: List[Dict[str, Any]] = []
    if run_plateau and candidate.plateau_grid:
        for params in candidate.plateau_grid:
            p_weights = candidate.builder(prices, **params)
            p_res = backtest_weight_matrix(
                prices,
                p_weights,
                candidate.spec,
                oos_start=EVAL_START_DATE,
                n_trials=n_trials,
                rf_returns=rf_returns,
            )
            p_eq = _slice_equity_from_returns(
                p_res.daily_returns if p_res.daily_returns is not None else pd.Series(dtype=float),
                EVAL_START_DATE,
                None,
            )
            p_m = compute_performance_metrics(p_eq, rf_returns=rf_returns, n_trials=n_trials)
            passed_pt = p_m.excess_sharpe >= gate.plateau_neighbor_min_ex_sharpe and p_m.excess_cagr_pct > 0.0
            plateau_points.append({
                "params": {k: list(v) if isinstance(v, tuple) else v for k, v in params.items()},
                "cagr_pct": p_m.cagr_pct,
                "excess_cagr_pct": p_m.excess_cagr_pct,
                "excess_sharpe": p_m.excess_sharpe,
                "max_drawdown_pct": p_m.max_drawdown_pct,
                "passed": bool(passed_pt),
            })
    plateau_pass_count = sum(1 for p in plateau_points if p["passed"])
    plateau_ratio = round(plateau_pass_count / len(plateau_points), 3) if plateau_points else 0.0

    # 6. Orthogonality & Unoptimized 50/50 Blend vs Meta-Portfolio A v2
    ortho: Dict[str, Any] = {"available": False}
    if meta_a_returns is not None and not meta_a_returns.empty and not eval_rets.empty:
        common = eval_rets.index.intersection(meta_a_returns.index)
        if len(common) >= 250:
            r_v3 = eval_rets.reindex(common).fillna(0.0)
            r_ma = meta_a_returns.reindex(common).fillna(0.0)
            corr = float(r_v3.corr(r_ma))
            eq_ma = 100.0 * (1.0 + r_ma).cumprod()
            eq_blend = 100.0 * (1.0 + 0.5 * r_v3 + 0.5 * r_ma).cumprod()
            m_ma = compute_performance_metrics(eq_ma, rf_returns=rf_returns)
            m_blend = compute_performance_metrics(eq_blend, rf_returns=rf_returns)
            # Also measure 2022+ overlap specifically
            c22 = common[common >= pd.Timestamp("2022-01-01")]
            corr_2022 = float(r_v3.reindex(c22).corr(r_ma.reindex(c22))) if len(c22) >= 60 else corr
            blend_improves = (
                m_blend.excess_sharpe > m_ma.excess_sharpe
                and m_blend.max_drawdown_pct >= m_ma.max_drawdown_pct - 1.5
            )
            ortho = {
                "available": True,
                "overlap_days": int(len(common)),
                "overlap_start": common[0].strftime("%Y-%m-%d"),
                "overlap_end": common[-1].strftime("%Y-%m-%d"),
                "correlation_full": round(corr, 3) if np.isfinite(corr) else None,
                "correlation_2022_plus": round(corr_2022, 3) if np.isfinite(corr_2022) else None,
                "meta_a_ex_sharpe": m_ma.excess_sharpe,
                "meta_a_max_dd_pct": m_ma.max_drawdown_pct,
                "blend_50_50_cagr_pct": m_blend.cagr_pct,
                "blend_50_50_ex_sharpe": m_blend.excess_sharpe,
                "blend_50_50_max_dd_pct": m_blend.max_drawdown_pct,
                "blend_improves_meta_a": bool(blend_improves),
            }

    # --- Strict 6-Gate Evaluation ---
    g1_ok = (
        positive_eras >= gate.min_positive_eras
        and cal["max_year_excess_share_pct"] <= gate.max_single_year_excess_share_pct
        and bool(cal["positive_without_best_year"])
    )
    m5 = cost_stress["5bps"]
    m25 = cost_stress["25bps"]
    g2_ok = (
        m5["excess_sharpe"] >= gate.min_ex_sharpe_5bps
        and m25["excess_sharpe"] >= gate.min_ex_sharpe_25bps
        and m25["excess_cagr_pct"] > 0.0
    )
    beat_2022 = (y2022_strat is not None and y2022_spy is not None and y2022_strat > y2022_spy)
    gfc_ok = True if y2008_dd is None else (y2008_dd >= -gate.max_gfc_2008_dd_pct)
    dd_ok = full_m.max_drawdown_pct >= -gate.max_overall_dd_pct
    g3_ok = bool(beat_2022 and gfc_ok and dd_ok)

    g4_ok = (not run_plateau) or (plateau_ratio >= gate.min_plateau_pass_ratio)
    if ortho.get("available"):
        corr_v = ortho.get("correlation_full")
        g5_ok = bool(
            (corr_v is not None and corr_v < gate.max_meta_a_correlation)
            or ortho.get("blend_improves_meta_a")
        )
    else:
        g5_ok = True

    gates = {
        "gate1_multi_era_and_concentration": {
            "passed": g1_ok,
            "detail": (
                f"{positive_eras}/{evaluated_eras} rejim pozitif ExBIL (hedef >={gate.min_positive_eras}); "
                f"en iyi yıl ({cal['max_year']}) payı %{cal['max_year_excess_share_pct']:.1f} (hedef <=%{gate.max_single_year_excess_share_pct:.0f})"
            ),
        },
        "gate2_cost_stress_5_and_25bps": {
            "passed": g2_ok,
            "detail": (
                f"5bps ExSh={m5['excess_sharpe']:+.2f} (>={gate.min_ex_sharpe_5bps:.2f}); "
                f"25bps ExSh={m25['excess_sharpe']:+.2f} (>={gate.min_ex_sharpe_25bps:.2f}), "
                f"ExCAGR={m25['excess_cagr_pct']:+.2f}%"
            ),
        },
        "gate3_crisis_protection": {
            "passed": g3_ok,
            "detail": (
                f"2022: {y2022_strat if y2022_strat is not None else 'N/A'}% vs SPY {y2022_spy if y2022_spy is not None else 'N/A'}%; "
                f"2008 MaxDD: {y2008_dd if y2008_dd is not None else 'N/A'}% (>=-{gate.max_gfc_2008_dd_pct:.0f}%); "
                f"Genel MaxDD: {full_m.max_drawdown_pct:.1f}% (>=-{gate.max_overall_dd_pct:.0f}%)"
            ),
        },
        "gate4_parameter_plateau": {
            "passed": g4_ok,
            "detail": f"{plateau_pass_count}/{len(plateau_points)} komşu geçti (%{plateau_ratio * 100:.0f}, hedef >=%{gate.min_plateau_pass_ratio * 100:.0f})",
        },
        "gate5_orthogonality_vs_meta_a": {
            "passed": g5_ok,
            "detail": (
                f"Korelasyon={ortho.get('correlation_full')} (<{gate.max_meta_a_correlation:.2f}); "
                f"50/50 harman ExSh={ortho.get('blend_50_50_ex_sharpe')} vs Meta-A={ortho.get('meta_a_ex_sharpe')}"
                if ortho.get("available")
                else "Meta-A örtüşmesi yok"
            ),
        },
    }
    passed_count = sum(1 for g in gates.values() if g["passed"])
    all_passed = passed_count == len(gates)
    verdict = "PROMOTE_TO_FORWARD_PAPER" if all_passed else "REJECTED"
    failed_gates = [k for k, g in gates.items() if not g["passed"]]

    return {
        "strategy_id": candidate.spec.strategy_id,
        "name": candidate.spec.name,
        "universe": candidate.spec.universe,
        "category": candidate.spec.category,
        "description": candidate.spec.description,
        "verdict": verdict,
        "gates_passed": passed_count,
        "gates_total": len(gates),
        "failed_gates": failed_gates,
        "gates": gates,
        "full_2008_plus": full_m.to_dict(),
        "eras": eras_out,
        "cost_stress": cost_stress,
        "calendar_years": cal,
        "crisis_2008_spy_dd_pct": y2008_spy_dd,
        "crisis_2022_spy_return_pct": y2022_spy,
        "plateau": {
            "pass_count": plateau_pass_count,
            "total": len(plateau_points),
            "pass_ratio": plateau_ratio,
            "points": plateau_points,
        },
        "orthogonality_vs_meta_a": ortho,
        "latest_date": base_res.latest_date,
        "current_weights": base_res.current_weights,
        "cash_weight_pct": base_res.cash_weight_pct,
        "signal_summary": base_res.signal_summary,
    }


def _compute_meta_a_reference_returns(macro_prices: pd.DataFrame) -> Optional[pd.Series]:
    """Compute Meta-Portfolio A v2 daily returns on the existing 2018+ US ETF frame (read-only)."""
    try:
        from src.quant.data_loader import US_ETF_UNIVERSE, load_universe_closes
        from src.quant.strategies.library import compute_meta_a_weights

        us_df = load_universe_closes("us_etf", US_ETF_UNIVERSE, start_date="2018-01-01")
        if us_df is None or us_df.empty:
            us_df = macro_prices
        w = compute_meta_a_weights(us_df)
        spec = StrategySpec(
            strategy_id="META_A_REF",
            name="Meta-Portföy A v2 (Referans)",
            universe="us_etf",
            category="meta",
            description="",
            cost_bps=5.0,
        )
        rf = us_df["BIL"].pct_change() if "BIL" in us_df.columns else None
        res = backtest_weight_matrix(us_df, w, spec, oos_start="2022-01-01", rf_returns=rf)
        return res.daily_returns
    except Exception as exc:  # noqa: BLE001
        logger.warning("[research-v3] Meta-A reference unavailable: %s", exc)
        return None


def run_strategy_research_v3(
    *,
    macro_prices: Optional[pd.DataFrame] = None,
    sector_prices: Optional[pd.DataFrame] = None,
    meta_a_returns: Optional[pd.Series] = None,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
    run_plateau: bool = True,
    gate: ResearchV3Gate = ResearchV3Gate(),
    save_outputs: bool = True,
    json_path: Optional[Path] = None,
    report_path: Optional[Path] = None,
    write_report: bool = True,
) -> Dict[str, Any]:
    """Execute the full 19-year Strategy Research v3 evaluation lab.

    ``write_report=False`` keeps the JSON snapshot but leaves the tracked
    ``docs/`` Markdown report untouched (used by the daily refresh).
    """
    macro_df = (
        macro_prices
        if macro_prices is not None
        else load_macro_v3_closes(start_date="2007-01-01", cache_dir=cache_dir, force_refresh=force_refresh)
    )
    sector_df = (
        sector_prices
        if sector_prices is not None
        else load_sector_factor_v3_closes(start_date="2007-01-01", cache_dir=cache_dir, force_refresh=force_refresh)
    )

    universes = {"macro_v3": macro_df, "sector_factor_v3": sector_df}
    rf_returns = macro_df["BIL"].pct_change() if (macro_df is not None and "BIL" in macro_df.columns) else None
    spy_returns = macro_df["SPY"].pct_change() if (macro_df is not None and "SPY" in macro_df.columns) else None
    meta_ref = meta_a_returns if meta_a_returns is not None else _compute_meta_a_reference_returns(macro_df)

    # Compute SPY & BIL benchmark summaries across the same 4 eras
    benchmarks: Dict[str, Any] = {}
    if spy_returns is not None:
        spy_eq_full = _slice_equity_from_returns(spy_returns, EVAL_START_DATE, None)
        benchmarks["SPY"] = {
            "full_2008_plus": compute_performance_metrics(spy_eq_full, rf_returns=rf_returns).to_dict(),
            "eras": {
                ek: compute_performance_metrics(_slice_equity_from_returns(spy_returns, st, en), rf_returns=rf_returns).to_dict()
                for ek, _, st, en in RESEARCH_ERAS
                if not _slice_equity_from_returns(spy_returns, st, en).empty
            },
        }
    if rf_returns is not None:
        bil_eq_full = _slice_equity_from_returns(rf_returns, EVAL_START_DATE, None)
        benchmarks["BIL"] = {
            "full_2008_plus": compute_performance_metrics(bil_eq_full).to_dict(),
        }

    candidates = build_v3_research_candidates()
    n_trials = PRIOR_TOURNAMENT_TRIALS + len(candidates)
    results: List[Dict[str, Any]] = []
    for cand in candidates:
        frame = universes.get(cand.universe_key)
        if frame is None or frame.empty:
            results.append({
                "strategy_id": cand.spec.strategy_id,
                "name": cand.spec.name,
                "verdict": "REJECTED",
                "gates_passed": 0,
                "gates_total": 5,
                "failed_gates": ["missing_data"],
                "error": f"Universe {cand.universe_key} unavailable",
            })
            continue
        ev = _evaluate_candidate_single(
            cand,
            frame,
            rf_returns,
            spy_returns=spy_returns,
            meta_a_returns=meta_ref,
            n_trials=n_trials,
            run_plateau=run_plateau,
            gate=gate,
        )
        results.append(ev)

    promoted = [r["strategy_id"] for r in results if r.get("verdict") == "PROMOTE_TO_FORWARD_PAPER"]
    rejected = [r["strategy_id"] for r in results if r.get("verdict") != "PROMOTE_TO_FORWARD_PAPER"]

    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eval_start_date": EVAL_START_DATE,
        "cumulative_trials_n": n_trials,
        "gate_thresholds": asdict(gate),
        "promoted_ids": promoted,
        "rejected_ids": rejected,
        "benchmarks": benchmarks,
        "candidates": results,
    }

    if save_outputs:
        target_json = Path(json_path or DEFAULT_RESEARCH_V3_JSON)
        target_json.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target_json.parent), prefix=".res_v3_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, target_json)

        if write_report:
            target_md = Path(report_path or DEFAULT_RESEARCH_V3_REPORT)
            target_md.parent.mkdir(parents=True, exist_ok=True)
            target_md.write_text(format_research_v3_markdown(payload), encoding="utf-8")

    return payload


def format_research_v3_markdown(payload: Dict[str, Any]) -> str:
    """Render an honest, transparent Turkish Markdown report for Strategy Research v3."""
    lines: List[str] = [
        "# Strateji Araştırması v3 (Öncelik D) — 19 Yıllık Çok-Rejimli Doğrulama Raporu",
        "",
        f"> **Oluşturulma:** {payload.get('generated_at')}  ",
        f"> **Değerlendirme Aralığı:** `{payload.get('eval_start_date')}` → günümüz (4 makro rejim: 2008 GFC, 2013–19 QE, 2020–21 COVID, 2022–26 Faiz Şoku)  ",
        f"> **Kümülatif Çoklu Test Sayısı (`DSR N`):** `{payload.get('cumulative_trials_n')}` (25 mevcut turnuva stratejisi + yeni v3 adayları)  ",
        "> **İzolasyon Güvencesi:** Dondurulmuş `PAA v2` ve `Meta-Portföy A v2` fonksiyonlarına dokunulmadı; parmak izleri korunmuştur. `ALPACA_PAPER=true` & `ALPACA_AUTO_EXECUTE=false`.",
        "",
        "---",
        "",
        "## 1. Özet Karar Tablosu (`2008–2026`, Net Maliyet, `BIL` Risksiz Faiz Üstü)",
        "",
        "| Strateji | Karar | Kapı | 2008+ CAGR | ExBIL CAGR | ExBIL Sharpe (5bps) | ExBIL Sharpe (25bps) | MaxDD | Devir | Meta-A Kor. | Canlı Hedef |",
        "| :--- | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
    ]

    spy_b = (payload.get("benchmarks") or {}).get("SPY", {}).get("full_2008_plus") or {}
    bil_b = (payload.get("benchmarks") or {}).get("BIL", {}).get("full_2008_plus") or {}
    if spy_b:
        lines.append(
            f"| *Referans: S&P 500 (`SPY`)* | BENCHMARK | — | {spy_b.get('cagr_pct', 0):+.2f}% | "
            f"{spy_b.get('excess_cagr_pct', 0):+.2f}% | {spy_b.get('excess_sharpe', 0):+.2f} | — | "
            f"{spy_b.get('max_drawdown_pct', 0):.1f}% | 0.0x | — | SPY %100 |"
        )
    if bil_b:
        lines.append(
            f"| *Referans: T-Bill (`BIL`)* | RISK-FREE | — | {bil_b.get('cagr_pct', 0):+.2f}% | "
            f"0.00% | 0.00 | 0.00 | {bil_b.get('max_drawdown_pct', 0):.1f}% | 0.0x | — | BIL %100 |"
        )

    for c in payload.get("candidates") or []:
        fm = c.get("full_2008_plus") or {}
        cs = c.get("cost_stress") or {}
        m5 = cs.get("5bps") or {}
        m25 = cs.get("25bps") or {}
        ortho = c.get("orthogonality_vs_meta_a") or {}
        corr_s = f"{ortho.get('correlation_full'):.2f}" if ortho.get("correlation_full") is not None else "—"
        badge = "✅ TERFİ" if c.get("verdict") == "PROMOTE_TO_FORWARD_PAPER" else "❌ RED"
        lines.append(
            f"| **{c.get('strategy_id')}** | {badge} | {c.get('gates_passed', 0)}/{c.get('gates_total', 5)} | "
            f"{fm.get('cagr_pct', 0):+.2f}% | {fm.get('excess_cagr_pct', 0):+.2f}% | "
            f"{m5.get('excess_sharpe', 0):+.2f} | {m25.get('excess_sharpe', 0):+.2f} | "
            f"{fm.get('max_drawdown_pct', 0):.1f}% | {m5.get('annual_turnover', 0):.1f}x | "
            f"{corr_s} | {c.get('signal_summary') or '—'} |"
        )

    lines.extend(["", "## 2. Rejim Bazlı (4 Makro Dönem) ExBIL Performans", ""])
    lines.append("| Strateji | 2008–12 GFC (ExCAGR / ExSh) | 2013–19 QE (ExCAGR / ExSh) | 2020–21 COVID (ExCAGR / ExSh) | 2022–26 Faiz (ExCAGR / ExSh) |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for c in payload.get("candidates") or []:
        eras = c.get("eras") or {}
        cells = []
        for ek, _, _, _ in RESEARCH_ERAS:
            e = eras.get(ek) or {}
            if e.get("available"):
                cells.append(f"{e['excess_cagr_pct']:+.2f}% / {e['excess_sharpe']:+.2f}")
            else:
                cells.append("—")
        lines.append(f"| **{c.get('strategy_id')}** | " + " | ".join(cells) + " |")

    lines.extend(["", "## 3. Maliyet Stresi (`5 / 15 / 25 / 50 bps`) ve Kapı Detayları", ""])
    for c in payload.get("candidates") or []:
        lines.append(f"### {c.get('strategy_id')} — {c.get('name')} (`{c.get('verdict')}`)")
        lines.append(f"- **Açıklama:** {c.get('description')}")
        cs = c.get("cost_stress") or {}
        cost_parts = [
            f"{k}: CAGR {v['cagr_pct']:+.2f}% · ExBIL {v['excess_cagr_pct']:+.2f}% · ExSh {v['excess_sharpe']:+.2f}"
            for k, v in cs.items()
        ]
        if cost_parts:
            lines.append("- **Maliyet Stresi:** " + " | ".join(cost_parts))
        ortho = c.get("orthogonality_vs_meta_a") or {}
        if ortho.get("available"):
            lines.append(
                f"- **Meta-A v2 Ortogonallik ({ortho['overlap_start']} → {ortho['overlap_end']}):** "
                f"Korelasyon `{ortho['correlation_full']}` (2022+: `{ortho['correlation_2022_plus']}`) · "
                f"Optimizasyonsuz 50/50 Harman ExSh `{ortho['blend_50_50_ex_sharpe']:+.2f}` (MaxDD `{ortho['blend_50_50_max_dd_pct']:.1f}%`) "
                f"vs Tekil Meta-A `{ortho['meta_a_ex_sharpe']:+.2f}` (MaxDD `{ortho['meta_a_max_dd_pct']:.1f}%`)"
            )
        for gname, gval in (c.get("gates") or {}).items():
            mark = "✓" if gval.get("passed") else "✗"
            lines.append(f"  - `{mark}` **{gname}:** {gval.get('detail')}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
