#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run strictly causal walk-forward validation for the 80% signal precision gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.quant.signal_walkforward import (  # noqa: E402
    DEFAULT_SIGNAL_WALKFORWARD_JSON,
    DEFAULT_SIGNAL_WALKFORWARD_REPORT,
    run_signal_walkforward,
)

DEFAULT_LOCAL_SIGNAL_WALKFORWARD_REPORT = Path("data") / "reports" / "SIGNAL_WALKFORWARD_REPORT.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Hisse Sinyali Walk-Forward (OOS) ve %80 Kabul Kapısı Doğrulaması")
    parser.add_argument("--cost-bps", type=float, default=10.0, help="Tek yön komisyon+kayma (bps, varsayılan 10)")
    parser.add_argument("--output-json", type=str, default=str(DEFAULT_SIGNAL_WALKFORWARD_JSON))
    parser.add_argument(
        "--output-md",
        type=str,
        default=None,
        help="Markdown rapor yolu (varsayılan: data/reports/SIGNAL_WALKFORWARD_REPORT.md; --publish ile docs/)",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Raporu git tarafından izlenen docs/SIGNAL_WALKFORWARD_REPORT.md dosyasına da yaz",
    )
    args = parser.parse_args()

    md_target = (
        Path(args.output_md)
        if args.output_md
        else (DEFAULT_SIGNAL_WALKFORWARD_REPORT if args.publish else DEFAULT_LOCAL_SIGNAL_WALKFORWARD_REPORT)
    )
    payload = run_signal_walkforward(
        cost_bps=args.cost_bps,
        json_path=Path(args.output_json),
        report_path=md_target,
    )
    oos = payload["out_of_sample"]
    print(f"=== Sinyal Walk-Forward (OOS 2022+, {payload['benchmark']}, {args.cost_bps:.0f} bps) ===")
    print(
        f"Karar: {oos['verdict']} | Sinyal: {oos['total_signals']} (yönlü N={oos['directional_samples']}) | "
        f"Precision: {oos['precision_10d_pct']}% | Endeks geçme: {oos['benchmark_beat_rate_10d_pct']}% | "
        f"Net PF: {oos['profit_factor_net']} | MaxDD: {oos['max_drawdown_pct']}%"
    )
    for chk in oos.get("failed_checks") or []:
        print(f"  - Başarısız kriter: {chk}")
    print(f"Rapor: {md_target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
