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


# ------------------------------------------------------------ disclosure bodies
def _form_row(name: str, label: str, value: str, *, summernote: bool = False) -> str:
    cell = "taxonomy-context-value-summernote" if summernote else "taxonomy-context-value col-order-class-3"
    return (
        '<tr class="oda-12000_New-Business-Relation-row-1 data-input-row presentation-enabled">'
        f'<td class="taxonomy-field-name-cell"><div class="gwt-Label taxonomy-field-name">{name}|</div></td>'
        '<td class="taxonomy-field-title"><table><tbody><tr>'
        f'<td><div class="gwt-Label multi-language-content content-tr" style="display: block;">{label}</div></td>'
        '<td><div class="gwt-Label multi-language-content content-en" style="display: none;">English</div></td>'
        '</tr></tbody></table></td>'
        f'<td colspan="2" class="{cell} multi-language-content content-tr" style="display: table-cell;">'
        f'<div>{value}</div></td>'
        f'<td colspan="2" class="{cell} multi-language-content content-en" style="display: none;">'
        '<div>English value</div></td></tr>'
    )


_FORM_HTML = "".join([
    _form_row("oda_UpdateAnnouncementFlag", "Yapılan Açıklama Güncelleme mi?", "Hayır (No)"),
    _form_row("oda_NameSurnameOrCompanyTitleOfCustomerOrSupplier", "Müşterinin Ticaret Ünvanı", "Uluslararası Müşteri"),
    _form_row("oda_ShareInNetSales", "Müşterinin Net Satışlar İçindeki Payı", "%0,0"),
    _form_row("oda_IsRelatedParty", "Karşı Taraf İlişkili Taraf mıdır?", "Hayır (No)"),
    _form_row("oda_ImpactOfNewBusinessRelation", "Ortaklık Faaliyetlerine Etkisi", "Şirketin cirosunu olumlu etkileyecektir."),
    _form_row("oda_ContractAmount", "Sözleşme Tutarı", "1,1 milyar ABD Doları"),
    _form_row(
        "oda_ExplanationTextBlock", "Açıklamalar",
        "<div>ASELSAN, uluslararası bir müşterisi ile toplam tutarı 1,1 milyar ABD Doları olan ihracat "
        "sözleşmesi imzalamıştır.</div><div><br/></div><div>Kamuoyuna saygılarımızla duyurulur.</div>",
        summernote=True,
    ),
])


def _next_payload(markup: str) -> str:
    """Embed markup the way the KAP Next.js page does (JSON-escaped), plus the rendered copy."""
    escaped = markup.replace("\\", "\\\\").replace('"', '\\"').replace("<", "\\u003c").replace(">", "\\u003e")
    return f'<html><script>self.__next_f.push([1,"{escaped}"])</script><body>{markup}</body></html>'


_FREE_HTML = (
    '<table><tr><td><div class="bgGreen pd5 mTB10"><div class="txtWhite font14">Ek Açıklamalar</div></div>'
    '</td></tr><tr><td><div class="gwt-HTML control-label lineheight-32px"><p>Bankamız tarafından 04.11.2026 '
    "tarihinde ağırlıklı ortalama 137,3850 TL fiyatla toplam 2.474.579 TL nominal değerli pay geri "
    "alınmıştır.</p><p>Saygılarımızla,</p></div></td></tr></table>"
)


def test_parse_disclosure_page_reads_form_fields_amounts_first() -> None:
    from data_provider.kap_fetcher import parse_disclosure_page

    text = parse_disclosure_page(_next_payload(_FORM_HTML))

    assert text.startswith("ASELSAN, uluslararası bir müşterisi ile toplam tutarı 1,1 milyar ABD Doları")
    assert "saygılarımızla" not in text
    parts = text.split(" | ")
    assert parts[1] == "Sözleşme Tutarı: 1,1 milyar ABD Doları"  # amounts before other fields
    assert "Müşterinin Ticaret Ünvanı: Uluslararası Müşteri" in parts
    assert "Ortaklık Faaliyetlerine Etkisi: Şirketin cirosunu olumlu etkileyecektir." in parts
    # Flags, "Hayır" answers, zero shares and the duplicated payload copy are dropped.
    assert "Güncelleme" not in text and "İlişkili Taraf" not in text and "%0,0" not in text
    assert text.count("Uluslararası Müşteri") == 1
    assert "English" not in text


