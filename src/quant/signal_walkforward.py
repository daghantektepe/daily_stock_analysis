# -*- coding: utf-8 -*-
"""Deterministic Walk-Forward & Out-of-Sample Validator for the 80% Signal Gate.

Evaluates pre-registered causal entry rules (matching the deterministic half of
``signal_reliability_gate``) across:
- In-Sample window: ``2018-01-01`` .. ``2021-12-31``
- Out-of-Sample Walk-Forward windows: 6-month non-overlapping slices from ``2022-01-01`` onward

Strict isolation invariant:
- MUST NOT import ``src/quant/strategies/library.py`` or ``research_v3.py`` so
  frozen forward-validation fingerprints stay untouched.
- Strictly zero-lookahead: signals computed on closes ``<= t`` enter at ``t+1``
  close and are evaluated over the next ``horizon_days`` (10) trading closes net
  of round-trip commission + slippage (``cost_bps``).
"""

from __future__ import annotations

import json
import logging
import os
import random
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.quant.data_loader import DEFAULT_CACHE_DIR, US_ETF_UNIVERSE, load_universe_closes

logger = logging.getLogger(__name__)

DEFAULT_SIGNAL_WALKFORWARD_JSON = DEFAULT_CACHE_DIR / "signal_walkforward_latest.json"
DEFAULT_SIGNAL_WALKFORWARD_REPORT = Path("docs") / "SIGNAL_WALKFORWARD_REPORT.md"


