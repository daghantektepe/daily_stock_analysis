# -*- coding: utf-8 -*-
"""Regression tests for Borsa Istanbul (``.IS``) suffix-only market support."""

from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from data_provider.base import (
    BaseFetcher,
    DataFetchError,
    DataFetcherManager,
    _market_tag,
    normalize_stock_code,
)
from data_provider.yfinance_fetcher import YfinanceFetcher
from src.core.trading_calendar import (
    MARKET_EXCHANGE,
    MARKET_TIMEZONE,
    build_market_phase_context,
    get_market_for_stock,
    is_market_open,
)
from src.market_context import detect_market, get_market_guidelines, get_market_role
from src.services.decision_signal_reassess_service import _infer_market
from src.services.market_symbol_utils import get_suffix_market, is_tr_suffix_symbol
from src.services.portfolio_service import PortfolioService
from src.services.stock_code_utils import (
    canonical_stock_code,
    is_code_like,
    normalize_code,
    resolve_daily_stock_identity,
)
from src.services.stock_list_parser import ParseStatus, parse_analysis_target
from src.share_image import _stock_heading_entry


class _FakeFetcher(BaseFetcher):
    def __init__(self, name: str, should_fail: bool = False):
        self.name = name
        self.priority = 0 if name != "YfinanceFetcher" else 4
        self.calls = []
        self.should_fail = should_fail

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        raise NotImplementedError

    def get_daily_data(self, stock_code, start_date=None, end_date=None, days=30):
        self.calls.append(stock_code)
        if self.should_fail:
            raise DataFetchError(f"{self.name} should not be called for {stock_code}")
        return pd.DataFrame(
            {
                "date": [pd.Timestamp("2026-11-04")],
                "open": [271.75],
                "high": [291.5],
                "low": [270.0],
                "close": [290.0],
                "volume": [1000],
                "amount": [290000.0],
                "pct_chg": [6.7],
            }
        )


def test_normalize_and_detect_bist_suffix_codes() -> None:
    assert normalize_stock_code("thyao.is") == "THYAO.IS"
    assert normalize_stock_code("A1CAP.IS") == "A1CAP.IS"
    assert normalize_stock_code("XU100.IS") == "XU100.IS"

    for code in ("THYAO.IS", "ASELS.IS", "A1CAP.IS", "XU100.IS"):
        assert get_suffix_market(code) == "tr"
        assert is_tr_suffix_symbol(code) is True
        assert _market_tag(code) == "tr"
        assert detect_market(code) == "tr"
        assert get_market_for_stock(code) == "tr"
        assert is_code_like(code) is True
        assert normalize_code(code) == code
        assert canonical_stock_code(code) == code


def test_bist_rules_reject_invalid_bases_and_keep_bare_tickers_as_us() -> None:
    # Bases must start with a letter and be 3-6 alphanumeric characters.
    for code in ("1234.IS", "AB.IS", "ABCDEFG.IS"):
        assert get_suffix_market(code) is None
        assert normalize_code(code) is None
        assert is_code_like(code) is False

    # Without the explicit suffix the ticker stays in the US namespace.
    assert get_suffix_market("THYAO") is None
    assert detect_market("THYAO") == "us"


def test_existing_suffix_markets_are_unchanged() -> None:
    assert get_suffix_market("7203.T") == "jp"
    assert get_suffix_market("005930.KS") == "kr"
    assert get_suffix_market("2330.TW") == "tw"
    assert detect_market("AAPL") == "us"
    assert detect_market("600519") == "cn"


def test_daily_identity_keeps_bist_suffix_only() -> None:
    identity = resolve_daily_stock_identity("thyao.is")

    assert identity is not None
    assert identity.market == "tr"
    assert identity.normalized_code == "THYAO.IS"
    assert identity.code_candidates == ("THYAO.IS",)


def test_stock_list_parser_assigns_istanbul_exchange() -> None:
    target = parse_analysis_target("thyao.is")
    assert target.asset_type == ParseStatus.STOCK
    assert target.canonical_id == "THYAO.IS"
    assert target.exchange == "IS"

    rejected = parse_analysis_target("1234.IS")
    assert rejected.asset_type == ParseStatus.UNSUPPORTED
    assert rejected.exchange == "IS"
    assert "Borsa Istanbul" in (rejected.unsupported_reason or "")


def test_yfinance_passes_bist_symbols_through() -> None:
    fetcher = YfinanceFetcher()

    assert fetcher._convert_stock_code("THYAO.IS") == "THYAO.IS"
    assert fetcher._convert_stock_code("XU100.IS") == "XU100.IS"
    assert fetcher._is_tr_suffix_stock("THYAO.IS") is True
    assert fetcher._is_tr_suffix_stock("AAPL") is False


