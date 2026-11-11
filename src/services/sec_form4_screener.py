# -*- coding: utf-8 -*-
"""U.S. Corporate Insider Buying Daily Screener.

Ranks U.S. equities by executive insider buying signals (SEC Form 4):
1. **Cluster Buying** (>= 2 distinct officers/directors buying within 5 days).
2. **C-Suite Conviction** (CEO / CFO / COO / President / Chair buying).
3. **Opportunistic Timing** (Cohen-Malloy-Pomorski 2012 non-routine insiders + no 10b5-1 plan).
4. **Significant Dollar Commitment** (filtering out token purchases).

Can feed candidates directly into ``python main.py --stocks TICKER1,TICKER2``
for deep technical, news, and debate analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from data_provider.sec_form4_fetcher import (
    InsiderClusterEvent,
    SecForm4Fetcher,
    resolve_sec_user_agent,
)

logger = logging.getLogger(__name__)


@dataclass
class ScoredInsiderCandidate:
    """U.S. stock candidate scored by insider conviction."""

    symbol: str
    company_name: str
    filing_date_str: str
    total_value: float
    total_shares: float
    avg_price: float
    insider_count: int
    has_c_level: bool
    is_opportunistic: bool
    is_cluster: bool
    score: int
    reasons: List[str]
    primary_titles: List[str]
    sec_edgar_url: str = ""
    cmp_class: str = "unclassified"
    has_10b51: bool = False
    holding_change_pct: Optional[float] = None
    trend_regime: str = "unclassified"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "filing_date": self.filing_date_str,
            "total_value": self.total_value,
            "total_shares": self.total_shares,
            "avg_price": self.avg_price,
            "insider_count": self.insider_count,
            "has_c_level": self.has_c_level,
            "is_opportunistic": self.is_opportunistic,
            "is_cluster": self.is_cluster,
            "score": self.score,
            "reasons": self.reasons,
            "primary_titles": self.primary_titles,
            "sec_edgar_url": self.sec_edgar_url,
            "cmp_class": self.cmp_class,
            "has_10b51": self.has_10b51,
            "holding_change_pct": self.holding_change_pct,
            "trend_regime": self.trend_regime,
        }


def score_insider_event(event: InsiderClusterEvent) -> Tuple[int, List[str]]:
    """Score an insider cluster event based on empirical alpha drivers (0 to 100)."""
    score = 0
    reasons: List[str] = []

    # 1. Cluster buying by officers/directors (strongest documented empirical alpha driver)
    if event.is_cluster:
        cnt = event.officer_director_count or event.insider_count
        score += 35
        reasons.append(f"Küme Alımı: {cnt} farklı yönetici eşzamanlı aldı (+35)")
    else:
        score += 10
        reasons.append("Tek yönetici alımı (+10)")

    # 2. C-Suite conviction (CEO / CFO / COO / President / Chair)
    if event.has_c_level:
        score += 25
        reasons.append("C-Suite / Üst Yönetim (CEO / CFO / Başkan) şahsi alımı (+25)")

    # 3. Cohen-Malloy-Pomorski opportunistic vs routine pattern
    if event.cmp_class == "opportunistic":
        score += 20
        reasons.append("CMP: Fırsatçı alım (geçmişte rutin takvim kalıbı yok) (+20)")
    elif event.cmp_class == "routine":
        score -= 20
        reasons.append("CMP: Rutin takvim alımı (-20)")
    else:
        # Unclassified history: fall back to 10b5-1 flag
        if not event.has_10b51:
            score += 15
            reasons.append("Fırsatçı alım (10b5-1 otomatik plan yok) (+15)")

    # 4. Pre-planned Rule 10b5-1 check
    if event.has_10b51:
        score -= 10
        reasons.append("Önceden planlanmış 10b5-1 programı (-10)")

    # 5. Institutional 10% owners only penalty (hedge funds / PE filing 10% form 4)
    if event.ten_pct_only:
        score -= 10
        reasons.append("Yalnızca %10 pay sahibi alımı (-10)")

    # 6. Dollar commitment scale
    val = event.total_value
    if val >= 500_000:
        score += 20
        reasons.append(f"Büyük tutarlı taahhüt: ${val:,.0f} (+20)")
    elif val >= 100_000:
        score += 15
        reasons.append(f"Önemli tutar: ${val:,.0f} (+15)")
    elif val >= 50_000:
        score += 10
        reasons.append(f"Tutar: ${val:,.0f} (+10)")
    else:
        score += 5

    # 7. Significant increase in holdings
    if event.holding_change_pct is not None and event.holding_change_pct >= 20.0:
        score += 10
        reasons.append(f"Mevcut pozisyonda belirgin artış: +%{event.holding_change_pct:.0f} (+10)")

    # 8. Trend / Momentum confirmation (protect against falling knives)
    if event.trend_regime == "uptrend":
        score += 20
        reasons.append("Trend Onayı: 200 günlük ortalama üzerinde / yükseliş trendinde (+20)")
    elif event.trend_regime == "downtrend":
        score -= 20
        reasons.append("Düşüş Trendi: 200 günlük ortalama altında / değer tuzağı riski (-20)")

    final_score = max(0, min(100, score))
    return final_score, reasons


def screen_us_insider_stocks(
    events: Iterable[InsiderClusterEvent],
    *,
    min_score: int = 40,
    top_n: int = 10,
    min_value: float = 30_000.0,
) -> List[ScoredInsiderCandidate]:
    """Score and rank U.S. stocks with recent executive insider purchases."""
    candidates: List[ScoredInsiderCandidate] = []
    seen_symbols = set()

    # Sort newest first, then largest value
    sorted_events = sorted(events, key=lambda e: (e.filing_date, e.total_value), reverse=True)

    for e in sorted_events:
        if e.total_value < min_value:
            continue
        if e.symbol in seen_symbols:
            continue

        score, reasons = score_insider_event(e)
        if score < min_score:
            continue

        edgar_url = e.sec_url or f"https://www.sec.gov/edgar/browse/?CIK={e.symbol}"
        candidates.append(ScoredInsiderCandidate(
            symbol=e.symbol,
            company_name=e.company_name,
            filing_date_str=e.filing_date.isoformat(),
            total_value=e.total_value,
            total_shares=e.total_shares,
            avg_price=e.avg_price,
            insider_count=e.insider_count,
            has_c_level=e.has_c_level,
            is_opportunistic=e.is_opportunistic or (not e.has_10b51 and e.cmp_class != "routine"),
            is_cluster=e.is_cluster,
            score=score,
            reasons=reasons,
            primary_titles=e.primary_titles,
            sec_edgar_url=edgar_url,
            cmp_class=e.cmp_class,
            has_10b51=e.has_10b51,
            holding_change_pct=e.holding_change_pct,
            trend_regime=e.trend_regime,
        ))
        seen_symbols.add(e.symbol)
        if len(candidates) >= top_n * 2:
            break

    candidates.sort(key=lambda c: (-c.score, -c.total_value))
    return candidates[: max(1, int(top_n))]


def format_sec_screener_report(candidates: Sequence[ScoredInsiderCandidate]) -> str:
    """Format scored U.S. insider candidates into Turkish summary text."""
    lines = [
        "🇺🇸 ABD Yönetici Alımları (SEC Form 4) Günlük Taraması",
        "=" * 66,
        f"Seçilen Aday Sayısı: {len(candidates)} hisse (En yüksek içsel bilgi ve küme alım puanı)",
        "Filtreler: Açık piyasa alımı ('P'), halka arz/tahsisli hariç, C-Suite ve küme alımları öncelikli.",
        "",
    ]
    if not candidates:
        lines.append("Belirtilen kriterlere uygun yönetici alım adayı bulunamadı.")
        return "\n".join(lines)

    for idx, c in enumerate(candidates, start=1):
        lines.append(f"{idx}. {c.symbol} ({c.company_name}) — Puan: {c.score}/100")
        lines.append(
            f"   Tutar: ${c.total_value:,.0f} ({c.total_shares:,.0f} adet @ ${c.avg_price:.2f}) | "
            f"Yönetici: {c.insider_count} kişi ({', '.join(c.primary_titles[:2]) or 'Yönetim'})"
        )
        lines.append(f"   Tarih: {c.filing_date_str} | EDGAR: {c.sec_edgar_url}")
        lines.append(f"   Nedenler: {'; '.join(c.reasons[:2])}")
        lines.append("")

    codes = ",".join(c.symbol for c in candidates)
    lines.append(f"Analiz komutu: python main.py --stocks {codes}")
    return "\n".join(lines)


__all__ = [
    "ScoredInsiderCandidate",
    "format_sec_screener_report",
    "score_insider_event",
    "screen_us_insider_stocks",
]
