# -*- coding: utf-8 -*-
"""Quantitative entry gates, market regime filter, portfolio risk guardrails, and live quotes."""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import desc, select

from src.storage import DatabaseManager, StockDaily

logger = logging.getLogger(__name__)

# Built-in GICS sector seed for top liquid US equities (zero-network fast path).
_US_SECTOR_SEED: Dict[str, str] = {
    # Semiconductors
    "NVDA": "Semiconductors",
    "AVGO": "Semiconductors",
    "AMD": "Semiconductors",
    "TSM": "Semiconductors",
    "ASML": "Semiconductors",
    "QCOM": "Semiconductors",
    "AMAT": "Semiconductors",
    "LRCX": "Semiconductors",
    "KLAC": "Semiconductors",
    "MU": "Semiconductors",
    "TXN": "Semiconductors",
    "INTC": "Semiconductors",
    "MRVL": "Semiconductors",
    "ADI": "Semiconductors",
    "ARM": "Semiconductors",
    "SMCI": "Semiconductors",
    # Software & Cloud / Hardware Tech
    "AAPL": "Technology",
    "MSFT": "Technology",
    "ORCL": "Technology",
    "CRM": "Technology",
    "ADBE": "Technology",
    "NOW": "Technology",
    "PANW": "Technology",
    "CRWD": "Technology",
    "SNOW": "Technology",
    "PLTR": "Technology",
    "INTU": "Technology",
    "SNPS": "Technology",
    "CDNS": "Technology",
    "CSCO": "Technology",
    "IBM": "Technology",
    "ACN": "Technology",
    # Communication Services & Internet
    "GOOGL": "Communication Services",
    "GOOG": "Communication Services",
    "META": "Communication Services",
    "NFLX": "Communication Services",
    "DIS": "Communication Services",
    "TMUS": "Communication Services",
    "VZ": "Communication Services",
    "T": "Communication Services",
    # Consumer Discretionary
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary",
    "LOW": "Consumer Discretionary",
    "MCD": "Consumer Discretionary",
    "NKE": "Consumer Discretionary",
    "SBUX": "Consumer Discretionary",
    "TJX": "Consumer Discretionary",
    "BKNG": "Consumer Discretionary",
    "CMG": "Consumer Discretionary",
    # Healthcare
    "LLY": "Healthcare",
    "UNH": "Healthcare",
    "JNJ": "Healthcare",
    "ABBV": "Healthcare",
    "MRK": "Healthcare",
    "TMO": "Healthcare",
    "ABT": "Healthcare",
    "DHR": "Healthcare",
    "ISRG": "Healthcare",
    "AMGN": "Healthcare",
    "VRTX": "Healthcare",
    "REGN": "Healthcare",
    "PFE": "Healthcare",
    # Financials
    "BRK-B": "Financials",
    "JPM": "Financials",
    "V": "Financials",
    "MA": "Financials",
    "BAC": "Financials",
    "GS": "Financials",
    "MS": "Financials",
    "BLK": "Financials",
    "SPGI": "Financials",
    "AXP": "Financials",
    "SCHW": "Financials",
    "C": "Financials",
    # Industrials & Defense
    "GE": "Industrials",
    "CAT": "Industrials",
    "RTX": "Industrials",
    "LMT": "Industrials",
    "HON": "Industrials",
    "UNP": "Industrials",
    "DE": "Industrials",
    "ETN": "Industrials",
    "BA": "Industrials",
    "UPS": "Industrials",
    # Consumer Staples
    "WMT": "Consumer Staples",
    "COST": "Consumer Staples",
    "PG": "Consumer Staples",
    "KO": "Consumer Staples",
    "PEP": "Consumer Staples",
    "PM": "Consumer Staples",
    # Energy & Utilities
    "XOM": "Energy",
    "CVX": "Energy",
    "COP": "Energy",
    "SLB": "Energy",
    "EOG": "Energy",
    "NEE": "Utilities",
    "SO": "Utilities",
    "DUK": "Utilities",
    "CEG": "Utilities",
    "VST": "Utilities",
    # ETFs
    "SPY": "ETF",
    "QQQ": "ETF",
    "IWM": "ETF",
    "DIA": "ETF",
}


