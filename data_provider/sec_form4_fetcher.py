# -*- coding: utf-8 -*-
"""SEC Form 4 (Insider Transactions) fetcher and parser.

Collects and parses corporate insider transactions filed with the U.S. Securities
and Exchange Commission (SEC) on Form 4 under Section 16(a) of the Securities
Exchange Act of 1934.

Two access modes:
1. **Quarterly Bulk Data Sets** (``{year}q{q}_form345.zip``): complete history for
   event studies. NOTE: SEC publishes these with a lag of several months, so they
   are NOT suitable for live screening on their own.
2. **Live SEC EDGAR Atom Stream**: lists the latest Form 4 filings (the per-filing
   XML still has to be parsed for live screening).

Data hygiene applied when building purchase events:
- Only original Form 4 filings (``DOCUMENT_TYPE == '4'``); ``4/A`` amendments and
  annual Form 5 reports are skipped so the same purchase is never counted twice.
- Only open-market purchases (``TRANS_CODE == 'P'``) of common/ordinary shares.
- Purchases whose footnotes / remarks mention an underwritten public offering,
  IPO, private placement or registered direct offering are flagged
  (``is_offering``) and excluded by default: they are allocations, not
  open-market conviction trades.
- The Rule 10b5-1 checkbox (``AFF10B5ONE``) is read robustly (``1``/``true``).
- Routine vs. opportunistic insiders follow Cohen, Malloy & Pomorski (2012):
  an insider who traded in the same calendar month in each of the three prior
  years is *routine*; an insider with trades in each of the three prior years
  but without that pattern is *opportunistic*; others are *unclassified*.
- Multi-owner (joint) filings: owners appearing on the same filing are merged
  into one economic actor so that a fund and its affiliates are not mistaken
  for several independent insiders ("fake cluster").

SEC EDGAR requires a User-Agent with contact information. It is read from the
``SEC_EDGAR_USER_AGENT`` environment variable (e.g. in ``.env``):
``SEC_EDGAR_USER_AGENT=DailyStockAnalysis/1.0 (contact: you@example.com)``.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import requests

logger = logging.getLogger(__name__)

SEC_USER_AGENT_ENV = "SEC_EDGAR_USER_AGENT"
DEFAULT_CACHE_DIR = Path("data") / "cache" / "sec_form4"

SEC_BULK_URL_PATTERNS = [
    "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{quarter}_form345.zip",
    "https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets/{quarter}_form345.zip",
]
SEC_DATASET_LISTING_URL = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"
SEC_RECENT_ATOM_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=4&company=&dateb=&owner=only&start=0&count={count}&output=atom"
)
SEC_ISSUER_FILINGS_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&dateb=&owner=include&count=40"

_TRUE_VALUES = {"1", "true", "t", "y", "yes"}
_OFFERING_PATTERN = re.compile(
    r"(public offering|underwrit|initial public|\bipo\b|private placement|registered direct|"
    r"subscription agreement|securities purchase agreement|concurrent (?:private )?placement|"
    r"directed share|purchased in the offering|participated in the offering)",
    re.IGNORECASE,
)
_NON_COMMON_PATTERN = re.compile(
    r"(preferred|warrant|\bnote|debenture|\bright|convertible|option)", re.IGNORECASE
)
_FUND_TRUST_PATTERN = re.compile(
    r"(\bfund\b|\bmunicipal\b|closed-end|income trust|term trust|floating rate|senior income|high income|"
    r"preferred income|fixed income|\betf\b|\bindex fund\b)",
    re.IGNORECASE,
)


def resolve_sec_user_agent(explicit: Optional[str] = None) -> str:
    """Return the SEC User-Agent from argument, env, or .env file, or raise a clear error."""
    value = (explicit or os.getenv(SEC_USER_AGENT_ENV) or "").strip()
    if not value or "@" not in value:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            value = (os.getenv(SEC_USER_AGENT_ENV) or "").strip()
        except Exception:  # noqa: BLE001
            pass
    if not value or "@" not in value:
        raise RuntimeError(
            f"{SEC_USER_AGENT_ENV} tanımlı değil. SEC, otomatik erişimde iletişim e-postası içeren bir "
            f"User-Agent ister. .env dosyasına ekleyin: "
            f"{SEC_USER_AGENT_ENV}=DailyStockAnalysis/1.0 (contact: siz@ornek.com)"
        )
    return value


def parse_bool_flag(value: Any) -> bool:
    """Parse SEC boolean columns that mix ``1/0`` and ``true/false`` spellings."""
    return str(value or "").strip().lower() in _TRUE_VALUES


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
    issuer_cik: str = ""
    owner_ciks: Tuple[str, ...] = ()
    shares_owned_after: float = 0.0
    is_offering: bool = False
    is_direct: bool = True


@dataclass
class InsiderClusterEvent:
    """Aggregated open-market insider purchase event for a company on a filing window."""

    symbol: str
    company_name: str
    filing_date: date
    insider_count: int
    insiders: List[Dict[str, Any]] = field(default_factory=list)
    total_value: float = 0.0
    total_shares: float = 0.0
    avg_price: float = 0.0
    has_c_level: bool = False
    # Cohen-Malloy-Pomorski: True only when at least one insider is classified opportunistic.
    is_opportunistic: bool = False
    is_cluster: bool = False
    primary_titles: List[str] = field(default_factory=list)
    issuer_cik: str = ""
    cmp_class: str = "unclassified"  # opportunistic | routine | unclassified
    has_10b51: bool = False
    officer_director_count: int = 0
    ten_pct_only: bool = False
    holding_change_pct: Optional[float] = None
    last_filing_date: Optional[date] = None
    trend_regime: str = "unclassified"  # uptrend | downtrend | unclassified

    @property
    def sec_url(self) -> str:
        return SEC_ISSUER_FILINGS_URL.format(cik=self.issuer_cik) if self.issuer_cik else ""

    @property
    def summary_headline(self) -> str:
        roles = ", ".join(self.primary_titles[:3]) or "Yönetici"
        cluster_tag = f" [KÜME ALIMI: {self.officer_director_count} yönetici]" if self.is_cluster else ""
        c_tag = " [ÜST YÖNETİM]" if self.has_c_level else ""
        cmp_tag = {"opportunistic": " [FIRSATÇI]", "routine": " [RUTİN]"}.get(self.cmp_class, "")
        plan_tag = " [10b5-1 PLANLI]" if self.has_10b51 else ""
        return (
            f"{self.symbol} — ${self.total_value:,.0f} ({self.total_shares:,.0f} adet @ ${self.avg_price:.2f}) "
            f"— {roles}{cluster_tag}{c_tag}{cmp_tag}{plan_tag}"
        )


@dataclass
class QuarterData:
    """Parsed content of one quarterly archive."""

    quarter: str
    purchases: List[InsiderTransaction]
    # owner CIK -> {(year, month)} of open-market trades (P or S), for routine classification
    trade_months: Dict[str, Set[Tuple[int, int]]]
    stats: Dict[str, int] = field(default_factory=dict)


class RoutineClassifier:
    """Cohen-Malloy-Pomorski (2012) routine/opportunistic insider classification.

    Uses only trades from the three calendar years *before* the event year, so the
    classification never looks ahead.
    """

    def __init__(self) -> None:
        self._months: Dict[str, Set[Tuple[int, int]]] = defaultdict(set)

    def add_trade_months(self, trade_months: Dict[str, Set[Tuple[int, int]]]) -> None:
        for cik, months in trade_months.items():
            self._months[cik].update(months)

    def add(self, owner_cik: str, trade_date: date) -> None:
        self._months[owner_cik].add((trade_date.year, trade_date.month))

    def classify(self, owner_cik: str, event_date: date) -> str:
        months = self._months.get(owner_cik)
        if not owner_cik or not months:
            return "unclassified"
        years = {y for y, _ in months}
        prior = (event_date.year - 1, event_date.year - 2, event_date.year - 3)
        if not all(y in years for y in prior):
            return "unclassified"
        if all((y, event_date.month) in months for y in prior):
            return "routine"
        return "opportunistic"


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


_C_LEVEL_PATTERN = re.compile(
    r"(\bceo\b|chief executive|\bcfo\b|chief financial|\bcoo\b|chief operating|chairman|\bchair\b|"
    r"(?<!vice )(?<!vice-)\bpresident\b)",
    re.IGNORECASE,
)


def _is_c_level_title(title: str, relationship: str = "") -> bool:
    """Whether a title represents top management (CEO/CFO/COO/President/Chair, not Vice President)."""
    if not title:
        return False
    return bool(_C_LEVEL_PATTERN.search(title))


def normalize_symbol(raw: Any) -> str:
    """Normalize SEC issuer trading symbols ('ABC, ABCW' -> 'ABC'; 'NONE' -> '')."""
    text = str(raw or "").strip().upper()
    if not text:
        return ""
    text = re.split(r"[,;/\s]+", text)[0]
    if text in ("NONE", "N/A", "NA", "NULL"):
        return ""
    return text


def _safe_float(val: Any) -> float:
    try:
        num = float(val)
        return 0.0 if (num < 0 or num != num) else num
    except (TypeError, ValueError):
        return 0.0


def _referenced_footnote_ids(row: Dict[str, Any]) -> Set[str]:
    ids: Set[str] = set()
    for key, value in row.items():
        if key and key.endswith("_FN") and value:
            ids.update(part.strip() for part in str(value).split(",") if part.strip())
    return ids


class SecForm4Fetcher:
    """Download, cache, and parse SEC Form 4 insider transactions."""

    def __init__(
        self,
        *,
        user_agent: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        timeout: float = 60.0,
        session_get: Optional[Callable[..., requests.Response]] = None,
    ) -> None:
        self._user_agent = user_agent
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.timeout = float(timeout)
        self._get = session_get or requests.get

    @property
    def user_agent(self) -> str:
        return resolve_sec_user_agent(self._user_agent)

    def _headers(self) -> Dict[str, str]:
        return {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}

    # ------------------------------------------------------------ Discovery
    def list_available_quarters(self) -> List[str]:
        """Quarters published on the SEC data set page, oldest first (e.g. ['2023q4', ...])."""
        resp = self._get(SEC_DATASET_LISTING_URL, headers=self._headers(), timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"SEC dataset listing returned HTTP {resp.status_code}")
        found = set(re.findall(r"(\d{4}q[1-4])_form345\.zip", resp.text))
        return sorted(found)

    def latest_available_quarter(self) -> str:
        quarters = self.list_available_quarters()
        if not quarters:
            raise RuntimeError("No SEC Form 3/4/5 quarterly datasets listed")
        return quarters[-1]

    # -------------------------------------------------------- Bulk Quarterly
    def download_quarter_zip(self, quarter_str: str, force: bool = False) -> Path:
        """Download and cache SEC quarterly Form 3/4/5 zip archive (e.g. '2026q1')."""
        norm_q = quarter_str.strip().lower()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        local_path = self.cache_dir / f"{norm_q}_form345.zip"

        if not force and local_path.is_file() and local_path.stat().st_size > 100_000:
            logger.debug("[sec-form4] Using cached zip: %s", local_path)
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

    def load_quarter(
        self,
        quarter_str: str,
        *,
        min_value: float = 10_000.0,
        min_price: float = 2.0,
        exclude_funds_and_trusts: bool = True,
        target_symbols: Optional[Iterable[str]] = None,
        zip_path: Optional[Path] = None,
    ) -> QuarterData:
        """Parse a quarterly archive into clean purchases plus trade-month history."""
        target_set = {s.strip().upper() for s in target_symbols} if target_symbols else None
        source_zip = Path(zip_path) if zip_path else self.download_quarter_zip(quarter_str)
        stats: Dict[str, int] = defaultdict(int)

        with zipfile.ZipFile(source_zip, "r") as archive:
            names = set(archive.namelist())
            if "SUBMISSION.tsv" not in names or "NONDERIV_TRANS.tsv" not in names:
                raise ValueError(f"Malformed SEC Form 4 zip archive: missing TSV tables in {source_zip}")

            def rows(name: str):
                with archive.open(name) as handle:
                    yield from csv.DictReader(
                        io.TextIOWrapper(handle, encoding="utf-8", errors="ignore"), delimiter="\t"
                    )

            # 1. Submissions (original Form 4 only)
            submissions: Dict[str, Dict[str, Any]] = {}
            for row in rows("SUBMISSION.tsv"):
                doc_type = (row.get("DOCUMENT_TYPE") or "").strip().upper()
                if doc_type != "4":
                    stats["skipped_non_form4_or_amendment"] += 1
                    continue
                filing_d = _parse_sec_date(row.get("FILING_DATE"))
                if not filing_d:
                    continue
                sym = normalize_symbol(row.get("ISSUERTRADINGSYMBOL"))
                submissions[row["ACCESSION_NUMBER"]] = {
                    "symbol": sym,
                    "company_name": (row.get("ISSUERNAME") or "").strip(),
                    "issuer_cik": (row.get("ISSUERCIK") or "").strip(),
                    "filing_date": filing_d,
                    "is_10b51": parse_bool_flag(row.get("AFF10B5ONE")),
                    "remarks_offering": bool(_OFFERING_PATTERN.search(row.get("REMARKS") or "")),
                }

            # 2. Reporting owners (all owners of each filing)
            owners: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            if "REPORTINGOWNER.tsv" in names:
                for row in rows("REPORTINGOWNER.tsv"):
                    acc = row.get("ACCESSION_NUMBER")
                    if acc not in submissions:
                        continue
                    rel = (row.get("RPTOWNER_RELATIONSHIP") or "").lower()
                    title = (row.get("RPTOWNER_TITLE") or "").strip()
                    is_off = "officer" in rel
                    is_dir = "director" in rel
                    owners[acc].append({
                        "cik": (row.get("RPTOWNERCIK") or "").strip(),
                        "name": (row.get("RPTOWNERNAME") or "").strip(),
                        "title": title or ("Director" if is_dir else ("Officer" if is_off else rel.title() or "Insider")),
                        "is_officer": is_off,
                        "is_director": is_dir,
                        "is_ten_percent": "tenpercentowner" in rel,
                        "is_c_level": (is_off or is_dir) and _is_c_level_title(title),
                    })

            # 3. Footnotes that mention offerings, keyed by (accession, footnote id)
            offering_notes: Set[Tuple[str, str]] = set()
            if "FOOTNOTES.tsv" in names:
                for row in rows("FOOTNOTES.tsv"):
                    acc = row.get("ACCESSION_NUMBER")
                    if acc in submissions and _OFFERING_PATTERN.search(row.get("FOOTNOTE_TXT") or ""):
                        offering_notes.add((acc, (row.get("FOOTNOTE_ID") or "").strip()))

            # 4. Transactions
            purchases: List[InsiderTransaction] = []
            trade_months: Dict[str, Set[Tuple[int, int]]] = defaultdict(set)
            for row in rows("NONDERIV_TRANS.tsv"):
                acc = row.get("ACCESSION_NUMBER")
                sub = submissions.get(acc)
                if not sub:
                    continue
                code = (row.get("TRANS_CODE") or "").strip().upper()
                if code not in ("P", "S"):
                    continue
                t_date = _parse_sec_date(row.get("TRANS_DATE")) or sub["filing_date"]
                owner_list = owners.get(acc) or []
                for owner in owner_list:
                    if owner["cik"]:
                        trade_months[owner["cik"]].add((t_date.year, t_date.month))
                if code != "P":
                    continue

                stats["purchase_rows"] += 1
                sym = sub["symbol"]
                if not sym:
                    stats["skipped_no_symbol"] += 1
                    continue
                if target_set and sym not in target_set:
                    continue
                if (row.get("TRANS_FORM_TYPE") or "4").strip() not in ("4", ""):
                    stats["skipped_form5_rows"] += 1
                    continue
                title_text = str(row.get("SECURITY_TITLE") or "Common Stock")
                if _NON_COMMON_PATTERN.search(title_text):
                    stats["skipped_non_common"] += 1
                    continue
                if exclude_funds_and_trusts:
                    if _FUND_TRUST_PATTERN.search(sub["company_name"]) or _FUND_TRUST_PATTERN.search(title_text):
                        stats["skipped_fund_or_trust"] += 1
                        continue
                shares = _safe_float(row.get("TRANS_SHARES"))
                price = _safe_float(row.get("TRANS_PRICEPERSHARE"))
                if shares <= 0 or price <= 0:
                    stats["skipped_zero_price"] += 1
                    continue
                if price < min_price:
                    stats["skipped_penny_stock"] += 1
                    continue
                value = shares * price
                if value < min_value:
                    stats["skipped_below_min_value"] += 1
                    continue

                fn_ids = _referenced_footnote_ids(row)
                is_offering = sub["remarks_offering"] or any((acc, fid) in offering_notes for fid in fn_ids)
                primary = owner_list[0] if owner_list else {}
                purchases.append(InsiderTransaction(
                    accession_number=acc,
                    symbol=sym,
                    company_name=sub["company_name"],
                    filing_date=sub["filing_date"],
                    trans_date=t_date,
                    owner_name=primary.get("name", "Unknown Insider"),
                    owner_title=" / ".join(dict.fromkeys(o["title"] for o in owner_list if o.get("title"))) or "Insider",
                    is_officer=any(o["is_officer"] for o in owner_list),
                    is_director=any(o["is_director"] for o in owner_list),
                    is_ten_percent=any(o["is_ten_percent"] for o in owner_list),
                    is_c_level=any(o["is_c_level"] for o in owner_list),
                    is_10b51=sub["is_10b51"],
                    trans_code=code,
                    shares=shares,
                    price=price,
                    total_value=value,
                    security_title=title_text,
                    issuer_cik=sub["issuer_cik"],
                    owner_ciks=tuple(o["cik"] for o in owner_list if o.get("cik")),
                    shares_owned_after=_safe_float(row.get("SHRS_OWND_FOLWNG_TRANS")),
                    is_offering=is_offering,
                    is_direct=(row.get("DIRECT_INDIRECT_OWNERSHIP") or "D").strip().upper() != "I",
                ))
                if is_offering:
                    stats["offering_flagged"] += 1

        stats["purchases_kept"] = len(purchases)
        return QuarterData(quarter=quarter_str.lower(), purchases=purchases, trade_months=dict(trade_months), stats=dict(stats))

    def parse_quarter(
        self,
        quarter_str: str,
        *,
        min_value: float = 10_000.0,
        min_price: float = 2.0,
        exclude_funds_and_trusts: bool = True,
        open_market_only: bool = True,  # kept for backwards compatibility; always True
        cluster_window_days: int = 5,
        target_symbols: Optional[Iterable[str]] = None,
        zip_path: Optional[Path] = None,
        classifier: Optional[RoutineClassifier] = None,
        exclude_offerings: bool = True,
    ) -> List[InsiderClusterEvent]:
        """Parse one quarter into purchase events (convenience wrapper)."""
        data = self.load_quarter(
            quarter_str,
            min_value=min_value,
            min_price=min_price,
            exclude_funds_and_trusts=exclude_funds_and_trusts,
            target_symbols=target_symbols,
            zip_path=zip_path,
        )
        return build_purchase_events(
            data.purchases,
            classifier=classifier,
            window_days=cluster_window_days,
            exclude_offerings=exclude_offerings,
        )

    def build_classifier(self, quarters: Sequence[str]) -> RoutineClassifier:
        """Load trade-month history from the given quarters into a routine classifier."""
        classifier = RoutineClassifier()
        for quarter in quarters:
            try:
                data = self.load_quarter(quarter, min_value=float("inf"))
                classifier.add_trade_months(data.trade_months)
            except Exception as exc:  # noqa: BLE001 - history is best effort
                logger.warning("[sec-form4] history quarter %s unavailable: %s", quarter, exc)
        return classifier

    # --------------------------------------------------------- Live Stream
    def fetch_recent_filings(self, count: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent Form 4 filings from the SEC EDGAR Atom feed (metadata only)."""
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

    def _resolve_raw_form4_xml_url(self, filing_url: str) -> Optional[str]:
        """Resolve raw Form 4 XML URL from an Atom entry link (index page or direct XML)."""
        clean_url = (filing_url or "").strip()
        if not clean_url:
            return None
        if clean_url.lower().endswith(".xml"):
            # Strip SEC XSLT render prefix if present so we retrieve raw XML.
            return re.sub(r"/xsl[^/]+/", "/", clean_url)
        try:
            resp = self._get(clean_url, headers=self._headers(), timeout=self.timeout)
            if resp.status_code != 200:
                return None
            # Find XML links on the filing index page; prefer non-XSLT raw XML.
            matches = re.findall(r'href="([^"]+\.xml)"', resp.text, flags=re.IGNORECASE)
            raw_candidates = [
                m for m in matches
                if "/xsl" not in m.lower() and "primary_doc" not in m.lower()
            ]
            chosen = raw_candidates[0] if raw_candidates else (matches[0] if matches else None)
            if not chosen:
                return None
            chosen = re.sub(r"/xsl[^/]+/", "/", chosen)
            if chosen.startswith("http"):
                return chosen
            if chosen.startswith("/"):
                return f"https://www.sec.gov{chosen}"
            base = clean_url.rsplit("/", 1)[0]
            return f"{base}/{chosen}"
        except Exception as exc:  # noqa: BLE001
            logger.debug("[sec-form4] Failed to resolve XML URL from %s: %s", clean_url, exc)
            return None

    def fetch_live_purchases(
        self,
        *,
        count: int = 80,
        max_filings: int = 40,
        min_value: float = 10_000.0,
        min_price: float = 2.0,
        exclude_funds_and_trusts: bool = True,
        exclude_offerings: bool = True,
        cluster_window_days: int = 5,
        classifier: Optional[RoutineClassifier] = None,
        target_symbols: Optional[Iterable[str]] = None,
        request_delay_seconds: float = 0.12,
    ) -> List[InsiderClusterEvent]:
        """Fetch live SEC EDGAR Form 4 Atom filings, parse raw XMLs, and build purchase events."""
        import time

        entries = self.fetch_recent_filings(count=count)
        if not entries:
            return []

        target_set = {normalize_symbol(s) for s in target_symbols} if target_symbols else None
        seen_links: Set[str] = set()
        transactions: List[InsiderTransaction] = []

        for entry in entries:
            link = str(entry.get("link") or "").strip()
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            if len(seen_links) > max(1, int(max_filings)):
                break

            if request_delay_seconds > 0:
                time.sleep(request_delay_seconds)
            xml_url = self._resolve_raw_form4_xml_url(link)
            if not xml_url:
                continue
            try:
                if request_delay_seconds > 0:
                    time.sleep(request_delay_seconds)
                resp = self._get(xml_url, headers=self._headers(), timeout=self.timeout)
                if resp.status_code != 200:
                    continue
                acc_match = re.search(r"/(\d{10}-\d{2}-\d{6})", link)
                acc_num = acc_match.group(1) if acc_match else link.rsplit("/", 1)[-1]
                filing_dt = _parse_atom_date(entry.get("updated"))
                parsed = parse_form4_xml(
                    resp.content,
                    accession_number=acc_num,
                    default_filing_date=filing_dt,
                    min_value=min_value,
                    min_price=min_price,
                    exclude_funds_and_trusts=exclude_funds_and_trusts,
                )
                for tx in parsed:
                    if target_set and tx.symbol not in target_set:
                        continue
                    transactions.append(tx)
            except Exception as exc:  # noqa: BLE001 - fail-open per filing
                logger.debug("[sec-form4] Live XML fetch/parse failed for %s: %s", xml_url, exc)

        return build_purchase_events(
            transactions,
            classifier=classifier,
            window_days=cluster_window_days,
            exclude_offerings=exclude_offerings,
        )


