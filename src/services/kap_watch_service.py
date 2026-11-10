# -*- coding: utf-8 -*-
"""KAP & Turkish news watcher: near-real-time alerts for Borsa Istanbul disclosures,
multi-source confirmed news, and spreading market rumors.

The daily analysis runs a few times a day; a contract, buyback, circuit breaker,
or breaking multi-outlet story published at 11:00 would otherwise wait until the
next run. The watcher polls KAP and (optionally) :class:`data_provider.tr_news_hub.TrNewsHub`
for the ``.IS`` stocks in ``STOCK_LIST`` every ``KAP_WATCH_INTERVAL_SECONDS``
during ``KAP_WATCH_HOURS`` (Istanbul time) and sends one message per stock and
poll to the configured notification channels.

- **KAP Material** = tagged earnings, dividend, bonus / rights issue, buyback,
  ownership, contract, regulatory, rating or circuit breaker (tags come from
  :mod:`data_provider.kap_fetcher`). Routine filings (warrant prices, ...) are
  remembered but not sent.
- **Multi-source news (`CONFIRMED` / `OFFICIAL`)** = story carried by >= 2 distinct
  outlets (with at least one tier-1 financial outlet or >= 3 mainstream outlets)
  and tagged with a material/catalyst event.
- **Spreading rumor (`RUMOR`)** = speculative claim (`iddia`, `kulis`, `duyum`,
  `söylenti`, ...) spreading across >= 2 distinct outlets, explicitly labeled as
  an unconfirmed rumor (`⚠️ SÖYLENTİ — resmî teyit yok`).
- **State**: seen disclosure indexes and news keys per stock plus recent alerts
  are stored in ``data/kap_watch_state.json``, so restarts do not resend and the
  Web UI / API can display recent alerts.

Alerts carry facts and verification status only; they are not trading advice.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from src.services.market_symbol_utils import is_tr_suffix_symbol

logger = logging.getLogger(__name__)

MATERIAL_TAGS = frozenset({
    "earnings", "dividend", "bonus_issue", "rights_issue", "buyback", "ownership", "contract",
    "regulatory", "rating", "circuit_breaker",
})
NEWS_ALERT_TAGS = MATERIAL_TAGS | frozenset({"target_price", "broker_flow"})
_TAG_LABELS_TR = {
    "earnings": "bilanço", "dividend": "temettü", "bonus_issue": "bedelsiz", "rights_issue": "bedelli",
    "buyback": "geri alım", "ownership": "pay/ortaklık", "contract": "sözleşme/iş ilişkisi",
    "regulatory": "tedbir/düzenleme", "rating": "derecelendirme", "circuit_breaker": "devre kesici",
    "target_price": "hedef fiyat", "broker_flow": "aracı kurum/yabancı akışı", "price_move": "fiyat hareketi",
}
_ISTANBUL_TZ = timezone(timedelta(hours=3))
_MAX_SEEN_PER_STOCK = 200
_MAX_RECENT_ALERTS = 60
DEFAULT_STATE_PATH = Path("data") / "kap_watch_state.json"

_live_preview_lock = threading.Lock()
_live_preview_cache: Tuple[float, List[Dict[str, Any]]] = (0.0, [])
_LIVE_PREVIEW_TTL_SECONDS = 300.0


def parse_active_hours(value: str) -> Tuple[int, int]:
    """``"08:00-23:00"`` -> minutes since midnight ``(480, 1380)``; invalid -> whole day."""
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    if not match:
        return 0, 24 * 60
    start_h, start_m, end_h, end_m = (int(part) for part in match.groups())
    start, end = start_h * 60 + start_m, end_h * 60 + end_m
    if not (0 <= start < 24 * 60 and 0 < end <= 24 * 60) or start >= end:
        return 0, 24 * 60
    return start, end


def is_material(item: Dict[str, Any]) -> bool:
    return bool(MATERIAL_TAGS.intersection(item.get("tags") or []))


def is_alertable_news_story(story: Any) -> bool:
    """Return True if a clustered :class:`NewsStory` warrants an intraday alert.

    Requires at least 2 distinct outlets and either:
    - ``RUMOR`` verification (spreading market rumor across >= 2 outlets), or
    - ``CONFIRMED`` / ``OFFICIAL`` verification with a catalyst tag (or >= 3 outlets
      on a non-price-move story).
    """
    sources = list(getattr(story, "sources", None) or [])
    if len(sources) < 2:
        return False
    verification = str(getattr(story, "verification", "") or "").upper()
    tags = set(getattr(story, "tags", None) or [])
    if verification == "RUMOR":
        return True
    if verification in {"CONFIRMED", "OFFICIAL"}:
        if NEWS_ALERT_TAGS.intersection(tags):
            return True
        if len(sources) >= 3 and tags != {"price_move"}:
            return True
    return False


def news_story_key(story: Any) -> str:
    """Deterministic deduplication key for a clustered :class:`NewsStory`."""
    from data_provider.tr_news_hub import title_tokens

    verification = str(getattr(story, "verification", "") or "").upper()
    primary_tag = getattr(story, "primary_tag", None) or "general"
    lead = getattr(story, "lead", None)
    lead_title = str(getattr(lead, "title", "") or "")
    stems = sorted(title_tokens(lead_title))[:4]
    stem_part = "-".join(stems) if stems else "story"
    if verification == "RUMOR":
        return f"rumor:{primary_tag}:{stem_part}"
    if primary_tag not in {"general", "price_move", "contract"}:
        first_seen = getattr(story, "first_seen", None)
        day_str = first_seen.astimezone(_ISTANBUL_TZ).strftime("%Y-%m-%d") if first_seen else "nodate"
        return f"tag:{primary_tag}:{day_str}"
    return f"news:{primary_tag}:{stem_part}"


def story_to_alert_item(story: Any, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Convert a :class:`NewsStory` into a serializable alert dictionary."""
    verification = str(getattr(story, "verification", "") or "REPORTED").upper()
    kind = "rumor" if verification == "RUMOR" else "news"
    lead = getattr(story, "lead", None)
    last_seen = getattr(story, "last_seen", None) or (now or datetime.now(timezone.utc))
    published_str = last_seen.astimezone(_ISTANBUL_TZ).strftime("%Y-%m-%d %H:%M")
    sources = list(getattr(story, "sources", None) or [])
    tags = list(getattr(story, "tags", None) or [])
    return {
        "kind": kind,
        "story_key": news_story_key(story),
        "title": str(getattr(lead, "title", "") or ""),
        "published_date": published_str,
        "verification": verification,
        "sources": sources,
        "source_count": len(sources),
        "tags": tags,
        "class_label": "Söylenti (Teyitsiz)" if kind == "rumor" else "Çok Kaynaklı Haber",
        "details": str(getattr(lead, "summary", "") or ""),
        "url": str(getattr(lead, "url", "") or ""),
    }


