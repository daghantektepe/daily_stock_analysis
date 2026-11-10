# -*- coding: utf-8 -*-
"""Read-only paper trading and KAP/news alert endpoints (simulated ledger, never real orders)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import get_database_manager
from api.v1.schemas.paper_trading import (
    KapAlertItem,
    KapAlertListResponse,
    PaperTradeListResponse,
    PaperTradingSummaryResponse,
)
from src.services.kap_watch_service import get_recent_kap_and_news_alerts
from src.services.paper_trading_benchmark import evaluate_signal_outcomes
from src.services.paper_trading_service import PaperTradingService
from src.storage import DatabaseManager

router = APIRouter()


@router.get("/summary", response_model=PaperTradingSummaryResponse)
def get_paper_trading_summary(
    benchmark: bool = Query(True, description="Add index-shadow and USD-based returns (BIST: BIST 100, USD/TRY)"),
    outcomes: bool = Query(False, description="Evaluate and include DecisionSignal 1/3/5/10d outcome hit rates"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> PaperTradingSummaryResponse:
    """Open positions, realized/unrealized P&L, win rate and benchmark comparison of the paper ledger."""
    payload = PaperTradingService(db_manager).get_summary(include_benchmarks=benchmark)
    if outcomes:
        payload["signal_outcomes"] = evaluate_signal_outcomes(db_manager=db_manager)
    return PaperTradingSummaryResponse(**payload)


@router.get("/trades", response_model=PaperTradeListResponse)
def list_paper_trades(
    limit: int = Query(200, ge=1, le=1000),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> PaperTradeListResponse:
    """Most recent simulated fills, newest first."""
    return PaperTradeListResponse(items=PaperTradingService(db_manager).list_trades(limit=limit))


@router.get("/kap-alerts", response_model=KapAlertListResponse)
def list_kap_and_news_alerts(
    limit: int = Query(30, ge=1, le=100),
    live: bool = Query(True, description="Fetch live KAP/news preview when watcher state has no recent alerts"),
) -> KapAlertListResponse:
    """Recent material KAP disclosures, multi-source confirmed news, and spreading rumor warnings."""
    items = get_recent_kap_and_news_alerts(live_fallback=live, max_items=limit)
    return KapAlertListResponse(items=[KapAlertItem(**item) for item in items])
