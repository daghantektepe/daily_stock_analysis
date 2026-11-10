# -*- coding: utf-8 -*-
"""Daily Borsa Istanbul (~800 stocks) screener: technical setup + volume surge + KAP catalyst.

Instead of analyzing a fixed 5-stock list every day, the screener scans the BIST
universe and selects the top ``top_n`` (typically 5–10) candidates for deep LLM
analysis, saving CLI/API quota while surfacing stocks with fresh catalysts or
technical setups:

1. **Technical setup**: trend alignment (``close > MA5 > MA20``), tight entry near
   ``MA5``, 20-day breakout, constructive RSI(14) momentum (52–68) or oversold
   reversal (<35 with positive bounce), with an anti-chase penalty near the +10%
   BIST daily ceiling (``tavan``).
2. **Volume surge**: latest volume vs prior 20-day average volume (``>= 1.5x``),
   plus a minimum daily turnover filter (default 5M TRY) to skip illiquid names.
3. **New KAP disclosure**: a single market-wide KAP query for the last 2 days
   boosts stocks with new contract, buyback, bonus issue, dividend or earnings
   filings and penalizes circuit-breaker / regulatory measure notices.

Fail-open: network errors return an empty selection so callers can fall back to
``STOCK_LIST``.
"""

from __future__ import annotations

import csv
import logging
import math
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from src.services.kap_watch_service import _TAG_LABELS_TR
from src.services.market_symbol_utils import is_tr_suffix_symbol

logger = logging.getLogger(__name__)

DEFAULT_SEED_CSV = Path(__file__).resolve().parents[2] / "scripts" / "stock_index_seeds" / "stock_list_tr.csv"
DEFAULT_TOP_N = 8
DEFAULT_MIN_SCORE = 25.0
DEFAULT_MIN_TURNOVER_TRY = 5_000_000.0
DEFAULT_KAP_DAYS = 2

CATALYST_KAP_TAGS = frozenset({"contract", "buyback", "bonus_issue", "dividend", "earnings"})
SECONDARY_KAP_TAGS = frozenset({"ownership", "rating"})
PENALTY_KAP_TAGS = frozenset({"circuit_breaker", "regulatory", "rights_issue"})

BarsProvider = Callable[[Sequence[str]], Dict[str, List[Dict[str, Any]]]]


