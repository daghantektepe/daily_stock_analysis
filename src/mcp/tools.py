# -*- coding: utf-8 -*-
"""DSA quantitative trading & research tools exposed over MCP.

Each handler lazy-imports DSA services so the MCP server boots in <150 ms and
gracefully reports partial degradation when an external market feed or optional
module (e.g. ``src.quant`` from v0.3) is unavailable.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_MCP_RESULT_BYTES = 120_000
_PAPER_DISCLAIMER = (
    "Paper trading ledger is strictly simulated (virtual money). "
    "No live broker order is ever submitted by these tools."
)


@dataclass(frozen=True)
class McpToolSpec:
    """One MCP-callable tool specification."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    read_only: bool = True

    def to_mcp_descriptor(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "readOnlyHint": self.read_only,
                "destructiveHint": False,
                "idempotentHint": self.read_only,
            },
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_jsonable(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return str(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(asdict(value), depth=depth + 1)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v, depth=depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item, depth=depth + 1) for item in value]
    # Handle numpy/pandas scalars cleanly without requiring numpy at import time.
    item_fn = getattr(value, "item", None)
    if callable(item_fn):
        try:
            return _to_jsonable(item_fn(), depth=depth + 1)
        except Exception:  # noqa: BLE001
            pass
    to_dict_fn = getattr(value, "to_dict", None)
    if callable(to_dict_fn):
        try:
            return _to_jsonable(to_dict_fn(), depth=depth + 1)
        except Exception:  # noqa: BLE001
            pass
    return str(value)


def safe_json_dumps(payload: Any, *, max_bytes: int = MAX_MCP_RESULT_BYTES) -> str:
    """Serialize payload to bounded UTF-8 JSON."""
    serialized = json.dumps(_to_jsonable(payload), ensure_ascii=False, indent=2)
    encoded = serialized.encode("utf-8")
    if len(encoded) <= max_bytes:
        return serialized
    truncated_text = encoded[: max(256, max_bytes - 256)].decode("utf-8", errors="ignore")
    envelope = {
        "ok": True,
        "truncated": True,
        "original_bytes": len(encoded),
        "preview": truncated_text,
    }
    return json.dumps(envelope, ensure_ascii=False)


def _ok(tool: str, data: Any, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ok": True,
        "tool": tool,
        "generated_at": _utc_now_iso(),
        "data": data,
    }
    out.update(extra)
    return out


def _err(tool: str, message: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ok": False,
        "tool": tool,
        "generated_at": _utc_now_iso(),
        "error": message,
    }
    out.update(extra)
    return out