def quarter_range(start: str, end: str) -> List[str]:
    """Inclusive list of quarters, e.g. quarter_range('2025q3', '2026q1')."""
    sy, sq = int(start[:4]), int(start[-1])
    ey, eq = int(end[:4]), int(end[-1])
    out = []
    y, q = sy, sq
    while (y, q) <= (ey, eq):
        out.append(f"{y}q{q}")
        q += 1
        if q > 4:
            y, q = y + 1, 1
    return out


def _merge_actors(txs: Sequence[InsiderTransaction]) -> Dict[str, str]:
    """Union owners that co-appear on a filing; returns owner key -> actor root."""
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for tx in txs:
        keys = list(tx.owner_ciks) or [f"name:{tx.owner_name}"]
        root = find(keys[0])
        for key in keys[1:]:
            other = find(key)
            if other != root:
                parent[other] = root
    return {k: find(k) for k in list(parent)}


def build_purchase_events(
    txs: Iterable[InsiderTransaction],
    *,
    classifier: Optional[RoutineClassifier] = None,
    window_days: int = 5,
    exclude_offerings: bool = True,
) -> List[InsiderClusterEvent]:
    """Group purchases of the same symbol filed within ``window_days`` into events."""
    by_symbol: Dict[str, List[InsiderTransaction]] = defaultdict(list)
    for tx in txs:
        if exclude_offerings and tx.is_offering:
            continue
        by_symbol[tx.symbol].append(tx)

    events: List[InsiderClusterEvent] = []
    for sym_txs in by_symbol.values():
        sym_txs.sort(key=lambda t: t.filing_date)
        current: List[InsiderTransaction] = []
        for tx in sym_txs:
            if current and (tx.filing_date - current[0].filing_date).days > window_days:
                events.append(_create_cluster_event(current, classifier))
                current = []
            current.append(tx)
        if current:
            events.append(_create_cluster_event(current, classifier))

    events.sort(key=lambda e: (e.filing_date, -e.total_value))
    return events


