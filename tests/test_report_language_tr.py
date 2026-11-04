# -*- coding: utf-8 -*-
"""Unit tests for the Turkish (tr) report language."""

from types import SimpleNamespace

import pytest

from src.analyzer import _localized_text
from src.daily_market_context_guardrail import apply_daily_market_context_guardrail
from src.market_structure_prompt import format_market_structure_prompt_section
from src.report_language import (
    SUPPORTED_REPORT_LANGUAGES,
    get_chip_unavailable_text,
    get_localized_stock_name,
    get_no_data_text,
    get_placeholder_text,
    get_report_labels,
    get_sentiment_label,
    get_signal_level,
    get_unknown_text,
    has_turkish_negated_verb_suffix,
    infer_decision_type_from_advice,
    localize_bias_status,
    localize_chip_health,
    localize_confidence_level,
    localize_consensus_level,
    localize_operation_advice,
    localize_strategy_skill,
    localize_strategy_synthesis_summary,
    localize_trend_prediction,
    normalize_report_language,
)
from src.schemas.decision_action import localize_action_label
from src.schemas.market_structure import MARKET_STRUCTURE_SCHEMA_VERSION


def test_turkish_is_supported_with_aliases() -> None:
    assert "tr" in SUPPORTED_REPORT_LANGUAGES
    for alias in ("tr", "TR", "turkish", "Türkçe", "turkce", "tr-TR", "tr_tr"):
        assert normalize_report_language(alias) == "tr"
    # Existing defaults stay unchanged.
    assert normalize_report_language("fr") == "zh"
    assert normalize_report_language("kr") == "ko"


def test_turkish_labels_cover_full_english_key_set() -> None:
    tr_labels = get_report_labels("tr")
    en_labels = get_report_labels("en")

    assert set(tr_labels) == set(en_labels)
    assert all(value.strip() for value in tr_labels.values())
    assert tr_labels["dashboard_title"] == "Karar Paneli"
    assert tr_labels["stop_loss_label"] == "Zarar Durdur"
    assert "{count}" in tr_labels["strategy_invalid_opinions_label"]


def test_turkish_fallback_texts() -> None:
    assert get_placeholder_text("tr") == "Belirlenecek"
    assert get_unknown_text("tr") == "Bilinmiyor"
    assert get_no_data_text("tr") == "Veri yok"
    assert "maliyet dağılımı" in get_chip_unavailable_text("tr").lower()
    assert get_localized_stock_name("", "THYAO.IS", "tr") == "Adı Doğrulanmamış Hisse"


def test_turkish_localization_maps() -> None:
    assert localize_operation_advice("买入", "tr") == "Al"
    assert localize_operation_advice("strong sell", "tr") == "Güçlü Sat"
    assert localize_trend_prediction("bullish", "tr") == "Yükseliş"
    assert localize_confidence_level("high", "tr") == "Yüksek"
    assert localize_consensus_level("insufficient", "tr") == "Yetersiz Kanıt"
    assert localize_strategy_skill("wave_theory", "tr") == "Dalga Teorisi"
    assert localize_chip_health("healthy", "tr") == "Sağlıklı"
    assert localize_bias_status("danger", "tr") == "Tehlike"
    assert localize_action_label("avoid", "tr") == "Uzak Dur"


def test_turkish_values_canonicalize_back_for_other_languages() -> None:
    assert localize_operation_advice("Güçlü Al", "en") == "Strong Buy"
    assert localize_operation_advice("İzle", "zh") == "观望"
    assert localize_trend_prediction("Güçlü Düşüş", "en") == "Strong Bearish"
    assert localize_confidence_level("Düşük", "ko") == "낮음"


@pytest.mark.parametrize(
    "advice, expected",
    [
        ("Al", "buy"),
        ("Güçlü Al", "buy"),
        ("Satın al, hedef 300 TL", "buy"),
        ("Sat", "sell"),
        ("Kısa vadede sat", "sell"),
        ("Tut", "hold"),
        ("İzle", "hold"),
        ("Alış fırsatı yok, tut", "hold"),
    ],
)
def test_turkish_advice_infers_decision_type(advice: str, expected: str) -> None:
    assert infer_decision_type_from_advice(advice) == expected


