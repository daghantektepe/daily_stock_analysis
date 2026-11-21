# -*- coding: utf-8 -*-
"""Orchestrator for daily PAA & Meta-Portfolio A StrategyPaperBook ledgers.

Bridges ``src/quant/strategies/library.py`` (``compute_paa_weights`` &
``compute_meta_a_weights``) with ``QuantAllocationPaperBook`` so both strategies
advance automatically on completed daily closes and persist JSON ledgers under
``data/strategy_paper/quant_<key>.json`` (strictly simulated; never real orders).
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd

from src.quant.data_loader import MACRO_V3_UNIVERSE, US_ETF_UNIVERSE, load_universe_closes
from src.quant.strategies.library import compute_meta_a_weights, compute_paa_weights
from src.quant.strategies.research_v3 import compute_v3_trend_risk_parity_bil_weights
from src.services.strategy_paper_book import (
    DEFAULT_BOOK_DIR,
    QuantAllocationPaperBook,
    format_quant_book_report,
)

logger = logging.getLogger(__name__)

QUANT_PAPER_SPECS: Dict[str, Dict[str, Any]] = {
    "paa": {
        "name": "quant_paa",
        "strategy_key": "paa",
        "strategy_id": "PROTECTIVE_ASSET_ALLOCATION_PAA",
        "label": "PAA Çöküş Kalkanı (US ETF)",
        "benchmark_symbol": "SPY",
        "weight_fn": compute_paa_weights,
    },
    "meta_a": {
        "name": "quant_meta_a",
        "strategy_key": "meta_a",
        "strategy_id": "META_US_ETF_ALL_WEATHER",
        "label": "Meta-Portföy A (ABD Ortogonal ETF Ensemble)",
        "benchmark_symbol": "SPY",
        "weight_fn": compute_meta_a_weights,
    },
    "v3_trp": {
        "name": "quant_v3_trp",
        "strategy_key": "v3_trp",
        "strategy_id": "V3_TREND_RISK_PARITY_BIL",
        "label": "v3 Vol-Yönetimli Trend-Frenli Risk Paritesi (BIL)",
        "benchmark_symbol": "SPY",
        "weight_fn": compute_v3_trend_risk_parity_bil_weights,
        "requires_macro_v3": True,
    },
}

DEFAULT_QUANT_PAPER_STRATEGIES = ("paa", "meta_a")


def normalize_quant_paper_strategies(raw: Optional[Sequence[str]]) -> List[str]:
    """Filter and deduplicate configured strategy keys, falling back to ``['paa', 'meta_a']``."""
    out: List[str] = []
    for item in raw or DEFAULT_QUANT_PAPER_STRATEGIES:
        key = str(item or "").strip().lower()
        if key in ("all", "*"):
            for valid in DEFAULT_QUANT_PAPER_STRATEGIES:
                if valid not in out:
                    out.append(valid)
            continue
        if key in QUANT_PAPER_SPECS and key not in out:
            out.append(key)
    return out or list(DEFAULT_QUANT_PAPER_STRATEGIES)


def build_quant_paper_book(
    strategy_key: str,
    *,
    initial_capital: float = 10_000.0,
    cost_bps: float = 5.0,
    rebalance_mode: str = "monthly",
    rebalance_band_pct: float = 1.0,
    book_dir: Optional[Path] = None,
) -> tuple[QuantAllocationPaperBook, Callable[[pd.DataFrame], pd.DataFrame]]:
    key = strategy_key.strip().lower()
    if key not in QUANT_PAPER_SPECS:
        raise ValueError(f"Unsupported quant paper strategy: {strategy_key!r}")
    spec = QUANT_PAPER_SPECS[key]
    book = QuantAllocationPaperBook(
        name=spec["name"],
        strategy_key=spec["strategy_key"],
        strategy_id=spec["strategy_id"],
        label=spec["label"],
        benchmark_symbol=spec["benchmark_symbol"],
        initial_capital=initial_capital,
        cost_bps=cost_bps,
        rebalance_mode=rebalance_mode,
        rebalance_band_pct=rebalance_band_pct,
        book_dir=book_dir or DEFAULT_BOOK_DIR,
    )
    return book, spec["weight_fn"]


def load_quant_paper_prices(
    *,
    force_refresh: bool = False,
    start_date: str = "2018-01-01",
    cache_dir: Optional[Path] = None,
    include_macro_v3: bool = False,
) -> pd.DataFrame:
    """Load completed daily closes for the US ETF universe (drops today's unfinished bar)."""
    frame = load_universe_closes(
        "us_etf",
        US_ETF_UNIVERSE,
        start_date=start_date,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
    )
    if include_macro_v3:
        macro_frame = load_universe_closes(
            "macro_v3",
            MACRO_V3_UNIVERSE,
            start_date=start_date,
            cache_dir=cache_dir,
            force_refresh=force_refresh,
        )
        if macro_frame is not None and not macro_frame.empty:
            if frame is None or frame.empty:
                frame = macro_frame
            else:
                extra = [c for c in macro_frame.columns if c not in frame.columns]
                if extra:
                    frame = frame.join(macro_frame[extra], how="outer").sort_index().ffill()
    if frame is None or frame.empty:
        return pd.DataFrame()
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    completed = frame[frame.index < today]
    return completed if not completed.empty else frame


def step_quant_paper_books(
    *,
    strategies: Optional[Sequence[str]] = None,
    initial_capital: float = 10_000.0,
    cost_bps: float = 5.0,
    rebalance_mode: str = "monthly",
    rebalance_band_pct: float = 1.0,
    force_rebalance: bool = False,
    force_refresh_prices: bool = False,
    prices: Optional[pd.DataFrame] = None,
    book_dir: Optional[Path] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Advance all requested quant StrategyPaperBooks (PAA / Meta-Portfolio A / v3) to the latest completed close."""
    keys = normalize_quant_paper_strategies(strategies)
    needs_macro_v3 = any(bool(QUANT_PAPER_SPECS.get(k, {}).get("requires_macro_v3")) for k in keys)
    price_frame = (
        prices
        if prices is not None
        else load_quant_paper_prices(force_refresh=force_refresh_prices, include_macro_v3=needs_macro_v3)
    )
    if price_frame is None or price_frame.empty:
        return {
            "ok": False,
            "simulated_only": True,
            "error": "US ETF fiyat verisi yüklenemedi.",
            "books": [],
            "total_new_trades": 0,
            "report_text": "",
        }

    books_out: List[Dict[str, Any]] = []
    reports: List[str] = []
    total_new_trades = 0

    for key in keys:
        book, weight_fn = build_quant_paper_book(
            key,
            initial_capital=initial_capital,
            cost_bps=cost_bps,
            rebalance_mode=rebalance_mode,
            rebalance_band_pct=rebalance_band_pct,
            book_dir=book_dir,
        )
        step_res = book.step(price_frame, weight_fn, today=today, force_rebalance=force_rebalance)
        summary = book.summary()
        report = format_quant_book_report(summary)
        summary["processed_days"] = int(step_res.get("processed_days") or 0)
        summary["new_trades"] = list(step_res.get("new_trades") or [])
        summary["report_text"] = report
        books_out.append(summary)
        reports.append(report)
        total_new_trades += len(summary["new_trades"])

    # Also advance any active 3-AI Council StrategyPaperBooks (Claude / Codex / Gemini)
    try:
        from src.quant.ai_council import load_council_etf_prices, step_active_council_books

        council_prices = prices if prices is not None else load_council_etf_prices(force_refresh=force_refresh_prices)
        council_books = step_active_council_books(
            prices=council_prices,
            initial_capital=initial_capital,
            cost_bps=cost_bps,
            force_rebalance=force_rebalance,
            book_dir=book_dir,
            today=today,
        )
        for cb in council_books:
            books_out.append(cb)
            if cb.get("report_text"):
                reports.append(cb["report_text"])
            total_new_trades += len(cb.get("new_trades") or [])
    except Exception as exc:
        logger.warning("[quant-paper] AI council step skipped: %s", exc)

    # Forward validation gate: freezes PAA / Meta-A on first run, then counts only later days.
    forward: List[Dict[str, Any]] = []
    try:
        from src.quant.forward_validation import format_forward_report, run_forward_validation

        forward = run_forward_validation(
            strategies=keys,
            prices=price_frame,
            book_dir=book_dir,
            paper_settings={
                "initial_capital": initial_capital,
                "cost_bps": cost_bps,
                "rebalance_mode": rebalance_mode,
                "rebalance_band_pct": rebalance_band_pct,
            },
            today=today,
        )
        reports.append(format_forward_report(forward))
    except Exception as exc:  # noqa: BLE001 - validation report is optional, books already stepped
        logger.warning("[quant-paper] forward validation skipped: %s", exc)

    return {
        "ok": True,
        "simulated_only": True,
        "strategies": [b["strategy_key"] for b in books_out],
        "total_new_trades": total_new_trades,
        "books": books_out,
        "forward_validation": forward,
        "report_text": "\n\n".join(reports),
    }


def get_quant_paper_books_status(
    *,
    strategies: Optional[Sequence[str]] = None,
    initial_capital: float = 10_000.0,
    cost_bps: float = 5.0,
    rebalance_mode: str = "monthly",
    auto_step_if_empty: bool = False,
    book_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read persisted PAA / Meta-Portfolio A StrategyPaperBooks without network I/O (unless auto_step_if_empty)."""
    keys = normalize_quant_paper_strategies(strategies)
    books_out: List[Dict[str, Any]] = []
    reports: List[str] = []
    needs_init = False

    for key in keys:
        book, _ = build_quant_paper_book(
            key,
            initial_capital=initial_capital,
            cost_bps=cost_bps,
            rebalance_mode=rebalance_mode,
            book_dir=book_dir,
        )
        summary = book.summary()
        if not summary.get("days"):
            needs_init = True
        report = format_quant_book_report(summary)
        summary["processed_days"] = 0
        summary["new_trades"] = []
        summary["report_text"] = report
        books_out.append(summary)
        reports.append(report)

    if auto_step_if_empty and needs_init:
        try:
            return step_quant_paper_books(
                strategies=keys,
                initial_capital=initial_capital,
                cost_bps=cost_bps,
                rebalance_mode=rebalance_mode,
                book_dir=book_dir,
            )
        except Exception as exc:
            logger.warning("[quant-paper] auto_step_if_empty failed: %s", exc)

    # Also include active 3-AI Council StrategyPaperBooks (Claude / Codex / Gemini)
    try:
        from src.quant.ai_council import get_active_council_books_status

        for cb in get_active_council_books_status(
            initial_capital=initial_capital,
            cost_bps=cost_bps,
            book_dir=book_dir,
        ):
            books_out.append(cb)
            if cb.get("report_text"):
                reports.append(cb["report_text"])
    except Exception as exc:
        logger.warning("[quant-paper] AI council status read skipped: %s", exc)

    return {
        "ok": True,
        "simulated_only": True,
        "strategies": [b["strategy_key"] for b in books_out],
        "total_new_trades": 0,
        "books": books_out,
        "report_text": "\n\n".join(reports),
    }