@dataclass(frozen=True)
class SignalAcceptanceGate:
    """Hard verification criteria for the 80% directional signal precision target."""

    min_samples: int = 30
    min_precision_pct: float = 80.0
    min_precision_ci90_low_pct: float = 65.0
    min_benchmark_beat_ci90_low_pct: float = 50.0
    min_profit_factor_net: float = 1.50
    max_drawdown_pct: float = -12.0


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0).rolling(period, min_periods=period).mean()
    loss = (-delta.clip(upper=0.0)).rolling(period, min_periods=period).mean()
    rs = gain / loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _bootstrap_ci90(values: Sequence[float], *, min_sample: int = 30, iterations: int = 2000, seed: int = 42) -> Optional[List[float]]:
    n = len(values)
    if n < min_sample:
        return None
    rng = random.Random(seed)
    vals = list(values)
    means: List[float] = []
    for _ in range(iterations):
        sample = [vals[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    low_idx = max(0, min(n - 1 if len(means) == 0 else len(means) - 1, int(0.05 * (len(means) - 1))))
    high_idx = max(0, min(len(means) - 1, int(0.95 * (len(means) - 1))))
    return [round(means[low_idx] * 100.0, 1), round(means[high_idx] * 100.0, 1)]


def generate_causal_signal_trades(
    closes: pd.DataFrame,
    *,
    benchmark_col: str = "SPY",
    exclude_cols: Sequence[str] = ("BIL", "SHY", "IEF", "TLT", "UUP"),
    horizon_days: int = 10,
    cost_bps: float = 10.0,
    neutral_band_pct: float = 2.0,
    cooldown_days: int = 10,
) -> List[Dict[str, Any]]:
    """Simulate strictly causal deterministic long setups on historical daily closes.

    Signal evaluated at day ``t`` using data ``<= t``, executed at ``t+1`` close,
    closed at ``t + 1 + horizon_days`` close net of ``cost_bps`` (one-way * 2 = round-trip).
    """
    if closes is None or closes.empty or benchmark_col not in closes.columns:
        return []
    frame = closes.sort_index()
    bench = pd.to_numeric(frame[benchmark_col], errors="coerce").dropna()
    bench_sma200 = bench.rolling(200, min_periods=200).mean()
    bench_ret63 = bench.pct_change(63)

    excluded = set(exclude_cols) | {benchmark_col}
    symbols = [c for c in frame.columns if c not in excluded]
    trades: List[Dict[str, Any]] = []
    round_trip_cost = (2.0 * float(cost_bps)) / 10000.0

    for sym in symbols:
        px = pd.to_numeric(frame[sym], errors="coerce").dropna()
        if len(px) < 220 + horizon_days:
            continue
        ma5 = px.rolling(5, min_periods=5).mean()
        ma10 = px.rolling(10, min_periods=10).mean()
        ma20 = px.rolling(20, min_periods=20).mean()
        ma50 = px.rolling(50, min_periods=50).mean()
        ma200 = px.rolling(200, min_periods=200).mean()
        rsi14 = _rsi(px, 14)
        ret63 = px.pct_change(63)

        b_aligned = bench.reindex(px.index)
        b_sma200 = bench_sma200.reindex(px.index)
        b_r63 = bench_ret63.reindex(px.index)

        last_entry_idx = -cooldown_days - 1
        max_t = len(px) - horizon_days - 2
        for pos in range(200, max_t + 1):
            if pos - last_entry_idx < cooldown_days:
                continue
            c_t = float(px.iloc[pos])
            if not (
                pd.notna(ma5.iloc[pos])
                and pd.notna(ma10.iloc[pos])
                and pd.notna(ma20.iloc[pos])
                and pd.notna(ma50.iloc[pos])
                and pd.notna(ma200.iloc[pos])
                and pd.notna(rsi14.iloc[pos])
                and pd.notna(ret63.iloc[pos])
                and pd.notna(b_sma200.iloc[pos])
                and pd.notna(b_aligned.iloc[pos])
                and pd.notna(b_r63.iloc[pos])
            ):
                continue

            # Pre-registered deterministic trend + anti-chasing + regime + relative-strength filter
            uptrend = (
                c_t > float(ma5.iloc[pos]) > float(ma10.iloc[pos]) > float(ma20.iloc[pos])
                and float(ma50.iloc[pos]) > float(ma200.iloc[pos])
            )
            bias_ma5_pct = ((c_t - float(ma5.iloc[pos])) / float(ma5.iloc[pos])) * 100.0
            no_chasing = 0.0 <= bias_ma5_pct <= 5.0
            rsi_ok = 45.0 <= float(rsi14.iloc[pos]) <= 70.0
            regime_ok = float(b_aligned.iloc[pos]) > float(b_sma200.iloc[pos])
            rel_strength_ok = float(ret63.iloc[pos]) > float(b_r63.iloc[pos])

            if not (uptrend and no_chasing and rsi_ok and regime_ok and rel_strength_ok):
                continue

            entry_idx = pos + 1
            exit_idx = entry_idx + horizon_days
            entry_px = float(px.iloc[entry_idx])
            exit_px = float(px.iloc[exit_idx])
            b_entry = float(b_aligned.iloc[entry_idx])
            b_exit = float(b_aligned.iloc[exit_idx])
            if entry_px <= 0 or b_entry <= 0:
                continue

            gross_ret_pct = ((exit_px / entry_px) - 1.0) * 100.0
            net_ret_pct = (((exit_px / entry_px) - 1.0) - round_trip_cost) * 100.0
            bench_ret_pct = ((b_exit / b_entry) - 1.0) * 100.0

            if net_ret_pct > float(neutral_band_pct):
                outcome = "hit"
            elif net_ret_pct < -float(neutral_band_pct):
                outcome = "miss"
            else:
                outcome = "neutral"

            trades.append({
                "symbol": sym,
                "signal_date": px.index[pos].strftime("%Y-%m-%d"),
                "entry_date": px.index[entry_idx].strftime("%Y-%m-%d"),
                "exit_date": px.index[exit_idx].strftime("%Y-%m-%d"),
                "gross_return_pct": round(gross_ret_pct, 3),
                "net_return_pct": round(net_ret_pct, 3),
                "benchmark_return_pct": round(bench_ret_pct, 3),
                "excess_return_pct": round(net_ret_pct - bench_ret_pct, 3),
                "beat_benchmark": bool(net_ret_pct > bench_ret_pct),
                "outcome": outcome,
            })
            last_entry_idx = pos

    trades.sort(key=lambda t: (t["signal_date"], t["symbol"]))
    return trades


def summarize_walkforward_trades(
    trades: Sequence[Dict[str, Any]],
    *,
    gate: SignalAcceptanceGate = SignalAcceptanceGate(),
    position_weight: float = 0.15,
) -> Dict[str, Any]:
    """Compute precision, benchmark beat rate, net profit factor, max drawdown, and verdict."""
    total = len(trades)
    hits = [t for t in trades if t.get("outcome") == "hit"]
    misses = [t for t in trades if t.get("outcome") == "miss"]
    neutral = [t for t in trades if t.get("outcome") == "neutral"]
    dir_total = len(hits) + len(misses)
    precision_pct = round(len(hits) / dir_total * 100.0, 2) if dir_total > 0 else None
    precision_ci90 = _bootstrap_ci90(
        [1.0 if t.get("outcome") == "hit" else 0.0 for t in [*hits, *misses]],
        min_sample=gate.min_samples,
    )

    beat_flags = [1.0 if t.get("beat_benchmark") else 0.0 for t in trades]
    beat_rate_pct = round(sum(beat_flags) / total * 100.0, 2) if total > 0 else None
    beat_ci90 = _bootstrap_ci90(beat_flags, min_sample=gate.min_samples)

    gains = sum(max(0.0, float(t.get("net_return_pct") or 0.0)) for t in trades)
    losses = sum(abs(min(0.0, float(t.get("net_return_pct") or 0.0))) for t in trades)
    if losses > 0:
        pf_net = round(gains / losses, 2)
    elif gains > 0:
        pf_net = round(gains, 2)
    else:
        pf_net = None

    # Sequential simulated portfolio equity curve (fractional allocation per trade)
    equity = 1.0
    peak = 1.0
    max_dd_pct = 0.0
    for t in trades:
        equity *= max(0.0, 1.0 + position_weight * (float(t.get("net_return_pct") or 0.0) / 100.0))
        peak = max(peak, equity)
        dd = ((equity / peak) - 1.0) * 100.0
        max_dd_pct = min(max_dd_pct, dd)
    max_dd_pct = round(max_dd_pct, 2)

    failed_checks: List[str] = []
    if dir_total < gate.min_samples:
        verdict = "INSUFFICIENT_SAMPLE"
        failed_checks.append(f"directional_sample {dir_total} < {gate.min_samples}")
    else:
        if precision_pct is None or precision_pct < gate.min_precision_pct:
            failed_checks.append(f"precision_10d {precision_pct}% < {gate.min_precision_pct}%")
        if not precision_ci90 or precision_ci90[0] <= gate.min_precision_ci90_low_pct:
            failed_checks.append(
                f"precision_ci90_low {precision_ci90[0] if precision_ci90 else None}% <= {gate.min_precision_ci90_low_pct}%"
            )
        if not beat_ci90 or beat_ci90[0] <= gate.min_benchmark_beat_ci90_low_pct:
            failed_checks.append(
                f"benchmark_beat_ci90_low {beat_ci90[0] if beat_ci90 else None}% <= {gate.min_benchmark_beat_ci90_low_pct}%"
            )
        if pf_net is None or pf_net < gate.min_profit_factor_net:
            failed_checks.append(f"profit_factor_net {pf_net} < {gate.min_profit_factor_net}")
        if max_dd_pct < gate.max_drawdown_pct:
            failed_checks.append(f"max_drawdown {max_dd_pct}% < {gate.max_drawdown_pct}%")
        verdict = "PROVEN" if not failed_checks else "UNPROVEN"

    avg_net = round(sum(float(t.get("net_return_pct") or 0.0) for t in trades) / total, 2) if total else None
    avg_excess = round(sum(float(t.get("excess_return_pct") or 0.0) for t in trades) / total, 2) if total else None
    return {
        "total_signals": total,
        "directional_samples": dir_total,
        "hits": len(hits),
        "misses": len(misses),
        "neutral": len(neutral),
        "precision_10d_pct": precision_pct,
        "precision_ci90_pct": precision_ci90,
        "benchmark_beat_rate_10d_pct": beat_rate_pct,
        "benchmark_beat_ci90_pct": beat_ci90,
        "avg_net_return_pct": avg_net,
        "avg_excess_return_pct": avg_excess,
        "profit_factor_net": pf_net,
        "max_drawdown_pct": max_dd_pct,
        "verdict": verdict,
        "failed_checks": failed_checks,
    }


def _split_six_month_slices(trades: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for t in trades:
        d = str(t.get("signal_date") or "")
        if len(d) < 7:
            continue
        year = d[:4]
        month = int(d[5:7])
        half = "H1" if month <= 6 else "H2"
        key = f"{year}-{half}"
        buckets.setdefault(key, []).append(dict(t))
    out: List[Dict[str, Any]] = []
    for key in sorted(buckets.keys()):
        summary = summarize_walkforward_trades(buckets[key])
        out.append({"window": key, **summary})
    return out


def run_signal_walkforward(
    *,
    prices: Optional[pd.DataFrame] = None,
    benchmark_col: str = "SPY",
    is_end_date: str = "2021-12-31",
    oos_start_date: str = "2022-01-01",
    cost_bps: float = 10.0,
    gate: SignalAcceptanceGate = SignalAcceptanceGate(),
    save_outputs: bool = True,
    json_path: Optional[Path] = None,
    report_path: Optional[Path] = None,
    write_report: bool = True,
) -> Dict[str, Any]:
    """Run causal walk-forward validation (2018-2021 IS + 2022+ OOS 6-month slices)."""
    frame = prices
    if frame is None:
        frame = load_universe_closes("us_etf", US_ETF_UNIVERSE, start_date="2017-01-01")
    if frame is None or frame.empty or benchmark_col not in frame.columns:
        raise RuntimeError(f"Walk-forward fiyat verisi ({benchmark_col}) yüklenemedi.")

    all_trades = generate_causal_signal_trades(
        frame,
        benchmark_col=benchmark_col,
        cost_bps=cost_bps,
    )
    in_sample = [t for t in all_trades if "2018-01-01" <= t["signal_date"] <= is_end_date]
    oos = [t for t in all_trades if t["signal_date"] >= oos_start_date]

    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "benchmark": benchmark_col,
        "cost_bps_one_way": float(cost_bps),
        "acceptance_gate": asdict(gate),
        "in_sample": summarize_walkforward_trades(in_sample, gate=gate),
        "out_of_sample": summarize_walkforward_trades(oos, gate=gate),
        "walkforward_6m_windows": _split_six_month_slices(oos),
    }

    if save_outputs:
        target = Path(json_path or DEFAULT_SIGNAL_WALKFORWARD_JSON)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".sig_wf_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, target)
        if write_report:
            md = Path(report_path or DEFAULT_SIGNAL_WALKFORWARD_REPORT)
            md.parent.mkdir(parents=True, exist_ok=True)
            md.write_text(format_signal_walkforward_markdown(payload), encoding="utf-8")
    return payload


def format_signal_walkforward_markdown(payload: Dict[str, Any]) -> str:
    oos = payload.get("out_of_sample") or {}
    ins = payload.get("in_sample") or {}
    lines = [
        "# Hisse Sinyali Walk-Forward ve %80 Kabul Kapısı Doğrulama Raporu",
        "",
        f"> **Oluşturulma:** {payload.get('generated_at')} · **Kıyas Endeksi:** `{payload.get('benchmark')}` · "
        f"**Tek Yön Maliyet:** {payload.get('cost_bps_one_way')} bps",
        "",
        f"## Örneklem Dışı (OOS 2022+) Kararı: `{oos.get('verdict')}`",
        "",
    ]
    for check in oos.get("failed_checks") or []:
        lines.append(f"- ❌ Başarısız kriter: `{check}`")
    lines.extend([
        "",
        "| Dönem | Sinyal | Yönlü (N) | Precision (10g ±%2) | Endeks Geçme (10g) | Net Profit Factor | MaxDD | Karar |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
        f"| In-Sample (2018–2021) | {ins.get('total_signals')} | {ins.get('directional_samples')} | "
        f"{ins.get('precision_10d_pct')}% | {ins.get('benchmark_beat_rate_10d_pct')}% | "
        f"{ins.get('profit_factor_net')} | {ins.get('max_drawdown_pct')}% | `{ins.get('verdict')}` |",
        f"| Out-of-Sample (2022+) | {oos.get('total_signals')} | {oos.get('directional_samples')} | "
        f"{oos.get('precision_10d_pct')}% | {oos.get('benchmark_beat_rate_10d_pct')}% | "
        f"{oos.get('profit_factor_net')} | {oos.get('max_drawdown_pct')}% | `{oos.get('verdict')}` |",
        "",
        "### 6 Aylık Walk-Forward Dilimleri (OOS)",
        "",
        "| Pencere | Sinyal | Precision (10g) | Endeks Geçme | Net PF | MaxDD |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for w in payload.get("walkforward_6m_windows") or []:
        lines.append(
            f"| {w['window']} | {w['total_signals']} | {w.get('precision_10d_pct')}% | "
            f"{w.get('benchmark_beat_rate_10d_pct')}% | {w.get('profit_factor_net')} | {w.get('max_drawdown_pct')}% |"
        )
    return "\n".join(lines) + "\n"
