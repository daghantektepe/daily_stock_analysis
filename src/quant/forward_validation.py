# -*- coding: utf-8 -*-
"""Forward (live paper) validation for the quant allocation strategies (PAA, Meta-Portfolio A).

The 2022-2026 "OOS" window was used to tune PAA v2 / QQQ hysteresis / the
Meta-A blend, so it is no longer out-of-sample. The only clean evidence is data
that arrives after the strategy is frozen. This module:

1. **Freezes** a strategy: a SHA-256 fingerprint of the weight function, every
   library helper / constant it references, and the paper-book settings, plus
   the freeze date. Forward days are counted only after the freeze.
2. **Invalidates** the forward record when the code or settings change later
   (``INVALIDATED``): tuning after the start would contaminate the test.
3. **Gates** the record with the QA plan criteria (defaults): >= 120 forward
   trading days, Excess Sharpe vs BIL >= 0.50, max drawdown no worse than
   -18%, measured execution slippage <= 20 bps, <= 10% days processed late.
4. **Compares** forward return with the frozen backtest: the percentile of the
   forward return among all historical windows of the same length (a forward
   result below the 5th percentile is a warning sign of overfitting).
5. **Measures slippage** on the Alpaca paper account: plans orders that move
   the paper account to the book's target weights (read-only), optionally
   submits them **only** to paper with an explicit command, and reconciles
   fills against the price seen at submission.

Nothing here changes ``ALPACA_PAPER`` / ``ALPACA_AUTO_EXECUTE``; the daily
scheduler never submits orders.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_PATH = Path("data") / "strategy_paper" / "forward_validation.json"
FORWARD_ORDER_PREFIX = "dsa-fwd"

STATUS_COLLECTING = "COLLECTING"
STATUS_PASS = "PASS"
STATUS_PASS_PENDING_SLIPPAGE = "PASS_PENDING_SLIPPAGE"
STATUS_FAIL = "FAIL"
STATUS_INVALIDATED = "INVALIDATED"
STATUS_NOT_FROZEN = "NOT_FROZEN"


@dataclass(frozen=True)
class ForwardGate:
    """Criteria for leaving paper trading (QA plan, Faz 4)."""

    min_trading_days: int = 120
    min_excess_sharpe: float = 0.50
    max_drawdown_pct: float = 18.0
    max_slippage_bps: float = 20.0
    max_late_ratio: float = 0.10
    min_slippage_fills: int = 5


# ------------------------------------------------------------------ fingerprint
def _module_references(source: str, names: Iterable[str]) -> List[str]:
    return [name for name in names if re.search(rf"\b{re.escape(name)}\b", source)]


def strategy_fingerprint(weight_fn: Callable[..., Any], settings: Dict[str, Any]) -> Dict[str, Any]:
    """Hash of ``weight_fn``, every same-module function / constant it reaches, and ``settings``.

    Unrelated strategies in the same module do not change the fingerprint; any
    edit to the code path this strategy actually runs does.
    """
    module = inspect.getmodule(weight_fn)
    members = dict(inspect.getmembers(module)) if module else {}
    functions = {
        name: obj for name, obj in members.items()
        if inspect.isfunction(obj) and getattr(obj, "__module__", None) == getattr(module, "__name__", None)
    }
    constants = {
        name: obj for name, obj in members.items()
        if name.isupper() and isinstance(obj, (int, float, str, tuple, list, dict, frozenset))
    }
    seen: List[str] = []
    queue = [weight_fn.__name__]
    while queue:
        name = queue.pop(0)
        if name in seen or name not in functions:
            continue
        seen.append(name)
        queue.extend(n for n in _module_references(inspect.getsource(functions[name]), functions) if n not in seen)
    used_constants = sorted({
        const for name in seen for const in _module_references(inspect.getsource(functions[name]), constants)
    })
    digest = hashlib.sha256()
    for name in sorted(seen):
        digest.update(name.encode())
        digest.update(inspect.getsource(functions[name]).encode())
    for const in used_constants:
        digest.update(f"{const}={constants[const]!r}".encode())
    digest.update(json.dumps(settings, sort_keys=True).encode())
    return {
        "sha256": digest.hexdigest(),
        "functions": sorted(seen),
        "constants": used_constants,
        "settings": dict(settings),
    }


# --------------------------------------------------------------------- registry
class ForwardRegistry:
    """JSON registry of frozen strategies, Alpaca forward orders and fills."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path or DEFAULT_REGISTRY_PATH)
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.data = {}
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"forward validation registry {self.path} is unreadable: {exc}") from exc
        self.data.setdefault("strategies", {})
        self.data.setdefault("orders", [])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".forward_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(self.data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def get(self, strategy_key: str) -> Optional[Dict[str, Any]]:
        return self.data["strategies"].get(strategy_key)

    def freeze(self, strategy_key: str, fingerprint: Dict[str, Any], frozen_date: date,
               expectation: Optional[Dict[str, Any]] = None, *, reset: bool = False) -> Dict[str, Any]:
        """Register the freeze; an existing freeze is kept unless ``reset`` (a new forward test)."""
        existing = self.get(strategy_key)
        if existing and not reset:
            return existing
        history = list(existing.get("previous", [])) if existing else []
        if existing:
            history.append({k: existing[k] for k in ("frozen_date", "fingerprint") if k in existing})
        entry = {
            "strategy_key": strategy_key,
            "frozen_date": frozen_date.isoformat(),
            "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fingerprint": fingerprint,
            "expectation": expectation or {},
            "previous": history,
        }
        self.data["strategies"][strategy_key] = entry
        self.save()
        return entry


