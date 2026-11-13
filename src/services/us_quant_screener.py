# -*- coding: utf-8 -*-
"""High-Alpha US Quantitative Multi-Factor & Composite Screener.

Implements academically validated US equity return predictors:
1. Residual Momentum (12-1 month return orthogonalized against SPY, Blitz et al. 2011)
2. 52-Week High Proximity (George & Hwang 2004)
3. Frog-in-the-Pan Information Discreteness (Da, Gurun & Warachka 2014)
4. Cash-Based Operating Profitability & Low Accruals (Ball et al. 2016; Sloan 1996)
   via SEC EDGAR XBRL companyfacts with yfinance fallback
5. Barroso & Santa-Clara (2015) Volatility-Scaled Momentum Weighting

Also exposes ``screen_us_alpha_candidates`` to combine US Quant factors,
PEAD 2.0 earnings surprises, and live SEC Form 4 cluster buys into a single
ranked candidate list for ``main.py --screen-us``.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

SEC_SUBMISSIONS_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Liquid US mid- & large-cap default universe (avoiding microcap illiquidity)
DEFAULT_US_QUANT_UNIVERSE: List[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "LLY",
    "JPM", "V", "UNH", "XOM", "COST", "HD", "MA", "PG",
    "NFLX", "CRM", "AMD", "ADBE", "ORCL", "CSCO", "ACN", "TMO",
    "ABT", "DHR", "LIN", "TXN", "QCOM", "INTU", "AMAT", "ISRG",
    "ANET", "PANW", "CRWD", "DDOG", "SNOW", "NET", "MDB", "ZS",
    "AXON", "DECK", "CELH", "ELF", "DUOL", "TOST", "CAVA", "ONON",
    "SAIA", "EME", "URI", "FIX", "PWR", "MOD", "VRT", "VST",
    "CEG", "NRG", "SMCI", "APP", "PLTR", "HOOD", "SOFI", "AFRM",
    "DKNG", "RKLB", "ASTS", "NTRA", "EXAS", "INSM", "HALO", "PCVX",
    "CROX", "WSM", "TSCO", "ORLY", "AZO", "ULTA", "LULU", "NKE",
]


@dataclass
class UsQuantCandidate:
    """Quantitative multi-factor evaluation result for a single US stock."""

    symbol: str
    score: float
    residual_momentum_z: Optional[float] = None
    raw_12_1m_return_pct: Optional[float] = None
    near_52w_high: Optional[float] = None
    fip_id: Optional[float] = None
    cash_op_profitability: Optional[float] = None
    accruals_ratio: Optional[float] = None
    realized_vol_ann: Optional[float] = None
    vol_scale_weight: Optional[float] = None
    avg_dollar_volume: Optional[float] = None
    last_close: Optional[float] = None
    pead_score: float = 0.0
    insider_score: float = 0.0
    reasons: List[str] = field(default_factory=list)


def _sec_headers(user_agent: Optional[str] = None) -> Dict[str, str]:
    ua = (
        user_agent
        or os.getenv("SEC_EDGAR_USER_AGENT", "").strip()
        or "daily_stock_analysis/1.0 (contact@example.com)"
    )
    return {
        "User-Agent": ua,
        "Accept": "application/json",
    }


def _extract_close_series(df: pd.DataFrame) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    col = "Close" if "Close" in df.columns else ("close" if "close" in df.columns else None)
    if col is None:
        return None
    s = df[col]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    s = pd.to_numeric(s, errors="coerce").dropna()
    return s if not s.empty else None


def _extract_high_series(df: pd.DataFrame) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    for col in ("High", "high", "Close", "close"):
        if col in df.columns:
            s = df[col]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            s = pd.to_numeric(s, errors="coerce").dropna()
            if not s.empty:
                return s
    return None


def _extract_volume_series(df: pd.DataFrame) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    for col in ("Volume", "volume"):
        if col in df.columns:
            s = df[col]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            s = pd.to_numeric(s, errors="coerce").dropna()
            if not s.empty:
                return s
    return None


def compute_residual_momentum(
    stock_close: pd.Series,
    market_close: pd.Series,
    *,
    lookback_days: int = 252,
    skip_recent_days: int = 21,
    min_obs: int = 120,
) -> Tuple[Optional[float], Optional[float]]:
    """Compute 12-1m residual momentum (mean/std of OLS residuals vs market).

    Returns ``(residual_mom_z, raw_12_1m_return_pct)``.
    """
    if stock_close is None or market_close is None:
        return None, None
    s_ret = stock_close.pct_change().dropna()
    m_ret = market_close.pct_change().dropna()
    aligned = pd.concat([s_ret.rename("s"), m_ret.rename("m")], axis=1, join="inner").dropna()
    if len(aligned) < min_obs + skip_recent_days:
        return None, None

    window = aligned.iloc[-(lookback_days + skip_recent_days) : len(aligned) - skip_recent_days]
    if len(window) < min_obs:
        return None, None

    x = window["m"].to_numpy(dtype=float)
    y = window["s"].to_numpy(dtype=float)
    var_x = float(np.var(x, ddof=1))
    if var_x <= 1e-12:
        return None, None

    beta = float(np.cov(x, y, ddof=1)[0, 1] / var_x)
    alpha = float(np.mean(y) - beta * np.mean(x))
    resid = y - (alpha + beta * x)
    resid_std = float(np.std(resid, ddof=1))
    if resid_std <= 1e-12:
        return None, None

    # Risk-adjusted residual momentum (Blitz, Huij & Martens 2011):
    # Preserve stock alpha (y - beta * x) while normalizing by idiosyncratic residual vol.
    abnormal_ret = y - beta * x
    resid_mom_z = float(np.mean(abnormal_ret) / resid_std) * math.sqrt(len(resid))
    raw_cum_pct = (float(np.prod(1.0 + y)) - 1.0) * 100.0
    return resid_mom_z, raw_cum_pct


def compute_52w_high_proximity(
    close_series: pd.Series,
    high_series: Optional[pd.Series] = None,
    *,
    window_days: int = 252,
) -> Optional[float]:
    """Return ``last_close / max(52w_high)`` in (0, 1+]."""
    if close_series is None or close_series.empty:
        return None
    last_close = float(close_series.iloc[-1])
    ref = high_series if (high_series is not None and not high_series.empty) else close_series
    peak = float(ref.tail(window_days).max())
    if peak <= 0 or last_close <= 0:
        return None
    return last_close / peak


def compute_frog_in_the_pan(
    close_series: pd.Series,
    *,
    lookback_days: int = 252,
    skip_recent_days: int = 21,
) -> Optional[float]:
    """Compute Information Discreteness ID = sign(PRET) * (%neg - %pos).

    Lower (more negative) ID indicates smooth, continuous information arrival,
    which produces stronger momentum continuation (Da, Gurun & Warachka 2014).
    """
    if close_series is None or len(close_series) < 60 + skip_recent_days:
        return None
    rets = close_series.pct_change().dropna()
    end_idx = len(rets) - skip_recent_days
    start_idx = max(0, end_idx - lookback_days)
    window = rets.iloc[start_idx:end_idx]
    if len(window) < 40:
        return None

    cum_ret = float(np.prod(1.0 + window.to_numpy(dtype=float)) - 1.0)
    if abs(cum_ret) < 1e-9:
        return 0.0
    sign_pret = 1.0 if cum_ret > 0 else -1.0
    pct_pos = float((window > 0).mean())
    pct_neg = float((window < 0).mean())
    return sign_pret * (pct_neg - pct_pos)


def compute_vol_scale_weight(
    close_series: pd.Series,
    *,
    target_vol_ann: float = 0.12,
    vol_lookback_days: int = 126,
    max_weight: float = 2.0,
    min_weight: float = 0.25,
) -> Tuple[Optional[float], Optional[float]]:
    """Return ``(realized_vol_ann, barroso_santa_clara_weight)``."""
    if close_series is None or len(close_series) < 30:
        return None, None
    rets = close_series.pct_change().dropna().tail(vol_lookback_days)
    if len(rets) < 20:
        return None, None
    daily_std = float(rets.std(ddof=1))
    if daily_std <= 1e-9:
        return None, None
    realized_vol_ann = daily_std * math.sqrt(252.0)
    weight = target_vol_ann / realized_vol_ann
    weight = max(min_weight, min(max_weight, weight))
    return realized_vol_ann, weight


def _latest_xbrl_fact_value(
    us_gaap: Dict[str, Any],
    tags: Sequence[str],
    *,
    unit: str = "USD",
) -> Optional[float]:
    for tag in tags:
        node = us_gaap.get(tag)
        if not isinstance(node, dict):
            continue
        units = node.get("units", {})
        items = units.get(unit)
        if not isinstance(items, list) or not items:
            continue
        # Prefer annual 10-K / FY items, sorted by end date descending
        annual = [
            it for it in items
            if str(it.get("form", "")).upper() in {"10-K", "20-F"}
            and str(it.get("fp", "")).upper() == "FY"
            and it.get("val") is not None
        ]
        pool = annual or [it for it in items if it.get("val") is not None]
        if not pool:
            continue
        pool.sort(key=lambda x: (str(x.get("end", "")), str(x.get("filed", ""))), reverse=True)
        try:
            return float(pool[0]["val"])
        except (TypeError, ValueError):
            continue
    return None


def fetch_sec_xbrl_quality(
    symbol: str,
    *,
    cik_map: Optional[Dict[str, str]] = None,
    session: Optional[requests.Session] = None,
    timeout: float = 10.0,
) -> Tuple[Optional[float], Optional[float]]:
    """Fetch Cash-Based Operating Profitability & Accruals from SEC EDGAR XBRL.

    Cash-Based Operating Profitability (Ball et al. 2016) ~=
        (Operating Cash Flow + Interest Expense - CapEx? or Operating Income - Accruals) / Total Assets.
    Specifically we compute:
        ``accruals_ratio = (NetIncome - OperatingCashFlow) / TotalAssets`` (Sloan 1996, lower is better)
        ``cash_op_profitability = (OperatingCashFlow + CashTaxesPaid_or_0) / TotalAssets``
    where OperatingCashFlow / TotalAssets serves as the clean, universally reported
    SEC XBRL cash-profitability proxy when detailed working-capital tags vary.
    """
    if cik_map is None:
        return None, None
    cik = cik_map.get(symbol.upper())
    if not cik:
        return None, None

    sess = session or requests.Session()
    url = SEC_COMPANYFACTS_URL.format(cik=str(cik).zfill(10))
    try:
        resp = sess.get(url, headers=_sec_headers(), timeout=timeout)
        if resp.status_code != 200:
            return None, None
        payload = resp.json()
    except Exception as exc:
        logger.debug("SEC companyfacts failed for %s: %s", symbol, exc)
        return None, None

    us_gaap = payload.get("facts", {}).get("us-gaap", {})
    if not isinstance(us_gaap, dict):
        return None, None

    assets = _latest_xbrl_fact_value(us_gaap, ["Assets"])
    if not assets or assets <= 0:
        return None, None

    ocf = _latest_xbrl_fact_value(
        us_gaap,
        [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ],
    )
    net_income = _latest_xbrl_fact_value(
        us_gaap,
        ["NetIncomeLoss", "ProfitLoss"],
    )
    op_income = _latest_xbrl_fact_value(
        us_gaap,
        ["OperatingIncomeLoss"],
    )

    cash_prof: Optional[float] = None
    accruals: Optional[float] = None
    if ocf is not None:
        cash_prof = ocf / assets
    elif op_income is not None:
        cash_prof = op_income / assets

    if net_income is not None and ocf is not None:
        accruals = (net_income - ocf) / assets

    return cash_prof, accruals


def fetch_yfinance_quality(symbol: str) -> Tuple[Optional[float], Optional[float]]:
    """Fallback quality metrics from yfinance info/financials when SEC XBRL is unavailable."""
    try:
        import yfinance as yf
    except ImportError:
        return None, None

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        ocf = info.get("operatingCashflow")
        total_assets = info.get("totalAssets")
        if total_assets and ocf is not None and float(total_assets) > 0:
            cash_prof = float(ocf) / float(total_assets)
            net_inc = info.get("netIncomeToCommon")
            accruals = (
                (float(net_inc) - float(ocf)) / float(total_assets)
                if net_inc is not None
                else None
            )
            return cash_prof, accruals
        # Secondary proxy: operatingMargins + returnOnEquity
        op_margin = info.get("operatingMargins")
        roe = info.get("returnOnEquity")
        if op_margin is not None:
            return float(op_margin) * 0.5, None
        if roe is not None:
            return float(roe) * 0.3, None
    except Exception as exc:
        logger.debug("yfinance quality fallback failed for %s: %s", symbol, exc)
    return None, None


def load_sec_cik_map(
    session: Optional[requests.Session] = None,
    timeout: float = 10.0,
) -> Dict[str, str]:
    """Load ticker -> 10-digit zero-padded CIK mapping from SEC EDGAR."""
    sess = session or requests.Session()
    try:
        resp = sess.get(SEC_SUBMISSIONS_TICKERS_URL, headers=_sec_headers(), timeout=timeout)
        if resp.status_code != 200:
            return {}
        raw = resp.json()
        mapping: Dict[str, str] = {}
        if isinstance(raw, dict):
            for entry in raw.values():
                if isinstance(entry, dict) and entry.get("ticker") and entry.get("cik_str") is not None:
                    mapping[str(entry["ticker"]).upper()] = str(entry["cik_str"]).zfill(10)
        return mapping
    except Exception as exc:
        logger.debug("SEC company_tickers fetch failed: %s", exc)
        return {}


def score_us_quant_candidate(
    symbol: str,
    stock_df: pd.DataFrame,
    market_df: pd.DataFrame,
    *,
    cash_op_profitability: Optional[float] = None,
    accruals_ratio: Optional[float] = None,
    min_dollar_volume: float = 5_000_000.0,
    target_vol_ann: float = 0.12,
) -> Optional[UsQuantCandidate]:
    """Compute multi-factor high-alpha score for a single US stock."""
    close_s = _extract_close_series(stock_df)
    high_s = _extract_high_series(stock_df)
    vol_s = _extract_volume_series(stock_df)
    mkt_close = _extract_close_series(market_df)
    if close_s is None or mkt_close is None or len(close_s) < 150:
        return None

    last_close = float(close_s.iloc[-1])
    if last_close < 3.0:  # avoid penny-stock microstructure noise
        return None

    avg_dollar_vol: Optional[float] = None
    if vol_s is not None and len(vol_s) >= 20:
        aligned_cv = pd.concat([close_s.tail(20), vol_s.tail(20)], axis=1).dropna()
        if not aligned_cv.empty:
            avg_dollar_vol = float((aligned_cv.iloc[:, 0] * aligned_cv.iloc[:, 1]).mean())
            if avg_dollar_vol < min_dollar_volume:
                return None

    resid_z, raw_12_1m = compute_residual_momentum(close_s, mkt_close)
    near_52w = compute_52w_high_proximity(close_s, high_s)
    fip_id = compute_frog_in_the_pan(close_s)
    realized_vol, vol_weight = compute_vol_scale_weight(close_s, target_vol_ann=target_vol_ann)

    if resid_z is None and near_52w is None:
        return None

    score = 0.0
    reasons: List[str] = []

    # 1. Residual Momentum (core alpha, max ~35 pts)
    if resid_z is not None:
        rm_pts = max(-15.0, min(35.0, resid_z * 14.0))
        score += rm_pts
        if resid_z >= 1.0:
            reasons.append(f"ResidMom z={resid_z:.2f} (+{raw_12_1m:.1f}%)")

    # 2. 52-Week High Proximity (George & Hwang 2004, max 25 pts)
    if near_52w is not None:
        if near_52w >= 0.90:
            hw_pts = min(25.0, (near_52w - 0.80) * 125.0)
            score += hw_pts
            reasons.append(f"52W-High={near_52w * 100:.1f}%")
        elif near_52w < 0.65:
            score -= 10.0

    # 3. Frog-in-the-Pan Information Discreteness (max 15 pts for smooth positive drift)
    if fip_id is not None:
        if fip_id < 0:
            fip_pts = min(15.0, abs(fip_id) * 60.0)
            score += fip_pts
            reasons.append(f"FIP_ID={fip_id:.3f}")
        elif fip_id > 0.10:
            score -= 5.0

    # 4. Cash-Based Operating Profitability & Low Accruals (max 25 pts)
    if cash_op_profitability is not None:
        # Typical strong cash profitability is 0.10 - 0.30 of assets
        cp_pts = max(-10.0, min(18.0, cash_op_profitability * 70.0))
        score += cp_pts
        if cash_op_profitability >= 0.10:
            reasons.append(f"CashOpProf={cash_op_profitability * 100:.1f}%")

    if accruals_ratio is not None:
        # Negative accruals (OCF > Net Income) = high earnings quality
        if accruals_ratio < -0.02:
            score += min(7.0, abs(accruals_ratio) * 70.0)
            reasons.append(f"LowAccruals={accruals_ratio * 100:.1f}%")
        elif accruals_ratio > 0.08:
            score -= min(10.0, (accruals_ratio - 0.05) * 80.0)

    # 5. Volatility-scaled momentum dampener (Barroso & Santa-Clara 2015)
    # Apply subtle penalty if realized vol is extremely elevated (>50% ann)
    if realized_vol is not None and realized_vol > 0.50:
        score *= max(0.70, 0.50 / realized_vol)

    return UsQuantCandidate(
        symbol=symbol.upper(),
        score=round(score, 2),
        residual_momentum_z=round(resid_z, 3) if resid_z is not None else None,
        raw_12_1m_return_pct=round(raw_12_1m, 2) if raw_12_1m is not None else None,
        near_52w_high=round(near_52w, 4) if near_52w is not None else None,
        fip_id=round(fip_id, 4) if fip_id is not None else None,
        cash_op_profitability=round(cash_op_profitability, 4) if cash_op_profitability is not None else None,
        accruals_ratio=round(accruals_ratio, 4) if accruals_ratio is not None else None,
        realized_vol_ann=round(realized_vol, 4) if realized_vol is not None else None,
        vol_scale_weight=round(vol_weight, 3) if vol_weight is not None else None,
        avg_dollar_volume=round(avg_dollar_vol, 0) if avg_dollar_vol is not None else None,
        last_close=round(last_close, 2),
        reasons=reasons,
    )


def _default_history_fetcher(symbol: str, period: str = "18mo") -> pd.DataFrame:
    import yfinance as yf

    return yf.Ticker(symbol).history(period=period, auto_adjust=True)


def screen_us_quant(
    symbols: Optional[Sequence[str]] = None,
    *,
    top_n: int = 10,
    min_score: float = 20.0,
    min_dollar_volume: float = 5_000_000.0,
    history_fetcher: Optional[Callable[[str], pd.DataFrame]] = None,
    quality_fetcher: Optional[Callable[[str], Tuple[Optional[float], Optional[float]]]] = None,
    use_sec_xbrl: bool = True,
) -> List[UsQuantCandidate]:
    """Screen US equities using Residual Momentum, 52W High, FIP, and Cash Profitability."""
    universe = [s.upper() for s in (symbols or DEFAULT_US_QUANT_UNIVERSE)]
    fetcher = history_fetcher or (lambda sym: _default_history_fetcher(sym, period="18mo"))

    market_df = fetcher("SPY")
    if market_df is None or market_df.empty:
        logger.warning("SPY benchmark history unavailable; US quant screener aborted.")
        return []

    cik_map: Dict[str, str] = {}
    if quality_fetcher is None and use_sec_xbrl:
        cik_map = load_sec_cik_map()

    results: List[UsQuantCandidate] = []
    for sym in universe:
        try:
            df = fetcher(sym)
            if df is None or df.empty:
                continue

            if quality_fetcher is not None:
                cash_prof, accruals = quality_fetcher(sym)
            else:
                cash_prof, accruals = (None, None)
                if cik_map:
                    cash_prof, accruals = fetch_sec_xbrl_quality(sym, cik_map=cik_map)
                if cash_prof is None:
                    cash_prof, accruals = fetch_yfinance_quality(sym)

            cand = score_us_quant_candidate(
                sym,
                df,
                market_df,
                cash_op_profitability=cash_prof,
                accruals_ratio=accruals,
                min_dollar_volume=min_dollar_volume,
            )
            if cand is not None and cand.score >= min_score:
                results.append(cand)
        except Exception as exc:
            logger.debug("US quant scoring failed for %s: %s", sym, exc)

    results.sort(key=lambda c: c.score, reverse=True)
    return results[:top_n]


def screen_us_alpha_candidates(
    symbols: Optional[Sequence[str]] = None,
    *,
    top_n: int = 8,
    include_pead: bool = True,
    include_form4: bool = True,
    history_fetcher: Optional[Callable[[str], pd.DataFrame]] = None,
    quality_fetcher: Optional[Callable[[str], Tuple[Optional[float], Optional[float]]]] = None,
    use_sec_xbrl: bool = True,
) -> List[UsQuantCandidate]:
    """Composite US high-alpha screener combining Quant + PEAD 2.0 + Live SEC Form 4.

    Fail-open design: if PEAD or Form 4 encounters network/API issues, Quant results
    still return cleanly, and vice versa.
    """
    merged: Dict[str, UsQuantCandidate] = {}

    # 1. Core Quant Multi-Factor
    quant_hits = screen_us_quant(
        symbols=symbols,
        top_n=max(top_n * 2, 16),
        min_score=10.0,
        history_fetcher=history_fetcher,
        quality_fetcher=quality_fetcher,
        use_sec_xbrl=use_sec_xbrl,
    )
    for c in quant_hits:
        merged[c.symbol] = c

    # 2. PEAD 2.0 Earnings Surprise Boost
    if include_pead:
        try:
            from src.services.pead_screener import screen_pead_candidates

            pead_hits = screen_pead_candidates(
                symbols=list(symbols) if symbols else list(DEFAULT_US_QUANT_UNIVERSE),
                top_n=top_n,
                min_score=30,
            )
            for p in pead_hits:
                sym = p.symbol.upper()
                surp_str = f"{p.eps_surprise_pct:+.1f}%" if p.eps_surprise_pct is not None else "n/a"
                pead_bonus = round(min(25.0, p.score * 0.25), 2)
                if sym in merged:
                    merged[sym].pead_score = pead_bonus
                    merged[sym].score = round(merged[sym].score + pead_bonus, 2)
                    merged[sym].reasons.append(f"PEAD={p.score:.0f} (EPS {surp_str})")
                else:
                    merged[sym] = UsQuantCandidate(
                        symbol=sym,
                        score=round(p.score * 0.65, 2),
                        near_52w_high=p.near_52w_high,
                        avg_dollar_volume=p.avg_dollar_volume,
                        pead_score=pead_bonus,
                        reasons=[f"PEAD={p.score:.0f} (EPS {surp_str})"],
                    )
        except Exception as exc:
            logger.warning("PEAD integration failed in composite US screener: %s", exc)

    # 3. Live SEC Form 4 Cluster Insider Buying Boost
    if include_form4:
        try:
            from data_provider.sec_form4_fetcher import SecForm4Fetcher
            from src.services.sec_form4_screener import score_insider_event

            fetcher = SecForm4Fetcher()
            clusters = fetcher.fetch_live_purchases(count=80, max_filings=40)
            for cl in clusters[:top_n]:
                sym = (cl.symbol or "").upper()
                if not sym:
                    continue
                ev_score, _ = score_insider_event(cl)
                insider_bonus = round(min(25.0, ev_score * 0.25), 2)
                if sym in merged:
                    merged[sym].insider_score = insider_bonus
                    merged[sym].score = round(merged[sym].score + insider_bonus, 2)
                    merged[sym].reasons.append(
                        f"Form4 Cluster ({cl.insider_count} insiders, ${cl.total_value:,.0f})"
                    )
                else:
                    merged[sym] = UsQuantCandidate(
                        symbol=sym,
                        score=round(ev_score * 0.65, 2),
                        insider_score=insider_bonus,
                        reasons=[
                            f"Form4 Cluster ({cl.insider_count} insiders, ${cl.total_value:,.0f})"
                        ],
                    )
        except Exception as exc:
            logger.warning("Live SEC Form 4 integration failed in composite US screener: %s", exc)

    ranked = sorted(merged.values(), key=lambda c: c.score, reverse=True)
    return ranked[:top_n]
