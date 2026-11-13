# -*- coding: utf-8 -*-
"""Pydantic schemas for Unified Alpha Discovery & Research endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class UsScreenRequest(BaseModel):
    symbols: Optional[List[str]] = Field(None, description="Optional custom ticker list; defaults to built-in liquid US universe")
    top_n: int = Field(12, ge=1, le=50)
    include_pead: bool = True
    include_form4: bool = True
    use_sec_xbrl: bool = True


class UsQuantCandidateItem(BaseModel):
    symbol: str
    score: float
    residual_momentum_z: Optional[float] = None
    raw_12_1m_return_pct: Optional[float] = None
    near_52w_high: Optional[float] = None
    fip_id: Optional[float] = None
    cash_op_profitability: Optional[float] = None
    accruals_ratio: Optional[float] = None
    realized_vol_ann: Optional[float] = None
    vol_scale_weight: Optional[float] = None
    avg_dollar_volume: Optional[float] = None
    last_close: Optional[float] = None
    pead_score: float = 0.0
    insider_score: float = 0.0
    reasons: List[str] = Field(default_factory=list)


class UsScreenResponse(BaseModel):
    count: int
    items: List[UsQuantCandidateItem] = Field(default_factory=list)


class Form4ClusterItem(BaseModel):
    symbol: str
    company_name: str = ""
    filing_date: Optional[str] = None
    insider_count: int = 0
    officer_director_count: int = 0
    total_value: float = 0.0
    total_shares: float = 0.0
    avg_price: float = 0.0
    has_c_level: bool = False
    is_opportunistic: bool = False
    is_cluster: bool = False
    cmp_class: str = "unclassified"
    has_10b51: bool = False
    primary_titles: List[str] = Field(default_factory=list)
    trend_regime: str = "neutral"
    score: float = 0.0
    reasons: List[str] = Field(default_factory=list)
    sec_url: str = ""


class Form4LiveResponse(BaseModel):
    count: int
    items: List[Form4ClusterItem] = Field(default_factory=list)


class PeadCandidateItem(BaseModel):
    symbol: str
    company_name: str = ""
    earnings_date: Optional[str] = None
    days_since_earnings: int = 0
    eps_estimate: Optional[float] = None
    eps_reported: Optional[float] = None
    eps_surprise_pct: Optional[float] = None
    sue_score: Optional[float] = None
    revenue_growth_pct: Optional[float] = None
    near_52w_high: Optional[float] = None
    avg_dollar_volume: Optional[float] = None
    announcement_session: str = "BMO"
    day1_return_pct: Optional[float] = None
    total_drift_pct: Optional[float] = None
    volume_surge_ratio: Optional[float] = None
    trend_regime: str = "neutral"
    conviction_tier: str = "watch"
    score: float = 0.0
    reasons: List[str] = Field(default_factory=list)


class PeadCandidatesResponse(BaseModel):
    count: int
    universe: str
    items: List[PeadCandidateItem] = Field(default_factory=list)


class PeadStudyRequest(BaseModel):
    symbols: List[str] = Field(default_factory=lambda: ["NVDA", "META", "AMZN", "AVGO", "NFLX"])
    min_surprise_pct: float = Field(5.0, ge=-50.0, le=500.0)
    benchmark_symbol: str = "SPY"
    estimated_slippage_pct: float = Field(0.25, ge=0.0, le=5.0)


class PeadStudyResponse(BaseModel):
    total_events: int
    evaluated_events: int
    benchmark_symbol: str
    estimated_slippage_pct: float
    horizons: Dict[str, Any] = Field(default_factory=dict)
    segments: Dict[str, Any] = Field(default_factory=dict)


class BistScreenRequest(BaseModel):
    top_n: int = Field(8, ge=1, le=25)
    min_score: float = Field(25.0, ge=0.0, le=100.0)
    include_kap: bool = True


class BistScreenResponse(BaseModel):
    selected_codes: List[str] = Field(default_factory=list)
    scanned_count: int = 0
    passed_count: int = 0
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class KapContractResponse(BaseModel):
    count: int
    items: List[Dict[str, Any]] = Field(default_factory=list)


class AlphaOverviewResponse(BaseModel):
    paper_trading_enabled: bool
    auth_enabled: bool
    open_position_count: int
    trade_count: int
    win_rate_pct: Optional[float] = None
    totals_by_currency: Dict[str, Any] = Field(default_factory=dict)
    recent_alerts_count: int = 0
    us_screener_enabled: bool = False
    bist_screener_enabled: bool = False
