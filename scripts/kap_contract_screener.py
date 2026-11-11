# -*- coding: utf-8 -*-
"""CLI script for Borsa Istanbul KAP New Contract / Business Relationship anomaly screener."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

from data_provider.kap_fetcher import KapDisclosureFetcher
from src.services.kap_contract_screener import (
    KapContractScreener,
    format_kap_contract_report,
)

logger = logging.getLogger(__name__)


def _yfinance_revenue_provider(symbol: str) -> Optional[float]:
    """Fetch Trailing 12-Month Total Revenue from yfinance for a BIST stock."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        rev = info.get("totalRevenue")
        if rev and float(rev) > 0:
            return float(rev)
        # Fallback to annual income statement
        fin = ticker.financials
        if fin is not None and not fin.empty:
            for k in ("Total Revenue", "TotalRevenue", "Revenue"):
                if k in fin.index:
                    val = fin.loc[k].iloc[0]
                    if val and float(val) > 0:
                        return float(val)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to fetch revenue for %s: %s", symbol, exc)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Borsa İstanbul KAP Yeni İş İlişkisi / Sözleşme Hasılat Anomali Taraması."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=5,
        help="Kaç günlük geçmiş KAP bildirimleri taransın (varsayılan: 5)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=35,
        help="Listelenecek asgari mahkûmiyet puanı (0-100, varsayılan: 35)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="En yüksek puanlı kaç hisse listelensin (varsayılan: 10)",
    )
    parser.add_argument(
        "--stocks",
        type=str,
        default="",
        help="Yalnızca belirli BIST hisselerini tara (örnek: ASELS,SDTTR,MIATK)",
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

    target_tickers = [s.strip().upper() for s in args.stocks.split(",") if s.strip()] if args.stocks else None

    print(f"\n🔍 Borsa İstanbul son {args.days} günün KAP sözleşme bildirimleri taranıyor...")
    screener = KapContractScreener(
        kap_fetcher=KapDisclosureFetcher(),
        revenue_provider=_yfinance_revenue_provider,
    )

    candidates = screener.scan_recent_contracts(
        days=args.days,
        min_score=args.min_score,
        top_n=args.top_n,
        target_tickers=target_tickers,
    )

    if args.json:
        import json
        print(json.dumps([c.to_dict() for c in candidates], indent=2, ensure_ascii=False))
        return 0

    report = format_kap_contract_report(candidates)
    print("\n" + report + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
