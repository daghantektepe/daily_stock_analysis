# -*- coding: utf-8 -*-
"""Read-only paper trading endpoints (simulated ledger, never real orders)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import get_database_manager
from api.v1.schemas.paper_trading import PaperTradeListResponse, PaperTradingSummaryResponse
from src.services.paper_trading_service import PaperTradingService
from src.storage import DatabaseManager

router = APIRouter()


@router.get("/summary", response_model=PaperTradingSummaryResponse)
def get_paper_trading_summary(
    benchmark: bool = Query(True, description="Add index-shadow and USD-based returns (BIST: BIST 100, USD/TRY)"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> PaperTradingSummaryResponse:
    """Open positions, realized/unrealized P&L, win rate and benchmark comparison of the paper ledger."""
    return PaperTradingSummaryResponse(
        **PaperTradingService(db_manager).get_summary(include_benchmarks=benchmark)
    )


@router.get("/trades", response_model=PaperTradeListResponse)
def list_paper_trades(
    limit: int = Query(200, ge=1, le=1000),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> PaperTradeListResponse:
    """Most recent simulated fills, newest first."""
    return PaperTradeListResponse(items=PaperTradingService(db_manager).list_trades(limit=limit))
