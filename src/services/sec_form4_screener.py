# -*- coding: utf-8 -*-
"""U.S. Corporate Insider Buying Daily Screener.

Ranks U.S. equities by executive insider buying signals (SEC Form 4):
1. **Cluster Buying** (>= 2 distinct insiders buying within 5 days).
2. **C-Suite Conviction** (CEO / CFO / COO buying with personal capital).
3. **Opportunistic Timing** (excluding Rule 10b5-1 automated recurring programs).
4. **Significant Dollar Commitment** (filtering out token purchases).

Can feed candidates directly into ``python main.py --stocks TICKER1,TICKER2``
for deep technical, news, and debate analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from data_provider.sec_form4_fetcher import InsiderClusterEvent, SecForm4Fetcher

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
        }


def score_insider_event(event: InsiderClusterEvent) -> Tuple[int, List[str]]:
    """Score an insider cluster event based on empirical alpha drivers (0 to 100)."""
    score = 0
    reasons: List[str] = []

    # 1. Cluster buying (strongest predictive signal)
    if event.is_cluster:
        score += 35
        reasons.append(f"Küme Alımı: {event.insider_count} farklı yönetici eşzamanlı aldı (+35)")
    else:
        score += 10
        reasons.append("Tek yönetici alımı (+10)")

    # 2. C-Suite conviction
    if event.has_c_level:
        score += 25
        reasons.append("C-Suite / Üst Yönetim (CEO / CFO / Başkan) şahsi alımı (+25)")

    # 3. Opportunistic vs. 10b5-1 program
    if event.is_opportunistic:
        score += 20
        reasons.append("Fırsatçı alım (10b5-1 otomatik plan yok) (+20)")
    else:
        score -= 10
        reasons.append("Önceden planlanmış 10b5-1 rutin programı (-10)")

    # 4. Dollar commitment scale
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

        edgar_url = f"https://www.sec.gov/edgar/browse/?CIK={e.symbol}"
        candidates.append(ScoredInsiderCandidate(
            symbol=e.symbol,
            company_name=e.company_name,
            filing_date_str=e.filing_date.isoformat(),
            total_value=e.total_value,
            total_shares=e.total_shares,
            avg_price=e.avg_price,
            insider_count=e.insider_count,
            has_c_level=e.has_c_level,
            is_opportunistic=e.is_opportunistic,
            is_cluster=e.is_cluster,
            score=score,
            reasons=reasons,
            primary_titles=e.primary_titles,
            sec_edgar_url=edgar_url,
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
        "Filtreler: Açık piyasa alımı ('P'), fırsatçı (10b5-1 yok), C-Suite ve küme alımları öncelikli.",
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
