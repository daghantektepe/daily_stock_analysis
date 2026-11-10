# -*- coding: utf-8 -*-
"""SEC Form 4 (Insider Transactions) fetcher and parser.

Collects and parses corporate insider transactions filed with the U.S. Securities
and Exchange Commission (SEC) on Form 4 under Section 16(a) of the Securities
Exchange Act of 1934.

Two access modes:
1. **Quarterly Bulk Data Sets**:
   Downloads and parses official SEC quarterly Form 3/4/5 archives
   (``{year}q{q}_form345.zip``), providing comprehensive coverage of all open-market
   executive transactions for event studies and backtesting.
2. **Live SEC EDGAR Atom Stream**:
   Polls the latest real-time Form 4 filings via SEC's public browse-edgar feed
   for near-real-time intraday screening.

Academic basis (Cohen, Malloy, Pomorski 2012; Lakonishok & Lee 2001):
- Filters for open-market purchases (``TRANS_CODE == 'P'``).
- Identifies C-suite executives (CEO, CFO, COO, President) vs. board/other.
- Distinguishes opportunistic purchases from pre-planned Rule 10b5-1 trading plans
  (``AFF10B5ONE == '1'``).
- Groups multi-insider buying ("cluster purchases"), the strongest documented
  predictive signal for post-filing abnormal returns.

SEC EDGAR requires a user-agent header containing identifying contact info in the
format ``Sample Company Name AdminContact@<sample company domain>.com``.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

logger = logging.getLogger(__name__)

DEFAULT_SEC_USER_AGENT = "DailyStockAnalysis/1.0 (contact: xavrail@gmail.com)"
DEFAULT_CACHE_DIR = Path("data") / "cache" / "sec_form4"

SEC_BULK_URL_PATTERNS = [
    "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{quarter}_form345.zip",
    "https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets/{quarter}_form345.zip",
]
SEC_RECENT_ATOM_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=4&company=&dateb=&owner=only&start=0&count={count}&output=atom"
)

_C_LEVEL_KEYWORDS = (
    "ceo", "chief executive", "cfo", "chief financial", "coo", "chief operating",
    "president", "chairman", "vice chairman", "executive chairman", "treasurer",
)


@dataclass
class InsiderTransaction:
    """Individual non-derivative transaction from Form 4 (NONDERIV_TRANS.tsv)."""

    accession_number: str
    symbol: str
    company_name: str
    filing_date: date
    trans_date: Optional[date]
    owner_name: str
    owner_title: str
    is_officer: bool
    is_director: bool
    is_ten_percent: bool
    is_c_level: bool
    is_10b51: bool
    trans_code: str
    shares: float
    price: float
    total_value: float
    security_title: str = "Common Stock"


@dataclass
class InsiderClusterEvent:
    """Aggregated open-market insider purchase event for a company on a filing date/window."""

    symbol: str
    company_name: str
    filing_date: date
    insider_count: int
    insiders: List[Dict[str, Any]] = field(default_factory=list)
    total_value: float = 0.0
    total_shares: float = 0.0
    avg_price: float = 0.0
    has_c_level: bool = False
    is_opportunistic: bool = True
    is_cluster: bool = False
    primary_titles: List[str] = field(default_factory=list)

    @property
    def summary_headline(self) -> str:
        roles = ", ".join(self.primary_titles[:3]) or "Yönetici"
        cluster_tag = f" [KÜME ALIMI: {self.insider_count} Yönetici]" if self.is_cluster else ""
        c_tag = " [C-SUITE]" if self.has_c_level else ""
        opp_tag = " [FIRSATÇI / 10b5-1 Yok]" if self.is_opportunistic else ""
        return (
            f"{self.symbol} — ${self.total_value:,.0f} ({self.total_shares:,.0f} adet @ ${self.avg_price:.2f}) "
            f"— {roles}{cluster_tag}{c_tag}{opp_tag}"
        )


def _parse_sec_date(value: Any) -> Optional[date]:
    """Parse SEC EDGAR date format (e.g. '31-MAR-2026', '2026-03-31')."""
    if isinstance(value, date):
        return value
    text = str(value or "").strip().upper()
    if not text or text == "NONE":
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _is_c_level_title(title: str, relationship: str) -> bool:
    """Determine whether an officer title represents a C-suite executive."""
    combined = f"{title} {relationship}".lower()
    return any(kw in combined for kw in _C_LEVEL_KEYWORDS)


class SecForm4Fetcher:
    """Download, cache, and parse SEC Form 4 insider transactions."""

    def __init__(
        self,
        *,
        user_agent: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        timeout: float = 30.0,
        session_get: Optional[Callable[..., requests.Response]] = None,
    ) -> None:
        self.user_agent = user_agent or os.getenv("SEC_EDGAR_USER_AGENT") or DEFAULT_SEC_USER_AGENT
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.timeout = float(timeout)
        self._get = session_get or requests.get

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "www.sec.gov",
        }

    # -------------------------------------------------------- Bulk Quarterly
    def download_quarter_zip(self, quarter_str: str, force: bool = False) -> Path:
        """Download and cache SEC quarterly Form 3/4/5 zip archive (e.g. '2026q1')."""
        norm_q = quarter_str.strip().lower()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        local_path = self.cache_dir / f"{norm_q}_form345.zip"

        if not force and local_path.is_file() and local_path.stat().st_size > 100_000:
            logger.info("[sec-form4] Using cached zip: %s", local_path)
            return local_path

        errors = []
        for pattern in SEC_BULK_URL_PATTERNS:
            url = pattern.format(quarter=norm_q)
            logger.info("[sec-form4] Downloading %s ...", url)
            try:
                resp = self._get(url, headers=self._headers(), stream=True, timeout=self.timeout)
                if resp.status_code == 200:
                    fd, tmp_name = tempfile.mkstemp(
                        dir=str(self.cache_dir), prefix=f".{norm_q}_", suffix=".zip"
                    )
                    with os.fdopen(fd, "wb") as handle:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if chunk:
                                handle.write(chunk)
                    os.replace(tmp_name, local_path)
                    logger.info("[sec-form4] Downloaded %s (%.1f MB)", local_path, local_path.stat().st_size / 1e6)
                    return local_path
                errors.append(f"{url} returned HTTP {resp.status_code}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url} error: {exc}")

        raise RuntimeError(f"Failed to download SEC Form 4 zip for {norm_q}: {'; '.join(errors)}")

    def parse_quarter(
        self,
        quarter_str: str,
        *,
        min_value: float = 20_000.0,
        open_market_only: bool = True,
        cluster_window_days: int = 5,
        target_symbols: Optional[Iterable[str]] = None,
        zip_path: Optional[Path] = None,
    ) -> List[InsiderClusterEvent]:
        """Parse quarterly SEC Form 4 dataset and group into insider purchase events."""
        target_set = {s.strip().upper() for s in target_symbols} if target_symbols else None
        source_zip = Path(zip_path) if zip_path else self.download_quarter_zip(quarter_str)

        with zipfile.ZipFile(source_zip, "r") as archive:
            name_list = archive.namelist()
            if "SUBMISSION.tsv" not in name_list or "NONDERIV_TRANS.tsv" not in name_list:
                raise ValueError(f"Malformed SEC Form 4 zip archive: missing TSV tables in {source_zip}")

            # 1. Parse SUBMISSION.tsv: Accession -> metadata
            submissions: Dict[str, Dict[str, Any]] = {}
            with archive.open("SUBMISSION.tsv") as f:
                reader = csv.DictReader(
                    io.TextIOWrapper(f, encoding="utf-8", errors="ignore"), delimiter="\t"
                )
                for row in reader:
                    sym = (row.get("ISSUERTRADINGSYMBOL") or "").strip().upper()
                    if not sym or sym in ("NONE", "N/A"):
                        continue
                    if target_set and sym not in target_set:
                        continue
                    filing_d = _parse_sec_date(row.get("FILING_DATE"))
                    if not filing_d:
                        continue
                    submissions[row["ACCESSION_NUMBER"]] = {
                        "symbol": sym,
                        "company_name": (row.get("ISSUERNAME") or "").strip(),
                        "filing_date": filing_d,
                        "is_10b51": row.get("AFF10B5ONE") == "1",
                    }

            # 2. Parse REPORTINGOWNER.tsv: Accession -> list of owners/titles
            owners: Dict[str, List[Dict[str, Any]]] = {}
            if "REPORTINGOWNER.tsv" in name_list:
                with archive.open("REPORTINGOWNER.tsv") as f:
                    reader = csv.DictReader(
                        io.TextIOWrapper(f, encoding="utf-8", errors="ignore"), delimiter="\t"
                    )
                    for row in reader:
                        acc = row.get("ACCESSION_NUMBER")
                        if acc not in submissions:
                            continue
                        rel = (row.get("RPTOWNER_RELATIONSHIP") or "").strip()
                        title = (row.get("RPTOWNER_TITLE") or "").strip()
                        name = (row.get("RPTOWNERNAME") or "").strip()
                        is_off = "officer" in rel.lower()
                        is_dir = "director" in rel.lower()
                        is_ten = "tenpercentowner" in rel.lower()
                        is_c = _is_c_level_title(title, rel)
                        owners.setdefault(acc, []).append({
                            "name": name,
                            "title": title or ("Director" if is_dir else ("Officer" if is_off else rel)),
                            "is_officer": is_off,
                            "is_director": is_dir,
                            "is_ten_percent": is_ten,
                            "is_c_level": is_c,
                        })

            # 3. Parse NONDERIV_TRANS.tsv: Extract purchases
            raw_txs: List[InsiderTransaction] = []
            with archive.open("NONDERIV_TRANS.tsv") as f:
                reader = csv.DictReader(
                    io.TextIOWrapper(f, encoding="utf-8", errors="ignore"), delimiter="\t"
                )
                for row in reader:
                    acc = row.get("ACCESSION_NUMBER")
                    sub = submissions.get(acc)
                    if not sub:
                        continue

                    code = (row.get("TRANS_CODE") or "").strip().upper()
                    if open_market_only and code != "P":
                        continue

                    shares = _safe_float(row.get("TRANS_SHARES"))
                    price = _safe_float(row.get("TRANS_PRICEPERSHARE"))
                    if shares <= 0 or price <= 0:
                        continue
                    val = shares * price
                    if val < min_value:
                        continue

                    owner_list = owners.get(acc, [{}])
                    primary_owner = owner_list[0] if owner_list else {}
                    t_date = _parse_sec_date(row.get("TRANS_DATE")) or sub["filing_date"]

                    raw_txs.append(InsiderTransaction(
                        accession_number=acc,
                        symbol=sub["symbol"],
                        company_name=sub["company_name"],
                        filing_date=sub["filing_date"],
                        trans_date=t_date,
                        owner_name=primary_owner.get("name", "Unknown Insider"),
                        owner_title=primary_owner.get("title", "Insider"),
                        is_officer=bool(primary_owner.get("is_officer")),
                        is_director=bool(primary_owner.get("is_director")),
                        is_ten_percent=bool(primary_owner.get("is_ten_percent")),
                        is_c_level=bool(primary_owner.get("is_c_level")),
                        is_10b51=sub["is_10b51"],
                        trans_code=code,
                        shares=shares,
                        price=price,
                        total_value=val,
                        security_title=str(row.get("SECURITY_TITLE") or "Common Stock"),
                    ))

        # 4. Cluster purchases for the same ticker within a rolling window
        return cluster_insider_transactions(raw_txs, window_days=cluster_window_days)

    # --------------------------------------------------------- Live Stream
    def fetch_recent_filings(self, count: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent real-time Form 4 filings from the SEC EDGAR Atom feed."""
        url = SEC_RECENT_ATOM_URL.format(count=max(10, min(100, int(count))))
        try:
            resp = self._get(url, headers=self._headers(), timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning("[sec-form4] Atom feed returned HTTP %s", resp.status_code)
                return []
            return parse_sec_atom_feed(resp.content)
        except Exception as exc:  # noqa: BLE001 - fail-open
            logger.warning("[sec-form4] Atom feed fetch failed: %s", exc)
            return []


def _safe_float(val: Any) -> float:
    try:
        num = float(val)
        return 0.0 if (num < 0 or num != num) else num
    except (TypeError, ValueError):
        return 0.0


def cluster_insider_transactions(
    txs: Iterable[InsiderTransaction],
    *,
    window_days: int = 5,
) -> List[InsiderClusterEvent]:
    """Group transactions of the same symbol within ``window_days`` into cluster events."""
    by_symbol: Dict[str, List[InsiderTransaction]] = {}
    for tx in txs:
        by_symbol.setdefault(tx.symbol, []).append(tx)

    events: List[InsiderClusterEvent] = []
    for symbol, sym_txs in by_symbol.items():
        sym_txs.sort(key=lambda t: t.filing_date)
        current_cluster: List[InsiderTransaction] = []

        for tx in sym_txs:
            if not current_cluster:
                current_cluster.append(tx)
                continue
            first_date = current_cluster[0].filing_date
            if (tx.filing_date - first_date).days <= window_days:
                current_cluster.append(tx)
            else:
                events.append(_create_cluster_event(current_cluster))
                current_cluster = [tx]
        if current_cluster:
            events.append(_create_cluster_event(current_cluster))

    events.sort(key=lambda e: (e.filing_date, -e.total_value))
    return events


def _create_cluster_event(cluster: List[InsiderTransaction]) -> InsiderClusterEvent:
    first = cluster[0]
    total_val = sum(t.total_value for t in cluster)
    total_qty = sum(t.shares for t in cluster)
    avg_px = total_val / total_qty if total_qty > 0 else first.price

    distinct_owners = {t.owner_name for t in cluster if t.owner_name and t.owner_name != "Unknown Insider"}
    insider_count = len(distinct_owners) or 1
    has_c = any(t.is_c_level for t in cluster)
    all_opp = all(not t.is_10b51 for t in cluster)

    titles = []
    seen_titles = set()
    for t in cluster:
        if t.owner_title and t.owner_title not in seen_titles:
            titles.append(t.owner_title)
            seen_titles.add(t.owner_title)

    insiders_detail = [
        {
            "name": t.owner_name,
            "title": t.owner_title,
            "shares": t.shares,
            "price": t.price,
            "value": t.total_value,
            "is_c_level": t.is_c_level,
            "is_10b51": t.is_10b51,
        }
        for t in cluster
    ]

    return InsiderClusterEvent(
        symbol=first.symbol,
        company_name=first.company_name,
        filing_date=first.filing_date,
        insider_count=insider_count,
        insiders=insiders_detail,
        total_value=round(total_val, 2),
        total_shares=round(total_qty, 2),
        avg_price=round(avg_px, 4),
        has_c_level=has_c,
        is_opportunistic=all_opp,
        is_cluster=insider_count >= 2,
        primary_titles=titles,
    )


def parse_sec_atom_feed(xml_bytes: bytes) -> List[Dict[str, Any]]:
    """Parse real-time SEC EDGAR Atom XML feed entries for Form 4 filings."""
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[sec-form4] Malformed XML in Atom feed: %s", exc)
        return []

    entries: List[Dict[str, Any]] = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for node in root.findall("atom:entry", ns):
        title_el = node.find("atom:title", ns)
        link_el = node.find("atom:link", ns)
        updated_el = node.find("atom:updated", ns)
        summary_el = node.find("atom:summary", ns)

        raw_title = (title_el.text or "").strip() if title_el is not None else ""
        link = link_el.attrib.get("href", "") if link_el is not None else ""
        updated_str = updated_el.text.strip() if (updated_el is not None and updated_el.text) else ""
        summary_text = summary_el.text or "" if summary_el is not None else ""

        # Form 4 title format: "4 - COMPANY NAME (CIK) (Issuer)" or "4 - PERSON (CIK) (Reporting)"
        match = re.match(r"^4\s*-\s*(.+?)\s*\((.*?)\)\s*\((Issuer|Reporting)\)", raw_title, re.IGNORECASE)
        name = match.group(1).strip() if match else raw_title
        cik = match.group(2).strip() if match else ""
        role = match.group(3).capitalize() if match else ""

        entries.append({
            "title": raw_title,
            "entity_name": name,
            "cik": cik,
            "entity_role": role,
            "link": link,
            "updated": updated_str,
            "summary": summary_text,
        })
    return entries


__all__ = [
    "DEFAULT_SEC_USER_AGENT",
    "InsiderClusterEvent",
    "InsiderTransaction",
    "SecForm4Fetcher",
    "cluster_insider_transactions",
    "parse_sec_atom_feed",
]
