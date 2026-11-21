#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Forward (live paper) validation of the frozen PAA / Meta-Portfolio A strategies.

    python scripts/quant_forward.py status                       # gate verdict (freezes on first run)
    python scripts/quant_forward.py freeze --strategy meta_a --reset   # start a NEW forward test after a code change
    python scripts/quant_forward.py alpaca-plan --strategy meta_a --capital 10000   # read-only order plan
    python scripts/quant_forward.py alpaca-submit-paper --strategy meta_a --capital 10000   # PAPER account only
    python scripts/quant_forward.py alpaca-reconcile             # record paper fills and slippage

The daily `quant_paper.py step` already evaluates the gate. Alpaca commands
never run from the scheduler; submission refuses anything but the paper
account and does not change ALPACA_PAPER / ALPACA_AUTO_EXECUTE.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _paper_settings():
    from src.config import get_config

    cfg = get_config()
    return cfg, {
        "initial_capital": float(getattr(cfg, "quant_paper_capital", 10000.0)),
        "cost_bps": float(getattr(cfg, "quant_paper_cost_bps", 5.0)),
        "rebalance_mode": str(getattr(cfg, "quant_paper_rebalance_mode", "monthly")),
    }


def _strategies(arg: str, cfg) -> list:
    return [s.strip() for s in arg.split(",") if s.strip()] if arg else list(
        getattr(cfg, "quant_paper_strategies", ["paa", "meta_a"]))


def cmd_status(args) -> int:
    from src.quant.forward_validation import format_forward_report, run_forward_validation

    cfg, settings = _paper_settings()
    results = run_forward_validation(strategies=_strategies(args.strategy, cfg), paper_settings=settings)
    print(format_forward_report(results))
    return 0


def cmd_freeze(args) -> int:
    from src.quant.forward_validation import format_forward_report, run_forward_validation

    cfg, settings = _paper_settings()
    if args.reset and not args.yes:
        answer = input("Mevcut ileri test kaydı arşivlenip yeni test başlatılacak. Devam? [e/H] ").strip().lower()
        if answer not in ("e", "evet", "y", "yes"):
            print("İptal edildi.")
            return 1
    results = run_forward_validation(strategies=_strategies(args.strategy, cfg), paper_settings=settings,
                                     reset=bool(args.reset))
    print(format_forward_report(results))
    return 0


def _alpaca_context(args):
    from src.brokers.alpaca import AlpacaClient
    from src.quant.paper_book import build_quant_paper_book

    cfg, settings = _paper_settings()
    client = AlpacaClient()
    if not client.is_configured():
        raise SystemExit("ALPACA_API_KEY / ALPACA_SECRET_KEY tanımlı değil (Alpaca Paper Trading anahtarları).")
    if not client.paper:
        raise SystemExit("İleri doğrulama yalnızca Alpaca sanal hesabıyla yapılır: ALPACA_PAPER=true olmalı.")
    book, _ = build_quant_paper_book(args.strategy, **settings)
    targets = book.state.get("live_target_weights") or {}
    if not targets:
        raise SystemExit("Sanal defterde hedef ağırlık yok; önce `python scripts/quant_paper.py step` çalıştırın.")
    return client, targets


def _plan(args):
    from src.quant.forward_validation import plan_alpaca_orders

    client, targets = _alpaca_context(args)
    account = client.get_account()
    positions = client.list_positions()
    symbols = sorted(set(targets) | {p["symbol"] for p in positions})
    trades = client.get_latest_trades(symbols)
    last_prices = {sym: float((row or {}).get("p") or 0.0) for sym, row in trades.items()}
    equity = float(account.get("equity") or account.get("portfolio_value") or 0.0)
    orders = plan_alpaca_orders(targets, equity, positions, last_prices, capital=args.capital)
    return client, orders, targets, equity


def cmd_alpaca_plan(args) -> int:
    _, orders, targets, equity = _plan(args)
    print(f"Hedef ağırlıklar ({args.strategy}): " + ", ".join(f"{k} %{v:.1f}" for k, v in targets.items()))
    print(f"Alpaca sanal hesap değeri: {equity:,.2f} USD | kullanılacak sermaye: {args.capital or equity:,.2f} USD")
    if not orders:
        print("Hesap hedefe yakın; emir gerekmiyor.")
    for order in orders:
        print(f"  {order['side'].upper():4} {order['qty']:>5} {order['symbol']:<5} ~{order['reference_price']:,.2f} "
              f"({order['notional']:,.0f} USD)")
    print("Bu yalnızca plan; emir gönderilmedi.")
    return 0


def cmd_alpaca_submit(args) -> int:
    from src.quant.forward_validation import ForwardRegistry, submit_paper_orders

    client, orders, _, _ = _plan(args)
    if not orders:
        print("Hesap hedefe yakın; emir gerekmiyor.")
        return 0
    if not args.yes:
        answer = input(f"{len(orders)} emir Alpaca SANAL hesabına gönderilecek. Devam? [e/H] ").strip().lower()
        if answer not in ("e", "evet", "y", "yes"):
            print("İptal edildi.")
            return 1
    sent = submit_paper_orders(client, orders, strategy_key=args.strategy, registry=ForwardRegistry())
    print(f"{len(sent)} sanal emir gönderildi. Dolumlar için birkaç dakika sonra `alpaca-reconcile` çalıştırın.")
    return 0


def cmd_alpaca_reconcile(_args) -> int:
    from src.brokers.alpaca import AlpacaClient
    from src.quant.forward_validation import ForwardRegistry, reconcile_paper_fills, slippage_summary

    client = AlpacaClient()
    if not client.is_configured() or not client.paper:
        raise SystemExit("Alpaca sanal hesap anahtarları gerekli (ALPACA_PAPER=true).")
    registry = ForwardRegistry()
    updated = reconcile_paper_fills(client, registry)
    for order in updated:
        extra = f" dolum {order['filled_avg_price']:.2f}, kayma {order['slippage_bps']:+.1f} bps" if order.get("slippage_bps") is not None else ""
        print(f"  {order['symbol']} {order['side']}: {order['status']}{extra}")
    summary = slippage_summary(registry.data["orders"])
    print(f"Toplam dolum: {summary['fills']} | ortalama kayma: {summary['avg_bps']} bps | en kötü: {summary['worst_bps']} bps")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Forward validation gate for PAA / Meta-Portfolio A")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="evaluate the gate (freezes on first run)")
    status.add_argument("--strategy", default="")
    freeze = sub.add_parser("freeze", help="freeze strategies (use --reset to start a new forward test)")
    freeze.add_argument("--strategy", default="")
    freeze.add_argument("--reset", action="store_true")
    freeze.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    for name in ("alpaca-plan", "alpaca-submit-paper"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--strategy", default="meta_a", choices=("paa", "meta_a"))
        cmd.add_argument("--capital", type=float, default=None, help="USD of the paper account to use")
        cmd.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    sub.add_parser("alpaca-reconcile")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    handlers = {"status": cmd_status, "freeze": cmd_freeze, "alpaca-plan": cmd_alpaca_plan,
                "alpaca-submit-paper": cmd_alpaca_submit, "alpaca-reconcile": cmd_alpaca_reconcile}
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
