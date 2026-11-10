#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Screen ~800 BIST stocks for technical setup, volume surge and new KAP events.

    python scripts/bist_screener.py                # print top 8 candidates
    python scripts/bist_screener.py --top 10       # print top 10 candidates
    python scripts/bist_screener.py --notify       # also send to configured channels
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BIST daily stock screener: technical setup, volume surge and recent KAP disclosures"
    )
    parser.add_argument("--top", type=int, default=8, help="number of top BIST candidates to select (default: 8)")
    parser.add_argument(
        "--min-score",
        type=float,
        default=25.0,
        help="minimum composite score required (default: 25.0)",
    )
    parser.add_argument(
        "--min-turnover",
        type=float,
        default=5_000_000.0,
        help="minimum daily turnover in TRY unless a KAP catalyst is present (default: 5000000)",
    )
    parser.add_argument("--no-kap", action="store_true", help="skip KAP disclosure check")
    parser.add_argument("--notify", action="store_true", help="send the screener summary to notification channels")
    args = parser.parse_args()

    from src.services.bist_screener import format_bist_screener_report, screen_bist_stocks

    result = screen_bist_stocks(
        top_n=args.top,
        min_score=args.min_score,
        min_turnover_try=args.min_turnover,
        include_kap=not args.no_kap,
    )
    text = format_bist_screener_report(result)
    print(text)
    if args.notify:
        from src.notification import NotificationService

        if not NotificationService().send(text):
            print("[Warn] no notification channel accepted the message", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

