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


def load_universe_closes(
    universe_name: str,
    tickers: Sequence[str],
    *,
    start_date: str = "2016-01-01",
    cache_dir: Optional[Path] = None,
    cache_ttl_hours: float = DEFAULT_CACHE_TTL_HOURS,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Download or load cached adjusted daily closes for a symbol universe."""
    target_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    cache_path = target_dir / f"closes_{universe_name}.csv"

    if not force_refresh and cache_path.is_file():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600.0
        if age_hours <= cache_ttl_hours:
            try:
                cached = pd.read_csv(cache_path, index_col=0, parse_dates=True)
                cached.columns = [str(c).upper() for c in cached.columns]
                if not cached.empty and len(cached) >= 100:
                    return cached.sort_index()
            except Exception as exc:  # noqa: BLE001
                logger.debug("[quant] cache read failed for %s: %s", universe_name, exc)

    unique_tickers = list(dict.fromkeys(str(t).strip().upper() for t in tickers if str(t).strip()))
    if not unique_tickers:
        return pd.DataFrame()

    import yfinance as yf

    raw = yf.download(
        tickers=unique_tickers,
        start=start_date,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    closes = _extract_close_frame(raw, unique_tickers)
    if closes.empty and cache_path.is_file():
        # Fail-open to stale cache if Yahoo Finance is temporarily unavailable
        try:
            return pd.read_csv(cache_path, index_col=0, parse_dates=True).sort_index()
        except Exception:  # noqa: BLE001
            return pd.DataFrame()

    if not closes.empty:
        try:
            closes.to_csv(cache_path)
        except OSError as exc:
            logger.debug("[quant] cache write failed for %s: %s", universe_name, exc)

    return closes


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
