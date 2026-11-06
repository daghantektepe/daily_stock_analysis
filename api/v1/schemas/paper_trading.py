# -*- coding: utf-8 -*-
"""Schemas for the read-only paper trading API."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PaperPosition(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    market: Optional[str] = None
    currency: Optional[str] = None
    quantity: float
    avg_cost: float
    last_close: Optional[float] = None
    last_close_date: Optional[str] = None
    price_stale: bool = Field(False, description="True when no stored daily close exists; marked at cost")
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: Optional[float] = None
    realized_pnl: float


class PaperCurrencyTotals(BaseModel):
    cost: float
    market_value: float
    realized_pnl: float
    unrealized_pnl: float


class PaperBenchmark(BaseModel):
    benchmark: str = Field(..., description="Benchmark index symbol, e.g. XU100.IS")
    benchmark_name: str
    currency: str
    capital_deployed: float = Field(..., description="Sum of buy amounts in the quote currency")
    strategy_return_pct: float
    benchmark_return_pct: Optional[float] = Field(
        None, description="Same cash flows invested in the benchmark index on the same days"
    )
    excess_return_pct: Optional[float] = None
    usd_return_pct: Optional[float] = Field(None, description="Strategy return with cash flows converted to USD")
    fx_change_pct: Optional[float] = Field(None, description="USD rate change since the first trade")


class PaperTradingSummaryResponse(BaseModel):
    enabled: bool
    position_size: float
    trade_count: int
    open_position_count: int
    closed_trade_count: int
    win_rate_pct: Optional[float] = None
    positions: List[PaperPosition]
    totals_by_currency: Dict[str, PaperCurrencyTotals] = Field(
        default_factory=dict,
        description="Totals grouped by quote currency; currencies are never mixed",
    )
    benchmarks: Dict[str, PaperBenchmark] = Field(
        default_factory=dict,
        description="Per-market benchmark comparison (index shadow, USD-based return); empty when unavailable",
    )


class PaperTrade(BaseModel):
    id: int
    signal_id: int
    stock_code: str
    stock_name: Optional[str] = None
    market: Optional[str] = None
    currency: Optional[str] = None
    action: str
    side: str
    quantity: float
    price: float
    trade_date: Optional[str] = None


class PaperTradeListResponse(BaseModel):
    items: List[PaperTrade]
