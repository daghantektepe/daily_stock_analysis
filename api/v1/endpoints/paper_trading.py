# -*- coding: utf-8 -*-
"""Read-only paper trading and KAP/news alert endpoints (simulated ledger, never real orders)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_database_manager
from api.v1.schemas.paper_trading import (
    KapAlertItem,
    KapAlertListResponse,
    PaperEquityCurveResponse,
    PaperManualOrderRequest,
    PaperTrade,
    PaperTradeListResponse,
    PaperTradingSummaryResponse,
    PaperUpdateStopsRequest,
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


@router.get("/equity-curve", response_model=PaperEquityCurveResponse)
def get_paper_equity_curve(
    days: int = Query(90, ge=7, le=365),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> PaperEquityCurveResponse:
    """Daily cumulative P&L and return % curve computed from simulated trades and StockDaily."""
    payload = PaperTradingService(db_manager).get_equity_curve(days=days)
    return PaperEquityCurveResponse(**payload)


@router.post("/orders", response_model=PaperTrade)
def place_manual_paper_order(
    req: PaperManualOrderRequest,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> PaperTrade:
    """Record a simulated manual paper order (buy, reduce, or sell) with ATR or explicit stops."""
    try:
        trade = PaperTradingService(db_manager).place_manual_order(
            stock_code=req.stock_code,
            action=req.action,
            quantity=req.quantity,
            price=req.price,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
            stock_name=req.stock_name,
            market=req.market,
        )
        return PaperTrade(**trade)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_paper_order", "message": str(exc)}) from exc


@router.patch("/positions/{stock_code}/stops", response_model=PaperTrade)
def update_paper_position_stops(
    stock_code: str,
    req: PaperUpdateStopsRequest,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> PaperTrade:
    """Update active stop-loss and take-profit targets for an open paper position."""
    try:
        trade = PaperTradingService(db_manager).update_position_stops(
            stock_code,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
        )
        return PaperTrade(**trade)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"error": "paper_position_not_found", "message": str(exc)}) from exc