def test_parse_disclosure_page_reads_free_text_and_condenses_long_explanations() -> None:
    from data_provider.kap_fetcher import _condense, parse_disclosure_page

    text = parse_disclosure_page(_FREE_HTML)
    assert text == (
        "Bankamız tarafından 04.11.2026 tarihinde ağırlıklı ortalama 137,3850 TL fiyatla toplam "
        "2.474.579 TL nominal değerli pay geri alınmıştır."
    )
    assert parse_disclosure_page("<html>nothing here</html>") == ""

    long_text = (
        "Bankamız Yönetim Kurulu'nun kararı ile güçlü finansal yapısına ve uzun vadeli değer yaratma "
        "potansiyeline duyduğumuz güvenin ortaya konulması amacıyla; - Sermaye Piyasası Kurulu'nun ilgili "
        "tebliği uyarınca bir program başlatılmasına, - Program çerçevesinde azami 85 milyon TL nominal değerli "
        "payın geri alınmasına, - Programın süresinin 3 yıl olarak belirlenmesine, - Pay geri alım işlemleri "
        "için ayrılacak fonun azami 11,0 milyar TL olarak belirlenmesine, - Geri alınan payların elde tutulma "
        "esaslarının Genel Kurul'un bilgisine sunulmasına karar verilmiştir. Garanti Holding B.V. ve G "
        "Netherlands B.V. ile ilgili süreç ayrıca yürütülmektedir."
    )
    condensed = _condense(long_text, 380)
    assert len(condensed) <= 380
    assert "85 milyon TL" in condensed and "11,0 milyar TL" in condensed
    assert "B.V. ve G" not in condensed.split(" … ")[0]  # abbreviations do not end a sentence


def test_market_notices_keep_bist_measures_and_mkk_conversions_only() -> None:
    rows = [
        {
            "publishDate": f"0{day}.11.2026 10:00:00",
            "kapTitle": "BORSA İSTANBUL BISTECH DEVRE KESİCİ UYGULAMASI",
            "disclosureClass": "DKB",
            "subject": "Pay Bazında Devre Kesici Bildirimi",
            "summary": "THYAO.E işlem sırasında Pay Bazında Devre Kesici Uygulaması devreye girmiştir",
            "disclosureIndex": 1690000 + day,
        }
        for day in range(1, 5)
    ] + [
        {
            "publishDate": "02.11.2026 16:55:14",
            "kapTitle": "MERKEZİ KAYIT KURULUŞU A.Ş.",
            "disclosureClass": "DKB",
            "subject": "Borsada İşlem Gören Tipe Dönüşüm Duyurusu",
            "summary": "DÖNÜŞÜM",
            "disclosureIndex": 1691500,
        },
        {
            "publishDate": "03.11.2026 17:16:27",
            "kapTitle": "MERKEZİ KAYIT KURULUŞU A.Ş.",
            "disclosureClass": "DKB",
            "subject": "SPK İşlem Yasağı Nedeniyle Pay Duyurusu",
            "summary": "SPK İşlem Yasağı Nedeniyle Pay Duyurusu",
            "disclosureIndex": 1691600,
        },
        {
            "publishDate": "03.11.2026 08:43:00",
            "kapTitle": "TÜRK HAVA YOLLARI A.O.",
            "disclosureClass": "ODA",
            "subject": "Payların Geri Alınmasına İlişkin Bildirim",
            "summary": "Pay Geri Alım Programı Başlatılması",
            "disclosureIndex": 1691700,
        },
    ]

    def fake_request(method, url, **_kwargs):
        if url.endswith("/company/items/IGS/A"):
            return _response(_COMPANIES)
        return _response(rows)

    fetcher = KapDisclosureFetcher()
    with patch("data_provider.kap_fetcher.requests.request", side_effect=fake_request):
        items = fetcher.get_recent_disclosures("THYAO.IS", today=date(2026, 11, 5))

    labels = [item["class_label"] for item in items]
    # At most three market notices in total, newest first: two breakers + the MKK conversion.
    assert sum(1 for item in items if item["disclosure_class"] == "DKB") == 3
    assert labels.count("Borsa İstanbul tedbir / devre kesici") == 2
    assert "MKK pay dönüşümü (borsada satılabilir tipe)" in labels
    assert {item["index"] for item in items} >= {1690004, 1690003, 1691500, 1691700}
    assert all("SPK İşlem Yasağı" not in item["title"] for item in items)
    breaker = next(item for item in items if item["class_label"].startswith("Borsa"))
    assert breaker["tags"] == ["circuit_breaker"]
    assert next(item for item in items if item["index"] == 1691700)["tags"] == ["buyback"]
    assert next(item for item in items if item["index"] == 1691500)["tags"] == ["ownership"]


