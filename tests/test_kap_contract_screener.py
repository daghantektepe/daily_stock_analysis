# -*- coding: utf-8 -*-
"""Unit tests for Borsa Istanbul KAP Contract Screener."""

from __future__ import annotations

import pytest

from src.services.kap_contract_screener import (
    KapContractCandidate,
    KapContractScreener,
    extract_counterparty,
    format_kap_contract_report,
    parse_contract_amount,
    parse_contract_revenue_ratio,
    score_contract_candidate,
)


def test_parse_contract_amount_various_formats() -> None:
    # 1. Standard TRY with dots
    amt, curr = parse_contract_amount("Toplam sözleşme bedeli 125.000.000 TL olarak belirlenmiştir.")
    assert amt == 125_000_000.0
    assert curr == "TRY"

    # 2. USD with comma decimal
    amt_usd, curr_usd = parse_contract_amount("Sözleşme tutarı 45.500.000 USD (KDV hariç)")
    assert amt_usd == 45_500_000.0
    assert curr_usd == "USD"

    # 3. EUR / Avro
    amt_eur, curr_eur = parse_contract_amount("İhale bedeli 8.250.000 Avro")
    assert amt_eur == 8_250_000.0
    assert curr_eur == "EUR"

    # 4. Textual million format
    amt_mil, curr_mil = parse_contract_amount("Proje büyüklüğü 75 milyon TL tutarındadır.")
    assert amt_mil == 75_000_000.0
    assert curr_mil == "TRY"


def test_parse_contract_revenue_ratio() -> None:
    # Explicit percentage with hasılat
    r1 = parse_contract_revenue_ratio("Sözleşme tutarının 2024 yılı hasılatına oranı: % 38,5")
    assert r1 == 38.5

    # Ciroya oranı
    r2 = parse_contract_revenue_ratio("İşlemin ciroya oranı %54.2 olarak hesaplanmıştır.")
    assert r2 == 54.2

    # Oranı: % 15
    r3 = parse_contract_revenue_ratio("Sözleşmenin son yıllık gelire oranı % 12,4'tür.")
    assert r3 == 12.4

    # None if missing
    r4 = parse_contract_revenue_ratio("Yeni bir iş ilişkisine başlanmıştır.")
    assert r4 is None


def test_extract_counterparty() -> None:
    text = "İşlemin Konusu: Radar Sistemi | Karşı Taraf: T.C. Cumhurbaşkanlığı Savunma Sanayii Başkanlığı | Tutar: 100M"
    cp = extract_counterparty(text)
    assert cp is not None
    assert "Savunma Sanayii" in cp


def test_score_contract_candidate() -> None:
    # 1. Mega catalyst (ratio >= 50%) + large size + Defense counterparty
    score_mega, tier_mega, reasons_mega = score_contract_candidate(
        contract_amount_try=600_000_000.0,
        ratio_pct=55.0,
        counterparty="Savunma Sanayii Başkanlığı",
        text="Savunma Sanayii ile sözleşme imzalandı.",
    )
    assert tier_mega == "MEGA"
    assert score_mega >= 80  # 55 (ratio) + 20 (size) + 10 (defense) = 85
    assert any("Oyun Değiştirici" in r for r in reasons_mega)

    # 2. Strong catalyst (ratio 25%-50%)
    score_str, tier_str, reasons_str = score_contract_candidate(
        contract_amount_try=150_000_000.0,
        ratio_pct=30.0,
        counterparty="Özel Müşteri",
        text="Kurulum sözleşmesi",
    )
    assert tier_str == "STRONG"
    assert score_str >= 50
    assert any("Yüksek Gelir Katalizörü" in r for r in reasons_str)

    # 3. Minor contract (ratio < 10%)
    score_min, tier_min, reasons_min = score_contract_candidate(
        contract_amount_try=5_000_000.0,
        ratio_pct=4.0,
        counterparty="Müşteri A.Ş.",
        text="Küçük bakım",
    )
    assert tier_min == "MINOR"
    assert score_min < 40


def test_kap_contract_screener_mocked() -> None:
    class MockKapFetcher:
        def get_market_disclosures(self, days: int = 5):
            return {
                "MIATK.IS": [
                    {
                        "index": 12345,
                        "title": "Yeni İş İlişkisi",
                        "subject": "Yeni İş İlişkisi",
                        "tags": ["contract"],
                        "publisher": "Mia Teknoloji A.Ş.",
                        "published_date": "2026-11-09 17:30",
                        "url": "https://www.kap.org.tr/tr/Bildirim/12345",
                    }
                ],
                "THYAO.IS": [
                    {
                        "index": 67890,
                        "title": "Uçak Alımı",
                        "subject": "Filo Genişlemesi",
                        "tags": [],
                        "publisher": "THY",
                        "published_date": "2026-11-08 10:00",
                        "url": "https://www.kap.org.tr/tr/Bildirim/67890",
                    }
                ],
            }

        def get_disclosure_details(self, index: int) -> str:
            if index == 12345:
                return (
                    "İşlemin Konusu: Akıllı Şehir Altyapı Projesi | "
                    "İşlemin Tutarı: 25.000.000 USD | "
                    "Sözleşmenin 2024 yılı hasılatına oranı: % 42,0 | "
                    "Karşı Taraf: Yurt Dışı Kamu Kurumu"
                )
            return ""

    screener = KapContractScreener(
        kap_fetcher=MockKapFetcher(),
        fx_rates={"USD": 38.0, "EUR": 40.0, "TRY": 1.0},
    )

    candidates = screener.scan_recent_contracts(days=5, min_score=40, top_n=5)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.symbol == "MIATK.IS"
    assert c.ticker == "MIATK"
    assert c.contract_amount == 25_000_000.0
    assert c.contract_currency == "USD"
    assert c.contract_amount_try == 950_000_000.0
    assert c.contract_to_revenue_pct == 42.0
    assert c.conviction_tier == "STRONG"
    assert c.score >= 60

    report = format_kap_contract_report(candidates)
    assert "MIATK.IS" in report
    assert "25,000,000 USD" in report
    assert "%42.0" in report
    assert "python main.py --stocks MIATK.IS" in report
