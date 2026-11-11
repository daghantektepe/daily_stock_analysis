# -*- coding: utf-8 -*-
"""KAP Contract Screener — Borsa Istanbul New Business Relation (Sözleşme) Anomaly Detector.

Detects high-conviction revenue catalysts from BIST companies announcing contracts,
orders, or tenders on the Public Disclosure Platform (KAP).

In Turkish equities, contract value relative to Trailing 12-Month (TTM) Revenue
(Sözleşme Tutarı / Hasılat Oranı) is one of the strongest fundamental price catalysts.
When a contract represents >= 25% (or >= 50%) of annual revenue, it produces substantial
abnormal multi-day returns and momentum.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from data_provider.kap_fetcher import KapDisclosureFetcher
from data_provider.realtime_types import CircuitBreaker

logger = logging.getLogger(__name__)

# Typical exchange rates fallback if live FX is unavailable
_DEFAULT_FX = {
    "USD": 38.0,
    "EUR": 40.0,
    "GBP": 48.0,
    "TRY": 1.0,
}

_CONTRACT_SUBJECT_RE = re.compile(
    r"(yeni iş ilişkisi|sözleşme|ihale|sipariş|siparis|is iliskisi|iş bağlantısı)",
    re.IGNORECASE,
)

_PRESTIGIOUS_COUNTERPARTIES = re.compile(
    r"(savunma sanayii|ssb|tusaş|aselsan|roketsan|havelsan|nato|bakanlık|bakanligi|"
    r"tcdd|türksat|turksat|yurt dışı|ihracat|yabancı|abone|kurum|avrupa birliği)",
    re.IGNORECASE,
)


@dataclass
class KapContractCandidate:
    """A scored BIST contract disclosure candidate."""

    symbol: str
    ticker: str
    company_name: str
    disclosure_index: int
    published_date: str
    title: str
    contract_amount: Optional[float]
    contract_currency: Optional[str]
    contract_amount_try: Optional[float]
    ttm_revenue_try: Optional[float]
    contract_to_revenue_pct: Optional[float]
    conviction_tier: str  # MEGA | STRONG | MODERATE | MINOR | UNCLASSIFIED
    score: int  # 0 to 100
    reasons: List[str]
    url: str
    counterparty: Optional[str] = None
    details_condensed: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "disclosure_index": self.disclosure_index,
            "published_date": self.published_date,
            "title": self.title,
            "contract_amount": self.contract_amount,
            "contract_currency": self.contract_currency,
            "contract_amount_try": self.contract_amount_try,
            "ttm_revenue_try": self.ttm_revenue_try,
            "contract_to_revenue_pct": self.contract_to_revenue_pct,
            "conviction_tier": self.conviction_tier,
            "score": self.score,
            "reasons": self.reasons,
            "url": self.url,
            "counterparty": self.counterparty,
            "details_condensed": self.details_condensed,
        }


def parse_contract_revenue_ratio(text: str) -> Optional[float]:
    """Extract explicit contract-to-revenue percentage from KAP disclosure text."""
    if not text:
        return None
    # 1. "hasılatına oranı: % 34,8" or "ciroya oranı %25"
    m = re.search(
        r"(?:has[ıi]lat|gelir|ciro)[a-zçğıöşü]*\s*oran[ıi](?:\s*\(%\))?\s*[:\s=]+%?\s*(\d+[.,]?\d*)",
        text,
        re.IGNORECASE,
    )
    if not m:
        # 2. "oranı: % 25,4"
        m = re.search(r"oran[ıi]\s*[:\s=]*%?\s*(\d+[.,]?\d*)\s*%", text, re.IGNORECASE)
    if not m:
        # 3. "% 35'lik hasılat payı"
        m = re.search(r"%\s*(\d+[.,]?\d*)\s*(?:'|\s|d)[a-z]*\s*(?:oran|has[ıi]lat|ciro)", text, re.IGNORECASE)

    if m:
        raw_val = m.group(1).replace(",", ".")
        try:
            val = float(raw_val)
            if 0.1 <= val <= 5000.0:
                return round(val, 2)
        except ValueError:
            return None
    return None


def parse_contract_amount(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Extract numeric contract amount and currency (TRY, USD, EUR) from disclosure text."""
    if not text:
        return None, None
    # Matches: 45.000.000 USD, 120,500,000 TL, 8.500.000 EUR
    m = re.search(
        r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(TL|TRY|USD|EUR|Avro|Euro|Dolar|ABD Doları)",
        text,
        re.IGNORECASE,
    )
    if not m:
        # Match "milyon TL/USD/EUR" format (e.g. 50 milyon TL, 12.5 milyon USD)
        m_mil = re.search(
            r"(\d+[.,]?\d*)\s*milyon\s*(TL|TRY|USD|EUR|Avro|Euro|Dolar)",
            text,
            re.IGNORECASE,
        )
        if m_mil:
            raw_num = m_mil.group(1).replace(",", ".")
            curr = m_mil.group(2).upper()
            try:
                amt = float(raw_num) * 1_000_000.0
                curr = _normalize_currency(curr)
                return amt, curr
            except ValueError:
                return None, None
        return None, None

    raw_amt = m.group(1).replace(".", "").replace(",", ".")
    curr = _normalize_currency(m.group(2))
    try:
        amt = float(raw_amt)
        return amt, curr
    except ValueError:
        return None, None