# ------------------------------------------------------------------ expectation
def backtest_expectation(
    prices: pd.DataFrame,
    weight_fn: Callable[[pd.DataFrame], pd.DataFrame],
    *,
    cost_bps: float,
    until: date,
    window_days: Sequence[int] = (20, 60, 120, 250),
) -> Dict[str, Any]:
    """Frozen backtest (data up to ``until``): daily net returns and rolling-window return percentiles."""
    from src.quant.strategies.engine import StrategySpec, backtest_weight_matrix

    history = prices.loc[: pd.Timestamp(until)]
    weights = weight_fn(history)
    spec = StrategySpec(strategy_id="FORWARD_EXPECTATION", name="forward expectation", universe="us_etf",
                        category="forward", description="", cost_bps=float(cost_bps))
    rf = history["BIL"].pct_change() if "BIL" in history.columns else None
    result = backtest_weight_matrix(history, weights, spec, rf_returns=rf)
    returns = result.daily_returns
    if returns is None or len(returns) < 60:
        return {}
    returns = returns[returns.index >= returns.index[0]]
    growth = (1.0 + returns).cumprod()
    windows: Dict[str, Dict[str, float]] = {}
    for n in window_days:
        if len(growth) <= n:
            continue
        rolling = (growth / growth.shift(n) - 1.0).dropna() * 100.0
        windows[str(n)] = {q: round(float(rolling.quantile(p)), 2)
                           for q, p in (("p5", 0.05), ("p25", 0.25), ("p50", 0.5), ("p75", 0.75), ("p95", 0.95))}
    return {
        "until": until.isoformat(),
        "start": returns.index[0].date().isoformat(),
        "cagr_pct": result.full.cagr_pct,
        "excess_sharpe": result.full.excess_sharpe,
        "max_drawdown_pct": result.full.max_drawdown_pct,
        "vol_pct": result.full.vol_pct,
        "window_return_pct": windows,
        "_daily_returns": returns,
    }


def forward_percentile(expectation_returns: pd.Series, forward_return_pct: float, n_days: int) -> Optional[float]:
    """Share of historical n-day windows whose return was below the forward return (0-100)."""
    if expectation_returns is None or len(expectation_returns) <= n_days or n_days < 5:
        return None
    growth = (1.0 + expectation_returns).cumprod()
    rolling = (growth / growth.shift(n_days) - 1.0).dropna() * 100.0
    if rolling.empty:
        return None
    return round(float((rolling < forward_return_pct).mean()) * 100.0, 1)


# ------------------------------------------------------------------- evaluation
def _drawdown_pct(nav: pd.Series) -> float:
    return float((nav / nav.cummax() - 1.0).min()) * 100.0 if len(nav) else 0.0


def slippage_summary(orders: Sequence[Dict[str, Any]], strategy_key: Optional[str] = None) -> Dict[str, Any]:
    """Notional-weighted execution slippage of filled forward orders (positive = paid more than quoted)."""
    fills = [o for o in orders if o.get("status") == "filled" and o.get("slippage_bps") is not None
             and (strategy_key is None or o.get("strategy_key") == strategy_key)]
    if not fills:
        return {"fills": 0, "avg_bps": None, "worst_bps": None}
    notional = [abs(float(o.get("filled_notional") or 0.0)) or 1.0 for o in fills]
    weighted = sum(float(o["slippage_bps"]) * w for o, w in zip(fills, notional)) / sum(notional)
    return {
        "fills": len(fills),
        "avg_bps": round(weighted, 2),
        "worst_bps": round(max(float(o["slippage_bps"]) for o in fills), 2),
    }


