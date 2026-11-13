#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""U.S. Corporate Insider Buying Daily Screener CLI (SEC Form 4).

Screens recent U.S. executive insider buying (cluster purchases, C-suite conviction,
opportunistic non-10b5-1 programs) and ranks top candidates for deep analysis.

Examples:
    # Screen top 8 insider buying stocks from latest available quarterly dataset
    python scripts/sec_form4_screener.py --top 8

    # Filter for larger purchases ($100k+) on a specific quarter and notify via Telegram
    python scripts/sec_form4_screener.py --quarter 2026q1 --min-value 100000 --notify
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load local environment (e.g. SEC_EDGAR_USER_AGENT)
load_dotenv(REPO_ROOT / ".env")

from data_provider.sec_form4_fetcher import SecForm4Fetcher
from src.services.sec_form4_screener import format_sec_screener_report, screen_us_insider_stocks


def main() -> int:
    parser = argparse.ArgumentParser(description="SEC Form 4 Executive Insider Buying Screener (U.S. Stocks)")
    parser.add_argument(
        "--mode",
        choices=("auto", "live", "quarter"),
        default="auto",
        help="Data mode: 'live' (SEC Atom+XML), 'quarter' (bulk ZIP), or 'auto' (live first, then quarter)",
    )
    parser.add_argument(
        "--quarter",
        default="latest",
        help="Quarter dataset to screen when mode is quarter/auto (e.g. '2026q1' or 'latest')",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=8,
        help="Number of top candidates to select (default: 8)",
    )
    parser.add_argument(
        "--min-value",
        type=float,
        default=50000.0,
        help="Minimum purchase value in USD (default: $50,000)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=40,
        help="Minimum conviction score out of 100 (default: 40)",
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
    events = []
    source_tag = args.mode
    if args.mode in ("auto", "live"):
        logger.info("Fetching live SEC EDGAR Form 4 Atom+XML filings...")
        events = fetcher.fetch_live_purchases(min_value=args.min_value)
        source_tag = "live"

    if not events and args.mode in ("auto", "quarter"):
        quarter = args.quarter.strip().lower()
        if quarter == "latest":
            try:
                quarter = fetcher.latest_available_quarter()
                logger.info("Auto-detected latest available quarter on SEC EDGAR: %s", quarter)
            except Exception as exc:
                logger.warning("Could not auto-detect latest quarter (%s), falling back to 2026q1", exc)
                quarter = "2026q1"

        logger.info("Loading Form 4 insider transactions for %s ...", quarter)
        try:
            events = fetcher.parse_quarter(quarter, min_value=args.min_value)
            source_tag = quarter
        except Exception as exc:
            logger.error("Failed to parse quarter %s: %s", quarter, exc)
            return 1

    candidates = screen_us_insider_stocks(
        events,
        min_score=args.min_score,
        top_n=args.top,
        min_value=args.min_value,
    )

    report_text = format_sec_screener_report(candidates)
    print("\n" + report_text + "\n")

    if args.notify:
        try:
            from src.notification import NotificationService

            notifier = NotificationService()
            if notifier.is_available():
                notifier.send(report_text, dedup_key=f"sec-form4-screener:{source_tag}")
                print("[Info] Report delivered to notification channels.")
            else:
                print("[Warn] No notification channel configured in .env", file=sys.stderr)
        except Exception as exc:
            logger.warning("Failed to send notification: %s", exc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
