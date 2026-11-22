# -*- coding: utf-8 -*-
"""Tests for Midas BIST/US, Binance Spot, Generic TR CSV/XLSX imports and templates."""

from __future__ import annotations

import io
from datetime import date

from fastapi.testclient import TestClient
import pandas as pd
import pytest

from api.app import create_app
from src.services.portfolio_import_service import PortfolioImportService


@pytest.fixture()
def importer() -> PortfolioImportService:
    # Ensure shared registry reflects current DEFAULT_PARSER_SPECS even if earlier tests loaded it
    PortfolioImportService._shared_registry_initialized = False
    PortfolioImportService._shared_parser_registry.clear()
    PortfolioImportService._shared_broker_alias_map.clear()
    return PortfolioImportService()


def test_supported_brokers_include_midas_binance_and_generic_tr(importer: PortfolioImportService) -> None:
    items = importer.list_supported_brokers()
    by_id = {item["broker"]: item for item in items}
    for key in ("midas_bist", "midas_us", "binance_spot", "generic_tr", "huatai", "citic", "cmb"):
        assert key in by_id


def test_parse_midas_bist_semicolon_csv_with_turkish_dates_and_commas(importer: PortfolioImportService) -> None:
    csv_text = (
        "İşlem Tarihi;Hisse Kodu;İşlem Türü;Adet;Birim Fiyat;Komisyon;Referans No\n"
        "20.11.2026;THYAO;Alış;10;312,50;1,25;MDS-1\n"
        "21.11.2026;TUPRS.IS;Satış;5;1.250,40;2,10;MDS-2\n"
    )
    parsed = importer.parse_trade_csv(broker="midas", content=csv_text.encode("utf-8-sig"))
    assert parsed["broker"] == "midas_bist"
    assert parsed["record_count"] == 2
    r0, r1 = parsed["records"]
    assert r0["trade_date"] == date(2026, 11, 20)
    assert r0["symbol"] == "THYAO.IS"
    assert r0["side"] == "buy"
    assert r0["quantity"] == pytest.approx(10.0)
    assert r0["price"] == pytest.approx(312.50)
    assert r0["fee"] == pytest.approx(1.25)
    assert r0["currency"] == "TRY"

    assert r1["trade_date"] == date(2026, 11, 21)
    assert r1["symbol"] == "TUPRS.IS"
    assert r1["side"] == "sell"
    assert r1["price"] == pytest.approx(1250.40)


def test_parse_midas_us_and_binance_spot_csv(importer: PortfolioImportService) -> None:
    us_csv = (
        "Transaction Date,Ticker,Side,Shares,Execution Price,Fee,Order ID\n"
        "2026-11-20,BIL,Buy,20,91.50,1.50,US-1\n"
        "2026-11-21,SPY,Sell,2,590.25,1.50,US-2\n"
    )
    parsed_us = importer.parse_trade_csv(broker="midas_us", content=us_csv.encode("utf-8"))
    assert parsed_us["record_count"] == 2
    assert parsed_us["records"][0]["symbol"] == "BIL"
    assert parsed_us["records"][0]["currency"] == "USD"

    binance_csv = (
        "Date(UTC),Pair,Side,Price,Executed,Fee,Order ID\n"
        "2026-11-20 14:30:00,BTC/USDT,BUY,88500.00,0.015BTC,1.32USDT,B-1\n"
    )
    parsed_bnc = importer.parse_trade_csv(broker="binance", content=binance_csv.encode("utf-8"))
    assert parsed_bnc["broker"] == "binance_spot"
    assert parsed_bnc["record_count"] == 1
    assert parsed_bnc["records"][0]["symbol"] == "BTCUSDT"
    assert parsed_bnc["records"][0]["quantity"] == pytest.approx(0.015)
    assert parsed_bnc["records"][0]["price"] == pytest.approx(88500.0)
    assert parsed_bnc["records"][0]["currency"] == "USDT"


def test_parse_xlsx_excel_workbook_with_openpyxl(importer: PortfolioImportService) -> None:
    df = pd.DataFrame(
        [
            {
                "Tarih": "18.11.2026",
                "Kod": "ASELS",
                "İşlem": "AL",
                "Adet": "25",
                "Fiyat": "72,40",
                "Komisyon": "1,00",
                "Para Birimi": "TRY",
                "İşlem No": "XLS-1",
            }
        ]
    )
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    parsed = importer.parse_trade_csv(broker="midas_bist", content=buf.getvalue())
    assert parsed["record_count"] == 1
    assert parsed["records"][0]["symbol"] == "ASELS.IS"
    assert parsed["records"][0]["price"] == pytest.approx(72.40)


def test_portfolio_csv_template_download_endpoint() -> None:
    PortfolioImportService._shared_registry_initialized = False
    PortfolioImportService._shared_parser_registry.clear()
    PortfolioImportService._shared_broker_alias_map.clear()

    app = create_app()
    client = TestClient(app)
    res = client.get("/api/v1/portfolio/imports/csv/template?broker=midas_bist")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "THYAO" in res.text