def evaluate_forward_record(
    book_state: Dict[str, Any],
    frozen: Optional[Dict[str, Any]],
    current_fingerprint: Optional[Dict[str, Any]],
    *,
    rf_closes: Optional[pd.Series] = None,
    expectation_returns: Optional[pd.Series] = None,
    orders: Sequence[Dict[str, Any]] = (),
    gate: ForwardGate = ForwardGate(),
) -> Dict[str, Any]:
    """Gate verdict for one strategy's forward paper record."""
    from src.quant.stats import compute_performance_metrics

    key = book_state.get("strategy_key") or (frozen or {}).get("strategy_key")
    base: Dict[str, Any] = {"strategy_key": key, "label": book_state.get("label"), "gate": asdict(gate)}
    if not frozen:
        return {**base, "status": STATUS_NOT_FROZEN, "reasons": ["Strateji dondurulmadı; ileri test başlamadı."]}
    base.update({"frozen_date": frozen["frozen_date"], "fingerprint": frozen["fingerprint"]["sha256"][:12]})
    if current_fingerprint and current_fingerprint["sha256"] != frozen["fingerprint"]["sha256"]:
        changed = sorted(set(current_fingerprint["functions"]) ^ set(frozen["fingerprint"]["functions"]))
        settings_changed = current_fingerprint.get("settings") != frozen["fingerprint"].get("settings")
        detail = "ayarlar" if settings_changed else "kod"
        return {**base, "status": STATUS_INVALIDATED, "reasons": [
            f"Dondurmadan sonra strateji {detail} değişti (parmak izi {frozen['fingerprint']['sha256'][:12]} → "
            f"{current_fingerprint['sha256'][:12]}{'; fonksiyon kümesi: ' + ', '.join(changed) if changed else ''}). "
            "İleri test kirlendi; `freeze --reset` ile yeni test başlatılmalı.",
        ]}

    frozen_day = date.fromisoformat(frozen["frozen_date"])
    history = [h for h in (book_state.get("history") or []) if date.fromisoformat(h["date"]) >= frozen_day]
    if len(history) < 2:
        return {**base, "status": STATUS_COLLECTING, "forward_days": 0,
                "reasons": ["Dondurmadan sonra henüz tamamlanmış işlem günü yok."]}
    index = pd.to_datetime([h["date"] for h in history])
    nav = pd.Series([float(h["nav"]) for h in history], index=index)
    bench = pd.Series([float(h.get("benchmark_nav") or 0.0) for h in history], index=index)
    forward_days = len(history) - 1  # first row is the freeze-day baseline
    late_days = sum(1 for h in history[1:] if h.get("late"))
    rf_returns = None
    if rf_closes is not None and not rf_closes.empty:
        rf_returns = rf_closes.sort_index().ffill().pct_change().reindex(index).fillna(0.0)
    metrics = compute_performance_metrics(nav, rf_returns=rf_returns)
    bench_metrics = compute_performance_metrics(bench, rf_returns=rf_returns) if bench.iloc[0] > 0 else None
    forward_return = (nav.iloc[-1] / nav.iloc[0] - 1.0) * 100.0
    max_dd = _drawdown_pct(nav)
    slip = slippage_summary(orders, key)
    # Sharpe estimated from n days has a standard error of about sqrt(252 / n).
    sharpe_se = round(math.sqrt(252.0 / forward_days), 2)
    result = {
        **base,
        "forward_days": forward_days,
        "late_days": late_days,
        "late_ratio": round(late_days / forward_days, 3),
        "forward_return_pct": round(forward_return, 2),
        "benchmark_return_pct": round((bench.iloc[-1] / bench.iloc[0] - 1.0) * 100.0, 2) if bench.iloc[0] > 0 else None,
        "excess_sharpe": metrics.excess_sharpe,
        "excess_sharpe_se": sharpe_se,
        "max_drawdown_pct": round(max_dd, 2),
        "benchmark_excess_sharpe": bench_metrics.excess_sharpe if bench_metrics else None,
        "slippage": slip,
        "backtest_percentile": forward_percentile(expectation_returns, forward_return, forward_days),
    }
    reasons: List[str] = []
    warnings: List[str] = []
    if max_dd < -gate.max_drawdown_pct:
        reasons.append(f"En büyük düşüş %{max_dd:.1f}, sınır -%{gate.max_drawdown_pct:.0f}.")
        return {**result, "status": STATUS_FAIL, "reasons": reasons, "warnings": warnings}
    pct = result["backtest_percentile"]
    if pct is not None and pct < 5.0:
        warnings.append(f"İleri getiri, backtest'teki aynı uzunluktaki dönemlerin %{pct:.0f}'inden kötü: aşırı uyum belirtisi olabilir.")
    if forward_days < gate.min_trading_days:
        reasons.append(f"{forward_days}/{gate.min_trading_days} ileri işlem günü toplandı.")
        return {**result, "status": STATUS_COLLECTING, "reasons": reasons, "warnings": warnings}
    if metrics.excess_sharpe < gate.min_excess_sharpe:
        reasons.append(f"BIL üstü Sharpe {metrics.excess_sharpe:.2f} < {gate.min_excess_sharpe:.2f}.")
    if result["late_ratio"] > gate.max_late_ratio:
        reasons.append(f"Günlerin %{result['late_ratio'] * 100:.0f}'i sonradan işlendi (sınır %{gate.max_late_ratio * 100:.0f}).")
    if slip["fills"] >= gate.min_slippage_fills and slip["avg_bps"] is not None and slip["avg_bps"] > gate.max_slippage_bps:
        reasons.append(f"Ortalama kayma {slip['avg_bps']:.1f} bps > {gate.max_slippage_bps:.0f} bps.")
    if reasons:
        return {**result, "status": STATUS_FAIL, "reasons": reasons, "warnings": warnings}
    if slip["fills"] < gate.min_slippage_fills:
        return {**result, "status": STATUS_PASS_PENDING_SLIPPAGE, "warnings": warnings, "reasons": [
            f"Getiri kriterleri geçti, ama kayma ölçümü yetersiz ({slip['fills']}/{gate.min_slippage_fills} Alpaca sanal dolum).",
        ]}
    return {**result, "status": STATUS_PASS, "reasons": [], "warnings": warnings}