def format_alert(stock_code: str, items: Iterable[Dict[str, Any]]) -> str:
    """One Telegram-friendly message for a stock's new material disclosures and/or news alerts."""
    items = list(items)
    kap_items = [item for item in items if item.get("kind", "kap") == "kap"]
    news_items = [item for item in items if item.get("kind") == "news"]
    rumor_items = [item for item in items if item.get("kind") == "rumor"]

    if kap_items and not news_items and not rumor_items:
        lines = [f"🔔 KAP: {stock_code} — {len(kap_items)} yeni önemli bildirim"]
    elif kap_items:
        lines = [
            f"🔔 KAP & Haber: {stock_code} — {len(kap_items)} KAP bildirimi, "
            f"{len(news_items) + len(rumor_items)} haber/söylenti"
        ]
    elif rumor_items and not news_items:
        lines = [f"⚠️ Söylenti Uyarısı: {stock_code} — {len(rumor_items)} yayılan söylenti"]
    else:
        lines = [f"📰 Haber Uyarısı: {stock_code} — {len(items)} çok kaynaklı gelişme"]

    for item in items:
        kind = item.get("kind", "kap")
        tags = ", ".join(_TAG_LABELS_TR.get(tag, tag) for tag in item.get("tags") or [])
        if kind == "rumor":
            sources_str = ", ".join((item.get("sources") or [])[:4])
            src_count = int(item.get("source_count") or len(item.get("sources") or []))
            lines.append(
                f"• ⚠️ [SÖYLENTİ — resmî teyit yok | {src_count} kaynak: {sources_str}] "
                f"{item.get('title', '')}"
            )
        elif kind == "news":
            sources_str = ", ".join((item.get("sources") or [])[:4])
            src_count = int(item.get("source_count") or len(item.get("sources") or []))
            lines.append(
                f"• 📰 [Çok kaynaklı haber | {src_count} güvenilir kaynak: {sources_str}] "
                f"{item.get('title', '')}"
            )
        else:
            lines.append(
                f"• [{item.get('published_date', '')}] {item.get('title', '')} ({item.get('class_label', '')})"
            )
        if tags:
            lines.append(f"  Tür: {tags}")
        if item.get("details"):
            details = str(item["details"])
            lines.append(f"  {details[:600]}{'…' if len(details) > 600 else ''}")
        if item.get("url"):
            lines.append(f"  {item['url']}")
    lines.append("Bilgi amaçlıdır, yatırım tavsiyesi değildir. Fiyatın tepkisini ve haberin teyidini kontrol et.")
    return "\n".join(lines)


