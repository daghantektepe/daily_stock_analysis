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


class QuantAllocationPaperBook:
    """Forward paper ledger for multi-asset target-weight quant strategies (PAA, Meta-Portfolio A).

    Strictly simulated (never sends real broker orders). Persists atomic JSON
    state inside ``data/strategy_paper/<name>.json`` alongside ``StrategyPaperBook``:

    - Day 1 (first completed close): deploys ``initial_capital`` into the
      strategy's causal target allocation with ``cost_bps`` per-side transaction cost.
    - Every subsequent completed trading day: marks all held ETF positions and
      the ``benchmark_symbol`` (default ``SPY``) buy-and-hold reference to market.
    - Rebalances automatically on the first completed close of each new month
      (``rebalance_mode="monthly"``, matching the empirical backtest 1-to-1) or
      on every close (``rebalance_mode="daily"``), or when ``force_rebalance=True``.
    - Strictly causal: on any bar ``ts``, ``weight_fn`` only ever sees ``prices.loc[:ts]``.
    """

    def __init__(
        self,
        name: str = "quant_paa",
        *,
        strategy_key: str = "paa",
        strategy_id: str = "PROTECTIVE_ASSET_ALLOCATION_PAA",
        label: str = "PAA Çöküş Kalkanı (US ETF)",
        benchmark_symbol: str = "SPY",
        initial_capital: float = 10_000.0,
        cost_bps: float = 5.0,
        rebalance_mode: str = "monthly",
        rebalance_band_pct: float = 1.0,
        min_trade_usd: float = 10.0,
        min_history_days: int = 252,
        book_dir: Optional[Path] = None,
    ) -> None:
        self.name = name
        self.strategy_key = strategy_key
        self.strategy_id = strategy_id
        self.label = label
        self.benchmark_symbol = benchmark_symbol.upper()
        self.initial_capital = float(initial_capital)
        self.cost_bps = max(0.0, float(cost_bps))
        self.rebalance_mode = rebalance_mode if rebalance_mode in ("monthly", "daily") else "monthly"
        self.rebalance_band_pct = max(0.0, float(rebalance_band_pct))
        self.min_trade_usd = max(0.0, float(min_trade_usd))
        self.min_history_days = max(20, int(min_history_days))
        self.path = Path(book_dir or DEFAULT_BOOK_DIR) / f"{name}.json"
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"quant paper book {self.path} is unreadable: {exc}") from exc
        return state if isinstance(state, dict) else {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=f".{self.name}_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(self.state, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _init_state(self, first_day: date, bench_price: float) -> None:
        self.state = {
            "simulated_only": True,
            "name": self.name,
            "strategy_key": self.strategy_key,
            "strategy_id": self.strategy_id,
            "label": self.label,
            "benchmark_symbol": self.benchmark_symbol,
            "cost_bps": self.cost_bps,
            "rebalance_mode": self.rebalance_mode,
            "rebalance_band_pct": self.rebalance_band_pct,
            "initial_capital": self.initial_capital,
            "start_date": first_day.isoformat(),
            "last_date": None,
            "last_rebalance_date": None,
            "cash": self.initial_capital,
            "positions": {},
            "benchmark_units": (self.initial_capital / bench_price) if bench_price > 0 else 0.0,
            "live_target_weights": {},
            "history": [],
            "trades": [],
        }

    @staticmethod
    def _clean_target_weights(raw_row: pd.Series, available_prices: Dict[str, float]) -> Dict[str, float]:
        weights: Dict[str, float] = {}
        total = 0.0
        for sym, val in raw_row.items():
            if pd.isna(val):
                continue
            w = float(val)
            if w <= 1e-4:
                continue
            price = available_prices.get(str(sym))
            if price is None or price <= 0:
                continue
            weights[str(sym)] = w
            total += w
        if total > 1.0 + 1e-9:
            weights = {sym: w / total for sym, w in weights.items()}
        return weights

    def _nav_and_weights(self, row_prices: Dict[str, float]) -> tuple[float, Dict[str, float]]:
        cash = float(self.state.get("cash", 0.0))
        positions = self.state.get("positions") or {}
        values: Dict[str, float] = {}
        total = cash
        for sym, pos in positions.items():
            shares = float(pos.get("shares", 0.0))
            if shares <= 1e-9:
                continue
            px = float(row_prices.get(sym) or pos.get("last_price") or pos.get("avg_cost") or 0.0)
            val = shares * px
            values[sym] = val
            total += val
        if total <= 1e-9:
            return 0.0, {}
        weights = {sym: round(val / total, 4) for sym, val in sorted(values.items()) if val / total >= 0.0005}
        return total, weights

    def _should_rebalance(self, day: date, *, force_rebalance: bool) -> tuple[bool, str]:
        last_rebal = self.state.get("last_rebalance_date")
        if not last_rebal:
            return True, "initial_allocation"
        if force_rebalance:
            return True, "manual_rebalance"
        if self.rebalance_mode == "daily":
            return True, "daily_rebalance"
        prev = date.fromisoformat(str(last_rebal))
        if (day.year, day.month) != (prev.year, prev.month):
            return True, "monthly_rebalance"
        return False, ""

    def _rebalance(
        self,
        day: date,
        row_prices: Dict[str, float],
        target_weights: Dict[str, float],
        *,
        reason: str,
        late: bool,
    ) -> List[Dict[str, Any]]:
        nav_before, cur_weights = self._nav_and_weights(row_prices)
        if nav_before <= 1e-9:
            return []

        all_syms = sorted(set(cur_weights.keys()) | set(target_weights.keys()))
        max_drift_pct = max(
            (abs(target_weights.get(s, 0.0) - cur_weights.get(s, 0.0)) * 100.0 for s in all_syms),
            default=0.0,
        )
        if reason != "initial_allocation" and max_drift_pct < self.rebalance_band_pct:
            return []

        cost_rate = self.cost_bps / 10_000.0
        positions: Dict[str, Dict[str, Any]] = self.state.setdefault("positions", {})
        cash = float(self.state.get("cash", 0.0))
        executed: List[Dict[str, Any]] = []

        # 1. Execute SELLS first so cash proceeds fund subsequent BUYS
        buy_intents: List[tuple[str, float, float, float]] = []  # (sym, buy_notional, px, target_w)
        for sym in all_syms:
            px = float(row_prices.get(sym) or 0.0)
            if px <= 0:
                continue
            pos = positions.get(sym)
            cur_shares = float(pos.get("shares", 0.0)) if pos else 0.0
            cur_val = cur_shares * px
            target_w = float(target_weights.get(sym, 0.0))
            target_val = nav_before * target_w
            delta = target_val - cur_val

            if delta < 0:
                closing = target_w <= 1e-4
                if not closing and abs(delta) < self.min_trade_usd:
                    continue
                sell_shares = cur_shares if closing else min(cur_shares, abs(delta) / px)
                sell_notional = sell_shares * px
                if sell_notional <= 1e-6:
                    continue
                cost = sell_notional * cost_rate
                cash += sell_notional - cost
                remaining = cur_shares - sell_shares
                if remaining <= 1e-8 or closing:
                    positions.pop(sym, None)
                else:
                    pos["shares"] = round(remaining, 8)
                    pos["last_price"] = round(px, 4)
                executed.append(
                    {
                        "date": day.isoformat(),
                        "symbol": sym,
                        "side": "SELL",
                        "shares": round(sell_shares, 6),
                        "price": round(px, 4),
                        "notional": round(sell_notional, 2),
                        "cost": round(cost, 4),
                        "target_weight_pct": round(target_w * 100.0, 2),
                        "reason": reason,
                        "late": late,
                    }
                )
            elif delta >= self.min_trade_usd:
                buy_intents.append((sym, delta, px, target_w))

        # 2. Execute BUYS scaled cleanly to available cash after transaction costs
        total_buy_cash_needed = sum(notional * (1.0 + cost_rate) for _, notional, _, _ in buy_intents)
        scale = 1.0
        if total_buy_cash_needed > cash and total_buy_cash_needed > 1e-9:
            scale = max(0.0, cash / total_buy_cash_needed)

        for sym, raw_notional, px, target_w in buy_intents:
            buy_notional = raw_notional * scale
            if buy_notional < self.min_trade_usd * 0.5:
                continue
            cost = buy_notional * cost_rate
            total_debit = buy_notional + cost
            if total_debit > cash + 1e-6:
                buy_notional = cash / (1.0 + cost_rate)
                cost = buy_notional * cost_rate
                total_debit = buy_notional + cost
            if buy_notional <= 1e-6:
                continue
            buy_shares = buy_notional / px
            cash = max(0.0, cash - total_debit)
            prev = positions.get(sym)
            if prev and float(prev.get("shares", 0.0)) > 1e-9:
                prev_shares = float(prev["shares"])
                prev_cost = float(prev.get("avg_cost", px))
                new_shares = prev_shares + buy_shares
                avg_cost = (prev_shares * prev_cost + buy_shares * px) / new_shares
                positions[sym] = {
                    "shares": round(new_shares, 8),
                    "avg_cost": round(avg_cost, 4),
                    "last_price": round(px, 4),
                }
            else:
                positions[sym] = {
                    "shares": round(buy_shares, 8),
                    "avg_cost": round(px, 4),
                    "last_price": round(px, 4),
                }
            executed.append(
                {
                    "date": day.isoformat(),
                    "symbol": sym,
                    "side": "BUY",
                    "shares": round(buy_shares, 6),
                    "price": round(px, 4),
                    "notional": round(buy_notional, 2),
                    "cost": round(cost, 4),
                    "target_weight_pct": round(target_w * 100.0, 2),
                    "reason": reason,
                    "late": late,
                }
            )

        self.state["cash"] = round(cash, 4)
        if executed:
            self.state["last_rebalance_date"] = day.isoformat()
            self.state.setdefault("trades", []).extend(executed)
        return executed

    def step(
        self,
        prices: pd.DataFrame,
        weight_fn: Any,
        *,
        today: Optional[date] = None,
        force_rebalance: bool = False,
    ) -> Dict[str, Any]:
        """Advance the paper book strictly forward through every completed close after ``last_date``."""
        frame = prices.sort_index().ffill()
        if frame.empty or self.benchmark_symbol not in frame.columns:
            raise ValueError(f"prices missing benchmark column {self.benchmark_symbol}")
        bench_series = frame[self.benchmark_symbol].dropna()
        if len(bench_series) < min(self.min_history_days, 30):
            raise ValueError("not enough price history to run quant allocation paper book")

        frame = frame.loc[bench_series.index]
        ready_start_idx = min(self.min_history_days, len(frame) - 1)
        ready = frame.index[ready_start_idx:]
        if len(ready) == 0:
            raise ValueError("not enough history after warmup window")

        if not self.state:
            first_ts = ready[-1]
            self._init_state(first_ts.date(), float(frame.at[first_ts, self.benchmark_symbol]))

        last = self.state.get("last_date")
        start = date.fromisoformat(str(self.state["start_date"]))
        pending = [
            ts for ts in ready
            if ts.date() >= start and (last is None or ts.date() > date.fromisoformat(str(last)))
        ]
        today = today or date.today()
        new_trades: List[Dict[str, Any]] = []

        # Allow explicit force_rebalance even when today's bar was already stepped
        if not pending and force_rebalance and last:
            latest_ts = ready[-1]
            row_prices = {str(col): float(val) for col, val in frame.loc[latest_ts].items() if pd.notna(val) and float(val) > 0}
            w_df = weight_fn(frame.loc[:latest_ts])
            target_w = self._clean_target_weights(w_df.iloc[-1], row_prices) if not w_df.empty else {}
            self.state["live_target_weights"] = {k: round(v * 100.0, 2) for k, v in sorted(target_w.items(), key=lambda kv: -kv[1])}
            trades = self._rebalance(
                latest_ts.date(),
                row_prices,
                target_w,
                reason="manual_rebalance",
                late=False,
            )
            new_trades.extend(trades)
            nav_after, cur_w = self._nav_and_weights(row_prices)
            if self.state.get("history"):
                self.state["history"][-1]["nav"] = round(nav_after, 2)
                self.state["history"][-1]["cash"] = round(float(self.state.get("cash", 0.0)), 2)
                self.state["history"][-1]["weights"] = cur_w
                self.state["history"][-1]["target_weights"] = {k: round(v, 4) for k, v in target_w.items()}
                self.state["history"][-1]["rebalanced"] = bool(trades) or bool(self.state["history"][-1].get("rebalanced"))
            self._save()
            return {
                "processed_days": 0,
                "new_trades": new_trades,
                "weights": cur_w,
                "live_target_weights_pct": self.state["live_target_weights"],
            }

        for ts in pending:
            day = ts.date()
            # US ETFs skip Sat/Sun -> >3 calendar days means computer missed trading day(s)
            late = (today - day).days > 3
            row_prices = {str(col): float(val) for col, val in frame.loc[ts].items() if pd.notna(val) and float(val) > 0}
            for sym, pos in (self.state.get("positions") or {}).items():
                if sym in row_prices:
                    pos["last_price"] = round(row_prices[sym], 4)

            should_rebal, reason = self._should_rebalance(
                day,
                force_rebalance=(force_rebalance and ts == pending[-1]),
            )
            target_w: Dict[str, float] = {}
            rebalanced = False
            if should_rebal or ts == pending[-1]:
                # Strictly causal slice: only closes <= ts
                w_df = weight_fn(frame.loc[:ts])
                target_w = self._clean_target_weights(w_df.iloc[-1], row_prices) if not w_df.empty else {}
                if ts == pending[-1]:
                    self.state["live_target_weights"] = {
                        k: round(v * 100.0, 2) for k, v in sorted(target_w.items(), key=lambda kv: -kv[1])
                    }
            if should_rebal:
                trades = self._rebalance(day, row_prices, target_w, reason=reason, late=late)
                if trades:
                    new_trades.extend(trades)
                    rebalanced = True

            nav_after, cur_w = self._nav_and_weights(row_prices)
            bench_nav = float(self.state.get("benchmark_units", 0.0)) * float(row_prices[self.benchmark_symbol])
            self.state.setdefault("history", []).append(
                {
                    "date": day.isoformat(),
                    "nav": round(nav_after, 2),
                    "cash": round(float(self.state.get("cash", 0.0)), 2),
                    "benchmark_nav": round(bench_nav, 2),
                    "weights": cur_w,
                    "target_weights": {k: round(v, 4) for k, v in target_w.items()} if target_w else cur_w,
                    "rebalanced": rebalanced,
                    "late": late,
                }
            )
            self.state["last_date"] = day.isoformat()

        if pending:
            self._save()

        # Refresh live target signal even if already up to date (without mutating NAV/trades)
        if not pending and self.state:
            latest_ts = ready[-1]
            row_prices = {str(col): float(val) for col, val in frame.loc[latest_ts].items() if pd.notna(val) and float(val) > 0}
            w_df = weight_fn(frame.loc[:latest_ts])
            target_w = self._clean_target_weights(w_df.iloc[-1], row_prices) if not w_df.empty else {}
            live_pct = {k: round(v * 100.0, 2) for k, v in sorted(target_w.items(), key=lambda kv: -kv[1])}
            if live_pct != self.state.get("live_target_weights"):
                self.state["live_target_weights"] = live_pct
                self._save()

        last_weights = (self.state.get("history") or [{}])[-1].get("weights", {})
        return {
            "processed_days": len(pending),
            "new_trades": new_trades,
            "weights": last_weights,
            "live_target_weights_pct": self.state.get("live_target_weights") or {},
        }

    def summary(self) -> Dict[str, Any]:
        history = self.state.get("history") or []
        if not history:
            return {
                "name": self.name,
                "strategy_key": self.strategy_key,
                "strategy_id": self.strategy_id,
                "label": self.label,
                "benchmark_symbol": self.benchmark_symbol,
                "simulated_only": True,
                "days": 0,
                "initial_capital": self.initial_capital,
                "nav": self.initial_capital,
                "cash": self.initial_capital,
                "return_pct": 0.0,
                "benchmark_return_pct": 0.0,
                "excess_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "benchmark_max_drawdown_pct": 0.0,
                "trade_count": 0,
                "weights_pct": {},
                "live_target_weights_pct": self.state.get("live_target_weights") or {},
                "positions": [],
                "recent_trades": [],
                "history": [],
            }

        nav = pd.Series([float(h["nav"]) for h in history], index=pd.to_datetime([h["date"] for h in history]))
        bench = pd.Series([float(h["benchmark_nav"]) for h in history], index=nav.index)
        dd = float((nav / nav.cummax() - 1.0).min()) * 100.0
        bench_dd = float((bench / bench.cummax() - 1.0).min()) * 100.0
        init_cap = float(self.state.get("initial_capital", self.initial_capital))
        cur_nav = float(history[-1]["nav"])
        cur_bench = float(history[-1]["benchmark_nav"])
        ret_pct = round((cur_nav / init_cap - 1.0) * 100.0, 2) if init_cap > 0 else 0.0
        bench_ret_pct = round((cur_bench / init_cap - 1.0) * 100.0, 2) if init_cap > 0 else 0.0

        positions_list: List[Dict[str, Any]] = []
        raw_positions = self.state.get("positions") or {}
        for sym, pos in sorted(raw_positions.items()):
            shares = float(pos.get("shares", 0.0))
            if shares <= 1e-9:
                continue
            avg_cost = float(pos.get("avg_cost", 0.0))
            last_price = float(pos.get("last_price", avg_cost))
            mkt_val = shares * last_price
            pnl_usd = (last_price - avg_cost) * shares
            pnl_pct = ((last_price / avg_cost) - 1.0) * 100.0 if avg_cost > 0 else 0.0
            positions_list.append(
                {
                    "symbol": sym,
                    "shares": round(shares, 4),
                    "avg_cost": round(avg_cost, 4),
                    "last_price": round(last_price, 4),
                    "market_value": round(mkt_val, 2),
                    "weight_pct": round((mkt_val / cur_nav) * 100.0, 2) if cur_nav > 0 else 0.0,
                    "unrealized_pnl_usd": round(pnl_usd, 2),
                    "unrealized_pnl_pct": round(pnl_pct, 2),
                }
            )
        positions_list.sort(key=lambda item: -item["weight_pct"])

        weights_pct = {
            k: round(float(v) * 100.0, 2)
            for k, v in sorted((history[-1].get("weights") or {}).items(), key=lambda kv: -float(kv[1]))
        }
        return {
            "name": self.state.get("name", self.name),
            "strategy_key": self.state.get("strategy_key", self.strategy_key),
            "strategy_id": self.state.get("strategy_id", self.strategy_id),
            "label": self.state.get("label", self.label),
            "benchmark_symbol": self.state.get("benchmark_symbol", self.benchmark_symbol),
            "rebalance_mode": self.state.get("rebalance_mode", self.rebalance_mode),
            "cost_bps": float(self.state.get("cost_bps", self.cost_bps)),
            "simulated_only": True,
            "start_date": self.state.get("start_date"),
            "last_date": self.state.get("last_date"),
            "last_rebalance_date": self.state.get("last_rebalance_date"),
            "days": len(history),
            "late_days": sum(1 for h in history if h.get("late")),
            "initial_capital": round(init_cap, 2),
            "nav": round(cur_nav, 2),
            "cash": round(float(self.state.get("cash", 0.0)), 2),
            "cash_pct": round((float(self.state.get("cash", 0.0)) / cur_nav) * 100.0, 2) if cur_nav > 0 else 100.0,
            "return_pct": ret_pct,
            "benchmark_return_pct": bench_ret_pct,
            "excess_return_pct": round(ret_pct - bench_ret_pct, 2),
            "max_drawdown_pct": round(dd, 2),
            "benchmark_max_drawdown_pct": round(bench_dd, 2),
            "weights_pct": weights_pct,
            "live_target_weights_pct": self.state.get("live_target_weights") or {},
            "positions": positions_list,
            "trade_count": len(self.state.get("trades") or []),
            "recent_trades": list(reversed((self.state.get("trades") or [])[-12:])),
            "history": history[-180:],
        }


def format_quant_book_report(summary: Dict[str, Any]) -> str:
    """Short Turkish report for PAA / Meta-Portfolio A StrategyPaperBook (console / Telegram)."""
    label = summary.get("label") or summary.get("name") or "Quant Sanal Portföy"
    if not summary.get("days"):
        return f"🛡️ {label} sanal portföyü henüz başlamadı."
    bench = summary.get("benchmark_symbol") or "SPY"
    lines = [
        f"🛡️ {label} ({summary['start_date']} → {summary['last_date']}, {summary['days']} gün)",
        f"Değer: {summary['nav']:,.2f} USD (başlangıç {summary['initial_capital']:,.0f}) | "
        f"getiri %{summary['return_pct']:+.2f} vs {bench} %{summary['benchmark_return_pct']:+.2f} "
        f"(fark %{summary['excess_return_pct']:+.2f})",
        f"En büyük düşüş: strateji %{summary['max_drawdown_pct']:.2f} vs {bench} %{summary['benchmark_max_drawdown_pct']:.2f} | "
        f"işlem: {summary['trade_count']} | son rebalance: {summary.get('last_rebalance_date') or '-'}",
    ]
    weights_pct = summary.get("weights_pct") or {}
    if weights_pct:
        alloc = " · ".join(f"{sym} %{pct:.1f}" for sym, pct in weights_pct.items())
        cash_pct = float(summary.get("cash_pct") or 0.0)
        if cash_pct >= 0.5:
            alloc = f"{alloc} · Nakit %{cash_pct:.1f}"
        lines.append(f"Güncel Dağılım: {alloc}")
    else:
        lines.append("Güncel Dağılım: %100 Nakit")
    live_targets = summary.get("live_target_weights_pct") or {}
    if live_targets and live_targets != weights_pct:
        live_str = " · ".join(f"{sym} %{pct:.1f}" for sym, pct in live_targets.items())
        lines.append(f"Canlı Sinyal Hedefi: {live_str}")
    if summary.get("late_days"):
        lines.append(f"Not: {summary['late_days']} gün bilgisayar kapalıyken sonradan işlendi.")
    lines.append("Sanal işlemdir; gerçek aracı kurum emri gönderilmez.")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_BOOK_DIR",
    "QuantAllocationPaperBook",
    "StrategyPaperBook",
    "format_book_report",
    "format_quant_book_report",
]
