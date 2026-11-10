#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Measure historical forward returns (1/5/20 trading days) and BIST 100 excess returns after KAP events.

    python scripts/kap_event_study.py                                # STOCK_LIST (.IS) over 365 days
    python scripts/kap_event_study.py --stocks THYAO.IS,ASELS.IS     # custom stocks
    python scripts/kap_event_study.py --days 365 --notify            # also send to Telegram / configured channels
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _parse_horizons(raw: str) -> List[int]:
    values: List[int] = []
    for item in (raw or "").split(","):
        item = item.strip().rstrip("dDgG")
        if item.isdigit() and int(item) > 0:
            values.append(int(item))
    return values or [1, 5, 20]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="KAP historical event study: 1/5/20 trading day returns vs BIST 100"
    )
    parser.add_argument(
        "--stocks",
        default=None,
        help="comma-separated .IS symbols (defaults to STOCK_LIST from .env)",
    )
    parser.add_argument("--days", type=int, default=365, help="lookback window in calendar days (default: 365)")
    parser.add_argument(
        "--horizons",
        default="1,5,20",
        help="forward trading-day horizons, comma-separated (default: 1,5,20)",
    )
    parser.add_argument("--notify", action="store_true", help="send the report to configured notification channels")
    args = parser.parse_args()

    from src.config import get_config
    from src.services.kap_event_study import format_kap_event_study_report, run_kap_event_study

    if args.stocks:
        stocks = [item.strip() for item in args.stocks.split(",") if item.strip()]
    else:
        config = get_config()
        config.refresh_stock_list()
        stocks = list(config.stock_list or [])

    study = run_kap_event_study(
        stocks,
        days=args.days,
        horizons=_parse_horizons(args.horizons),
    )
    text = format_kap_event_study_report(study)
    print(text)
    if args.notify:
        from src.notification import NotificationService

        if not NotificationService().send(text):
            print("[Warn] no notification channel accepted the message", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

