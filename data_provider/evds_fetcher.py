# -*- coding: utf-8 -*-
"""TCMB EVDS2 Turkish macro & inflation fetcher (``TP.DK.USD.S.YTL`` + ``TP.FG.J0``).

Behavior:
- When ``EVDS_API_KEY`` is configured, calls the official TCMB EVDS2 JSON service
  sending the key strictly in HTTP headers (``headers={"key": api_key}`` as
  required by TCMB's April 2024+ authentication update) with a 12-hour disk
  TTL cache in ``data/cache/evds_macro.json``.
- When ``EVDS_API_KEY`` is missing or EVDS is temporarily unreachable, degrades
  gracefully by fetching ``USD/TRY`` from Yahoo Finance (``TRY=X``) and marking
  TÜFE inflation honestly as ``source="unavailable"`` instead of fabricating
  stale hardcoded rates.
- Also provides ``compute_real_purchase_power_tr(...)`` to compare nominal TRY
  returns vs USD-adjusted returns vs TÜFE-adjusted real purchasing power.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

EVDS_BASE_URL = "https://evds2.tcmb.gov.tr/service/evds"
USD_TRY_SERIES = "TP.DK.USD.S.YTL"
CPI_INDEX_SERIES = "TP.FG.J0"  # TÜFE Genel Endeks (2003=100)
_DEFAULT_CACHE_PATH = Path("data/cache/evds_macro.json")


def _safe_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    if isinstance(val, str):
        val = val.replace(",", ".").strip()
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if num != num:  # NaN check
        return None
    return num


def _format_evds_date(dt: datetime) -> str:
    return dt.strftime("%d-%m-%Y")


def compute_real_purchase_power_tr(
    *,
    nominal_return_pct: float,
    usd_try_change_pct: Optional[float],
    cpi_yoy_pct: Optional[float],
) -> Dict[str, Any]:
    """Convert a nominal TRY return into USD-based return and TÜFE real return.

    Formulae (exact Fisher / FX parity):
    - ``real_return_tufe_pct = ((1 + R_try) / (1 + CPI_yoy) - 1) * 100``
    - ``usd_return_pct       = ((1 + R_try) / (1 + dFX) - 1) * 100``
    """
    r = float(nominal_return_pct) / 100.0
    usd_ret: Optional[float] = None
    if usd_try_change_pct is not None and (1.0 + usd_try_change_pct / 100.0) > 0:
        fx = float(usd_try_change_pct) / 100.0
        usd_ret = round((((1.0 + r) / (1.0 + fx)) - 1.0) * 100.0, 2)

    real_ret: Optional[float] = None
    beats_inflation: Optional[bool] = None
    if cpi_yoy_pct is not None and (1.0 + cpi_yoy_pct / 100.0) > 0:
        cpi = float(cpi_yoy_pct) / 100.0
        real_ret = round((((1.0 + r) / (1.0 + cpi)) - 1.0) * 100.0, 2)
        beats_inflation = real_ret > 0

    return {
        "nominal_return_pct": round(float(nominal_return_pct), 2),
        "usd_based_return_pct": usd_ret,
        "real_tufe_return_pct": real_ret,
        "beats_inflation": beats_inflation,
    }


class EvdsMacroFetcher:
    """TCMB EVDS2 macro fetcher with 12h disk TTL cache and ``TRY=X`` fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        cache_path: Optional[Path] = None,
        cache_ttl_seconds: int = 12 * 3600,
        timeout: float = 12.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = (api_key or "").strip() or None
        self.cache_path = Path(cache_path) if cache_path is not None else _DEFAULT_CACHE_PATH
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))
        self.timeout = float(timeout)
        self.session = session or requests.Session()

    @classmethod
    def from_config(cls, config: Any = None) -> "EvdsMacroFetcher":
        if config is None:
            from src.config import get_config

            config = get_config()
        return cls(api_key=getattr(config, "evds_api_key", None))

    def _read_cache(self) -> Optional[Dict[str, Any]]:
        if self.cache_ttl_seconds <= 0 or not self.cache_path.exists():
            return None
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            fetched_at = float(payload.get("fetched_at", 0))
            if (time.time() - fetched_at) > self.cache_ttl_seconds:
                return None
            data = payload.get("snapshot")
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _write_cache(self, snapshot: Dict[str, Any]) -> None:
        if self.cache_ttl_seconds <= 0:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps({"fetched_at": time.time(), "snapshot": snapshot}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("[evds-fetcher] cache write skipped: %s", exc)

    def _fetch_evds_series(self, series_code: str, *, days_back: int = 430) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=days_back)
        url = (
            f"{EVDS_BASE_URL}/series={series_code}"
            f"&startDate={_format_evds_date(start_dt)}"
            f"&endDate={_format_evds_date(end_dt)}"
            f"&type=json"
        )
        try:
            resp = self.session.get(
                url,
                headers={"key": self.api_key, "Accept": "application/json"},
                timeout=self.timeout,
            )
            if resp.status_code >= 400:
                logger.warning("[evds-fetcher] %s HTTP %s: %s", series_code, resp.status_code, resp.text[:200])
                return []
            payload = resp.json()
            items = payload.get("items")
            return items if isinstance(items, list) else []
        except Exception as exc:
            logger.warning("[evds-fetcher] request failed for %s: %s", series_code, exc)
            return []

    @staticmethod
    def _extract_usd_try_from_evds(items: List[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        col_key = USD_TRY_SERIES.replace(".", "_")
        valid: List[Tuple[str, float]] = []
        for row in items:
            raw_val = row.get(col_key) if col_key in row else row.get(USD_TRY_SERIES)
            val = _safe_float(raw_val)
            if val is not None and val > 0:
                valid.append((str(row.get("Tarih") or ""), val))
        if not valid:
            return None, None, None
        latest_date, latest_val = valid[-1]
        yoy_change_pct: Optional[float] = None
        if len(valid) >= 2:
            # Find value roughly 250 business days / earliest in ~365d window
            ref_val = valid[max(0, len(valid) - 252)][1]
            if ref_val > 0:
                yoy_change_pct = round(((latest_val / ref_val) - 1.0) * 100.0, 2)
        return round(latest_val, 4), yoy_change_pct, latest_date

    @staticmethod
    def _extract_cpi_yoy_from_evds(items: List[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        col_key = CPI_INDEX_SERIES.replace(".", "_")
        valid: List[Tuple[str, float]] = []
        for row in items:
            raw_val = row.get(col_key) if col_key in row else row.get(CPI_INDEX_SERIES)
            val = _safe_float(raw_val)
            if val is not None and val > 0:
                valid.append((str(row.get("Tarih") or ""), val))
        if len(valid) < 2:
            return None, None, None
        latest_date, latest_idx = valid[-1]
        prev_month_idx = valid[-2][1]
        mom_pct = round(((latest_idx / prev_month_idx) - 1.0) * 100.0, 2) if prev_month_idx > 0 else None
        yoy_pct: Optional[float] = None
        if len(valid) >= 13:
            year_ago_idx = valid[-13][1]
            if year_ago_idx > 0:
                yoy_pct = round(((latest_idx / year_ago_idx) - 1.0) * 100.0, 2)
        return yoy_pct, mom_pct, latest_date

    @staticmethod
    def _fetch_yahoo_usd_try() -> Tuple[Optional[float], Optional[float], Optional[str]]:
        try:
            import yfinance as yf

            hist = yf.Ticker("TRY=X").history(period="1y", auto_adjust=True)
            if hist is None or hist.empty:
                return None, None, None
            closes = hist["Close"].dropna()
            if closes.empty:
                return None, None, None
            latest = float(closes.iloc[-1])
            first = float(closes.iloc[0])
            yoy_pct = round(((latest / first) - 1.0) * 100.0, 2) if first > 0 else None
            latest_date = str(closes.index[-1])[:10]
            return round(latest, 4), yoy_pct, latest_date
        except Exception as exc:
            logger.debug("[evds-fetcher] TRY=X fallback failed: %s", exc)
            return None, None, None

    def get_macro_snapshot(self, *, force_refresh: bool = False) -> Dict[str, Any]:
        """Return USD/TRY + CPI inflation snapshot (EVDS primary, ``TRY=X`` fallback)."""
        if not force_refresh:
            cached = self._read_cache()
            if cached is not None:
                return dict(cached, cached=True)

        usd_try: Optional[float] = None
        usd_try_1y_change_pct: Optional[float] = None
        usd_date: Optional[str] = None
        usd_source = "unavailable"

        cpi_yoy_pct: Optional[float] = None
        cpi_mom_pct: Optional[float] = None
        cpi_date: Optional[str] = None
        cpi_source = "unavailable"

        if self.api_key:
            usd_items = self._fetch_evds_series(USD_TRY_SERIES, days_back=400)
            usd_try, usd_try_1y_change_pct, usd_date = self._extract_usd_try_from_evds(usd_items)
            if usd_try is not None:
                usd_source = "tcmb_evds2"

            cpi_items = self._fetch_evds_series(CPI_INDEX_SERIES, days_back=460)
            cpi_yoy_pct, cpi_mom_pct, cpi_date = self._extract_cpi_yoy_from_evds(cpi_items)
            if cpi_yoy_pct is not None or cpi_mom_pct is not None:
                cpi_source = "tcmb_evds2"

        if usd_try is None:
            usd_try, usd_try_1y_change_pct, usd_date = self._fetch_yahoo_usd_try()
            if usd_try is not None:
                usd_source = "yahoo_try_x_fallback"

        snapshot: Dict[str, Any] = {
            "evds_configured": bool(self.api_key),
            "usd_try": usd_try,
            "usd_try_1y_change_pct": usd_try_1y_change_pct,
            "usd_try_as_of": usd_date,
            "usd_try_source": usd_source,
            "cpi_yoy_pct": cpi_yoy_pct,
            "cpi_mom_pct": cpi_mom_pct,
            "cpi_as_of": cpi_date,
            "cpi_source": cpi_source,
            "cached": False,
        }
        if usd_try is not None or cpi_yoy_pct is not None:
            self._write_cache(snapshot)
        return snapshot
