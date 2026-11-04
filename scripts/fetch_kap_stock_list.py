#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the Borsa Istanbul autocomplete seed from KAP's listed-company list.

Writes ``scripts/stock_index_seeds/stock_list_tr.csv`` in the shared seed
format (``ts_code,symbol,name,enname,aliases``). Then merge it into the Web
autocomplete index without needing the A-share / HK / US source CSVs::

    python scripts/fetch_kap_stock_list.py
    python scripts/generate_index_from_csv.py --merge-markets TR

The company list comes from the public KAP website endpoint used by
``data_provider.kap_fetcher`` (no API key). A company with several share
classes (e.g. ``ISATR, ISBTR, ISCTR``) produces one row per ticker.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_OUTPUT = REPO_ROOT / "scripts" / "stock_index_seeds" / "stock_list_tr.csv"
# Legal-form suffixes dropped from the short alias (kept in the display name).
_LEGAL_SUFFIX_RE = re.compile(
    r"\s+(?:T\.?\s*)?A\.?\s*[ŞSO]\.?$|\s+ANONİM\s+(?:ŞİRKETİ|ORTAKLIĞI)$",
    re.IGNORECASE,
)
_GENERIC_TAIL_RE = re.compile(r"\s+(?:SANAYİ\s+VE\s+TİCARET|SAN\.?\s+VE\s+TİC\.?)$", re.IGNORECASE)


def turkish_lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


_LOWERCASE_WORDS = {"ve", "ile", "veya"}
_ASCII_FOLD = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _capitalize_tr(word: str) -> str:
    lowered = turkish_lower(word)
    if not lowered:
        return lowered
    first = lowered[0]
    first = "İ" if first == "i" else "I" if first == "ı" else first.upper()
    return first + lowered[1:]


def turkish_title(text: str) -> str:
    """Title-case a Turkish upper-case company title (İ/ı aware).

    Tokens containing a dot (``A.Ş.``, ``T.A.Ş.``) and short all-consonant
    abbreviations stay upper-case; conjunctions (``ve``, ``ile``) are lower-case
    except at the start; hyphenated parts are capitalized separately.
    """
    words: List[str] = []
    for index, token in enumerate(text.split()):
        if "." in token or (len(token) <= 3 and not re.search(r"[AEIİOÖUÜ]", token)):
            words.append(token)
            continue
        if index and turkish_lower(token) in _LOWERCASE_WORDS:
            words.append(turkish_lower(token))
            continue
        words.append("-".join(_capitalize_tr(part) for part in token.split("-")))
    return " ".join(words)


def ascii_fold(text: str) -> str:
    return text.translate(_ASCII_FOLD)


def short_alias(title: str) -> str:
    alias = _LEGAL_SUFFIX_RE.sub("", title.strip())
    alias = _GENERIC_TAIL_RE.sub("", alias)
    return turkish_title(alias.strip())


def build_seed_rows(companies: Dict[str, Dict[str, str]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for ticker in sorted(companies):
        title = (companies[ticker].get("title") or "").strip()
        if not title or not re.fullmatch(r"[A-Z][A-Z0-9]{2,5}", ticker):
            continue
        name = turkish_title(title)
        aliases: List[str] = [ticker]
        short = short_alias(title)
        for alias in (short, ascii_fold(short), title):
            if alias and alias not in aliases and alias != name:
                aliases.append(alias)
        rows.append({
            "ts_code": f"{ticker}.IS",
            "symbol": f"{ticker}.IS",
            "name": name,
            "enname": title,
            "aliases": "|".join(aliases),
        })
    return rows


def write_seed(rows: Iterable[Dict[str, str]], output: Path) -> int:
    rows = list(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ts_code", "symbol", "name", "enname", "aliases"])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the BIST autocomplete seed CSV from KAP")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    from data_provider.kap_fetcher import KapDisclosureFetcher

    companies = KapDisclosureFetcher()._company_table()
    if not companies:
        print("[Error] KAP company list is empty or unreachable; seed not written.")
        return 1
    count = write_seed(build_seed_rows(companies), args.output)
    print(f"Wrote {count} BIST tickers to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