_STATUS_TEXT = {
    STATUS_COLLECTING: "⏳ veri toplanıyor",
    STATUS_PASS: "✅ kapıyı geçti",
    STATUS_PASS_PENDING_SLIPPAGE: "🟡 getiri geçti, kayma ölçülmedi",
    STATUS_FAIL: "❌ kapıdan kaldı",
    STATUS_INVALIDATED: "⚠️ geçersiz (strateji değişti)",
    STATUS_NOT_FROZEN: "— dondurulmadı",
}


def format_forward_report(results: Sequence[Dict[str, Any]]) -> str:
    """Turkish text report of the forward gate for every frozen strategy."""
    lines = ["🧪 İleri doğrulama (dondurulmuş strateji, gerçek para yok)"]
    for res in results:
        label = res.get("label") or res.get("strategy_key")
        lines.append(f"\n{label}: {_STATUS_TEXT.get(res['status'], res['status'])}")
        if res.get("frozen_date"):
            lines.append(f"  Dondurma: {res['frozen_date']} (parmak izi {res.get('fingerprint')})")
        if res.get("forward_days"):
            gate = res["gate"]
            pct = res.get("backtest_percentile")
            slip = res.get("slippage") or {}
            bench = res.get("benchmark_return_pct")
            lines.append(
                f"  {res['forward_days']}/{gate['min_trading_days']} gün | getiri %{res['forward_return_pct']:+.2f}"
                + (f" (SPY %{bench:+.2f})" if bench is not None else "")
                + f" | BIL üstü Sharpe {res['excess_sharpe']:.2f} ± {res['excess_sharpe_se']:.2f} (eşik {gate['min_excess_sharpe']:.2f})"
                + f" | en büyük düşüş %{res['max_drawdown_pct']:.1f} (sınır -%{gate['max_drawdown_pct']:.0f})"
            )
            lines.append(
                "  Backtest kıyası: " + (f"ileri getiri, aynı uzunluktaki geçmiş dönemlerin %{pct:.0f}'inden iyi" if pct is not None else "henüz kısa")
                + f" | kayma: {slip.get('fills', 0)} dolum"
                + (f", ort. {slip['avg_bps']:.1f} bps" if slip.get("avg_bps") is not None else "")
                + f" | sonradan işlenen gün: {res.get('late_days', 0)}"
            )
        for reason in res.get("reasons") or []:
            lines.append(f"  • {reason}")
        for warning in res.get("warnings") or []:
            lines.append(f"  ⚠️ {warning}")
    lines.append(
        "\nNot: 120 günlük Sharpe tahmininin hata payı ±1,4 civarıdır; kapıyı geçmek kanıtın başlangıcıdır, garantisi değil. "
        "Kapı geçilmeden ALPACA_PAPER=true ve ALPACA_AUTO_EXECUTE=false kalır."
    )
    return "\n".join(lines)


