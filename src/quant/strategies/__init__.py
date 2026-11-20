# -*- coding: utf-8 -*-
"""Zero-lookahead backtest engine and 25-strategy quantitative library."""

from src.quant.strategies.engine import (
    StrategyResult,
    StrategySpec,
    backtest_weight_matrix,
    combine_strategy_returns,
)
from src.quant.strategies.library import (
    compute_paa_weights,
    run_all_base_strategies,
)

__all__ = [
    "StrategyResult",
    "StrategySpec",
    "backtest_weight_matrix",
    "combine_strategy_returns",
    "compute_paa_weights",
    "run_all_base_strategies",
]