def test_attach_details_reads_newest_company_filings_and_caches() -> None:
    page = _next_payload(_FORM_HTML).encode("utf-8")
    calls = []

    def fake_request(method, url, **_kwargs):
        calls.append(url)
        if url.endswith("/tr/Bildirim/1691350"):
            response = MagicMock()
            response.raise_for_status.return_value = None
            response.content = page
            return response
        raise requests.ConnectionError("down")

    items = [
        {"index": 1691350, "disclosure_class": "ODA", "tags": ["contract"]},
        {"index": 1687401, "disclosure_class": "FR", "tags": ["earnings"]},
        {"index": 1691000, "disclosure_class": "ODA", "tags": []},
    ]
    fetcher = KapDisclosureFetcher()
    with patch("data_provider.kap_fetcher.requests.request", side_effect=fake_request):
        fetcher.attach_details(items, limit=3)
        first_round = list(calls)
        fetcher.attach_details([{"index": 1691350, "disclosure_class": "ODA", "tags": []}], limit=3)

    assert items[0]["details"].startswith("ASELSAN, uluslararası bir müşterisi")
    assert items[0]["tags"] == ["contract"]
    assert "details" not in items[1]  # financial reports are not fetched
    assert "details" not in items[2]  # fail-open for unreachable pages
    assert sorted(url.rsplit("/", 1)[-1] for url in first_round) == ["1691000", "1691350"]
    assert len(calls) == len(first_round)  # cached; nothing new fetched


def test_format_context_shows_tags_and_details() -> None:
    text = format_kap_disclosure_context(
        [{
            "published_date": "2026-11-03 10:07",
            "class_label": "Özel Durum Açıklaması",
            "title": "Sözleşme İmzalanması",
            "tags": ["contract"],
            "details": "ASELSAN, 1,1 milyar ABD Doları tutarında ihracat sözleşmesi imzalamıştır.",
            "url": "https://www.kap.org.tr/tr/Bildirim/1691350",
        }],
        stock_code="ASELS.IS",
    )
    assert "1. [2026-11-03 10:07] (Özel Durum Açıklaması) [contract] Sözleşme İmzalanması" in text
    assert "     Details: ASELSAN, 1,1 milyar ABD Doları" in text
    assert "prefer them over news" in text


def test_pipeline_helper_persists_disclosure_details() -> None:
    from src.core.pipeline import StockAnalysisPipeline

    items = [{
        "index": 1691350,
        "ticker": "ASELS",
        "published_date": "2026-11-03 10:07",
        "title": "Sözleşme İmzalanması",
        "class_label": "Özel Durum Açıklaması",
        "publisher": "ASELSAN",
        "disclosure_class": "ODA",
        "tags": ["contract"],
        "is_late": False,
        "url": "https://www.kap.org.tr/tr/Bildirim/1691350",
    }]
    fake_fetcher = MagicMock()
    fake_fetcher.get_recent_disclosures.return_value = items
    fake_fetcher.attach_details.side_effect = lambda found, limit: [
        item.update(details="1,1 milyar ABD Doları tutarında ihracat sözleşmesi") for item in found
    ]
    pipeline = SimpleNamespace(db=MagicMock(), _build_query_context=lambda query_id: {})

    with patch("data_provider.kap_fetcher.get_kap_fetcher", return_value=fake_fetcher):
        context = StockAnalysisPipeline._build_kap_disclosure_context(
            pipeline, code="ASELS.IS", stock_name="Aselsan", query_id=None
        )

    assert "Details: 1,1 milyar ABD Doları tutarında ihracat sözleşmesi" in context
    snippet = pipeline.db.save_news_intel.call_args.kwargs["response"].results[0].snippet
    assert snippet == "Özel Durum Açıklaması · ASELSAN · 1,1 milyar ABD Doları tutarında ihracat sözleşmesi"
