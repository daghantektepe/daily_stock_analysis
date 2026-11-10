# -*- coding: utf-8 -*-
"""Offline tests for the daily BIST (~800 stocks) screener."""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from src.services.bist_screener import (
    format_bist_screener_report,
    load_bist_universe,
    screen_bist_stocks,
)


def _make_bars(
    *,
    base_close: float = 100.0,
    last_close: float = 104.0,
    prev_close: float = 101.0,
    base_vol: float = 200_000.0,
    last_vol: float = 500_000.0,
    trend_step: float = 0.2,
):
    bars = []
    start = date(2026, 10, 1)
    for i in range(20):
        close = base_close + i * trend_step
        bars.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "close": close,
            "high": close * 1.005,
            "low": close * 0.995,
            "volume": base_vol,
        })
    bars[-1]["close"] = prev_close
    bars[-1]["high"] = prev_close * 1.005
    bars.append({
        "date": (start + timedelta(days=20)).isoformat(),
        "close": last_close,
        "high": last_close,
        "low": prev_close,
        "volume": last_vol,
    })
    return bars


def test_screener_ranks_catalyst_and_technical_breakout_while_penalizing_ceiling_and_breakers() -> None:
    universe = [
        {"symbol": "ASELS.IS", "name": "Aselsan"},
        {"symbol": "THYAO.IS", "name": "Türk Hava Yolları"},
        {"symbol": "TAVAN.IS", "name": "Tavan Hisse"},
        {"symbol": "SIKIS.IS", "name": "Devre Kesicili"},
        {"symbol": "SIKMA.IS", "name": "Sığ Tahta"},
    ]
    bars_map = {
        # 1) ASELS: strong trend + breakout + 2.5x volume + KAP contract catalyst
        "ASELS.IS": _make_bars(base_close=100.0, prev_close=103.5, last_close=105.0, base_vol=200_000, last_vol=500_000),
        # 2) THYAO: breakout + 2.0x volume, no KAP filing
        "THYAO.IS": _make_bars(base_close=200.0, prev_close=203.0, last_close=206.0, base_vol=150_000, last_vol=300_000),
        # 3) TAVAN: already up +9.8% (near +10% BIST ceiling) -> anti-chase penalty
        "TAVAN.IS": _make_bars(base_close=50.0, prev_close=50.0, last_close=54.9, base_vol=200_000, last_vol=220_000, trend_step=0.0),
        # 4) SIKIS: has circuit_breaker KAP warning -> penalized
        "SIKIS.IS": _make_bars(base_close=80.0, prev_close=80.0, last_close=80.2, base_vol=200_000, last_vol=220_000, trend_step=0.0),
        # 5) SIKMA: daily turnover only 50,000 TRY (< 5,000,000 TRY) -> skipped as illiquid
        "SIKMA.IS": _make_bars(base_close=10.0, prev_close=10.2, last_close=10.5, base_vol=2_000, last_vol=4_000),
    }

    class _FakeKapFetcher:
        def get_market_disclosures(self, **_kwargs):
            return {
                "ASELS.IS": [{"index": 1, "title": "Yeni İhracat Sözleşmesi", "tags": ["contract"]}],
                "SIKIS.IS": [{"index": 2, "title": "Pay Bazında Devre Kesici", "tags": ["circuit_breaker"]}],
            }

    result = screen_bist_stocks(
        universe=universe,
        top_n=5,
        min_score=25.0,
        bars_provider=lambda _symbols: bars_map,
        kap_fetcher=_FakeKapFetcher(),
    )

    assert result["universe_count"] == 5
    assert result["selected_codes"] == ["ASELS.IS", "THYAO.IS"]
    first, second = result["candidates"]
    assert first["stock_code"] == "ASELS.IS"
    assert first["score"] > second["score"]
    assert "yeni KAP: sözleşme/iş ilişkisi" in first["reasons"]
    assert "20g zirve kırılımı" in first["reasons"]

    report = format_bist_screener_report(result)
    assert "🔍 BIST Günlük Tarama Özeti" in report
    assert "1. ASELS.IS (Aselsan)" in report
    assert "KAP: Yeni İhracat Sözleşmesi" in report


def test_load_bist_universe_reads_seed_csv() -> None:
    universe = load_bist_universe()
    assert len(universe) >= 700
    symbols = {item["symbol"] for item in universe}
    assert "THYAO.IS" in symbols and "ASELS.IS" in symbols


def test_main_bist_screener_hook_selects_or_falls_back() -> None:
    from main import _resolve_bist_screener_codes

    cfg_off = SimpleNamespace(bist_screener_enabled=False, bist_screener_top_n=6)
    args_off = SimpleNamespace(screen_bist=False)
    assert _resolve_bist_screener_codes(cfg_off, args_off) is None

    cfg_on = SimpleNamespace(bist_screener_enabled=True, bist_screener_top_n=6)
    with patch(
        "src.services.bist_screener.screen_bist_stocks",
        return_value={"selected_codes": ["ASELS.IS", "THYAO.IS"], "candidates": []},
    ):
        assert _resolve_bist_screener_codes(cfg_on, args_off) == ["ASELS.IS", "THYAO.IS"]

    with patch("src.services.bist_screener.screen_bist_stocks", return_value={"selected_codes": [], "candidates": []}):
        assert _resolve_bist_screener_codes(cfg_on, args_off) is None

