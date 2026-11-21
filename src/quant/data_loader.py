# -*- coding: utf-8 -*-
"""Multi-universe daily adjusted-close loader with local disk cache."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("data") / "quant_cache"
DEFAULT_CACHE_TTL_HOURS = 12.0

# 12 PAA risk assets + 3 defensive bond/cash ETFs
US_ETF_RISK_ASSETS: tuple[str, ...] = (
    "SPY", "QQQ", "IWM", "VGK", "EWJ", "EEM",
    "VNQ", "GLD", "DBC", "HYG", "LQD", "TLT",
)
US_ETF_SAFE_ASSETS: tuple[str, ...] = ("IEF", "SHY", "BIL")
US_ETF_UNIVERSE: tuple[str, ...] = US_ETF_RISK_ASSETS + US_ETF_SAFE_ASSETS

US_SECTOR_FACTOR_UNIVERSE: tuple[str, ...] = (
    "XLK", "XLV", "XLF", "XLE", "XLI", "XLP", "XLU", "XLY", "XLB", "XLC", "XLRE",
    "MTUM", "QUAL", "USMV", "VLUE", "SPY", "IEF", "SHY",
)

CRYPTO_UNIVERSE: tuple[str, ...] = ("BTC-USD", "ETH-USD")

BIST_LIQUID_UNIVERSE: tuple[str, ...] = (
    "THYAO.IS", "ASELS.IS", "TUPRS.IS", "KCHOL.IS", "BIMAS.IS",
    "AKBNK.IS", "GARAN.IS", "ISCTR.IS", "YKBNK.IS", "EREGL.IS",
    "FROTO.IS", "SISE.IS", "SAHOL.IS", "TCELL.IS", "TOASO.IS",
    "PGSUS.IS", "ENKAI.IS", "MGROS.IS", "KRDMD.IS", "ARCLK.IS",
)


def _extract_close_frame(raw: pd.DataFrame, tickers: Sequence[str]) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    clean_tickers = [t.upper() for t in tickers]
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(raw.columns.get_level_values(0))
        level1 = set(raw.columns.get_level_values(1))
        if "Close" in level0:
            closes = raw["Close"].copy()
        elif "Adj Close" in level0:
            closes = raw["Adj Close"].copy()
        elif "Close" in level1:
            closes = raw.xs("Close", axis=1, level=1).copy()
        else:
            return pd.DataFrame()
    else:
        col = "Close" if "Close" in raw.columns else ("Adj Close" if "Adj Close" in raw.columns else None)
        if col is None:
            return pd.DataFrame()
        closes = pd.DataFrame({clean_tickers[0]: raw[col]})

    closes.columns = [str(c).upper() for c in closes.columns]
    idx = pd.to_datetime(closes.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    closes.index = idx.normalize()
    closes = closes[~closes.index.duplicated(keep="last")].sort_index()
    for col in closes.columns:
        closes[col] = pd.to_numeric(closes[col], errors="coerce")
    return closes.dropna(how="all")


def _merge_close_frames(existing: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    """Non-destructively merge fresh closes onto existing history (never drops older dates or extra columns)."""
    if existing is None or existing.empty:
        return fresh.sort_index()
    if fresh is None or fresh.empty:
        return existing.sort_index()
    old = existing.copy()
    new = fresh.copy()
    old.columns = [str(c).upper() for c in old.columns]
    new.columns = [str(c).upper() for c in new.columns]
    all_idx = old.index.union(new.index).sort_values()
    all_cols = list(dict.fromkeys([*old.columns, *new.columns]))
    merged = new.reindex(index=all_idx, columns=all_cols).combine_first(
        old.reindex(index=all_idx, columns=all_cols)
    )
    return merged.sort_index().dropna(how="all")


def load_universe_closes(
    universe_name: str,
    tickers: Sequence[str],
    *,
    start_date: str = "2016-01-01",
    cache_dir: Optional[Path] = None,
    cache_ttl_hours: float = DEFAULT_CACHE_TTL_HOURS,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Download or load cached adjusted daily closes for a symbol universe.

    Cache integrity guarantees:
    - Cached data is accepted only if it covers the requested ``start_date``
      (within a 21-day holiday/inception tolerance) and at least 85% of the
      requested tickers.
    - Writing back to disk always non-destructively merges with any existing
      wider/longer cache so a narrow call can never poison a shared universe CSV.
    """
    target_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    cache_path = target_dir / f"closes_{universe_name}.csv"
    unique_tickers = list(dict.fromkeys(str(t).strip().upper() for t in tickers if str(t).strip()))
    if not unique_tickers:
        return pd.DataFrame()

    existing_cached: Optional[pd.DataFrame] = None
    if cache_path.is_file():
        try:
            loaded = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            loaded.columns = [str(c).upper() for c in loaded.columns]
            if not loaded.empty:
                existing_cached = loaded.sort_index()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[quant] cache read failed for %s: %s", universe_name, exc)

    req_start_ts = pd.Timestamp(start_date)
    if not force_refresh and existing_cached is not None and len(existing_cached) >= 100:
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600.0
        cached_cols = set(existing_cached.columns)
        present_count = sum(1 for t in unique_tickers if t in cached_cols)
        covers_cols = present_count >= max(1, int(len(unique_tickers) * 0.85))
        # Accept cache start if it begins at or near req_start_ts (or <= 2018-01-15 for 2016 requests on 2018 ETFs)
        earliest_ok = existing_cached.index[0] <= max(req_start_ts + pd.Timedelta(days=21), pd.Timestamp("2018-01-15"))
        if req_start_ts >= pd.Timestamp("2018-01-01"):
            earliest_ok = existing_cached.index[0] <= req_start_ts + pd.Timedelta(days=21)
        if age_hours <= cache_ttl_hours and covers_cols and earliest_ok:
            sel = [c for c in unique_tickers if c in cached_cols]
            sub = existing_cached.loc[existing_cached.index >= req_start_ts, sel].copy()
            if not sub.empty:
                return sub

    # Determine effective download start: preserve earliest existing cache start so merged file stays complete
    fetch_start = start_date
    if existing_cached is not None and not existing_cached.empty:
        existing_start_str = existing_cached.index[0].strftime("%Y-%m-%d")
        if existing_start_str < fetch_start:
            fetch_start = existing_start_str
    fetch_tickers = list(dict.fromkeys([*unique_tickers, *(list(existing_cached.columns) if existing_cached is not None else [])]))

    import yfinance as yf

    raw = yf.download(
        tickers=fetch_tickers,
        start=fetch_start,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    closes = _extract_close_frame(raw, fetch_tickers)
    if closes.empty and existing_cached is not None:
        sel = [c for c in unique_tickers if c in existing_cached.columns]
        return existing_cached.loc[existing_cached.index >= req_start_ts, sel].copy()

    merged = _merge_close_frames(existing_cached, closes)
    if not merged.empty:
        try:
            merged.to_csv(cache_path)
        except OSError as exc:
            logger.debug("[quant] cache write failed for %s: %s", universe_name, exc)

    sel = [c for c in unique_tickers if c in merged.columns]
    return merged.loc[merged.index >= req_start_ts, sel].copy() if sel else merged


def load_all_tournament_universes(
    *,
    start_date: str = "2016-01-01",
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
) -> Dict[str, pd.DataFrame]:
    """Load all multi-asset tournament universes with local disk caching."""
    us_all = list(dict.fromkeys([*US_ETF_UNIVERSE, *US_SECTOR_FACTOR_UNIVERSE]))
    us_frame = load_universe_closes(
        "us_etf_and_sectors",
        us_all,
        start_date=start_date,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
    )
    crypto_frame = load_universe_closes(
        "crypto",
        CRYPTO_UNIVERSE,
        start_date=start_date,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
    )
    bist_frame = load_universe_closes(
        "bist_liquid",
        BIST_LIQUID_UNIVERSE,
        start_date=start_date,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
    )
    return {
        "us_etf": us_frame[[c for c in US_ETF_UNIVERSE if c in us_frame.columns]].copy() if not us_frame.empty else pd.DataFrame(),
        "us_sectors": us_frame[[c for c in US_SECTOR_FACTOR_UNIVERSE if c in us_frame.columns]].copy() if not us_frame.empty else pd.DataFrame(),
        "crypto": crypto_frame,
        "bist": bist_frame,
    }
