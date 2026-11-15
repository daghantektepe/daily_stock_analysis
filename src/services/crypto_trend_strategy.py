# -*- coding: utf-8 -*-
"""Crypto trend-following strategy: be in the coin above its long moving average, in cash below.

Rule (time-series momentum / trend filter, e.g. Moskowitz-Ooi-Pedersen 2012;
Liu-Tsyvinski 2021 for crypto):

- Capital is split into equal **sleeves**, one per asset (default BTC, ETH)
  and per moving-average length (default 50/100/150/200/250 days). Using the
  whole ensemble instead of the "best" length avoids fitting one parameter to
  the past: exposure to a coin is the share of its averages it trades above.
- At each daily close, a sleeve holds its coin when ``close > SMA(n)`` and
  cash otherwise. The decision uses the close of day *t* and is filled at
  that close plus costs, so day *t+1* is the first day of exposure (no
  lookahead).
- A sleeve only trades when its signal flips; each side costs ``cost_pct``
  (exchange fee + spread + slippage).

The aim is not to predict tomorrow but to sit out the long crashes (-70% to
-90% for BTC / ETH) that buy-and-hold has to endure. The same functions run
the backtest and the paper book, so paper results and backtest share one rule.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_ASSETS = ("BTC-USD", "ETH-USD")
DEFAULT_SMA_DAYS = 200
DEFAULT_SMA_WINDOWS = (50, 100, 150, 200, 250)
DEFAULT_COST_PCT = 0.15  # per side: ~0.1% taker fee + spread/slippage
TRADING_DAYS_PER_YEAR = 365  # crypto trades every day


@dataclass(frozen=True)
class TrendConfig:
    assets: Sequence[str] = DEFAULT_ASSETS
    sma_windows: Sequence[int] = DEFAULT_SMA_WINDOWS
    cost_pct: float = DEFAULT_COST_PCT

    @property
    def windows(self) -> List[int]:
        return sorted({int(n) for n in self.sma_windows if int(n) > 1})

    @property
    def longest(self) -> int:
        return max(self.windows)


@dataclass
class Sleeve:
    """One asset's share of the capital: either fully in the coin or in cash."""

    asset: str
    cash: float
    units: float = 0.0
    trades: List[Dict[str, Any]] = field(default_factory=list)

    def value(self, price: float) -> float:
        return self.cash + self.units * price

    def step(self, day: date, price: float, in_trend: bool, cost_pct: float) -> Optional[Dict[str, Any]]:
        """Move the sleeve to coin / cash for ``in_trend``; returns the trade, if any."""
        if price <= 0:
            return None
        cost = cost_pct / 100.0
        if in_trend and self.units == 0 and self.cash > 0:
            self.units = self.cash * (1 - cost) / price
            trade = {"date": day.isoformat(), "asset": self.asset, "side": "buy", "price": price,
                     "units": self.units, "value": self.cash}
            self.cash = 0.0
        elif not in_trend and self.units > 0:
            proceeds = self.units * price
            self.cash = proceeds * (1 - cost)
            trade = {"date": day.isoformat(), "asset": self.asset, "side": "sell", "price": price,
                     "units": self.units, "value": proceeds}
            self.units = 0.0
        else:
            return None
        self.trades.append(trade)
        return trade


def trend_flags(closes: pd.Series, sma_days: int) -> pd.Series:
    """True where the close is above its trailing SMA (NaN history -> False)."""
    sma = closes.rolling(sma_days, min_periods=sma_days).mean()
    return (closes > sma).fillna(False)


