# -*- coding: utf-8 -*-
"""Plain 3-line morning summary notification mode ("Annem İçin 3 Satırlık Özet").

Controlled via ``NOTIFICATION_SIMPLE_MODE=true``. Produces exactly three calm,
jargon-free Turkish lines and suppresses repeat alerts unless allocation changes
or ``only_on_change=False``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.services.simple_investor_brief import build_simple_investor_brief

logger = logging.getLogger(__name__)

DEFAULT_SIMPLE_NOTIFY_STATE = Path("data") / "simple_notify_state.json"


def _basket_signature(profile: Dict[str, Any]) -> str:
    pairs = [
        f"{item.get('symbol')}:{float(item.get('weight_pct') or 0.0):.1f}"
        for item in (profile.get("assets") or [])
    ]
    raw = "|".join(sorted(pairs))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def format_simple_morning_summary(
    brief: Optional[Dict[str, Any]] = None,
    *,
    weights_changed: Optional[bool] = None,
    profile_id: str = "balanced",
    weekly_watch: Optional[Dict[str, Any]] = None,
) -> str:
    """Format strictly 3 calm Turkish lines summarizing market weather and basket status."""
    data = brief if brief is not None else build_simple_investor_brief()
    status = data.get("data_status") or {}
    weather = data.get("weather") or {}
    prot_raw = weather.get("protection_pct")
    profiles = data.get("profiles") or []
    chosen = next((p for p in profiles if p.get("id") == profile_id), None) or (profiles[0] if profiles else {})
    assets = chosen.get("assets") or []
    if status.get("state") == "missing" or prot_raw is None or not assets:
        return (
            "❔ Strateji verisi yok: bugün için sepet ya da kalkan oranı hesaplanamadı.\n"
            "Turnuva ve v3 araştırma dosyaları güncellenince özet yeniden gönderilir.\n"
            "Sadece bilgi amaçlıdır; otomatik alım-satım yapılmamıştır."
        )
    emoji = weather.get("emoji") or "⛅"
    as_of = data.get("as_of_date") or "tarih bilinmiyor"
    headline = weather.get("headline") or ""
    prot = float(prot_raw)
    top_slice = ", ".join(
        f"{a.get('symbol')} %{float(a.get('weight_pct') or 0.0):.0f}"
        for a in assets[:3]
    )

    if weights_changed is False:
        line2 = f"Sepet Değişmedi ({top_slice}) — bugün hiçbir işlem yapmana gerek yok."
    elif weights_changed is True:
        line2 = f"Sepet Güncellendi — yeni dağılım: {top_slice}."
    else:
        line2 = f"Önerilen Dağılım ({chosen.get('title', 'Dengeli')}): {top_slice}."

    line1 = f"{emoji} {as_of} Özeti: {headline} (Kalkan: %{prot:.0f})."
    notes = []
    if status.get("state") in ("stale", "partial"):
        stale_msg = str(status.get("message", "")).split(" Günlük sanal defter")[0].strip()
        if stale_msg:
            notes.append(f"Dikkat: {stale_msg}")
    acc = data.get("signal_accuracy") or {}
    if isinstance(acc, dict) and acc.get("summary_line"):
        notes.append(str(acc["summary_line"]).rstrip(".") + ".")
    if isinstance(weekly_watch, dict) and int(weekly_watch.get("total") or 0) > 0 and weekly_watch.get("line"):
        notes.append(str(weekly_watch["line"]).rstrip(".") + ".")
        if weekly_watch.get("alert_line"):
            notes.append(str(weekly_watch["alert_line"]))
    notes.append("Sadece bilgi amaçlıdır; otomatik alım-satım yapılmamıştır, sakin kalabilirsin.")
    line3 = " ".join(notes)
    return f"{line1}\n{line2}\n{line3}"


def dispatch_simple_morning_summary(
    *,
    notifier: Any = None,
    brief: Optional[Dict[str, Any]] = None,
    only_on_change: bool = True,
    state_path: Optional[Path] = None,
    profile_id: str = "balanced",
) -> Dict[str, Any]:
    """Evaluate allocation changes and optionally send the 3-line morning summary."""
    data = brief if brief is not None else build_simple_investor_brief()
    profiles = data.get("profiles") or []
    chosen = next((p for p in profiles if p.get("id") == profile_id), None) or (profiles[0] if profiles else {})
    if (data.get("data_status") or {}).get("state") == "missing" or not chosen.get("assets"):
        # Never announce an allocation that was not computed from real snapshots.
        return {
            "sent": False,
            "skipped_reason": "no_strategy_data",
            "changed": False,
            "message": format_simple_morning_summary(data, profile_id=profile_id),
        }
    sig = _basket_signature(chosen)

    path = Path(state_path or DEFAULT_SIMPLE_NOTIFY_STATE)
    prev_sig: Optional[str] = None
    if path.is_file():
        try:
            prev_sig = json.loads(path.read_text(encoding="utf-8")).get("last_signature")
        except Exception:
            prev_sig = None

    changed = prev_sig is not None and prev_sig != sig
    if prev_sig is None:
        changed = True  # First run counts as initial announcement

    message = format_simple_morning_summary(data, weights_changed=changed, profile_id=profile_id)
    if only_on_change and not changed:
        return {"sent": False, "skipped_reason": "allocation_unchanged", "changed": False, "message": message}

    if notifier is None:
        from src.notification import NotificationService

        notifier = NotificationService()

    delivered = bool(notifier.send(message, dedup_key=f"simple-morning:{sig}"))
    if delivered:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "last_signature": sig,
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                        "profile_id": profile_id,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:  # pragma: no cover
            logger.debug("[simple-notify] state write skipped: %s", exc)
    return {"sent": delivered, "changed": changed, "message": message}
