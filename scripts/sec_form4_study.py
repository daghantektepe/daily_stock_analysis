#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEC Form 4 Executive Insider Buying Event Study CLI.

Measures whether corporate insider purchases filed with the SEC on Form 4
produce abnormal returns (Alpha) relative to the S&P 500 benchmark (SPY).

Examples:
    # Evaluate 2026 Q1 insider purchases >= $50,000 (first 50 events)
    python scripts/sec_form4_study.py --quarters 2026q1 --min-value 50000 --limit 50

    # Evaluate multiple quarters and notify via Telegram
    python scripts/sec_form4_study.py --quarters 2025q3,2025q4 --min-value 100000 --notify
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_provider.sec_form4_fetcher import SecForm4Fetcher
from src.services.sec_form4_study import format_sec_form4_study_report, run_sec_form4_event_study


def main() -> int:
    parser = argparse.ArgumentParser(description="SEC Form 4 Insider Buying Event Study (U.S. Stocks)")
    parser.add_argument(
        "--quarters",
        default="2026q1",
        help="Comma-separated quarters to evaluate (e.g. 2026q1 or 2025q3,2025q4)",
    )
    parser.add_argument(
        "--min-value",
        type=float,
        default=50000.0,
        help="Minimum total purchase amount in USD (default: $50,000)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=60,
        help="Maximum events to evaluate per run (default: 60)",
    )
    parser.add_argument(
        "--benchmark",
        default="SPY",
        help="Benchmark symbol (default: SPY for S&P 500)",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send summary report to configured notification channels (e.g. Telegram)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger(__name__)

    fetcher = SecForm4Fetcher()
    quarters = [q.strip().lower() for q in args.quarters.split(",") if q.strip()]

    all_events = []
    for q in quarters:
        logger.info("Loading SEC Form 4 dataset for %s ...", q)
        try:
            events = fetcher.parse_quarter(q, min_value=args.min_value)
            logger.info("Found %d insider purchase events in %s", len(events), q)
            all_events.extend(events)
        except Exception as exc:
            logger.error("Failed to parse quarter %s: %s", q, exc)

    if not all_events:
        print("[Error] No insider purchase events found for specified quarters.", file=sys.stderr)
        return 1

    all_events.sort(key=lambda e: e.filing_date)
    logger.info("Running event study on %d total events (limit %d) vs %s ...", len(all_events), args.limit, args.benchmark)

    results = run_sec_form4_event_study(
        all_events,
        benchmark_symbol=args.benchmark,
        min_value=args.min_value,
        max_events=args.limit,
    )

    report_text = format_sec_form4_study_report(results)
    print("\n" + report_text + "\n")

    if args.notify:
        try:
            from src.notification import NotificationService

            notifier = NotificationService()
            if notifier.is_available():
                notifier.send(report_text, dedup_key=f"sec-form4-study:{quarters[0]}")
                print("[Info] Report delivered to notification channels.")
            else:
                print("[Warn] No notification channel configured in .env", file=sys.stderr)
        except Exception as exc:
            logger.warning("Failed to send notification: %s", exc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