def _stats(equity: pd.Series) -> Dict[str, Any]:
    equity = equity.dropna()
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return {"cagr_pct": None, "max_drawdown_pct": None, "sharpe": None, "vol_pct": None, "total_return_pct": None}
    returns = equity.pct_change().dropna()
    years = max((len(equity) - 1) / TRADING_DAYS_PER_YEAR, 1e-9)
    total = equity.iloc[-1] / equity.iloc[0]
    vol = returns.std() * math.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = (returns.mean() * TRADING_DAYS_PER_YEAR) / vol if vol > 0 else None
    drawdown = (equity / equity.cummax() - 1).min()
    return {
        "total_return_pct": round((total - 1) * 100, 1),
        "cagr_pct": round((total ** (1 / years) - 1) * 100, 1),
        "max_drawdown_pct": round(drawdown * 100, 1),
        "sharpe": round(float(sharpe), 2) if sharpe is not None else None,
        "vol_pct": round(float(vol) * 100, 1),
    }


def run_backtest(
    prices: pd.DataFrame,
    config: TrendConfig = TrendConfig(),
    *,
    initial_capital: float = 10_000.0,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> Dict[str, Any]:
    """Backtest the sleeve rule on daily closes (columns = assets, index = dates).

    Evaluation starts once every asset has ``sma_days`` of history (or at
    ``start``). Benchmarks: equal-weight buy-and-hold of the same assets and
    buy-and-hold of the first asset (BTC by default).
    """
    assets = [a for a in config.assets if a in prices.columns]
    if not assets:
        raise ValueError("no price columns for the configured assets")
    windows = config.windows
    frame = prices[assets].sort_index().ffill()
    flags = {(a, n): trend_flags(frame[a], n) for a in assets for n in windows}
    valid = frame.dropna().index
    first_ready = max(frame[a].dropna().index[min(config.longest, len(frame[a].dropna()) - 1)] for a in assets)
    window = valid[(valid >= first_ready)]
    if start is not None:
        window = window[window >= pd.Timestamp(start)]
    if end is not None:
        window = window[window <= pd.Timestamp(end)]
    if len(window) < 2:
        raise ValueError("not enough history for the backtest window")

    keys = [(a, n) for a in assets for n in windows]
    sleeves = {key: Sleeve(asset=key[0], cash=initial_capital / len(keys)) for key in keys}
    hold_units = {a: (initial_capital / len(assets)) / frame.at[window[0], a] for a in assets}
    equity, benchmark, first_asset, exposure = [], [], [], []
    for ts in window:
        day = ts.date()
        for key in keys:
            sleeves[key].step(day, float(frame.at[ts, key[0]]), bool(flags[key].at[ts]), config.cost_pct)
        equity.append(sum(sleeves[key].value(float(frame.at[ts, key[0]])) for key in keys))
        benchmark.append(sum(hold_units[a] * float(frame.at[ts, a]) for a in assets))
        first_asset.append(initial_capital * float(frame.at[ts, assets[0]]) / float(frame.at[window[0], assets[0]]))
        exposure.append(sum(1 for key in keys if sleeves[key].units > 0) / len(keys))

    index = pd.DatetimeIndex(window)
    eq = pd.Series(equity, index=index)
    bh = pd.Series(benchmark, index=index)
    first = pd.Series(first_asset, index=index)
    trades = [t for key in keys for t in sleeves[key].trades]
    years = max((len(index) - 1) / TRADING_DAYS_PER_YEAR, 1e-9)
    yearly = []
    for year in sorted({ts.year for ts in index}):
        mask = index.year == year
        if mask.sum() < 2:
            continue

        def _ret(series: pd.Series) -> float:
            part = series[mask]
            prev = series[index < part.index[0]]
            base = prev.iloc[-1] if len(prev) else part.iloc[0]
            return round((part.iloc[-1] / base - 1) * 100, 1)
        yearly.append({"year": year, "strategy_pct": float(_ret(eq)), "buy_hold_pct": float(_ret(bh)),
                       "first_asset_pct": float(_ret(first))})
    return {
        "assets": assets,
        "sma_windows": windows,
        "cost_pct": config.cost_pct,
        "start": index[0].date().isoformat(),
        "end": index[-1].date().isoformat(),
        "strategy": _stats(eq),
        "buy_hold": _stats(bh),
        "first_asset_buy_hold": _stats(first),
        "first_asset": assets[0],
        "exposure_pct": round(sum(exposure) / len(exposure) * 100, 1),
        "trades_per_year": round(len(trades) / years, 1),
        "trade_count": len(trades),
        "yearly": yearly,
        "equity": eq,
        "benchmark": bh,
    }


def robustness_grid(
    prices: pd.DataFrame,
    sma_values: Iterable[int] = DEFAULT_SMA_WINDOWS,
    *,
    assets: Sequence[str] = DEFAULT_ASSETS,
    cost_pct: float = DEFAULT_COST_PCT,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Each single SMA length plus the ensemble, all over the same window.

    A real effect should not hinge on one value. Every run starts on the same
    day (the longest SMA must be ready) so the rows are comparable.
    """
    sma_values = sorted(set(int(v) for v in sma_values))
    common_start = date.fromisoformat(
        run_backtest(prices, TrendConfig(assets=assets, sma_windows=(max(sma_values),), cost_pct=cost_pct),
                     start=start, end=end)["start"]
    )
    variants = [((n,), f"SMA{n}") for n in sma_values] + [(tuple(sma_values), "topluluk")]
    rows = []
    for windows, label in variants:
        result = run_backtest(prices, TrendConfig(assets=assets, sma_windows=windows, cost_pct=cost_pct),
                              start=common_start, end=end)
        rows.append({"label": label, "sma_windows": list(windows),
                     **{f"strategy_{k}": v for k, v in result["strategy"].items()},
                     "buy_hold_cagr_pct": result["buy_hold"]["cagr_pct"],
                     "buy_hold_max_drawdown_pct": result["buy_hold"]["max_drawdown_pct"],
                     "buy_hold_sharpe": result["buy_hold"]["sharpe"],
                     "exposure_pct": result["exposure_pct"], "trades_per_year": result["trades_per_year"],
                     "start": result["start"], "end": result["end"]})
    return rows


def current_targets(prices: pd.DataFrame, config: TrendConfig = TrendConfig()) -> Dict[str, Dict[str, Any]]:
    """Today's signal per asset from the latest completed daily close.

    ``weight`` is the share of the asset's capital that should be in the coin
    (fraction of its moving averages that the close is above).
    """
    targets: Dict[str, Dict[str, Any]] = {}
    for asset in config.assets:
        if asset not in prices.columns:
            continue
        closes = prices[asset].dropna()
        if len(closes) < config.longest:
            targets[asset] = {"weight": 0.0, "in_trend": False, "reason": "insufficient_history"}
            continue
        close = float(closes.iloc[-1])
        averages = {n: float(closes.rolling(n).mean().iloc[-1]) for n in config.windows}
        above = [n for n, sma in averages.items() if close > sma]
        targets[asset] = {
            "date": closes.index[-1].date().isoformat(),
            "close": round(close, 2),
            "averages": {str(n): round(v, 2) for n, v in averages.items()},
            "above": above,
            "weight": round(len(above) / len(averages), 2),
            "in_trend": bool(above),
        }
    return targets


def load_daily_closes(assets: Sequence[str], start: str = "2015-01-01") -> pd.DataFrame:
    """Daily closes from Yahoo Finance (columns = assets); drops today's unfinished bar."""
    import yfinance as yf

    columns = {}
    for asset in assets:
        history = yf.Ticker(asset).history(start=start, auto_adjust=True)
        if history.empty:
            logger.warning("[crypto-trend] no history for %s", asset)
            continue
        series = history["Close"].copy()
        series.index = pd.DatetimeIndex(series.index.tz_localize(None) if series.index.tz else series.index).normalize()
        columns[asset] = series
    frame = pd.DataFrame(columns).sort_index()
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    return frame[frame.index < today]


__all__ = [
    "DEFAULT_ASSETS",
    "DEFAULT_COST_PCT",
    "DEFAULT_SMA_DAYS",
    "DEFAULT_SMA_WINDOWS",
    "Sleeve",
    "TrendConfig",
    "current_targets",
    "load_daily_closes",
    "robustness_grid",
    "run_backtest",
    "trend_flags",
]
