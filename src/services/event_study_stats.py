# -*- coding: utf-8 -*-
"""Statistics shared by the event studies (Form 4, PEAD, KAP).

Plain per-event t-statistics overstate significance in two ways:

1. **Overlapping events.** Events in the same month share the same market
   shock, so they are not independent. :func:`clustered_test` averages excess
   returns per calendar month (calendar-time portfolio) and tests the monthly
   means: the effective sample is the number of months, not events.
2. **Many tests.** Checking a dozen segments x horizons will produce a
   "significant" cell by chance. :func:`holm_adjust` applies the Holm-Bonferroni
   step-down correction across all cells reported together.

:func:`delisting_sensitivity` bounds survivorship bias: events whose prices are
missing (typically delisted micro caps) are assumed to lose a fixed amount.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Shumway (1997): performance-related delistings average about -30%.
DEFAULT_DELISTING_RETURN_PCT = -30.0
MIN_MONTHS_FOR_SIGNIFICANCE = 12


def two_sided_p_value(t_stat: float) -> float:
    """Normal approximation of the two-sided p-value (fine for >= ~20 clusters)."""
    return math.erfc(abs(t_stat) / math.sqrt(2.0))


def clustered_test(observations: Iterable[Tuple[date, float]]) -> Dict[str, Any]:
    """Calendar-month clustered test of mean excess return against zero.

    Returns event-level mean / median, the mean of monthly averages, the number
    of months and the clustered t-statistic and p-value.
    """
    obs = [(day, float(value)) for day, value in observations if day is not None and value is not None]
    if not obs:
        return {"count": 0, "months": 0, "mean": 0.0, "median": 0.0, "monthly_mean": 0.0,
                "t_stat": 0.0, "p_value": 1.0}
    by_month: Dict[Tuple[int, int], List[float]] = defaultdict(list)
    for day, value in obs:
        by_month[(day.year, day.month)].append(value)
    monthly = [sum(values) / len(values) for values in by_month.values()]
    months = len(monthly)
    monthly_mean = sum(monthly) / months
    if months > 1:
        stderr = statistics.stdev(monthly) / math.sqrt(months)
        t_stat = monthly_mean / stderr if stderr > 0 else 0.0
    else:
        t_stat = 0.0
    values = [value for _, value in obs]
    return {
        "count": len(values),
        "months": months,
        "mean": round(sum(values) / len(values), 2),
        "median": round(statistics.median(values), 2),
        "monthly_mean": round(monthly_mean, 2),
        "t_stat": round(t_stat, 2),
        "p_value": round(two_sided_p_value(t_stat), 4) if months > 1 else 1.0,
    }


def holm_adjust(p_values: Dict[str, float]) -> Dict[str, float]:
    """Holm-Bonferroni adjusted p-values (monotone, capped at 1)."""
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    total = len(ordered)
    adjusted: Dict[str, float] = {}
    running = 0.0
    for rank, (key, p_value) in enumerate(ordered):
        running = max(running, min(1.0, (total - rank) * p_value))
        adjusted[key] = round(running, 4)
    return adjusted


def mark_significance(
    cells: Dict[str, Dict[str, Any]],
    *,
    alpha: float = 0.05,
    min_months: int = MIN_MONTHS_FOR_SIGNIFICANCE,
) -> None:
    """Add ``p_holm`` and ``is_significant`` to every cell (in place).

    A cell is significant only if its Holm-adjusted clustered p-value is below
    ``alpha`` and it spans at least ``min_months`` calendar months.
    """
    eligible = {key: cell["p_value"] for key, cell in cells.items() if cell.get("months", 0) > 1}
    adjusted = holm_adjust(eligible) if eligible else {}
    for key, cell in cells.items():
        cell["p_holm"] = adjusted.get(key, 1.0)
        cell["is_significant"] = bool(
            cell["p_holm"] < alpha and cell.get("months", 0) >= min_months
        )


def delisting_sensitivity(
    observed_excess: Sequence[float],
    missing_count: int,
    *,
    assumed_return_pct: float = DEFAULT_DELISTING_RETURN_PCT,
) -> Optional[float]:
    """Mean excess return if every missing event had returned ``assumed_return_pct``."""
    total = len(observed_excess) + max(0, missing_count)
    if total == 0:
        return None
    return round((sum(observed_excess) + missing_count * assumed_return_pct) / total, 2)


__all__: List[str] = [
    "DEFAULT_DELISTING_RETURN_PCT",
    "MIN_MONTHS_FOR_SIGNIFICANCE",
    "clustered_test",
    "delisting_sensitivity",
    "holm_adjust",
    "mark_significance",
    "two_sided_p_value",
]
