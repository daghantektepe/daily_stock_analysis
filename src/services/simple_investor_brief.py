# -*- coding: utf-8 -*-
"""Plain-Turkish beginner investor brief service ("Basit Mod / Bugün Ne Yapayım?").

Translates the verified quantitative engines (PAA v2, Meta-Portfolio A v2,
Meta-Portfolio B v2, Strategy Research v3 winner `v3_trp`, and Forward
Validation Gate) into calm, jargon-free guidance with Turkish Bank/TEFAS &
Midas equivalents. Strictly read-only & zero slow network calls.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_TOURNAMENT_JSON = Path("data") / "quant_cache" / "tournament_latest.json"
DEFAULT_RESEARCH_V3_JSON = Path("data") / "quant_cache" / "research_v3_latest.json"
DEFAULT_FORWARD_JSON = Path("data") / "strategy_paper" / "forward_validation.json"
DEFAULT_BOOK_DIR = Path("data") / "strategy_paper"

PLAIN_ASSET_CATALOG: Dict[str, Dict[str, str]] = {
    "BIL": {
        "plain_name": "ABD Kısa Vadeli Hazine Bonosu (Dolar Nakit)",
        "role": "Fırtınalı günlerde parayı değer kaybından koruyup kısa vadeli dolar faizi üreten en güvenli liman.",
        "risk_level": "çok düşük",
        "tr_equivalent": "TEFAS Para Piyasası Fonu (PPF) / Kısa Vadeli Döviz-Borçlanma Fonu",
        "midas_hint": "Midas → ABD Borsaları → BIL (veya banka uygulamasından TEFAS Para Piyasası Fonu)",
    },
    "SHY": {
        "plain_name": "ABD 1–3 Yıllık Devlet Tahvili",
        "role": "Düşük dalgalı kısa vadeli devlet tahvili; faiz düşüşlerinde küçük ek koruma sağlar.",
        "risk_level": "çok düşük",
        "tr_equivalent": "TEFAS Kısa Vadeli Borçlanma Araçları / Eurobond Fonu",
        "midas_hint": "Midas → ABD Borsaları → SHY (veya TEFAS Kısa Vadeli Tahvil Fonu)",
    },
    "UUP": {
        "plain_name": "ABD Doları Endeksi (Dolar Gücü)",
        "role": "Borsalar ve tahviller birlikte düşerken dolar güçlendiğinde portföyü dengeleyen kalkan.",
        "risk_level": "düşük",
        "tr_equivalent": "Döviz (USD) / TEFAS Dolar Cinsi Serbest veya Eurobond Fonu",
        "midas_hint": "Midas → ABD Borsaları → UUP (veya banka uygulamasında USD / Eurobond Fonu)",
    },
    "GLD": {
        "plain_name": "Fiziki Altın ETF'i",
        "role": "Enflasyon ve jeopolitik belirsizlik dönemlerinde uzun vadeli değer koruyucu.",
        "risk_level": "orta",
        "tr_equivalent": "TEFAS Altın Fonu veya Banka Gram Altın",
        "midas_hint": "Midas → ABD Borsaları → GLD (veya TEFAS Altın Fonu / Gram Altın)",
    },
    "SPY": {
        "plain_name": "ABD En Büyük 500 Şirketi (S&P 500)",
        "role": "Piyasalar güneşliyken uzun vadeli büyüme motoru (Apple, Microsoft, Amazon vb. tek sepette).",
        "risk_level": "orta-yüksek",
        "tr_equivalent": "TEFAS Amerikan Hisse Senedi / S&P 500 Fonu",
        "midas_hint": "Midas → ABD Borsaları → SPY / VOO (veya TEFAS Yabancı Hisse Fonu)",
    },
    "QQQ": {
        "plain_name": "ABD Teknoloji Liderleri (Nasdaq-100)",
        "role": "Güçlü yükseliş dönemlerinde hızlı büyüme sağlayan teknoloji odaklı sepet.",
        "risk_level": "yüksek",
        "tr_equivalent": "TEFAS Teknoloji / Nasdaq Yabancı Hisse Fonu",
        "midas_hint": "Midas → ABD Borsaları → QQQ (veya TEFAS Teknoloji Hisse Fonu)",
    },
    "IEF": {
        "plain_name": "ABD 7–10 Yıllık Devlet Tahvili",
        "role": "Orta vadeli devlet tahvili; durgunluk dönemlerinde hisselere karşı denge kurar.",
        "risk_level": "düşük-orta",
        "tr_equivalent": "TEFAS Orta-Uzun Vadeli Borçlanma / Eurobond Fonu",
        "midas_hint": "Midas → ABD Borsaları → IEF",
    },
    "TLT": {
        "plain_name": "ABD 20+ Yıllık Devlet Tahvili",
        "role": "Uzun vadeli tahvil; faizler sert düştüğünde yüksek getiri potansiyeli sunar ancak dalgalıdır.",
        "risk_level": "orta",
        "tr_equivalent": "TEFAS Uzun Vadeli Eurobond Fonu",
        "midas_hint": "Midas → ABD Borsaları → TLT",
    },
    "DBC": {
        "plain_name": "Geniş Emtia Sepeti (Enerji, Metal, Tarım)",
        "role": "Enflasyon ve emtia yükselişlerinde hisselere alternatif koruma sağlar.",
        "risk_level": "orta-yüksek",
        "tr_equivalent": "TEFAS Emtia Sepeti Fonu",
        "midas_hint": "Midas → ABD Borsaları → DBC (veya TEFAS Emtia Fonu)",
    },
    "CASH": {
        "plain_name": "Nakit Bekleme (Kripto / İşlem Dışı)",
        "role": "Kripto trendi bozukken düşüşten tam korunmak için nakitte bekleme payı.",
        "risk_level": "çok düşük",
        "tr_equivalent": "TEFAS Para Piyasası Fonu (PPF) / Vadeli TL veya USDT",
        "midas_hint": "Kripto almadan nakitte / Para Piyasası Fonunda beklet",
    },
    "BTC-USD": {
        "plain_name": "Bitcoin (Trend Kalkanlı)",
        "role": "Yalnızca uzun vadeli yükseliş trendi netken sınırlı payla katılınan yüksek riskli uydu varlık.",
        "risk_level": "yüksek",
        "tr_equivalent": "Binance TR / Midas Kripto → BTC",
        "midas_hint": "Yalnızca trend pozitifken Binance TR / Midas Kripto üzerinden BTC",
    },
    "ETH-USD": {
        "plain_name": "Ethereum (Trend Kalkanlı)",
        "role": "Yalnızca yükseliş trendinde tutulan yüksek dalgalı kripto uydu varlığı.",
        "risk_level": "yüksek",
        "tr_equivalent": "Binance TR / Midas Kripto → ETH",
        "midas_hint": "Yalnızca trend pozitifken Binance TR / Midas Kripto üzerinden ETH",
    },
}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _asset_item(symbol: str, weight_pct: float) -> Dict[str, Any]:
    sym = str(symbol or "CASH").upper()
    meta = PLAIN_ASSET_CATALOG.get(
        sym,
        {
            "plain_name": f"{sym} Borsa Yatırım Fonu / Varlığı",
            "role": "Trend filtresini geçen çeşitlendirme varlığı.",
            "risk_level": "orta",
            "tr_equivalent": f"Midas ABD / BIST üzerinden {sym}",
            "midas_hint": f"Midas uygulamasında {sym} koduyla ara",
        },
    )
    return {
        "symbol": sym,
        "weight_pct": round(float(weight_pct), 1),
        "plain_name": meta["plain_name"],
        "role": meta["role"],
        "risk_level": meta["risk_level"],
        "tr_equivalent": meta["tr_equivalent"],
        "midas_hint": meta["midas_hint"],
    }


def _normalize_weights_pct(raw: Dict[str, Any], cash_pct: float = 0.0) -> List[Dict[str, Any]]:
    cleaned: Dict[str, float] = {}
    for sym, val in (raw or {}).items():
        try:
            w = float(val)
        except (TypeError, ValueError):
            continue
        if w > 0.05:
            cleaned[str(sym).upper()] = cleaned.get(str(sym).upper(), 0.0) + w
    if cash_pct > 0.05:
        cleaned["CASH"] = cleaned.get("CASH", 0.0) + float(cash_pct)
    total = sum(cleaned.values())
    if total <= 0:
        cleaned = {"BIL": 100.0}
        total = 100.0
    items = [
        _asset_item(sym, (w / total) * 100.0)
        for sym, w in sorted(cleaned.items(), key=lambda kv: kv[1], reverse=True)
    ]
    # Keep rounding exact to 100.0%
    diff = round(100.0 - sum(i["weight_pct"] for i in items), 1)
    if items and abs(diff) > 0:
        items[0]["weight_pct"] = round(max(0.0, items[0]["weight_pct"] + diff), 1)
    return items


def _blend_weights_50_50(w_a: Dict[str, float], w_b: Dict[str, float]) -> Dict[str, float]:
    merged: Dict[str, float] = {}
    for sym, val in (w_a or {}).items():
        merged[str(sym).upper()] = merged.get(str(sym).upper(), 0.0) + 0.5 * float(val)
    for sym, val in (w_b or {}).items():
        merged[str(sym).upper()] = merged.get(str(sym).upper(), 0.0) + 0.5 * float(val)
    return merged


def _safe_weight_share(weights: Dict[str, Any]) -> float:
    safe_syms = {"BIL", "SHY", "IEF", "UUP", "CASH"}
    total = sum(float(v) for v in (weights or {}).values() if v)
    if total <= 0:
        return 100.0
    safe_sum = sum(float(v) for k, v in (weights or {}).items() if str(k).upper() in safe_syms and v)
    return round((safe_sum / total) * 100.0, 1)


def _load_paper_exam_items(book_dir: Path, forward_path: Path) -> List[Dict[str, Any]]:
    fwd = _read_json(forward_path)
    strategies = fwd.get("strategies") or {}
    label_map = {
        "paa": "PAA Çöküş Kalkanı",
        "meta_a": "Dengeli Şampiyon (Meta-A v2)",
        "v3_trp": "Çok Temkinli Kalkan (v3 Risk Paritesi)",
    }
    book_files = {
        "paa": book_dir / "quant_paa.json",
        "meta_a": book_dir / "quant_meta_a.json",
        "v3_trp": book_dir / "quant_v3_trp.json",
    }
    out: List[Dict[str, Any]] = []
    for key in ("v3_trp", "meta_a", "paa"):
        frozen = strategies.get(key)
        book = _read_json(book_files[key])
        if not frozen and not book:
            continue
        history = book.get("history") or []
        frozen_date = (frozen or {}).get("frozen_date")
        if frozen_date:
            fwd_rows = [h for h in history if str(h.get("date", "")) >= str(frozen_date)]
            forward_days = max(0, len(fwd_rows) - 1)
        else:
            forward_days = 0
        nav = float(book.get("nav") or book.get("initial_capital") or 10000.0)
        init_cap = float(book.get("initial_capital") or 10000.0)
        ret_pct = round(((nav / init_cap) - 1.0) * 100.0, 2) if init_cap > 0 else 0.0
        bench_ret = None
        if history and history[0].get("benchmark_nav") and history[-1].get("benchmark_nav"):
            b0 = float(history[0]["benchmark_nav"])
            b1 = float(history[-1]["benchmark_nav"])
            if b0 > 0:
                bench_ret = round(((b1 / b0) - 1.0) * 100.0, 2)
        out.append({
            "strategy_key": key,
            "plain_label": label_map.get(key, key),
            "frozen_date": frozen_date,
            "fingerprint": str(((frozen or {}).get("fingerprint") or {}).get("sha256") or "")[:12] or None,
            "forward_days": forward_days,
            "target_days": 120,
            "nav_usd": round(nav, 2),
            "initial_capital_usd": round(init_cap, 2),
            "return_pct": ret_pct,
            "benchmark_return_pct": bench_ret,
            "status_plain": (
                f"Canlı sınav sürüyor ({forward_days}/120 işlem günü)"
                if frozen_date
                else "Henüz dondurulmadı"
            ),
        })
    return out


def build_simple_investor_brief(
    *,
    tournament_path: Optional[Path] = None,
    research_v3_path: Optional[Path] = None,
    forward_path: Optional[Path] = None,
    book_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Assemble the plain-Turkish simple-mode dashboard brief from local persisted snapshots."""
    t_data = _read_json(Path(tournament_path or DEFAULT_TOURNAMENT_JSON))
    v3_data = _read_json(Path(research_v3_path or DEFAULT_RESEARCH_V3_JSON))
    fwd_path = Path(forward_path or DEFAULT_FORWARD_JSON)
    b_dir = Path(book_dir or DEFAULT_BOOK_DIR)

    paa_row = t_data.get("paa") or {}
    meta_a_row = t_data.get("meta_portfolio_a") or t_data.get("champion") or {}
    meta_b_row = t_data.get("meta_portfolio_b") or {}
    bist_ref = t_data.get("bist_usd_reference") or {}

    v3_trp_row: Dict[str, Any] = {}
    for cand in v3_data.get("candidates") or []:
        if cand.get("strategy_id") == "V3_TREND_RISK_PARITY_BIL":
            v3_trp_row = cand
            break

    meta_a_weights = dict(meta_a_row.get("current_weights") or {"BIL": 80.0, "SHY": 20.0})
    meta_b_weights = dict(meta_b_row.get("current_weights") or {"BIL": 64.0, "SHY": 16.0})
    meta_b_cash = float(meta_b_row.get("cash_weight_pct") or 20.0)
    v3_trp_weights = dict(v3_trp_row.get("current_weights") or {"BIL": 83.3, "UUP": 16.7})
    paa_weights = dict(paa_row.get("current_weights") or {"BIL": 100.0})

    safe_share = _safe_weight_share(paa_weights)
    meta_safe_share = _safe_weight_share(meta_a_weights)
    protection_pct = max(safe_share, meta_safe_share)

    as_of_date = (
        meta_a_row.get("latest_date")
        or v3_trp_row.get("latest_date")
        or t_data.get("latest_date")
        or "Güncel"
    )
    usdtry_rate = float(bist_ref.get("usdtry_end") or 50.56)

    # Traffic-light weather summary
    if protection_pct >= 75.0:
        weather = {
            "status": "stormy",
            "emoji": "⛈️",
            "badge_label": "Koruma Kalkanı Açık",
            "headline": "Piyasalar Şu An Fırtınalı — Paranı Güvende Tut",
            "plain_summary": (
                "Küresel borsalarda düşüş baskısı yüksek olduğu için sistem otomatik koruma kalkanını açtı. "
                "Şu an hisse veya kripto kovalamak yerine paranın büyük bölümünü güvenli kısa vadeli nakit/bono araçlarında tutmak en sakin ve akıllı seçim."
            ),
            "behavioral_guard": (
                "Sakin kal: Böyle dönemlerde herkes panikle hatalı alım-satım yapar. "
                "Sistem zaten kalkanı açtığı için her gün ekran izlemene veya acele karar vermene gerek yok."
            ),
            "protection_pct": protection_pct,
        }
        decision_steps = [
            {
                "step": 1,
                "title": "Piyasa Nabzı Kontrol Edildi",
                "status": "warning",
                "explanation": "Büyük dünya borsalarının çoğu son 1 yıllık ortalamasının altına indi; fırtına sinyali var.",
                "glossary_term": "trend_kalkan",
            },
            {
                "step": 2,
                "title": "Koruma Kalkanı Devreye Girdi",
                "status": "shield",
                "explanation": f"Riskli hisse ve kripto payı düşürüldü; kalkan oranı %{protection_pct:.0f} seviyesinde.",
                "glossary_term": "risk_off",
            },
            {
                "step": 3,
                "title": "Para Güvenli Limana Alındı",
                "status": "safe",
                "explanation": "Sermaye ABD kısa vadeli hazine bonosu (veya Türkiye'de Para Piyasası Fonu) + trenddeki Dolar'da bekletiliyor.",
                "glossary_term": "bil_ppf",
            },
        ]
    elif protection_pct >= 35.0:
        weather = {
            "status": "cloudy",
            "emoji": "⛅",
            "badge_label": "Temkinli & Dengeli",
            "headline": "Piyasalar Parçalı Bulutlu — Yarı Kalkanla İlerle",
            "plain_summary": (
                "Bazı piyasalar yükselirken bazıları zayıf seyrediyor. "
                "Sistem paranın bir kısmını güçlü yükselen araçlarda tutarken diğer kısmını güvenli limanda koruyor."
            ),
            "behavioral_guard": "Dengeli dağılım ani sürprizlerde uykunu kaçırmadan yola devam etmeni sağlar.",
            "protection_pct": protection_pct,
        }
        decision_steps = [
            {
                "step": 1,
                "title": "Piyasa Karışık Sinyal Veriyor",
                "status": "info",
                "explanation": "Bazı sektör ve borsalar pozitif trendde, bazıları zayıf.",
                "glossary_term": "trend_kalkan",
            },
            {
                "step": 2,
                "title": "Kısmi Kalkan Aktif",
                "status": "shield",
                "explanation": f"Sermayenin yaklaşık %{protection_pct:.0f}'i güvenli limanda, kalanı en güçlü yükselenlerde.",
                "glossary_term": "risk_off",
            },
            {
                "step": 3,
                "title": "Aylık Sakin Kontrol Yeterli",
                "status": "safe",
                "explanation": "Ayda yalnızca bir kez dağılımı kontrol etmek işlem masraflarını çok düşük tutar.",
                "glossary_term": "rebalance",
            },
        ]
    else:
        weather = {
            "status": "sunny",
            "emoji": "☀️",
            "badge_label": "Yükseliş Havası",
            "headline": "Piyasalar Güneşli — Büyüme Motoru Açık",
            "plain_summary": (
                "Küresel borsaların geniş bölümü yükseliş trendinde. "
                "Sistem parayı en güçlü yükselen geniş sepet fonlarına yönlendiriyor."
            ),
            "behavioral_guard": "Yükselişte de tüm paranı tek bir hisseye yatırma; sepet dağılımına sadık kal.",
            "protection_pct": protection_pct,
        }
        decision_steps = [
            {
                "step": 1,
                "title": "Geniş Yükseliş Trendi Onaylandı",
                "status": "positive",
                "explanation": "Küresel borsaların büyük çoğunluğu uzun vadeli ortalamasının üzerinde.",
                "glossary_term": "trend_kalkan",
            },
            {
                "step": 2,
                "title": "Büyüme Sepeti Seçildi",
                "status": "positive",
                "explanation": "En istikrarlı yükselen geniş borsa fonları (ETF) seçildi.",
                "glossary_term": "etf",
            },
            {
                "step": 3,
                "title": "Kalkan Arka Planda Hazır",
                "status": "safe",
                "explanation": "Trend bozulursa sistem otomatik olarak tekrar güvenli limana geçiş uyarısı verir.",
                "glossary_term": "max_dd",
            },
        ]

    blended_balanced = _blend_weights_50_50(meta_a_weights, v3_trp_weights)

    profiles = [
        {
            "id": "cautious",
            "emoji": "🛡️",
            "title": "Çok Temkinli (Önce Paramı Koru)",
            "subtitle": "Sert düşüşlerden hiç hoşlanmayan, sakin uyku isteyenler için",
            "recommended": False,
            "engine_note": "19 yıllık (2008–2026) v3 Volatilite-Frenli Risk Paritesi — 2008 ve 2022 krizlerinde bile sarsılmadı.",
            "historical_max_dd_pct": -7.3,
            "estimated_annual_cost_pct": 0.04,
            "rebalance_cadence": "Ayda 1 kez (sadece büyük değişim varsa)",
            "assets": _normalize_weights_pct(v3_trp_weights),
        },
        {
            "id": "balanced",
            "emoji": "⚖️",
            "title": "Dengeli Kalkan (Önerilen)",
            "subtitle": "Hem krizde korusun hem yükselişte kazansın isteyen standart kullanıcı için",
            "recommended": True,
            "engine_note": "Meta-Portföy A v2 + v3 Risk Paritesi (%50 / %50 eşit harman) — en yüksek risk başına istikrar.",
            "historical_max_dd_pct": -5.4,
            "estimated_annual_cost_pct": 0.06,
            "rebalance_cadence": "Ayda 1 kez (ay başında 5 dakikalık kontrol)",
            "assets": _normalize_weights_pct(blended_balanced),
        },
        {
            "id": "growth",
            "emoji": "🚀",
            "title": "Büyüme + Kripto Uydu",
            "subtitle": "Daha yüksek getiri potansiyeli için küçük kripto trend dilimini kabul edenler için",
            "recommended": False,
            "engine_note": "Meta-Portföy B v2 (%80 Dengeli ETF Kalkanı + %20 Kripto 5-SMA Trend — kripto düşerken nakitte bekler).",
            "historical_max_dd_pct": -9.6,
            "estimated_annual_cost_pct": 0.09,
            "rebalance_cadence": "Ayda 1 kez (kripto trendi haftalık kontrol edilir)",
            "assets": _normalize_weights_pct(meta_b_weights, cash_pct=meta_b_cash),
        },
    ]

    return {
        "ok": True,
        "simulated_only": True,
        "as_of_date": str(as_of_date),
        "usdtry_rate": round(usdtry_rate, 2),
        "weather": weather,
        "decision_steps": decision_steps,
        "profiles": profiles,
        "paper_exam": _load_paper_exam_items(b_dir, fwd_path),
        "disclaimer": (
            "Bu ekran eğitim ve karar destek amaçlıdır; yatırım tavsiyesi değildir. "
            "Program hiçbir aracı kuruma otomatik gerçek emir göndermez (ALPACA_PAPER=true, ALPACA_AUTO_EXECUTE=false). "
            "Stratejiler 20 Kasım 2026 itibarıyla dondurulmuş 120 iş günlük canlı sanal sınavdadır."
        ),
    }
