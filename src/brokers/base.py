# -*- coding: utf-8 -*-
"""Unified BrokerAdapter contract and structured JSONL audit logging."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_BROKER_AUDIT_PATH = Path("data") / "broker_audit.jsonl"

_SENSITIVE_KEYS = {"api_key", "api_secret", "secret", "password", "token", "signature"}


class BrokerSecurityError(RuntimeError):
    """Raised when a broker write operation violates sandbox / confirmation / read-only safety locks."""


def _scrub_payload(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            str(k): ("***REDACTED***" if str(k).lower() in _SENSITIVE_KEYS else _scrub_payload(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_scrub_payload(v) for v in data[:25]]
    return data


def append_broker_audit_event(
    *,
    broker_id: str,
    action: str,
    status: str,
    details: Optional[Dict[str, Any]] = None,
    audit_path: Optional[Path] = None,
) -> None:
    """Append a structured JSONL audit event (fail-open, never logs secrets)."""
    path = Path(audit_path) if audit_path is not None else DEFAULT_BROKER_AUDIT_PATH
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "broker_id": str(broker_id),
        "action": str(action),
        "status": str(status),
        "details": _scrub_payload(details or {}),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover - audit should not crash trading preview
        logger.debug("[broker-audit] write skipped (%s): %s", path, exc)


def read_broker_audit_tail(limit: int = 20, audit_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read recent broker audit log records, newest first."""
    path = Path(audit_path) if audit_path is not None else DEFAULT_BROKER_AUDIT_PATH
    if not path.is_file():
        return []
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        selected = lines[-max(1, int(limit)) :]
        parsed: List[Dict[str, Any]] = []
        for raw in reversed(selected):
            try:
                parsed.append(json.loads(raw))
            except ValueError:
                continue
        return parsed
    except Exception:
        return []


class BrokerAdapter(ABC):
    """Unified safety-locked broker interface across US, Crypto, and BIST bridges."""

    broker_id: str = "base"
    display_name: str = "Base Broker"
    audit_path: Optional[Path] = None

    @property
    @abstractmethod
    def is_sandbox(self) -> bool:
        """True if operating in paper/testnet sandbox mode."""

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """True when required API credentials are configured."""

    @property
    def read_only_enforced(self) -> bool:
        """True when all order submission / position write actions are blocked."""
        return True

    def _audit(self, action: str, status: str, details: Optional[Dict[str, Any]] = None) -> None:
        append_broker_audit_event(
            broker_id=self.broker_id,
            action=action,
            status=status,
            details=details,
            audit_path=self.audit_path,
        )

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Inspect adapter configuration, safety locks, and optional reachability."""

    @abstractmethod
    def get_account_summary(self) -> Dict[str, Any]:
        """Return normalized account cash, equity, and currency."""

    @abstractmethod
    def list_positions(self) -> List[Dict[str, Any]]:
        """Return current broker holdings in normalized form."""

    @abstractmethod
    def preview_rebalance_plan(
        self,
        target_weights: Dict[str, float],
        *,
        capital: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Compute delta orders against target weights WITHOUT placing any order."""

    @abstractmethod
    def submit_paper_order(
        self,
        order: Dict[str, Any],
        *,
        confirmed: bool = False,
    ) -> Dict[str, Any]:
        """Submit ONE sandbox/paper order only when ``confirmed=True`` and locks permit."""

    @abstractmethod
    def reconcile_fills(self, symbol: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        """Return filled order summary / execution slippage statistics."""