class KapWatchService:
    """Poll KAP and Turkish news feeds for watched ``.IS`` stocks and notify on material events."""

    def __init__(
        self,
        *,
        stocks: Iterable[str],
        fetcher: Any = None,
        news_hub: Any = None,
        watch_news: Optional[bool] = None,
        notifier: Any = None,
        state_path: Optional[Path] = None,
        active_hours: str = "08:00-23:00",
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.stocks = [code.strip().upper() for code in stocks if is_tr_suffix_symbol(code.strip())]
        default_fetcher_used = fetcher is None
        if fetcher is None:
            from data_provider.kap_fetcher import KapDisclosureFetcher

            # Own instance with a short cache: the shared one caches disclosures for 15 minutes.
            fetcher = KapDisclosureFetcher(disclosure_ttl_seconds=30)
        self.fetcher = fetcher

        if news_hub is not None:
            self.news_hub = news_hub
        elif watch_news is True or (watch_news is None and default_fetcher_used):
            from data_provider.tr_news_hub import TrNewsHub

            self.news_hub = TrNewsHub(cache_ttl_seconds=120)
        else:
            self.news_hub = None

        self.notifier = notifier
        self.state_path = Path(state_path or DEFAULT_STATE_PATH)
        self.active_window = parse_active_hours(active_hours)
        self.clock = clock
        self.state, self.seen_news, self.recent_alerts = self._load_state_bundle()

    # ------------------------------------------------------------ state
    def _load_state_bundle(
        self,
    ) -> Tuple[Dict[str, List[int]], Dict[str, List[str]], List[Dict[str, Any]]]:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}, {}, []
        except (OSError, ValueError) as exc:
            logger.warning("[kap-watch] state file unreadable, starting fresh: %s", exc)
            return {}, {}, []
        if not isinstance(raw, dict):
            return {}, {}, []

        seen_raw = raw.get("seen")
        seen: Dict[str, List[int]] = {}
        if isinstance(seen_raw, dict):
            seen = {
                str(code): [int(i) for i in indexes if isinstance(i, int)]
                for code, indexes in seen_raw.items()
                if isinstance(indexes, list)
            }

        seen_news_raw = raw.get("seen_news")
        seen_news: Dict[str, List[str]] = {}
        if isinstance(seen_news_raw, dict):
            seen_news = {
                str(code): [str(k) for k in keys if isinstance(k, str) and k]
                for code, keys in seen_news_raw.items()
                if isinstance(keys, list)
            }

        recent_raw = raw.get("recent_alerts")
        recent_alerts: List[Dict[str, Any]] = []
        if isinstance(recent_raw, list):
            recent_alerts = [item for item in recent_raw if isinstance(item, dict)][-_MAX_RECENT_ALERTS:]

        return seen, seen_news, recent_alerts

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        bundle: Dict[str, Any] = {"seen": self.state}
        if self.seen_news:
            bundle["seen_news"] = self.seen_news
        if self.recent_alerts:
            bundle["recent_alerts"] = self.recent_alerts[-_MAX_RECENT_ALERTS:]
        payload = json.dumps(bundle, ensure_ascii=False, indent=0)
        # Atomic replace so an interrupted write never corrupts the state.
        fd, tmp_name = tempfile.mkstemp(dir=str(self.state_path.parent), prefix=".kap_watch_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, self.state_path)

    def _record_recent_alerts(self, stock_code: str, items: Iterable[Dict[str, Any]], now_iso: str) -> None:
        for item in items:
            kind = str(item.get("kind") or "kap")
            tags = list(item.get("tags") or [])
            entry = {
                "stock_code": stock_code,
                "kind": kind,
                "index": item.get("index"),
                "story_key": item.get("story_key"),
                "title": str(item.get("title") or ""),
                "published_date": str(item.get("published_date") or ""),
                "class_label": str(item.get("class_label") or ""),
                "verification": item.get("verification") or ("OFFICIAL" if kind == "kap" else None),
                "sources": list(item.get("sources") or (["KAP"] if kind == "kap" else [])),
                "source_count": int(item.get("source_count") or (1 if kind == "kap" else len(item.get("sources") or []))),
                "tags": tags,
                "tag_labels_tr": [_TAG_LABELS_TR.get(t, t) for t in tags],
                "details": str(item.get("details") or "")[:600],
                "url": str(item.get("url") or ""),
                "alerted_at": now_iso,
            }
            self.recent_alerts.append(entry)
        self.recent_alerts = self.recent_alerts[-_MAX_RECENT_ALERTS:]

    # ------------------------------------------------------------- polling
    def is_active(self, now: Optional[datetime] = None) -> bool:
        local = (now or self.clock()).astimezone(_ISTANBUL_TZ)
        minutes = local.hour * 60 + local.minute
        start, end = self.active_window
        return start <= minutes < end

    def _poll_stock_news(self, code: str, now: datetime) -> Tuple[List[Dict[str, Any]], bool]:
        """Poll :attr:`news_hub` for ``code`` and return ``(new_alert_items, state_changed)``."""
        if self.news_hub is None:
            return [], False
        try:
            digest = self.news_hub.digest(code, days=2, max_stories=10, macro_hours=12, max_macro_stories=0, now=now)
        except Exception as exc:  # noqa: BLE001 - fail-open
            logger.info("[kap-watch] %s news digest failed: %s", code, exc)
            return [], False

        stories = list(getattr(digest, "stories", None) or [])
        alertable = [story for story in stories if is_alertable_news_story(story)]
        first_news_poll = code not in self.seen_news
        seen_keys = list(self.seen_news.get(code, []))
        seen_set = set(seen_keys)

        new_stories = [story for story in alertable if news_story_key(story) not in seen_set]
        if not new_stories and not first_news_poll:
            return [], False

        for story in new_stories:
            key = news_story_key(story)
            if key not in seen_set:
                seen_keys.append(key)
                seen_set.add(key)
        self.seen_news[code] = seen_keys[-_MAX_SEEN_PER_STOCK:]

        if first_news_poll:
            logger.info("[kap-watch] %s: %d existing news stories recorded (no alert)", code, len(new_stories))
            return [], True

        items = [story_to_alert_item(story, now=now) for story in new_stories]
        return items, True

    def poll_once(self, *, send: bool = True) -> Dict[str, List[Dict[str, Any]]]:
        """Check every stock once; returns ``{stock: [new material/news items]}`` (sent when ``send``)."""
        alerts: Dict[str, List[Dict[str, Any]]] = {}
        now = self.clock()
        local_now = now.astimezone(_ISTANBUL_TZ)
        today = local_now.date()
        now_iso = local_now.isoformat()
        changed = False

        for code in self.stocks:
            stock_alerts: List[Dict[str, Any]] = []

            # 1) Poll official KAP disclosures
            try:
                items = self.fetcher.get_recent_disclosures(code, days=2, max_items=20, today=today)
            except Exception as exc:  # noqa: BLE001 - fetcher is fail-open, belt and braces
                logger.info("[kap-watch] %s fetch failed: %s", code, exc)
                items = None

            if items is not None:
                first_poll = code not in self.state
                seen = set(self.state.get(code, []))
                new_items = [item for item in items if item.get("index") not in seen]
                if new_items or first_poll:
                    self.state[code] = sorted(seen | {item["index"] for item in new_items})[-_MAX_SEEN_PER_STOCK:]
                    changed = True
                    if first_poll:
                        logger.info(
                            "[kap-watch] %s: %d existing disclosures recorded (no alert)", code, len(new_items)
                        )
                    else:
                        material = sorted(
                            (item for item in new_items if is_material(item)),
                            key=lambda item: str(item.get("published_date")),
                        )
                        if material:
                            try:
                                self.fetcher.attach_details(material, limit=3)
                            except Exception as exc:  # noqa: BLE001
                                logger.info("[kap-watch] %s details failed: %s", code, exc)
                            stock_alerts.extend(material)

            # 2) Poll multi-source confirmed news and spreading rumors
            news_items, news_changed = self._poll_stock_news(code, now)
            if news_changed:
                changed = True
            if news_items:
                stock_alerts.extend(news_items)

            if not stock_alerts:
                continue

            alerts[code] = stock_alerts
            self._record_recent_alerts(code, stock_alerts, now_iso)
            changed = True

            if send and self.notifier is not None:
                last_item = stock_alerts[-1]
                dedup_suffix = last_item.get("index") or last_item.get("story_key") or len(stock_alerts)
                try:
                    delivered = self.notifier.send(
                        format_alert(code, stock_alerts),
                        dedup_key=f"kap-watch:{code}:{dedup_suffix}",
                    )
                    logger.info(
                        "[kap-watch] %s: %d alert item(s), delivered=%s", code, len(stock_alerts), delivered
                    )
                except Exception as exc:  # noqa: BLE001 - one channel failure must not stop the loop
                    logger.warning("[kap-watch] %s notification failed: %s", code, exc)

        if changed:
            try:
                self._save_state()
            except OSError as exc:
                logger.warning("[kap-watch] state save failed: %s", exc)
        return alerts

    def run_forever(
        self,
        *,
        interval_seconds: int,
        sleep: Callable[[float], None] = time.sleep,
        max_polls: Optional[int] = None,
    ) -> None:
        """Poll in the active window until interrupted (``max_polls`` is for tests)."""
        polls = 0
        logger.info(
            "[kap-watch] watching %s every %ss, active %s (Istanbul)",
            ", ".join(self.stocks) or "-",
            interval_seconds,
            self.active_window,
        )
        while max_polls is None or polls < max_polls:
            if self.is_active():
                self.poll_once()
            polls += 1
            sleep(max(60, int(interval_seconds)))


def get_recent_kap_and_news_alerts(
    *,
    state_path: Optional[Path] = None,
    stocks: Optional[Iterable[str]] = None,
    live_fallback: bool = True,
    max_items: int = 30,
) -> List[Dict[str, Any]]:
    """Return recent KAP, multi-source news, and rumor alerts for the API / Web UI.

    Reads persisted ``recent_alerts`` from ``data/kap_watch_state.json`` first.
    When empty and ``live_fallback=True``, fetches recent material KAP disclosures
    and multi-source news for the configured ``.IS`` stocks (cached for 5 minutes).
    """
    target_path = Path(state_path or DEFAULT_STATE_PATH)
    try:
        raw = json.loads(target_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("recent_alerts"), list) and raw["recent_alerts"]:
            items = [item for item in raw["recent_alerts"] if isinstance(item, dict)]
            items.reverse()
            return items[: max(1, int(max_items))]
    except (FileNotFoundError, OSError, ValueError):
        pass

    if not live_fallback:
        return []

    global _live_preview_cache
    with _live_preview_lock:
        cached_at, cached_items = _live_preview_cache
        if cached_items and (time.monotonic() - cached_at) < _LIVE_PREVIEW_TTL_SECONDS:
            return cached_items[: max(1, int(max_items))]

    try:
        from data_provider.kap_fetcher import get_kap_fetcher
        from data_provider.tr_news_hub import get_tr_news_hub
        from src.config import get_config

        raw_stocks = list(stocks) if stocks is not None else list(get_config().stock_list or [])
        tr_stocks = [code.strip().upper() for code in raw_stocks if is_tr_suffix_symbol(str(code).strip())][:10]
        if not tr_stocks:
            return []

        kap = get_kap_fetcher()
        hub = get_tr_news_hub()
        preview: List[Dict[str, Any]] = []
        now_iso = datetime.now(_ISTANBUL_TZ).isoformat()
        for code in tr_stocks:
            try:
                disclosures = kap.get_recent_disclosures(code, days=14, max_items=10)
                for item in disclosures:
                    if not is_material(item):
                        continue
                    tags = list(item.get("tags") or [])
                    preview.append({
                        "stock_code": code,
                        "kind": "kap",
                        "index": item.get("index"),
                        "story_key": None,
                        "title": str(item.get("title") or ""),
                        "published_date": str(item.get("published_date") or ""),
                        "class_label": str(item.get("class_label") or "KAP Bildirimi"),
                        "verification": "OFFICIAL",
                        "sources": ["KAP"],
                        "source_count": 1,
                        "tags": tags,
                        "tag_labels_tr": [_TAG_LABELS_TR.get(t, t) for t in tags],
                        "details": str(item.get("details") or item.get("summary") or "")[:600],
                        "url": str(item.get("url") or ""),
                        "alerted_at": now_iso,
                    })
            except Exception as exc:  # noqa: BLE001
                logger.debug("[kap-watch] live KAP preview failed for %s: %s", code, exc)

            try:
                digest = hub.digest(code, days=3, max_stories=6, macro_hours=12, max_macro_stories=0)
                for story in digest.stories:
                    if not is_alertable_news_story(story):
                        continue
                    alert_item = story_to_alert_item(story)
                    tags = list(alert_item.get("tags") or [])
                    preview.append({
                        "stock_code": code,
                        "kind": alert_item["kind"],
                        "index": None,
                        "story_key": alert_item.get("story_key"),
                        "title": alert_item["title"],
                        "published_date": alert_item["published_date"],
                        "class_label": alert_item["class_label"],
                        "verification": alert_item["verification"],
                        "sources": alert_item["sources"],
                        "source_count": alert_item["source_count"],
                        "tags": tags,
                        "tag_labels_tr": [_TAG_LABELS_TR.get(t, t) for t in tags],
                        "details": alert_item["details"][:600],
                        "url": alert_item["url"],
                        "alerted_at": now_iso,
                    })
            except Exception as exc:  # noqa: BLE001
                logger.debug("[kap-watch] live news preview failed for %s: %s", code, exc)

        preview.sort(key=lambda item: str(item.get("published_date") or ""), reverse=True)
        with _live_preview_lock:
            _live_preview_cache = (time.monotonic(), preview)
        return preview[: max(1, int(max_items))]
    except Exception as exc:  # noqa: BLE001
        logger.debug("[kap-watch] live preview failed: %s", exc)
        return []