def _bool_arg(args: Dict[str, Any], key: str, default: bool) -> bool:
    raw = args.get(key, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


def _int_arg(args: Dict[str, Any], key: str, default: int, *, minimum: int = 1, maximum: int = 500) -> int:
    try:
        value = int(args.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _float_arg(
    args: Dict[str, Any],
    key: str,
    default: float,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    try:
        value = float(args.get(key, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _has_quant_tournament_module() -> bool:
    try:
        return (
            importlib.util.find_spec("src.quant") is not None
            and importlib.util.find_spec("src.quant.tournament") is not None
        )
    except ModuleNotFoundError:
        return False


def _get_db_manager():
    from src.storage import DatabaseManager

    return DatabaseManager.get_instance()


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def _handle_system_overview(args: Dict[str, Any]) -> Dict[str, Any]:
    from src.config import get_config

    cfg = get_config()
    paper_summary: Dict[str, Any] = {}
    paper_error: Optional[str] = None
    try:
        from src.services.paper_trading_service import PaperTradingService

        paper_summary = PaperTradingService(_get_db_manager()).get_summary(include_benchmarks=False)
    except Exception as exc:  # noqa: BLE001
        paper_error = str(exc)

    alerts_count = 0
    try:
        from src.services.kap_watch_service import get_recent_kap_and_news_alerts

        alerts_count = len(get_recent_kap_and_news_alerts(live_fallback=False, max_items=30))
    except Exception:  # noqa: BLE001
        alerts_count = 0

    crypto_book_path = Path("data") / "strategy_paper" / "crypto_trend.json"
    crypto_book_snapshot: Optional[Dict[str, Any]] = None
    if crypto_book_path.is_file():
        try:
            raw_book = json.loads(crypto_book_path.read_text(encoding="utf-8"))
            history = raw_book.get("history") or []
            latest = history[-1] if history else {}
            crypto_book_snapshot = {
                "assets": raw_book.get("assets"),
                "start_date": raw_book.get("start_date"),
                "last_date": raw_book.get("last_date"),
                "initial_capital": raw_book.get("initial_capital"),
                "latest_nav": latest.get("nav"),
                "latest_benchmark_nav": latest.get("benchmark_nav"),
                "latest_weights": latest.get("weights"),
            }
        except Exception:  # noqa: BLE001
            crypto_book_snapshot = None

    return _ok(
        "dsa_get_system_overview",
        {
            "paper_trading_enabled": bool(paper_summary.get("enabled", False)),
            "open_position_count": int(paper_summary.get("open_position_count", 0) or 0),
            "trade_count": int(paper_summary.get("trade_count", 0) or 0),
            "win_rate_pct": paper_summary.get("win_rate_pct"),
            "totals_by_currency": paper_summary.get("totals_by_currency") or {},
            "paper_error": paper_error,
            "recent_kap_alerts_count": alerts_count,
            "us_screener_enabled": bool(getattr(cfg, "us_screener_enabled", False)),
            "bist_screener_enabled": bool(getattr(cfg, "bist_screener_enabled", False)),
            "crypto_trend_paper_book": crypto_book_snapshot,
            "quant_tournament_module_available": _has_quant_tournament_module(),
        },
        safety_note=_PAPER_DISCLAIMER,
    )


def _handle_market_regime(args: Dict[str, Any]) -> Dict[str, Any]:
    allow_remote = _bool_arg(args, "allow_remote", True)
    from src.services.quant_risk_gate import compute_portfolio_drawdown_pct, evaluate_market_regime

    db = None
    try:
        db = _get_db_manager()
    except Exception:  # noqa: BLE001
        db = None

    regime = evaluate_market_regime(db, allow_remote=allow_remote)
    drawdown_pct = None
    if db is not None:
        try:
            drawdown_pct = compute_portfolio_drawdown_pct(db)
        except Exception:  # noqa: BLE001
            drawdown_pct = None

    return _ok(
        "dsa_get_market_regime",
        {
            "regime": regime.to_dict(),
            "portfolio_drawdown_pct": drawdown_pct,
        },
    )


def _handle_crypto_trend_signal(args: Dict[str, Any]) -> Dict[str, Any]:
    from src.config import get_config
    from src.services.crypto_trend_strategy import (
        TrendConfig,
        current_targets,
        load_daily_closes,
        robustness_grid,
        run_backtest,
    )
    from src.services.strategy_paper_book import StrategyPaperBook, format_book_report

    cfg = get_config()
    raw_assets = args.get("assets")
    if isinstance(raw_assets, list) and raw_assets:
        assets = tuple(str(a).strip().upper() for a in raw_assets if str(a).strip())
    else:
        assets = tuple(getattr(cfg, "crypto_trend_assets", None) or ("BTC-USD", "ETH-USD"))

    step_paper = _bool_arg(args, "step_paper", False)
    include_backtest = _bool_arg(args, "include_backtest", True)

    trend = TrendConfig(assets=assets)
    prices = load_daily_closes(trend.assets)
    targets = current_targets(prices, trend)

    payload: Dict[str, Any] = {
        "assets": list(trend.assets),
        "sma_windows": list(trend.windows),
        "cost_pct_per_side": trend.cost_pct,
        "signals": targets,
    }

    if include_backtest:
        payload["backtest_all"] = robustness_grid(
            prices, trend.windows, assets=trend.assets, cost_pct=trend.cost_pct, start=None, end=None
        )
        payload["backtest_oos_2022_present"] = robustness_grid(
            prices,
            trend.windows,
            assets=trend.assets,
            cost_pct=trend.cost_pct,
            start=date(2022, 1, 1),
            end=None,
        )
        bt_res = run_backtest(prices, trend)
        payload["yearly"] = bt_res.get("yearly") or []

    book = StrategyPaperBook(
        config=trend,
        initial_capital=float(getattr(cfg, "crypto_trend_capital", 10_000.0)),
    )
    if step_paper:
        payload["paper_step"] = book.step(prices)
    payload["paper_summary"] = book.summary()
    payload["paper_report"] = format_book_report(payload["paper_summary"], targets)

    return _ok("dsa_get_crypto_trend_signal", payload, safety_note=_PAPER_DISCLAIMER)


def _handle_us_alpha_screen(args: Dict[str, Any]) -> Dict[str, Any]:
    from src.services.us_quant_screener import screen_us_alpha_candidates

    symbols = args.get("symbols")
    clean_symbols = (
        [str(s).strip().upper() for s in symbols if str(s).strip()]
        if isinstance(symbols, list) and symbols
        else None
    )
    top_n = _int_arg(args, "top_n", 10, minimum=1, maximum=30)
    include_pead = _bool_arg(args, "include_pead", False)
    include_form4 = _bool_arg(args, "include_form4", False)
    use_sec_xbrl = _bool_arg(args, "use_sec_xbrl", False)
    fast_mode = _bool_arg(args, "fast_mode", True)

    candidates = screen_us_alpha_candidates(
        symbols=clean_symbols,
        top_n=top_n,
        include_pead=include_pead,
        include_form4=include_form4,
        quality_fetcher=(lambda _sym: (None, None)) if (fast_mode and not use_sec_xbrl) else None,
        use_sec_xbrl=use_sec_xbrl,
    )
    items = [asdict(c) for c in candidates]
    return _ok(
        "dsa_screen_us_alpha",
        {
            "count": len(items),
            "include_pead": include_pead,
            "include_form4": include_form4,
            "items": items,
        },
    )


def _handle_bist_screen(args: Dict[str, Any]) -> Dict[str, Any]:
    from src.services.bist_screener import screen_bist_stocks

    top_n = _int_arg(args, "top_n", 8, minimum=1, maximum=30)
    min_score = _float_arg(args, "min_score", 25.0, minimum=0.0, maximum=100.0)
    include_kap = _bool_arg(args, "include_kap", True)
    max_symbols = _int_arg(args, "max_symbols", 120, minimum=20, maximum=800)

    res = screen_bist_stocks(
        top_n=top_n,
        min_score=min_score,
        include_kap=include_kap,
        max_symbols=max_symbols,
    )
    return _ok(
        "dsa_screen_bist_stocks",
        {
            "selected_codes": list(res.get("selected_codes") or []),
            "scanned_count": int(
                res.get("scanned_count")
                or res.get("evaluated_count")
                or res.get("universe_count")
                or 0
            ),
            "passed_count": int(
                res.get("passed_count")
                or res.get("qualified_count")
                or len(res.get("candidates") or [])
            ),
            "candidates": list(res.get("candidates") or []),
            "errors": list(res.get("errors") or [])[:10],
        },
    )


def _handle_sec_form4_live(args: Dict[str, Any]) -> Dict[str, Any]:
    from data_provider.sec_form4_fetcher import SecForm4Fetcher
    from src.services.sec_form4_screener import score_insider_event

    count = _int_arg(args, "count", 80, minimum=10, maximum=200)
    max_filings = _int_arg(args, "max_filings", 40, minimum=5, maximum=100)
    min_value = _float_arg(args, "min_value", 10_000.0, minimum=0.0)
    top_n = _int_arg(args, "top_n", 15, minimum=1, maximum=50)

    fetcher = SecForm4Fetcher()
    clusters = fetcher.fetch_live_purchases(
        count=count,
        max_filings=max_filings,
        min_value=min_value,
    )
    items: List[Dict[str, Any]] = []
    for cl in clusters:
        ev_score, reasons = score_insider_event(cl)
        items.append(
            {
                "symbol": cl.symbol,
                "company_name": cl.company_name,
                "filing_date": cl.filing_date.isoformat() if cl.filing_date else None,
                "insider_count": cl.insider_count,
                "officer_director_count": cl.officer_director_count,
                "total_value": round(float(cl.total_value), 2),
                "total_shares": round(float(cl.total_shares), 2),
                "avg_price": round(float(cl.avg_price), 4),
                "has_c_level": bool(cl.has_c_level),
                "is_opportunistic": bool(cl.is_opportunistic),
                "is_cluster": bool(cl.is_cluster),
                "cmp_class": cl.cmp_class,
                "has_10b51": bool(cl.has_10b51),
                "primary_titles": list(cl.primary_titles or []),
                "trend_regime": cl.trend_regime,
                "score": float(ev_score),
                "reasons": list(reasons),
                "sec_url": cl.sec_url,
            }
        )
    items.sort(key=lambda row: row["score"], reverse=True)
    return _ok(
        "dsa_scan_sec_form4_live",
        {
            "count": len(items[:top_n]),
            "total_clusters_found": len(items),
            "items": items[:top_n],
        },
    )


def _handle_pead_candidates(args: Dict[str, Any]) -> Dict[str, Any]:
    from scripts.pead_screener import DEFAULT_US_MIDCAP_WATCHLIST, DEFAULT_US_WATCHLIST
    from src.services.pead_screener import screen_pead_candidates

    universe = str(args.get("universe") or "all").strip().lower()
    if universe not in {"all", "midcap", "megacap"}:
        universe = "all"
    max_days = _int_arg(args, "max_days", 21, minimum=1, maximum=90)
    min_score = _float_arg(args, "min_score", 40.0, minimum=0.0, maximum=100.0)
    top_n = _int_arg(args, "top_n", 15, minimum=1, maximum=50)

    if universe == "midcap":
        syms = DEFAULT_US_MIDCAP_WATCHLIST
    elif universe == "megacap":
        syms = DEFAULT_US_WATCHLIST
    else:
        syms = list(dict.fromkeys([*DEFAULT_US_MIDCAP_WATCHLIST, *DEFAULT_US_WATCHLIST]))

    candidates = screen_pead_candidates(
        symbols=syms,
        max_days=max_days,
        min_score=min_score,
        top_n=top_n,
        deadline_seconds=14.0,
    )
    items = [c.to_dict() for c in candidates]
    return _ok(
        "dsa_scan_pead_candidates",
        {
            "universe": universe,
            "count": len(items),
            "items": items,
        },
    )


def _handle_kap_contracts(args: Dict[str, Any]) -> Dict[str, Any]:
    from src.services.kap_contract_screener import KapContractScreener
    from src.services.kap_watch_service import get_recent_kap_and_news_alerts

    days_back = _int_arg(args, "days_back", 7, minimum=1, maximum=90)
    min_score = _int_arg(args, "min_score", 30, minimum=0, maximum=100)
    top_n = _int_arg(args, "top_n", 15, minimum=1, maximum=50)
    include_alerts = _bool_arg(args, "include_alerts", True)

    contracts = KapContractScreener().scan_recent_contracts(
        days=days_back,
        min_score=min_score,
        top_n=top_n,
    )
    items = [asdict(row) if is_dataclass(row) else dict(row) for row in contracts]
    alerts = (
        get_recent_kap_and_news_alerts(live_fallback=True, max_items=15)
        if include_alerts
        else []
    )
    return _ok(
        "dsa_scan_kap_contracts",
        {
            "days_back": days_back,
            "contract_count": len(items),
            "contracts": items,
            "recent_alerts": alerts,
        },
    )


def _handle_paper_portfolio(args: Dict[str, Any]) -> Dict[str, Any]:
    from src.services.paper_trading_service import PaperTradingService

    include_benchmarks = _bool_arg(args, "include_benchmarks", True)
    include_trades = _bool_arg(args, "include_trades", True)
    trades_limit = _int_arg(args, "trades_limit", 25, minimum=1, maximum=200)
    include_equity_curve = _bool_arg(args, "include_equity_curve", False)
    equity_days = _int_arg(args, "equity_days", 90, minimum=7, maximum=365)

    svc = PaperTradingService(_get_db_manager())
    payload: Dict[str, Any] = {
        "summary": svc.get_summary(include_benchmarks=include_benchmarks),
    }
    if include_trades:
        payload["recent_trades"] = svc.list_trades(limit=trades_limit)
    if include_equity_curve:
        payload["equity_curve"] = svc.get_equity_curve(days=equity_days)

    return _ok("dsa_get_paper_portfolio", payload, safety_note=_PAPER_DISCLAIMER)


def _handle_place_paper_order(args: Dict[str, Any]) -> Dict[str, Any]:
    from src.services.paper_trading_service import PaperTradingService

    stock_code = str(args.get("stock_code") or "").strip().upper()
    action = str(args.get("action") or "").strip().lower()
    if not stock_code:
        return _err("dsa_place_paper_order", "stock_code is required")
    if action not in {"buy", "reduce", "sell"}:
        return _err("dsa_place_paper_order", "action must be one of: buy, reduce, sell")

    quantity = _float_arg(args, "quantity", 0.0, minimum=0.0)
    if quantity <= 0:
        return _err("dsa_place_paper_order", "quantity must be > 0")

    price = args.get("price")
    stop_loss = args.get("stop_loss")
    take_profit = args.get("take_profit")

    trade = PaperTradingService(_get_db_manager()).place_manual_order(
        stock_code=stock_code,
        action=action,
        quantity=quantity,
        price=float(price) if price is not None else None,
        stop_loss=float(stop_loss) if stop_loss is not None else None,
        take_profit=float(take_profit) if take_profit is not None else None,
        stock_name=str(args.get("stock_name")).strip() if args.get("stock_name") else None,
        market=str(args.get("market")).strip() if args.get("market") else None,
    )
    return _ok(
        "dsa_place_paper_order",
        {"simulated_only": True, "trade": trade},
        safety_note=_PAPER_DISCLAIMER,
    )


def _handle_analyze_stock(args: Dict[str, Any]) -> Dict[str, Any]:
    stock_code = str(args.get("stock_code") or "").strip().upper()
    if not stock_code:
        return _err("dsa_analyze_stock", "stock_code is required (e.g. NVDA, SPY, THYAO.IS, 600519)")

    days = _int_arg(args, "days", 90, minimum=20, maximum=365)
    from src.agent.factory import get_tool_registry

    registry = get_tool_registry()
    sections: Dict[str, Any] = {"stock_code": stock_code}
    errors: Dict[str, str] = {}

    tool_calls = [
        ("realtime_quote", "get_realtime_quote", {"stock_code": stock_code}),
        ("trend_analysis", "analyze_trend", {"stock_code": stock_code, "days": days}),
        ("moving_averages", "calculate_ma", {"stock_code": stock_code, "days": days}),
        ("stock_info", "get_stock_info", {"stock_code": stock_code}),
    ]
    for section_key, tool_name, call_args in tool_calls:
        tool_def = registry.get(tool_name)
        if tool_def is None:
            continue
        try:
            sections[section_key] = registry.execute(tool_name, **call_args)
        except Exception as exc:  # noqa: BLE001
            errors[section_key] = str(exc)

    try:
        from src.services.quant_risk_gate import evaluate_entry_risk_gate

        gate = evaluate_entry_risk_gate(
            stock_code=stock_code,
            db_manager=_get_db_manager(),
            allow_remote_regime=True,
        )
        sections["entry_risk_gate"] = gate.to_dict()
    except Exception as exc:  # noqa: BLE001
        errors["entry_risk_gate"] = str(exc)

    if errors:
        sections["partial_errors"] = errors
    return _ok("dsa_analyze_stock", sections)


def _handle_decision_signals(args: Dict[str, Any]) -> Dict[str, Any]:
    from src.services.decision_signal_service import DecisionSignalService

    stock_code = str(args.get("stock_code") or "").strip().upper() or None
    status = str(args.get("status") or "").strip().lower() or None
    market = str(args.get("market") or "").strip().lower() or None
    page_size = _int_arg(args, "limit", 15, minimum=1, maximum=50)

    svc = DecisionSignalService()
    result = svc.list_signals(
        market=market,
        stock_code=stock_code,
        status=status,
        page=1,
        page_size=page_size,
    )
    return _ok("dsa_get_decision_signals", result)


def _compact_tournament_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Strip heavy equity curve arrays so MCP JSON stays crisp and token-efficient."""
    compact_rows = []
    for row in raw.get("strategies") or []:
        oos = row.get("oos") or {}
        compact_rows.append(
            {
                "strategy_id": row.get("strategy_id"),
                "name": row.get("name"),
                "universe": row.get("universe"),
                "verdict": row.get("verdict"),
                "oos_cagr_pct": oos.get("cagr_pct"),
                "oos_sharpe": oos.get("sharpe"),
                "oos_max_drawdown_pct": oos.get("max_drawdown_pct"),
                "oos_recovery": oos.get("recovery_factor"),
                "oos_dsr_pct": oos.get("dsr_pct"),
                "current_weights": row.get("current_weights") or {},
                "cash_weight_pct": row.get("cash_weight_pct"),
                "signal_summary": row.get("signal_summary"),
            }
        )
    return {
        "generated_at": raw.get("generated_at"),
        "oos_start": raw.get("oos_start"),
        "latest_date": raw.get("latest_date"),
        "total_strategies": raw.get("total_strategies"),
        "total_assets": raw.get("total_assets"),
        "total_asset_days": raw.get("total_asset_days"),
        "pass_elite_count": raw.get("pass_elite_count"),
        "champion": raw.get("champion"),
        "paa": raw.get("paa"),
        "meta_portfolio_a": raw.get("meta_portfolio_a"),
        "meta_portfolio_b": raw.get("meta_portfolio_b"),
        "leaderboard": compact_rows,
    }


def _handle_paa_allocation(args: Dict[str, Any]) -> Dict[str, Any]:
    from src.quant.tournament import get_live_paa_signal

    force_refresh = _bool_arg(args, "force_refresh", False)
    result = get_live_paa_signal(force_refresh=force_refresh)
    if result.get("ok") is False:
        return _err("dsa_get_paa_allocation", str(result.get("error") or "PAA calculation failed"))
    return _ok("dsa_get_paa_allocation", result, safety_note=_PAPER_DISCLAIMER)


def _handle_quant_paper_books(args: Dict[str, Any]) -> Dict[str, Any]:
    from src.config import get_config
    from src.quant.paper_book import get_quant_paper_books_status, step_quant_paper_books

    cfg = get_config()
    step = _bool_arg(args, "step_paper", False)
    force_rebalance = _bool_arg(args, "force_rebalance", False)
    force_refresh = _bool_arg(args, "force_refresh_prices", False)
    raw_strats = args.get("strategies")
    strategies = (
        [str(s).strip().lower() for s in raw_strats if str(s).strip()]
        if isinstance(raw_strats, list) and raw_strats
        else list(getattr(cfg, "quant_paper_strategies", ["paa", "meta_a"]))
    )
    kwargs = {
        "strategies": strategies,
        "initial_capital": float(getattr(cfg, "quant_paper_capital", 10000.0)),
        "cost_bps": float(getattr(cfg, "quant_paper_cost_bps", 5.0)),
        "rebalance_mode": str(getattr(cfg, "quant_paper_rebalance_mode", "monthly")),
    }
    if step or force_rebalance:
        result = step_quant_paper_books(
            **kwargs,
            force_rebalance=force_rebalance,
            force_refresh_prices=force_refresh,
        )
    else:
        result = get_quant_paper_books_status(**kwargs, auto_step_if_empty=True)

    # Compact heavy history arrays for crisp MCP context
    compact_books = []
    for book in result.get("books") or []:
        compact_books.append({k: v for k, v in book.items() if k != "history"})
    return _ok(
        "dsa_get_quant_paper_books",
        {
            "ok": result.get("ok", True),
            "simulated_only": True,
            "strategies": result.get("strategies") or strategies,
            "total_new_trades": result.get("total_new_trades", 0),
            "books": compact_books,
            "report_text": result.get("report_text", ""),
        },
        safety_note=_PAPER_DISCLAIMER,
    )


def _handle_forward_validation(args: Dict[str, Any]) -> Dict[str, Any]:
    """Forward (live paper) validation gate for the frozen PAA / Meta-Portfolio A strategies (read-only)."""
    try:
        from src.config import get_config
        from src.quant.forward_validation import format_forward_report, run_forward_validation

        cfg = get_config()
        strategies = args.get("strategies") or list(getattr(cfg, "quant_paper_strategies", ["paa", "meta_a"]))
        results = run_forward_validation(
            strategies=strategies,
            auto_freeze=False,
            paper_settings={
                "initial_capital": float(getattr(cfg, "quant_paper_capital", 10000.0)),
                "cost_bps": float(getattr(cfg, "quant_paper_cost_bps", 5.0)),
                "rebalance_mode": str(getattr(cfg, "quant_paper_rebalance_mode", "monthly")),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return _err("dsa_get_forward_validation", f"İleri doğrulama okunamadı: {exc}")
    compact = [
        {k: r.get(k) for k in ("strategy_key", "label", "status", "frozen_date", "forward_days", "forward_return_pct",
                               "benchmark_return_pct", "excess_sharpe", "excess_sharpe_se", "max_drawdown_pct",
                               "backtest_percentile", "slippage", "reasons", "warnings") if k in r}
        for r in results
    ]
    return _ok("dsa_get_forward_validation", {"strategies": compact, "report_text": format_forward_report(results)},
               safety_note=_PAPER_DISCLAIMER)


def _handle_strategy_tournament(args: Dict[str, Any]) -> Dict[str, Any]:
    """Return empirical multi-universe 25-strategy tournament results (PAA, Meta-Portfolio A/B, OOS DSR)."""
    force_refresh = _bool_arg(args, "force_refresh", False)
    if _has_quant_tournament_module():
        try:
            from src.quant.tournament import load_latest_tournament_results, run_tournament

            data = (
                run_tournament(force_refresh=True)
                if force_refresh
                else load_latest_tournament_results(auto_run_if_missing=True)
            )
            if isinstance(data, dict) and data.get("strategies"):
                return _ok(
                    "dsa_get_strategy_tournament",
                    {
                        "module_present": True,
                        **_compact_tournament_summary(data),
                    },
                    safety_note=_PAPER_DISCLAIMER,
                )
        except Exception as exc:  # noqa: BLE001
            return _err("dsa_get_strategy_tournament", f"src.quant.tournament failed: {exc}")

    return _ok(
        "dsa_get_strategy_tournament",
        {
            "module_present": False,
            "message": "src/quant/tournament.py is not available.",
        },
    )


def _compact_quant_book(book: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "strategy_key": book.get("strategy_key"),
        "label": book.get("label"),
        "days": book.get("days"),
        "last_date": book.get("last_date"),
        "nav": book.get("nav"),
        "return_pct": book.get("return_pct"),
        "benchmark_return_pct": book.get("benchmark_return_pct"),
        "max_drawdown_pct": book.get("max_drawdown_pct"),
        "weights_pct": book.get("weights_pct"),
        "trade_count": book.get("trade_count"),
    }


def _compact_tournament_entry(entry: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    oos = entry.get("oos") or {}
    return {
        "strategy_id": entry.get("strategy_id"),
        "name": entry.get("name"),
        "verdict": entry.get("verdict"),
        "signal_summary": entry.get("signal_summary"),
        "current_weights": entry.get("current_weights"),
        "oos_cagr_pct": oos.get("cagr_pct"),
        "oos_excess_cagr_pct": oos.get("excess_cagr_pct"),
        "oos_sharpe": oos.get("sharpe"),
        "oos_excess_sharpe": oos.get("excess_sharpe"),
        "oos_max_drawdown_pct": oos.get("max_drawdown_pct"),
        "oos_dsr_pct": oos.get("dsr_pct"),
    }


def _handle_strategic_trading_brief(args: Dict[str, Any]) -> Dict[str, Any]:
    """One-call multi-pillar strategic trading brief (parallelized with per-pillar timeouts & compact mode)."""
    include_crypto = _bool_arg(args, "include_crypto_trend", True)
    include_us_screen = _bool_arg(args, "include_us_screen", False)
    include_bist_screen = _bool_arg(args, "include_bist_screen", False)
    include_form4 = _bool_arg(args, "include_form4", False)
    include_pead = _bool_arg(args, "include_pead", False)
    compact = _bool_arg(args, "compact", True)
    top_n = _int_arg(args, "top_n", 5, minimum=1, maximum=15)
    pillar_timeout = _float_arg(args, "pillar_timeout_s", 20.0, minimum=5.0, maximum=90.0)

    brief: Dict[str, Any] = {}
    errors: Dict[str, str] = {}

    def _kap_alerts_task():
        from src.services.kap_watch_service import get_recent_kap_and_news_alerts

        return get_recent_kap_and_news_alerts(live_fallback=False, max_items=10)

    # Run lightweight SPY/VIX regime first so yfinance initializes its session/cache
    # cleanly without multi-thread lock contention against batch downloads.
    try:
        brief["market_regime"] = _handle_market_regime({"allow_remote": True}).get("data")
    except Exception as exc:  # noqa: BLE001
        errors["market_regime"] = str(exc)

    tasks: Dict[str, Callable[[], Any]] = {
        "paper_portfolio": lambda: _handle_paper_portfolio(
            {"include_benchmarks": False, "include_trades": True, "trades_limit": 10}
        ).get("data"),
        "recent_kap_alerts": _kap_alerts_task,
        "recent_decision_signals": lambda: _handle_decision_signals({"limit": 8}).get("data"),
    }

    if include_crypto:
        tasks["crypto_trend_strategy"] = lambda: _handle_crypto_trend_signal(
            {"step_paper": False, "include_backtest": False}
        ).get("data")

    if include_us_screen:
        # Keep fast_mode=True & include_pead=False for single-batch ~5s execution.
        tasks["us_alpha_top_candidates"] = lambda: _handle_us_alpha_screen(
            {
                "top_n": top_n,
                "include_pead": False,
                "include_form4": False,
                "use_sec_xbrl": False,
                "fast_mode": True,
            }
        ).get("data")

    if include_form4:
        tasks["sec_form4_live_clusters"] = lambda: _handle_sec_form4_live(
            {"top_n": top_n, "count": 60, "max_filings": 25}
        ).get("data")

    if include_pead:
        tasks["pead_candidates"] = lambda: _handle_pead_candidates(
            {"universe": "megacap", "top_n": top_n}
        ).get("data")

    if include_bist_screen:
        tasks["bist_top_candidates"] = lambda: _handle_bist_screen(
            {"top_n": top_n, "include_kap": True}
        ).get("data")

    if _has_quant_tournament_module():
        def _tournament_brief_task():
            from src.quant.tournament import get_live_paa_signal, load_latest_tournament_results

            cached = load_latest_tournament_results(auto_run_if_missing=False)
            paa_live = get_live_paa_signal(force_refresh=False)
            if compact and isinstance(paa_live, dict):
                paa_live = {
                    "as_of_date": paa_live.get("as_of_date"),
                    "regime_label": paa_live.get("regime_label"),
                    "crash_protection_pct": paa_live.get("crash_protection_pct"),
                    "risk_assets_below_sma252": paa_live.get("risk_assets_below_sma252"),
                    "risk_assets_total": paa_live.get("risk_assets_total"),
                    "target_weights_pct": paa_live.get("target_weights_pct"),
                }
            out: Dict[str, Any] = {"paa_live": paa_live}
            if cached:
                out["champion"] = _compact_tournament_entry(cached.get("champion")) if compact else cached.get("champion")
                out["paa"] = _compact_tournament_entry(cached.get("paa")) if compact else cached.get("paa")
                out["meta_portfolio_a"] = _compact_tournament_entry(cached.get("meta_portfolio_a")) if compact else cached.get("meta_portfolio_a")
                out["meta_portfolio_b"] = _compact_tournament_entry(cached.get("meta_portfolio_b")) if compact else cached.get("meta_portfolio_b")
                out["total_strategies"] = cached.get("total_strategies")
                out["pass_elite_count"] = cached.get("pass_elite_count")
            try:
                qbooks = _handle_quant_paper_books({"step_paper": False}).get("data") or {}
                if compact and isinstance(qbooks, dict):
                    out["quant_paper_books"] = [_compact_quant_book(b) for b in (qbooks.get("books") or [])]
                else:
                    out["quant_paper_books"] = qbooks
            except Exception:
                pass
            return out

        tasks["strategy_tournament_and_paa"] = _tournament_brief_task

    pool = ThreadPoolExecutor(max_workers=min(6, max(1, len(tasks))))
    futures = {name: pool.submit(fn) for name, fn in tasks.items()}
    try:
        for name, fut in futures.items():
            try:
                val = fut.result(timeout=pillar_timeout)
                if compact and name == "crypto_trend_strategy" and isinstance(val, dict):
                    val = {
                        "assets": val.get("assets"),
                        "signals": val.get("signals"),
                        "paper_nav": (val.get("paper_summary") or {}).get("nav"),
                        "paper_return_pct": (val.get("paper_summary") or {}).get("return_pct"),
                        "paper_benchmark_return_pct": (val.get("paper_summary") or {}).get("benchmark_return_pct"),
                    }
                elif compact and name == "recent_decision_signals" and isinstance(val, dict):
                    raw_items = val.get("items") or val.get("signals") or []
                    val = {
                        "count": len(raw_items),
                        "items": [
                            {
                                "code": it.get("code"),
                                "name": it.get("name"),
                                "action": it.get("action") or it.get("operation_advice"),
                                "sentiment_score": it.get("sentiment_score"),
                                "date": it.get("date") or it.get("created_at"),
                            }
                            for it in raw_items[:5]
                        ],
                    }
                elif compact and name == "paper_portfolio" and isinstance(val, dict):
                    sm = val.get("summary") or {}
                    val = {
                        "enabled": sm.get("enabled"),
                        "open_position_count": sm.get("open_position_count"),
                        "trade_count": sm.get("trade_count"),
                        "win_rate_pct": sm.get("win_rate_pct"),
                        "totals_by_currency": sm.get("totals_by_currency"),
                    }
                brief[name] = val
            except FuturesTimeoutError:
                errors[name] = f"Timed out after {pillar_timeout:.0f}s"
            except Exception as exc:  # noqa: BLE001
                errors[name] = str(exc)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    if errors:
        brief["partial_errors"] = errors

    return _ok(
        "dsa_get_strategic_trading_brief",
        brief,
        safety_note=_PAPER_DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Catalog builder
# ---------------------------------------------------------------------------


def build_dsa_mcp_tools() -> List[McpToolSpec]:
    """Return the full catalog of DSA MCP tool specifications."""
    return [
        McpToolSpec(
            name="dsa_get_system_overview",
            description=(
                "Get the live Daily Stock Analysis (DSA) cockpit overview: paper trading ledger "
                "counts, win rate, totals by currency, recent KAP alerts count, crypto trend book "
                "snapshot, and whether the v0.3 quant tournament module is present."
            ),
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=_handle_system_overview,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_get_strategic_trading_brief",
            description=(
                "Generate a consolidated multi-pillar strategic trading brief combining live SPY/VIX "
                "market regime & position scale, simulated paper portfolio status, Crypto 5-SMA Trend "
                "Ensemble weights, recent KAP alerts, recent AI decision signals, and optional live "
                "scans (US Alpha, SEC Form 4, PEAD, BIST). Ideal first call when asked for the "
                "safest high-probability strategic trading recommendation right now."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "include_crypto_trend": {
                        "type": "boolean",
                        "description": "Include live BTC-USD / ETH-USD 5-SMA trend weights & paper book.",
                        "default": True,
                    },
                    "include_us_screen": {
                        "type": "boolean",
                        "description": "Run live US High-Alpha multi-factor screen (adds ~10-20s).",
                        "default": False,
                    },
                    "include_bist_screen": {
                        "type": "boolean",
                        "description": "Run live BIST technical + KAP catalyst screen.",
                        "default": False,
                    },
                    "include_form4": {
                        "type": "boolean",
                        "description": "Fetch live SEC EDGAR Form 4 executive insider buying clusters.",
                        "default": False,
                    },
                    "include_pead": {
                        "type": "boolean",
                        "description": "Scan US Post-Earnings Announcement Drift (PEAD 2.0) candidates.",
                        "default": False,
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Top candidates per optional live scan (1-15).",
                        "default": 5,
                    },
                },
                "additionalProperties": False,
            },
            handler=_handle_strategic_trading_brief,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_get_market_regime",
            description=(
                "Evaluate broad US market regime (risk_on / caution / risk_off / neutral) from SPY "
                "50/200-day SMAs and VIX volatility, returning recommended position_scale (0.0 to 1.0) "
                "and current paper portfolio drawdown percentage."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "allow_remote": {
                        "type": "boolean",
                        "description": "Fetch SPY and ^VIX from Yahoo Finance if local DB has <50 bars.",
                        "default": True,
                    },
                },
                "additionalProperties": False,
            },
            handler=_handle_market_regime,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_get_crypto_trend_signal",
            description=(
                "Run the empirically validated Crypto 5-SMA Trend Ensemble (50/100/150/200/250d SMAs) "
                "for BTC-USD and ETH-USD: returns current coin vs cash allocation targets, backtest "
                "metrics (full period and 2022-present OOS), and simulated crypto paper book status."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "assets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional Yahoo Finance crypto tickers (default: ['BTC-USD', 'ETH-USD']).",
                    },
                    "include_backtest": {
                        "type": "boolean",
                        "description": "Include full-period and 2022-present OOS robustness grid.",
                        "default": True,
                    },
                    "step_paper": {
                        "type": "boolean",
                        "description": "Advance the simulated crypto paper book to the latest completed daily close.",
                        "default": False,
                    },
                },
                "additionalProperties": False,
            },
            handler=_handle_crypto_trend_signal,
            read_only=False,
        ),
        McpToolSpec(
            name="dsa_screen_us_alpha",
            description=(
                "Run the US High-Alpha Quantitative Multi-Factor Screener (Residual Momentum, 52W High "
                "Proximity, Frog-in-the-Pan Discreteness, Cash Operating Profitability, Vol-Scaled "
                "Weights, plus optional PEAD and Form 4 signals)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional subset of US tickers; omit to scan the default 80-stock liquid universe.",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Number of top-ranked candidates to return (1-30).",
                        "default": 10,
                    },
                    "include_pead": {
                        "type": "boolean",
                        "description": "Include per-ticker PEAD earnings surprise bonus (slower; defaults to false for fast ~5s screening).",
                        "default": False,
                    },
                    "include_form4": {
                        "type": "boolean",
                        "description": "Include live SEC Form 4 insider buying bonus.",
                        "default": False,
                    },
                    "use_sec_xbrl": {
                        "type": "boolean",
                        "description": "Query SEC XBRL companyfacts directly (slower but authoritative).",
                        "default": False,
                    },
                    "fast_mode": {
                        "type": "boolean",
                        "description": "Skip per-ticker yfinance financial statements for fast (~5s) single-batch price/momentum/52W/FIP screening.",
                        "default": True,
                    },
                },
                "additionalProperties": False,
            },
            handler=_handle_us_alpha_screen,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_screen_bist_stocks",
            description=(
                "Scan Borsa Istanbul (BIST) equities for constructive technical breakouts, volume "
                "surges (>=1.5x 20d avg), anti-chase filters, and fresh KAP catalyst disclosures."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "Number of top BIST candidates to return (1-30).",
                        "default": 8,
                    },
                    "min_score": {
                        "type": "number",
                        "description": "Minimum composite screener score (0-100).",
                        "default": 25.0,
                    },
                    "include_kap": {
                        "type": "boolean",
                        "description": "Incorporate recent KAP disclosures into scoring.",
                        "default": True,
                    },
                },
                "additionalProperties": False,
            },
            handler=_handle_bist_screen,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_scan_sec_form4_live",
            description=(
                "Fetch live SEC EDGAR Form 4 open-market executive/director purchase clusters, "
                "filtered for CEFs/trusts and scored via Cohen-Malloy-Pomorski opportunistic vs routine "
                "classification and trend confirmation."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "default": 80, "description": "Atom feed entries to inspect (10-200)."},
                    "max_filings": {"type": "integer", "default": 40, "description": "Max XML filings to parse (5-100)."},
                    "min_value": {"type": "number", "default": 10000.0, "description": "Minimum USD open-market purchase value."},
                    "top_n": {"type": "integer", "default": 15, "description": "Top scored clusters to return (1-50)."},
                },
                "additionalProperties": False,
            },
            handler=_handle_sec_form4_live,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_scan_pead_candidates",
            description=(
                "Scan US equities for recent Post-Earnings Announcement Drift (PEAD 2.0) setups with "
                "positive EPS surprise and trend alignment."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "universe": {
                        "type": "string",
                        "enum": ["all", "midcap", "megacap"],
                        "default": "all",
                        "description": "Universe to scan.",
                    },
                    "max_days": {"type": "integer", "default": 21, "description": "Max days since earnings release (1-90)."},
                    "min_score": {"type": "number", "default": 40.0, "description": "Minimum PEAD score (0-100)."},
                    "top_n": {"type": "integer", "default": 15, "description": "Top candidates to return (1-50)."},
                },
                "additionalProperties": False,
            },
            handler=_handle_pead_candidates,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_scan_kap_contracts",
            description=(
                "Fetch and score recent BIST KAP new contract/tender disclosures and material "
                "multi-source news alerts."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "days_back": {"type": "integer", "default": 7, "description": "Lookback window in days (1-90)."},
                    "min_score": {"type": "integer", "default": 30, "description": "Minimum contract score (0-100)."},
                    "top_n": {"type": "integer", "default": 15, "description": "Max contracts to return (1-50)."},
                    "include_alerts": {"type": "boolean", "default": True, "description": "Include recent KAP/news alerts."},
                },
                "additionalProperties": False,
            },
            handler=_handle_kap_contracts,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_get_paper_portfolio",
            description=(
                "Retrieve the simulated paper trading ledger: open positions with stop-loss/take-profit, "
                "realized/unrealized P&L, win rate, benchmark comparisons (BIST100/SPY), and recent trades."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "include_benchmarks": {"type": "boolean", "default": True},
                    "include_trades": {"type": "boolean", "default": True},
                    "trades_limit": {"type": "integer", "default": 25},
                    "include_equity_curve": {"type": "boolean", "default": False},
                    "equity_days": {"type": "integer", "default": 90},
                },
                "additionalProperties": False,
            },
            handler=_handle_paper_portfolio,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_place_paper_order",
            description=(
                "Record a SIMULATED manual paper trade (buy, reduce, or sell) in the virtual paper "
                "ledger with optional ATR/explicit stop-loss and take-profit. Only call when the user "
                "explicitly asks to record a paper order; never submits real broker orders."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "Ticker symbol (e.g. NVDA, THYAO.IS, SPY)."},
                    "action": {"type": "string", "enum": ["buy", "reduce", "sell"]},
                    "quantity": {"type": "number", "description": "Share/unit quantity (> 0)."},
                    "price": {"type": "number", "description": "Optional explicit fill price; omitted uses latest quote."},
                    "stop_loss": {"type": "number", "description": "Optional stop-loss price."},
                    "take_profit": {"type": "number", "description": "Optional take-profit price."},
                    "stock_name": {"type": "string", "description": "Optional display name."},
                    "market": {"type": "string", "description": "Optional market code (us, tr, hk, cn)."},
                },
                "required": ["stock_code", "action", "quantity"],
                "additionalProperties": False,
            },
            handler=_handle_place_paper_order,
            read_only=False,
        ),
        McpToolSpec(
            name="dsa_analyze_stock",
            description=(
                "Perform comprehensive technical & risk-gate analysis on a single stock ticker "
                "(US like NVDA/AAPL/SPY, BIST like THYAO.IS, HK like HK00700, or A-share like 600519): "
                "real-time quote, trend analysis, moving averages, fundamentals, and entry risk gate."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "Exact ticker symbol."},
                    "days": {"type": "integer", "default": 90, "description": "Lookback days for technical analysis (20-365)."},
                },
                "required": ["stock_code"],
                "additionalProperties": False,
            },
            handler=_handle_analyze_stock,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_get_decision_signals",
            description=(
                "Query recent persisted AI decision signals (buy/sell/hold recommendations, entry/stop "
                "levels, confidence, and status) from the DSA database."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "stock_code": {"type": "string", "description": "Optional ticker filter."},
                    "market": {"type": "string", "description": "Optional market filter (us, tr, cn, hk)."},
                    "status": {"type": "string", "description": "Optional status filter (active, expired, etc.)."},
                    "limit": {"type": "integer", "default": 15, "description": "Max signals to return (1-50)."},
                },
                "additionalProperties": False,
            },
            handler=_handle_decision_signals,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_get_strategy_tournament",
            description=(
                "Retrieve empirical multi-universe 25-strategy tournament results (PAA Crash-Shield, "
                "VAA, DAA, Meta-Portfolio A/B, Crypto 5-SMA, BIST, OOS Sharpe/CAGR/MaxDD/DSR, and live "
                "target weights)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "force_refresh": {
                        "type": "boolean",
                        "description": "Re-download market data and recompute all 25 strategies (default uses fresh cache).",
                        "default": False,
                    },
                },
                "additionalProperties": False,
            },
            handler=_handle_strategy_tournament,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_get_paa_allocation",
            description=(
                "Compute the live Protective Asset Allocation (PAA) 12-ETF breadth crash-shield signal: "
                "number of risk ETFs below 252-day SMA, crash protection percentage, and exact live target "
                "ETF weights (offensive top-6 vs defensive IEF/SHY)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "force_refresh": {
                        "type": "boolean",
                        "description": "Force refresh Yahoo Finance ETF closes.",
                        "default": False,
                    },
                },
                "additionalProperties": False,
            },
            handler=_handle_paa_allocation,
            read_only=True,
        ),
        McpToolSpec(
            name="dsa_get_quant_paper_books",
            description=(
                "Read or advance the simulated daily StrategyPaperBook ledgers for PAA Crash-Shield "
                "and Meta-Portfolio A (virtual NAV, return vs SPY, open ETF shares/weights, recent "
                "rebalance trades). Strictly simulated; never places real broker orders."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "strategies": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["paa", "meta_a"]},
                        "description": "Optional list of strategy books (default ['paa', 'meta_a']).",
                    },
                    "step_paper": {
                        "type": "boolean",
                        "description": "Advance books through latest completed daily close (default false).",
                        "default": False,
                    },
                    "force_rebalance": {
                        "type": "boolean",
                        "description": "Force rebalance to live model targets on latest close (default false).",
                        "default": False,
                    },
                    "force_refresh_prices": {
                        "type": "boolean",
                        "description": "Force refresh Yahoo Finance ETF closes before stepping (default false).",
                        "default": False,
                    },
                },
                "additionalProperties": False,
            },
            handler=_handle_quant_paper_books,
            read_only=False,
        ),
        McpToolSpec(
            name="dsa_get_forward_validation",
            description=(
                "Forward (live paper) validation gate for the frozen PAA and Meta-Portfolio A strategies: "
                "days collected since the freeze, forward return vs SPY, Excess Sharpe vs BIL with its "
                "standard error, max drawdown, percentile of the forward return within the frozen backtest, "
                "measured Alpaca paper slippage, and the verdict (COLLECTING / PASS / FAIL / INVALIDATED). "
                "Use before claiming any strategy is proven; read-only."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "strategies": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["paa", "meta_a"]},
                        "description": "Optional list (default: configured quant paper strategies).",
                    },
                },
                "additionalProperties": False,
            },
            handler=_handle_forward_validation,
            read_only=True,
        ),
    ]
