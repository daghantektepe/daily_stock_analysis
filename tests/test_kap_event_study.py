# -*- coding: utf-8 -*-
"""Offline tests for the KAP historical event study and multi-window KAP fetcher helpers."""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from data_provider.kap_fetcher import KapDisclosureFetcher
from src.services.kap_event_study import (
    format_kap_event_study_report,
    run_kap_event_study,
)


def _build_trading_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    curr = start
    while len(days) < count:
        if curr.weekday() < 5:
            days.append(curr)
        curr += timedelta(days=1)
    return days


def test_event_study_respects_18h_cutoff_deduplicates_and_computes_excess_returns() -> None:
    trading_days = _build_trading_days(date(2026, 9, 1), 30)
    # Day index 1 = 2026-09-02 (Wednesday), Day index 2 = 2026-09-03 (Thursday).
    stock_closes = {day: 100.0 for day in trading_days}
    # On index 1 (entry for daytime contract filing): close is 102 (+2% day0).
    stock_closes[trading_days[1]] = 102.0
    stock_closes[trading_days[2]] = 105.06   # +3% at 1d from 102
    stock_closes[trading_days[6]] = 112.20   # +10% at 5d from 102
    stock_closes[trading_days[21]] = 122.40  # +20% at 20d from 102

    # Index 2 is also entry for after-hours buyback published on trading_days[1] at 19:15.
    stock_closes[trading_days[3]] = 107.1612  # +2% at 1d from 105.06
    stock_closes[trading_days[7]] = 110.313   # +5% at 5d from 105.06
    stock_closes[trading_days[22]] = 115.566  # +10% at 20d from 105.06

    # BIST 100 rises +1% over [1 -> 2], +2% over [1 -> 6], +5% over [1 -> 21].
    index_closes = {day: 10000.0 for day in trading_days}
    index_closes[trading_days[1]] = 10000.0
    index_closes[trading_days[2]] = 10100.0
    index_closes[trading_days[6]] = 10200.0
    index_closes[trading_days[21]] = 10500.0
    index_closes[trading_days[3]] = 10100.0
    index_closes[trading_days[7]] = 10100.0
    index_closes[trading_days[22]] = 10100.0

    def fake_history(symbol: str, start: date, end: date):
        source = index_closes if symbol == "XU100.IS" else stock_closes
        return {d: v for d, v in source.items() if start <= d <= end}

    class _FakeFetcher:
        def get_recent_disclosures(self, code: str, **_kwargs):
            return [
                # 1) Intraday contract filing at 11:00 on trading_days[1] -> enters at trading_days[1] close (102.0).
                {
                    "index": 10,
                    "ticker": "ASELS",
                    "published_at": datetime.combine(trading_days[1], datetime.min.time()).replace(hour=11, minute=0),
                    "published_date": f"{trading_days[1].isoformat()} 11:00",
                    "title": "Yeni Sözleşme İmzalanması",
                    "tags": ["contract"],
                },
                # Duplicate contract filing on the same session -> deduplicated.
                {
                    "index": 11,
                    "ticker": "ASELS",
                    "published_at": datetime.combine(trading_days[1], datetime.min.time()).replace(hour=14, minute=30),
                    "published_date": f"{trading_days[1].isoformat()} 14:30",
                    "title": "Ek Sözleşme Açıklaması",
                    "tags": ["contract"],
                },
                # 2) After-hours buyback filing at 19:15 on trading_days[1] -> enters at trading_days[2] close (105.06).
                {
                    "index": 12,
                    "ticker": "ASELS",
                    "published_at": datetime.combine(trading_days[1], datetime.min.time()).replace(hour=19, minute=15),
                    "published_date": f"{trading_days[1].isoformat()} 19:15",
                    "title": "Pay Geri Alım Programı",
                    "tags": ["buyback"],
                },
            ]

    study = run_kap_event_study(
        ["ASELS.IS", "AAPL"],
        days=90,
        horizons=(1, 5, 20),
        fetcher=_FakeFetcher(),
        history=fake_history,
        today=trading_days[-1],
    )
    assert study["stock_count"] == 1
    assert study["event_count"] == 2
    by_tag = {bucket["tag"]: bucket for bucket in study["by_tag"]}

    contract = by_tag["contract"]
    assert contract["event_count"] == 1
    assert contract["avg_day0_return_pct"] == pytest.approx(2.0)
    assert contract["horizons"]["1d"]["avg_return_pct"] == pytest.approx(3.0, abs=0.02)
    assert contract["horizons"]["1d"]["avg_excess_return_pct"] == pytest.approx(2.0, abs=0.02)
    assert contract["horizons"]["5d"]["avg_return_pct"] == pytest.approx(10.0, abs=0.02)
    assert contract["horizons"]["5d"]["avg_excess_return_pct"] == pytest.approx(8.0, abs=0.02)
    assert contract["horizons"]["20d"]["avg_return_pct"] == pytest.approx(20.0, abs=0.02)
    assert contract["horizons"]["20d"]["avg_excess_return_pct"] == pytest.approx(15.0, abs=0.02)
    assert contract["horizons"]["5d"]["beat_index_rate_pct"] == 100.0

    buyback = by_tag["buyback"]
    assert buyback["event_count"] == 1
    assert buyback["horizons"]["1d"]["avg_return_pct"] == pytest.approx(2.0, abs=0.02)
    assert buyback["horizons"]["5d"]["avg_return_pct"] == pytest.approx(5.0, abs=0.02)

    report = format_kap_event_study_report(study)
    assert "📊 KAP Olay Etkisi Analizi" in report
    assert "sözleşme/iş ilişkisi (n=1" in report
    assert "geri alım (n=1" in report
    assert "BIST 100 fark +8.00%" in report


def test_kap_fetcher_chunks_long_ranges_and_fetches_market_disclosures() -> None:
    companies = [{"mkkMemberOid": "oid-thy", "kapMemberTitle": "THY A.O.", "stockCode": "THYAO"}]
    post_Windows = []

    def fake_request(method, url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        if url.endswith("/company/items/IGS/A"):
            resp.json.return_value = companies
            return resp
        body = kwargs["json"]
        post_Windows.append((body["memberType"], body["mkkMemberOidList"], body["fromDate"], body["toDate"]))
        resp.json.return_value = [
            {
                "publishDate": "04.11.2026 10:00:00",
                "kapTitle": "THY A.O.",
                "disclosureClass": "ODA",
                "summary": "Pay Geri Alım Bildirimi",
                "subject": "Payların Geri Alınmasına İlişkin Bildirim",
                "disclosureIndex": 9001,
                "stockCodes": "THYAO",
            }
        ]
        return resp

    fetcher = KapDisclosureFetcher()
    with patch("data_provider.kap_fetcher.requests.request", side_effect=fake_request):
        items = fetcher.get_recent_disclosures("THYAO.IS", days=365, max_items=100, today=date(2026, 11, 6))
        market_map = fetcher.get_market_disclosures(days=2, today=date(2026, 11, 6))

    # 365 days is split into 3 chunks of <=180 days, deduplicated by disclosureIndex.
    assert len(items) == 1
    assert items[0]["index"] == 9001
    assert len([w for w in post_Windows if w[1] == ["oid-thy"]]) >= 2

    # Market-wide query uses memberType="IGS" and empty mkkMemberOidList.
    assert "THYAO.IS" in market_map
    assert market_map["THYAO.IS"][0]["tags"] == ["buyback"]
    assert post_Windows[-1][0] == "IGS" and post_Windows[-1][1] == []

