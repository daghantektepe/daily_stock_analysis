#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI script for Post-Earnings Announcement Drift (PEAD) anomaly screener."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

from src.services.pead_screener import format_pead_report, screen_pead_candidates

logger = logging.getLogger(__name__)

# Default liquid US watch basket (mega tech, growth, industrials, retail)
DEFAULT_US_WATCHLIST = [
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "PLTR",
    "AMD", "AVGO", "NFLX", "COST", "WMT", "LIN", "ISRG", "UBER",
    "CRM", "NOW", "QCOM", "TXN", "AMAT", "MU", "LRCX", "PANW",
    "CAT", "GE", "UNH", "LLY", "JNJ", "ABBV", "MRK", "V", "MA",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bilanço Sonrası Sürüklenme (PEAD) Anomali ve Kâr Sürprizi Taraması."
    )
    parser.add_argument(
        "--stocks",
        type=str,
        default="",
        help="Taranacak hisseler (virgülle ayrılmış, örn: NVDA,AAPL,PLTR,AMD). Boş bırakılırsa varsayılan likit ABD hisseleri taranır.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=40,
        help="En fazla kaç gün önce açıklanmış bilançolar incelensin (varsayılan: 40)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=40,
        help="Listelenecek asgari mahkûmiyet puanı (0-100, varsayılan: 40)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="En yüksek puanlı kaç hisse listelensin (varsayılan: 10)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Çıktıyı JSON formatında ver",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.stocks:
        symbols = [s.strip().upper() for s in args.stocks.split(",") if s.strip()]
    else:
        symbols = DEFAULT_US_WATCHLIST

    print(f"\n🔍 {len(symbols)} hisse için son {args.days} günün bilanço sürprizleri ve PEAD sürüklenmesi taranıyor...")
    candidates = screen_pead_candidates(
        symbols,
        max_days=args.days,
        min_score=args.min_score,
        top_n=args.top_n,
    )

    if args.json:
        import json
        print(json.dumps([c.to_dict() for c in candidates], indent=2, ensure_ascii=False))
        return 0

    report = format_pead_report(candidates)
    print("\n" + report + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
