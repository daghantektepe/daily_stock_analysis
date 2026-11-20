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
    report_text: Optional[str] = None


class Form4StudyRequest(BaseModel):
    quarters: str = Field("2023q1..2026q3", description="Quarter range e.g. 2023q1..2026q3 or 2025q1..2026q1")
    min_value: float = Field(50000.0, ge=0.0)
    min_price: float = Field(2.0, ge=0.0)
    limit: int = Field(0, ge=0, le=50000, description="0 = all events, or sample limit for faster runs")
    slippage: float = Field(0.5, ge=0.0, le=5.0)


class Form4StudyResponse(BaseModel):
    quarters: List[str] = Field(default_factory=list)
    total_events: int = 0
    evaluated_events: int = 0
    report_text: str = ""
    horizons: Dict[str, Any] = Field(default_factory=dict)


class PeadUnbiasedStudyRequest(BaseModel):
    universe: str = Field("smid", pattern="^(sp400|sp600|sp500|smid)$")
    sample: int = Field(400, ge=10, le=1500)
    min_surprise_pct: Optional[float] = None
    slippage: float = Field(0.25, ge=0.0, le=5.0)
    seed: int = 7


class CryptoTrendResponse(BaseModel):
    assets: List[str] = Field(default_factory=list)
    signals: Dict[str, Any] = Field(default_factory=dict)
    backtest_all: List[Dict[str, Any]] = Field(default_factory=list)
    backtest_oos: List[Dict[str, Any]] = Field(default_factory=list)
    yearly: List[Dict[str, Any]] = Field(default_factory=list)
    paper_report: str = ""
    report_text: str = ""


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


class TournamentRunRequest(BaseModel):
    oos_start: str = Field("2022-01-01", description="Out-of-sample evaluation start date (YYYY-MM-DD)")
    force_refresh: bool = Field(False, description="Ignore cached price CSVs and re-fetch Yahoo Finance")


class TournamentResponse(BaseModel):
    generated_at: Optional[str] = None
    oos_start: str = "2022-01-01"
    latest_date: Optional[str] = None
    total_strategies: int = 0
    total_assets: int = 0
    total_asset_days: int = 0
    pass_elite_count: int = 0
    pass_solid_count: int = 0
    champion: Optional[Dict[str, Any]] = None
    paa: Optional[Dict[str, Any]] = None
    meta_portfolio_a: Optional[Dict[str, Any]] = None
    meta_portfolio_b: Optional[Dict[str, Any]] = None
    featured_strategy_ids: List[str] = Field(default_factory=list)
    strategies: List[Dict[str, Any]] = Field(default_factory=list)
    paper_snapshot: Optional[Dict[str, Any]] = None


class PaaSignalResponse(BaseModel):
    as_of_date: Optional[str] = None
    risk_assets_total: int = 0
    risk_assets_below_sma252: int = 0
    crash_protection_pct: float = 0.0
    regime_label: str = "UNKNOWN"
    target_weights_pct: Dict[str, float] = Field(default_factory=dict)
    risk_asset_breadth: List[Dict[str, Any]] = Field(default_factory=list)
