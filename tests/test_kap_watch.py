# -*- coding: utf-8 -*-
"""Offline tests for the KAP material disclosure watcher."""

import json
from datetime import datetime, timezone

from src.services.kap_watch_service import KapWatchService, format_alert, is_material, parse_active_hours


def _item(index, title, tags, published="2026-11-06 11:05"):
    return {
        "index": index, "title": title, "tags": tags, "published_date": published,
        "class_label": "Özel Durum Açıklaması", "disclosure_class": "ODA",
        "url": f"https://www.kap.org.tr/tr/Bildirim/{index}",
    }


class _Fetcher:
    def __init__(self):
        self.items = {"ASELS.IS": [_item(1, "Sözleşme İmzalanması", ["contract"], "2026-11-03 10:07")]}
        self.detail_calls = []

    def get_recent_disclosures(self, code, **_kwargs):
        if code == "BROKEN.IS":
            raise RuntimeError("down")
        return list(self.items.get(code, []))

    def attach_details(self, items, limit=3):
        self.detail_calls.append([item["index"] for item in items])
        for item in items:
            item["details"] = "toplam tutarı 442,5 milyon ABD Doları olan ihracat sözleşmesi"
        return items


class _Notifier:
    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail

    def send(self, content, **kwargs):
        if self.fail:
            raise RuntimeError("telegram down")
        self.messages.append((content, kwargs))
        return True


def _service(tmp_path, fetcher, notifier, hour=11):
    clock = lambda: datetime(2026, 11, 6, hour - 3, 0, tzinfo=timezone.utc)  # noqa: E731 - Istanbul = UTC+3
    return KapWatchService(
        stocks=["ASELS.IS", "AAPL", "BROKEN.IS"], fetcher=fetcher, notifier=notifier,
        state_path=tmp_path / "state.json", clock=clock,
    )


def test_first_poll_records_existing_then_alerts_only_new_material(tmp_path) -> None:
    fetcher, notifier = _Fetcher(), _Notifier()
    service = _service(tmp_path, fetcher, notifier)
    assert service.stocks == ["ASELS.IS", "BROKEN.IS"]  # non-BIST codes are ignored

    assert service.poll_once() == {}  # seeds state, no flood of old disclosures
    assert notifier.messages == []

    fetcher.items["ASELS.IS"] += [
        _item(2, "Yatırım Kuruluşu Varantları İtfa Fiyatları", []),
        _item(3, "Sözleşme İmzalanması", ["contract"]),
    ]
    alerts = service.poll_once()
    assert [item["index"] for item in alerts["ASELS.IS"]] == [3]
    assert fetcher.detail_calls == [[3]]
    text, kwargs = notifier.messages[0]
    assert text.startswith("🔔 KAP: ASELS.IS — 1 yeni önemli bildirim")
    assert "Tür: sözleşme/iş ilişkisi" in text and "442,5 milyon ABD Doları" in text
    assert "yatırım tavsiyesi değildir" in text
    assert kwargs["dedup_key"] == "kap-watch:ASELS.IS:3"

    # Nothing new -> nothing sent; routine filing was remembered.
    assert service.poll_once() == {}
    assert len(notifier.messages) == 1
    saved = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert saved["seen"]["ASELS.IS"] == [1, 2, 3]


def test_state_survives_restart_and_notification_errors_do_not_stop(tmp_path) -> None:
    fetcher = _Fetcher()
    _service(tmp_path, fetcher, _Notifier()).poll_once()
    fetcher.items["ASELS.IS"].append(_item(4, "Pay Geri Alım Programı", ["buyback"]))

    restarted = _service(tmp_path, fetcher, _Notifier(fail=True))
    alerts = restarted.poll_once()  # sending fails, loop keeps going
    assert [item["index"] for item in alerts["ASELS.IS"]] == [4]
    assert restarted.poll_once() == {}  # marked seen even though delivery failed


def test_active_hours_and_helpers(tmp_path) -> None:
    service = _service(tmp_path, _Fetcher(), _Notifier())
    assert service.is_active(datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)) is True   # 11:00 TR
    assert service.is_active(datetime(2026, 11, 6, 21, 0, tzinfo=timezone.utc)) is False  # 00:00 TR
    assert parse_active_hours("09:30-18:15") == (570, 1095)
    assert parse_active_hours("garbage") == (0, 1440)
    assert is_material({"tags": ["circuit_breaker"]}) and not is_material({"tags": []})
    assert "1 yeni önemli" in format_alert("THYAO.IS", [_item(9, "x", ["earnings"])])


