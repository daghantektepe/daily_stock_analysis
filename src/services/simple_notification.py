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
) -> str:
    """Format strictly 3 calm Turkish lines summarizing market weather and basket status."""
    data = brief if brief is not None else build_simple_investor_brief()
    weather = data.get("weather") or {}
    emoji = weather.get("emoji") or "⛅"
    as_of = data.get("as_of_date") or "Güncel"
    headline = weather.get("headline") or "Piyasa dengeli seyrediyor"
    prot = float(weather.get("protection_pct") or 0.0)

    profiles = data.get("profiles") or []
    chosen = next((p for p in profiles if p.get("id") == profile_id), None) or (profiles[0] if profiles else {})
    assets = chosen.get("assets") or []
    top_slice = ", ".join(
        f"{a.get('symbol')} %{float(a.get('weight_pct') or 0.0):.0f}"
        for a in assets[:3]
    ) or "BIL %100"

    if weights_changed is False:
        line2 = f"Sepet Değişmedi ({top_slice}) — bugün hiçbir işlem yapmana gerek yok."
    elif weights_changed is True:
        line2 = f"Sepet Güncellendi — yeni dağılım: {top_slice}."
    else:
        line2 = f"Önerilen Dağılım ({chosen.get('title', 'Dengeli')}): {top_slice}."

    line1 = f"{emoji} {as_of} Özeti: {headline} (Kalkan: %{prot:.0f})."
    line3 = "Sadece bilgi amaçlıdır; otomatik alım-satım yapılmamıştır, sakin kalabilirsin."
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
