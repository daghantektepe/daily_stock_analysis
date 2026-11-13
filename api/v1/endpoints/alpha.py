# -*- coding: utf-8 -*-
"""Unified Alpha Discovery & Research endpoints (US Quant, PEAD 2.0, Live SEC Form 4, BIST, KAP)."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from api.deps import get_config_dep, get_database_manager
from api.v1.schemas.alpha import (
    AlphaOverviewResponse,
    BistScreenRequest,
    BistScreenResponse,
    Form4ClusterItem,
    Form4LiveResponse,
    KapContractResponse,
    PeadCandidateItem,
    PeadCandidatesResponse,
    PeadStudyRequest,
    PeadStudyResponse,
    UsQuantCandidateItem,
    UsScreenRequest,
    UsScreenResponse,
)
from src.config import Config
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/overview", response_model=AlphaOverviewResponse)
def get_alpha_overview(
    config: Config = Depends(get_config_dep),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> AlphaOverviewResponse:
    """Lightweight live cockpit status: paper trading ledger summary, alert count, and safety flags."""
    from src.services.kap_watch_service import get_recent_kap_and_news_alerts
    from src.services.paper_trading_service import PaperTradingService

    summary = PaperTradingService(db_manager).get_summary(include_benchmarks=False)
    alerts = get_recent_kap_and_news_alerts(live_fallback=False, max_items=30)
    return AlphaOverviewResponse(
        paper_trading_enabled=bool(summary.get("enabled", False)),
        auth_enabled=bool(getattr(config, "admin_auth_enabled", False)),
        open_position_count=int(summary.get("open_position_count", 0) or 0),
        trade_count=int(summary.get("trade_count", 0) or 0),
        win_rate_pct=summary.get("win_rate_pct"),
        totals_by_currency=summary.get("totals_by_currency") or {},
        recent_alerts_count=len(alerts),
        us_screener_enabled=bool(getattr(config, "us_screener_enabled", False)),
        bist_screener_enabled=bool(getattr(config, "bist_screener_enabled", False)),
    )


@router.post("/us-screen", response_model=UsScreenResponse)
def run_us_alpha_screen(req: UsScreenRequest) -> UsScreenResponse:
    """Run composite US High-Alpha screen (Residual Momentum + 52W High + FIP + CashOpProf + PEAD + Form 4)."""
    from src.services.us_quant_screener import screen_us_alpha_candidates

    candidates = screen_us_alpha_candidates(
        symbols=req.symbols or None,
        top_n=req.top_n,
        include_pead=req.include_pead,
        include_form4=req.include_form4,
        use_sec_xbrl=req.use_sec_xbrl,
    )
    items = [UsQuantCandidateItem(**asdict(c)) for c in candidates]
    return UsScreenResponse(count=len(items), items=items)


@router.get("/form4-live", response_model=Form4LiveResponse)
def get_live_form4_clusters(
    count: int = Query(80, ge=10, le=200),
    max_filings: int = Query(40, ge=5, le=100),
    min_value: float = Query(10000.0, ge=0.0),
) -> Form4LiveResponse:
    """Fetch live SEC EDGAR Form 4 Atom filings and cluster open-market executive purchases."""
    from data_provider.sec_form4_fetcher import SecForm4Fetcher
    from src.services.sec_form4_screener import score_insider_event

    fetcher = SecForm4Fetcher()
    clusters = fetcher.fetch_live_purchases(
        count=count,
        max_filings=max_filings,
        min_value=min_value,
    )
    items: List[Form4ClusterItem] = []
    for cl in clusters:
        ev_score, reasons = score_insider_event(cl)
        items.append(
            Form4ClusterItem(
                symbol=cl.symbol,
                company_name=cl.company_name,
                filing_date=cl.filing_date.isoformat() if cl.filing_date else None,
                insider_count=cl.insider_count,
                officer_director_count=cl.officer_director_count,
                total_value=round(float(cl.total_value), 2),
                total_shares=round(float(cl.total_shares), 2),
                avg_price=round(float(cl.avg_price), 4),
                has_c_level=bool(cl.has_c_level),
                is_opportunistic=bool(cl.is_opportunistic),
                is_cluster=bool(cl.is_cluster),
                cmp_class=cl.cmp_class,
                has_10b51=bool(cl.has_10b51),
                primary_titles=list(cl.primary_titles or []),
                trend_regime=cl.trend_regime,
                score=float(ev_score),
                reasons=list(reasons),
                sec_url=cl.sec_url,
            )
        )
    items.sort(key=lambda x: x.score, reverse=True)
    return Form4LiveResponse(count=len(items), items=items)


@router.get("/pead-candidates", response_model=PeadCandidatesResponse)
def get_pead_candidates(
    universe: str = Query("all", pattern="^(all|midcap|megacap)$"),
    max_days: int = Query(21, ge=1, le=90),
    min_score: float = Query(40.0, ge=0.0, le=100.0),
    top_n: int = Query(15, ge=1, le=50),
) -> PeadCandidatesResponse:
    """Scan US stocks for recent Post-Earnings Announcement Drift (PEAD 2.0) setups."""
    from scripts.pead_screener import DEFAULT_US_MIDCAP_WATCHLIST, DEFAULT_US_WATCHLIST
    from src.services.pead_screener import screen_pead_candidates

    if universe == "midcap":
        syms = DEFAULT_US_MIDCAP_WATCHLIST
    elif universe == "megacap":
        syms = DEFAULT_US_WATCHLIST
    else:
        syms = list(dict.fromkeys([*DEFAULT_US_MIDCAP_WATCHLIST, *DEFAULT_US_WATCHLIST]))

    candidates = screen_pead_candidates(
        symbols=syms,
        max_days=max_days,
        min_score=min_score,
        top_n=top_n,
    )
    items = [PeadCandidateItem(**c.to_dict()) for c in candidates]
    return PeadCandidatesResponse(count=len(items), universe=universe, items=items)


@router.post("/pead-study", response_model=PeadStudyResponse)
def execute_pead_study(req: PeadStudyRequest) -> PeadStudyResponse:
    """Run empirical PEAD event study (BMO/AMC aligned, net of slippage, vs SPY)."""
    from src.services.pead_event_study import run_pead_event_study

    report = run_pead_event_study(
        symbols=req.symbols,
        min_surprise_pct=req.min_surprise_pct,
        benchmark_symbol=req.benchmark_symbol,
        estimated_slippage_pct=req.estimated_slippage_pct,
    )
    return PeadStudyResponse(**report)


@router.post("/bist-screen", response_model=BistScreenResponse)
def run_bist_screen(req: BistScreenRequest) -> BistScreenResponse:
    """Scan BIST stocks for technical breakouts, volume surges, and KAP catalysts."""
    from src.services.bist_screener import screen_bist_stocks

    res = screen_bist_stocks(
        top_n=req.top_n,
        min_score=req.min_score,
        include_kap=req.include_kap,
    )
    return BistScreenResponse(
        selected_codes=list(res.get("selected_codes") or []),
        scanned_count=int(res.get("scanned_count") or 0),
        passed_count=int(res.get("passed_count") or 0),
        candidates=list(res.get("candidates") or []),
        errors=list(res.get("errors") or []),
    )


@router.get("/kap-contracts", response_model=KapContractResponse)
def get_kap_contracts(
    days_back: int = Query(7, ge=1, le=90),
    min_score: int = Query(30, ge=0, le=100),
    top_n: int = Query(20, ge=1, le=100),
) -> KapContractResponse:
    """Fetch and score recent BIST KAP new contract/tender disclosures."""
    from src.services.kap_contract_screener import KapContractScreener

    candidates = KapContractScreener().scan_recent_contracts(
        days=days_back,
        min_score=min_score,
        top_n=top_n,
    )
    items = [asdict(row) if hasattr(row, "__dataclass_fields__") else dict(row) for row in candidates]
    return KapContractResponse(count=len(items), items=items)
