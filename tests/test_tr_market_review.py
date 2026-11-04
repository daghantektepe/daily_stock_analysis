# -*- coding: utf-8 -*-
"""Tests for the Borsa Istanbul market review region (MARKET_REVIEW_REGION=tr)."""

from unittest.mock import MagicMock

import pytest

from data_provider.yfinance_fetcher import YfinanceFetcher
from src.core.market_profile import get_profile
from src.core.market_review import _resolve_market_review_regions
from src.core.market_strategy import get_market_strategy_blueprint
from src.core.trading_calendar import compute_effective_region
from src.market_analyzer import MarketAnalyzer
from src.utils.market_review_region import (
    MARKET_REVIEW_REGION_ALL,
    normalize_market_review_region_lenient,
    normalize_market_review_region_strict,
)


def test_both_keeps_legacy_five_markets_and_tr_is_opt_in() -> None:
    assert MARKET_REVIEW_REGION_ALL == "cn,hk,us,jp,kr"
    assert normalize_market_review_region_lenient("both") == "cn,hk,us,jp,kr"
    assert normalize_market_review_region_lenient("tr") == "tr"
    assert normalize_market_review_region_lenient("tr,us") == "us,tr"
    assert normalize_market_review_region_strict("us,tr") == "us,tr"
    assert normalize_market_review_region_strict("both") == "cn,hk,us,jp,kr"
    with pytest.raises(ValueError):
        normalize_market_review_region_strict("both,tr")
    assert _resolve_market_review_regions("tr") == ["tr"]


def test_effective_region_uses_istanbul_trading_days() -> None:
    assert compute_effective_region("tr", {"tr"}) == "tr"
    assert compute_effective_region("tr", {"us"}) == ""
    assert compute_effective_region("us,tr", {"us", "tr"}) == "us,tr"
    assert compute_effective_region("both", {"cn", "tr"}) == "cn"


def test_tr_profile_and_strategy() -> None:
    profile = get_profile("tr")
    assert profile.region == "tr"
    assert profile.mood_index_code == "XU100"
    assert any("BIST" in query for query in profile.news_queries)
    assert profile.has_market_stats is False
    blueprint = get_market_strategy_blueprint("tr")
    assert blueprint.region == "tr"
    assert "BIST 100" in blueprint.positioning


def test_yfinance_tr_indices_include_bist_and_usdtry() -> None:
    fetcher = YfinanceFetcher()
    captured = []

    def fake_fetch(_yf, yf_code, name, return_code):
        captured.append((yf_code, return_code))
        return {"code": return_code, "name": name, "current": 1.0}

    fetcher._fetch_yf_ticker_data = fake_fetch  # type: ignore[method-assign]
    indices = fetcher.get_main_indices("tr") or []

    assert [item["code"] for item in indices] == ["XU100", "XU030", "XBANK", "USDTRY"]
    assert ("XU100.IS", "XU100") in captured
    assert ("TRY=X", "USDTRY") in captured


@pytest.mark.parametrize("language", ["en", "tr"])
def test_market_analyzer_tr_region_uses_turkey_scaffolding(language: str) -> None:
    config = MagicMock()
    config.report_language = language
    config.market_review_color_scheme = "green_up"
    analyzer = MarketAnalyzer(region="tr", config=config)

    assert analyzer.region == "tr"
    assert analyzer._get_market_scope_name("en") == "Turkey (Borsa Istanbul) market"
    assert analyzer._get_market_scope_name("zh") == "土耳其市场"
    assert analyzer._get_review_title("2026-11-04") == "## 2026-11-04 Turkey Market Recap"
    assert "USD/TRY" in analyzer._get_index_hint()
    assert "Turkey Market Regime Strategy" in analyzer._get_strategy_prompt_block()
    assert "USD/TRY" in analyzer._get_strategy_markdown_block()
    assert analyzer._get_turnover_unit_label() == "TRY bn"


def test_index_change_uses_previous_session_from_wider_window() -> None:
    import pandas as pd

    class _Ticker:
        def __init__(self, _code):
            pass

        def history(self, period):
            assert period == "5d"
            return pd.DataFrame(
                {
                    "Open": [10900.0, 10950.0],
                    "High": [11000.0, 11050.0],
                    "Low": [10800.0, 10900.0],
                    "Close": [10921.1, 11023.6],
                    "Volume": [1, 2],
                }
            )

    yf_stub = MagicMock()
    yf_stub.Ticker = _Ticker
    item = YfinanceFetcher()._fetch_yf_ticker_data(yf_stub, "XU100.IS", "BIST 100", "XU100")

    assert item["prev_close"] == 10921.1
    assert round(item["change_pct"], 3) == round((11023.6 - 10921.1) / 10921.1 * 100, 3)