def cluster_insider_transactions(
    txs: Iterable[InsiderTransaction],
    *,
    window_days: int = 5,
    classifier: Optional[RoutineClassifier] = None,
) -> List[InsiderClusterEvent]:
    """Backwards compatible alias of :func:`build_purchase_events` (offerings kept)."""
    return build_purchase_events(txs, classifier=classifier, window_days=window_days, exclude_offerings=False)


def _create_cluster_event(
    cluster: List[InsiderTransaction],
    classifier: Optional[RoutineClassifier] = None,
) -> InsiderClusterEvent:
    first = cluster[0]
    total_val = sum(t.total_value for t in cluster)
    total_qty = sum(t.shares for t in cluster)
    avg_px = total_val / total_qty if total_qty > 0 else first.price

    actor_of = _merge_actors(cluster)
    actors: Set[str] = set()
    officer_director_actors: Set[str] = set()
    actor_classes: List[str] = []
    for tx in cluster:
        keys = list(tx.owner_ciks) or [f"name:{tx.owner_name}"]
        actor = actor_of[keys[0]]
        actors.add(actor)
        if tx.is_officer or tx.is_director:
            officer_director_actors.add(actor)
        if classifier is not None:
            for cik in tx.owner_ciks:
                actor_classes.append(classifier.classify(cik, tx.trans_date or tx.filing_date))

    classified = [c for c in actor_classes if c != "unclassified"]
    if "opportunistic" in classified:
        cmp_class = "opportunistic"
    elif classified:
        cmp_class = "routine"
    else:
        cmp_class = "unclassified"

    pre_holdings = sum(max(t.shares_owned_after - t.shares, 0.0) for t in cluster if t.shares_owned_after > 0)
    holding_change = (total_qty / pre_holdings * 100.0) if pre_holdings > 0 else None

    titles: List[str] = []
    for t in cluster:
        if t.owner_title and t.owner_title not in titles:
            titles.append(t.owner_title)

    insiders_detail = [
        {
            "name": t.owner_name,
            "title": t.owner_title,
            "owner_ciks": list(t.owner_ciks),
            "shares": t.shares,
            "price": t.price,
            "value": t.total_value,
            "is_c_level": t.is_c_level,
            "is_10b51": t.is_10b51,
            "trans_date": t.trans_date.isoformat() if t.trans_date else None,
        }
        for t in cluster
    ]

    return InsiderClusterEvent(
        symbol=first.symbol,
        company_name=first.company_name,
        filing_date=first.filing_date,
        insider_count=len(actors) or 1,
        insiders=insiders_detail,
        total_value=round(total_val, 2),
        total_shares=round(total_qty, 2),
        avg_price=round(avg_px, 4),
        has_c_level=any(t.is_c_level for t in cluster),
        is_opportunistic=cmp_class == "opportunistic",
        is_cluster=len(officer_director_actors) >= 2,
        primary_titles=titles,
        issuer_cik=first.issuer_cik,
        cmp_class=cmp_class,
        has_10b51=any(t.is_10b51 for t in cluster),
        officer_director_count=len(officer_director_actors),
        ten_pct_only=not any(t.is_officer or t.is_director for t in cluster),
        holding_change_pct=round(holding_change, 2) if holding_change is not None else None,
        last_filing_date=max(t.filing_date for t in cluster),
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
        summary_text = (summary_el.text or "") if summary_el is not None else ""

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


def _parse_atom_date(updated_str: Optional[str]) -> Optional[date]:
    if not updated_str:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(updated_str).strip())
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            return None
    return None


