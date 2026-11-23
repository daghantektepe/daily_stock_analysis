#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Strategy Research v4: does an inverse-ETF (no-margin) short sleeve add value?

Usage (Windows: .venv\\Scripts\\python.exe instead of python):
    python scripts/run_strategy_research_v4.py
    python scripts/run_strategy_research_v4.py --refresh
    python scripts/run_strategy_research_v4.py --no-plateau

Research only: nothing is enrolled into the paper books or sent to a broker.
Writes data/quant_cache/research_v4_latest.json and docs/STRATEGY_RESEARCH_V4_REPORT.md.
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
    parser = argparse.ArgumentParser(description="Strategy Research v4: long/short (inverse ETF) vs long-only control")
    parser.add_argument("--refresh", action="store_true", help="re-download 2007+ prices")
    parser.add_argument("--no-plateau", action="store_true", help="skip the ±20%% parameter plateau grid")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

    from src.quant.research_v4_lab import DEFAULT_RESEARCH_V4_REPORT, run_strategy_research_v4

    payload = run_strategy_research_v4(force_refresh=bool(args.refresh), run_plateau=not bool(args.no_plateau))
    cmp_ = payload["short_vs_control"]
    ls, ctrl = cmp_["long_short"], cmp_["long_only_control"]
    print("=== Strateji Araştırması v4: Short (ters ETF) değer katıyor mu? ===")
    print(f"Sonuç: {'EVET' if cmp_['short_adds_value'] else 'HAYIR (kanıt yetersiz)'}")
    for reason in cmp_["reasons"]:
        print(f"  - {reason}")
    print(
        f"Long/Short : BIL üstü Sharpe {ls['excess_sharpe_5bps']:+.2f} (25 bps {ls['excess_sharpe_25bps']:+.2f}) "
        f"| 2008 {ls['return_2008_pct']:+.1f}% | 2022 {ls['return_2022_pct']:+.1f}%"
    )
    print(
        f"Long-Only  : BIL üstü Sharpe {ctrl['excess_sharpe_5bps']:+.2f} (25 bps {ctrl['excess_sharpe_25bps']:+.2f}) "
        f"| 2008 {ctrl['return_2008_pct']:+.1f}% | 2022 {ctrl['return_2022_pct']:+.1f}%"
    )
    print(f"Rapor: {DEFAULT_RESEARCH_V4_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
