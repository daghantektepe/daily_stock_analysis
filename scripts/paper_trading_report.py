#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print (and optionally send) the paper trading summary with benchmarks.

    python scripts/paper_trading_report.py            # console
    python scripts/paper_trading_report.py --notify   # also send to configured channels

Borsa Istanbul trades are compared with BIST 100 (same cash flows, same days)
and converted to USD at each day's USD/TRY rate. Read-only: never trades.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper trading summary with BIST 100 / USD benchmarks and signal hit rates")
    parser.add_argument("--notify", action="store_true", help="send the summary to configured notification channels")
    parser.add_argument("--no-benchmark", action="store_true", help="skip index / USD comparison (no network)")
    parser.add_argument("--no-outcomes", action="store_true", help="skip DecisionSignal outcome evaluation and stats")
    parser.add_argument("--market", default=None, help="optional market filter for signal outcomes (e.g. tr)")
    parser.add_argument(
        "--weekly-if-due",
        action="store_true",
        help="only send when it is Friday after market close in Istanbul and not yet sent this ISO week",
    )
    args = parser.parse_args()

    from src.services.paper_trading_benchmark import (
        evaluate_signal_outcomes,
        format_paper_trading_report,
        maybe_send_weekly_performance_report,
    )
    from src.services.paper_trading_service import PaperTradingService

    if args.weekly_if_due:
        maybe_send_weekly_performance_report(market=args.market)
        return 0

    outcomes = {} if args.no_outcomes else evaluate_signal_outcomes(market=args.market)
    summary = PaperTradingService().get_summary(include_benchmarks=not args.no_benchmark)
    text = format_paper_trading_report(summary, outcome_stats=outcomes)
    print(text)
    if args.notify:
        from src.notification import NotificationService

        if not NotificationService().send(text):
            print("[Warn] no notification channel accepted the message", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