def test_run_forever_skips_polls_outside_active_hours(tmp_path) -> None:
    fetcher = _Fetcher()
    service = _service(tmp_path, fetcher, _Notifier(), hour=3)  # 03:00 Istanbul
    sleeps = []
    service.run_forever(interval_seconds=10, sleep=sleeps.append, max_polls=2)
    assert sleeps == [60, 60]  # interval floor
    assert not (tmp_path / "state.json").exists()  # never polled at night


def test_confirmed_multi_source_news_and_rumor_alerts(tmp_path) -> None:
    from types import SimpleNamespace
    from data_provider.tr_news_hub import NewsItem, NewsStory
    from src.services.kap_watch_service import get_recent_kap_and_news_alerts

    t0 = datetime(2026, 11, 6, 8, 15, tzinfo=timezone.utc)

    def _make_story(titles_and_sources):
        items = [
            NewsItem(
                title=title,
                url=f"https://example.com/{idx}",
                source=source,
                published_at=t0,
                summary="Detay özet",
            )
            for idx, (title, source) in enumerate(titles_and_sources)
        ]
        return NewsStory(items=items)

    class _FakeNewsHub:
        def __init__(self):
            self.stories_by_code = {
                "ASELS.IS": [
                    # Existing confirmed story at startup -> recorded on first poll, not alerted
                    _make_story([
                        ("Aselsan 3. çeyrek bilançosunda net kârını artırdı", "Bloomberg HT"),
                        ("Aselsan 3. çeyrek finansal sonuçlarını açıkladı", "Dünya"),
                    ])
                ]
            }

        def digest(self, code, **_kwargs):
            return SimpleNamespace(stories=list(self.stories_by_code.get(code, [])))

    fetcher = _Fetcher()
    notifier = _Notifier()
    hub = _FakeNewsHub()
    state_file = tmp_path / "state_news.json"
    clock = lambda: t0  # noqa: E731

    service = KapWatchService(
        stocks=["ASELS.IS"],
        fetcher=fetcher,
        news_hub=hub,
        notifier=notifier,
        state_path=state_file,
        clock=clock,
    )

    # First poll seeds existing KAP and existing news without sending alerts
    assert service.poll_once() == {}
    assert notifier.messages == []

    # Second poll:
    # 1) Single-outlet story -> ignored (not multi-source)
    # 2) Multi-source confirmed contract story (Bloomberg HT + Ekonomim) -> alerted!
    # 3) Multi-source spreading rumor (2 outlets with 'kulis'/'iddia') -> alerted with rumor warning!
    hub.stories_by_code["ASELS.IS"].extend([
        _make_story([
            ("Aselsan'dan tek kaynaklı haber", "Paratic"),
        ]),
        _make_story([
            ("Aselsan 120 milyon dolarlık yeni ihracat sözleşmesi imzaladı", "Bloomberg HT"),
            ("Aselsan'dan 120 milyon dolarlık yeni sözleşme", "Ekonomim"),
        ]),
        _make_story([
            ("Kulis: Aselsan için stratejik ortaklık iddiası konuşuluyor", "Sözcü"),
            ("Aselsan hisselerinde ortaklık söylentisi ve kulis iddiası", "Habertürk"),
        ]),
    ])

    alerts = service.poll_once()
    assert len(alerts["ASELS.IS"]) == 2
    kinds = [item["kind"] for item in alerts["ASELS.IS"]]
    assert kinds == ["news", "rumor"]
    assert len(notifier.messages) == 1
    msg_text, _ = notifier.messages[0]
    assert "Çok kaynaklı haber | 2 güvenilir kaynak: Bloomberg HT, Ekonomim" in msg_text
    assert "⚠️ [SÖYLENTİ — resmî teyit yok | 2 kaynak:" in msg_text

    # Third poll: no duplicate alerts
    assert service.poll_once() == {}
    assert len(notifier.messages) == 1

    # Recent alerts are persisted and readable via get_recent_kap_and_news_alerts
    recent = get_recent_kap_and_news_alerts(state_path=state_file, live_fallback=False)
    assert len(recent) == 2
    assert {item["kind"] for item in recent} == {"news", "rumor"}