def test_turkish_signal_level_and_sentiment() -> None:
    assert get_signal_level("Güçlü Al", 80, "tr") == ("Güçlü Al", "💚", "strong_buy")
    assert get_signal_level("Sat", 30, "tr") == ("Sat", "🔴", "sell")
    assert get_sentiment_label(85, "tr") == "Çok İyimser"
    assert get_sentiment_label(50, "tr") == "Nötr"
    assert get_sentiment_label(5, "tr") == "Çok Kötümser"


def test_turkish_strategy_synthesis_summary() -> None:
    summary = localize_strategy_synthesis_summary(
        {
            "final_signal": "buy",
            "consensus_level": "high",
            "conflict_severity": "none",
            "conflict_count": 0,
            "summary_params": {"opinion_count": 3},
        },
        "tr",
    )
    assert summary == (
        "3 stratejinin sentezi: nihai sinyal Al, uzlaşı düzeyi Yüksek, strateji çelişkisi tespit edilmedi."
    )


def test_localized_text_uses_turkish_or_english_never_chinese() -> None:
    assert _localized_text("tr", en="Done", zh="完成", ko="완료", tr="Tamam") == "Tamam"
    assert _localized_text("tr", en="Done", zh="完成", ko="완료") == "Done"
    assert _localized_text("zh", en="Done", zh="完成", ko="완료", tr="Tamam") == "完成"


@pytest.mark.parametrize(
    "suffix, negated",
    [
        ("mayın", True),  # almayın: do not buy
        ("ma", True),
        ("mamalı", True),  # almamalı: should not buy
        ("mak mantıklı", False),  # almak: infinitive
        ("malısınız", False),  # almalısınız: you should buy
        ("", False),
        (" için", False),
    ],
)
def test_turkish_negated_verb_suffix(suffix: str, negated: bool) -> None:
    assert has_turkish_negated_verb_suffix(suffix) is negated


def _buy_result(advice: str) -> SimpleNamespace:
    return SimpleNamespace(
        decision_type="buy",
        operation_advice=advice,
        confidence_level="Yüksek",
        sentiment_score=82,
        dashboard={},
        report_language="tr",
    )


def test_daily_market_guardrail_softens_turkish_aggressive_buy() -> None:
    result = _buy_result("Hemen al, hedef 300 TL")

    adjustments = apply_daily_market_context_guardrail(
        result,
        daily_market_context={"risk_tags": ["high_risk"]},
        report_language="tr",
    )

    assert "daily_market_context_buy_softened" in adjustments
    assert result.decision_type == "hold"
    assert result.operation_advice == "İzle"
    assert result.confidence_level == "Orta"
    assert result.sentiment_score <= 52
    limitations = result.dashboard["phase_decision"]["data_limitations"]
    assert any("yumuşatıldı" in item for item in limitations)


def test_daily_market_guardrail_respects_turkish_suffix_negation() -> None:
    result = _buy_result("Hemen almayın, destek teyidini bekleyin")
    result.decision_type = "hold"

    adjustments = apply_daily_market_context_guardrail(
        result,
        daily_market_context={"risk_tags": ["high_risk"]},
        report_language="tr",
    )

    assert adjustments == []
    assert result.operation_advice == "Hemen almayın, destek teyidini bekleyin"


def test_market_structure_prompt_uses_english_scaffolding_for_turkish() -> None:
    context = {
        "schema_version": MARKET_STRUCTURE_SCHEMA_VERSION,
        "status": "ok",
        "market_theme_context": {"active_themes": ["Savunma"]},
        "stock_market_position": {"role": "leader"},
    }
    tr_section = format_market_structure_prompt_section(context, report_language="tr")
    en_section = format_market_structure_prompt_section(context, report_language="en")
    assert tr_section == en_section
