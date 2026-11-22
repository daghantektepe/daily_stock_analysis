# -*- coding: utf-8 -*-
"""Pydantic schemas for Turkish & Crypto bridge endpoints (`/api/v1/bridges`)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BridgeItemStatus(BaseModel):
    id: str
    name: str
    kind: str
    configured: bool
    sandbox_or_readonly: bool = True
    mode_label: str
    live_reachable: Optional[bool] = None
    note: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class BridgesStatusResponse(BaseModel):
    ok: bool = True
    checked_live: bool = False
    bridges: List[BridgeItemStatus] = Field(default_factory=list)


class TefasFundItem(BaseModel):
    code: str
    title: str
    category: str = ""
    bucket: str = "diger"
    global_proxy: str = ""
    price_try: Optional[float] = None
    daily_return_pct: Optional[float] = None
    fund_size_try: Optional[float] = None
    investors: Optional[int] = None
    category_rank: Optional[int] = None
    category_total: Optional[int] = None
    market_share_pct: Optional[float] = None
    source: str = "curated_fallback"


class TefasFundsResponse(BaseModel):
    ok: bool = True
    count: int = 0
    live_count: int = 0
    funds: List[TefasFundItem] = Field(default_factory=list)


class PurchasePowerResult(BaseModel):
    nominal_return_pct: float
    usd_based_return_pct: Optional[float] = None
    real_tufe_return_pct: Optional[float] = None
    beats_inflation: Optional[bool] = None


class MacroTrResponse(BaseModel):
    ok: bool = True
    evds_configured: bool = False
    usd_try: Optional[float] = None
    usd_try_1y_change_pct: Optional[float] = None
    usd_try_as_of: Optional[str] = None
    usd_try_source: str = "unavailable"
    cpi_yoy_pct: Optional[float] = None
    cpi_mom_pct: Optional[float] = None
    cpi_as_of: Optional[str] = None
    cpi_source: str = "unavailable"
    cached: bool = False
    purchasing_power: Optional[PurchasePowerResult] = None


class BinancePreviewTicker(BaseModel):
    asset: str
    symbol: str
    last_price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread_bps: Optional[float] = None
    price_change_pct_24h: Optional[float] = None
    quote_volume_usdt_24h: Optional[float] = None
    source: str = "binance_public"
    error: Optional[str] = None


class BinancePreviewResponse(BaseModel):
    ok: bool = True
    testnet: bool = True
    configured: bool = False
    auto_execute: bool = False
    tickers: List[BinancePreviewTicker] = Field(default_factory=list)
    account: Optional[Dict[str, Any]] = None
