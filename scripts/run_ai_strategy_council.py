#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convene Claude CLI, Codex CLI, and Gemini CLI to author & track daily paper strategies.

    python scripts/run_ai_strategy_council.py convene
    python scripts/run_ai_strategy_council.py convene --members claude,codex,gemini
    python scripts/run_ai_strategy_council.py status
    python scripts/run_ai_strategy_council.py step
    python scripts/run_ai_strategy_council.py reevaluate   # v2 gate on stored charters, no CLI calls
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def cmd_convene(args: argparse.Namespace) -> int:
    from src.config import get_config
    from src.quant.ai_council import convene_ai_strategy_council

    cfg = get_config()
    members = [m.strip().lower() for m in args.members.split(",") if m.strip()]
    overrides = {}
    if args.claude_model:
        overrides["claude"] = args.claude_model
    if args.codex_model:
        overrides["codex"] = args.codex_model
    if args.gemini_model:
        overrides["gemini"] = args.gemini_model

    res = convene_ai_strategy_council(
        members=members,
        initial_capital=float(getattr(cfg, "quant_paper_capital", 10000.0)),
        cost_bps=float(getattr(cfg, "quant_paper_cost_bps", 5.0)),
        timeout_s=float(args.timeout),
        model_overrides=overrides,
        force_refresh_prices=bool(args.refresh),
    )
    print(f"=== 3-AI Strateji Konseyi ({res.get('as_of_date')}) ===")
    for member, info in (res.get("results") or {}).items():
        if not info.get("ok"):
            print(f"\n[HATA · {member.upper()}] {info.get('error')}")
            continue
        ch = info["charter"]
        oos = ch.get("oos_backtest") or {}
        book = info["book"]
        print(f"\n[{ch['engine_label']} ({ch['model']})] -> {ch['strategy_name']}")
        print(f"  Kural Motoru : {ch['rule_engine']} (rebalance: {ch['rebalance_mode']}) | Karar: {ch['verdict']}")
        print(
            f"  OOS 2022+    : CAGR {oos.get('cagr_pct', 0):+.1f}% | Sharpe {oos.get('sharpe', 0):.2f} "
            f"| MaxDD {oos.get('max_drawdown_pct', 0):.1f}% | DSR %{oos.get('dsr_pct', 0):.1f}"
        )
        v2 = ch.get("council_v2") or {}
        stress25 = (v2.get("cost_stress") or {}).get("25") or {}
        print(
            f"  Konsey v2    : {v2.get('verdict', '—')} | BIL üstü Sharpe {oos.get('excess_sharpe', 0):+.2f} "
            f"(25 bps: {stress25.get('excess_sharpe', 0):+.2f})"
        )
        print(f"  Tez          : {ch['thesis']}")
        print(f"  Canlı Defter : NAV ${book['nav']:,.2f} | İşlem: {book['trade_count']} | Dağılım: {book['weights_pct']}")
    return 0 if res.get("ok") else 1


def cmd_status(_args: argparse.Namespace) -> int:
    from src.quant.ai_council import get_active_council_books_status

    books = get_active_council_books_status()
    if not books:
        print("Henüz başlatılmış AI Konseyi strateji defteri yok. `convene` komutunu çalıştırın.")
        return 0
    for b in books:
        print(b.get("report_text") or "")
        print()
    return 0


def cmd_step(args: argparse.Namespace) -> int:
    from src.quant.ai_council import step_active_council_books

    books = step_active_council_books(
        force_rebalance=bool(args.force_rebalance),
        force_refresh_prices=bool(args.refresh),
    )
    if not books:
        print("Takip edilecek AI Konseyi strateji defteri bulunamadı.")
        return 0
    for b in books:
        print(b.get("report_text") or "")
        print()
    return 0


def cmd_reevaluate(args: argparse.Namespace) -> int:
    from src.config import get_config
    from src.quant.ai_council import format_council_v2_report, reevaluate_council_charters

    cfg = get_config()
    res = reevaluate_council_charters(
        cost_bps=float(getattr(cfg, "quant_paper_cost_bps", 5.0)),
        force_refresh_prices=bool(args.refresh),
    )
    if not res.get("ok"):
        print(res.get("error"))
        return 1
    print(format_council_v2_report(res.get("results") or []))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="3-AI Quantitative Strategy Council (Claude, Codex, Gemini)")
    sub = parser.add_subparsers(dest="command", required=True)

    conv = sub.add_parser("convene", help="Convene Claude, Codex, and Gemini CLIs to author & launch live paper strategies")
    conv.add_argument("--members", default="claude,codex,gemini", help="Comma-separated CLI engines")
    conv.add_argument("--timeout", type=float, default=120.0, help="Per-CLI timeout in seconds")
    conv.add_argument("--refresh", action="store_true", help="Force refresh ETF prices")
    conv.add_argument("--claude-model", default="", help="Optional Claude CLI model override")
    conv.add_argument("--codex-model", default="", help="Optional Codex CLI model override")
    conv.add_argument("--gemini-model", default="", help="Optional Gemini CLI model override")

    sub.add_parser("status", help="Show current AI Council live paper books")
    st = sub.add_parser("step", help="Advance active AI Council paper books by latest daily close")
    st.add_argument("--force-rebalance", action="store_true")
    st.add_argument("--refresh", action="store_true")

    rev = sub.add_parser("reevaluate", help="Re-run the council v2 gate (BIL, cost stress, 2022) on stored charters")
    rev.add_argument("--refresh", action="store_true")

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    return {"convene": cmd_convene, "status": cmd_status, "step": cmd_step, "reevaluate": cmd_reevaluate}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
