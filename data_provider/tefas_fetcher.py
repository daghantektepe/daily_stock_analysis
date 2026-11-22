# -*- coding: utf-8 -*-
"""TEFAS (Türkiye Elektronik Fon Alım Satım Platformu) public fund fetcher.

Uses TEFAS's official JSON backend (``POST https://www.tefas.gov.tr/api/funds/fonBilgiGetir``)
with 6-hour disk TTL caching (``data/cache/tefas_funds.json``), rate-limit-friendly
per-code querying, and honest metadata fallback when TEFAS is offline.
Zero fabricated return/price numbers are ever emitted on fallback.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import requests

logger = logging.getLogger(__name__)

TEFAS_FUND_INFO_URL = "https://www.tefas.gov.tr/api/funds/fonBilgiGetir"
_DEFAULT_CACHE_PATH = Path("data/cache/tefas_funds.json")

# Curated liquid TEFAS benchmark funds grouped by investor role / bucket
CURATED_TEFAS_CATALOG: List[Dict[str, str]] = [
    {"code": "PPZ", "bucket": "ppf", "default_title": "Azimut Portföy Para Piyasası (TL) Fonu", "global_proxy": "BIL"},
    {"code": "PRY", "bucket": "ppf", "default_title": "Pusula Portföy Para Piyasası (TL) Fonu", "global_proxy": "BIL"},
    {"code": "RPT", "bucket": "ppf", "default_title": "Rota Portföy Para Piyasası (TL) Fonu", "global_proxy": "BIL"},
    {"code": "TCA", "bucket": "altin", "default_title": "Ziraat Portföy Altın Katılım Fonu", "global_proxy": "GLD"},
    {"code": "GGK", "bucket": "altin", "default_title": "Garanti Portföy Altın Fonu", "global_proxy": "GLD"},
    {"code": "TI2", "bucket": "bist", "default_title": "İş Portföy BIST Hisse Senedi (TL) Fonu", "global_proxy": "XU100.IS"},
    {"code": "MAC", "bucket": "bist", "default_title": "Marmara Capital Portföy Hisse Senedi Fonu", "global_proxy": "XU100.IS"},
    {"code": "AFT", "bucket": "yabanci", "default_title": "Ak Portföy Yeni Teknolojiler Yabancı Hisse Fonu", "global_proxy": "QQQ"},
    {"code": "YAY", "bucket": "yabanci", "default_title": "Yapı Kredi Portföy Yabancı Teknoloji Hisse Fonu", "global_proxy": "QQQ"},
    {"code": "TMG", "bucket": "yabanci", "default_title": "İş Portföy Yabancı Hisse Senedi Fonu", "global_proxy": "SPY"},
    {"code": "DBH", "bucket": "degisken_doviz", "default_title": "Deniz Portföy Eurobond (Döviz) Borçlanma Fonu", "global_proxy": "SHY"},
    {"code": "TCD", "bucket": "degisken_doviz", "default_title": "Tacirler Portföy Değişken Fon", "global_proxy": "UUP"},
]

_CURATED_MAP: Dict[str, Dict[str, str]] = {item["code"]: item for item in CURATED_TEFAS_CATALOG}


def _opt_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        num = float(val)
        return None if num != num else num
    except (TypeError, ValueError):
        return None


def _opt_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


class TefasFetcher:
    """Fetch live TEFAS fund unit prices, daily returns, AUM, and category rank."""

    def __init__(
        self,
        *,
        cache_path: Optional[Path] = None,
        cache_ttl_seconds: int = 6 * 3600,
        timeout: float = 8.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.cache_path = Path(cache_path) if cache_path is not None else _DEFAULT_CACHE_PATH
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))
        self.timeout = float(timeout)
        self.session = session or requests.Session()

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            ),
            "Origin": "https://www.tefas.gov.tr",
            "Referer": "https://www.tefas.gov.tr/",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _read_cache(self) -> Dict[str, Dict[str, Any]]:
        if self.cache_ttl_seconds <= 0 or not self.cache_path.exists():
            return {}
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            fetched_at = float(payload.get("fetched_at", 0))
            if (time.time() - fetched_at) > self.cache_ttl_seconds:
                return {}
            funds = payload.get("funds")
            return funds if isinstance(funds, dict) else {}
        except Exception:
            return {}

    def _write_cache(self, funds: Dict[str, Dict[str, Any]]) -> None:
        if self.cache_ttl_seconds <= 0:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps({"fetched_at": time.time(), "funds": funds}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("[tefas-fetcher] cache write skipped: %s", exc)

    def fetch_fund_info(self, fund_code: str, *, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch live details for a single TEFAS fund code (with cache + honest fallback)."""
        code = str(fund_code or "").strip().upper()
        if not code:
            raise ValueError("Fund code must be non-empty.")

        cached_map = {} if force_refresh else self._read_cache()
        if code in cached_map:
            row = dict(cached_map[code])
            row["source"] = "tefas_cached"
            return row

        catalog_meta = _CURATED_MAP.get(code, {})
        try:
            resp = self.session.post(
                TEFAS_FUND_INFO_URL,
                json={"fonKodu": code, "dil": "TR"},
                headers=self._headers(),
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("resultList") or []
                if items and isinstance(items[0], dict):
                    raw = items[0]
                    record: Dict[str, Any] = {
                        "code": str(raw.get("fonKodu") or code).upper(),
                        "title": str(raw.get("fonUnvan") or catalog_meta.get("default_title") or code),
                        "category": str(raw.get("fonKategori") or ""),
                        "bucket": catalog_meta.get("bucket", "diger"),
                        "global_proxy": catalog_meta.get("global_proxy", ""),
                        "price_try": _opt_float(raw.get("sonFiyat")),
                        "daily_return_pct": _opt_float(raw.get("gunlukGetiri")),
                        "fund_size_try": _opt_float(raw.get("portBuyukluk")),
                        "investors": _opt_int(raw.get("yatirimciSayi")),
                        "category_rank": _opt_int(raw.get("kategoriDerece")),
                        "category_total": _opt_int(raw.get("kategoriFonSay")),
                        "market_share_pct": _opt_float(raw.get("pazarPayi")),
                        "source": "tefas_live",
                    }
                    # Merge into cache file
                    existing = self._read_cache()
                    existing[code] = record
                    self._write_cache(existing)
                    return record
        except Exception as exc:
            logger.warning("[tefas-fetcher] request failed for %s: %s", code, exc)

        return {
            "code": code,
            "title": catalog_meta.get("default_title", code),
            "category": "",
            "bucket": catalog_meta.get("bucket", "diger"),
            "global_proxy": catalog_meta.get("global_proxy", ""),
            "price_try": None,
            "daily_return_pct": None,
            "fund_size_try": None,
            "investors": None,
            "category_rank": None,
            "category_total": None,
            "market_share_pct": None,
            "source": "curated_fallback",
        }

    def fetch_curated_funds(
        self,
        *,
        bucket: Optional[str] = None,
        codes: Optional[Sequence[str]] = None,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """Fetch curated TEFAS benchmark funds (or explicit codes), cached 6 hours."""
        target_codes: List[str]
        if codes:
            target_codes = [str(c).strip().upper() for c in codes if str(c).strip()]
        else:
            target_codes = [
                item["code"]
                for item in CURATED_TEFAS_CATALOG
                if not bucket or item["bucket"] == bucket
            ]

        cached_map = {} if force_refresh else self._read_cache()
        results: List[Dict[str, Any]] = []
        updated_cache = dict(cached_map)
        cache_dirty = False

        for code in target_codes:
            if not force_refresh and code in cached_map:
                row = dict(cached_map[code])
                row["source"] = "tefas_cached"
                results.append(row)
                continue

            row = self.fetch_fund_info(code, force_refresh=force_refresh)
            results.append(row)
            if row.get("source") == "tefas_live":
                updated_cache[code] = row
                cache_dirty = True

        if cache_dirty:
            self._write_cache(updated_cache)
        return results
