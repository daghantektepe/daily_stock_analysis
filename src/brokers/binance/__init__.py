# -*- coding: utf-8 -*-
"""Binance Spot REST + Testnet broker client (HMAC-SHA256, zero external SDKs)."""

from src.brokers.binance.client import (
    BINANCE_SPOT_MAINNET_URL,
    BINANCE_SPOT_TESTNET_URL,
    BinanceBrokerError,
    BinanceClient,
)

__all__ = [
    "BINANCE_SPOT_MAINNET_URL",
    "BINANCE_SPOT_TESTNET_URL",
    "BinanceBrokerError",
    "BinanceClient",
]