@dataclass
class MarketRegimeSnapshot:
    regime: str  # risk_on | caution | risk_off | neutral
    position_scale: float
    spy_close: Optional[float] = None
    spy_sma50: Optional[float] = None
    spy_sma200: Optional[float] = None
    vix_level: Optional[float] = None
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskGateDecision:
    allowed: bool
    position_scale: float
    blocked_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    regime: Optional[MarketRegimeSnapshot] = None
    sector: Optional[str] = None
    quant_score: Optional[float] = None
    drawdown_pct: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if self.regime is not None:
            payload["regime"] = self.regime.to_dict()
        return payload


def _load_db_closes(
    db_manager: DatabaseManager,
    code: str,
    *,
    as_of_date: Optional[date] = None,
    limit: int = 240,
) -> List[float]:
    stmt = select(StockDaily.close).where(StockDaily.code == code)
    if as_of_date is not None:
        stmt = stmt.where(StockDaily.date <= as_of_date)
    stmt = stmt.order_by(desc(StockDaily.date)).limit(limit)
    with db_manager.session_scope() as session:
        rows = session.execute(stmt).all()
    closes = [float(r[0]) for r in reversed(rows) if r[0] is not None and float(r[0]) > 0]
    return closes


def evaluate_market_regime(
    db_manager: Optional[DatabaseManager] = None,
    *,
    as_of_date: Optional[date] = None,
    history_fetcher: Optional[Callable[[str], Sequence[float]]] = None,
    allow_remote: bool = False,
) -> MarketRegimeSnapshot:
    """Assess broad US equity regime from SPY 50/200 SMA trend and VIX volatility."""
    spy_closes: List[float] = []
    vix_closes: List[float] = []

    if history_fetcher is not None:
        try:
            spy_closes = [float(x) for x in (history_fetcher("SPY") or []) if float(x) > 0]
            vix_closes = [float(x) for x in (history_fetcher("^VIX") or []) if float(x) > 0]
        except Exception as exc:
            logger.debug("Custom regime history_fetcher failed: %s", exc)
    elif db_manager is not None:
        spy_closes = _load_db_closes(db_manager, "SPY", as_of_date=as_of_date)
        vix_closes = _load_db_closes(db_manager, "^VIX", as_of_date=as_of_date, limit=30)

    if len(spy_closes) < 50 and allow_remote:
        try:
            import yfinance as yf

            hist = yf.Ticker("SPY").history(period="1y", auto_adjust=True)
            if hist is not None and not hist.empty and "Close" in hist:
                spy_closes = [float(x) for x in hist["Close"].dropna().tolist() if float(x) > 0]
            vix_hist = yf.Ticker("^VIX").history(period="1mo")
            if vix_hist is not None and not vix_hist.empty and "Close" in vix_hist:
                vix_closes = [float(x) for x in vix_hist["Close"].dropna().tolist() if float(x) > 0]
        except Exception as exc:
            logger.debug("Remote SPY/VIX regime fetch failed: %s", exc)

    vix_level = round(vix_closes[-1], 2) if vix_closes else None
    if len(spy_closes) < 50:
        reasons = ["SPY benchmark history unavailable (<50 bars); regime gate neutral"]
        return MarketRegimeSnapshot(
            regime="neutral",
            position_scale=1.0,
            vix_level=vix_level,
            reasons=reasons,
        )

    spy_close = round(spy_closes[-1], 4)
    sma50 = round(sum(spy_closes[-50:]) / 50.0, 4)
    sma200 = round(sum(spy_closes[-200:]) / 200.0, 4) if len(spy_closes) >= 200 else None

    reasons: List[str] = []
    if (sma200 is not None and spy_close < sma200) or (vix_level is not None and vix_level >= 32.0):
        if sma200 is not None and spy_close < sma200:
            reasons.append(f"SPY {spy_close:.2f} < SMA200 {sma200:.2f} (downtrend)")
        if vix_level is not None and vix_level >= 32.0:
            reasons.append(f"VIX elevated crisis level ({vix_level:.1f} >= 32)")
        return MarketRegimeSnapshot(
            regime="risk_off",
            position_scale=0.0,
            spy_close=spy_close,
            spy_sma50=sma50,
            spy_sma200=sma200,
            vix_level=vix_level,
            reasons=reasons,
        )

    if spy_close < sma50 or (vix_level is not None and vix_level >= 24.0):
        if spy_close < sma50:
            reasons.append(f"SPY {spy_close:.2f} < SMA50 {sma50:.2f} (short-term pullback)")
        if vix_level is not None and vix_level >= 24.0:
            reasons.append(f"VIX elevated ({vix_level:.1f} >= 24)")
        return MarketRegimeSnapshot(
            regime="caution",
            position_scale=0.5,
            spy_close=spy_close,
            spy_sma50=sma50,
            spy_sma200=sma200,
            vix_level=vix_level,
            reasons=reasons,
        )

    reasons.append(
        f"SPY {spy_close:.2f} > SMA50 {sma50:.2f}"
        + (f" & SMA200 {sma200:.2f}" if sma200 is not None else "")
    )
    return MarketRegimeSnapshot(
        regime="risk_on",
        position_scale=1.0,
        spy_close=spy_close,
        spy_sma50=sma50,
        spy_sma200=sma200,
        vix_level=vix_level,
        reasons=reasons,
    )


