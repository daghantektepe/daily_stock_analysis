# -*- coding: utf-8 -*-
"""Paper book for the crypto trend strategy (simulated money, never real orders).

Runs :mod:`src.services.crypto_trend_strategy` forward in time with the exact
sleeve rule used by the backtest, so paper results can be compared with the
backtest one-to-one.

- State lives in ``data/strategy_paper/<name>.json`` (cash / units per sleeve,
  NAV history, trades).
- :meth:`StrategyPaperBook.step` processes every completed daily close since
  the last step, in order. Days caught up after the computer was off are
  marked ``late`` so the report can show that they were not acted on live.
- The benchmark is equal-weight buy-and-hold of the same coins from the book's
  first day.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.services.crypto_trend_strategy import Sleeve, TrendConfig, trend_flags

logger = logging.getLogger(__name__)

DEFAULT_BOOK_DIR = Path("data") / "strategy_paper"


class StrategyPaperBook:
    """Forward paper run of the crypto trend sleeves with a JSON ledger."""

    def __init__(
        self,
        name: str = "crypto_trend",
        *,
        config: TrendConfig = TrendConfig(),
        initial_capital: float = 10_000.0,
        book_dir: Optional[Path] = None,
    ) -> None:
        self.name = name
        self.config = config
        self.initial_capital = float(initial_capital)
        self.path = Path(book_dir or DEFAULT_BOOK_DIR) / f"{name}.json"
        self.state = self._load()

    # ---------------------------------------------------------------- state
    def _load(self) -> Dict[str, Any]:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"paper book {self.path} is unreadable: {exc}") from exc
        return state if isinstance(state, dict) else {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.name}_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(self.state, handle, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def _sleeve_keys(self) -> List[str]:
        return [f"{asset}|{n}" for asset in self.config.assets for n in self.config.windows]

    def _init_state(self, first_day: date, prices: Dict[str, float]) -> None:
        keys = self._sleeve_keys()
        self.state = {
            "name": self.name,
            "assets": list(self.config.assets),
            "sma_windows": self.config.windows,
            "cost_pct": self.config.cost_pct,
            "initial_capital": self.initial_capital,
            "start_date": first_day.isoformat(),
            "last_date": None,
            "sleeves": {key: {"cash": self.initial_capital / len(keys), "units": 0.0} for key in keys},
            "benchmark_units": {
                asset: (self.initial_capital / len(self.config.assets)) / prices[asset]
                for asset in self.config.assets
            },
            "history": [],
            "trades": [],
        }

    # ----------------------------------------------------------------- run
    def step(self, prices: pd.DataFrame, *, today: Optional[date] = None) -> Dict[str, Any]:
        """Apply the rule to every completed close after ``last_date``; returns a summary of this step."""
        assets = list(self.config.assets)
        frame = prices[[a for a in assets if a in prices.columns]].sort_index().ffill().dropna()
        if frame.shape[1] != len(assets) or frame.empty:
            raise ValueError("prices are missing for some strategy assets")
        flags = {(a, n): trend_flags(frame[a], n) for a in assets for n in self.config.windows}
        ready = frame.index[frame.index >= frame.index[min(self.config.longest, len(frame) - 1)]]
        if not self.state:
            if len(ready) == 0:
                raise ValueError("not enough history to start the paper book")
            first = ready[-1]
            self._init_state(first.date(), {a: float(frame.at[first, a]) for a in assets})
        last = self.state.get("last_date")
        start = date.fromisoformat(self.state["start_date"])
        # The book starts on its first close; never replay history before it.
        pending = [
            ts for ts in ready
            if ts.date() >= start and (last is None or ts.date() > date.fromisoformat(last))
        ]
        today = today or date.today()
        new_trades: List[Dict[str, Any]] = []
        for ts in pending:
            day = ts.date()
            late = (today - day).days > 1  # acted on after the next day: computer was off
            for key, data in self.state["sleeves"].items():
                asset, window = key.split("|")
                sleeve = Sleeve(asset=asset, cash=float(data["cash"]), units=float(data["units"]))
                trade = sleeve.step(day, float(frame.at[ts, asset]), bool(flags[(asset, int(window))].at[ts]),
                                    self.config.cost_pct)
                data["cash"], data["units"] = sleeve.cash, sleeve.units
                if trade:
                    trade.update({"sleeve": key, "late": late})
                    self.state["trades"].append(trade)
                    new_trades.append(trade)
            self.state["history"].append({
                "date": day.isoformat(),
                "nav": round(self._nav(frame, ts), 2),
                "benchmark_nav": round(sum(units * float(frame.at[ts, a])
                                           for a, units in self.state["benchmark_units"].items()), 2),
                "weights": self._weights(),
                "late": late,
            })
            self.state["last_date"] = day.isoformat()
        if pending:
            self._save()
        return {"processed_days": len(pending), "new_trades": new_trades, "weights": self._weights()}

    def _nav(self, frame: pd.DataFrame, ts: pd.Timestamp) -> float:
        total = 0.0
        for key, data in self.state["sleeves"].items():
            asset = key.split("|")[0]
            total += float(data["cash"]) + float(data["units"]) * float(frame.at[ts, asset])
        return total

    def _weights(self) -> Dict[str, float]:
        """Share of each asset's sleeves currently in the coin."""
        weights: Dict[str, float] = {}
        for asset in self.config.assets:
            keys = [k for k in self.state.get("sleeves", {}) if k.startswith(f"{asset}|")]
            invested = sum(1 for k in keys if float(self.state["sleeves"][k]["units"]) > 0)
            weights[asset] = round(invested / len(keys), 2) if keys else 0.0
        return weights

    # -------------------------------------------------------------- report
    def summary(self) -> Dict[str, Any]:
        history = self.state.get("history") or []
        if not history:
            return {"name": self.name, "days": 0}
        nav = pd.Series([h["nav"] for h in history], index=pd.to_datetime([h["date"] for h in history]))
        bench = pd.Series([h["benchmark_nav"] for h in history], index=nav.index)
        dd = float((nav / nav.cummax() - 1).min()) * 100
        bench_dd = float((bench / bench.cummax() - 1).min()) * 100
        return {
            "name": self.name,
            "start_date": self.state["start_date"],
            "last_date": self.state["last_date"],
            "days": len(history),
            "late_days": sum(1 for h in history if h.get("late")),
            "initial_capital": self.state["initial_capital"],
            "nav": history[-1]["nav"],
            "return_pct": round((history[-1]["nav"] / self.state["initial_capital"] - 1) * 100, 2),
            "benchmark_return_pct": round((history[-1]["benchmark_nav"] / self.state["initial_capital"] - 1) * 100, 2),
            "max_drawdown_pct": round(dd, 2),
            "benchmark_max_drawdown_pct": round(bench_dd, 2),
            "weights": history[-1]["weights"],
            "trade_count": len(self.state.get("trades") or []),
        }


