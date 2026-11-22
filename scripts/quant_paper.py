#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PAA Crash-Shield & Meta-Portfolio A StrategyPaperBook CLI (simulated only, never real orders).

    python scripts/quant_paper.py status                     # print current ledgers without network calls
    python scripts/quant_paper.py step                       # advance PAA & Meta-A ledgers to latest close
    python scripts/quant_paper.py step --strategy paa        # advance only PAA
    python scripts/quant_paper.py step --force-rebalance     # force immediate rebalance to live signal
    python scripts/quant_paper.py step --notify              # push Telegram/notification when trades occur
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_settings(strategy_arg: str):
    from src.config import get_config
    from src.quant.paper_book import normalize_quant_paper_strategies, resolve_active_quant_paper_strategies

    cfg = get_config()
    strategies = (
        normalize_quant_paper_strategies([s.strip() for s in strategy_arg.split(",") if s.strip()])
        if strategy_arg
        else resolve_active_quant_paper_strategies(getattr(cfg, "quant_paper_strategies", None))
    )
    return {
        "strategies": strategies,
        "initial_capital": float(getattr(cfg, "quant_paper_capital", 10000.0)),
        "cost_bps": float(getattr(cfg, "quant_paper_cost_bps", 5.0)),
        "rebalance_mode": str(getattr(cfg, "quant_paper_rebalance_mode", "monthly")),
    }


def cmd_status(args: argparse.Namespace) -> int:
    from src.quant.paper_book import get_quant_paper_books_status

    settings = _load_settings(args.strategy)
    res = get_quant_paper_books_status(**settings)
    print(res.get("report_text") or "Henüz kayıtlı PAA/Meta-A sanal portföy defteri yok.")
    return 0


def cmd_step(args: argparse.Namespace) -> int:
    from src.quant.paper_book import step_quant_paper_books

    settings = _load_settings(args.strategy)
    res = step_quant_paper_books(
        **settings,
        force_rebalance=bool(args.force_rebalance),
        force_refresh_prices=bool(args.refresh),
    )
    if not res.get("ok"):
        print(f"[Hata] {res.get('error')}", file=sys.stderr)
        return 1
    report = res.get("report_text") or ""
    print(report)
    if not args.no_snapshot_refresh:
        from src.quant.snapshot_refresh import format_snapshot_refresh_report, refresh_strategy_snapshots

        refresh = refresh_strategy_snapshots(force_refresh_prices=bool(args.refresh))
        line = format_snapshot_refresh_report(refresh)
        if line:
            print(f"\n{line}")
    new_trades = int(res.get("total_new_trades") or 0)
    if new_trades:
        print(f"\nBu adımda toplam {new_trades} sanal ETF işlemi kaydedildi.")
    if args.notify and (new_trades > 0 or args.always_notify):
        from src.notification import NotificationService

        books = res.get("books") or []
        last_date = books[0].get("last_date") if books else "latest"
        NotificationService().send(report, dedup_key=f"quant-paper:{last_date}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PAA & Meta-Portfolio A daily StrategyPaperBook CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    st = sub.add_parser("status", help="print persisted PAA / Meta-A paper book ledgers")
    st.add_argument("--strategy", default="", help="paa, meta_a, v3_trp or all (comma-separated)")

    step = sub.add_parser("step", help="advance PAA / Meta-A paper books to the latest completed close")
    step.add_argument("--strategy", default="", help="paa, meta_a, v3_trp or all (comma-separated)")
    step.add_argument("--force-rebalance", action="store_true", help="force rebalance on latest close")
    step.add_argument("--refresh", action="store_true", help="force refresh US ETF prices from Yahoo Finance")
    step.add_argument("--notify", action="store_true", help="send notification when trades occur")
    step.add_argument("--always-notify", action="store_true", help="with --notify: send even without trades")
    step.add_argument(
        "--no-snapshot-refresh",
        action="store_true",
        help="skip refreshing tournament / research v3 snapshots used by the /simple screen",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    return {"status": cmd_status, "step": cmd_step}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