def _xml_text(root: ET.Element, path: str) -> str:
    node = root.find(path)
    return (node.text or "").strip() if (node is not None and node.text) else ""


def parse_form4_xml(
    xml_bytes: bytes,
    *,
    accession_number: str = "",
    default_filing_date: Optional[date] = None,
    min_value: float = 10_000.0,
    min_price: float = 2.0,
    exclude_funds_and_trusts: bool = True,
) -> List[InsiderTransaction]:
    """Parse a raw SEC Form 4 XML document into clean open-market purchase transactions."""
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[sec-form4] Malformed Form 4 XML: %s", exc)
        return []

    doc_type = _xml_text(root, "documentType").upper()
    if doc_type and doc_type != "4":
        return []

    symbol = normalize_symbol(_xml_text(root, "issuer/issuerTradingSymbol"))
    if not symbol:
        return []
    company_name = _xml_text(root, "issuer/issuerName") or symbol
    issuer_cik = _xml_text(root, "issuer/issuerCik").zfill(10) if _xml_text(root, "issuer/issuerCik").isdigit() else _xml_text(root, "issuer/issuerCik")

    is_10b51 = parse_bool_flag(_xml_text(root, "aff10b5One"))
    remarks = _xml_text(root, "remarks")
    remarks_offering = bool(_OFFERING_PATTERN.search(remarks))

    filing_date = (
        default_filing_date
        or _parse_sec_date(_xml_text(root, "ownerSignature/signatureDate"))
        or _parse_sec_date(_xml_text(root, "periodOfReport"))
        or date.today()
    )

    footnotes: Dict[str, str] = {}
    for fn in root.findall("footnotes/footnote"):
        fid = (fn.attrib.get("id") or "").strip()
        if fid:
            footnotes[fid] = "".join(fn.itertext()).strip()

    owners: List[Dict[str, Any]] = []
    for owner_el in root.findall("reportingOwner"):
        ocik = _xml_text(owner_el, "reportingOwnerId/rptOwnerCik")
        oname = _xml_text(owner_el, "reportingOwnerId/rptOwnerName") or "Unknown Insider"
        is_off = parse_bool_flag(_xml_text(owner_el, "reportingOwnerRelationship/isOfficer"))
        is_dir = parse_bool_flag(_xml_text(owner_el, "reportingOwnerRelationship/isDirector"))
        is_ten = parse_bool_flag(_xml_text(owner_el, "reportingOwnerRelationship/isTenPercentOwner"))
        title = _xml_text(owner_el, "reportingOwnerRelationship/officerTitle")
        if not title:
            if is_dir:
                title = "Director"
            elif is_ten:
                title = "10% Owner"
            else:
                title = "Insider"
        owners.append({
            "cik": ocik,
            "name": oname,
            "title": title,
            "is_officer": is_off,
            "is_director": is_dir,
            "is_ten_percent": is_ten,
            "is_c_level": _is_c_level_title(title),
        })

    primary = owners[0] if owners else {}
    combined_title = " / ".join(dict.fromkeys(o["title"] for o in owners if o.get("title"))) or "Insider"
    owner_ciks = tuple(o["cik"] for o in owners if o.get("cik"))

    purchases: List[InsiderTransaction] = []
    for tx_el in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _xml_text(tx_el, "transactionCoding/transactionCode").upper()
        if code != "P":
            continue
        form_type = _xml_text(tx_el, "transactionCoding/transactionFormType").upper()
        if form_type and form_type != "4":
            continue

        sec_title = _xml_text(tx_el, "securityTitle/value") or "Common Stock"
        if _NON_COMMON_PATTERN.search(sec_title):
            continue
        if exclude_funds_and_trusts and (
            _FUND_TRUST_PATTERN.search(company_name) or _FUND_TRUST_PATTERN.search(sec_title)
        ):
            continue

        shares = _safe_float(_xml_text(tx_el, "transactionAmounts/transactionShares/value"))
        price = _safe_float(_xml_text(tx_el, "transactionAmounts/transactionPricePerShare/value"))
        if shares <= 0 or price < min_price:
            continue
        total_value = shares * price
        if total_value < min_value:
            continue

        t_date = _parse_sec_date(_xml_text(tx_el, "transactionDate/value")) or filing_date
        shares_after = _safe_float(_xml_text(tx_el, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"))
        direct_flag = _xml_text(tx_el, "ownershipNature/directOrIndirectOwnership/value").upper()

        fn_ids = [
            (fn_ref.attrib.get("id") or "").strip()
            for fn_ref in tx_el.findall(".//footnoteId")
        ]
        is_offering = remarks_offering or any(
            _OFFERING_PATTERN.search(footnotes.get(fid, "")) for fid in fn_ids if fid
        )

        purchases.append(InsiderTransaction(
            accession_number=accession_number or f"live-{symbol}-{t_date.isoformat()}",
            symbol=symbol,
            company_name=company_name,
            filing_date=filing_date,
            trans_date=t_date,
            owner_name=primary.get("name", "Unknown Insider"),
            owner_title=combined_title,
            is_officer=any(o["is_officer"] for o in owners),
            is_director=any(o["is_director"] for o in owners),
            is_ten_percent=any(o["is_ten_percent"] for o in owners),
            is_c_level=any(o["is_c_level"] for o in owners),
            is_10b51=is_10b51,
            trans_code="P",
            shares=shares,
            price=price,
            total_value=total_value,
            security_title=sec_title,
            issuer_cik=issuer_cik,
            owner_ciks=owner_ciks,
            shares_owned_after=shares_after,
            is_offering=is_offering,
            is_direct=(direct_flag != "I"),
        ))

    return purchases


__all__ = [
    "InsiderClusterEvent",
    "InsiderTransaction",
    "QuarterData",
    "RoutineClassifier",
    "SEC_USER_AGENT_ENV",
    "SecForm4Fetcher",
    "build_purchase_events",
    "cluster_insider_transactions",
    "normalize_symbol",
    "parse_bool_flag",
    "parse_form4_xml",
    "parse_sec_atom_feed",
    "quarter_range",
    "resolve_sec_user_agent",
]