# ----------------------------------------------------------------- orchestration
def _book_settings(book: Any) -> Dict[str, Any]:
    return {"cost_bps": book.cost_bps, "rebalance_mode": book.rebalance_mode,
            "rebalance_band_pct": book.rebalance_band_pct, "benchmark_symbol": book.benchmark_symbol}


def run_forward_validation(
    *,
    strategies: Optional[Sequence[str]] = None,
    prices: Optional[pd.DataFrame] = None,
    auto_freeze: bool = True,
    reset: bool = False,
    registry: Optional[ForwardRegistry] = None,
    book_dir: Optional[Path] = None,
    paper_settings: Optional[Dict[str, Any]] = None,
    gate: ForwardGate = ForwardGate(),
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Freeze (if needed) and evaluate every requested quant paper strategy."""
    from src.quant.paper_book import (
        QUANT_PAPER_SPECS,
        build_quant_paper_book,
        load_quant_paper_prices,
        normalize_quant_paper_strategies,
    )

    # The registry lives next to the paper books it validates.
    registry = registry or ForwardRegistry(Path(book_dir) / DEFAULT_REGISTRY_PATH.name if book_dir else None)
    settings = dict(paper_settings or {})
    norm_keys = normalize_quant_paper_strategies(strategies)
    needs_macro_v3 = any(bool(QUANT_PAPER_SPECS.get(k, {}).get("requires_macro_v3")) for k in norm_keys)
    frame = prices if prices is not None else load_quant_paper_prices(include_macro_v3=needs_macro_v3)
    results: List[Dict[str, Any]] = []
    for key in norm_keys:
        book, weight_fn = build_quant_paper_book(key, book_dir=book_dir, **settings)
        fingerprint = strategy_fingerprint(weight_fn, _book_settings(book))
        frozen = registry.get(key)
        if (frozen is None and auto_freeze) or reset:
            last = book.state.get("last_date")
            frozen_day = date.fromisoformat(last) if last else (today or date.today())
            expectation = {}
            if frame is not None and not frame.empty:
                try:
                    raw = backtest_expectation(frame, weight_fn, cost_bps=book.cost_bps, until=frozen_day)
                    expectation = {k: v for k, v in raw.items() if not k.startswith("_")}
                except Exception as exc:  # noqa: BLE001 - expectation is optional context
                    logger.warning("[forward] backtest expectation failed for %s: %s", key, exc)
            frozen = registry.freeze(key, fingerprint, frozen_day, expectation, reset=reset)
        expectation_returns = None
        if frozen and frame is not None and not frame.empty:
            try:
                expectation_returns = backtest_expectation(
                    frame, weight_fn, cost_bps=book.cost_bps, until=date.fromisoformat(frozen["frozen_date"]),
                ).get("_daily_returns")
            except Exception as exc:  # noqa: BLE001
                logger.warning("[forward] expectation returns failed for %s: %s", key, exc)
        rf = frame["BIL"] if frame is not None and "BIL" in getattr(frame, "columns", []) else None
        result = evaluate_forward_record(
            book.state or {"strategy_key": key, "label": book.label}, frozen, fingerprint,
            rf_closes=rf, expectation_returns=expectation_returns, orders=registry.data["orders"], gate=gate,
        )
        result.setdefault("label", book.label)
        result["expectation"] = expectation_summary((frozen or {}).get("expectation") or {}, gate.min_trading_days)
        results.append(result)
    return results


def expectation_summary(expectation: Dict[str, Any], horizon_days: int) -> Dict[str, Any]:
    """Frozen backtest headline numbers plus the return band for the gate horizon (for UI / MCP)."""
    if not expectation:
        return {}
    bands = expectation.get("window_return_pct") or {}
    return {
        "backtest_start": expectation.get("start"),
        "backtest_until": expectation.get("until"),
        "cagr_pct": expectation.get("cagr_pct"),
        "excess_sharpe": expectation.get("excess_sharpe"),
        "max_drawdown_pct": expectation.get("max_drawdown_pct"),
        "horizon_days": horizon_days,
        "band_pct": bands.get(str(horizon_days)) or {},
    }


# ------------------------------------------------------------------ Alpaca paper
def plan_alpaca_orders(
    target_weights_pct: Dict[str, float],
    account_equity: float,
    positions: Sequence[Dict[str, Any]],
    last_prices: Dict[str, float],
    *,
    capital: Optional[float] = None,
    min_order_usd: float = 25.0,
) -> List[Dict[str, Any]]:
    """Whole-share orders that move the paper account to the book's target weights (sells first)."""
    budget = min(float(capital), float(account_equity)) if capital else float(account_equity)
    held = {p["symbol"]: float(p.get("qty") or 0.0) for p in positions}
    symbols = sorted(set(held) | set(target_weights_pct))
    orders: List[Dict[str, Any]] = []
    for sym in symbols:
        price = float(last_prices.get(sym) or 0.0)
        if price <= 0:
            continue
        target_qty = math.floor(budget * float(target_weights_pct.get(sym, 0.0)) / 100.0 / price)
        delta = target_qty - held.get(sym, 0.0)
        if abs(delta) * price < min_order_usd or abs(delta) < 1:
            continue
        orders.append({"symbol": sym, "side": "buy" if delta > 0 else "sell", "qty": int(abs(delta)),
                       "reference_price": round(price, 4), "notional": round(abs(delta) * price, 2)})
    return sorted(orders, key=lambda o: (o["side"] != "sell", o["symbol"]))


def submit_paper_orders(client: Any, orders: Sequence[Dict[str, Any]], *, strategy_key: str,
                        registry: ForwardRegistry, today: Optional[date] = None) -> List[Dict[str, Any]]:
    """Send planned orders to the Alpaca **paper** account and remember the quoted price for slippage.

    Refuses anything but a paper client. Never called by the scheduler.
    """
    if not getattr(client, "paper", False):
        raise RuntimeError("Forward validation orders go only to the Alpaca paper account (ALPACA_PAPER=true).")
    day = (today or date.today()).isoformat()
    submitted: List[Dict[str, Any]] = []
    for order in orders:
        client_order_id = f"{FORWARD_ORDER_PREFIX}-{strategy_key}-{day}-{order['symbol']}-{order['side']}"[:48]
        if any(o.get("client_order_id") == client_order_id for o in registry.data["orders"]):
            continue  # already sent today
        raw = client.submit_order(symbol=order["symbol"], qty=order["qty"], side=order["side"],
                                  client_order_id=client_order_id)
        record = {**order, "strategy_key": strategy_key, "client_order_id": client_order_id,
                  "order_id": raw.get("id"), "submitted_date": day, "status": "submitted"}
        registry.data["orders"].append(record)
        submitted.append(record)
    registry.save()
    return submitted


def reconcile_paper_fills(client: Any, registry: ForwardRegistry) -> List[Dict[str, Any]]:
    """Read closed Alpaca paper orders and record fill prices and slippage vs the quoted price."""
    pending = {o["client_order_id"]: o for o in registry.data["orders"] if o.get("status") == "submitted"}
    if not pending:
        return []
    updated: List[Dict[str, Any]] = []
    for row in client.list_orders(status="closed", limit=500):
        record = pending.get(row.get("client_order_id"))
        if not record:
            continue
        fill_price = row.get("filled_avg_price")
        filled_qty = float(row.get("filled_qty") or 0.0)
        if row.get("status") != "filled" or not fill_price or filled_qty <= 0:
            record["status"] = str(row.get("status") or "closed")
            updated.append(record)
            continue
        ref = float(record["reference_price"])
        sign = 1.0 if record["side"] == "buy" else -1.0
        record.update({
            "status": "filled",
            "filled_avg_price": float(fill_price),
            "filled_qty": filled_qty,
            "filled_notional": round(float(fill_price) * filled_qty, 2),
            "slippage_bps": round(sign * (float(fill_price) / ref - 1.0) * 10_000.0, 2),
        })
        updated.append(record)
    if updated:
        registry.save()
    return updated


__all__ = [
    "FORWARD_ORDER_PREFIX",
    "ForwardGate",
    "ForwardRegistry",
    "backtest_expectation",
    "evaluate_forward_record",
    "format_forward_report",
    "forward_percentile",
    "plan_alpaca_orders",
    "reconcile_paper_fills",
    "run_forward_validation",
    "slippage_summary",
    "strategy_fingerprint",
    "submit_paper_orders",
]
