# -*- coding: utf-8 -*-
"""Offline tests for the KAP (Borsa Istanbul) disclosure fetcher and its wiring."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

from data_provider.kap_fetcher import (
    KapDisclosureFetcher,
    _parse_kap_datetime,
    format_kap_disclosure_context,
)
from src.search_service import SearchService

_COMPANIES = [
    {
        "mkkMemberOid": "oid-thy",
        "kapMemberTitle": "TÜRK HAVA YOLLARI A.O.",
        "stockCode": "THYAO",
    },
    {
        "mkkMemberOid": "oid-isbank",
        "kapMemberTitle": "TÜRKİYE İŞ BANKASI A.Ş.",
        "stockCode": "ISATR, ISBTR, ISCTR",
    },
    {"mkkMemberOid": "", "kapMemberTitle": "No OID", "stockCode": "NOOID"},
    "not-a-dict",
]

_DISCLOSURES = [
    {
        "publishDate": "04.11.2026 08:01:00",
        "kapTitle": "TÜRK HAVA YOLLARI A.O.",
        "disclosureClass": "ODA",
        "summary": "2026 3. Çeyrek Finansal Sonuçlar",
        "subject": "Özel Durum Açıklaması (Genel)",
        "disclosureIndex": 1691986,
        "isLate": False,
    },
    {
        "publishDate": "26.10.2026 15:45:00",
        "kapTitle": "TÜRK HAVA YOLLARI A.O.",
        "disclosureClass": "FR",
        "summary": "",
        "subject": "Finansal Rapor",
        "disclosureIndex": 1687401,
        "isLate": True,
    },
    {
        # Settlement noise from another institution: must be skipped.
        "publishDate": "04.11.2026 12:46:41",
        "kapTitle": "İSTANBUL TAKAS VE SAKLAMA BANKASI A.Ş.",
        "disclosureClass": "DKB",
        "summary": "Temerrüt İşleminin Tamamlanması",
        "disclosureIndex": 1692139,
    },
    {"publishDate": "bad", "disclosureClass": "ODA", "summary": "x", "disclosureIndex": 1},
]


def _response(payload):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def _fake_request(method, url, **_kwargs):
    if url.endswith("/company/items/IGS/A"):
        return _response(_COMPANIES)
    if url.endswith("/disclosure/members/byCriteria"):
        return _response(_DISCLOSURES)
    raise AssertionError(f"unexpected url {url}")


def test_company_list_maps_share_classes_and_skips_bad_rows() -> None:
    table = KapDisclosureFetcher._parse_company_list(_COMPANIES)

    assert table["THYAO"] == {"mkk_member_oid": "oid-thy", "title": "TÜRK HAVA YOLLARI A.O."}
    assert table["ISCTR"]["mkk_member_oid"] == "oid-isbank"
    assert table["ISATR"]["mkk_member_oid"] == "oid-isbank"
    assert "NOOID" not in table
    assert KapDisclosureFetcher._parse_company_list({"unexpected": "shape"}) == {}


def test_recent_disclosures_keep_company_filings_newest_first() -> None:
    fetcher = KapDisclosureFetcher()
    with patch("data_provider.kap_fetcher.requests.request", side_effect=_fake_request) as mocked:
        items = fetcher.get_recent_disclosures("thyao.is", days=14, today=date(2026, 11, 4))

    assert [item["index"] for item in items] == [1691986, 1687401]
    first, second = items
    assert first["title"] == "2026 3. Çeyrek Finansal Sonuçlar"
    assert first["class_label"] == "Özel Durum Açıklaması"
    assert first["url"] == "https://www.kap.org.tr/tr/Bildirim/1691986"
    assert first["published_date"] == "2026-11-04 08:01"
    # Empty summary falls back to the subject; late filings are flagged.
    assert second["title"] == "Finansal Rapor"
    assert second["is_late"] is True

    post_call = [c for c in mocked.call_args_list if c.args[0] == "POST"][0]
    body = post_call.kwargs["json"]
    assert body["mkkMemberOidList"] == ["oid-thy"]
    assert body["fromDate"] == "2026-10-21"
    assert body["toDate"] == "2026-11-04"


def test_non_bist_and_unknown_tickers_return_nothing_without_network() -> None:
    fetcher = KapDisclosureFetcher()
    with patch("data_provider.kap_fetcher.requests.request", side_effect=_fake_request) as mocked:
        assert fetcher.get_recent_disclosures("AAPL") == []
        assert fetcher.get_recent_disclosures("7203.T") == []
        assert mocked.call_count == 0
        assert fetcher.get_recent_disclosures("ZZZZZ.IS") == []
        assert fetcher.get_company_title("THYAO.IS") == "TÜRK HAVA YOLLARI A.O."


def test_fetcher_fails_open_and_opens_circuit_after_repeated_errors() -> None:
    fetcher = KapDisclosureFetcher()
    with patch(
        "data_provider.kap_fetcher.requests.request",
        side_effect=requests.ConnectionError("down"),
    ) as mocked:
        for _ in range(5):
            assert fetcher.get_recent_disclosures("THYAO.IS") == []
        # Circuit opens after three failures, so later calls skip the network.
        assert mocked.call_count == 3


def test_kap_datetime_parsing() -> None:
    assert _parse_kap_datetime("04.11.2026 08:01:00").isoformat() == "2026-11-04T08:01:00"
    assert _parse_kap_datetime("04.11.2026").isoformat() == "2026-11-04T00:00:00"
    assert _parse_kap_datetime("2026-11-04") is None
    assert _parse_kap_datetime(None) is None


def test_format_context_marks_untrusted_evidence() -> None:
    fetcher = KapDisclosureFetcher()
    with patch("data_provider.kap_fetcher.requests.request", side_effect=_fake_request):
        items = fetcher.get_recent_disclosures("THYAO.IS", today=date(2026, 11, 4))

    text = format_kap_disclosure_context(items, stock_code="THYAO.IS", lookback_days=14)
    assert "KAP company disclosures for THYAO.IS (last 14 days)" in text
    assert "untrusted" in text
    assert "[late filing]" in text
    assert "https://www.kap.org.tr/tr/Bildirim/1691986" in text
    assert format_kap_disclosure_context([], stock_code="THYAO.IS") == ""


def test_pipeline_helper_injects_and_persists_kap_disclosures() -> None:
    from src.core.pipeline import StockAnalysisPipeline

    items = [
        {
            "index": 1691986,
            "ticker": "THYAO",
            "published_date": "2026-11-04 08:01",
            "title": "2026 3. Çeyrek Finansal Sonuçlar",
            "class_label": "Özel Durum Açıklaması",
            "publisher": "TÜRK HAVA YOLLARI A.O.",
            "is_late": False,
            "url": "https://www.kap.org.tr/tr/Bildirim/1691986",
        }
    ]
    pipeline = SimpleNamespace(db=MagicMock(), _build_query_context=lambda query_id: {"query_id": query_id})
    fake_fetcher = MagicMock()
    fake_fetcher.get_recent_disclosures.return_value = items

    with patch("data_provider.kap_fetcher.get_kap_fetcher", return_value=fake_fetcher):
        context = StockAnalysisPipeline._build_kap_disclosure_context(
            pipeline, code="THYAO.IS", stock_name="Türk Hava Yolları", query_id="q1"
        )
        skipped = StockAnalysisPipeline._build_kap_disclosure_context(
            pipeline, code="AAPL", stock_name="Apple", query_id="q2"
        )

    assert "2026 3. Çeyrek Finansal Sonuçlar" in context
    assert skipped == ""
    fake_fetcher.get_recent_disclosures.assert_called_once()
    saved = pipeline.db.save_news_intel.call_args.kwargs
    assert saved["dimension"] == "announcements"
    assert saved["response"].provider == "KAP"
    assert saved["response"].results[0].url == "https://www.kap.org.tr/tr/Bildirim/1691986"
    assert saved["query_context"] == {"query_id": "q1"}


def test_pipeline_helper_fails_open_when_fetcher_raises() -> None:
    from src.core.pipeline import StockAnalysisPipeline

    pipeline = SimpleNamespace(db=MagicMock(), _build_query_context=lambda query_id: {})
    with patch("data_provider.kap_fetcher.get_kap_fetcher", side_effect=RuntimeError("boom")):
        assert StockAnalysisPipeline._build_kap_disclosure_context(
            pipeline, code="THYAO.IS", stock_name="THY", query_id=None
        ) == ""
    pipeline.db.save_news_intel.assert_not_called()


def test_bist_news_search_uses_foreign_query_templates() -> None:
    assert SearchService._is_foreign_stock("THYAO.IS") is True
    assert SearchService._is_foreign_stock("600519") is False


def test_intelligence_templates_include_turkish_market_feeds() -> None:
    from src.services.intelligence_service import IntelligenceService

    service = IntelligenceService(repository=MagicMock(), config=SimpleNamespace(newsnow_base_url=""))
    templates = service.list_source_templates(market="tr")["items"]
    assert {item["template_id"] for item in templates} == {"tr-aa-economy", "tr-dunya", "tr-bloomberght"}
    assert all(item["source_type"] == "rss" and item["scope_type"] == "market" for item in templates)


def test_stock_name_for_bist_uses_kap_title_before_other_sources() -> None:
    from data_provider.base import DataFetcherManager

    fake = MagicMock()
    fake.get_company_title.return_value = "TÜRK HAVA YOLLARI A.O."
    manager = DataFetcherManager(fetchers=[])
    with patch("data_provider.kap_fetcher.get_kap_fetcher", return_value=fake), \
            patch.object(manager, "get_realtime_quote") as realtime:
        assert manager.get_stock_name("ZZTHY.IS") == "TÜRK HAVA YOLLARI A.O."
        realtime.assert_not_called()

    # Non-BIST codes never consult KAP.
    fake.get_company_title.reset_mock()
    with patch("data_provider.kap_fetcher.get_kap_fetcher", return_value=fake):
        manager.get_stock_name("ZZZZ", allow_realtime=False)
    fake.get_company_title.assert_not_called()


def test_stock_name_for_bist_fails_open_when_kap_errors() -> None:
    from data_provider.base import DataFetcherManager

    manager = DataFetcherManager(fetchers=[])
    with patch("data_provider.kap_fetcher.get_kap_fetcher", side_effect=RuntimeError("down")):
        assert manager.get_stock_name("ZZERR.IS", allow_realtime=False) == ""
