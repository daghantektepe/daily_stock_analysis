# -*- coding: utf-8 -*-
"""Offline tests for TCMB EVDS2 macro fetcher, caching, TRY=X fallback, and purchasing-power math."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi.testclient import TestClient
import pandas as pd
import pytest

from api.app import create_app
from data_provider.evds_fetcher import (
    CPI_INDEX_SERIES,
    EvdsMacroFetcher,
    USD_TRY_SERIES,
    compute_real_purchase_power_tr,
)


class _FakeHttpResponse:
    def __init__(self, status_code: int, payload: Dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> Dict[str, Any]:
        return self._payload


class _FakeEvdsSession:
    def __init__(self) -> None:
        self.headers_seen: List[Dict[str, str]] = []

    def get(self, url: str, headers: Dict[str, str], timeout: float = 12.0) -> _FakeHttpResponse:
        self.headers_seen.append(dict(headers))
        if USD_TRY_SERIES in url:
            return _FakeHttpResponse(
                200,
                {
                    "items": [
                        {"Tarih": "01-11-2025", "TP_DK_USD_S_YTL": "40.00"},
                        {"Tarih": "20-11-2026", "TP_DK_USD_S_YTL": "50.00"},
                    ]
                },
            )
        if CPI_INDEX_SERIES in url:
            items = [{"Tarih": f"2025-{m:02d}", "TP_FG_J0": str(1000.0 + m * 20)} for m in range(1, 13)]
            items.append({"Tarih": "2026-01", "TP_FG_J0": "1530.0"})  # vs 1020.0 (13 pts -> 50% YoY)
            return _FakeHttpResponse(200, {"items": items})
        return _FakeHttpResponse(404, {})


def test_real_purchasing_power_exact_fisher_math() -> None:
    # +50% nominal TRY when USD/TRY rises +25% and TÜFE CPI is +50% -> +20% USD, 0% real
    out = compute_real_purchase_power_tr(
        nominal_return_pct=50.0,
        usd_try_change_pct=25.0,
        cpi_yoy_pct=50.0,
    )
    assert out["nominal_return_pct"] == pytest.approx(50.0)
    assert out["usd_based_return_pct"] == pytest.approx(20.0)
    assert out["real_tufe_return_pct"] == pytest.approx(0.0)
    assert out["beats_inflation"] is False

    out_beat = compute_real_purchase_power_tr(
        nominal_return_pct=65.0,
        usd_try_change_pct=25.0,
        cpi_yoy_pct=50.0,
    )
    assert out_beat["real_tufe_return_pct"] == pytest.approx(10.0)
    assert out_beat["beats_inflation"] is True


def test_evds_fetcher_uses_header_auth_and_caches(tmp_path: Path) -> None:
    sess = _FakeEvdsSession()
    cache_file = tmp_path / "evds.json"
    fetcher = EvdsMacroFetcher(api_key="evds-demo-key", cache_path=cache_file, session=sess)

    snap = fetcher.get_macro_snapshot()
    assert snap["evds_configured"] is True
    assert snap["usd_try"] == pytest.approx(50.0)
    assert snap["usd_try_1y_change_pct"] == pytest.approx(25.0)
    assert snap["usd_try_source"] == "tcmb_evds2"
    assert snap["cpi_yoy_pct"] == pytest.approx(50.0)
    assert snap["cpi_source"] == "tcmb_evds2"
    assert snap["cached"] is False
    assert all(h.get("key") == "evds-demo-key" for h in sess.headers_seen)

    # Cached response skips HTTP
    calls_before = len(sess.headers_seen)
    snap2 = fetcher.get_macro_snapshot()
    assert snap2["cached"] is True
    assert len(sess.headers_seen) == calls_before


def test_evds_fetcher_degrades_gracefully_without_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeTryTicker:
        def history(self, period: str = "1y", auto_adjust: bool = True):
            return pd.DataFrame(
                {"Close": [40.0, 50.0]},
                index=pd.DatetimeIndex(["2025-11-20", "2026-11-20"]),
            )

    monkeypatch.setattr("yfinance.Ticker", lambda sym: _FakeTryTicker())
    fetcher = EvdsMacroFetcher(api_key=None, cache_path=tmp_path / "evds.json")
    snap = fetcher.get_macro_snapshot()
    assert snap["evds_configured"] is False
    assert snap["usd_try"] == pytest.approx(50.0)
    assert snap["usd_try_source"] == "yahoo_try_x_fallback"
    assert snap["cpi_yoy_pct"] is None
    assert snap["cpi_source"] == "unavailable"


def test_bridges_macro_tr_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "api.v1.endpoints.bridges.EvdsMacroFetcher.get_macro_snapshot",
        lambda self, force_refresh=False: {
            "evds_configured": True,
            "usd_try": 50.0,
            "usd_try_1y_change_pct": 25.0,
            "usd_try_as_of": "20-11-2026",
            "usd_try_source": "tcmb_evds2",
            "cpi_yoy_pct": 35.0,
            "cpi_mom_pct": 2.1,
            "cpi_as_of": "2026-10",
            "cpi_source": "tcmb_evds2",
            "cached": False,
        },
    )
    app = create_app()
    client = TestClient(app)
    res = client.get("/api/v1/bridges/macro-tr?nominal_return_pct=50")
    assert res.status_code == 200
    data = res.json()
    assert data["usd_try"] == pytest.approx(50.0)
    assert data["purchasing_power"]["usd_based_return_pct"] == pytest.approx(20.0)
    assert data["purchasing_power"]["beats_inflation"] is True
