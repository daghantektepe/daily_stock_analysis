# -*- coding: utf-8 -*-
"""Daily refresh of the strategy snapshots the beginner screen reads.

``/simple`` ("Bugün Ne Yapayım?") and the morning summary read the live target
weights from ``data/quant_cache/tournament_latest.json`` and
``data/quant_cache/research_v3_latest.json``. Those files used to change only
when someone ran the tournament or the research lab by hand, so the screen could
show a weeks-old allocation. The daily paper step now refreshes them.

- Fail-open: a failed refresh is reported and the old snapshot stays; it never
  stops the paper books from advancing.
- A snapshot younger than ``max_age_hours`` is not rebuilt (e.g. a second run
  on the same day).
- Only the JSON snapshots under ``data/`` are written. The tracked Markdown
  reports under ``docs/`` are left alone so ``git pull`` keeps working.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE_HOURS = 20.0


def _age_hours(path: Path) -> Optional[float]:
    if not path.is_file():
        return None
    return (time.time() - path.stat().st_mtime) / 3600.0


def _run_tournament(cache_dir: Optional[Path], force_refresh_prices: bool) -> Dict[str, Any]:
    from src.quant.tournament import run_tournament

    payload = run_tournament(cache_dir=cache_dir, force_refresh=force_refresh_prices, write_report=False)
    return {"latest_date": payload.get("latest_date"), "strategies": payload.get("total_strategies")}


def _run_research(cache_dir: Optional[Path], force_refresh_prices: bool) -> Dict[str, Any]:
    from src.quant.research_lab import run_strategy_research_v3

    json_path = (Path(cache_dir) / "research_v3_latest.json") if cache_dir else None
    payload = run_strategy_research_v3(
        cache_dir=cache_dir,
        force_refresh=force_refresh_prices,
        save_outputs=True,
        json_path=json_path,
        write_report=False,
    )
    latest = max((str(c.get("latest_date") or "") for c in payload.get("candidates") or []), default="")
    return {"latest_date": latest or None, "promoted": payload.get("promoted_ids")}


def refresh_strategy_snapshots(
    *,
    cache_dir: Optional[Path] = None,
    force_refresh_prices: bool = False,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    force: bool = False,
    runners: Optional[Dict[str, Callable[[Optional[Path], bool], Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Rebuild the tournament and research v3 snapshots when they are older than ``max_age_hours``."""
    from src.quant.data_loader import DEFAULT_CACHE_DIR

    base = Path(cache_dir or DEFAULT_CACHE_DIR)
    jobs = runners or {"tournament": _run_tournament, "research_v3": _run_research}
    files = {"tournament": base / "tournament_latest.json", "research_v3": base / "research_v3_latest.json"}
    results: Dict[str, Any] = {}
    for name, runner in jobs.items():
        age = _age_hours(files[name])
        if not force and age is not None and age < max_age_hours:
            results[name] = {"status": "fresh", "age_hours": round(age, 1)}
            continue
        started = time.time()
        try:
            info = runner(cache_dir, force_refresh_prices)
            results[name] = {"status": "refreshed", "seconds": round(time.time() - started, 1), **(info or {})}
        except Exception as exc:  # noqa: BLE001 - keep the old snapshot, never stop the daily step
            logger.warning("[snapshot-refresh] %s failed, keeping previous snapshot: %s", name, exc)
            results[name] = {
                "status": "failed",
                "error": str(exc),
                "previous_age_hours": round(age, 1) if age is not None else None,
            }
    return {"ok": all(r["status"] != "failed" for r in results.values()), "results": results}


def format_snapshot_refresh_report(result: Dict[str, Any]) -> str:
    labels = {"tournament": "Strateji turnuvası", "research_v3": "v3 araştırması"}
    lines = []
    for name, info in (result.get("results") or {}).items():
        label = labels.get(name, name)
        status = info.get("status")
        if status == "refreshed":
            lines.append(f"{label}: yenilendi (veri tarihi {info.get('latest_date') or '—'}, {info.get('seconds')} sn)")
        elif status == "fresh":
            lines.append(f"{label}: güncel ({info.get('age_hours')} saat önce yenilenmiş)")
        else:
            prev = info.get("previous_age_hours")
            keep = f"önceki veri korunuyor ({prev} saatlik)" if prev is not None else "önceki veri yok"
            lines.append(f"{label}: YENİLENEMEDİ — {info.get('error')}; {keep}")
    return "Strateji verisi: " + " | ".join(lines) if lines else ""
