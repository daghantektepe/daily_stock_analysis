# -*- coding: utf-8 -*-
"""Unified Alpha Discovery & Research endpoints (US Quant, PEAD 2.0, Live SEC Form 4, BIST, KAP)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from api.deps import get_config_dep, get_database_manager
from api.v1.schemas.alpha import (
    AlphaOverviewResponse,
    BistScreenRequest,
    BistScreenResponse,
    CryptoTrendResponse,
    Form4ClusterItem,
    Form4LiveResponse,
    Form4StudyRequest,
    Form4StudyResponse,
    KapContractResponse,
    PaaSignalResponse,
    PeadCandidateItem,
    PeadCandidatesResponse,
    PeadStudyRequest,
    PeadStudyResponse,
    PeadUnbiasedStudyRequest,
    ForwardValidationResponse,
    QuantPaperBooksResponse,
    QuantPaperStepRequest,
    SimpleBriefResponse,
    TournamentResponse,
    TournamentRunRequest,
    UsQuantCandidateItem,
    UsScreenRequest,
    UsScreenResponse,
)
from src.config import Config
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()

_SCREENER_CACHE_DIR = Path("data") / "cache" / "screeners"
_SCREENER_TTL_SECONDS = 1200.0  # 20 minutes


def _screener_cache_key(prefix: str, params: Dict[str, Any]) -> Path:
    digest = hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return _SCREENER_CACHE_DIR / f"{prefix}_{digest}.json"


def _read_screener_cache(prefix: str, params: Dict[str, Any], ttl_s: float = _SCREENER_TTL_SECONDS) -> Optional[Dict[str, Any]]:
    path = _screener_cache_key(prefix, params)
    if not path.is_file():
        return None
    try:
        if (time.time() - path.stat().st_mtime) > ttl_s:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_screener_cache(prefix: str, params: Dict[str, Any], payload: Dict[str, Any]) -> None:
    try:
        _SCREENER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _screener_cache_key(prefix, params)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except (OSError, TypeError, ValueError):
        pass


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
def run_us_alpha_screen(
    req: UsScreenRequest,
    refresh: bool = Query(False, description="Bypass 20-minute screener cache"),
) -> UsScreenResponse:
    """Run composite US High-Alpha screen (Residual Momentum + 52W High + FIP + CashOpProf + PEAD + Form 4)."""
    from src.services.us_quant_screener import screen_us_alpha_candidates

    cache_params = req.model_dump()
    if not refresh:
        cached = _read_screener_cache("us_screen", cache_params)
        if cached is not None:
            return UsScreenResponse(**cached)

    candidates = screen_us_alpha_candidates(
        symbols=req.symbols or None,
        top_n=req.top_n,
        include_pead=req.include_pead,
        include_form4=req.include_form4,
        use_sec_xbrl=req.use_sec_xbrl,
    )
    items = [UsQuantCandidateItem(**asdict(c)) for c in candidates]
    resp = UsScreenResponse(count=len(items), items=items)
    _write_screener_cache("us_screen", cache_params, resp.model_dump())
    return resp


@router.get("/form4-live", response_model=Form4LiveResponse)
def get_live_form4_clusters(
    count: int = Query(80, ge=10, le=200),
    max_filings: int = Query(40, ge=5, le=100),
    min_value: float = Query(10000.0, ge=0.0),
    refresh: bool = Query(False, description="Bypass 20-minute Form 4 cache"),
) -> Form4LiveResponse:
    """Fetch live SEC EDGAR Form 4 Atom filings and cluster open-market executive purchases."""
    from data_provider.sec_form4_fetcher import SecForm4Fetcher
    from src.services.sec_form4_screener import score_insider_event

    cache_params = {"count": count, "max_filings": max_filings, "min_value": min_value}
    if not refresh:
        cached = _read_screener_cache("form4_live", cache_params)
        if cached is not None:
            return Form4LiveResponse(**cached)

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
    resp = Form4LiveResponse(count=len(items), items=items)
    _write_screener_cache("form4_live", cache_params, resp.model_dump())
    return resp


@router.get("/pead-candidates", response_model=PeadCandidatesResponse)
def get_pead_candidates(
    universe: str = Query("all", pattern="^(all|midcap|megacap)$"),
    max_days: int = Query(21, ge=1, le=90),
    min_score: float = Query(40.0, ge=0.0, le=100.0),
    top_n: int = Query(15, ge=1, le=50),
    refresh: bool = Query(False, description="Bypass 20-minute PEAD cache"),
) -> PeadCandidatesResponse:
    """Scan US stocks for recent Post-Earnings Announcement Drift (PEAD 2.0) setups."""
    from scripts.pead_screener import DEFAULT_US_MIDCAP_WATCHLIST, DEFAULT_US_WATCHLIST
    from src.services.pead_screener import screen_pead_candidates

    cache_params = {"universe": universe, "max_days": max_days, "min_score": min_score, "top_n": top_n}
    if not refresh:
        cached = _read_screener_cache("pead_candidates", cache_params)
        if cached is not None:
            return PeadCandidatesResponse(**cached)

    if universe == "midcap":
        syms = DEFAULT_US_MIDCAP_WATCHLIST
    elif universe == "megacap":
        syms = DEFAULT_US_WATCHLIST
    else:
        syms = list(dict.fromkeys([*DEFAULT_US_WATCHLIST, *DEFAULT_US_MIDCAP_WATCHLIST]))

    candidates = screen_pead_candidates(
        symbols=syms,
        max_days=max_days,
        min_score=int(min_score),
        top_n=top_n,
        deadline_seconds=14.0,
    )
    items = [PeadCandidateItem(**c.to_dict()) for c in candidates]
    resp = PeadCandidatesResponse(count=len(items), universe=universe, items=items)
    _write_screener_cache("pead_candidates", cache_params, resp.model_dump())
    return resp


@router.post("/pead-study", response_model=PeadStudyResponse)
def execute_pead_study(req: PeadStudyRequest) -> PeadStudyResponse:
    """Run empirical PEAD event study (BMO/AMC aligned, net of slippage, vs SPY)."""
    from src.services.pead_event_study import format_pead_study_report, run_pead_event_study

    report = run_pead_event_study(
        symbols=req.symbols,
        min_surprise_pct=req.min_surprise_pct,
        benchmark_symbol=req.benchmark_symbol,
        estimated_slippage_pct=req.estimated_slippage_pct,
    )
    return PeadStudyResponse(**report, report_text=format_pead_study_report(report))


@router.post("/pead-unbiased-study", response_model=PeadStudyResponse)
def execute_pead_unbiased_study(req: PeadUnbiasedStudyRequest) -> PeadStudyResponse:
    """Run unbiased index constituent PEAD study (S&P 400 + S&P 600, matching scripts/pead_study.py)."""
    import random
    from scripts.pead_study import load_index_constituents
    from src.services.pead_event_study import format_pead_study_report, run_pead_event_study

    names = ("sp400", "sp600") if req.universe == "smid" else (req.universe,)
    symbols = sorted({sym for name in names for sym in load_index_constituents(name)})
    if req.sample and len(symbols) > req.sample:
        symbols = sorted(random.Random(req.seed).sample(symbols, req.sample))

    report = run_pead_event_study(
        symbols=symbols,
        min_surprise_pct=req.min_surprise_pct,
        estimated_slippage_pct=req.slippage,
    )
    txt = f"PEAD testi: {len(symbols)} hisse ({req.universe})\n\n" + format_pead_study_report(report)
    return PeadStudyResponse(**report, report_text=txt)


@router.post("/form4-study", response_model=Form4StudyResponse)
def execute_form4_study(req: Form4StudyRequest) -> Form4StudyResponse:
    """Run historical SEC Form 4 executive insider buying study (matching scripts/sec_form4_study.py)."""
    from data_provider.sec_form4_fetcher import SecForm4Fetcher, quarter_range
    from src.services.sec_form4_study import format_sec_form4_study_report, run_sec_form4_event_study

    fetcher = SecForm4Fetcher()
    raw_q = req.quarters.strip().lower()
    if ".." in raw_q:
        parts = raw_q.split("..")
        quarters = quarter_range(parts[0].strip(), parts[1].strip())
    else:
        quarters = [q.strip().lower() for q in raw_q.split(",") if q.strip()]

    all_events = []
    for q in quarters:
        try:
            events = fetcher.parse_quarter(
                q,
                min_value=req.min_value,
                min_price=req.min_price,
                exclude_funds_and_trusts=True,
            )
            all_events.extend(events)
        except Exception as exc:
            logger.warning("Failed to parse quarter %s: %s", q, exc)

    all_events.sort(key=lambda e: e.filing_date)
    if req.limit and len(all_events) > req.limit:
        n = len(all_events)
        all_events = [all_events[int(i * n / req.limit)] for i in range(req.limit)]

    result = run_sec_form4_event_study(
        all_events,
        benchmark_symbol="SPY",
        estimated_slippage_pct=req.slippage,
    )
    txt = format_sec_form4_study_report(result, quarters_label=", ".join(quarters))
    return Form4StudyResponse(
        quarters=quarters,
        total_events=int(result.get("total_events", 0)),
        evaluated_events=int(result.get("evaluated_events", 0)),
        report_text=txt,
        horizons=result.get("horizons") or {},
    )


@router.get("/crypto-trend", response_model=CryptoTrendResponse)
def get_crypto_trend_status(
    step_paper: bool = Query(True, description="Advance the paper book to latest close"),
    refresh: bool = Query(False, description="Bypass 20-minute crypto trend cache"),
) -> CryptoTrendResponse:
    """Run Crypto Trend Strategy signal, backtest, and paper book status (matching scripts/crypto_trend.py)."""
    from datetime import date
    from src.config import get_config
    from src.services.crypto_trend_strategy import (
        TrendConfig,
        current_targets,
        load_daily_closes,
        robustness_grid,
        run_backtest,
    )
    from src.services.strategy_paper_book import StrategyPaperBook, format_book_report

    cfg = get_config()
    assets = tuple(getattr(cfg, "crypto_trend_assets", None) or ("BTC-USD", "ETH-USD"))
    cache_params = {"assets": list(assets), "step_paper": bool(step_paper)}
    if not refresh:
        cached = _read_screener_cache("crypto_trend", cache_params)
        if cached is not None:
            return CryptoTrendResponse(**cached)

    trend = TrendConfig(assets=assets)
    prices = load_daily_closes(trend.assets)
    targets = current_targets(prices, trend)

    bt_all = robustness_grid(prices, trend.windows, assets=trend.assets, cost_pct=trend.cost_pct, start=None, end=None)
    bt_oos = robustness_grid(
        prices, trend.windows, assets=trend.assets, cost_pct=trend.cost_pct, start=date(2022, 1, 1), end=None
    )
    bt_res = run_backtest(prices, trend)

    book = StrategyPaperBook(config=trend, initial_capital=float(getattr(cfg, "crypto_trend_capital", 10_000.0)))
    if step_paper:
        book.step(prices)
    paper_rep = format_book_report(book.summary(), targets)

    lines = [f"Kripto trend geçmiş testi ({', '.join(trend.assets)}; maliyet %{trend.cost_pct} / işlem)"]
    for label, rows in (("Tüm dönem", bt_all), ("2022-bugün (örneklem dışı)", bt_oos)):
        lines.append(f"\n{label}:")
        for row in rows:
            lines.append(
                f"  {row['label']:>9}: yıllık %{row['strategy_cagr_pct']:>6} | en büyük düşüş %{row['strategy_max_drawdown_pct']:>6} "
                f"| Sharpe {row['strategy_sharpe']} || al-tut yıllık %{row['buy_hold_cagr_pct']:>6} "
                f"düşüş %{row['buy_hold_max_drawdown_pct']:>6} Sharpe {row['buy_hold_sharpe']} "
                f"({row['start']} → {row['end']})"
            )
    lines.append("\n" + paper_rep)

    resp = CryptoTrendResponse(
        assets=list(trend.assets),
        signals=targets,
        backtest_all=bt_all,
        backtest_oos=bt_oos,
        yearly=bt_res.get("yearly") or [],
        paper_report=paper_rep,
        report_text="\n".join(lines),
    )
    _write_screener_cache("crypto_trend", cache_params, resp.model_dump())
    return resp


@router.post("/bist-screen", response_model=BistScreenResponse)
def run_bist_screen(
    req: BistScreenRequest,
    refresh: bool = Query(False, description="Bypass 20-minute BIST screener cache"),
) -> BistScreenResponse:
    """Scan liquid BIST equities for technical breakouts, volume surges, and KAP catalysts."""
    from src.services.bist_screener import screen_bist_stocks

    cache_params = req.model_dump()
    if not refresh:
        cached = _read_screener_cache("bist_screen", cache_params)
        if cached is not None:
            return BistScreenResponse(**cached)

    res = screen_bist_stocks(
        top_n=req.top_n,
        min_score=req.min_score,
        include_kap=req.include_kap,
        max_symbols=120,
    )
    resp = BistScreenResponse(
        selected_codes=list(res.get("selected_codes") or []),
        scanned_count=int(
            res.get("scanned_count")
            or res.get("evaluated_count")
            or res.get("universe_count")
            or 0
        ),
        passed_count=int(
            res.get("passed_count")
            or res.get("qualified_count")
            or len(res.get("candidates") or [])
        ),
        candidates=list(res.get("candidates") or []),
        errors=list(res.get("errors") or []),
    )
    _write_screener_cache("bist_screen", cache_params, resp.model_dump())
    return resp


@router.get("/kap-contracts", response_model=KapContractResponse)
def get_kap_contracts(
    days_back: int = Query(7, ge=1, le=90),
    min_score: int = Query(30, ge=0, le=100),
    top_n: int = Query(20, ge=1, le=100),
    refresh: bool = Query(False, description="Bypass 20-minute KAP cache"),
) -> KapContractResponse:
    """Fetch and score recent BIST KAP new contract/tender disclosures."""
    from src.services.kap_contract_screener import KapContractScreener

    cache_params = {"days_back": days_back, "min_score": min_score, "top_n": top_n}
    if not refresh:
        cached = _read_screener_cache("kap_contracts", cache_params)
        if cached is not None:
            return KapContractResponse(**cached)

    candidates = KapContractScreener().scan_recent_contracts(
        days=days_back,
        min_score=min_score,
        top_n=top_n,
    )
    items = [asdict(row) if hasattr(row, "__dataclass_fields__") else dict(row) for row in candidates]
    resp = KapContractResponse(count=len(items), items=items)
    _write_screener_cache("kap_contracts", cache_params, resp.model_dump())
    return resp


@router.get("/tournament", response_model=TournamentResponse)
def get_strategy_tournament(
    auto_run: bool = Query(True, description="Run tournament automatically when cache is missing"),
) -> TournamentResponse:
    """Return the cached 25-strategy multi-universe empirical tournament leaderboard & OOS equity curves."""
    from src.quant.tournament import load_latest_tournament_results

    data = load_latest_tournament_results(auto_run_if_missing=auto_run)
    if not data:
        return TournamentResponse()
    return TournamentResponse(**data)


@router.post("/tournament/run", response_model=TournamentResponse)
def trigger_strategy_tournament(req: TournamentRunRequest) -> TournamentResponse:
    """Execute the 25-strategy empirical tournament (OOS 2022+, zero lookahead, net of costs, DSR)."""
    from src.quant.tournament import run_tournament

    data = run_tournament(
        oos_start=req.oos_start,
        force_refresh=req.force_refresh,
    )
    return TournamentResponse(**data)


@router.get("/paa", response_model=PaaSignalResponse)
def get_paa_live_signal(
    refresh: bool = Query(False, description="Force refresh Yahoo Finance ETF prices"),
) -> PaaSignalResponse:
    """Return live Protective Asset Allocation (PAA) crash-shield breadth and target weights."""
    from src.quant.tournament import get_live_paa_signal

    data = get_live_paa_signal(force_refresh=refresh)
    if data.get("ok") is False:
        return PaaSignalResponse(regime_label="UNAVAILABLE")
    return PaaSignalResponse(**data)


def _active_quant_paper_strategies(cfg: Config) -> tuple[str, ...]:
    """Return configured quant paper strategies plus any extra frozen v3 books registered locally."""
    base = list(getattr(cfg, "quant_paper_strategies", ["paa", "meta_a"]) or ["paa", "meta_a"])
    try:
        from src.quant.forward_validation import DEFAULT_REGISTRY_PATH, ForwardRegistry
        from src.quant.paper_book import QUANT_PAPER_SPECS

        if DEFAULT_REGISTRY_PATH.is_file():
            frozen = ForwardRegistry(DEFAULT_REGISTRY_PATH).data.get("strategies") or {}
            for key in frozen:
                if key in QUANT_PAPER_SPECS and key not in base:
                    base.append(key)
    except Exception:  # noqa: BLE001
        pass
    return tuple(base)


@router.get("/simple-brief", response_model=SimpleBriefResponse)
def get_simple_investor_brief() -> SimpleBriefResponse:
    """Plain-Turkish beginner dashboard brief (weather, decision flow, budget baskets & TR equivalents)."""
    from src.services.simple_investor_brief import build_simple_investor_brief

    data = build_simple_investor_brief()
    return SimpleBriefResponse(**data)


@router.get("/quant-paper", response_model=QuantPaperBooksResponse)
def get_quant_paper_books(
    auto_step: bool = Query(True, description="Initialize paper books automatically if not yet started"),
) -> QuantPaperBooksResponse:
    """Return persisted PAA, Meta-Portfolio A & enrolled v3 StrategyPaperBook ledgers (simulated only)."""
    from src.config import get_config
    from src.quant.paper_book import get_quant_paper_books_status

    cfg = get_config()
    data = get_quant_paper_books_status(
        strategies=_active_quant_paper_strategies(cfg),
        initial_capital=float(getattr(cfg, "quant_paper_capital", 10000.0)),
        cost_bps=float(getattr(cfg, "quant_paper_cost_bps", 5.0)),
        rebalance_mode=str(getattr(cfg, "quant_paper_rebalance_mode", "monthly")),
        auto_step_if_empty=auto_step,
    )
    return QuantPaperBooksResponse(**data)


@router.get("/forward-validation", response_model=ForwardValidationResponse)
def get_forward_validation() -> ForwardValidationResponse:
    """Forward (live paper) validation gate for all frozen quant books (read-only)."""
    from src.config import get_config
    from src.quant.forward_validation import format_forward_report, run_forward_validation

    cfg = get_config()
    try:
        items = run_forward_validation(
            strategies=_active_quant_paper_strategies(cfg),
            auto_freeze=False,
            paper_settings={
                "initial_capital": float(getattr(cfg, "quant_paper_capital", 10000.0)),
                "cost_bps": float(getattr(cfg, "quant_paper_cost_bps", 5.0)),
                "rebalance_mode": str(getattr(cfg, "quant_paper_rebalance_mode", "monthly")),
            },
        )
    except Exception as exc:  # noqa: BLE001 - surface as a soft error card, not a 500
        logger.warning("[alpha] forward validation failed: %s", exc)
        return ForwardValidationResponse(ok=False, error=f"İleri doğrulama okunamadı: {exc}")
    return ForwardValidationResponse(items=items, report_text=format_forward_report(items))


@router.post("/quant-paper/step", response_model=QuantPaperBooksResponse)
def step_quant_paper(req: QuantPaperStepRequest) -> QuantPaperBooksResponse:
    """Advance PAA, Meta-Portfolio A & enrolled v3 StrategyPaperBook ledgers to the latest completed close."""
    from src.config import get_config
    from src.quant.paper_book import step_quant_paper_books

    cfg = get_config()
    data = step_quant_paper_books(
        strategies=req.strategies or _active_quant_paper_strategies(cfg),
        initial_capital=float(getattr(cfg, "quant_paper_capital", 10000.0)),
        cost_bps=float(getattr(cfg, "quant_paper_cost_bps", 5.0)),
        rebalance_mode=str(getattr(cfg, "quant_paper_rebalance_mode", "monthly")),
        force_rebalance=req.force_rebalance,
        force_refresh_prices=req.force_refresh_prices,
    )
    return QuantPaperBooksResponse(**data)