def resolve_stock_sectors(
    symbols: Iterable[str],
    *,
    sector_map: Optional[Dict[str, str]] = None,
    allow_remote: bool = False,
) -> Dict[str, str]:
    """Resolve sector label per ticker using local seed, custom map, and optional yfinance."""
    out: Dict[str, str] = {}
    missing: List[str] = []
    for raw in symbols:
        sym = str(raw or "").strip().upper()
        if not sym:
            continue
        if sector_map and sym in sector_map and sector_map[sym]:
            out[sym] = str(sector_map[sym])
        elif sym in _US_SECTOR_SEED:
            out[sym] = _US_SECTOR_SEED[sym]
        else:
            missing.append(sym)

    if missing and allow_remote:
        try:
            import yfinance as yf

            for sym in missing:
                try:
                    info = yf.Ticker(sym).info or {}
                    sec = info.get("industry") if info.get("industry") == "Semiconductors" else info.get("sector")
                    if sec:
                        out[sym] = str(sec)
                        _US_SECTOR_SEED[sym] = str(sec)
                except Exception:
                    continue
        except ImportError:
            pass
    return out


def fetch_live_quotes(
    symbols: Sequence[str],
    *,
    alpaca_client: Optional[Any] = None,
) -> Dict[str, Tuple[float, date]]:
    """Fetch latest quote prices fail-open via Alpaca Data API (when configured) or yfinance."""
    clean = [str(s or "").strip().upper() for s in symbols if str(s or "").strip()]
    if not clean:
        return {}

    quotes: Dict[str, Tuple[float, date]] = {}
    if alpaca_client is not None and getattr(alpaca_client, "is_configured", lambda: False)():
        us_syms = [s for s in clean if "." not in s and not s.isdigit()]
        if us_syms:
            try:
                trades = alpaca_client.get_latest_trades(us_syms)
                today = date.today()
                for sym, payload in trades.items():
                    price = float(payload.get("p") or payload.get("price") or 0.0)
                    if price > 0:
                        quotes[sym.upper()] = (price, today)
            except Exception as exc:
                logger.debug("Alpaca live quote fetch failed (falling back): %s", exc)

    remaining = [s for s in clean if s not in quotes]
    if remaining:
        try:
            import yfinance as yf

            today = date.today()
            for sym in remaining:
                try:
                    t = yf.Ticker(sym)
                    fi = getattr(t, "fast_info", None)
                    last_px = None
                    if fi is not None:
                        last_px = getattr(fi, "last_price", None) or (
                            fi.get("last_price") if isinstance(fi, dict) else None
                        )
                    if last_px is None or float(last_px) <= 0:
                        hist = t.history(period="2d")
                        if hist is not None and not hist.empty:
                            last_px = float(hist["Close"].iloc[-1])
                    if last_px is not None and float(last_px) > 0:
                        quotes[sym] = (round(float(last_px), 6), today)
                except Exception:
                    continue
        except ImportError:
            pass

    return quotes