def test_data_fetcher_manager_routes_bist_daily_only_to_yfinance() -> None:
    efinance = _FakeFetcher("EfinanceFetcher", should_fail=True)
    akshare = _FakeFetcher("AkshareFetcher", should_fail=True)
    yfinance = _FakeFetcher("YfinanceFetcher")
    manager = DataFetcherManager(fetchers=[efinance, akshare, yfinance])

    with patch("data_provider.base.record_provider_run_started"), patch("data_provider.base.record_provider_run"):
        df, source = manager.get_daily_data("THYAO.IS")

    assert source == "YfinanceFetcher"
    assert not df.empty
    assert efinance.calls == []
    assert akshare.calls == []
    assert yfinance.calls == ["THYAO.IS"]


def test_trading_calendar_registers_borsa_istanbul() -> None:
    assert MARKET_EXCHANGE["tr"] == "XIST"
    assert MARKET_TIMEZONE["tr"] == "Europe/Istanbul"

    # 2026-10-29 is Republic Day (market holiday); 2026-11-07 is a Saturday.
    assert is_market_open("tr", date(2026, 10, 29)) is False
    assert is_market_open("tr", date(2026, 11, 4)) is True
    assert is_market_open("tr", date(2026, 11, 7)) is False


def test_bist_market_phase_follows_istanbul_session() -> None:
    tz = ZoneInfo("Europe/Istanbul")
    cases = (
        (datetime(2026, 11, 4, 9, 30, tzinfo=tz), "premarket"),
        (datetime(2026, 11, 4, 12, 0, tzinfo=tz), "intraday"),
        (datetime(2026, 11, 4, 17, 59, tzinfo=tz), "intraday"),
        (datetime(2026, 11, 4, 18, 5, tzinfo=tz), "postmarket"),
    )
    for current_time, expected in cases:
        context = build_market_phase_context(market="tr", current_time=current_time).to_dict()
        assert context["phase"] == expected, current_time


def test_market_guidelines_for_bist_use_turkey_context() -> None:
    zh = get_market_guidelines("THYAO.IS", lang="zh")
    en = get_market_guidelines("THYAO.IS", lang="en")

    assert "土耳其股" in zh
    assert "TCMB" in zh and "KAP" in zh
    assert "Borsa Istanbul" in en
    assert "TRY" in en and "TCMB" in en and "KAP" in en
    assert "do not apply China A-share" in en
    # Turkish/Korean reports reuse the English structural guidelines.
    assert get_market_guidelines("THYAO.IS", lang="tr") == en
    assert get_market_role("THYAO.IS", lang="tr") == "Turkey (Borsa Istanbul) stock"


def test_portfolio_defaults_bist_accounts_to_try() -> None:
    assert PortfolioService._default_currency_for_market("tr") == "TRY"
    assert PortfolioService._default_currency_for_market("jp") == "CNY"


def test_decision_signal_reassess_infers_tr_market() -> None:
    assert _infer_market("THYAO.IS") == "tr"
    assert _infer_market("2330.TW") == "tw"


def test_share_image_heading_extracts_bist_code() -> None:
    assert _stock_heading_entry("🟢 Türk Hava Yolları (THYAO.IS)") == ("Türk Hava Yolları", "THYAO.IS")
    assert _stock_heading_entry("Apple (AAPL)") == ("Apple", "AAPL")


def test_try_amounts_are_not_labelled_as_rmb() -> None:
    from src.notification import NotificationService

    assert NotificationService._format_amount_cn(250_000_000.0, "TRY") == "2.50 亿土耳其里拉"
    assert NotificationService._format_amount_cn(250_000_000.0, "CNY") == "2.50 亿元"


class _NamedFetcher(_FakeFetcher):
    def get_stock_name(self, stock_code):
        self.calls.append(("name", stock_code))
        if self.should_fail:
            raise DataFetchError(f"{self.name} must not resolve names for {stock_code}")
        return "Should not be used"


def test_stock_name_lookup_skips_a_share_sources_for_bist() -> None:
    baostock = _NamedFetcher("BaostockFetcher", should_fail=True)
    akshare = _NamedFetcher("AkshareFetcher", should_fail=True)
    manager = DataFetcherManager(fetchers=[baostock, akshare])

    # Keep the test offline: KAP (the BIST name source) has no answer here.
    with patch("data_provider.kap_fetcher.get_kap_fetcher") as kap:
        kap.return_value.get_company_title.return_value = None
        # A ticker that is not in the autocomplete index, so no static name exists.
        assert manager.get_stock_name("ZZNOA.IS", allow_realtime=False) == ""
    assert baostock.calls == []
    assert akshare.calls == []