def _normalize_currency(curr_raw: str) -> str:
    c = curr_raw.upper().strip()
    if c in ("AVRO", "EURO"):
        return "EUR"
    if c in ("DOLAR", "ABD DOLARI", "ABD DOLAR"):
        return "USD"
    if c in ("TL", "TRY", "TÜRK LİRASI", "TURK LIRASI"):
        return "TRY"
    return c


def extract_counterparty(text: str) -> Optional[str]:
    """Extract customer / counterparty name if present in structured fields."""
    if not text:
        return None
    m = re.search(r"Karşı Taraf[a-zçğıöşü\s]*:\s*([^|\n]+)", text, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        if len(name) > 3 and name.lower() not in ("-", "yok", "belirtilmedi"):
            return name[:120]
    return None


def score_contract_candidate(
    *,
    contract_amount_try: Optional[float],
    ratio_pct: Optional[float],
    counterparty: Optional[str] = None,
    text: str = "",
) -> Tuple[int, str, List[str]]:
    """Compute conviction score (0-100), tier, and reasoning factors."""
    score = 0
    reasons: List[str] = []

    # 1. Primary Driver: Contract Value / Annual Revenue Ratio
    if ratio_pct is not None:
        if ratio_pct >= 50.0:
            tier = "MEGA"
            score += 55
            reasons.append(f"🔥 Oyun Değiştirici Hasılat Oranı: Sözleşme yıllık cironun %{ratio_pct:.1f}'si büyüklüğünde (+55)")
        elif ratio_pct >= 25.0:
            tier = "STRONG"
            score += 40
            reasons.append(f"🚀 Yüksek Gelir Katalizörü: Sözleşme yıllık cironun %{ratio_pct:.1f}'si büyüklüğünde (+40)")
        elif ratio_pct >= 10.0:
            tier = "MODERATE"
            score += 25
            reasons.append(f"📈 Kayda Değer Sözleşme: Sözleşme yıllık cironun %{ratio_pct:.1f}'si (+25)")
        else:
            tier = "MINOR"
            score += 10
            reasons.append(f"ℹ️ Küçük/Rutin Sözleşme: Sözleşme yıllık cironun %{ratio_pct:.1f}'si (+10)")
    else:
        tier = "UNCLASSIFIED"
        score += 15
        reasons.append("Sözleşme hasılat oranı metinde belirtilmemiş (+15)")

    # 2. Absolute Size Scale (in TRY)
    if contract_amount_try is not None:
        if contract_amount_try >= 1_000_000_000.0:
            score += 25
            reasons.append(f"Devasa Nominal Tutar: {contract_amount_try / 1_000_000:,.1f} Milyon TL (+25)")
        elif contract_amount_try >= 250_000_000.0:
            score += 20
            reasons.append(f"Çok Büyük Tutar: {contract_amount_try / 1_000_000:,.1f} Milyon TL (+20)")
        elif contract_amount_try >= 50_000_000.0:
            score += 15
            reasons.append(f"Önemli Tutar: {contract_amount_try / 1_000_000:,.1f} Milyon TL (+15)")
        elif contract_amount_try >= 10_000_000.0:
            score += 10
            reasons.append(f"Nominal Tutar: {contract_amount_try / 1_000_000:,.1f} Milyon TL (+10)")
        else:
            score += 5

    # 3. High-Profile Counterparty Bonus
    check_text = f"{counterparty or ''} {text}"
    if _PRESTIGIOUS_COUNTERPARTIES.search(check_text):
        score += 10
        reasons.append("Kurumsal / Prestijli Müşteri veya İhracat Sözleşmesi (Savunma Sanayii / Yurt Dışı / Kamu) (+10)")

    final_score = max(0, min(100, score))
    return final_score, tier, reasons


class KapContractScreener:
    """Screens BIST companies for high-conviction contract and business relationship catalysts."""

    def __init__(
        self,
        kap_fetcher: Optional[KapDisclosureFetcher] = None,
        revenue_provider: Optional[Callable[[str], Optional[float]]] = None,
        fx_rates: Optional[Dict[str, float]] = None,
    ) -> None:
        self.fetcher = kap_fetcher or KapDisclosureFetcher()
        self.revenue_provider = revenue_provider
        self.fx_rates = fx_rates or dict(_DEFAULT_FX)

    def scan_recent_contracts(
        self,
        *,
        days: int = 5,
        min_score: int = 40,
        top_n: int = 15,
        target_tickers: Optional[Iterable[str]] = None,
    ) -> List[KapContractCandidate]:
        """Scan recent KAP filings across BIST for new contracts and score conviction."""
        grouped = self.fetcher.get_market_disclosures(days=days)
        candidates: List[KapContractCandidate] = []

        if target_tickers:
            norm_targets = {t.upper().replace(".IS", "") for t in target_tickers}
        else:
            norm_targets = None

        for symbol, items in grouped.items():
            ticker = symbol.replace(".IS", "")
            if norm_targets and ticker not in norm_targets:
                continue

            for item in items:
                subject = item.get("subject", "")
                title = item.get("title", "")
                tags = item.get("tags", [])

                # Filter for contract related disclosures
                is_contract = (
                    "contract" in tags
                    or _CONTRACT_SUBJECT_RE.search(subject)
                    or _CONTRACT_SUBJECT_RE.search(title)
                )
                if not is_contract:
                    continue

                idx = item.get("index")
                details = self.fetcher.get_disclosure_details(idx) if idx else ""
                full_text = f"{title} | {subject} | {details}"

                amount, currency = parse_contract_amount(full_text)
                ratio_pct = parse_contract_revenue_ratio(full_text)
                counterparty = extract_counterparty(full_text)

                # Compute TRY amount
                amount_try = None
                if amount is not None and currency:
                    fx = self.fx_rates.get(currency, 1.0)
                    amount_try = round(amount * fx, 2)

                # If ratio is missing but we have amount_try and a revenue provider, calculate it
                ttm_rev = None
                if ratio_pct is None and amount_try and self.revenue_provider:
                    try:
                        ttm_rev = self.revenue_provider(symbol)
                        if ttm_rev and ttm_rev > 0:
                            ratio_pct = round((amount_try / ttm_rev) * 100.0, 2)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Revenue provider lookup failed for %s: %s", symbol, exc)

                score, tier, reasons = score_contract_candidate(
                    contract_amount_try=amount_try,
                    ratio_pct=ratio_pct,
                    counterparty=counterparty,
                    text=full_text,
                )

                if score >= min_score:
                    candidates.append(
                        KapContractCandidate(
                            symbol=symbol,
                            ticker=ticker,
                            company_name=item.get("publisher") or ticker,
                            disclosure_index=idx,
                            published_date=item.get("published_date") or "",
                            title=title,
                            contract_amount=amount,
                            contract_currency=currency,
                            contract_amount_try=amount_try,
                            ttm_revenue_try=ttm_rev,
                            contract_to_revenue_pct=ratio_pct,
                            conviction_tier=tier,
                            score=score,
                            reasons=reasons,
                            url=item.get("url") or "",
                            counterparty=counterparty,
                            details_condensed=details[:300] if details else title,
                        )
                    )

        # Sort by score descending, then newest published date
        candidates.sort(key=lambda c: (c.score, c.contract_to_revenue_pct or 0.0), reverse=True)
        return candidates[:top_n]


def format_kap_contract_report(candidates: List[KapContractCandidate]) -> str:
    """Format scored contract candidates into an actionable Turkish terminal/Telegram report."""
    if not candidates:
        return (
            "📋 Borsa İstanbul KAP Yeni İş İlişkisi / Sözleşme Taraması\n"
            "----------------------------------------------------------\n"
            "Seçilen kriterlere ve eşik puanına uygun yeni sözleşme bildirimi bulunamadı."
        )

    lines = [
        "📑 BORSA İSTANBUL KAP YENİ İŞ İLİŞKİSİ VE SÖZLEŞME ANOMALİ TARAMASI",
        "==================================================================",
        f"Tespit Edilen Yüksek Hasılat Katalizörü Sayısı: {len(candidates)}",
        "Kriter: Sözleşme büyüklüğü, yıllık hasılata oranı ve kurumsal müşteri gücü.",
        "",
    ]

    for rank, c in enumerate(candidates, 1):
        tier_icons = {
            "MEGA": "🔥 [MEGA KATALİZÖR]",
            "STRONG": "🚀 [GÜÇLÜ KATALİZÖR]",
            "MODERATE": "📈 [KAYDA DEĞER]",
            "MINOR": "ℹ️ [RUTİN]",
            "UNCLASSIFIED": "📋 [BİLDİRİM]",
        }
        icon = tier_icons.get(c.conviction_tier, "📋")

        lines.append(f"#{rank} {icon} {c.symbol} - {c.company_name} (Puan: {c.score}/100)")
        lines.append(f"   • Bildirim Tarihi: {c.published_date} | Başlık: {c.title}")

        amt_str = f"{c.contract_amount:,.0f} {c.contract_currency}" if c.contract_amount else "Belirtilmedi"
        if c.contract_amount_try and c.contract_currency != "TRY":
            amt_str += f" (~{c.contract_amount_try / 1_000_000:,.1f} Milyon TL)"
        lines.append(f"   • Sözleşme Tutarı: {amt_str}")

        if c.contract_to_revenue_pct is not None:
            lines.append(f"   • Hasılat Oranı  : %{c.contract_to_revenue_pct:.1f} (Yıllık Ciroya Oranı)")
        if c.counterparty:
            lines.append(f"   • Karşı Taraf    : {c.counterparty}")

        lines.append("   • Katalizör Nedenleri:")
        for r in c.reasons:
            lines.append(f"     - {r}")
        lines.append(f"   • KAP Linki      : {c.url}")
        lines.append(f"   • Hızlı Analiz   : python main.py --stocks {c.symbol}")
        lines.append("")

    return "\n".join(lines).strip()
