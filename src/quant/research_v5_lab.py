# -*- coding: utf-8 -*-
"""Strategy Research v5 lab: does correlation-aware (Min-Corr) sizing beat naive 1/vol?

Runs the two pre-registered v5 candidates through the exact same 5 gates as v3/v4
(multi-era, 5/25 bps cost stress, 2008 & 2022 crisis, ±20 % plateau, orthogonality
vs Meta-Portfolio A) and compares ``V5_MINCORR_TREND_RISK_PARITY`` against its
single-variable control ``V5_INVVOL_TREND_CONTROL``. Correlation-aware sizing
"adds value" only if the Min-Corr candidate passes all 5 gates AND beats the
1/vol control on BIL-excess Sharpe by at least +0.05 at both 5 bps and 25 bps.
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

from src.quant.data_loader import DEFAULT_CACHE_DIR, load_macro_v3_closes
from src.quant.research_lab import (
    EVAL_START_DATE,
    PRIOR_TOURNAMENT_TRIALS,
    ResearchV3Gate,
    _compute_meta_a_reference_returns,
    _evaluate_candidate_single,
)
from src.quant.strategies.research_v5 import (
    V5_RISK_ASSETS,
    build_v5_research_candidates,
)

logger = logging.getLogger(__name__)

DEFAULT_RESEARCH_V5_JSON = DEFAULT_CACHE_DIR / "research_v5_latest.json"
DEFAULT_RESEARCH_V5_REPORT = Path("docs") / "STRATEGY_RESEARCH_V5_REPORT.md"
V3_TRIALS = 3
V4_TRIALS = 2
MIN_SHARPE_EDGE = 0.05

_EQUITY_CLUSTER = ("SPY", "QQQ", "EFA", "EEM", "VNQ")
_DIVERSIFIER_CLUSTER = ("TLT", "IEF", "GLD", "DBC", "UUP")


def concentration_diagnostics(weights: pd.DataFrame) -> Dict[str, Any]:
    """Compare equity-cluster vs diversifier-cluster weight share since 2008."""
    held = weights.shift(1).fillna(0.0)
    held = held.loc[held.index >= pd.Timestamp(EVAL_START_DATE)]
    risk_cols = [c for c in V5_RISK_ASSETS if c in held.columns]
    if not risk_cols or held.empty:
        return {"available": False}
    risk_sum = held[risk_cols].sum(axis=1)
    active = risk_sum > 0.001
    eq_cols = [c for c in _EQUITY_CLUSTER if c in held.columns]
    div_cols = [c for c in _DIVERSIFIER_CLUSTER if c in held.columns]
    eq_share = (held[eq_cols].sum(axis=1)[active] / risk_sum[active]).mean() * 100.0 if active.any() and eq_cols else 0.0
    div_share = (held[div_cols].sum(axis=1)[active] / risk_sum[active]).mean() * 100.0 if active.any() and div_cols else 0.0
    hhi = ((held[risk_cols].div(risk_sum.replace(0.0, pd.NA), axis=0)) ** 2).sum(axis=1).dropna()
    return {
        "available": True,
        "active_days_pct": round(float(active.mean()) * 100.0, 1),
        "avg_risk_weight_pct": round(float(risk_sum.mean()) * 100.0, 1),
        "equity_cluster_share_of_risk_pct": round(float(eq_share), 1),
        "diversifier_cluster_share_of_risk_pct": round(float(div_share), 1),
        "avg_normalized_hhi": round(float(hhi.mean()), 3) if not hhi.empty else None,
    }


def _compare_mincorr_vs_control(mc: Dict[str, Any], ctrl: Dict[str, Any]) -> Dict[str, Any]:
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

    a, b = pick(mc), pick(ctrl)
    edge5 = (a["excess_sharpe_5bps"] or 0.0) - (b["excess_sharpe_5bps"] or 0.0)
    edge25 = (a["excess_sharpe_25bps"] or 0.0) - (b["excess_sharpe_25bps"] or 0.0)
    adds_value = (
        mc.get("verdict") == "PROMOTE_TO_FORWARD_PAPER" and edge5 >= MIN_SHARPE_EDGE and edge25 >= MIN_SHARPE_EDGE
    )
    reasons: List[str] = []
    if mc.get("verdict") != "PROMOTE_TO_FORWARD_PAPER":
        reasons.append(f"Min-Corr aday kapılardan geçemedi ({', '.join(mc.get('failed_gates') or []) or 'veri yok'}).")
    if edge5 < MIN_SHARPE_EDGE:
        reasons.append(f"5 bps'de BIL üstü Sharpe farkı {edge5:+.2f} (gereken ≥ +{MIN_SHARPE_EDGE:.2f}).")
    if edge25 < MIN_SHARPE_EDGE:
        reasons.append(f"25 bps'de BIL üstü Sharpe farkı {edge25:+.2f} (gereken ≥ +{MIN_SHARPE_EDGE:.2f}).")
    return {
        "mincorr": a,
        "invvol_control": b,
        "excess_sharpe_edge_5bps": round(edge5, 2),
        "excess_sharpe_edge_25bps": round(edge25, 2),
        "mincorr_adds_value": bool(adds_value),
        "reasons": reasons,
    }


def run_strategy_research_v5(
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
    """Evaluate the v5 Min-Corr trend candidate against its 1/vol control."""
    frame = prices if prices is not None else load_macro_v3_closes(cache_dir=cache_dir, force_refresh=force_refresh)
    if frame is None or frame.empty or "BIL" not in frame.columns or "SPY" not in frame.columns:
        raise RuntimeError("v5 fiyat verisi (SPY, BIL ve makro ETF'ler) yüklenemedi.")
    rf = frame["BIL"].pct_change()
    spy = frame["SPY"].pct_change()
    meta_ref = meta_a_returns if meta_a_returns is not None else _compute_meta_a_reference_returns(frame)
    candidates = build_v5_research_candidates()
    n_trials = PRIOR_TOURNAMENT_TRIALS + V3_TRIALS + V4_TRIALS + len(candidates)

    results: List[Dict[str, Any]] = []
    for cand in candidates:
        ev = _evaluate_candidate_single(
            cand,
            frame,
            rf,
            spy_returns=spy,
            meta_a_returns=meta_ref,
            n_trials=n_trials,
            run_plateau=run_plateau,
            gate=gate,
        )
        ev["concentration"] = concentration_diagnostics(cand.builder(frame))
        results.append(ev)

    by_id = {r["strategy_id"]: r for r in results}
    comparison = _compare_mincorr_vs_control(
        by_id["V5_MINCORR_TREND_RISK_PARITY"],
        by_id["V5_INVVOL_TREND_CONTROL"],
    )
    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eval_start_date": EVAL_START_DATE,
        "data_start": frame.index[0].strftime("%Y-%m-%d"),
        "data_end": frame.index[-1].strftime("%Y-%m-%d"),
        "cumulative_trials_n": n_trials,
        "gate_thresholds": asdict(gate),
        "promoted_ids": [r["strategy_id"] for r in results if r.get("verdict") == "PROMOTE_TO_FORWARD_PAPER"],
        "candidates": results,
        "mincorr_vs_control": comparison,
    }

    if save_outputs:
        target = Path(json_path or DEFAULT_RESEARCH_V5_JSON)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".res_v5_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, target)
        if write_report:
            md = Path(report_path or DEFAULT_RESEARCH_V5_REPORT)
            md.parent.mkdir(parents=True, exist_ok=True)
            md.write_text(format_research_v5_markdown(payload), encoding="utf-8")
    return payload


def _fmt(value: Any, suffix: str = "", signed: bool = True, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):+.{digits}f}{suffix}" if signed else f"{float(value):.{digits}f}{suffix}"


def format_research_v5_markdown(payload: Dict[str, Any]) -> str:
    """Turkish report: Min-Corr vs 1/vol control, 5 gates and cluster concentration diagnostics."""
    cmp_ = payload.get("mincorr_vs_control") or {}
    mc, ctrl = cmp_.get("mincorr") or {}, cmp_.get("invvol_control") or {}
    lines = [
        "# Strateji Araştırması v5 — Korelasyon-Duyarlı (Min-Corr) Ağırlıklandırma 1/vol'e Göre Değer Katıyor mu?",
        "",
        f"> **Oluşturulma:** {payload.get('generated_at')} · **Veri:** {payload.get('data_start')} → {payload.get('data_end')} "
        f"· **Değerlendirme:** {payload.get('eval_start_date')}+ · **Kümülatif deneme sayısı:** {payload.get('cumulative_trials_n')}",
        "",
        "Aynı 10 makro ETF (`SPY, QQQ, EFA, EEM, VNQ, TLT, IEF, GLD, DBC, UUP`) ve `BIL` nakit kalkanı üzerinde "
        "aynı trend kuralı (`SMA200` + `12A > BIL`) ve aynı `%8` hedef volatilite kullanıldı; iki aday yalnızca "
        "`use_corr_penalty` anahtarında ayrılır. Parametreler sonuç görülmeden önce sabitlendi.",
        "",
        "## Sonuç",
        "",
        f"**Min-Corr ağırlıklandırma 1/vol kontrol grubuna göre değer katıyor mu? {'EVET' if cmp_.get('mincorr_adds_value') else 'HAYIR (kanıt yetersiz)'}**",
        "",
    ]
    for reason in cmp_.get("reasons") or []:
        lines.append(f"- {reason}")
    lines.extend([
        "",
        "| | Min-Corr Trend Risk Paritesi | Basit 1/vol Kontrol |",
        "| :--- | ---: | ---: |",
        f"| Karar | `{mc.get('verdict')}` | `{ctrl.get('verdict')}` |",
        f"| CAGR (2008+) | {_fmt(mc.get('cagr_pct'), '%')} | {_fmt(ctrl.get('cagr_pct'), '%')} |",
        f"| BIL üstü Sharpe (5 bps) | {_fmt(mc.get('excess_sharpe_5bps'))} | {_fmt(ctrl.get('excess_sharpe_5bps'))} |",
        f"| BIL üstü Sharpe (25 bps) | {_fmt(mc.get('excess_sharpe_25bps'))} | {_fmt(ctrl.get('excess_sharpe_25bps'))} |",
        f"| En büyük düşüş | {_fmt(mc.get('max_drawdown_pct'), '%')} | {_fmt(ctrl.get('max_drawdown_pct'), '%')} |",
        f"| 2008 getirisi | {_fmt(mc.get('return_2008_pct'), '%')} | {_fmt(ctrl.get('return_2008_pct'), '%')} |",
        f"| 2022 getirisi | {_fmt(mc.get('return_2022_pct'), '%')} | {_fmt(ctrl.get('return_2022_pct'), '%')} |",
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
        conc = cand.get("concentration") or {}
        if conc.get("available"):
            lines.append("")
            lines.append(
                f"- **Küme dağılımı (aktif risk içinde):** Hisse kümesi (`SPY/QQQ/EFA/EEM/VNQ`) %{conc['equity_cluster_share_of_risk_pct']} · "
                f"Çeşitlendirici küme (`TLT/IEF/GLD/DBC/UUP`) %{conc['diversifier_cluster_share_of_risk_pct']} · "
                f"Ortalama toplam risk ağırlığı %{conc['avg_risk_weight_pct']}."
            )
        lines.append(f"- **Bugünkü hedef:** {cand.get('signal_summary') or '—'}")
        lines.append("")
    lines.append(
        "> *Geçmiş test sonucudur, gelecek getirinin garantisi değildir. Dondurulmuş ileri doğrulama stratejileri "
        "(`paa`, `meta_a`, `v3_trp`) bu araştırmadan etkilenmez.*"
    )
    return "\n".join(lines) + "\n"
