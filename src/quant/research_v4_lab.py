# -*- coding: utf-8 -*-
"""Strategy Research v4 lab: is a (no-margin) short sleeve worth having?

Runs the two pre-registered v4 candidates through exactly the same 5 gates as
v3 (multi-era, 5/25 bps cost stress, 2008 & 2022 crisis, ±20 % plateau,
orthogonality vs Meta-Portfolio A) and then compares the long/short candidate
with its long-only control. A short sleeve "adds value" only if the long/short
version passes every gate AND beats the control on Sharpe over BIL at both
5 bps and 25 bps costs.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.quant.data_loader import DEFAULT_CACHE_DIR, load_universe_closes
from src.quant.research_lab import (
    EVAL_START_DATE,
    PRIOR_TOURNAMENT_TRIALS,
    ResearchV3Gate,
    _compute_meta_a_reference_returns,
    _evaluate_candidate_single,
)
from src.quant.strategies.research_v4 import (
    LONGSHORT_V4_UNIVERSE,
    V4_INVERSE_ETFS,
    build_v4_research_candidates,
)

logger = logging.getLogger(__name__)

DEFAULT_RESEARCH_V4_JSON = DEFAULT_CACHE_DIR / "research_v4_latest.json"
DEFAULT_RESEARCH_V4_REPORT = Path("docs") / "STRATEGY_RESEARCH_V4_REPORT.md"
V3_TRIALS = 3
MIN_SHARPE_EDGE = 0.05  # long/short must beat the control by at least this much


def load_longshort_v4_closes(
    *,
    start_date: str = "2007-01-01",
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """2007+ closes for the v4 pillars, their inverse ETFs and BIL (isolated cache file)."""
    return load_universe_closes(
        "longshort_v4", LONGSHORT_V4_UNIVERSE, start_date=start_date, cache_dir=cache_dir, force_refresh=force_refresh
    )


def short_sleeve_diagnostics(prices: pd.DataFrame, weights: pd.DataFrame) -> Dict[str, Any]:
    """How often, how big and how profitable the inverse-ETF (short) sleeve was since 2008."""
    inv_cols = [c for c in V4_INVERSE_ETFS if c in weights.columns and c in prices.columns]
    held = weights.shift(1).fillna(0.0)
    held = held.loc[held.index >= pd.Timestamp(EVAL_START_DATE)]
    if not inv_cols or held.empty:
        return {"available": False}
    short_w = held[inv_cols].sum(axis=1)
    rets = prices[inv_cols].pct_change().reindex(held.index).fillna(0.0)
    contrib = (held[inv_cols] * rets).sum(axis=1)
    years = max(len(contrib) / 252.0, 1e-9)
    yearly = {str(int(y)): round(float(g.sum()) * 100.0, 2) for y, g in contrib.groupby(contrib.index.year)}
    by_etf = {c: round(float((held[c] * rets[c]).sum()) * 100.0 / years, 2) for c in inv_cols}
    active = short_w > 0.001
    return {
        "available": True,
        "share_of_days_with_short_pct": round(float(active.mean()) * 100.0, 1),
        "avg_short_weight_when_active_pct": round(float(short_w[active].mean()) * 100.0, 1) if active.any() else 0.0,
        "max_short_weight_pct": round(float(short_w.max()) * 100.0, 1),
        "annual_contribution_pct": round(float(contrib.sum()) * 100.0 / years, 2),
        "contribution_by_year_pct": yearly,
        "annual_contribution_by_etf_pct": by_etf,
    }


def _compare_short_vs_control(ls: Dict[str, Any], ctrl: Dict[str, Any]) -> Dict[str, Any]:
    def pick(res: Dict[str, Any]) -> Dict[str, Any]:
        full = res.get("full_2008_plus") or {}
        stress = res.get("cost_stress") or {}
        years = res.get("calendar_years") or {}
        yearly = years.get("yearly") or {}
        return {
            "cagr_pct": full.get("cagr_pct"),
            "excess_sharpe_5bps": (stress.get("5bps") or {}).get("excess_sharpe"),
            "excess_sharpe_25bps": (stress.get("25bps") or {}).get("excess_sharpe"),
            "max_drawdown_pct": full.get("max_drawdown_pct"),
            "return_2008_pct": (yearly.get("2008") or {}).get("return_pct"),
            "return_2022_pct": (yearly.get("2022") or {}).get("return_pct"),
            "verdict": res.get("verdict"),
        }

    a, b = pick(ls), pick(ctrl)
    edge5 = (a["excess_sharpe_5bps"] or 0.0) - (b["excess_sharpe_5bps"] or 0.0)
    edge25 = (a["excess_sharpe_25bps"] or 0.0) - (b["excess_sharpe_25bps"] or 0.0)
    adds_value = (
        ls.get("verdict") == "PROMOTE_TO_FORWARD_PAPER" and edge5 >= MIN_SHARPE_EDGE and edge25 >= MIN_SHARPE_EDGE
    )
    reasons: List[str] = []
    if ls.get("verdict") != "PROMOTE_TO_FORWARD_PAPER":
        reasons.append(f"Long/short aday kapılardan geçemedi ({', '.join(ls.get('failed_gates') or []) or 'veri yok'}).")
    if edge5 < MIN_SHARPE_EDGE:
        reasons.append(f"5 bps'de BIL üstü Sharpe farkı {edge5:+.2f} (gereken ≥ +{MIN_SHARPE_EDGE:.2f}).")
    if edge25 < MIN_SHARPE_EDGE:
        reasons.append(f"25 bps'de BIL üstü Sharpe farkı {edge25:+.2f} (gereken ≥ +{MIN_SHARPE_EDGE:.2f}).")
    return {
        "long_short": a,
        "long_only_control": b,
        "excess_sharpe_edge_5bps": round(edge5, 2),
        "excess_sharpe_edge_25bps": round(edge25, 2),
        "short_adds_value": bool(adds_value),
        "reasons": reasons,
    }


def run_strategy_research_v4(
    *,
    prices: Optional[pd.DataFrame] = None,
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
    """Evaluate the v4 long/short candidate against its long-only control."""
    frame = prices if prices is not None else load_longshort_v4_closes(cache_dir=cache_dir, force_refresh=force_refresh)
    if frame is None or frame.empty or "BIL" not in frame.columns or "SPY" not in frame.columns:
        raise RuntimeError("v4 fiyat verisi (SPY, BIL ve ters ETF'ler) yüklenemedi.")
    rf = frame["BIL"].pct_change()
    spy = frame["SPY"].pct_change()
    meta_ref = meta_a_returns if meta_a_returns is not None else _compute_meta_a_reference_returns(frame)
    candidates = build_v4_research_candidates()
    n_trials = PRIOR_TOURNAMENT_TRIALS + V3_TRIALS + len(candidates)

    results: List[Dict[str, Any]] = []
    for cand in candidates:
        ev = _evaluate_candidate_single(
            cand, frame, rf, spy_returns=spy, meta_a_returns=meta_ref,
            n_trials=n_trials, run_plateau=run_plateau, gate=gate,
        )
        ev["short_sleeve"] = short_sleeve_diagnostics(frame, cand.builder(frame))
        results.append(ev)

    by_id = {r["strategy_id"]: r for r in results}
    comparison = _compare_short_vs_control(by_id["V4_TREND_LONG_SHORT_INVERSE"], by_id["V4_TREND_LONG_ONLY_CONTROL"])
    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eval_start_date": EVAL_START_DATE,
        "data_start": frame.index[0].strftime("%Y-%m-%d"),
        "data_end": frame.index[-1].strftime("%Y-%m-%d"),
        "cumulative_trials_n": n_trials,
        "gate_thresholds": asdict(gate),
        "promoted_ids": [r["strategy_id"] for r in results if r.get("verdict") == "PROMOTE_TO_FORWARD_PAPER"],
        "candidates": results,
        "short_vs_control": comparison,
    }

    if save_outputs:
        target = Path(json_path or DEFAULT_RESEARCH_V4_JSON)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".res_v4_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, target)
        if write_report:
            md = Path(report_path or DEFAULT_RESEARCH_V4_REPORT)
            md.parent.mkdir(parents=True, exist_ok=True)
            md.write_text(format_research_v4_markdown(payload), encoding="utf-8")
    return payload


def _fmt(value: Any, suffix: str = "", signed: bool = True, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):+.{digits}f}{suffix}" if signed else f"{float(value):.{digits}f}{suffix}"


def format_research_v4_markdown(payload: Dict[str, Any]) -> str:
    """Turkish report: long/short vs long-only control, gates and short-sleeve diagnostics."""
    cmp_ = payload.get("short_vs_control") or {}
    ls, ctrl = cmp_.get("long_short") or {}, cmp_.get("long_only_control") or {}
    lines = [
        "# Strateji Araştırması v4 — Short (Ters ETF) Gerçekten Değer Katıyor mu?",
        "",
        f"> **Oluşturulma:** {payload.get('generated_at')} · **Veri:** {payload.get('data_start')} → {payload.get('data_end')} "
        f"· **Değerlendirme:** {payload.get('eval_start_date')}+ · **Kümülatif deneme sayısı:** {payload.get('cumulative_trials_n')}",
        "",
        "Short pozisyon yalnızca **ters ETF satın alarak** alınır (SH, PSQ, EFZ, TBF): kredili hesap, ödünç pay "
        "ya da opsiyon yok; bir pozisyonda en fazla yatırılan para kaybedilir. Ters ETF fiyatları günlük sıfırlama "
        "kaybını ve yönetim ücretini zaten içerir. Parametreler sonuç görülmeden önce sabitlendi.",
        "",
        "## Sonuç",
        "",
        f"**Short değer katıyor mu? {'EVET' if cmp_.get('short_adds_value') else 'HAYIR (kanıt yetersiz)'}**",
        "",
    ]
    for reason in cmp_.get("reasons") or []:
        lines.append(f"- {reason}")
    lines.extend([
        "",
        "| | Long/Short (ters ETF) | Long-Only Kontrol |",
        "| :--- | ---: | ---: |",
        f"| Karar | `{ls.get('verdict')}` | `{ctrl.get('verdict')}` |",
        f"| CAGR (2008+) | {_fmt(ls.get('cagr_pct'), '%')} | {_fmt(ctrl.get('cagr_pct'), '%')} |",
        f"| BIL üstü Sharpe (5 bps) | {_fmt(ls.get('excess_sharpe_5bps'))} | {_fmt(ctrl.get('excess_sharpe_5bps'))} |",
        f"| BIL üstü Sharpe (25 bps) | {_fmt(ls.get('excess_sharpe_25bps'))} | {_fmt(ctrl.get('excess_sharpe_25bps'))} |",
        f"| En büyük düşüş | {_fmt(ls.get('max_drawdown_pct'), '%')} | {_fmt(ctrl.get('max_drawdown_pct'), '%')} |",
        f"| 2008 getirisi | {_fmt(ls.get('return_2008_pct'), '%')} | {_fmt(ctrl.get('return_2008_pct'), '%')} |",
        f"| 2022 getirisi | {_fmt(ls.get('return_2022_pct'), '%')} | {_fmt(ctrl.get('return_2022_pct'), '%')} |",
        "",
    ])
    for cand in payload.get("candidates") or []:
        lines.append(f"## {cand.get('strategy_id')} — `{cand.get('verdict')}` ({cand.get('gates_passed')}/{cand.get('gates_total')} kapı)")
        lines.append("")
        for name, gate in (cand.get("gates") or {}).items():
            lines.append(f"- {'✅' if gate.get('passed') else '❌'} `{name}`: {gate.get('detail')}")
        eras = cand.get("eras") or {}
        if eras:
            lines.append("")
            lines.append("| Rejim | CAGR | BIL üstü | BIL üstü Sharpe | MaxDD |")
            lines.append("| :--- | ---: | ---: | ---: | ---: |")
            for era in eras.values():
                if era.get("available"):
                    lines.append(
                        f"| {era.get('label')} | {_fmt(era.get('cagr_pct'), '%')} | {_fmt(era.get('excess_cagr_pct'), '%')} | "
                        f"{_fmt(era.get('excess_sharpe'))} | {_fmt(era.get('max_drawdown_pct'), '%')} |"
                    )
        short = cand.get("short_sleeve") or {}
        if short.get("available"):
            lines.append("")
            lines.append(
                f"- **Short dilimi:** günlerin %{short['share_of_days_with_short_pct']}'inde aktif; aktifken ortalama ağırlık "
                f"%{short['avg_short_weight_when_active_pct']} (en çok %{short['max_short_weight_pct']}); "
                f"portföye yıllık katkısı {_fmt(short['annual_contribution_pct'], ' puan')}."
            )
            by_etf = ", ".join(f"{k} {_fmt(v, '')}" for k, v in (short.get("annual_contribution_by_etf_pct") or {}).items())
            lines.append(f"- **ETF bazında yıllık katkı (puan):** {by_etf}")
        lines.append(f"- **Bugünkü hedef:** {cand.get('signal_summary') or '—'}")
        lines.append("")
    lines.append(
        "> *Geçmiş test sonucudur, gelecek getirinin garantisi değildir. Ters ETF'ler uzun süre tutulduğunda değer "
        "kaybeder (örn. SH 2010–2026: %−90); yalnızca trend kuralıyla ve kısa süreli kullanılmalıdır.*"
    )
    return "\n".join(lines) + "\n"