def format_book_report(summary: Dict[str, Any], targets: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """Short Turkish report for the console / Telegram."""
    if not summary.get("days"):
        return "🪙 Kripto trend sanal portföyü henüz başlamadı."
    lines = [
        f"🪙 Kripto trend sanal portföyü ({summary['start_date']} → {summary['last_date']}, {summary['days']} gün)",
        f"Değer: {summary['nav']:,.2f} USD (başlangıç {summary['initial_capital']:,.0f}) | "
        f"getiri %{summary['return_pct']:+.2f} vs al-tut %{summary['benchmark_return_pct']:+.2f}",
        f"En büyük düşüş: strateji %{summary['max_drawdown_pct']:.1f} vs al-tut %{summary['benchmark_max_drawdown_pct']:.1f} | "
        f"işlem: {summary['trade_count']}",
    ]
    for asset, weight in (summary.get("weights") or {}).items():
        detail = ""
        if targets and asset in targets and targets[asset].get("close"):
            info = targets[asset]
            detail = f" (kapanış {info['close']:,.2f}; {len(info.get('above', []))}/{len(info.get('averages', {}))} ortalamanın üstünde)"
        lines.append(f"- {asset}: %{weight * 100:.0f} coin, %{(1 - weight) * 100:.0f} nakit{detail}")
    if summary.get("late_days"):
        lines.append(f"Not: {summary['late_days']} gün bilgisayar kapalıyken sonradan işlendi.")
    lines.append("Sanal işlemdir; gerçek emir verilmez. Kural: ortalamaların üstündeyse coin, altındaysa nakit.")
    return "\n".join(lines)


__all__ = ["DEFAULT_BOOK_DIR", "StrategyPaperBook", "format_book_report"]
