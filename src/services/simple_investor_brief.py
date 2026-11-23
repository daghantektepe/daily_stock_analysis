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
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_TOURNAMENT_JSON = Path("data") / "quant_cache" / "tournament_latest.json"
DEFAULT_RESEARCH_V3_JSON = Path("data") / "quant_cache" / "research_v3_latest.json"
DEFAULT_FORWARD_JSON = Path("data") / "strategy_paper" / "forward_validation.json"
DEFAULT_BOOK_DIR = Path("data") / "strategy_paper"

# A snapshot older than this (calendar days, so weekends/holidays fit) is flagged stale.
STALE_AFTER_DAYS = 5
SNAPSHOT_REFRESH_HINT = (
    "Günlük sanal defter görevi bu verileri her gün yeniler; hemen yenilemek için "
    "`python scripts/quant_paper.py step` çalıştırın (Windows: `.venv\\Scripts\\python.exe scripts\\quant_paper.py step`)."
)

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
        return []
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


def _safe_weight_share(weights: Dict[str, Any], cash_pct: float = 0.0) -> Optional[float]:
    """Share of the book in cash-like assets; None when there are no weights at all."""
    safe_syms = {"BIL", "SHY", "IEF", "UUP", "CASH"}
    total = sum(float(v) for v in (weights or {}).values() if v) + max(0.0, float(cash_pct or 0.0))
    if total <= 0:
        return None
    safe_sum = sum(float(v) for k, v in (weights or {}).items() if str(k).upper() in safe_syms and v)
    safe_sum += max(0.0, float(cash_pct or 0.0))
    return round((safe_sum / total) * 100.0, 1)


