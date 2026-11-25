# -*- coding: utf-8 -*-
"""Unified registry and strategy-target resolver for BrokerAdapter instances."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.brokers.algolab import AlgoLabBrokerAdapter
from src.brokers.alpaca.adapter import AlpacaBrokerAdapter
from src.brokers.base import BrokerAdapter, append_broker_audit_event
from src.brokers.binance.adapter import BinanceBrokerAdapter
from src.brokers.ibkr import IbkrBrokerAdapter

DEFAULT_TOURNAMENT_JSON = Path("data") / "quant_cache" / "tournament_latest.json"
DEFAULT_RESEARCH_V3_JSON = Path("data") / "quant_cache" / "research_v3_latest.json"


def get_broker_registry(
    config: Any = None,
    *,
    audit_path: Optional[Path] = None,
) -> Dict[str, BrokerAdapter]:
    """Instantiate all Phase 8 BrokerAdapters keyed by canonical broker_id."""
    if config is None:
        from src.config import get_config

        config = get_config()
    return {
        "alpaca": AlpacaBrokerAdapter.from_config(config, audit_path=audit_path),
        "binance": BinanceBrokerAdapter.from_config(config, audit_path=audit_path),
        "algolab": AlgoLabBrokerAdapter.from_config(config, audit_path=audit_path),
        "ibkr": IbkrBrokerAdapter.from_config(config, audit_path=audit_path),
    }


def list_broker_statuses(
    config: Any = None,
    *,
    audit_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Return normalized health_check dicts across all registered adapters + Midas CSV."""
    registry = get_broker_registry(config, audit_path=audit_path)
    items = [adapter.health_check() for adapter in registry.values()]
    items.append(
        {
            "broker_id": "midas_csv",
            "display_name": "Midas BIST / ABD (Manuel + CSV İçe Aktarım)",
            "configured": True,
            "sandbox": True,
            "read_only_enforced": True,
            "mode_label": "Manuel Liste & CSV",
            "note": "Midas için otomatik API yoktur; Emir Planı kopyalanır veya işlem CSV/Excel dosyası yüklenir.",
        }
    )
    return items


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def resolve_strategy_target_weights(
    strategy_key: str = "meta_a",
    *,
    tournament_path: Optional[Path] = None,
    research_v3_path: Optional[Path] = None,
) -> Dict[str, float]:
    """Resolve current persisted allocation weights (%) for a given strategy key."""
    key = (strategy_key or "meta_a").strip().lower()
    t_data = _read_json(Path(tournament_path or DEFAULT_TOURNAMENT_JSON))
    v3_data = _read_json(Path(research_v3_path or DEFAULT_RESEARCH_V3_JSON))

    paa_w = dict((t_data.get("paa") or {}).get("current_weights") or {"BIL": 100.0})
    meta_a_w = dict(
        (t_data.get("meta_portfolio_a") or t_data.get("champion") or {}).get("current_weights")
        or {"BIL": 80.0, "SHY": 20.0}
    )
    v3_trp_w: Dict[str, float] = {"BIL": 83.3, "UUP": 16.7}
    for cand in v3_data.get("candidates") or []:
        if cand.get("strategy_id") == "V3_TREND_RISK_PARITY_BIL" and cand.get("current_weights"):
            v3_trp_w = dict(cand["current_weights"])
            break

    if key == "paa":
        return {str(k).upper(): float(v) for k, v in paa_w.items() if float(v) > 0}
    if key == "v3_trp":
        return {str(k).upper(): float(v) for k, v in v3_trp_w.items() if float(v) > 0}
    if key in {"balanced", "balanced_50_50"}:
        merged: Dict[str, float] = {}
        for sym, val in meta_a_w.items():
            merged[str(sym).upper()] = merged.get(str(sym).upper(), 0.0) + 0.5 * float(val)
        for sym, val in v3_trp_w.items():
            merged[str(sym).upper()] = merged.get(str(sym).upper(), 0.0) + 0.5 * float(val)
        return {k: round(v, 2) for k, v in merged.items() if v > 0.05}
    if key == "crypto_5sma":
        return {"BTC-USD": 25.0, "ETH-USD": 25.0}
    return {str(k).upper(): float(v) for k, v in meta_a_w.items() if float(v) > 0}


def run_broker_dry_run_reconciliation(
    broker_id: str,
    *,
    strategy_key: str = "meta_a",
    capital: Optional[float] = None,
    config: Any = None,
    audit_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only pre-flight reconciliation (health + account + positions + rebalance preview).

    Never submits any order; records a ``dry_run_reconciliation`` audit entry so
    sandbox readiness and error states are explicitly observable before execution.
    """
    bid = str(broker_id or "").strip().lower()
    registry = get_broker_registry(config, audit_path=audit_path)
    if bid not in registry:
        raise ValueError(f"Unknown broker_id '{broker_id}'; available: {sorted(registry.keys())}")
    adapter = registry[bid]
    weights = resolve_strategy_target_weights(strategy_key)

    errors: List[str] = []
    health = adapter.health_check()
    try:
        account = adapter.get_account_summary()
    except Exception as exc:
        account = {"broker_id": bid, "error": str(exc)}
        errors.append(f"account_summary:{exc}")
    try:
        positions = adapter.list_positions()
    except Exception as exc:
        positions = []
        errors.append(f"list_positions:{exc}")
    try:
        plan = adapter.preview_rebalance_plan(weights, capital=capital)
    except Exception as exc:
        plan = {"broker_id": bid, "orders": [], "error": str(exc)}
        errors.append(f"preview_rebalance:{exc}")

    status = "error" if errors else ("ok" if health.get("sandbox") else "blocked_non_sandbox")
    append_broker_audit_event(
        broker_id=bid,
        action="dry_run_reconciliation",
        status=status,
        details={
            "strategy_key": strategy_key,
            "order_count": len(plan.get("orders") or []),
            "position_count": len(positions),
            "errors": errors,
        },
        audit_path=audit_path,
    )
    return {
        "ok": len(errors) == 0 and bool(health.get("sandbox")),
        "dry_run_only": True,
        "broker_id": bid,
        "strategy_key": strategy_key,
        "health": health,
        "account": account,
        "positions": positions,
        "plan": plan,
        "errors": errors,
    }
