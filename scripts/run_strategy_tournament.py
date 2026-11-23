#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run the 25-strategy multi-universe empirical tournament and write report/cache.

Usage::

    python scripts/run_strategy_tournament.py
    python scripts/run_strategy_tournament.py --refresh
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.quant.tournament import (  # noqa: E402
    TOURNAMENT_REPORT_PATH,
    format_tournament_markdown,
    run_tournament,
)

DEFAULT_LOCAL_TOURNAMENT_REPORT = Path("data") / "reports" / "STRATEGY_TOURNAMENT_REPORT.md"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass

    parser = argparse.ArgumentParser(description="Run DSA 25-strategy empirical tournament")
    parser.add_argument("--refresh", action="store_true", help="Ignore disk cache and re-download Yahoo Finance closes")
    parser.add_argument("--oos-start", default="2022-01-01", help="Out-of-sample start date (YYYY-MM-DD)")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also overwrite tracked docs/STRATEGY_TOURNAMENT_REPORT.md (default writes data/reports/)",
    )
    args = parser.parse_args()

    payload = run_tournament(
        oos_start=args.oos_start,
        force_refresh=args.refresh,
        write_report=bool(args.publish),
    )
    report_dest = TOURNAMENT_REPORT_PATH
    if not args.publish:
        report_dest = DEFAULT_LOCAL_TOURNAMENT_REPORT
        report_dest.parent.mkdir(parents=True, exist_ok=True)
        report_dest.write_text(format_tournament_markdown(payload), encoding="utf-8")

    champ = payload.get("champion") or {}
    paa = payload.get("paa") or {}
    meta_a = payload.get("meta_portfolio_a") or {}
    meta_b = payload.get("meta_portfolio_b") or {}

    print(
        f"Turnuva tamamlandı: {payload['total_strategies']} strateji · "
        f"{payload['total_assets']} varlık · {payload['total_asset_days']:,} varlık-gün "
        f"(OOS {payload['oos_start']} -> {payload['latest_date']})"
    )
    print(f"PASS_ELITE: {payload['pass_elite_count']} | PASS_SOLID: {payload['pass_solid_count']}")
    if paa:
        o = paa["oos"]
        ex_sh = o.get("excess_sharpe", o["sharpe"])
        print(f"  PAA Çöküş Kalkanı : CAGR {o['cagr_pct']:+.1f}% | BIL üstü Sharpe {ex_sh:+.2f} | MaxDD {o['max_drawdown_pct']:.1f}% | DSR %{o['dsr_pct']:.1f} | Hedef: {paa['signal_summary']}")
    if meta_a:
        o = meta_a["oos"]
        ex_sh = o.get("excess_sharpe", o["sharpe"])
        print(f"  Meta-Portföy A    : CAGR {o['cagr_pct']:+.1f}% | BIL üstü Sharpe {ex_sh:+.2f} | MaxDD {o['max_drawdown_pct']:.1f}% | DSR %{o['dsr_pct']:.1f} | Hedef: {meta_a['signal_summary']}")
    if meta_b:
        o = meta_b["oos"]
        ex_sh = o.get("excess_sharpe", o["sharpe"])
        print(f"  Meta-Portföy B    : CAGR {o['cagr_pct']:+.1f}% | BIL üstü Sharpe {ex_sh:+.2f} | MaxDD {o['max_drawdown_pct']:.1f}% | DSR %{o['dsr_pct']:.1f} | Hedef: {meta_b['signal_summary']}")
    if champ:
        o = champ["oos"]
        ex_sh = o.get("excess_sharpe", o["sharpe"])
        print(f"  Genel Şampiyon    : {champ['name']} (BIL üstü Sharpe {ex_sh:+.2f}, CAGR {o['cagr_pct']:+.1f}%, MaxDD {o['max_drawdown_pct']:.1f}%)")
    print(f"Rapor kaydedildi: {report_dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
