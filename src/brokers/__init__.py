# -*- coding: utf-8 -*-
"""Unified broker adapters and safety-locked audit helpers."""

from src.brokers.base import (
    BrokerAdapter,
    BrokerSecurityError,
    append_broker_audit_event,
    read_broker_audit_tail,
)
from src.brokers.registry import (
    get_broker_registry,
    list_broker_statuses,
    resolve_strategy_target_weights,
)

__all__ = [
    "BrokerAdapter",
    "BrokerSecurityError",
    "append_broker_audit_event",
    "get_broker_registry",
    "list_broker_statuses",
    "read_broker_audit_tail",
    "resolve_strategy_target_weights",
]
