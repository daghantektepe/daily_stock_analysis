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
    bist_usd_reference: Optional[Dict[str, Any]] = Field(
        None, description="USDTRY change and XU100 in TL vs USD over the OOS window (BIST rows are judged in USD)"
    )


class PaaSignalResponse(BaseModel):
    as_of_date: Optional[str] = None
    risk_assets_total: int = 0
    risk_assets_below_sma252: int = 0
    crash_protection_pct: float = 0.0
    regime_label: str = "UNKNOWN"
    target_weights_pct: Dict[str, float] = Field(default_factory=dict)
    risk_asset_breadth: List[Dict[str, Any]] = Field(default_factory=list)


class QuantPaperPositionItem(BaseModel):
    symbol: str
    shares: float = 0.0
    avg_cost: float = 0.0
    last_price: float = 0.0
    market_value: float = 0.0
    weight_pct: float = 0.0
    unrealized_pnl_usd: float = 0.0
    unrealized_pnl_pct: float = 0.0


class QuantPaperBookItem(BaseModel):
    name: str
    strategy_key: str
    strategy_id: str
    label: str
    benchmark_symbol: str = "SPY"
    rebalance_mode: str = "monthly"
    cost_bps: float = 5.0
    simulated_only: bool = True
    start_date: Optional[str] = None
    last_date: Optional[str] = None
    last_rebalance_date: Optional[str] = None
    days: int = 0
    late_days: int = 0
    initial_capital: float = 10000.0
    nav: float = 10000.0
    cash: float = 10000.0
    cash_pct: float = 100.0
    return_pct: float = 0.0
    benchmark_return_pct: float = 0.0
    excess_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    benchmark_max_drawdown_pct: float = 0.0
    weights_pct: Dict[str, float] = Field(default_factory=dict)
    live_target_weights_pct: Dict[str, float] = Field(default_factory=dict)
    positions: List[QuantPaperPositionItem] = Field(default_factory=list)
    trade_count: int = 0
    processed_days: int = 0
    new_trades: List[Dict[str, Any]] = Field(default_factory=list)
    recent_trades: List[Dict[str, Any]] = Field(default_factory=list)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    report_text: str = ""
    council_meta: Optional[Dict[str, Any]] = None


class QuantPaperStepRequest(BaseModel):
    strategies: Optional[List[str]] = Field(
        default=None,
        description="Strategy keys to step (e.g. ['paa', 'meta_a']); defaults to configured strategies",
    )
    force_rebalance: bool = Field(False, description="Force rebalance to live model targets on latest close")
    force_refresh_prices: bool = Field(False, description="Force refresh US ETF prices from Yahoo Finance")


class ForwardSlippage(BaseModel):
    fills: int = 0
    avg_bps: Optional[float] = None
    worst_bps: Optional[float] = None


class ForwardExpectation(BaseModel):
    backtest_start: Optional[str] = None
    backtest_until: Optional[str] = None
    cagr_pct: Optional[float] = None
    excess_sharpe: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    horizon_days: Optional[int] = None
    band_pct: Dict[str, float] = Field(default_factory=dict, description="Return percentiles (p5..p95) for the gate horizon")


class ForwardValidationItem(BaseModel):
    strategy_key: Optional[str] = None
    label: Optional[str] = None
    status: str = "NOT_FROZEN"
    frozen_date: Optional[str] = None
    fingerprint: Optional[str] = None
    forward_days: int = 0
    late_days: int = 0
    late_ratio: float = 0.0
    forward_return_pct: Optional[float] = None
    benchmark_return_pct: Optional[float] = None
    excess_sharpe: Optional[float] = None
    excess_sharpe_se: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    backtest_percentile: Optional[float] = None
    slippage: ForwardSlippage = Field(default_factory=ForwardSlippage)
    gate: Dict[str, float] = Field(default_factory=dict)
    expectation: ForwardExpectation = Field(default_factory=ForwardExpectation)
    reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ForwardValidationResponse(BaseModel):
    ok: bool = True
    simulated_only: bool = True
    items: List[ForwardValidationItem] = Field(default_factory=list)
    report_text: str = ""
    error: Optional[str] = None


class QuantPaperBooksResponse(BaseModel):
    ok: bool = True
    simulated_only: bool = True
    strategies: List[str] = Field(default_factory=list)
    total_new_trades: int = 0
    books: List[QuantPaperBookItem] = Field(default_factory=list)
    forward_validation: List[ForwardValidationItem] = Field(default_factory=list)
    report_text: str = ""
    error: Optional[str] = None


class SimpleWeatherSummary(BaseModel):
    status: str = "cloudy"
    emoji: str = "⛅"
    badge_label: str = ""
    headline: str = ""
    plain_summary: str = ""
    behavioral_guard: str = ""
    protection_pct: float = 0.0


class SimpleDecisionStep(BaseModel):
    step: int
    title: str
    status: str = "info"
    explanation: str
    glossary_term: Optional[str] = None


class SimpleBasketAssetItem(BaseModel):
    symbol: str
    weight_pct: float
    plain_name: str
    role: str
    risk_level: str
    tr_equivalent: str
    midas_hint: str


class SimpleProfileOption(BaseModel):
    id: str
    emoji: str
    title: str
    subtitle: str
    recommended: bool = False
    engine_note: str = ""
    historical_max_dd_pct: float = 0.0
    estimated_annual_cost_pct: float = 0.05
    rebalance_cadence: str = ""
    assets: List[SimpleBasketAssetItem] = Field(default_factory=list)


class SimplePaperExamItem(BaseModel):
    strategy_key: str
    plain_label: str
    frozen_date: Optional[str] = None
    fingerprint: Optional[str] = None
    forward_days: int = 0
    target_days: int = 120
    nav_usd: float = 10000.0
    initial_capital_usd: float = 10000.0
    return_pct: float = 0.0
    benchmark_return_pct: Optional[float] = None
    status_plain: str = ""


class SimpleBriefResponse(BaseModel):
    ok: bool = True
    simulated_only: bool = True
    as_of_date: str = ""
    usdtry_rate: float = 50.0
    weather: SimpleWeatherSummary = Field(default_factory=SimpleWeatherSummary)
    decision_steps: List[SimpleDecisionStep] = Field(default_factory=list)
    profiles: List[SimpleProfileOption] = Field(default_factory=list)
    paper_exam: List[SimplePaperExamItem] = Field(default_factory=list)
    disclaimer: str = ""