def compute_portfolio_drawdown_pct(
    trades: Sequence[Dict[str, Any]],
    mark_prices: Optional[Dict[str, float]] = None,
    *,
    equity_base: Optional[float] = None,
) -> Optional[float]:
    """Compute portfolio drawdown % from realized PnL + current open unrealized PnL.

    Tracks cumulative closed PnL trajectory plus open mark-to-market relative to
    ``max(equity_base, peak_deployed_capital, 1.0)``.
    """
    if not trades:
        return 0.0

    marks = {str(k).upper(): float(v) for k, v in (mark_prices or {}).items() if float(v) > 0}
    books: Dict[str, Dict[str, float]] = {}
    realized_cumulative = 0.0
    peak_pnl = 0.0
    peak_deployed = 0.0

    for trade in trades:
        code = str(trade.get("stock_code") or "").upper()
        side = str(trade.get("side") or "").lower()
        qty = float(trade.get("quantity") or 0.0)
        px = float(trade.get("price") or 0.0)
        if not code or qty <= 0 or px <= 0:
            continue
        book = books.setdefault(code, {"qty": 0.0, "cost": 0.0, "last_px": px})
        book["last_px"] = px
        if side == "buy":
            book["qty"] += qty
            book["cost"] += qty * px
            total_cost_now = sum(b["cost"] for b in books.values() if b["qty"] > 1e-9)
            peak_deployed = max(peak_deployed, total_cost_now)
        else:
            if book["qty"] <= 1e-9:
                continue
            avg_cost = book["cost"] / book["qty"]
            sold = min(qty, book["qty"])
            realized_cumulative += (px - avg_cost) * sold
            book["cost"] -= avg_cost * sold
            book["qty"] -= sold
            peak_pnl = max(peak_pnl, realized_cumulative)

    unrealized = 0.0
    for code, book in books.items():
        if book["qty"] <= 1e-9:
            continue
        mark = marks.get(code, book["last_px"])
        unrealized += (mark * book["qty"]) - book["cost"]

    current_total_pnl = realized_cumulative + unrealized
    peak_pnl = max(peak_pnl, current_total_pnl, 0.0)
    base = max(float(equity_base or 0.0), peak_deployed, 1.0)
    peak_equity = base + peak_pnl
    current_equity = base + current_total_pnl
    if current_equity >= peak_equity:
        return 0.0
    drawdown = ((peak_equity - current_equity) / peak_equity) * 100.0
    return round(max(0.0, drawdown), 2)


def _score_single_stock_quant_from_db(
    db_manager: DatabaseManager,
    stock_code: str,
    *,
    as_of_date: Optional[date] = None,
) -> Optional[float]:
    """Compute an offline residual-momentum + 52w-high quant score using stored DB bars."""
    import pandas as pd
    from src.services.us_quant_screener import score_us_quant_candidate

    spy_stmt = select(StockDaily.date, StockDaily.high, StockDaily.low, StockDaily.close, StockDaily.volume).where(
        StockDaily.code == "SPY"
    )
    stk_stmt = select(StockDaily.date, StockDaily.high, StockDaily.low, StockDaily.close, StockDaily.volume).where(
        StockDaily.code == stock_code
    )
    if as_of_date is not None:
        spy_stmt = spy_stmt.where(StockDaily.date <= as_of_date)
        stk_stmt = stk_stmt.where(StockDaily.date <= as_of_date)
    spy_stmt = spy_stmt.order_by(StockDaily.date)
    stk_stmt = stk_stmt.order_by(StockDaily.date)

    with db_manager.session_scope() as session:
        spy_rows = session.execute(spy_stmt).all()
        stk_rows = session.execute(stk_stmt).all()

    if len(spy_rows) < 150 or len(stk_rows) < 150:
        return None

    spy_df = pd.DataFrame(spy_rows, columns=["date", "High", "Low", "Close", "Volume"]).set_index("date")
    stk_df = pd.DataFrame(stk_rows, columns=["date", "High", "Low", "Close", "Volume"]).set_index("date")
    cand = score_us_quant_candidate(stock_code, stk_df, spy_df, min_dollar_volume=0.0)
    return float(cand.score) if cand is not None else 0.0


