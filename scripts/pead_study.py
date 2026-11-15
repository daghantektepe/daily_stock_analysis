#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Historical PEAD (post-earnings drift) event study on an unbiased universe.

    python scripts/pead_study.py                          # S&P 400 + S&P 600 (mid + small caps)
    python scripts/pead_study.py --universe sp600 --sample 300
    python scripts/pead_study.py --universe-file tickers.txt

Why not the screener watchlists: they were picked from today's winners, so a
backtest on them is biased upwards. Index constituents are chosen by rules, not
by past returns (they still carry survivorship: today's members only).
"""

from __future__ import annotations

import argparse
import io
import logging
import random
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_WIKI_PAGES = {
    "sp400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "sp600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
}
_CACHE_DIR = REPO_ROOT / "data" / "cache" / "universe"


def load_index_constituents(name: str) -> List[str]:
    """Current constituents from Wikipedia, cached on disk for offline reruns."""
    cache = _CACHE_DIR / f"{name}.txt"
    if cache.exists():
        return [line.strip() for line in cache.read_text(encoding="utf-8").splitlines() if line.strip()]
    import pandas as pd
    import requests

    response = requests.get(_WIKI_PAGES[name], timeout=30,
                            headers={"User-Agent": "daily-stock-analysis research script (personal use)"})
    response.raise_for_status()
    table = pd.read_html(io.StringIO(response.text))[0]
    column = next(col for col in table.columns if "symbol" in str(col).lower() or "ticker" in str(col).lower())
    symbols = sorted({str(sym).strip().replace(".", "-") for sym in table[column] if str(sym).strip()})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("\n".join(symbols), encoding="utf-8")
    return symbols


def main() -> int:
    parser = argparse.ArgumentParser(description="PEAD historical event study (U.S. stocks)")
    parser.add_argument("--universe", choices=("sp400", "sp600", "sp500", "smid"), default="smid",
                        help="index constituents to test (default: smid = S&P 400 + S&P 600)")
    parser.add_argument("--universe-file", type=Path, help="text file with one ticker per line (overrides --universe)")
    parser.add_argument("--sample", type=int, default=400, help="random sample of tickers (0 = all, default 400)")
    parser.add_argument("--min-surprise", type=float, default=None, help="only events with EPS surprise >= this %%")
    parser.add_argument("--slippage", type=float, default=0.25, help="slippage + commission %% per trade")
    parser.add_argument("--seed", type=int, default=7, help="random seed for the ticker sample")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from src.services.pead_event_study import format_pead_study_report, run_pead_event_study

    if args.universe_file:
        symbols = [line.strip().upper() for line in args.universe_file.read_text(encoding="utf-8").splitlines()
                   if line.strip() and not line.startswith("#")]
    else:
        names = ("sp400", "sp600") if args.universe == "smid" else (args.universe,)
        symbols = sorted({sym for name in names for sym in load_index_constituents(name)})
    if args.sample and len(symbols) > args.sample:
        symbols = sorted(random.Random(args.seed).sample(symbols, args.sample))
    print(f"PEAD testi: {len(symbols)} hisse (bu birkaç dakika sürebilir; fiyatlar data/cache altında saklanır)")

    result = run_pead_event_study(
        symbols, min_surprise_pct=args.min_surprise, estimated_slippage_pct=args.slippage,
    )
    print("\n" + format_pead_study_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