def load_bist_universe(
    *,
    seed_path: Optional[Path] = None,
    kap_fetcher: Any = None,
) -> List[Dict[str, str]]:
    """Return ``[{"symbol": "THYAO.IS", "name": "Türk Hava Yolları A.O."}, ...]``."""
    target = Path(seed_path or DEFAULT_SEED_CSV)
    rows: List[Dict[str, str]] = []
    seen = set()
    if target.exists():
        try:
            with open(target, "r", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    symbol = str(row.get("symbol") or row.get("ts_code") or "").strip().upper()
                    if not symbol or not is_tr_suffix_symbol(symbol) or symbol in seen:
                        continue
                    seen.add(symbol)
                    rows.append({"symbol": symbol, "name": str(row.get("name") or symbol).strip()})
        except OSError as exc:
            logger.info("[bist-screener] seed CSV read failed: %s", exc)
    if rows:
        return rows

    try:
        if kap_fetcher is None:
            from data_provider.kap_fetcher import KapDisclosureFetcher

            kap_fetcher = KapDisclosureFetcher()
        table = kap_fetcher._company_table()
        for ticker in sorted(table):
            symbol = f"{ticker}.IS"
            if symbol not in seen:
                seen.add(symbol)
                rows.append({"symbol": symbol, "name": str(table[ticker].get("title") or symbol).strip()})
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.info("[bist-screener] KAP universe fallback failed: %s", exc)
    return rows


def yfinance_batch_bars(
    symbols: Sequence[str],
    *,
    period: str = "3mo",
    chunk_size: int = 100,
) -> Dict[str, List[Dict[str, Any]]]:
    """Download daily OHLCV bars in batches from Yahoo Finance (fail-open per batch)."""
    clean_symbols = [str(s).strip().upper() for s in symbols if str(s or "").strip()]
    if not clean_symbols:
        return {}
    try:
        import yfinance as yf
    except ImportError:
        return {}

    out: Dict[str, List[Dict[str, Any]]] = {}
    step = max(1, int(chunk_size))
    for offset in range(0, len(clean_symbols), step):
        chunk = clean_symbols[offset : offset + step]
        try:
            frame = yf.download(
                tickers=chunk,
                period=period,
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
        except Exception as exc:  # noqa: BLE001 - fail-open per batch
            logger.info("[bist-screener] yfinance batch failed offset=%d: %s", offset, exc)
            continue
        if frame is None or getattr(frame, "empty", True):
            continue
        for symbol in chunk:
            try:
                sub = frame[symbol] if len(chunk) > 1 or symbol in getattr(frame, "columns", []) else frame
            except KeyError:
                continue
            bars: List[Dict[str, Any]] = []
            for idx, row in sub.iterrows():
                close = _finite_float(row.get("Close"))
                high = _finite_float(row.get("High")) or close
                low = _finite_float(row.get("Low")) or close
                volume = _finite_float(row.get("Volume"), allow_zero=True)
                if close is None or volume is None:
                    continue
                bars.append({
                    "date": idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10],
                    "close": close,
                    "high": high if high is not None else close,
                    "low": low if low is not None else close,
                    "volume": volume,
                })
            if bars:
                out[symbol] = bars
    return out


def _finite_float(value: Any, *, allow_zero: bool = False) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if allow_zero:
        return number if number >= 0 else None
    return number if number > 0 else None


def _compute_rsi(closes: Sequence[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    window = closes[-(period + 1) :]
    gains = 0.0
    losses = 0.0
    for prev, curr in zip(window, window[1:]):
        diff = curr - prev
        if diff > 0:
            gains += diff
        elif diff < 0:
            losses += -diff
    if losses <= 1e-12:
        return 100.0 if gains > 0 else 50.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))


def score_bist_candidate(
    stock_code: str,
    bars: Sequence[Dict[str, Any]],
    *,
    stock_name: Optional[str] = None,
    kap_items: Optional[Sequence[Dict[str, Any]]] = None,
    min_turnover_try: float = DEFAULT_MIN_TURNOVER_TRY,
) -> Optional[Dict[str, Any]]:
    """Score one BIST stock on technical setup, volume surge and recent KAP disclosures."""
    code = str(stock_code or "").strip().upper()
    if not is_tr_suffix_symbol(code) or len(bars) < 21:
        return None
    closes = [_finite_float(bar.get("close")) for bar in bars]
    highs = [_finite_float(bar.get("high")) or _finite_float(bar.get("close")) for bar in bars]
    volumes = [_finite_float(bar.get("volume"), allow_zero=True) for bar in bars]
    if any(c is None for c in closes[-21:]) or any(v is None for v in volumes[-21:]):
        return None

    last_close = float(closes[-1])
    prev_close = float(closes[-2])
    last_volume = float(volumes[-1])
    if last_close <= 0 or prev_close <= 0 or last_volume <= 0:
        return None

    daily_return_pct = (last_close / prev_close - 1.0) * 100.0
    turnover_try = last_close * last_volume
    prior_volumes = [float(v) for v in volumes[-21:-1] if v is not None and v > 0]
    if not prior_volumes:
        return None
    avg_volume_20d = sum(prior_volumes) / len(prior_volumes)
    volume_ratio = last_volume / avg_volume_20d if avg_volume_20d > 0 else 1.0

    ma5 = sum(float(c) for c in closes[-5:]) / 5.0
    ma20 = sum(float(c) for c in closes[-20:]) / 20.0
    high_20d_prev = max(float(h) for h in highs[-21:-1] if h is not None)
    rsi14 = _compute_rsi([float(c) for c in closes[-20:]], period=14)

    kap_tags: List[str] = []
    kap_titles: List[str] = []
    for item in kap_items or []:
        title = str(item.get("title") or "").strip()
        if title and title not in kap_titles:
            kap_titles.append(title)
        for tag in item.get("tags") or []:
            if tag not in kap_tags:
                kap_tags.append(tag)

    has_catalyst_kap = bool(CATALYST_KAP_TAGS.intersection(kap_tags))
    if turnover_try < float(min_turnover_try) and not has_catalyst_kap:
        return None

    score = 0.0
    reasons: List[str] = []

    # 1. KAP disclosure catalyst / penalty
    catalyst_hits = [tag for tag in kap_tags if tag in CATALYST_KAP_TAGS]
    secondary_hits = [tag for tag in kap_tags if tag in SECONDARY_KAP_TAGS]
    penalty_hits = [tag for tag in kap_tags if tag in PENALTY_KAP_TAGS]
    if catalyst_hits:
        score += 30.0
        labels = ", ".join(_TAG_LABELS_TR.get(t, t) for t in catalyst_hits)
        reasons.append(f"yeni KAP: {labels}")
    elif secondary_hits:
        score += 15.0
        labels = ", ".join(_TAG_LABELS_TR.get(t, t) for t in secondary_hits)
        reasons.append(f"KAP: {labels}")
    if penalty_hits:
        score -= 25.0
        labels = ", ".join(_TAG_LABELS_TR.get(t, t) for t in penalty_hits)
        reasons.append(f"KAP uyarısı: {labels}")

    # 2. Volume surge (only rewarded on non-negative price action)
    if volume_ratio >= 1.5 and daily_return_pct >= 0.0:
        vol_pts = min(30.0, round((volume_ratio - 1.0) * 15.0, 1))
        score += vol_pts
        reasons.append(f"hacim {volume_ratio:.1f}x")

    # 3. Technical setup
    ma5_dist_pct = (last_close - ma5) / ma5 * 100.0 if ma5 > 0 else 0.0
    if last_close > ma5 > ma20:
        score += 20.0
        reasons.append("MA5>MA20 trend")
        if 0.0 <= ma5_dist_pct <= 3.5:
            score += 10.0
            reasons.append("MA5 yakın kurulum")

    if last_close >= high_20d_prev and volume_ratio >= 1.2 and daily_return_pct > 0:
        score += 20.0
        reasons.append("20g zirve kırılımı")

    if rsi14 is not None:
        if 52.0 <= rsi14 <= 68.0 and last_close > ma20:
            score += 10.0
            reasons.append(f"RSI {rsi14:.0f} momentum")
        elif rsi14 < 35.0 and daily_return_pct >= 1.0 and volume_ratio >= 1.2:
            score += 20.0
            reasons.append(f"aşırı satımdan dönüş (RSI {rsi14:.0f})")

    # Anti-chase guard: avoid stocks already locked near BIST +10% ceiling or far above MA5.
    if daily_return_pct >= 8.5 or ma5_dist_pct > 12.0:
        score -= 25.0
        reasons.append("aşırı uzama/tavan riski")

    return {
        "stock_code": code,
        "stock_name": (stock_name or code).strip(),
        "score": round(score, 1),
        "close": round(last_close, 4),
        "daily_return_pct": round(daily_return_pct, 2),
        "volume_ratio": round(volume_ratio, 2),
        "turnover_try": round(turnover_try, 2),
        "ma5": round(ma5, 4),
        "ma20": round(ma20, 4),
        "rsi14": round(rsi14, 1) if rsi14 is not None else None,
        "kap_tags": kap_tags,
        "kap_titles": kap_titles[:2],
        "reasons": reasons,
    }


def screen_bist_stocks(
    *,
    universe: Optional[Sequence[Dict[str, str]]] = None,
    top_n: int = DEFAULT_TOP_N,
    min_score: float = DEFAULT_MIN_SCORE,
    min_turnover_try: float = DEFAULT_MIN_TURNOVER_TRY,
    kap_days: int = DEFAULT_KAP_DAYS,
    include_kap: bool = True,
    bars_provider: BarsProvider = yfinance_batch_bars,
    kap_fetcher: Any = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Scan BIST stocks and return the top ``top_n`` candidates sorted by score."""
    entries = list(universe) if universe is not None else load_bist_universe(kap_fetcher=kap_fetcher)
    symbols = [entry["symbol"] for entry in entries if entry.get("symbol")]
    name_map = {entry["symbol"]: entry.get("name") or entry["symbol"] for entry in entries if entry.get("symbol")}

    kap_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    if include_kap and symbols:
        try:
            if kap_fetcher is None:
                from data_provider.kap_fetcher import get_kap_fetcher

                kap_fetcher = get_kap_fetcher()
            kap_by_symbol = kap_fetcher.get_market_disclosures(days=kap_days, today=today) or {}
        except Exception as exc:  # noqa: BLE001 - fail-open
            logger.info("[bist-screener] KAP market disclosures unavailable: %s", exc)
            kap_by_symbol = {}

    try:
        bars_by_symbol = bars_provider(symbols) if symbols else {}
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.info("[bist-screener] bars provider failed: %s", exc)
        bars_by_symbol = {}

    qualified: List[Dict[str, Any]] = []
    evaluated_count = 0
    for symbol in symbols:
        bars = bars_by_symbol.get(symbol)
        if not bars:
            continue
        evaluated_count += 1
        candidate = score_bist_candidate(
            symbol,
            bars,
            stock_name=name_map.get(symbol, symbol),
            kap_items=kap_by_symbol.get(symbol),
            min_turnover_try=min_turnover_try,
        )
        if candidate is None:
            continue
        if candidate["score"] >= float(min_score) and candidate["reasons"]:
            qualified.append(candidate)

    qualified.sort(key=lambda item: (-item["score"], -item["turnover_try"], item["stock_code"]))
    safe_top = max(1, int(top_n))
    selected = qualified[:safe_top]
    return {
        "universe_count": len(symbols),
        "evaluated_count": evaluated_count,
        "qualified_count": len(qualified),
        "top_n": safe_top,
        "selected_codes": [item["stock_code"] for item in selected],
        "candidates": selected,
    }


def format_bist_screener_report(result: Dict[str, Any]) -> str:
    """Plain-text (Turkish) summary of the daily BIST screener selection."""
    candidates = result.get("candidates") or []
    lines = [
        f"🔍 BIST Günlük Tarama Özeti (evren: {result.get('universe_count', 0)}, "
        f"veri alınan: {result.get('evaluated_count', 0)}, "
        f"eşik üstü: {result.get('qualified_count', 0)}, seçilen: {len(candidates)})"
    ]
    if not candidates:
        lines.append("Eşiği geçen aday bulunamadı.")
        return "\n".join(lines)
    for rank, item in enumerate(candidates, start=1):
        reasons = ", ".join(item.get("reasons") or [])
        lines.append(
            f"{rank}. {item['stock_code']} ({item.get('stock_name', '')}) — puan {item['score']:.0f} | "
            f"kapanış {item['close']:,.2f} ({item['daily_return_pct']:+.2f}%) | "
            f"hacim {item['volume_ratio']:.1f}x | {reasons}"
        )
        for kap_title in item.get("kap_titles") or []:
            lines.append(f"   KAP: {kap_title}")
    lines.append("Not: Tarama yalnızca derin analiz adaylarını seçer; yatırım tavsiyesi değildir.")
    return "\n".join(lines)


__all__ = [
    "CATALYST_KAP_TAGS",
    "DEFAULT_KAP_DAYS",
    "DEFAULT_MIN_SCORE",
    "DEFAULT_MIN_TURNOVER_TRY",
    "DEFAULT_TOP_N",
    "PENALTY_KAP_TAGS",
    "SECONDARY_KAP_TAGS",
    "format_bist_screener_report",
    "load_bist_universe",
    "score_bist_candidate",
    "screen_bist_stocks",
    "yfinance_batch_bars",
]

