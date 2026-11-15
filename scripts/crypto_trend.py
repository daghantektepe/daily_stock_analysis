#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crypto trend strategy: backtest, today's signal, and the paper book.

    python scripts/crypto_trend.py backtest            # robustness table + yearly results
    python scripts/crypto_trend.py signal              # today's coin / cash split
    python scripts/crypto_trend.py paper               # advance the paper book to the last close
    python scripts/crypto_trend.py paper --notify      # ... and send changes / summary

Assets: CRYPTO_TREND_ASSETS (default BTC-USD,ETH-USD). Paper capital:
CRYPTO_TREND_CAPITAL (default 10000 USD). Never places real orders.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _config():
    from src.config import get_config
    from src.services.crypto_trend_strategy import TrendConfig

    cfg = get_config()
    assets = tuple(getattr(cfg, "crypto_trend_assets", None) or ("BTC-USD", "ETH-USD"))
    return cfg, TrendConfig(assets=assets)


def cmd_backtest(_args) -> int:
    from src.services.crypto_trend_strategy import load_daily_closes, robustness_grid, run_backtest

    _, trend = _config()
    prices = load_daily_closes(trend.assets)
    print(f"Kripto trend geçmiş testi ({', '.join(trend.assets)}; maliyet %{trend.cost_pct} / işlem)")
    for label, start, end in (("Tüm dönem", None, None), ("2022-bugün (kural seçiminden sonra)", date(2022, 1, 1), None)):
        print(f"\n{label}:")
        for row in robustness_grid(prices, trend.windows, assets=trend.assets, cost_pct=trend.cost_pct,
                                   start=start, end=end):
            print(f"  {row['label']:>9}: yıllık %{row['strategy_cagr_pct']:>6} | en büyük düşüş %{row['strategy_max_drawdown_pct']:>6} "
                  f"| Sharpe {row['strategy_sharpe']} || al-tut yıllık %{row['buy_hold_cagr_pct']:>6} "
                  f"düşüş %{row['buy_hold_max_drawdown_pct']:>6} Sharpe {row['buy_hold_sharpe']} "
                  f"({row['start']} → {row['end']})")
    result = run_backtest(prices, trend)
    print("\nYıllık getiri (topluluk kuralı vs eşit ağırlıklı al-tut):")
    for year in result["yearly"]:
        print(f"  {year['year']}: strateji %{year['strategy_pct']:+.1f} | al-tut %{year['buy_hold_pct']:+.1f}")
    print("\nNot: geçmiş sonuç geleceği garanti etmez; strateji boğa yıllarında geride kalır, çöküşlerde korur.")
    return 0


def cmd_signal(_args) -> int:
    from src.services.crypto_trend_strategy import current_targets, load_daily_closes

    _, trend = _config()
    targets = current_targets(load_daily_closes(trend.assets), trend)
    for asset, info in targets.items():
        if info.get("reason"):
            print(f"{asset}: yetersiz geçmiş veri")
            continue
        averages = ", ".join(f"SMA{n} {v:,.0f}" for n, v in info["averages"].items())
        print(f"{asset} ({info['date']} kapanış {info['close']:,.2f}): hedef %{info['weight'] * 100:.0f} coin — {averages}")
    return 0


def cmd_paper(args) -> int:
    from src.services.crypto_trend_strategy import current_targets, load_daily_closes
    from src.services.strategy_paper_book import StrategyPaperBook, format_book_report

    cfg, trend = _config()
    prices = load_daily_closes(trend.assets)
    book = StrategyPaperBook(config=trend, initial_capital=float(getattr(cfg, "crypto_trend_capital", 10_000.0)))
    step = book.step(prices)
    report = format_book_report(book.summary(), current_targets(prices, trend))
    print(report)
    if step["new_trades"]:
        print(f"\nBu adımda {len(step['new_trades'])} sanal işlem yapıldı.")
    if args.notify and (step["new_trades"] or args.always_notify):
        from src.notification import NotificationService

        NotificationService().send(report, dedup_key=f"crypto-trend:{book.state.get('last_date')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Crypto trend strategy (BTC/ETH)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backtest", help="robustness table and yearly results")
    sub.add_parser("signal", help="today's target coin / cash split")
    paper = sub.add_parser("paper", help="advance the paper book to the last completed close")
    paper.add_argument("--notify", action="store_true", help="send the report when positions change")
    paper.add_argument("--always-notify", action="store_true", help="with --notify: send even without changes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    return {"backtest": cmd_backtest, "signal": cmd_signal, "paper": cmd_paper}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
