# -*- coding: utf-8 -*-
"""Offline unit tests for Unified Alpha Discovery endpoints (/api/v1/alpha/*)."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_config_dep, get_database_manager
from api.v1.endpoints import alpha as alpha_ep
from data_provider.sec_form4_fetcher import InsiderClusterEvent
from src.services.kap_contract_screener import KapContractCandidate
from src.services.pead_screener import PeadCandidate
from src.services.us_quant_screener import UsQuantCandidate


def _make_app():
    app = FastAPI()
    app.include_router(alpha_ep.router, prefix="/api/v1/alpha")
    app.dependency_overrides[get_config_dep] = lambda: SimpleNamespace(
        admin_auth_enabled=False,
        us_screener_enabled=True,
        bist_screener_enabled=True,
    )
    app.dependency_overrides[get_database_manager] = lambda: MagicMock()
    return app


def test_alpha_overview_and_screens(monkeypatch) -> None:
    app = _make_app()
    client = TestClient(app)

    monkeypatch.setattr(
        "src.services.paper_trading_service.PaperTradingService.get_summary",
        lambda self, include_benchmarks=False: {
            "enabled": True,
            "open_position_count": 2,
            "trade_count": 5,
            "win_rate_pct": 60.0,
            "totals_by_currency": {"USD": {"realized_pnl": 350.0, "unrealized_pnl": 120.0}},
        },
    )
    monkeypatch.setattr(
        "src.services.kap_watch_service.get_recent_kap_and_news_alerts",
        lambda live_fallback=False, max_items=30: [{"stock_code": "THYAO.IS", "title": "Test"}],
    )

    ov = client.get("/api/v1/alpha/overview")
    assert ov.status_code == 200
    body = ov.json()
    assert body["paper_trading_enabled"] is True
    assert body["auth_enabled"] is False
    assert body["open_position_count"] == 2
    assert body["recent_alerts_count"] == 1

    monkeypatch.setattr(
        "src.services.us_quant_screener.screen_us_alpha_candidates",
        lambda **kwargs: [
            UsQuantCandidate(
                symbol="NVDA",
                score=88.5,
                residual_momentum_z=2.4,
                raw_12_1m_return_pct=45.0,
                near_52w_high=0.97,
                fip_id=-0.12,
                cash_op_profitability=0.28,
                accruals_ratio=-0.04,
                realized_vol_ann=0.35,
                vol_scale_weight=0.34,
                avg_dollar_volume=1_000_000_000.0,
                last_close=135.0,
                pead_score=18.0,
                insider_score=0.0,
                reasons=["ResidMom z=2.40 (+45.0%)"],
            )
        ],
    )
    us_res = client.post("/api/v1/alpha/us-screen", json={"top_n": 5})
    assert us_res.status_code == 200
    assert us_res.json()["count"] == 1
    assert us_res.json()["items"][0]["symbol"] == "NVDA"

    monkeypatch.setattr(
        "data_provider.sec_form4_fetcher.SecForm4Fetcher.fetch_live_purchases",
        lambda self, **kwargs: [
            InsiderClusterEvent(
                symbol="ACME",
                company_name="Acme Corp",
                filing_date=date(2026, 11, 10),
                insider_count=3,
                officer_director_count=3,
                total_value=450_000.0,
                total_shares=10_000.0,
                avg_price=45.0,
                has_c_level=True,
                is_opportunistic=True,
                is_cluster=True,
                cmp_class="opportunistic",
                has_10b51=False,
                primary_titles=["CEO", "CFO"],
                issuer_cik="0001234567",
            )
        ],
    )
    f4_res = client.get("/api/v1/alpha/form4-live")
    assert f4_res.status_code == 200
    assert f4_res.json()["items"][0]["symbol"] == "ACME"
    assert f4_res.json()["items"][0]["is_cluster"] is True

    monkeypatch.setattr(
        "src.services.pead_screener.screen_pead_candidates",
        lambda **kwargs: [
            PeadCandidate(
                symbol="AXON",
                company_name="Axon Enterprise",
                earnings_date="2026-11-05",
                days_since_earnings=5,
                eps_estimate=1.20,
                eps_reported=1.60,
                eps_surprise_pct=33.3,
                day1_return_pct=12.4,
                total_drift_pct=16.0,
                volume_surge_ratio=2.8,
                trend_regime="uptrend",
                conviction_tier="strong",
                score=85.0,
                reasons=["EPS Sürprizi +%33.3"],
                sue_score=3.1,
                revenue_growth_pct=28.0,
                near_52w_high=0.98,
                avg_dollar_volume=250_000_000.0,
                announcement_session="AMC",
            )
        ],
    )
    pead_res = client.get("/api/v1/alpha/pead-candidates?universe=midcap")
    assert pead_res.status_code == 200
    assert pead_res.json()["items"][0]["symbol"] == "AXON"

    monkeypatch.setattr(
        "src.services.bist_screener.screen_bist_stocks",
        lambda **kwargs: {
            "selected_codes": ["THYAO.IS"],
            "scanned_count": 500,
            "passed_count": 12,
            "candidates": [{"code": "THYAO.IS", "score": 78}],
            "errors": [],
        },
    )
    bist_res = client.post("/api/v1/alpha/bist-screen", json={"top_n": 5})
    assert bist_res.status_code == 200
    assert bist_res.json()["selected_codes"] == ["THYAO.IS"]

    monkeypatch.setattr(
        "src.services.kap_contract_screener.KapContractScreener.scan_recent_contracts",
        lambda self, **kwargs: [
            KapContractCandidate(
                symbol="ASELS.IS",
                ticker="ASELS",
                company_name="ASELSAN",
                disclosure_index="12345",
                published_date="2026-11-12",
                title="Yeni Sözleşme İmzalanması",
                contract_amount=50_000_000.0,
                contract_currency="USD",
                contract_amount_try=1_700_000_000.0,
                ttm_revenue_try=10_000_000_000.0,
                contract_to_revenue_pct=17.0,
                conviction_tier="STRONG",
                score=82,
                reasons=["Cironun %17.0'si"],
                url="https://kap.org.tr/tr/Bildirim/12345",
            )
        ],
    )
    kap_res = client.get("/api/v1/alpha/kap-contracts")
    assert kap_res.status_code == 200
    assert kap_res.json()["items"][0]["symbol"] == "ASELS.IS"
