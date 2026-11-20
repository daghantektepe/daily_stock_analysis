# -*- coding: utf-8 -*-
"""Empirical multi-universe quantitative strategy tournament and portfolio engine."""

from src.quant.stats import (
    PerformanceMetrics,
    classify_strategy_verdict,
    compute_performance_metrics,
    deflated_sharpe_ratio,
)

__all__ = [
    "PerformanceMetrics",
    "classify_strategy_verdict",
    "compute_performance_metrics",
    "deflated_sharpe_ratio",
]
