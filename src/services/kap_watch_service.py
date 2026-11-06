# -*- coding: utf-8 -*-
"""KAP watcher: near-real-time alerts for material Borsa Istanbul disclosures.

The daily analysis runs a few times a day; a contract, buyback or circuit
breaker published at 11:00 would otherwise wait until the next run. The
watcher polls KAP for the ``.IS`` stocks in ``STOCK_LIST`` every
``KAP_WATCH_INTERVAL_SECONDS`` during ``KAP_WATCH_HOURS`` (Istanbul time) and
sends one message per stock and poll to the configured notification channels.

- **Material** = tagged earnings, dividend, bonus / rights issue, buyback,
  ownership, contract, regulatory, rating or circuit breaker (tags come from
  :mod:`data_provider.kap_fetcher`). Routine filings (warrant prices, ...) are
  remembered but not sent.
- **State**: seen disclosure indexes per stock are stored in a small JSON
  file, so restarts do not resend. The first poll of a stock only records what
  already exists (no flood of old disclosures).
- **Fail-open**: a KAP or notification error is logged and retried on the next
  poll; it never stops the loop.

Alerts carry the disclosure facts only; they are not trading advice.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
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
_TAG_LABELS_TR = {
    "earnings": "bilanço", "dividend": "temettü", "bonus_issue": "bedelsiz", "rights_issue": "bedelli",
    "buyback": "geri alım", "ownership": "pay/ortaklık", "contract": "sözleşme/iş ilişkisi",
    "regulatory": "tedbir/düzenleme", "rating": "derecelendirme", "circuit_breaker": "devre kesici",
}
_ISTANBUL_TZ = timezone(timedelta(hours=3))
_MAX_SEEN_PER_STOCK = 200
DEFAULT_STATE_PATH = Path("data") / "kap_watch_state.json"


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


def format_alert(stock_code: str, items: Iterable[Dict[str, Any]]) -> str:
    """One Telegram-friendly message for a stock's new material disclosures."""
    items = list(items)
    lines = [f"🔔 KAP: {stock_code} — {len(items)} yeni önemli bildirim"]
    for item in items:
        tags = ", ".join(_TAG_LABELS_TR.get(tag, tag) for tag in item.get("tags") or [])
        lines.append(f"• [{item.get('published_date', '')}] {item.get('title', '')} ({item.get('class_label', '')})")
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
    """Poll KAP for watched ``.IS`` stocks and notify on new material disclosures."""

    def __init__(
        self,
        *,
        stocks: Iterable[str],
        fetcher: Any = None,
        notifier: Any = None,
        state_path: Optional[Path] = None,
        active_hours: str = "08:00-23:00",
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.stocks = [code.strip().upper() for code in stocks if is_tr_suffix_symbol(code.strip())]
        if fetcher is None:
            from data_provider.kap_fetcher import KapDisclosureFetcher

            # Own instance with a short cache: the shared one caches disclosures for 15 minutes.
            fetcher = KapDisclosureFetcher(disclosure_ttl_seconds=30)
        self.fetcher = fetcher
        self.notifier = notifier
        self.state_path = Path(state_path or DEFAULT_STATE_PATH)
        self.active_window = parse_active_hours(active_hours)
        self.clock = clock
        self.state: Dict[str, List[int]] = self._load_state()

    # ------------------------------------------------------------ state
    def _load_state(self) -> Dict[str, List[int]]:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            logger.warning("[kap-watch] state file unreadable, starting fresh: %s", exc)
            return {}
        seen = raw.get("seen") if isinstance(raw, dict) else None
        if not isinstance(seen, dict):
            return {}
        return {str(code): [int(i) for i in indexes if isinstance(i, int)] for code, indexes in seen.items()
                if isinstance(indexes, list)}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"seen": self.state}, ensure_ascii=False, indent=0)
        # Atomic replace so an interrupted write never corrupts the state.
        fd, tmp_name = tempfile.mkstemp(dir=str(self.state_path.parent), prefix=".kap_watch_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, self.state_path)

    # ------------------------------------------------------------- polling
    def is_active(self, now: Optional[datetime] = None) -> bool:
        local = (now or self.clock()).astimezone(_ISTANBUL_TZ)
        minutes = local.hour * 60 + local.minute
        start, end = self.active_window
        return start <= minutes < end

    def poll_once(self, *, send: bool = True) -> Dict[str, List[Dict[str, Any]]]:
        """Check every stock once; returns ``{stock: [new material items]}`` (sent when ``send``)."""
        alerts: Dict[str, List[Dict[str, Any]]] = {}
        today = self.clock().astimezone(_ISTANBUL_TZ).date()
        changed = False
        for code in self.stocks:
            try:
                items = self.fetcher.get_recent_disclosures(code, days=2, max_items=20, today=today)
            except Exception as exc:  # noqa: BLE001 - fetcher is fail-open, belt and braces
                logger.info("[kap-watch] %s fetch failed: %s", code, exc)
                continue
            first_poll = code not in self.state
            seen = set(self.state.get(code, []))
            new_items = [item for item in items if item.get("index") not in seen]
            if not new_items and not first_poll:
                continue
            self.state[code] = sorted(seen | {item["index"] for item in new_items})[-_MAX_SEEN_PER_STOCK:]
            changed = True
            if first_poll:
                logger.info("[kap-watch] %s: %d existing disclosures recorded (no alert)", code, len(new_items))
                continue
            material = sorted((item for item in new_items if is_material(item)),
                              key=lambda item: str(item.get("published_date")))
            if not material:
                continue
            try:
                self.fetcher.attach_details(material, limit=3)
            except Exception as exc:  # noqa: BLE001
                logger.info("[kap-watch] %s details failed: %s", code, exc)
            alerts[code] = material
            if send and self.notifier is not None:
                try:
                    delivered = self.notifier.send(
                        format_alert(code, material),
                        dedup_key=f"kap-watch:{code}:{material[-1]['index']}",
                    )
                    logger.info("[kap-watch] %s: %d alert item(s), delivered=%s", code, len(material), delivered)
                except Exception as exc:  # noqa: BLE001 - one channel failure must not stop the loop
                    logger.warning("[kap-watch] %s notification failed: %s", code, exc)
        if changed:
            try:
                self._save_state()
            except OSError as exc:
                logger.warning("[kap-watch] state save failed: %s", exc)
        return alerts

    def run_forever(self, *, interval_seconds: int, sleep: Callable[[float], None] = time.sleep,
                    max_polls: Optional[int] = None) -> None:
        """Poll in the active window until interrupted (``max_polls`` is for tests)."""
        polls = 0
        logger.info("[kap-watch] watching %s every %ss, active %s (Istanbul)",
                    ", ".join(self.stocks) or "-", interval_seconds, self.active_window)
        while max_polls is None or polls < max_polls:
            if self.is_active():
                self.poll_once()
            polls += 1
            sleep(max(60, int(interval_seconds)))