def _row_weights(row: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Live target weights of a strategy row, or None when the snapshot has no such row."""
    if not row:
        return None
    weights = row.get("current_weights")
    if not isinstance(weights, dict):
        return None
    if not weights and float(row.get("cash_weight_pct") or 0.0) <= 0.0:
        return None
    return {str(k): float(v) for k, v in weights.items()}


def _age_days(as_of: Optional[str], today: date) -> Optional[int]:
    if not as_of:
        return None
    try:
        return (today - date.fromisoformat(str(as_of)[:10])).days
    except ValueError:
        return None


def _source_status(key: str, label: str, as_of: Optional[str], available: bool, today: date) -> Dict[str, Any]:
    age = _age_days(as_of, today) if available else None
    return {
        "key": key,
        "label": label,
        "available": bool(available),
        "as_of_date": as_of if available else None,
        "age_days": age,
        "stale": bool(available and age is not None and age > STALE_AFTER_DAYS),
    }


def _build_data_status(sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    missing = [s["label"] for s in sources if not s["available"]]
    stale = [s for s in sources if s["stale"]]
    if len(missing) == len(sources):
        state = "missing"
        message = "Strateji verisi bulunamadı; bu ekran şu an öneri gösteremez. " + SNAPSHOT_REFRESH_HINT
    elif missing:
        state = "partial"
        message = f"Eksik veri: {', '.join(missing)}. Bu veriye dayanan sepetler gösterilmiyor. " + SNAPSHOT_REFRESH_HINT
    elif stale:
        oldest = max(stale, key=lambda s: s["age_days"] or 0)
        state = "stale"
        message = (
            f"Veriler güncel değil: {', '.join(s['label'] for s in stale)} "
            f"{oldest['age_days']} gün önceye ait ({oldest['as_of_date']}). Öneri o günün piyasasını yansıtır. "
            + SNAPSHOT_REFRESH_HINT
        )
    else:
        state = "ok"
        message = ""
    return {"state": state, "message": message, "stale_after_days": STALE_AFTER_DAYS, "sources": sources}


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


def load_signal_accuracy_for_brief(
    *,
    db_manager: Optional[Any] = None,
    history_provider: Optional[Any] = None,
) -> Dict[str, Any]:
    """Read directional signal vs. index status without triggering slow bar refills."""
    from src.services.paper_trading_benchmark import build_signal_accuracy_summary, evaluate_signal_outcomes

    try:
        from src.config import get_config
        from src.storage import DatabaseManager, DecisionSignalRecord

        if db_manager is None:
            db_path = getattr(get_config(), "database_path", None)
            if db_path and not Path(str(db_path)).is_file():
                return build_signal_accuracy_summary({}, signal_count=0)
        manager = db_manager or DatabaseManager.get_instance()
        with manager.get_session() as session:
            signal_count = int(session.query(DecisionSignalRecord.id).count())
        if signal_count <= 0:
            return build_signal_accuracy_summary({}, signal_count=0)
        outcomes = evaluate_signal_outcomes(
            db_manager=manager,
            refill_missing_bars=False,
            history_provider=history_provider,
        )
        return build_signal_accuracy_summary(outcomes, signal_count=signal_count)
    except Exception as exc:  # noqa: BLE001 - fail-open, report missing data explicitly
        logger.info("[simple-brief] signal accuracy skipped: %s", exc)
        return build_signal_accuracy_summary({}, signal_count=0)


def build_simple_investor_brief(
    *,
    tournament_path: Optional[Path] = None,
    research_v3_path: Optional[Path] = None,
    forward_path: Optional[Path] = None,
    book_dir: Optional[Path] = None,
    today: Optional[date] = None,
    db_manager: Optional[Any] = None,
    signal_summary_loader: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Assemble the plain-Turkish simple-mode dashboard brief from local persisted snapshots.

    Nothing is invented when a snapshot is missing: weights, dates, FX and the
    market "weather" come only from the tournament / research v3 files, and
    ``data_status`` tells the reader what is missing or stale.
    """
    today = today or date.today()
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

    paa_weights = _row_weights(paa_row)
    meta_a_weights = _row_weights(meta_a_row)
    meta_b_weights = _row_weights(meta_b_row)
    meta_b_cash = float(meta_b_row.get("cash_weight_pct") or 0.0) if meta_b_row else 0.0
    v3_trp_weights = _row_weights(v3_trp_row)

    shares = [
        share
        for share in (
            _safe_weight_share(paa_weights) if paa_weights is not None else None,
            _safe_weight_share(meta_a_weights) if meta_a_weights is not None else None,
        )
        if share is not None
    ]
    protection_pct: Optional[float] = max(shares) if shares else None

    tournament_as_of = t_data.get("latest_date") or meta_a_row.get("latest_date")
    research_as_of = v3_trp_row.get("latest_date")
    data_status = _build_data_status(
        [
            _source_status(
                "tournament", "Strateji turnuvası", tournament_as_of,
                bool(paa_weights is not None or meta_a_weights is not None), today,
            ),
            _source_status("research_v3", "v3 araştırması", research_as_of, v3_trp_weights is not None, today),
        ]
    )
    dated = [str(d)[:10] for d in (meta_a_row.get("latest_date"), tournament_as_of, research_as_of) if d]
    as_of_date = max(dated) if dated else ""
    usdtry_end = bist_ref.get("usdtry_end")
    usdtry_rate: Optional[float] = round(float(usdtry_end), 2) if usdtry_end else None

    # Traffic-light weather summary
    if protection_pct is None:
        weather = {
            "status": "unknown",
            "emoji": "❔",
            "badge_label": "Veri Yok",
            "headline": "Piyasa Durumu Bilinmiyor — Önce Strateji Verisini Güncelle",
            "plain_summary": (
                "PAA ve Meta-Portföy A sinyalleri okunamadı, bu yüzden sistem bugün için bir koruma "
                "ya da alım kararı göstermiyor. Tahmine dayalı bir dağılım göstermek yerine boş bırakıldı."
            ),
            "behavioral_guard": "Veri gelene kadar mevcut portföyünde değişiklik yapma.",
            "protection_pct": None,
        }
        decision_steps = [
            {
                "step": 1,
                "title": "Strateji Verisi Bekleniyor",
                "status": "warning",
                "explanation": SNAPSHOT_REFRESH_HINT,
                "glossary_term": None,
            },
        ]
    elif protection_pct >= 75.0:
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

    v3_full = v3_trp_row.get("full_2008_plus") or {}
    ortho = v3_trp_row.get("orthogonality_vs_meta_a") or {}
    meta_b_oos = meta_b_row.get("oos") or {}

    profiles: List[Dict[str, Any]] = []
    if v3_trp_weights is not None:
        profiles.append({
            "id": "cautious",
            "emoji": "🛡️",
            "title": "Çok Temkinli (Önce Paramı Koru)",
            "subtitle": "Sert düşüşlerden hiç hoşlanmayan, sakin uyku isteyenler için",
            "recommended": False,
            "engine_note": "19 yıllık (2008–2026) v3 Volatilite-Frenli Risk Paritesi — 2008 ve 2022 krizlerinde bile sarsılmadı.",
            "historical_max_dd_pct": v3_full.get("max_drawdown_pct"),
            "estimated_annual_cost_pct": 0.04,
            "rebalance_cadence": "Ayda 1 kez (sadece büyük değişim varsa)",
            "assets": _normalize_weights_pct(v3_trp_weights),
        })
    if meta_a_weights is not None and v3_trp_weights is not None:
        profiles.append({
            "id": "balanced",
            "emoji": "⚖️",
            "title": "Dengeli Kalkan (Önerilen)",
            "subtitle": "Hem krizde korusun hem yükselişte kazansın isteyen standart kullanıcı için",
            "recommended": True,
            "engine_note": "Meta-Portföy A v2 + v3 Risk Paritesi (%50 / %50 eşit harman) — en yüksek risk başına istikrar.",
            "historical_max_dd_pct": ortho.get("blend_50_50_max_dd_pct"),
            "estimated_annual_cost_pct": 0.06,
            "rebalance_cadence": "Ayda 1 kez (ay başında 5 dakikalık kontrol)",
            "assets": _normalize_weights_pct(_blend_weights_50_50(meta_a_weights, v3_trp_weights)),
        })
    if meta_b_weights is not None:
        profiles.append({
            "id": "growth",
            "emoji": "🚀",
            "title": "Büyüme + Kripto Uydu",
            "subtitle": "Daha yüksek getiri potansiyeli için küçük kripto trend dilimini kabul edenler için",
            "recommended": False,
            "engine_note": "Meta-Portföy B v2 (%80 Dengeli ETF Kalkanı + %20 Kripto 5-SMA Trend — kripto düşerken nakitte bekler).",
            "historical_max_dd_pct": meta_b_oos.get("max_drawdown_pct"),
            "estimated_annual_cost_pct": 0.09,
            "rebalance_cadence": "Ayda 1 kez (kripto trendi haftalık kontrol edilir)",
            "assets": _normalize_weights_pct(meta_b_weights, cash_pct=meta_b_cash),
        })
    profiles = [p for p in profiles if p["assets"]]

    paper_exam = _load_paper_exam_items(b_dir, fwd_path)
    signal_accuracy = (
        signal_summary_loader()
        if signal_summary_loader is not None
        else load_signal_accuracy_for_brief(db_manager=db_manager)
    )
    frozen_dates = sorted({str(item["frozen_date"]) for item in paper_exam if item.get("frozen_date")})
    exam_note = (
        f"Stratejiler {', '.join(frozen_dates)} itibarıyla dondurulmuş 120 işlem günlük canlı sanal sınavdadır."
        if frozen_dates
        else "Stratejilerin canlı sanal sınavı henüz başlamadı."
    )

    return {
        "ok": data_status["state"] != "missing",
        "simulated_only": True,
        "as_of_date": as_of_date,
        "usdtry_rate": usdtry_rate,
        "data_status": data_status,
        "weather": weather,
        "decision_steps": decision_steps,
        "profiles": profiles,
        "paper_exam": paper_exam,
        "signal_accuracy": signal_accuracy,
        "disclaimer": (
            "Bu ekran eğitim ve karar destek amaçlıdır; yatırım tavsiyesi değildir. "
            "Program hiçbir aracı kuruma otomatik gerçek emir göndermez (ALPACA_PAPER=true, ALPACA_AUTO_EXECUTE=false). "
            + exam_note
        ),
    }
