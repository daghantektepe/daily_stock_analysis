# -*- coding: utf-8 -*-
"""Helpers for report output language selection and localization."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from src.schemas.decision_scale import signal_key_for_score

SUPPORTED_REPORT_LANGUAGES = ("zh", "en", "ko", "tr")

_REPORT_LANGUAGE_ALIASES = {
    "zh-cn": "zh",
    "zh_cn": "zh",
    "zh-hans": "zh",
    "zh_hans": "zh",
    "zh-tw": "zh",
    "zh_tw": "zh",
    "cn": "zh",
    "chinese": "zh",
    "english": "en",
    "en-us": "en",
    "en_us": "en",
    "en-gb": "en",
    "en_gb": "en",
    "korean": "ko",
    "kr": "ko",
    "ko-kr": "ko",
    "ko_kr": "ko",
    "turkish": "tr",
    "türkçe": "tr",
    "turkce": "tr",
    "tr-tr": "tr",
    "tr_tr": "tr",
}

_OPERATION_ADVICE_CANONICAL_MAP = {
    "强烈买入": "strong_buy",
    "strong buy": "strong_buy",
    "strong_buy": "strong_buy",
    "买入": "buy",
    "buy": "buy",
    "加仓": "buy",
    "accumulate": "buy",
    "add position": "buy",
    "持有": "hold",
    "洗盘观察": "hold",
    "观察": "hold",
    "hold": "hold",
    "观望": "watch",
    "watch": "watch",
    "wait": "watch",
    "wait and see": "watch",
    "减仓": "reduce",
    "reduce": "reduce",
    "trim": "reduce",
    "卖出": "sell",
    "sell": "sell",
    "强烈卖出": "strong_sell",
    "strong sell": "strong_sell",
    "strong_sell": "strong_sell",
    "적극 매수": "strong_buy",
    "매수": "buy",
    "보유": "hold",
    "보유 관찰": "hold",
    "관망": "watch",
    "비중축소": "reduce",
    "매도": "sell",
    "적극 매도": "strong_sell",
}

_OPERATION_ADVICE_TRANSLATIONS = {
    "strong_buy": {"zh": "强烈买入", "en": "Strong Buy", "ko": "적극 매수", "tr": "Güçlü Al"},
    "buy": {"zh": "买入", "en": "Buy", "ko": "매수", "tr": "Al"},
    "hold": {"zh": "持有", "en": "Hold", "ko": "보유", "tr": "Tut"},
    "watch": {"zh": "观望", "en": "Watch", "ko": "관망", "tr": "İzle"},
    "reduce": {"zh": "减仓", "en": "Reduce", "ko": "비중축소", "tr": "Azalt"},
    "sell": {"zh": "卖出", "en": "Sell", "ko": "매도", "tr": "Sat"},
    "strong_sell": {"zh": "强烈卖出", "en": "Strong Sell", "ko": "적극 매도", "tr": "Güçlü Sat"},
}

_TREND_PREDICTION_CANONICAL_MAP = {
    "强势空头": "strong_bearish",
    "强烈看多": "strong_bullish",
    "strong bullish": "strong_bullish",
    "very bullish": "strong_bullish",
    "强势多头": "strong_bullish",
    "多头排列": "bullish",
    "空头排列": "bearish",
    "弱势多头": "bullish",
    "弱势空头": "bearish",
    "看多": "bullish",
    "盘整": "sideways",
    "bullish": "bullish",
    "uptrend": "bullish",
    "震荡": "sideways",
    "neutral": "sideways",
    "sideways": "sideways",
    "range-bound": "sideways",
    "看空": "bearish",
    "bearish": "bearish",
    "downtrend": "bearish",
    "强烈看空": "strong_bearish",
    "strong bearish": "strong_bearish",
    "very bearish": "strong_bearish",
    "강한 상승": "strong_bullish",
    "상승": "bullish",
    "횡보": "sideways",
    "하락": "bearish",
    "강한 하락": "strong_bearish",
}

_TREND_PREDICTION_TRANSLATIONS = {
    "strong_bullish": {"zh": "强烈看多", "en": "Strong Bullish", "ko": "강한 상승", "tr": "Güçlü Yükseliş"},
    "bullish": {"zh": "看多", "en": "Bullish", "ko": "상승", "tr": "Yükseliş"},
    "sideways": {"zh": "震荡", "en": "Sideways", "ko": "횡보", "tr": "Yatay"},
    "bearish": {"zh": "看空", "en": "Bearish", "ko": "하락", "tr": "Düşüş"},
    "strong_bearish": {"zh": "强烈看空", "en": "Strong Bearish", "ko": "강한 하락", "tr": "Güçlü Düşüş"},
}

_CONFIDENCE_LEVEL_CANONICAL_MAP = {
    "高": "high",
    "high": "high",
    "中": "medium",
    "medium": "medium",
    "med": "medium",
    "低": "low",
    "low": "low",
    "높음": "high",
    "보통": "medium",
    "낮음": "low",
}

_CONFIDENCE_LEVEL_TRANSLATIONS = {
    "high": {"zh": "高", "en": "High", "ko": "높음", "tr": "Yüksek"},
    "medium": {"zh": "中", "en": "Medium", "ko": "보통", "tr": "Orta"},
    "low": {"zh": "低", "en": "Low", "ko": "낮음", "tr": "Düşük"},
}

_STRATEGY_SIGNAL_CANONICAL_MAP = {
    "strong buy": "strong_buy",
    "strong_buy": "strong_buy",
    "强烈买入": "strong_buy",
    "buy": "buy",
    "买入": "buy",
    "hold": "hold",
    "持有": "hold",
    "sell": "sell",
    "卖出": "sell",
    "strong sell": "strong_sell",
    "strong_sell": "strong_sell",
    "强烈卖出": "strong_sell",
}

_STRATEGY_SIGNAL_TRANSLATIONS = {
    "strong_buy": {"zh": "强烈买入", "en": "Strong Buy", "ko": "적극 매수", "tr": "Güçlü Al"},
    "buy": {"zh": "买入", "en": "Buy", "ko": "매수", "tr": "Al"},
    "hold": {"zh": "持有", "en": "Hold", "ko": "보유", "tr": "Tut"},
    "sell": {"zh": "卖出", "en": "Sell", "ko": "매도", "tr": "Sat"},
    "strong_sell": {"zh": "强烈卖出", "en": "Strong Sell", "ko": "적극 매도", "tr": "Güçlü Sat"},
}

_CONSENSUS_LEVEL_CANONICAL_MAP = {
    "high": "high",
    "高": "high",
    "medium": "medium",
    "中": "medium",
    "low": "low",
    "低": "low",
    "insufficient": "insufficient",
    "证据不足": "insufficient",
    "Insufficient": "insufficient",
    "증거 부족": "insufficient",
}

_CONSENSUS_LEVEL_TRANSLATIONS = {
    "high": {"zh": "高", "en": "High", "ko": "높음", "tr": "Yüksek"},
    "medium": {"zh": "中", "en": "Medium", "ko": "보통", "tr": "Orta"},
    "low": {"zh": "低", "en": "Low", "ko": "낮음", "tr": "Düşük"},
    "insufficient": {"zh": "证据不足", "en": "Insufficient", "ko": "증거 부족", "tr": "Yetersiz Kanıt"},
}

_CONFLICT_SEVERITY_CANONICAL_MAP = {
    "none": "none",
    "无": "none",
    "low": "low",
    "低": "low",
    "medium": "medium",
    "中": "medium",
    "high": "high",
    "高": "high",
}

_CONFLICT_SEVERITY_TRANSLATIONS = {
    "none": {"zh": "无", "en": "None", "ko": "없음", "tr": "Yok"},
    "low": {"zh": "低", "en": "Low", "ko": "낮음", "tr": "Düşük"},
    "medium": {"zh": "中", "en": "Medium", "ko": "보통", "tr": "Orta"},
    "high": {"zh": "高", "en": "High", "ko": "높음", "tr": "Yüksek"},
}

_STRATEGY_SKILL_CANONICAL_MAP = {
    "bull trend": "bull_trend",
    "bull_trend": "bull_trend",
    "默认多头趋势": "bull_trend",
    "hot theme": "hot_theme",
    "hot_theme": "hot_theme",
    "热点题材": "hot_theme",
    "volume breakout": "volume_breakout",
    "volume_breakout": "volume_breakout",
    "放量突破": "volume_breakout",
    "ma golden cross": "ma_golden_cross",
    "ma_golden_cross": "ma_golden_cross",
    "均线金叉": "ma_golden_cross",
    "growth quality": "growth_quality",
    "growth_quality": "growth_quality",
    "成长质量": "growth_quality",
    "bottom volume": "bottom_volume",
    "bottom_volume": "bottom_volume",
    "底部放量": "bottom_volume",
    "box oscillation": "box_oscillation",
    "box_oscillation": "box_oscillation",
    "箱体震荡": "box_oscillation",
    "chan theory": "chan_theory",
    "chan_theory": "chan_theory",
    "缠论结构": "chan_theory",
    "dragon head": "dragon_head",
    "dragon_head": "dragon_head",
    "龙头战法": "dragon_head",
    "emotion cycle": "emotion_cycle",
    "emotion_cycle": "emotion_cycle",
    "情绪周期": "emotion_cycle",
    "event driven": "event_driven",
    "event_driven": "event_driven",
    "事件驱动": "event_driven",
    "expectation repricing": "expectation_repricing",
    "expectation_repricing": "expectation_repricing",
    "预期重估": "expectation_repricing",
    "one yang three yin": "one_yang_three_yin",
    "one_yang_three_yin": "one_yang_three_yin",
    "一阳三阴": "one_yang_three_yin",
    "shrink pullback": "shrink_pullback",
    "shrink_pullback": "shrink_pullback",
    "缩量回踩": "shrink_pullback",
    "wave theory": "wave_theory",
    "wave_theory": "wave_theory",
    "波浪理论": "wave_theory",
}

_STRATEGY_SKILL_TRANSLATIONS = {
    "bull_trend": {"zh": "默认多头趋势", "en": "Bull Trend", "ko": "기본 상승 추세", "tr": "Temel Yükseliş Trendi"},
    "hot_theme": {"zh": "热点题材", "en": "Hot Theme", "ko": "핫 테마", "tr": "Popüler Tema"},
    "volume_breakout": {"zh": "放量突破", "en": "Volume Breakout", "ko": "거래량 돌파", "tr": "Hacimli Kırılım"},
    "ma_golden_cross": {"zh": "均线金叉", "en": "MA Golden Cross", "ko": "이평선 골든크로스", "tr": "HO Altın Kesişim"},
    "growth_quality": {"zh": "成长质量", "en": "Growth Quality", "ko": "성장 품질", "tr": "Büyüme Kalitesi"},
    "bottom_volume": {"zh": "底部放量", "en": "Bottom Volume", "ko": "저점 거래량", "tr": "Dip Hacmi"},
    "box_oscillation": {"zh": "箱体震荡", "en": "Box Oscillation", "ko": "박스권 등락", "tr": "Kutu İçi Dalgalanma"},
    "chan_theory": {"zh": "缠论结构", "en": "Chan Theory", "ko": "찬 이론 구조", "tr": "Chan Teorisi Yapısı"},
    "dragon_head": {"zh": "龙头战法", "en": "Dragon Head", "ko": "대장주 전략", "tr": "Lider Hisse Stratejisi"},
    "emotion_cycle": {"zh": "情绪周期", "en": "Emotion Cycle", "ko": "심리 사이클", "tr": "Duygu Döngüsü"},
    "event_driven": {"zh": "事件驱动", "en": "Event Driven", "ko": "이벤트 드리븐", "tr": "Olay Odaklı"},
    "expectation_repricing": {"zh": "预期重估", "en": "Expectation Repricing", "ko": "기대 재평가", "tr": "Beklenti Yeniden Fiyatlaması"},
    "one_yang_three_yin": {"zh": "一阳三阴", "en": "One Yang Three Yin", "ko": "일양삼음", "tr": "Bir Yang Üç Yin"},
    "shrink_pullback": {"zh": "缩量回踩", "en": "Shrink Pullback", "ko": "거래량 축소 눌림", "tr": "Düşük Hacimli Geri Çekilme"},
    "wave_theory": {"zh": "波浪理论", "en": "Wave Theory", "ko": "파동 이론", "tr": "Dalga Teorisi"},
}

_CHIP_HEALTH_CANONICAL_MAP = {
    "健康": "healthy",
    "healthy": "healthy",
    "一般": "average",
    "average": "average",
    "警惕": "caution",
    "caution": "caution",
    "양호": "healthy",
    "보통": "average",
    "주의": "caution",
}

_CHIP_HEALTH_TRANSLATIONS = {
    "healthy": {"zh": "健康", "en": "Healthy", "ko": "양호", "tr": "Sağlıklı"},
    "average": {"zh": "一般", "en": "Average", "ko": "보통", "tr": "Ortalama"},
    "caution": {"zh": "警惕", "en": "Caution", "ko": "주의", "tr": "Dikkat"},
}

_BIAS_STATUS_CANONICAL_MAP = {
    "安全": "safe",
    "safe": "safe",
    "警戒": "caution",
    "警惕": "caution",
    "caution": "caution",
    "危险": "danger",
    "risk": "danger",
    "danger": "danger",
    "안전": "safe",
    "경계": "caution",
    "위험": "danger",
}

_BIAS_STATUS_TRANSLATIONS = {
    "safe": {"zh": "安全", "en": "Safe", "ko": "안전", "tr": "Güvenli"},
    "caution": {"zh": "警戒", "en": "Caution", "ko": "경계", "tr": "Dikkat"},
    "danger": {"zh": "危险", "en": "Danger", "ko": "위험", "tr": "Tehlike"},
}

_PLACEHOLDER_BY_LANGUAGE = {
    "zh": "待补充",
    "en": "TBD",
    "ko": "미정",
    "tr": "Belirlenecek",
}

_UNKNOWN_BY_LANGUAGE = {
    "zh": "未知",
    "en": "Unknown",
    "ko": "알 수 없음",
    "tr": "Bilinmiyor",
}

_NO_DATA_BY_LANGUAGE = {
    "zh": "数据缺失",
    "en": "Data unavailable",
    "ko": "데이터 없음",
    "tr": "Veri yok",
}

_CHIP_UNAVAILABLE_BY_LANGUAGE = {
    "zh": "筹码分布未启用或数据源暂不可用，未纳入筹码判断。",
    "en": "Chip distribution is disabled or temporarily unavailable; chip signals were not used.",
    "ko": "매물대가 비활성화되었거나 데이터 소스를 일시적으로 사용할 수 없어 매물대 신호를 반영하지 않았습니다.",
    "tr": "Maliyet dağılımı (chip) devre dışı veya veri kaynağı geçici olarak kullanılamıyor; maliyet dağılımı sinyalleri dikkate alınmadı.",
}

_CHIP_PLACEHOLDER_EXACT = {
    "",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "tbd",
    "数据缺失",
    "未知",
    "暂无",
    "待补充",
}

_CHIP_PLACEHOLDER_HINTS = (
    "数据缺失",
    "无法判断",
    "data unavailable",
    "unavailable",
    "not available",
    "missing",
    "not supported",
)

_CHIP_METRIC_KEYS = ("profit_ratio", "avg_cost", "concentration")
_CHIP_UNAVAILABLE_REASON_KEYS = (
    "chip_unavailable_reason",
    "unavailable_reason",
    "chip_unavailable",
)

_GENERIC_STOCK_NAME_BY_LANGUAGE = {
    "zh": "待确认股票",
    "en": "Unnamed Stock",
    "ko": "미확인 종목",
    "tr": "Adı Doğrulanmamış Hisse",
}

_REPORT_LABELS: Dict[str, Dict[str, str]] = {
    "zh": {
        "dashboard_title": "决策仪表盘",
        "brief_title": "决策简报",
        "analyzed_prefix": "共分析",
        "stock_unit": "只股票",
        "stock_unit_compact": "只",
        "buy_label": "买入",
        "watch_label": "观望",
        "sell_label": "卖出",
        "summary_heading": "分析结果摘要",
        "info_heading": "重要信息速览",
        "sentiment_summary_label": "舆情情绪",
        "earnings_outlook_label": "业绩预期",
        "risk_alerts_label": "风险警报",
        "positive_catalysts_label": "利好催化",
        "latest_news_label": "最新动态",
        "core_conclusion_heading": "核心结论",
        "one_sentence_label": "一句话决策",
        "time_sensitivity_label": "时效性",
        "default_time_sensitivity": "本周内",
        "position_status_label": "持仓情况",
        "action_advice_label": "操作建议",
        "no_position_label": "空仓者",
        "has_position_label": "持仓者",
        "continue_holding": "继续持有",
        "market_snapshot_heading": "当日行情",
        "close_label": "收盘",
        "prev_close_label": "昨收",
        "open_label": "开盘",
        "high_label": "最高",
        "low_label": "最低",
        "change_pct_label": "涨跌幅",
        "change_amount_label": "涨跌额",
        "amplitude_label": "振幅",
        "volume_label": "成交量",
        "amount_label": "成交额",
        "current_price_label": "当前价",
        "volume_ratio_label": "量比",
        "turnover_rate_label": "换手率",
        "source_label": "行情来源",
        "data_perspective_heading": "数据透视",
        "ma_alignment_label": "均线排列",
        "bullish_alignment_label": "多头排列",
        "yes_label": "是",
        "no_label": "否",
        "none_label": "无",
        "trend_strength_label": "趋势强度",
        "price_metrics_label": "价格指标",
        "ma5_label": "MA5",
        "ma10_label": "MA10",
        "ma20_label": "MA20",
        "bias_ma5_label": "乖离率(MA5)",
        "support_level_label": "支撑位",
        "resistance_level_label": "压力位",
        "chip_label": "筹码",
        "phase_decision_heading": "盘中决策护栏",
        "action_window_label": "行动窗口",
        "immediate_action_label": "当前动作",
        "watch_conditions_label": "观察条件",
        "next_check_time_label": "下次检查",
        "confidence_reason_label": "置信度理由",
        "data_limitations_label": "数据限制",
        "battle_plan_heading": "作战计划",
        "ideal_buy_label": "理想买入点",
        "secondary_buy_label": "次优买入点",
        "stop_loss_label": "止损位",
        "take_profit_label": "目标位",
        "suggested_position_label": "仓位建议",
        "entry_plan_label": "建仓策略",
        "risk_control_label": "风控策略",
        "checklist_heading": "检查清单",
        "failed_checks_heading": "检查未通过项",
        "history_compare_heading": "历史信号对比",
        "time_label": "时间",
        "score_label": "评分",
        "advice_label": "建议",
        "trend_label": "趋势",
        "generated_at_label": "报告生成时间",
        "report_time_label": "生成时间",
        "no_results": "无分析结果",
        "report_title": "股票分析报告",
        "avg_score_label": "均分",
        "action_points_heading": "操作点位",
        "position_advice_heading": "持仓建议",
        "analysis_model_label": "分析模型",
        "not_investment_advice": "AI生成，仅供参考，不构成投资建议",
        "details_report_hint": "详细报告见",
        "financial_summary_heading": "财务摘要",
        "report_date_label": "报告期",
        "revenue_label": "营业收入",
        "net_profit_label": "归母净利润",
        "operating_cash_flow_label": "经营现金流",
        "roe_label": "ROE",
        "revenue_yoy_label": "营收同比",
        "net_profit_yoy_label": "净利同比",
        "gross_margin_label": "毛利率",
        "shareholder_return_heading": "股东回报",
        "ttm_cash_dividend_label": "近12月每股现金分红(税前)",
        "ttm_event_count_label": "近12月分红次数",
        "ttm_dividend_yield_label": "TTM 股息率",
        "latest_ex_dividend_label": "最近除息日",
        "institutional_flow_heading": "三大法人动向",
        "institutional_flow_note": "正数=净买超，负数=净卖超；单位为股。",
        "inst_foreign_label": "外资",
        "inst_trust_label": "投信",
        "inst_dealer_label": "自营商",
        "inst_total_label": "三大法人合计",
        "related_boards_heading": "关联板块",
        "industry_boards_heading": "行业板块",
        "concept_boards_heading": "概念板块",
        "board_name_label": "板块",
        "board_type_label": "类型",
        "board_status_label": "板块表现",
        "board_change_pct_label": "板块涨跌幅",
        "leading_board_label": "领涨",
        "lagging_board_label": "领跌",
        "signal_attribution_heading": "信号归因分析",
        "attribution_weights_label": "归因权重",
        "technical_indicators_label": "技术指标",
        "news_sentiment_label": "新闻舆情",
        "fundamentals_label": "基本面",
        "market_conditions_label": "市场环境",
        "strongest_bullish_signal_label": "最强看多信号",
        "strongest_bearish_signal_label": "最强看空信号",
        "strategy_synthesis_heading": "多策略综合",
        "strategy_final_signal_label": "综合信号",
        "strategy_consensus_level_label": "共识度",
        "strategy_conflict_label": "冲突",
        "strategy_confidence_label": "置信度",
        "strategy_summary_label": "综合说明",
        "strategy_supporting_skills_label": "支持策略",
        "strategy_opposing_skills_label": "反方策略",
        "strategy_invalid_opinions_label": "另有 {count} 个策略解析失败",
    },
    "en": {
        "dashboard_title": "Decision Dashboard",
        "brief_title": "Decision Brief",
        "analyzed_prefix": "Analyzed",
        "stock_unit": "stocks",
        "stock_unit_compact": "stocks",
        "buy_label": "Buy",
        "watch_label": "Watch",
        "sell_label": "Sell",
        "summary_heading": "Summary",
        "info_heading": "Key Updates",
        "sentiment_summary_label": "Sentiment",
        "earnings_outlook_label": "Earnings Outlook",
        "risk_alerts_label": "Risk Alerts",
        "positive_catalysts_label": "Positive Catalysts",
        "latest_news_label": "Latest News",
        "core_conclusion_heading": "Core Conclusion",
        "one_sentence_label": "One-line Decision",
        "time_sensitivity_label": "Time Sensitivity",
        "default_time_sensitivity": "This week",
        "position_status_label": "Position",
        "action_advice_label": "Action",
        "no_position_label": "No Position",
        "has_position_label": "Holding",
        "continue_holding": "Continue holding",
        "market_snapshot_heading": "Market Snapshot",
        "close_label": "Close",
        "prev_close_label": "Prev Close",
        "open_label": "Open",
        "high_label": "High",
        "low_label": "Low",
        "change_pct_label": "Change %",
        "change_amount_label": "Change",
        "amplitude_label": "Amplitude",
        "volume_label": "Volume",
        "amount_label": "Turnover",
        "current_price_label": "Price",
        "volume_ratio_label": "Volume Ratio",
        "turnover_rate_label": "Turnover Rate",
        "source_label": "Source",
        "data_perspective_heading": "Data View",
        "ma_alignment_label": "MA Alignment",
        "bullish_alignment_label": "Bullish Alignment",
        "yes_label": "Yes",
        "no_label": "No",
        "none_label": "None",
        "trend_strength_label": "Trend Strength",
        "price_metrics_label": "Price Metrics",
        "ma5_label": "MA5",
        "ma10_label": "MA10",
        "ma20_label": "MA20",
        "bias_ma5_label": "Bias (MA5)",
        "support_level_label": "Support",
        "resistance_level_label": "Resistance",
        "chip_label": "Chip Structure",
        "phase_decision_heading": "Phase Decision Guardrail",
        "action_window_label": "Action Window",
        "immediate_action_label": "Current Action",
        "watch_conditions_label": "Watch Conditions",
        "next_check_time_label": "Next Check",
        "confidence_reason_label": "Confidence Reason",
        "data_limitations_label": "Data Limitations",
        "battle_plan_heading": "Battle Plan",
        "ideal_buy_label": "Ideal Entry",
        "secondary_buy_label": "Secondary Entry",
        "stop_loss_label": "Stop Loss",
        "take_profit_label": "Target",
        "suggested_position_label": "Position Size",
        "entry_plan_label": "Entry Plan",
        "risk_control_label": "Risk Control",
        "checklist_heading": "Checklist",
        "failed_checks_heading": "Failed Checks",
        "history_compare_heading": "Historical Signal Comparison",
        "time_label": "Time",
        "score_label": "Score",
        "advice_label": "Advice",
        "trend_label": "Trend",
        "generated_at_label": "Generated At",
        "report_time_label": "Generated",
        "no_results": "No analysis results",
        "report_title": "Stock Analysis Report",
        "avg_score_label": "Avg Score",
        "action_points_heading": "Action Levels",
        "position_advice_heading": "Position Advice",
        "analysis_model_label": "Model",
        "not_investment_advice": "AI-generated content for reference only. Not investment advice.",
        "details_report_hint": "See detailed report:",
        "financial_summary_heading": "Financial Summary",
        "report_date_label": "Report Date",
        "revenue_label": "Revenue",
        "net_profit_label": "Net Profit (Parent)",
        "operating_cash_flow_label": "Operating Cash Flow",
        "roe_label": "ROE",
        "revenue_yoy_label": "Revenue YoY",
        "net_profit_yoy_label": "Net Profit YoY",
        "gross_margin_label": "Gross Margin",
        "shareholder_return_heading": "Shareholder Return",
        "ttm_cash_dividend_label": "TTM Cash Dividend / Share (Pre-tax)",
        "ttm_event_count_label": "TTM Dividend Events",
        "ttm_dividend_yield_label": "TTM Dividend Yield",
        "latest_ex_dividend_label": "Latest Ex-dividend Date",
        "institutional_flow_heading": "Institutional Flows (3 Majors)",
        "institutional_flow_note": "Positive = net buy, negative = net sell; unit: shares.",
        "inst_foreign_label": "Foreign",
        "inst_trust_label": "Inv. Trust",
        "inst_dealer_label": "Dealer",
        "inst_total_label": "Total (3 Majors)",
        "related_boards_heading": "Related Boards",
        "industry_boards_heading": "Industry Sectors",
        "concept_boards_heading": "Concept Themes",
        "board_name_label": "Board",
        "board_type_label": "Type",
        "board_status_label": "Status",
        "board_change_pct_label": "Change %",
        "leading_board_label": "Leading",
        "lagging_board_label": "Lagging",
        "signal_attribution_heading": "Signal Attribution",
        "attribution_weights_label": "Attribution Weights",
        "technical_indicators_label": "Technical Indicators",
        "news_sentiment_label": "News Sentiment",
        "fundamentals_label": "Fundamentals",
        "market_conditions_label": "Market Conditions",
        "strongest_bullish_signal_label": "Strongest Bullish Signal",
        "strongest_bearish_signal_label": "Strongest Bearish Signal",
        "strategy_synthesis_heading": "Strategy Synthesis",
        "strategy_final_signal_label": "Final Signal",
        "strategy_consensus_level_label": "Consensus",
        "strategy_conflict_label": "Conflict",
        "strategy_confidence_label": "Confidence",
        "strategy_summary_label": "Summary",
        "strategy_supporting_skills_label": "Supporting Strategies",
        "strategy_opposing_skills_label": "Opposing Strategies",
        "strategy_invalid_opinions_label": "{count} additional strategies failed to produce valid signals",
    },
    "ko": {
        "dashboard_title": "결정 대시보드",
        "brief_title": "결정 브리핑",
        "analyzed_prefix": "분석 종목",
        "stock_unit": "개 종목",
        "stock_unit_compact": "개",
        "buy_label": "매수",
        "watch_label": "관망",
        "sell_label": "매도",
        "summary_heading": "분석 결과 요약",
        "info_heading": "핵심 업데이트",
        "sentiment_summary_label": "투자심리",
        "earnings_outlook_label": "실적 전망",
        "risk_alerts_label": "리스크 경보",
        "positive_catalysts_label": "긍정 촉매",
        "latest_news_label": "최신 뉴스",
        "core_conclusion_heading": "핵심 결론",
        "one_sentence_label": "한 줄 결론",
        "time_sensitivity_label": "시의성",
        "default_time_sensitivity": "이번 주",
        "position_status_label": "보유 상태",
        "action_advice_label": "대응 전략",
        "no_position_label": "미보유",
        "has_position_label": "보유 중",
        "continue_holding": "보유 유지",
        "market_snapshot_heading": "시세 스냅샷",
        "close_label": "종가",
        "prev_close_label": "전일 종가",
        "open_label": "시가",
        "high_label": "고가",
        "low_label": "저가",
        "change_pct_label": "등락률",
        "change_amount_label": "등락액",
        "amplitude_label": "변동폭",
        "volume_label": "거래량",
        "amount_label": "거래대금",
        "current_price_label": "현재가",
        "volume_ratio_label": "거래량비",
        "turnover_rate_label": "회전율",
        "source_label": "시세 출처",
        "data_perspective_heading": "데이터 분석",
        "ma_alignment_label": "이동평균 배열",
        "bullish_alignment_label": "정배열",
        "yes_label": "예",
        "no_label": "아니오",
        "none_label": "없음",
        "trend_strength_label": "추세 강도",
        "price_metrics_label": "가격 지표",
        "ma5_label": "MA5",
        "ma10_label": "MA10",
        "ma20_label": "MA20",
        "bias_ma5_label": "이격도(MA5)",
        "support_level_label": "지지선",
        "resistance_level_label": "저항선",
        "chip_label": "매물대",
        "phase_decision_heading": "장중 결정 가드레일",
        "action_window_label": "대응 시점",
        "immediate_action_label": "현재 행동",
        "watch_conditions_label": "관찰 조건",
        "next_check_time_label": "다음 점검",
        "confidence_reason_label": "신뢰도 근거",
        "data_limitations_label": "데이터 한계",
        "battle_plan_heading": "실행 계획",
        "ideal_buy_label": "이상적 매수가",
        "secondary_buy_label": "추가 매수가",
        "stop_loss_label": "손절가",
        "take_profit_label": "목표가",
        "suggested_position_label": "비중 제안",
        "entry_plan_label": "진입 전략",
        "risk_control_label": "리스크 관리",
        "checklist_heading": "체크리스트",
        "failed_checks_heading": "미충족 항목",
        "history_compare_heading": "과거 신호 비교",
        "time_label": "시간",
        "score_label": "점수",
        "advice_label": "제안",
        "trend_label": "추세",
        "generated_at_label": "생성 시각",
        "report_time_label": "생성",
        "no_results": "분석 결과 없음",
        "report_title": "종목 분석 리포트",
        "avg_score_label": "평균 점수",
        "action_points_heading": "대응 가격대",
        "position_advice_heading": "보유 전략",
        "analysis_model_label": "분석 모델",
        "not_investment_advice": "AI 생성 참고용이며 투자 권유가 아닙니다.",
        "details_report_hint": "상세 리포트 보기:",
        "financial_summary_heading": "재무 요약",
        "report_date_label": "보고 기준",
        "revenue_label": "매출액",
        "net_profit_label": "지배주주 순이익",
        "operating_cash_flow_label": "영업 현금흐름",
        "roe_label": "ROE",
        "revenue_yoy_label": "매출 전년比",
        "net_profit_yoy_label": "순이익 전년比",
        "gross_margin_label": "매출총이익률",
        "shareholder_return_heading": "주주 환원",
        "ttm_cash_dividend_label": "최근 12개월 주당 현금배당(세전)",
        "ttm_event_count_label": "최근 12개월 배당 횟수",
        "ttm_dividend_yield_label": "TTM 배당수익률",
        "latest_ex_dividend_label": "최근 배당락일",
        "institutional_flow_heading": "3대 기관 동향",
        "institutional_flow_note": "양수=순매수, 음수=순매도; 단위: 주.",
        "inst_foreign_label": "외국인",
        "inst_trust_label": "투신",
        "inst_dealer_label": "딜러",
        "inst_total_label": "3대 기관 합계",
        "related_boards_heading": "관련 섹터",
        "industry_boards_heading": "업종 섹터",
        "concept_boards_heading": "테마 섹터",
        "board_name_label": "섹터",
        "board_type_label": "유형",
        "board_status_label": "섹터 상태",
        "board_change_pct_label": "섹터 등락률",
        "leading_board_label": "강세",
        "lagging_board_label": "약세",
        "signal_attribution_heading": "신호 귀인 분석",
        "attribution_weights_label": "귀인 가중치",
        "technical_indicators_label": "기술 지표",
        "news_sentiment_label": "뉴스 심리",
        "fundamentals_label": "펀더멘털",
        "market_conditions_label": "시장 환경",
        "strongest_bullish_signal_label": "최강 상승 신호",
        "strongest_bearish_signal_label": "최강 하락 신호",
        "strategy_synthesis_heading": "전략 종합",
        "strategy_final_signal_label": "종합 신호",
        "strategy_consensus_level_label": "공감도",
        "strategy_conflict_label": "충돌",
        "strategy_confidence_label": "신뢰도",
        "strategy_summary_label": "종합 설명",
        "strategy_supporting_skills_label": "지지 전략",
        "strategy_opposing_skills_label": "반대 전략",
        "strategy_invalid_opinions_label": "추가로 {count}개 전략이 유효한 신호를 생성하지 못했습니다",
    },
    "tr": {
        "dashboard_title": "Karar Paneli",
        "brief_title": "Karar Özeti",
        "analyzed_prefix": "Analiz edilen",
        "stock_unit": "hisse",
        "stock_unit_compact": "hisse",
        "buy_label": "Al",
        "watch_label": "İzle",
        "sell_label": "Sat",
        "summary_heading": "Analiz Sonuç Özeti",
        "info_heading": "Önemli Gelişmeler",
        "sentiment_summary_label": "Piyasa Algısı",
        "earnings_outlook_label": "Kâr Beklentisi",
        "risk_alerts_label": "Risk Uyarıları",
        "positive_catalysts_label": "Olumlu Katalizörler",
        "latest_news_label": "Son Haberler",
        "core_conclusion_heading": "Temel Sonuç",
        "one_sentence_label": "Tek Cümlelik Sonuç",
        "time_sensitivity_label": "Zaman Hassasiyeti",
        "default_time_sensitivity": "Bu hafta",
        "position_status_label": "Pozisyon Durumu",
        "action_advice_label": "İşlem Önerisi",
        "no_position_label": "Pozisyon yok",
        "has_position_label": "Pozisyon var",
        "continue_holding": "Tutmaya devam",
        "market_snapshot_heading": "Piyasa Görünümü",
        "close_label": "Kapanış",
        "prev_close_label": "Önceki Kapanış",
        "open_label": "Açılış",
        "high_label": "En Yüksek",
        "low_label": "En Düşük",
        "change_pct_label": "Değişim %",
        "change_amount_label": "Değişim",
        "amplitude_label": "Gün İçi Aralık",
        "volume_label": "Hacim (adet)",
        "amount_label": "İşlem Hacmi",
        "current_price_label": "Güncel Fiyat",
        "volume_ratio_label": "Hacim Oranı",
        "turnover_rate_label": "Devir Hızı",
        "source_label": "Fiyat Kaynağı",
        "data_perspective_heading": "Veri Analizi",
        "ma_alignment_label": "Hareketli Ortalama Dizilimi",
        "bullish_alignment_label": "Yükseliş Dizilimi",
        "yes_label": "Evet",
        "no_label": "Hayır",
        "none_label": "Yok",
        "trend_strength_label": "Trend Gücü",
        "price_metrics_label": "Fiyat Göstergeleri",
        "ma5_label": "MA5",
        "ma10_label": "MA10",
        "ma20_label": "MA20",
        "bias_ma5_label": "Sapma (MA5)",
        "support_level_label": "Destek",
        "resistance_level_label": "Direnç",
        "chip_label": "Maliyet Dağılımı",
        "phase_decision_heading": "Seans İçi Karar Koruması",
        "action_window_label": "İşlem Zamanı",
        "immediate_action_label": "Şimdiki Aksiyon",
        "watch_conditions_label": "İzleme Koşulları",
        "next_check_time_label": "Sonraki Kontrol",
        "confidence_reason_label": "Güven Gerekçesi",
        "data_limitations_label": "Veri Sınırlamaları",
        "battle_plan_heading": "Uygulama Planı",
        "ideal_buy_label": "İdeal Alım",
        "secondary_buy_label": "İkincil Alım",
        "stop_loss_label": "Zarar Durdur",
        "take_profit_label": "Kâr Al",
        "suggested_position_label": "Önerilen Pozisyon",
        "entry_plan_label": "Giriş Planı",
        "risk_control_label": "Risk Yönetimi",
        "checklist_heading": "Kontrol Listesi",
        "failed_checks_heading": "Karşılanmayan Koşullar",
        "history_compare_heading": "Geçmiş Sinyal Karşılaştırması",
        "time_label": "Zaman",
        "score_label": "Puan",
        "advice_label": "Öneri",
        "trend_label": "Trend",
        "generated_at_label": "Oluşturulma",
        "report_time_label": "Oluşturuldu",
        "no_results": "Analiz sonucu yok",
        "report_title": "Hisse Analiz Raporu",
        "avg_score_label": "Ortalama Puan",
        "action_points_heading": "İşlem Seviyeleri",
        "position_advice_heading": "Pozisyon Stratejisi",
        "analysis_model_label": "Analiz Modeli",
        "not_investment_advice": "Yapay zekâ tarafından üretilmiştir, yalnızca bilgi amaçlıdır; yatırım tavsiyesi değildir.",
        "details_report_hint": "Ayrıntılı rapor:",
        "financial_summary_heading": "Finansal Özet",
        "report_date_label": "Rapor Dönemi",
        "revenue_label": "Hasılat",
        "net_profit_label": "Ana Ortaklık Net Kârı",
        "operating_cash_flow_label": "Faaliyet Nakit Akışı",
        "roe_label": "ROE",
        "revenue_yoy_label": "Hasılat Yıllık Değişim",
        "net_profit_yoy_label": "Net Kâr Yıllık Değişim",
        "gross_margin_label": "Brüt Kâr Marjı",
        "shareholder_return_heading": "Hissedar Getirisi",
        "ttm_cash_dividend_label": "Son 12 Ay Hisse Başı Nakit Temettü (vergi öncesi)",
        "ttm_event_count_label": "Son 12 Ay Temettü Sayısı",
        "ttm_dividend_yield_label": "Son 12 Ay Temettü Verimi",
        "latest_ex_dividend_label": "Son Hak Kullanım Tarihi",
        "institutional_flow_heading": "Üç Kurumsal Yatırımcı Grubu",
        "institutional_flow_note": "Pozitif = net alım, negatif = net satım; birim: adet.",
        "inst_foreign_label": "Yabancı",
        "inst_trust_label": "Yatırım Fonu",
        "inst_dealer_label": "Aracı Kurum",
        "inst_total_label": "Kurumsal Toplam",
        "related_boards_heading": "İlgili Sektörler",
        "industry_boards_heading": "Sektör Grupları",
        "concept_boards_heading": "Tema Grupları",
        "board_name_label": "Sektör",
        "board_type_label": "Tür",
        "board_status_label": "Sektör Durumu",
        "board_change_pct_label": "Sektör Değişim %",
        "leading_board_label": "Güçlü",
        "lagging_board_label": "Zayıf",
        "signal_attribution_heading": "Sinyal Kaynak Analizi",
        "attribution_weights_label": "Kaynak Ağırlıkları",
        "technical_indicators_label": "Teknik Göstergeler",
        "news_sentiment_label": "Haber Algısı",
        "fundamentals_label": "Temel Veriler",
        "market_conditions_label": "Piyasa Koşulları",
        "strongest_bullish_signal_label": "En Güçlü Yükseliş Sinyali",
        "strongest_bearish_signal_label": "En Güçlü Düşüş Sinyali",
        "strategy_synthesis_heading": "Strateji Sentezi",
        "strategy_final_signal_label": "Nihai Sinyal",
        "strategy_consensus_level_label": "Uzlaşı Düzeyi",
        "strategy_conflict_label": "Çelişki",
        "strategy_confidence_label": "Güven",
        "strategy_summary_label": "Özet",
        "strategy_supporting_skills_label": "Destekleyen Stratejiler",
        "strategy_opposing_skills_label": "Karşı Stratejiler",
        "strategy_invalid_opinions_label": "{count} strateji daha geçerli sinyal üretemedi",
    },
}

_DECISION_INTENT_NEGATIONS = (
    "不",
    "并非",
    "并未",
    "未",
    "没有",
    "无",
    "不是",
    "no ",
    "not ",
    " never",
)

_DECISION_INTENT_NEGATION_SCOPE_BREAK_CHARS = "，,。；;:!?！？"
_DECISION_INTENT_NEGATION_CONNECTORS = (
    "建议",
    "应",
    "应当",
    "宜",
    "先",
    "再",
    "暂",
    "暂时",
    "可",
    "可以",
    "需要",
    "需",
    "继续",
)


def _strip_decision_negation_connectors(text: str) -> str:
    """Remove common advisory connectors between a negation token and decision word."""
    suffix = text.strip()
    changed = True
    while changed:
        changed = False
        for connector in _DECISION_INTENT_NEGATION_CONNECTORS:
            if suffix.startswith(connector):
                suffix = suffix[len(connector):].strip()
                changed = True
                break
    return suffix


_TURKISH_NEGATED_VERB_SUFFIX = re.compile(r"m[ae](?!k|l[ıi])")


def has_turkish_negated_verb_suffix(text_after_marker: str) -> bool:
    """Return whether a Turkish verb marker is negated by its suffix.

    Turkish negates verbs with the ``-ma/-me`` suffix (``al`` -> ``almayın``),
    so prefix-based negation hints cannot see it. Infinitive ``-mak/-mek`` and
    necessity ``-malı/-meli`` are affirmative and are not treated as negation.
    """
    return bool(_TURKISH_NEGATED_VERB_SUFFIX.match(text_after_marker or ""))


def normalize_report_language(value: Optional[str], default: str = "zh") -> str:
    """Normalize report language to a supported short code."""
    candidate = (value or default).strip().lower().replace(" ", "_")
    candidate = _REPORT_LANGUAGE_ALIASES.get(candidate, candidate)
    if candidate in SUPPORTED_REPORT_LANGUAGES:
        return candidate
    return default


def is_supported_report_language_value(value: Optional[str]) -> bool:
    """Return whether the raw value is a supported language code or alias."""
    candidate = (value or "").strip().lower().replace(" ", "_")
    if not candidate:
        return False
    return candidate in SUPPORTED_REPORT_LANGUAGES or candidate in _REPORT_LANGUAGE_ALIASES


def get_report_labels(language: Optional[str]) -> Dict[str, str]:
    """Return UI copy for the selected report language."""
    normalized = normalize_report_language(language)
    return _REPORT_LABELS[normalized]


def get_placeholder_text(language: Optional[str]) -> str:
    """Return placeholder text for missing localized content."""
    return _PLACEHOLDER_BY_LANGUAGE[normalize_report_language(language)]


def get_unknown_text(language: Optional[str]) -> str:
    """Return localized unknown text."""
    return _UNKNOWN_BY_LANGUAGE[normalize_report_language(language)]


def get_no_data_text(language: Optional[str]) -> str:
    """Return localized data unavailable text."""
    return _NO_DATA_BY_LANGUAGE[normalize_report_language(language)]


def get_chip_unavailable_text(language: Optional[str]) -> str:
    """Return the localized one-line chip distribution fallback text."""
    return _CHIP_UNAVAILABLE_BY_LANGUAGE[normalize_report_language(language)]


def _normalize_lookup_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", " ").replace("-", " ")


def _register_lookup_aliases(canonical_map: Dict[str, str], aliases: Dict[str, str]) -> None:
    """Register aliases using the same normalization as runtime lookups.

    Turkish dotted capitals (``İ``) lower-case to ``i̇`` in Python, so the keys
    must go through ``_normalize_lookup_key`` instead of being hand-written.
    """
    for alias, canonical in aliases.items():
        canonical_map.setdefault(_normalize_lookup_key(alias), canonical)


# Turkish (tr) labels emitted by the LLM / localized UI, mapped back to canonical keys.
_register_lookup_aliases(_OPERATION_ADVICE_CANONICAL_MAP, {
    "Güçlü Al": "strong_buy", "Al": "buy", "Kademeli Al": "buy", "Pozisyon Artır": "buy",
    "Tut": "hold", "Tut ve İzle": "hold", "İzle": "watch", "Bekle": "watch",
    "Azalt": "reduce", "Pozisyon Azalt": "reduce", "Sat": "sell", "Güçlü Sat": "strong_sell",
})
_register_lookup_aliases(_TREND_PREDICTION_CANONICAL_MAP, {
    "Güçlü Yükseliş": "strong_bullish", "Yükseliş": "bullish", "Yatay": "sideways",
    "Düşüş": "bearish", "Güçlü Düşüş": "strong_bearish",
})
_register_lookup_aliases(_CONFIDENCE_LEVEL_CANONICAL_MAP, {"Yüksek": "high", "Orta": "medium", "Düşük": "low"})
_register_lookup_aliases(_STRATEGY_SIGNAL_CANONICAL_MAP, {
    "Güçlü Al": "strong_buy", "Al": "buy", "Tut": "hold", "Sat": "sell", "Güçlü Sat": "strong_sell",
})
_register_lookup_aliases(_CONSENSUS_LEVEL_CANONICAL_MAP, {
    "Yüksek": "high", "Orta": "medium", "Düşük": "low", "Yetersiz Kanıt": "insufficient",
})
_register_lookup_aliases(_CONFLICT_SEVERITY_CANONICAL_MAP, {"Yok": "none", "Düşük": "low", "Orta": "medium", "Yüksek": "high"})
_register_lookup_aliases(_CHIP_HEALTH_CANONICAL_MAP, {"Sağlıklı": "healthy", "Ortalama": "average", "Dikkat": "caution"})
_register_lookup_aliases(_BIAS_STATUS_CANONICAL_MAP, {"Güvenli": "safe", "Dikkat": "caution", "Tehlike": "danger"})


def _iter_lookup_candidates(value: Any) -> list[str]:
    raw_text = str(value or "").strip()
    if not raw_text:
        return []

    candidates = [raw_text]
    for part in re.split(r"[/|,，、]+", raw_text):
        normalized = part.strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


def _canonicalize_lookup_value(value: Any, canonical_map: Dict[str, str]) -> Optional[str]:
    for candidate in _iter_lookup_candidates(value):
        canonical = canonical_map.get(_normalize_lookup_key(candidate))
        if canonical:
            return canonical
    return None


def _first_non_negated_position(text: str, token: str) -> Optional[int]:
    if not text or not token:
        return None

    normalized_text = text.lower().strip()
    if any(ch in normalized_text for ch in "abcdefghijklmnopqrstuvwxyz"):
        # Turkish letters count as word characters so short tokens such as
        # ``sat``/``al`` never match inside ``satın``/``alış``.
        matches = list(
            re.finditer(
                rf"(?<![a-z0-9_çğıöşüâîû]){re.escape(token)}(?![a-z0-9_çğıöşüâîû])",
                normalized_text,
            )
        )
    else:
        matches = list(re.finditer(re.escape(token), normalized_text))

    for match in matches:
        prefix = normalized_text[: match.start()]
        if any(prefix.rstrip().endswith(neg) for neg in _DECISION_INTENT_NEGATIONS):
            continue
        lookback = prefix[-12:]
        negated = False
        for neg in _DECISION_INTENT_NEGATIONS:
            if not neg:
                continue
            neg_idx = lookback.rfind(neg)
            if neg_idx < 0:
                continue
            suffix = lookback[neg_idx + len(neg):]
            if not suffix:
                negated = True
                break
            if any(ch in suffix for ch in _DECISION_INTENT_NEGATION_SCOPE_BREAK_CHARS):
                continue
            normalized_suffix = _strip_decision_negation_connectors(suffix)
            if not normalized_suffix:
                negated = True
                break
            if any(ch in normalized_suffix for ch in _DECISION_INTENT_NEGATION_SCOPE_BREAK_CHARS):
                continue
            if len(normalized_suffix) > 6 and token not in normalized_suffix:
                continue
            if normalized_suffix.startswith(token):
                negated = True
                break
        if negated:
            continue
        else:
            return match.start()
    return None


def _is_placeholder_stock_name(value: Any, code: Any = None) -> bool:
    text = str(value or "").strip()
    if not text:
        return True

    lowered = text.lower()
    if lowered in {"n/a", "na", "none", "null", "unknown"}:
        return True
    if text in {"-", "—", "未知", "待补充"}:
        return True

    code_text = str(code or "").strip()
    if code_text and lowered == code_text.lower():
        return True

    return text.startswith("股票")


def _translate_from_map(
    value: Any,
    language: Optional[str],
    *,
    canonical_map: Dict[str, str],
    translations: Dict[str, Dict[str, str]],
) -> str:
    normalized_language = normalize_report_language(language)
    raw_text = str(value or "").strip()
    if not raw_text:
        return raw_text

    canonical = _canonicalize_lookup_value(raw_text, canonical_map)
    if canonical:
        return translations[canonical][normalized_language]
    return raw_text


def localize_operation_advice(value: Any, language: Optional[str]) -> str:
    """Translate operation advice between Chinese and English when recognized."""
    return _translate_from_map(
        value,
        language,
        canonical_map=_OPERATION_ADVICE_CANONICAL_MAP,
        translations=_OPERATION_ADVICE_TRANSLATIONS,
    )


def localize_trend_prediction(value: Any, language: Optional[str]) -> str:
    """Translate trend prediction between Chinese and English when recognized."""
    normalized_language = normalize_report_language(language)
    raw_text = str(value or "").strip()
    if not raw_text:
        return raw_text
    if normalized_language == "zh":
        if re.search(r"[\u4e00-\u9fff]", raw_text):
            return raw_text
    return _translate_from_map(
        value,
        normalized_language,
        canonical_map=_TREND_PREDICTION_CANONICAL_MAP,
        translations=_TREND_PREDICTION_TRANSLATIONS,
    )


def localize_confidence_level(value: Any, language: Optional[str]) -> str:
    """Translate confidence level between Chinese and English when recognized."""
    return _translate_from_map(
        value,
        language,
        canonical_map=_CONFIDENCE_LEVEL_CANONICAL_MAP,
        translations=_CONFIDENCE_LEVEL_TRANSLATIONS,
    )


def localize_strategy_signal(value: Any, language: Optional[str]) -> str:
    """Translate strategy signal labels when recognized."""
    return _translate_from_map(
        value,
        language,
        canonical_map=_STRATEGY_SIGNAL_CANONICAL_MAP,
        translations=_STRATEGY_SIGNAL_TRANSLATIONS,
    )


def localize_consensus_level(value: Any, language: Optional[str]) -> str:
    """Translate strategy consensus levels when recognized."""
    return _translate_from_map(
        value,
        language,
        canonical_map=_CONSENSUS_LEVEL_CANONICAL_MAP,
        translations=_CONSENSUS_LEVEL_TRANSLATIONS,
    )


def localize_conflict_severity(value: Any, language: Optional[str]) -> str:
    """Translate strategy conflict severity when recognized."""
    return _translate_from_map(
        value,
        language,
        canonical_map=_CONFLICT_SEVERITY_CANONICAL_MAP,
        translations=_CONFLICT_SEVERITY_TRANSLATIONS,
    )


def localize_strategy_skill(value: Any, language: Optional[str]) -> str:
    """Translate strategy skill names when recognized."""
    return _translate_from_map(
        value,
        language,
        canonical_map=_STRATEGY_SKILL_CANONICAL_MAP,
        translations=_STRATEGY_SKILL_TRANSLATIONS,
    )


def localize_chip_health(value: Any, language: Optional[str]) -> str:
    """Translate chip health labels between Chinese and English when recognized."""
    return _translate_from_map(
        value,
        language,
        canonical_map=_CHIP_HEALTH_CANONICAL_MAP,
        translations=_CHIP_HEALTH_TRANSLATIONS,
    )


def is_chip_placeholder_value(value: Any) -> bool:
    """Return True for chip fields filled with empty or no-data placeholders."""
    if value is None:
        return True
    if isinstance(value, (int, float)) and value == 0:
        return True
    text = str(value).strip()
    lowered = text.lower()
    if lowered in _CHIP_PLACEHOLDER_EXACT:
        return True
    return any(hint in lowered for hint in _CHIP_PLACEHOLDER_HINTS)


def is_chip_structure_unavailable(chip_data: Any) -> bool:
    """Detect chip_structure blocks that contain only unavailable placeholders."""
    if not isinstance(chip_data, dict) or not chip_data:
        return False
    for key in _CHIP_UNAVAILABLE_REASON_KEYS:
        raw = chip_data.get(key)
        if isinstance(raw, bool):
            if raw:
                return True
            continue
        if str(raw or "").strip():
            return True
    if any(key in chip_data for key in _CHIP_METRIC_KEYS):
        return all(is_chip_placeholder_value(chip_data.get(key)) for key in _CHIP_METRIC_KEYS)
    return all(is_chip_placeholder_value(value) for value in chip_data.values())


def localize_strategy_conflict_description(conflict_type: Any, language: Optional[str]) -> str:
    """Translate strategy conflict type into a display sentence at render boundaries."""
    lang = normalize_report_language(language)
    key = str(conflict_type or "").strip()
    translations = {
        "directional_opposition": {
            "zh": "策略方向出现对立：部分策略看多，部分策略看空，综合结论需要降低确定性。",
            "en": "Strategy directions diverge: some strategies are bullish while others are bearish, so conviction should be reduced.",
            "ko": "전략 방향이 엇갈립니다. 일부 전략은 상승을, 일부 전략은 하락을 보며 확신도를 낮춰야 합니다.",
            "tr": "Strateji yönleri ayrışıyor: bazı stratejiler yükseliş, bazıları düşüş bekliyor; güven düzeyi düşürülmeli.",
        },
        "wide_score_dispersion": {
            "zh": "策略信号分数分布较宽，说明多策略对行情结构存在明显分歧。",
            "en": "Strategy signal scores are widely dispersed, indicating meaningful disagreement on market structure.",
            "ko": "전략 신호 점수 분포가 넓어 시장 구조에 대한 전략 간 이견이 큽니다.",
            "tr": "Strateji sinyal puanları geniş bir aralığa dağılmış; stratejiler piyasa yapısı konusunda belirgin şekilde ayrışıyor.",
        },
        "high_confidence_dissent": {
            "zh": "存在高置信少数派策略与综合信号明显不一致，应保留反方观点。",
            "en": "A high-confidence minority strategy materially disagrees with the final signal and should be kept as a dissenting view.",
            "ko": "높은 확신도의 소수 전략이 종합 신호와 크게 달라 반대 관점으로 보존해야 합니다.",
            "tr": "Yüksek güvenli azınlık stratejiler nihai sinyalden belirgin şekilde ayrışıyor; karşı görüş olarak korunmalı.",
        },
        "adjustment_contradiction": {
            "zh": "策略加减分方向相互矛盾，说明不同策略对同一标的的边际评分分歧较大。",
            "en": "Strategy score adjustments contradict each other, showing large disagreement in marginal scoring.",
            "ko": "전략별 점수 조정 방향이 서로 충돌해 동일 종목의 한계 평가 차이가 큽니다.",
            "tr": "Stratejilerin puan düzeltme yönleri birbiriyle çelişiyor; aynı hisse için marjinal değerlendirmeler belirgin şekilde farklı.",
        },
    }
    localized = translations.get(key, {})
    return localized.get(lang) or localized.get("zh") or key


def normalize_strategy_synthesis_payload(value: Any) -> Dict[str, Any]:
    """Return a renderer-safe copy of a strategy synthesis payload.

    Historical records and external callers may contain pre-contract values.
    Renderers must treat a malformed top-level payload as absent and must not
    iterate malformed collection fields as strategy/conflict entries.
    """
    if not isinstance(value, dict) or not value:
        return {}

    payload = dict(value)
    for key in ("supporting_skills", "opposing_skills", "conflicts"):
        items = payload.get(key)
        payload[key] = (
            [item for item in items if isinstance(item, dict)]
            if isinstance(items, list)
            else []
        )
    return payload


def strategy_invalid_opinion_count(strategy_synthesis: Any) -> int:
    """Safely extract invalid_opinion_count from a possibly-malformed synthesis payload.

    Guards against `summary_params` being absent OR present-but-not-a-dict
    (e.g. a legacy string value).  `d.get(k, {})` only uses the default when
    the key is missing; if the key exists with a bad value it returns that value
    and the subsequent `.get()` crashes.  This helper eliminates that footgun
    for all renderers.
    """
    strategy_synthesis = normalize_strategy_synthesis_payload(strategy_synthesis)
    if not strategy_synthesis:
        return 0
    summary_params = strategy_synthesis.get("summary_params")
    if not isinstance(summary_params, dict):
        return 0
    count = summary_params.get("invalid_opinion_count")
    if isinstance(count, bool):
        return 0
    if isinstance(count, int):
        return count if count > 0 else 0
    if isinstance(count, str):
        normalized = count.strip()
        if normalized.isascii() and normalized.isdecimal():
            parsed = int(normalized)
            return parsed if parsed > 0 else 0
    return 0


def localize_strategy_synthesis_summary(strategy_synthesis: Any, language: Optional[str]) -> str:
    """Render a language-specific summary from the structured synthesis payload."""
    strategy_synthesis = normalize_strategy_synthesis_payload(strategy_synthesis)
    if not strategy_synthesis:
        return ""
    lang = normalize_report_language(language)
    summary_params = strategy_synthesis.get("summary_params")
    if not isinstance(summary_params, dict):
        summary_params = {}
    opinion_count = summary_params.get("opinion_count")
    if not isinstance(opinion_count, int):
        opinion_count = len(strategy_synthesis.get("supporting_skills") or []) + len(strategy_synthesis.get("opposing_skills") or [])
    final_signal = localize_strategy_signal(strategy_synthesis.get("final_signal"), lang)
    consensus_level = localize_consensus_level(strategy_synthesis.get("consensus_level"), lang)
    conflict_severity = localize_conflict_severity(strategy_synthesis.get("conflict_severity"), lang)
    conflict_count = strategy_synthesis.get("conflict_count", 0)
    if lang == "en":
        if conflict_count:
            base = f"Strategy synthesis from {opinion_count} strategies: final signal is {final_signal}, consensus level is {consensus_level}, conflict severity is {conflict_severity}."
        else:
            base = f"Strategy synthesis from {opinion_count} strategies: final signal is {final_signal}, consensus level is {consensus_level}, with no detected conflicts."
        return base
    if lang == "ko":
        if conflict_count:
            base = f"{opinion_count}개 전략의 종합 판단: 종합 신호는 {final_signal}, 공감도는 {consensus_level}, 충돌 강도는 {conflict_severity}입니다."
        else:
            base = f"{opinion_count}개 전략의 종합 판단: 종합 신호는 {final_signal}, 공감도는 {consensus_level}, 감지된 전략 충돌은 없습니다."
        return base
    if lang == "tr":
        if conflict_count:
            base = f"{opinion_count} stratejinin sentezi: nihai sinyal {final_signal}, uzlaşı düzeyi {consensus_level}, çelişki şiddeti {conflict_severity}."
        else:
            base = f"{opinion_count} stratejinin sentezi: nihai sinyal {final_signal}, uzlaşı düzeyi {consensus_level}, strateji çelişkisi tespit edilmedi."
        return base
    if conflict_count:
        base = f"来自 {opinion_count} 个策略的综合判断：综合信号为{final_signal}，共识度为{consensus_level}，冲突强度为{conflict_severity}。"
    else:
        base = f"来自 {opinion_count} 个策略的综合判断：综合信号为{final_signal}，共识度为{consensus_level}，未检测到策略冲突。"
    return base


def get_chip_unavailable_reason(value: Any, language: Optional[str]) -> str:
    """Return the explicit or default chip unavailable reason for rendering."""
    if not isinstance(value, dict) or not value:
        return ""
    for key in _CHIP_UNAVAILABLE_REASON_KEYS:
        raw = value.get(key)
        if isinstance(raw, bool):
            if raw:
                return get_chip_unavailable_text(language)
            continue
        text = str(raw or "").strip()
        if text:
            return text
    if is_chip_structure_unavailable(value):
        return get_chip_unavailable_text(language)
    return ""


def localize_bias_status(value: Any, language: Optional[str]) -> str:
    """Translate price bias status labels between Chinese and English when recognized."""
    return _translate_from_map(
        value,
        language,
        canonical_map=_BIAS_STATUS_CANONICAL_MAP,
        translations=_BIAS_STATUS_TRANSLATIONS,
    )


def get_bias_status_emoji(value: Any) -> str:
    """Return the stable alert emoji for a localized or canonical bias status."""
    canonical = _canonicalize_lookup_value(value, _BIAS_STATUS_CANONICAL_MAP)
    if canonical == "safe":
        return "✅"
    if canonical == "caution":
        return "⚠️"
    return "🚨"


def infer_decision_type_from_advice(value: Any, default: str = "hold") -> str:
    """Infer buy/hold/sell from human-readable operation advice."""
    canonical = _canonicalize_lookup_value(value, _OPERATION_ADVICE_CANONICAL_MAP)
    if canonical in {"strong_buy", "buy"}:
        return "buy"
    if canonical in {"reduce", "sell", "strong_sell"}:
        return "sell"
    if canonical in {"hold", "watch"}:
        return "hold"

    normalized_text = _normalize_lookup_key(value)
    best_position: Optional[int] = None
    best_canonical: Optional[str] = None
    for option, canonical in _OPERATION_ADVICE_CANONICAL_MAP.items():
        option_norm = _normalize_lookup_key(option)
        pos = _first_non_negated_position(normalized_text, option_norm)
        if pos is None:
            continue
        if best_position is None or pos < best_position:
            best_position = pos
            best_canonical = canonical

    if best_canonical in {"strong_buy", "buy"}:
        return "buy"
    if best_canonical in {"reduce", "sell", "strong_sell"}:
        return "sell"
    if best_canonical in {"hold", "watch"}:
        return "hold"

    return default


def get_signal_level(advice: Any, score: Any, language: Optional[str]) -> tuple[str, str, str]:
    """Return localized signal text, emoji, and stable color tag."""
    normalized_language = normalize_report_language(language)
    canonical = _canonicalize_lookup_value(advice, _OPERATION_ADVICE_CANONICAL_MAP)
    if canonical == "strong_buy":
        return (_OPERATION_ADVICE_TRANSLATIONS["strong_buy"][normalized_language], "💚", "strong_buy")
    if canonical == "buy":
        return (_OPERATION_ADVICE_TRANSLATIONS["buy"][normalized_language], "🟢", "buy")
    if canonical == "hold":
        return (_OPERATION_ADVICE_TRANSLATIONS["hold"][normalized_language], "🟡", "hold")
    if canonical == "watch":
        return (_OPERATION_ADVICE_TRANSLATIONS["watch"][normalized_language], "⚪", "watch")
    if canonical == "reduce":
        return (_OPERATION_ADVICE_TRANSLATIONS["reduce"][normalized_language], "🟠", "reduce")
    if canonical in {"sell", "strong_sell"}:
        return (_OPERATION_ADVICE_TRANSLATIONS["sell"][normalized_language], "🔴", "sell")

    try:
        numeric_score = int(float(score))
    except (TypeError, ValueError):
        numeric_score = 50

    score_signal = signal_key_for_score(numeric_score)
    if score_signal == "strong_buy":
        return (_OPERATION_ADVICE_TRANSLATIONS["strong_buy"][normalized_language], "💚", "strong_buy")
    if score_signal == "buy":
        return (_OPERATION_ADVICE_TRANSLATIONS["buy"][normalized_language], "🟢", "buy")
    if score_signal == "watch":
        return (_OPERATION_ADVICE_TRANSLATIONS["watch"][normalized_language], "⚪", "watch")
    if score_signal == "reduce":
        return (_OPERATION_ADVICE_TRANSLATIONS["reduce"][normalized_language], "🟠", "reduce")
    return (_OPERATION_ADVICE_TRANSLATIONS["sell"][normalized_language], "🔴", "sell")


def get_localized_stock_name(value: Any, code: Any, language: Optional[str]) -> str:
    """Return a localized stock name placeholder when the original name is missing."""
    raw_text = str(value or "").strip()
    if not _is_placeholder_stock_name(raw_text, code):
        return raw_text
    return _GENERIC_STOCK_NAME_BY_LANGUAGE[normalize_report_language(language)]


def get_sentiment_label(score: int, language: Optional[str]) -> str:
    """Return localized sentiment label by score band."""
    normalized = normalize_report_language(language)
    if normalized == "en":
        if score >= 80:
            return "Very Bullish"
        if score >= 60:
            return "Bullish"
        if score >= 40:
            return "Neutral"
        if score >= 20:
            return "Bearish"
        return "Very Bearish"

    if normalized == "ko":
        if score >= 80:
            return "매우 낙관"
        if score >= 60:
            return "낙관"
        if score >= 40:
            return "중립"
        if score >= 20:
            return "비관"
        return "매우 비관"

    if normalized == "tr":
        if score >= 80:
            return "Çok İyimser"
        if score >= 60:
            return "İyimser"
        if score >= 40:
            return "Nötr"
        if score >= 20:
            return "Kötümser"
        return "Çok Kötümser"

    if score >= 80:
        return "极度乐观"
    if score >= 60:
        return "乐观"
    if score >= 40:
        return "中性"
    if score >= 20:
        return "悲观"
    return "极度悲观"
