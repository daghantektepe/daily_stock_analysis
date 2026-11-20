# -*- coding: utf-8 -*-
"""Multi-universe 25-strategy empirical tournament runner, reporter, and cache."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.quant.data_loader import (
    DEFAULT_CACHE_DIR,
    US_ETF_RISK_ASSETS,
    US_ETF_SAFE_ASSETS,
    US_ETF_UNIVERSE,
    load_all_tournament_universes,
    load_universe_closes,
)
from src.quant.portfolio import build_meta_portfolios, save_champion_paper_snapshot
from src.quant.stats import (
    classify_strategy_verdict,
    compute_cross_sectional_sr_variance,
    deflated_sharpe_ratio,
)
from src.quant.strategies.engine import DEFAULT_OOS_START, StrategyResult
from src.quant.strategies.library import compute_paa_weights, run_all_base_strategies

logger = logging.getLogger(__name__)

TOURNAMENT_CACHE_FILE = DEFAULT_CACHE_DIR / "tournament_latest.json"
TOURNAMENT_REPORT_PATH = Path("docs") / "STRATEGY_TOURNAMENT_REPORT.md"


def _verdict_rank(verdict: str) -> int:
    order = {
        "PASS_ELITE": 0,
        "PASS_SOLID": 1,
        "BENCHMARK": 2,
        "CAVEAT_SURVIVORSHIP": 3,
        "FAIL_WEAK": 4,
    }
    return order.get(verdict, 5)


def format_tournament_markdown(payload: Dict[str, Any]) -> str:
    """Render the 25-strategy tournament summary to GitHub-flavored Markdown."""
    strategies = payload.get("strategies") or []
    champion = payload.get("champion") or {}
    meta_a = payload.get("meta_portfolio_a") or {}
    meta_b = payload.get("meta_portfolio_b") or {}

    lines = [
        "# Çoklu Evren Ampirik Strateji Turnuvası Raporu",
        "",
        f"- **Oluşturulma:** `{payload.get('generated_at')}`",
        f"- **Örneklem Dışı (OOS) Dönem:** `{payload.get('oos_start')} → {payload.get('latest_date')}`",
        f"- **Toplam Strateji (N):** `{payload.get('total_strategies')}` · **Toplam Varlık:** `{payload.get('total_assets')}` · **Varlık-Gün Gözlem:** `{payload.get('total_asset_days'):,}`",
        "- **Metodoloji:** Sıfır lookahead (`T` kapanış → `T+1` işlem), çift yönlü işlem maliyeti düşülmüş net getiri, Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR).",
        "",
        "## Canlı Şampiyon & Meta-Portföy Dağılımları",
        "",
    ]
    if champion:
        lines.append(
            f"- **Şampiyon (`{champion.get('strategy_id')}`):** {champion.get('signal_summary')} "
            f"(OOS CAGR `{champion.get('oos', {}).get('cagr_pct')}%`, Sharpe `{champion.get('oos', {}).get('sharpe')}`, "
            f"MaxDD `{champion.get('oos', {}).get('max_drawdown_pct')}%`, DSR `%{champion.get('oos', {}).get('dsr_pct')}`)"
        )
    if meta_a:
        lines.append(
            f"- **Meta-Portföy A (`{meta_a.get('strategy_id')}`):** {meta_a.get('signal_summary')} "
            f"(OOS CAGR `{meta_a.get('oos', {}).get('cagr_pct')}%`, Sharpe `{meta_a.get('oos', {}).get('sharpe')}`, "
            f"MaxDD `{meta_a.get('oos', {}).get('max_drawdown_pct')}%`)"
        )
    if meta_b:
        lines.append(
            f"- **Meta-Portföy B (`{meta_b.get('strategy_id')}`):** {meta_b.get('signal_summary')} "
            f"(OOS CAGR `{meta_b.get('oos', {}).get('cagr_pct')}%`, Sharpe `{meta_b.get('oos', {}).get('sharpe')}`, "
            f"MaxDD `{meta_b.get('oos', {}).get('max_drawdown_pct')}%`)"
        )

    lines.extend(
        [
            "",
            "## Turnuva Liderlik Tablosu (OOS Net)",
            "",
            "| Strateji | Evren | Karar | OOS CAGR | OOS Sharpe | OOS MaxDD | Recovery | DSR (`N=25`) | Güncel Hedef |",
            "| :--- | :---: | :---: | ---: | ---: | ---: | ---: | ---: | :--- |",
        ]
    )
    for row in strategies:
        oos = row.get("oos") or {}
        lines.append(
            f"| **{row.get('name')}** | `{row.get('universe')}` | `{row.get('verdict')}` | "
            f"{oos.get('cagr_pct', 0):+.1f}% | {oos.get('sharpe', 0):.2f} | "
            f"{oos.get('max_drawdown_pct', 0):.1f}% | {oos.get('recovery_factor', 0):.2f}x | "
            f"%{oos.get('dsr_pct', 0):.1f} | {row.get('signal_summary', '')} |"
        )
    lines.append("")
    lines.append("> *Not: Tüm sonuçlar geriye dönük ampirik simülasyondur; BIST stratejileri hayatta kalma yanlılığı ve TL enflasyonu nedeniyle `CAVEAT_SURVIVORSHIP` etiketi taşır. Yatırım tavsiyesi değildir.*")
    return "\n".join(lines) + "\n"


def run_tournament(
    *,
    oos_start: str = DEFAULT_OOS_START,
    start_date: str = "2016-01-01",
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
    write_report: bool = True,
    update_paper_snapshot: bool = True,
) -> Dict[str, Any]:
    """Run the full 25-strategy multi-universe empirical tournament and cache results."""
    target_cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
    universes = load_all_tournament_universes(
        start_date=start_date,
        cache_dir=target_cache_dir,
        force_refresh=force_refresh,
    )
    base_results = run_all_base_strategies(universes, oos_start=oos_start, n_trials=25)
    meta_results = build_meta_portfolios(base_results, oos_start=oos_start, n_trials=25)

    all_map: Dict[str, StrategyResult] = {**base_results, **meta_results}
    n_trials = len(all_map)

    # Recompute cross-sectional DSR across all N tournament trials on OOS returns
    oos_series_list = [res.oos_returns for res in all_map.values() if res.oos_returns is not None and not res.oos_returns.empty]
    sr_var = compute_cross_sectional_sr_variance(oos_series_list)

    for res in all_map.values():
        if res.oos_returns is not None and not res.oos_returns.empty:
            res.oos.dsr_pct = deflated_sharpe_ratio(
                res.oos_returns,
                n_trials=n_trials,
                sr_variance=sr_var,
            )
        if res.daily_returns is not None and not res.daily_returns.empty:
            res.full.dsr_pct = deflated_sharpe_ratio(
                res.daily_returns,
                n_trials=n_trials,
                sr_variance=sr_var,
            )
        res.verdict = classify_strategy_verdict(
            res.oos,
            universe=res.universe,
            is_benchmark=res.is_benchmark,
        )

    ordered = sorted(
        all_map.values(),
        key=lambda r: (_verdict_rank(r.verdict), -float(r.oos.sharpe), -float(r.oos.cagr_pct)),
    )

    # Select champion among non-benchmark USD/meta elite strategies (preferring PAA / highest OOS Sharpe)
    elite_usd = [
        r for r in ordered
        if not r.is_benchmark and r.universe in {"us_etf", "us_sectors", "meta"} and r.verdict in {"PASS_ELITE", "PASS_SOLID"}
    ]
    champion = elite_usd[0] if elite_usd else ordered[0]
    meta_a = all_map.get("META_US_ETF_ALL_WEATHER")
    meta_b = all_map.get("META_GLOBAL_ETF_CRYPTO_TREND")
    paa = all_map.get("PROTECTIVE_ASSET_ALLOCATION_PAA")

    # Compute universe observation totals
    unique_assets = set()
    total_asset_days = 0
    latest_dates: List[str] = []
    for frame in universes.values():
        if frame is not None and not frame.empty:
            unique_assets.update(str(c) for c in frame.columns)
            total_asset_days += int(frame.notna().sum().sum())
            ts = frame.index[-1]
            latest_dates.append(ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts))

    # Build key featured curves for Recharts comparison chart
    featured_ids = [
        "PROTECTIVE_ASSET_ALLOCATION_PAA",
        "META_US_ETF_ALL_WEATHER",
        "META_GLOBAL_ETF_CRYPTO_TREND",
        "CRYPTO_5SMA_ENSEMBLE",
        "BENCHMARK_SPY_BUY_HOLD",
        "BENCHMARK_60_40",
        "BENCHMARK_CRYPTO_BUY_HOLD",
    ]
    if champion.strategy_id not in featured_ids:
        featured_ids.insert(0, champion.strategy_id)

    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "oos_start": oos_start,
        "latest_date": max(latest_dates) if latest_dates else None,
        "total_strategies": n_trials,
        "total_assets": len(unique_assets),
        "total_asset_days": total_asset_days,
        "pass_elite_count": sum(1 for r in ordered if r.verdict == "PASS_ELITE"),
        "pass_solid_count": sum(1 for r in ordered if r.verdict == "PASS_SOLID"),
        "champion": champion.to_public_dict(include_curve=False),
        "paa": paa.to_public_dict(include_curve=False) if paa else None,
        "meta_portfolio_a": meta_a.to_public_dict(include_curve=False) if meta_a else None,
        "meta_portfolio_b": meta_b.to_public_dict(include_curve=False) if meta_b else None,
        "featured_strategy_ids": [sid for sid in featured_ids if sid in all_map],
        "strategies": [r.to_public_dict(include_curve=(r.strategy_id in featured_ids)) for r in ordered],
    }

    if update_paper_snapshot:
        try:
            payload["paper_snapshot"] = save_champion_paper_snapshot(
                paa or champion,
                meta_a=meta_a,
                meta_b=meta_b,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[quant] failed to save champion paper snapshot: %s", exc)

    target_cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = target_cache_dir / "tournament_latest.json"
    try:
        cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("[quant] failed to write tournament cache: %s", exc)

    if write_report:
        try:
            TOURNAMENT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOURNAMENT_REPORT_PATH.write_text(format_tournament_markdown(payload), encoding="utf-8")
        except OSError as exc:
            logger.warning("[quant] failed to write tournament report: %s", exc)

    return payload


def load_latest_tournament_results(
    *,
    cache_dir: Optional[Path] = None,
    auto_run_if_missing: bool = False,
) -> Optional[Dict[str, Any]]:
    """Load the cached tournament JSON from disk, optionally running it if missing."""
    target = Path(cache_dir or DEFAULT_CACHE_DIR) / "tournament_latest.json"
    if target.is_file():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("strategies"):
                return data
        except (OSError, ValueError) as exc:
            logger.warning("[quant] corrupt tournament cache %s: %s", target, exc)
    if auto_run_if_missing:
        return run_tournament(cache_dir=cache_dir)
    return None


def get_live_paa_signal(
    *,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Compute the live Protective Asset Allocation (PAA) crash-shield target weights right now."""
    closes = load_universe_closes(
        "us_etf_and_sectors",
        US_ETF_UNIVERSE,
        start_date="2023-01-01",
        cache_dir=cache_dir,
        force_refresh=force_refresh,
    )
    if closes.empty or len(closes) < 252:
        return {"ok": False, "error": "Insufficient ETF price history for PAA (need >= 252 trading days)."}

    risk_cols = [c for c in US_ETF_RISK_ASSETS if c in closes.columns]
    safe_cols = [c for c in ("IEF", "SHY") if c in closes.columns]
    weights = compute_paa_weights(closes, risk_assets=risk_cols, safe_assets=safe_cols)

    sma252 = closes[risk_cols].rolling(252, min_periods=252).mean()
    last_close = closes.iloc[-1]
    last_sma = sma252.iloc[-1]
    asset_status = []
    bad_count = 0
    for sym in risk_cols:
        px = float(last_close[sym])
        s = float(last_sma[sym])
        mom_pct = ((px / s) - 1.0) * 100.0 if s > 0 else 0.0
        above = px > s
        if not above:
            bad_count += 1
        asset_status.append(
            {
                "symbol": sym,
                "close": round(px, 2),
                "sma252": round(s, 2),
                "mom_vs_sma252_pct": round(mom_pct, 2),
                "above_sma252": above,
            }
        )
    asset_status.sort(key=lambda x: x["mom_vs_sma252_pct"], reverse=True)

    last_w = weights.iloc[-1]
    target_weights = {str(col): round(float(val) * 100.0, 1) for col, val in last_w.items() if float(val) > 0.001}
    crash_protection_pct = round(min(100.0, (2.0 * bad_count / max(1, len(risk_cols))) * 100.0), 1)
    as_of = closes.index[-1].strftime("%Y-%m-%d") if hasattr(closes.index[-1], "strftime") else str(closes.index[-1])

    return {
        "as_of_date": as_of,
        "risk_assets_total": len(risk_cols),
        "risk_assets_below_sma252": bad_count,
        "crash_protection_pct": crash_protection_pct,
        "regime_label": (
            "FULL_CRASH_SHIELD" if crash_protection_pct >= 99.0 else ("PARTIAL_DEFENSIVE" if crash_protection_pct >= 50.0 else "RISK_ON")
        ),
        "target_weights_pct": target_weights,
        "risk_asset_breadth": asset_status,
    }
