#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run Strategy Research v5: does correlation-aware (Min-Corr) sizing beat naive 1/vol?"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.quant.research_v5_lab import (  # noqa: E402
    DEFAULT_RESEARCH_V5_JSON,
    DEFAULT_RESEARCH_V5_REPORT,
    run_strategy_research_v5,
)

DEFAULT_LOCAL_RESEARCH_V5_REPORT = Path("data") / "reports" / "STRATEGY_RESEARCH_V5_REPORT.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Strateji Araştırması v5 — Min-Corr vs 1/vol kontrol testi")
    parser.add_argument("--refresh", action="store_true", help="Fiyat önbelleğini yeniden indir")
    parser.add_argument("--skip-plateau", action="store_true", help="±%20 komşuluk testini atla")
    parser.add_argument("--output-json", type=str, default=str(DEFAULT_RESEARCH_V5_JSON))
    parser.add_argument(
        "--output-md",
        type=str,
        default=None,
        help="Markdown rapor yolu (varsayılan: data/reports/STRATEGY_RESEARCH_V5_REPORT.md; --publish ile docs/)",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Raporu git tarafından izlenen docs/STRATEGY_RESEARCH_V5_REPORT.md dosyasına da yaz",
    )
    args = parser.parse_args()

    md_target = (
        Path(args.output_md)
        if args.output_md
        else (DEFAULT_RESEARCH_V5_REPORT if args.publish else DEFAULT_LOCAL_RESEARCH_V5_REPORT)
    )

    payload = run_strategy_research_v5(
        force_refresh=args.refresh,
        run_plateau=not args.skip_plateau,
        json_path=Path(args.output_json),
        report_path=md_target,
    )
    cmp_ = payload["mincorr_vs_control"]
    ls, ctrl = cmp_["mincorr"], cmp_["invvol_control"]
    print(f"=== Strateji Araştırması v5 ({payload['data_start']} -> {payload['data_end']}) ===")
    print(
        f"Min-Corr:  {ls['verdict']} | CAGR {ls['cagr_pct']:+.2f}% | "
        f"BIL üstü Sharpe 5/25bps {ls['excess_sharpe_5bps']:+.2f}/{ls['excess_sharpe_25bps']:+.2f} | "
        f"MaxDD {ls['max_drawdown_pct']:.2f}% | 2008 {ls['return_2008_pct']:+.1f}% | 2022 {ls['return_2022_pct']:+.1f}%"
    )
    print(
        f"Kontrol:   {ctrl['verdict']} | CAGR {ctrl['cagr_pct']:+.2f}% | "
        f"BIL üstü Sharpe 5/25bps {ctrl['excess_sharpe_5bps']:+.2f}/{ctrl['excess_sharpe_25bps']:+.2f} | "
        f"MaxDD {ctrl['max_drawdown_pct']:.2f}% | 2008 {ctrl['return_2008_pct']:+.1f}% | 2022 {ctrl['return_2022_pct']:+.1f}%"
    )
    print(f"Min-Corr değer katıyor mu? {'EVET' if cmp_['mincorr_adds_value'] else 'HAYIR'}")
    for reason in cmp_.get("reasons") or []:
        print(f"  - {reason}")
    print(f"Rapor: {md_target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
