#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI runner for Strategy Research v3 (19-year 4-era anti-overfitting lab).

Usage:
    .venv\\Scripts\\python.exe scripts\\run_strategy_research_v3.py
    .venv\\Scripts\\python.exe scripts\\run_strategy_research_v3.py --refresh
    .venv\\Scripts\\python.exe scripts\\run_strategy_research_v3.py --no-plateau
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 19-year multi-era Strategy Research v3 evaluation lab.")
    parser.add_argument("--refresh", action="store_true", help="Force refresh 2007-present Yahoo Finance caches")
    parser.add_argument("--no-plateau", action="store_true", help="Skip ±20% parameter plateau grid (faster)")
    parser.add_argument(
        "--enroll-winner",
        action="store_true",
        help="Enroll & freeze standout promoted v3 winner (v3_trp) as an independent ForwardRegistry paper book",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    from src.quant.research_lab import DEFAULT_RESEARCH_V3_REPORT, run_strategy_research_v3

    payload = run_strategy_research_v3(
        force_refresh=bool(args.refresh),
        run_plateau=not bool(args.no_plateau),
        save_outputs=True,
    )

    print("\n=== Strateji Araştırması v3 (2008–2026 · 4 Makro Rejim · 5 Kapı) ===")
    print(f"Terfi Edenler : {payload['promoted_ids'] or 'YOK (hiçbiri 5/5 kapıyı geçmedi)'}")
    print(f"Reddedilenler : {payload['rejected_ids'] or 'YOK'}")
    for c in payload.get("candidates") or []:
        fm = c.get("full_2008_plus") or {}
        m25 = (c.get("cost_stress") or {}).get("25bps") or {}
        print(
            f"\n[{c['verdict']}] {c['strategy_id']} ({c['gates_passed']}/{c['gates_total']} kapı) | "
            f"2008+ CAGR {fm.get('cagr_pct', 0):+.2f}% | ExBIL {fm.get('excess_cagr_pct', 0):+.2f}% | "
            f"ExSh(5bps) {fm.get('excess_sharpe', 0):+.2f} | ExSh(25bps) {m25.get('excess_sharpe', 0):+.2f} | "
            f"MaxDD {fm.get('max_drawdown_pct', 0):.1f}%"
        )
        for gname, gval in (c.get("gates") or {}).items():
            mark = "✓" if gval.get("passed") else "✗"
            print(f"  {mark} {gname}: {gval.get('detail')}")
    print(f"\nRapor kaydedildi: {DEFAULT_RESEARCH_V3_REPORT}")

    if args.enroll_winner and "V3_TREND_RISK_PARITY_BIL" in (payload.get("promoted_ids") or []):
        from src.quant.paper_book import step_quant_paper_books

        print("\n=== Bağımsız İleri Doğrulama Dondurma: v3_trp (V3_TREND_RISK_PARITY_BIL) ===")
        step_res = step_quant_paper_books(strategies=["v3_trp"])
        if step_res.get("report_text"):
            print(step_res["report_text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
