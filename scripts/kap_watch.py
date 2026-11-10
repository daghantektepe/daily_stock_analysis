#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Watch KAP for the Borsa Istanbul stocks in STOCK_LIST and alert new material disclosures.

    python scripts/kap_watch.py            # loop (KAP_WATCH_INTERVAL_SECONDS, KAP_WATCH_HOURS)
    python scripts/kap_watch.py --once     # one poll, print alerts, do not send
    python scripts/kap_watch.py --stocks THYAO.IS,ASELS.IS

Alerts go to the notification channels configured in .env (e.g. Telegram). The
first poll of each stock only records existing disclosures; state lives in
data/kap_watch_state.json. Run it next to ``python main.py --serve --schedule``.
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
    parser = argparse.ArgumentParser(description="KAP & Turkish news material disclosure watcher (Borsa Istanbul)")
    parser.add_argument("--stocks", help="comma separated .IS codes (default: STOCK_LIST)")
    parser.add_argument("--once", action="store_true", help="poll once and print, without sending")
    parser.add_argument("--no-news", action="store_true", help="disable multi-source news and rumor alerts (KAP only)")
    parser.add_argument("--state", type=Path, default=REPO_ROOT / "data" / "kap_watch_state.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from src.config import get_config
    from src.services.kap_watch_service import KapWatchService, format_alert

    config = get_config()
    stocks = [code for code in (args.stocks.split(",") if args.stocks else config.stock_list) if code.strip()]
    notifier = None
    if not args.once:
        from src.notification import NotificationService

        notifier = NotificationService()
        if not notifier.is_available():
            print("[Warn] no notification channel configured; alerts will only be logged", file=sys.stderr)
    watch_news = False if args.no_news else bool(getattr(config, "kap_watch_news_enabled", True))
    service = KapWatchService(
        stocks=stocks,
        watch_news=watch_news,
        notifier=notifier,
        state_path=args.state,
        active_hours=config.kap_watch_hours,
    )
    if not service.stocks:
        print("[Error] no .IS stocks to watch (set STOCK_LIST or --stocks)", file=sys.stderr)
        return 1
    if args.once:
        alerts = service.poll_once(send=False)
        for code, items in alerts.items():
            print(format_alert(code, items))
        print(f"{len(alerts)} stock(s) with new material disclosures")
        return 0
    try:
        service.run_forever(interval_seconds=config.kap_watch_interval_seconds)
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