def evaluate_entry_risk_gate(
    *,
    stock_code: str,
    signal: Dict[str, Any],
    open_positions: Sequence[Dict[str, Any]],
    trades: Sequence[Dict[str, Any]],
    mark_prices: Optional[Dict[str, float]] = None,
    db_manager: Optional[DatabaseManager] = None,
    as_of_date: Optional[date] = None,
    position_size_budget: float = 10000.0,
    max_open_positions: Optional[int] = None,
    max_sector_positions: Optional[int] = None,
    max_drawdown_pct: Optional[float] = None,
    market_regime_filter: bool = False,
    quant_gate_enabled: bool = False,
    quant_min_score: float = 40.0,
    sector_map: Optional[Dict[str, str]] = None,
    regime_history_fetcher: Optional[Callable[[str], Sequence[float]]] = None,
    allow_remote: bool = False,
) -> RiskGateDecision:
    """Enforce portfolio concentration, drawdown circuit-breaker, regime, and quant gates."""
    code = str(stock_code or "").strip().upper()
    blocked: List[str] = []
    warnings: List[str] = []
    position_scale = 1.0

    # 1. Max Open Positions Cap
    held_codes = {str(p.get("stock_code") or "").upper() for p in open_positions if float(p.get("quantity") or 0) > 0}
    if max_open_positions is not None and code not in held_codes and len(held_codes) >= int(max_open_positions):
        blocked.append(f"max_open_positions_reached ({len(held_codes)}/{int(max_open_positions)})")

    # 2. Sector Concentration Cap
    resolved_sector: Optional[str] = None
    if max_sector_positions is not None or held_codes:
        all_syms = sorted(held_codes | {code})
        sectors = resolve_stock_sectors(all_syms, sector_map=sector_map, allow_remote=allow_remote)
        resolved_sector = sectors.get(code)
        if max_sector_positions is not None and resolved_sector:
            same_sector_count = sum(
                1 for sym in held_codes if sym != code and sectors.get(sym) == resolved_sector
            )
            if same_sector_count >= int(max_sector_positions):
                blocked.append(
                    f"max_sector_positions_reached ({resolved_sector}: {same_sector_count}/{int(max_sector_positions)})"
                )

    # 3. Portfolio Drawdown Circuit Breaker
    dd_pct = compute_portfolio_drawdown_pct(
        trades,
        mark_prices=mark_prices,
        equity_base=position_size_budget * max(1, int(max_open_positions or 4)),
    )
    if max_drawdown_pct is not None and dd_pct is not None and dd_pct >= float(max_drawdown_pct):
        blocked.append(f"drawdown_circuit_breaker ({dd_pct:.2f}% >= {float(max_drawdown_pct):.1f}%)")

    # 4. US Market Regime Filter (SPY 50/200 SMA + VIX)
    regime: Optional[MarketRegimeSnapshot] = None
    if market_regime_filter or regime_history_fetcher is not None:
        regime = evaluate_market_regime(
            db_manager=db_manager,
            as_of_date=as_of_date,
            history_fetcher=regime_history_fetcher,
            allow_remote=allow_remote,
        )
        if market_regime_filter:
            if regime.regime == "risk_off":
                blocked.append(f"market_regime_risk_off ({'; '.join(regime.reasons)})")
                position_scale = 0.0
            elif regime.regime == "caution":
                position_scale = min(position_scale, regime.position_scale)
                warnings.append(f"market_regime_caution ({'; '.join(regime.reasons)})")

    # 5. Quantitative Entry Gate (prevent pure-narrative LLM BUYs below quant threshold)
    quant_score: Optional[float] = None
    raw_q = signal.get("quant_score")
    if raw_q is not None:
        try:
            quant_score = float(raw_q)
        except (TypeError, ValueError):
            quant_score = None
    elif quant_gate_enabled and db_manager is not None:
        quant_score = _score_single_stock_quant_from_db(db_manager, code, as_of_date=as_of_date)

    if quant_gate_enabled:
        if quant_score is None:
            warnings.append("quant_score_unavailable_fail_open")
        elif quant_score < float(quant_min_score):
            blocked.append(f"quant_gate_below_min ({quant_score:.1f} < {float(quant_min_score):.1f})")

    return RiskGateDecision(
        allowed=(len(blocked) == 0),
        position_scale=round(position_scale, 3),
        blocked_reasons=blocked,
        warnings=warnings,
        regime=regime,
        sector=resolved_sector,
        quant_score=round(quant_score, 2) if quant_score is not None else None,
        drawdown_pct=dd_pct,
    )
