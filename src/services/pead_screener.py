# -*- coding: utf-8 -*-
"""PEAD (Post-Earnings Announcement Drift) Screener.

Exploits one of the most robust, academically verified market anomalies in quantitative finance:
stock prices do not adjust instantaneously to earnings surprises; instead, they drift in the
direction of the surprise over 20 to 60 trading days (Ball & Brown 1968, Bernard & Thomas 1989).

Alpha Factors Evaluated:
1. Standardized EPS Surprise % (Actual vs. Consensus Estimate).
2. Day 1 Immediate Price Reaction & Gap Confirmation.
3. Volume Expansion (> 1.5x 20-day Average Volume on Announcement Day).
4. Multi-Month Trend Alignment (Price > SMA 200 or SMA 50).
5. Post-Announcement Drift Horizon (1 to 45 calendar days).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PeadCandidate:
    """A scored Post-Earnings Announcement Drift candidate."""

    symbol: str
    company_name: str
    earnings_date: str
    days_since_earnings: int
    eps_estimate: Optional[float]
    eps_reported: Optional[float]
    eps_surprise_pct: Optional[float]
    day1_return_pct: Optional[float]
    total_drift_pct: Optional[float]
    volume_surge_ratio: Optional[float]
    trend_regime: str  # uptrend | downtrend | neutral
    conviction_tier: str  # HIGH | MEDIUM | LOW | NEGATIVE
    score: int  # 0 to 100
    reasons: List[str]
    sue_score: Optional[float] = None
    revenue_growth_pct: Optional[float] = None
    near_52w_high: Optional[float] = None
    avg_dollar_volume: Optional[float] = None
    announcement_session: str = "BMO"  # BMO | AMC

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "earnings_date": self.earnings_date,
            "days_since_earnings": self.days_since_earnings,
            "eps_estimate": self.eps_estimate,
            "eps_reported": self.eps_reported,
            "eps_surprise_pct": self.eps_surprise_pct,
            "sue_score": self.sue_score,
            "revenue_growth_pct": self.revenue_growth_pct,
            "near_52w_high": self.near_52w_high,
            "avg_dollar_volume": self.avg_dollar_volume,
            "announcement_session": self.announcement_session,
            "day1_return_pct": self.day1_return_pct,
            "total_drift_pct": self.total_drift_pct,
            "volume_surge_ratio": self.volume_surge_ratio,
            "trend_regime": self.trend_regime,
            "conviction_tier": self.conviction_tier,
            "score": self.score,
            "reasons": self.reasons,
        }


def resolve_event_day0(
    earn_ts: Any,
    trading_days: Sequence[date],
) -> Tuple[Optional[date], Optional[date], str]:
    """Resolve announcement Day 0 and baseline Day -1 accounting for BMO vs. AMC timing.

    If ``earn_ts`` carries an After-Market-Close timestamp (hour >= 16, or 15:45+),
    market reaction occurs on the *next* trading day (`d > earn_date`) and baseline
    is the close on `earn_date` (or prior trading day). Otherwise (BMO / date-only),
    Day 0 is `d >= earn_date` and baseline is the preceding trading day.
    """
    if not trading_days:
        return None, None, "BMO"
    earn_dt = earn_ts.date() if hasattr(earn_ts, "date") else earn_ts
    hour = getattr(earn_ts, "hour", 0)
    minute = getattr(earn_ts, "minute", 0)
    is_amc = (hour >= 16) or (hour == 15 and minute >= 45)
    session_label = "AMC" if is_amc else "BMO"

    if is_amc:
        post_days = [d for d in trading_days if d > earn_dt]
        if not post_days:
            return None, None, session_label
        day0 = post_days[0]
        day0_idx = list(trading_days).index(day0)
        base_day = trading_days[max(0, day0_idx - 1)]
        return day0, base_day, session_label

    post_days = [d for d in trading_days if d >= earn_dt]
    if not post_days:
        return None, None, session_label
    day0 = post_days[0]
    day0_idx = list(trading_days).index(day0)
    base_day = trading_days[max(0, day0_idx - 1)]
    return day0, base_day, session_label


def score_pead_candidate(
    *,
    eps_surprise_pct: Optional[float],
    day1_return_pct: Optional[float],
    volume_surge_ratio: Optional[float],
    trend_regime: str,
    days_since_earnings: int,
    sue_score: Optional[float] = None,
    revenue_growth_pct: Optional[float] = None,
    near_52w_high: Optional[float] = None,
) -> Tuple[int, str, List[str]]:
    """Compute conviction score (0-100), tier, and reasoning factors for PEAD."""
    score = 0
    reasons: List[str] = []

    # 1. Primary Driver: EPS Surprise Magnitude
    if eps_surprise_pct is not None:
        if eps_surprise_pct >= 25.0:
            tier = "HIGH"
            score += 40
            reasons.append(f"🔥 Çok Yüksek Kâr Sürprizi: Beklentinin +%{eps_surprise_pct:.1f} üzerinde (+40)")
        elif eps_surprise_pct >= 10.0:
            tier = "HIGH"
            score += 30
            reasons.append(f"🚀 Güçlü Kâr Sürprizi: Beklentinin +%{eps_surprise_pct:.1f} üzerinde (+30)")
        elif eps_surprise_pct >= 2.0:
            tier = "MEDIUM"
            score += 15
            reasons.append(f"📈 Pozitif Kâr Sürprizi: Beklentinin +%{eps_surprise_pct:.1f} üzerinde (+15)")
        elif eps_surprise_pct < 0.0:
            tier = "NEGATIVE"
            score -= 30
            reasons.append(f"⚠️ Negatif Kâr Sürprizi: Beklentinin %{abs(eps_surprise_pct):.1f} altında (-30)")
        else:
            tier = "LOW"
            score += 5
            reasons.append("Beklentiye paralel kâr (+5)")
    else:
        tier = "LOW"
        reasons.append("Sürpriz yüzdesi hesaplanamadı")

    # 2. Initial Day-1 Price Reaction
    if day1_return_pct is not None:
        if day1_return_pct >= 4.0:
            score += 20
            reasons.append(f"Güçlü Açıklama Günü Tepkisi: İlk gün +%{day1_return_pct:.1f} yükseliş (+20)")
        elif day1_return_pct >= 1.0:
            score += 15
            reasons.append(f"Pozitif Açıklama Günü Tepkisi: İlk gün +%{day1_return_pct:.1f} (+15)")
        elif day1_return_pct < -2.0:
            score -= 15
            reasons.append(f"Açıklama Günü Satış Baskısı: İlk gün %{day1_return_pct:.1f} ('Haber Satışı' / Zayıf Beklenti) (-15)")

    # 3. Volume Surge on Announcement
    if volume_surge_ratio is not None:
        if volume_surge_ratio >= 2.0:
            score += 15
            reasons.append(f"Kurumsal Hacim Patlaması: 20 günlük ortalama hacmin {volume_surge_ratio:.1f} katı (+15)")
        elif volume_surge_ratio >= 1.3:
            score += 10
            reasons.append(f"Yüksek Hacim Desteği: Ortalama hacmin {volume_surge_ratio:.1f} katı (+10)")

    # 4. Long-Term Trend Regime (SMA 200 / SMA 50)
    if trend_regime == "uptrend":
        score += 15
        reasons.append("Trend Onayı: Hisse 200 günlük hareketli ortalamasının üzerinde (+15)")
    elif trend_regime == "downtrend":
        score -= 15
        reasons.append("Düşüş Trendi: 200 günlük ortalama altında / tepki yükselişi riski (-15)")

    # 5. Drift Window Sweet Spot (Optimal PEAD entry is between 2 and 30 days)
    if 2 <= days_since_earnings <= 25:
        score += 10
        reasons.append(f"İdeal Sürüklenme Penceresi: Bilanço açıklanalı {days_since_earnings} gün oldu (+10)")
    elif days_since_earnings > 45:
        score -= 10
        reasons.append(f"Gecikmiş Pencere: Bilanço açıklanalı {days_since_earnings} gün oldu, sürüklenme zayıflamış olabilir (-10)")

    # 6. SUE & Revenue Growth Confirmation (Jegadeesh & Livnat 2006)
    if sue_score is not None and sue_score >= 2.0:
        score += 10
        reasons.append(f"Standartlaştırılmış SUE={sue_score:.1f} (>=2.0) güçlü istatistiksel sürpriz (+10)")
    if revenue_growth_pct is not None:
        if eps_surprise_pct is not None and eps_surprise_pct > 0 and revenue_growth_pct >= 10.0:
            score += 10
            reasons.append(f"Ciro Büyümesi Onayı: Yıllık +%{revenue_growth_pct:.1f} hasılat artışı (+10)")
        elif eps_surprise_pct is not None and eps_surprise_pct > 0 and revenue_growth_pct <= -5.0:
            score -= 10
            reasons.append(f"Ciro Daralması Uyarısı: Kâr sürprizine rağmen hasılat %{revenue_growth_pct:.1f} geriledi (-10)")

    # 7. 52-Week High Proximity (George & Hwang 2004)
    if near_52w_high is not None and near_52w_high >= 0.85:
        score += 5
        reasons.append(f"52 Hafta Zirve Yakınlığı ({near_52w_high:.2f}x) çapa etkisi (+5)")

    final_score = max(0, min(100, score))
    return final_score, tier, reasons


def evaluate_pead_for_symbol(
    symbol: str,
    *,
    today: Optional[date] = None,
    max_days: int = 45,
    min_score: int = 35,
    min_dollar_volume: float = 2_000_000.0,
    ticker_fetcher: Optional[Callable[[str], Any]] = None,
) -> Optional[PeadCandidate]:
    """Evaluate PEAD metrics for a single stock symbol using yfinance or provided fetcher."""
    ref_date = today or date.today()
    try:
        if ticker_fetcher:
            t = ticker_fetcher(symbol)
        else:
            import yfinance as yf
            t = yf.Ticker(symbol)

        # 1. Fetch recent earnings dates and surprises
        ed_df = t.get_earnings_dates(limit=12)
        if ed_df is None or ed_df.empty:
            return None

        # Collect all historical EPS surprises for SUE standardization + window filter
        all_eps_diffs: List[float] = []
        valid_earnings: List[Tuple[Any, date, float, float, float]] = []
        for idx_ts, row in ed_df.iterrows():
            rep = row.get("Reported EPS")
            est = row.get("EPS Estimate")
            surp = row.get("Surprise(%)")

            if pd.isna(rep):
                continue
            if est is not None and not pd.isna(est):
                all_eps_diffs.append(float(rep) - float(est))

            e_dt = idx_ts.date() if hasattr(idx_ts, "date") else idx_ts
            days_ago = (ref_date - e_dt).days
            if 0 <= days_ago <= max_days:
                surp_val = float(surp) if not pd.isna(surp) else (
                    round((float(rep) - float(est)) / abs(float(est)) * 100.0, 2)
                    if est and not pd.isna(est) and float(est) != 0 else 0.0
                )
                valid_earnings.append((idx_ts, e_dt, float(rep), float(est) if not pd.isna(est) else 0.0, surp_val))

        if not valid_earnings:
            return None

        # Most recent reported earnings within window
        valid_earnings.sort(key=lambda x: x[1], reverse=True)
        earn_ts, earn_date, rep_eps, est_eps, surp_pct = valid_earnings[0]
        days_since = (ref_date - earn_date).days

        # SUE = (Reported - Estimate) / std(historical EPS surprises)
        sue_score: Optional[float] = None
        if len(all_eps_diffs) >= 3:
            s = pd.Series(all_eps_diffs).std(ddof=1)
            if s and not pd.isna(s) and float(s) > 0:
                sue_score = round((rep_eps - est_eps) / max(float(s), 0.02), 2)

        # 2. Fetch price history around earnings date to measure reaction & drift
        start_hist = earn_date - timedelta(days=320)
        hist = t.history(start=start_hist.isoformat(), end=(ref_date + timedelta(days=2)).isoformat())
        if hist is None or len(hist) < 25:
            return None

        # Normalize index to date
        hist.index = [ts.date() if hasattr(ts, "date") else ts for ts in hist.index]
        trading_days = sorted(hist.index)

        day0, base_day, session_label = resolve_event_day0(earn_ts, trading_days)
        if day0 is None or base_day is None:
            return None
        day0_idx = trading_days.index(day0)

        base_price = float(hist.loc[base_day]["Close"])
        day0_close = float(hist.loc[day0]["Close"])
        latest_close = float(hist.loc[trading_days[-1]]["Close"])

        day1_return = round((day0_close / base_price - 1.0) * 100.0, 2) if base_price > 0 else 0.0
        total_drift = round((latest_close / day0_close - 1.0) * 100.0, 2) if day0_close > 0 else 0.0

        # Liquidity & Volume surge on Day 0 vs preceding 20-day average
        prior_vol_days = trading_days[max(0, day0_idx - 20): day0_idx]
        avg_dollar_volume: Optional[float] = None
        if prior_vol_days:
            prior_slice = hist.loc[prior_vol_days]
            avg_vol = float(prior_slice["Volume"].mean())
            avg_dollar_volume = float((prior_slice["Close"] * prior_slice["Volume"]).mean())
            day0_vol = float(hist.loc[day0]["Volume"])
            vol_ratio = round(day0_vol / avg_vol, 2) if avg_vol > 0 else 1.0
        else:
            vol_ratio = 1.0

        if min_dollar_volume > 0 and avg_dollar_volume is not None and avg_dollar_volume < min_dollar_volume:
            return None

        # 52-week high proximity (George & Hwang 2004)
        high_52w = float(hist["Close"].iloc[-252:].max()) if len(hist) > 0 else 0.0
        near_52w_high = round(latest_close / high_52w, 3) if high_52w > 0 else None

        # SMA 200 trend regime
        if len(trading_days) >= 200:
            sma200 = float(hist["Close"].iloc[-200:].mean())
            trend_regime = "uptrend" if latest_close > sma200 else "downtrend"
        elif len(trading_days) >= 50:
            sma50 = float(hist["Close"].iloc[-50:].mean())
            trend_regime = "uptrend" if latest_close > sma50 else "downtrend"
        else:
            trend_regime = "neutral"

        info = getattr(t, "info", None) or {}
        company_name = info.get("shortName") or symbol
        rev_growth_raw = info.get("revenueGrowth")
        revenue_growth_pct = round(float(rev_growth_raw) * 100.0, 2) if rev_growth_raw is not None else None

        # 3. Score candidate
        score, tier, reasons = score_pead_candidate(
            eps_surprise_pct=surp_pct,
            day1_return_pct=day1_return,
            volume_surge_ratio=vol_ratio,
            trend_regime=trend_regime,
            days_since_earnings=days_since,
            sue_score=sue_score,
            revenue_growth_pct=revenue_growth_pct,
            near_52w_high=near_52w_high,
        )

        if score < min_score:
            return None

        return PeadCandidate(
            symbol=symbol,
            company_name=company_name,
            earnings_date=earn_date.isoformat(),
            days_since_earnings=days_since,
            eps_estimate=round(est_eps, 2),
            eps_reported=round(rep_eps, 2),
            eps_surprise_pct=round(surp_pct, 2),
            sue_score=sue_score,
            revenue_growth_pct=revenue_growth_pct,
            near_52w_high=near_52w_high,
            avg_dollar_volume=round(avg_dollar_volume, 0) if avg_dollar_volume is not None else None,
            announcement_session=session_label,
            day1_return_pct=day1_return,
            total_drift_pct=total_drift,
            volume_surge_ratio=vol_ratio,
            trend_regime=trend_regime,
            conviction_tier=tier,
            score=score,
            reasons=reasons,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed evaluating PEAD for %s: %s", symbol, exc)
        return None


def screen_pead_candidates(
    symbols: Sequence[str],
    *,
    max_days: int = 40,
    min_score: int = 45,
    top_n: int = 10,
    max_workers: int = 8,
    today: Optional[date] = None,
) -> List[PeadCandidate]:
    """Scan a list of symbols in parallel for Post-Earnings Announcement Drift setups."""
    from concurrent.futures import ThreadPoolExecutor

    results: List[PeadCandidate] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(evaluate_pead_for_symbol, sym, today=today, max_days=max_days, min_score=min_score)
            for sym in symbols
        ]
        for f in futures:
            res = f.result()
            if res is not None:
                results.append(res)

    results.sort(key=lambda c: (c.score, c.eps_surprise_pct or 0.0), reverse=True)
    return results[:top_n]


def format_pead_report(candidates: List[PeadCandidate]) -> str:
    """Format scored PEAD candidates into an actionable Turkish terminal/Telegram report."""
    if not candidates:
        return (
            "📋 Bilanço Sonrası Sürüklenme (PEAD) Taraması\n"
            "----------------------------------------------\n"
            "Seçilen hisseler arasında kriterlere uygun kâr sürprizi ve sürüklenme adayı bulunamadı."
        )

    lines = [
        "📑 BİLANÇO SONRASI SÜRÜKLENME (PEAD) ANOMALİ TARAMASI",
        "======================================================",
        f"Tespit Edilen Güçlü Bilanço Sürüklenme Adayı: {len(candidates)}",
        "Akademik Kural: Yüksek EPS sürprizi + hacimli ilk gün tepkisi + trend onayı.",
        "",
    ]

    tier_icons = {
        "HIGH": "🔥 [YÜKSEK SÜRÜKLENME]",
        "MEDIUM": "🚀 [ORTA SÜRÜKLENME]",
        "LOW": "ℹ️ [ZAYIF]",
        "NEGATIVE": "⚠️ [NEGATİF SÜRPRİZ]",
    }

    for rank, c in enumerate(candidates, 1):
        icon = tier_icons.get(c.conviction_tier, "📈")
        lines.append(f"#{rank} {icon} {c.symbol} - {c.company_name} (Puan: {c.score}/100)")
        lines.append(f"   • Bilanço Tarihi: {c.earnings_date} ({c.days_since_earnings} gün önce)")
        surp_str = f"+%{c.eps_surprise_pct:.1f}" if c.eps_surprise_pct and c.eps_surprise_pct > 0 else f"%{c.eps_surprise_pct}"
        lines.append(f"   • EPS Sürprizi  : {surp_str} (Açıklanan: ${c.eps_reported:.2f} vs. Beklenti: ${c.eps_estimate:.2f})")
        lines.append(f"   • İlk Gün Tepki : %{c.day1_return_pct:+.2f} | Hacim Artışı: {c.volume_surge_ratio:.1f}x")
        lines.append(f"   • Açıklamadan Beri Toplam Sürüklenme: %{c.total_drift_pct:+.2f}")
        lines.append(f"   • Trend Durumu  : {'Yükseliş Trendi (SMA200 Üstü)' if c.trend_regime == 'uptrend' else 'Düşüş/Zayıf Trend'}")
        lines.append("   • Mahkûmiyet Faktörleri:")
        for r in c.reasons:
            lines.append(f"     - {r}")
        lines.append(f"   • Hızlı Analiz  : python main.py --stocks {c.symbol}")
        lines.append("")

    return "\n".join(lines).strip()
