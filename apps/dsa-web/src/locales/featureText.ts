import type { BacktestPhaseFilter } from '../types/backtest';
import type { AlertTargetScope, AlertType, MarketLightStatus, MarketRegion, PortfolioStopLossMode } from '../types/alerts';
import type { PortfolioCashDirection, PortfolioCorporateActionType, PortfolioSide } from '../types/portfolio';
import type { UiLanguage } from '../i18n/uiText';

type Option<T extends string = string> = { value: T; label: string };
const alertTypes: AlertType[] = ['price_cross', 'price_change_percent', 'volume_spike', 'ma_price_cross', 'rsi_threshold', 'macd_cross', 'kdj_cross', 'cci_threshold', 'portfolio_stop_loss', 'portfolio_concentration', 'portfolio_drawdown', 'portfolio_price_stale', 'market_light_status', 'market_light_score_drop'];
const symbolAlertTypes = alertTypes.slice(0, 8);
const portfolioAlertTypes = alertTypes.slice(8, 12);
const marketAlertTypes = alertTypes.slice(12);

const BACKTEST_TEXT_EN = {
  documentTitle: 'Strategy Backtest - DSA',
  codePlaceholder: 'Filter by stock code (leave empty for all)',
  filter: 'Filter',
  evalWindow: 'Evaluation window',
  phase: 'Phase',
  startDate: 'Start date',
  startDateAria: 'Analysis start date',
  endDate: 'End date',
  endDateAria: 'Analysis end date',
  oneDayValidation: '1D validation',
  forceRerun: 'Force rerun',
  running: 'Backtesting...',
  runBacktest: 'Run backtest',
  oneDayModeDescription: '1D validation checks AI predictions against the next trading day close.',
  windowModeDescription: 'Set the evaluation window to 1 to compare AI predictions with the next trading day close.',
  overallPerformance: 'Overall performance',
  noMetricsTitle: 'No metrics',
  noMetricsDescription: 'Portfolio-level performance metrics appear after a backtest runs.',
  loadingResults: 'Loading results...',
  noResultsTitle: 'No results',
  noResultsDescription: 'Run a backtest to evaluate historical analysis accuracy.',
  nextDayValidation: 'Next-day validation',
  resultSet: 'Result set',
  allStocks: 'All stocks',
  filteredStock: 'Filtered {code}',
  dayWindow: '{days}-day window',
  fromDate: 'from {date}',
  toDate: 'to {date}',
  scrollHint: 'Scroll horizontally on small screens',
  stock: 'Stock',
  analysisDate: 'Analysis date',
  aiPrediction: 'AI prediction',
  actualPerformance: 'Actual performance',
  windowReturn: 'Window return',
  accuracy: 'Accuracy',
  directionMatch: 'Direction match',
  result: 'Result',
  status: 'Status',
  totalPage: '{total} results · Page {page} / {pages}',
  directionAccuracy: 'Direction accuracy',
  winRate: 'Win rate',
  avgSimulatedReturn: 'Avg simulated return',
  avgStockReturn: 'Avg stock return',
  stopLossTriggerRate: 'Stop-loss trigger rate',
  takeProfitTriggerRate: 'Take-profit trigger rate',
  avgDaysToFirstHit: 'Avg days to first hit',
  evaluationCount: 'Evaluations',
  outcomeSummary: 'Win / Loss / Neutral',
  phaseDistribution: 'Phase breakdown: {text}',
  processed: 'Processed:',
  saved: 'Saved:',
  completed: 'Completed:',
  insufficient: 'Insufficient:',
  errors: 'Errors:',
  yes: 'Yes',
  no: 'No',
  unknown: 'Unknown',
} as const;

export const BACKTEST_TEXT: Record<UiLanguage, Record<keyof typeof BACKTEST_TEXT_EN, string>> = {
  zh: { documentTitle: '策略回测 - DSA', codePlaceholder: '按股票代码筛选（留空表示全部）', filter: '筛选', evalWindow: '评估窗口', phase: '阶段', startDate: '开始日期', startDateAria: '分析开始日期', endDate: '结束日期', endDateAria: '分析结束日期', oneDayValidation: '1 日验证', forceRerun: '强制重跑', running: '回测中...', runBacktest: '运行回测', oneDayModeDescription: '1 日验证模式会用下一个交易日收盘表现校验 AI 预测。', windowModeDescription: '将评估窗口设为 1，可查看 AI 预测与下一个交易日收盘表现的匹配情况。', overallPerformance: '整体表现', noMetricsTitle: '暂无指标', noMetricsDescription: '运行回测后会生成组合级表现指标。', loadingResults: '正在加载结果...', noResultsTitle: '暂无结果', noResultsDescription: '运行回测后可评估历史分析准确性。', nextDayValidation: '次日验证', resultSet: '结果集', allStocks: '全部股票', filteredStock: '筛选 {code}', dayWindow: '{days} 日窗口', fromDate: '自 {date}', toDate: '至 {date}', scrollHint: '小屏幕可横向滚动', stock: '股票', analysisDate: '分析日期', aiPrediction: 'AI 预测', actualPerformance: '实际表现', windowReturn: '窗口收益', accuracy: '准确性', directionMatch: '方向匹配', result: '结果', status: '状态', totalPage: '共 {total} 条结果 · 第 {page} / {pages} 页', directionAccuracy: '方向准确率', winRate: '胜率', avgSimulatedReturn: '平均模拟收益', avgStockReturn: '平均个股收益', stopLossTriggerRate: '止损触发率', takeProfitTriggerRate: '止盈触发率', avgDaysToFirstHit: '平均命中天数', evaluationCount: '评估数', outcomeSummary: '盈 / 亏 / 中', phaseDistribution: '阶段分布：{text}', processed: '已处理:', saved: '已保存:', completed: '已完成:', insufficient: '数据不足:', errors: '错误:', yes: '是', no: '否', unknown: '未知' },
  en: BACKTEST_TEXT_EN,
  tr: {
    documentTitle: 'Strateji Geriye Dönük Testi - DSA',
    codePlaceholder: 'Sembole göre filtrele (tümü için boş bırakın)',
    filter: 'Filtrele',
    evalWindow: 'Değerlendirme penceresi',
    phase: 'Seans fazı',
    startDate: 'Başlangıç tarihi',
    startDateAria: 'Analiz başlangıç tarihi',
    endDate: 'Bitiş tarihi',
    endDateAria: 'Analiz bitiş tarihi',
    oneDayValidation: '1G doğrulama',
    forceRerun: 'Yeniden çalıştır',
    running: 'Test ediliyor...',
    runBacktest: 'Testi Çalıştır',
    oneDayModeDescription: '1G doğrulama modu AI tahminlerini bir sonraki işlem günü kapanışıyla karşılaştırır.',
    windowModeDescription: 'Sonraki işlem günü kapanışı ile karşılaştırmak için pencereyi 1 gün seçin.',
    overallPerformance: 'Genel Performans',
    noMetricsTitle: 'Henüz metrik yok',
    noMetricsDescription: 'Geriye dönük test çalıştırıldıktan sonra portföy metrikleri burada görünür.',
    loadingResults: 'Sonuçlar yükleniyor...',
    noResultsTitle: 'Henüz sonuç yok',
    noResultsDescription: 'Geçmiş analiz isabetini ölçmek için geriye dönük test çalıştırın.',
    nextDayValidation: 'Ertesi gün doğrulaması',
    resultSet: 'Sonuç seti',
    allStocks: 'Tüm hisseler',
    filteredStock: 'Filtre: {code}',
    dayWindow: '{days} günlük pencere',
    fromDate: '{date} tarihinden',
    toDate: '{date} tarihine',
    scrollHint: 'Küçük ekranda yatay kaydırın',
    stock: 'Hisse',
    analysisDate: 'Analiz tarihi',
    aiPrediction: 'AI Tahmini',
    actualPerformance: 'Gerçekleşen',
    windowReturn: 'Pencere getirisi',
    accuracy: 'İsabet',
    directionMatch: 'Yön eşleşmesi',
    result: 'Sonuç',
    status: 'Durum',
    totalPage: '{total} sonuç · Sayfa {page} / {pages}',
    directionAccuracy: 'Yön isabet oranı',
    winRate: 'Kazanma oranı',
    avgSimulatedReturn: 'Ort. simüle getiri',
    avgStockReturn: 'Ort. hisse getirisi',
    stopLossTriggerRate: 'Zarar kes tetiklenme oranı',
    takeProfitTriggerRate: 'Kâr al tetiklenme oranı',
    avgDaysToFirstHit: 'İlk hedefe ort. gün',
    evaluationCount: 'Değerlendirme',
    outcomeSummary: 'Kazanç / Kayıp / Nötr',
    phaseDistribution: 'Faz dağılımı: {text}',
    processed: 'İşlenen:',
    saved: 'Kaydedilen:',
    completed: 'Tamamlanan:',
    insufficient: 'Yetersiz:',
    errors: 'Hata:',
    yes: 'Evet',
    no: 'Hayır',
    unknown: 'Bilinmiyor',
  },
};

export const BACKTEST_PHASE_FILTER_OPTIONS: Record<UiLanguage, Array<Option<BacktestPhaseFilter>>> = {
  zh: [{ value: 'all', label: '全部阶段' }, { value: 'premarket', label: '盘前' }, { value: 'intraday', label: '盘中' }, { value: 'postmarket', label: '盘后' }, { value: 'unknown', label: '未知' }],
  en: [{ value: 'all', label: 'All phases' }, { value: 'premarket', label: 'Pre-market' }, { value: 'intraday', label: 'Intraday' }, { value: 'postmarket', label: 'Post-market' }, { value: 'unknown', label: 'Unknown' }],
  tr: [{ value: 'all', label: 'Tüm fazlar' }, { value: 'premarket', label: 'Seans öncesi' }, { value: 'intraday', label: 'Seans içi' }, { value: 'postmarket', label: 'Seans sonrası' }, { value: 'unknown', label: 'Bilinmiyor' }],
};
export const BACKTEST_PHASE_LABELS: Record<UiLanguage, Record<string, string>> = {
  zh: { premarket: '盘前', intraday: '盘中', postmarket: '盘后', unknown: '未知' },
  en: { premarket: 'Pre-market', intraday: 'Intraday', postmarket: 'Post-market', unknown: 'Unknown' },
  tr: { premarket: 'Seans öncesi', intraday: 'Seans içi', postmarket: 'Seans sonrası', unknown: 'Bilinmiyor' },
};
export const BACKTEST_OUTCOME_LABELS: Record<UiLanguage, Record<string, string>> = {
  zh: { win: '盈利', loss: '亏损', neutral: '中性' },
  en: { win: 'Win', loss: 'Loss', neutral: 'Neutral' },
  tr: { win: 'Kazanç', loss: 'Kayıp', neutral: 'Nötr' },
};
export const BACKTEST_STATUS_LABELS: Record<UiLanguage, Record<string, string>> = {
  zh: { completed: '已完成', insufficient: '数据不足', insufficient_data: '数据不足', error: '错误' },
  en: { completed: 'Completed', insufficient: 'Insufficient data', insufficient_data: 'Insufficient data', error: 'Error' },
  tr: { completed: 'Tamamlandı', insufficient: 'Yetersiz veri', insufficient_data: 'Yetersiz veri', error: 'Hata' },
};
export const BACKTEST_MOVEMENT_LABELS: Record<UiLanguage, Record<string, string>> = {
  zh: { up: '上涨', down: '下跌', flat: '持平' },
  en: { up: 'Up', down: 'Down', flat: 'Flat' },
  tr: { up: 'Yükseliş', down: 'Düşüş', flat: 'Yatay' },
};
export const BACKTEST_DIRECTION_EXPECTED_LABELS: Record<UiLanguage, Record<string, string>> = {
  zh: { long: '做多', cash: '空仓', up: '看涨', down: '看跌', not_down: '不看跌', flat: '持平' },
  en: { long: 'Long', cash: 'Cash', up: 'Bullish', down: 'Bearish', not_down: 'Not bearish', flat: 'Flat' },
  tr: { long: 'Alım (Long)', cash: 'Nakit', up: 'Boğa', down: 'Ayı', not_down: 'Düşüş beklemiyor', flat: 'Yatay' },
};

export const ALERT_TYPE_LABELS: Record<UiLanguage, Record<AlertType, string>> = {
  zh: { price_cross: '价格突破', price_change_percent: '涨跌幅', volume_spike: '成交量放大', ma_price_cross: '价格均线穿越', rsi_threshold: 'RSI 阈值', macd_cross: 'MACD 金叉/死叉', kdj_cross: 'KDJ 金叉/死叉', cci_threshold: 'CCI 阈值', portfolio_stop_loss: '组合止损', portfolio_concentration: '组合集中度', portfolio_drawdown: '组合回撤', portfolio_price_stale: '组合价格状态', market_light_status: '大盘红绿灯状态', market_light_score_drop: '大盘红绿灯分数下降' },
  en: { price_cross: 'Price crossing', price_change_percent: 'Price change', volume_spike: 'Volume spike', ma_price_cross: 'Price/MA crossing', rsi_threshold: 'RSI threshold', macd_cross: 'MACD cross', kdj_cross: 'KDJ cross', cci_threshold: 'CCI threshold', portfolio_stop_loss: 'Portfolio stop loss', portfolio_concentration: 'Portfolio concentration', portfolio_drawdown: 'Portfolio drawdown', portfolio_price_stale: 'Portfolio price status', market_light_status: 'Market traffic light status', market_light_score_drop: 'Market traffic light score drop' },
  tr: { price_cross: 'Fiyat kesişimi', price_change_percent: 'Fiyat değişimi (%)', volume_spike: 'Hacim sıçraması', ma_price_cross: 'Fiyat/Hareketli Ort. kesişimi', rsi_threshold: 'RSI eşiği', macd_cross: 'MACD kesişimi', kdj_cross: 'KDJ kesişimi', cci_threshold: 'CCI eşiği', portfolio_stop_loss: 'Portföy zarar kes', portfolio_concentration: 'Portföy yoğunlaşma', portfolio_drawdown: 'Portföy düşüşü (Drawdown)', portfolio_price_stale: 'Portföy fiyat durumu', market_light_status: 'Piyasa trafik ışığı durumu', market_light_score_drop: 'Piyasa skoru düşüşü' },
};
export const ALERT_SEVERITY_LABELS: Record<UiLanguage, Record<string, string>> = {
  zh: { info: '提示', warning: '警告', critical: '严重' },
  en: { info: 'Info', warning: 'Warning', critical: 'Critical' },
  tr: { info: 'Bilgi', warning: 'Uyarı', critical: 'Kritik' },
};
export const ALERT_SCOPE_LABELS: Record<UiLanguage, Record<AlertTargetScope, string>> = {
  zh: { single_symbol: '单标的', watchlist: '自选股', portfolio_holdings: '持仓标的', portfolio_account: '持仓账户', market: '大盘市场' },
  en: { single_symbol: 'Single symbol', watchlist: 'Watchlist', portfolio_holdings: 'Portfolio holdings', portfolio_account: 'Portfolio account', market: 'Market' },
  tr: { single_symbol: 'Tek hisse', watchlist: 'İzleme listesi', portfolio_holdings: 'Portföy varlıkları', portfolio_account: 'Portföy hesabı', market: 'Genel piyasa' },
};
export const ALERT_MARKET_REGION_LABELS: Record<UiLanguage, Record<MarketRegion, string>> = {
  zh: { cn: 'A 股', hk: '港股', us: '美股' },
  en: { cn: 'A-shares', hk: 'Hong Kong', us: 'US' },
  tr: { cn: 'Çin A', hk: 'Hong Kong', us: 'ABD' },
};
export const ALERT_MARKET_LIGHT_STATUS_LABELS: Record<UiLanguage, Record<MarketLightStatus, string>> = {
  zh: { yellow: '黄灯', red: '红灯' },
  en: { yellow: 'Yellow', red: 'Red' },
  tr: { yellow: 'Sarı', red: 'Kırmızı' },
};
export const ALERT_DIRECTION_LABELS = {
  zh: { abovePrice: '上破', belowPrice: '下破', upChange: '上涨', downChange: '下跌', aboveThreshold: '上穿', belowThreshold: '下穿', bullishCross: '金叉', bearishCross: '死叉', stopLossNear: '接近止损', stopLossBreach: '已触发止损' },
  en: { abovePrice: 'above', belowPrice: 'below', upChange: 'up', downChange: 'down', aboveThreshold: 'above', belowThreshold: 'below', bullishCross: 'bullish cross', bearishCross: 'bearish cross', stopLossNear: 'Near stop loss', stopLossBreach: 'Stop loss breached' },
  tr: { abovePrice: 'üzerine çıktı', belowPrice: 'altına indi', upChange: 'artış', downChange: 'düşüş', aboveThreshold: 'yukarı kesti', belowThreshold: 'aşağı kesti', bullishCross: 'altın kesişim', bearishCross: 'ölüm kesişimi', stopLossNear: 'Zarar kes yakını', stopLossBreach: 'Zarar kes ihlal edildi' },
} as const;
export const ALERT_LIST_TEXT = {
  zh: { title: '告警规则', subtitle: '{total} 条规则', enabledFilter: '启停状态', alertTypeFilter: '规则类型', loadingRules: '正在加载规则', emptyTitle: '暂无告警规则', emptyDescription: '创建规则后，后台评估任务会按轮询周期处理已启用的告警。', rule: '规则', target: '目标', type: '类型', parameters: '参数', status: '状态', cooldown: '冷却', updatedAt: '更新时间', action: '操作', source: '来源：{source}', allAccounts: '全部账户', accountTarget: '账户 {target}', enabled: '已启用', disabled: '已停用', coolingDown: '冷却中', notCoolingDown: '未冷却', childTargetCooldown: '子目标见触发历史', test: '测试', testing: '测试中', disabling: '停用中', enabling: '启用中', disable: '停用', enable: '启用', delete: '删除', cancel: '取消', scoreDropAtLeast: 'Score 下降 >= {value}', deleteAria: '删除 {name}', deleteTitle: '删除告警规则', deleteMessage: '确认删除「{name}」吗？该操作不会删除已有触发历史。' },
  en: { title: 'Alert rules', subtitle: '{total} rules', enabledFilter: 'Status', alertTypeFilter: 'Rule type', loadingRules: 'Loading rules', emptyTitle: 'No alert rules', emptyDescription: 'After rules are created, background evaluation processes enabled alerts on the polling schedule.', rule: 'Rule', target: 'Target', type: 'Type', parameters: 'Parameters', status: 'Status', cooldown: 'Cooldown', updatedAt: 'Updated', action: 'Actions', source: 'Source: {source}', allAccounts: 'All accounts', accountTarget: 'Account {target}', enabled: 'Enabled', disabled: 'Disabled', coolingDown: 'Cooling down', notCoolingDown: 'Not cooling down', childTargetCooldown: 'Per-target cooldowns are in trigger history', test: 'Test', testing: 'Testing', disabling: 'Disabling', enabling: 'Enabling', disable: 'Disable', enable: 'Enable', delete: 'Delete', cancel: 'Cancel', scoreDropAtLeast: 'Score drop >= {value}', deleteAria: 'Delete {name}', deleteTitle: 'Delete alert rule', deleteMessage: 'Delete "{name}"? Existing trigger history will be kept.' },
  tr: { title: 'Alarm Kuralları', subtitle: '{total} kural', enabledFilter: 'Durum', alertTypeFilter: 'Kural tipi', loadingRules: 'Kurallar yükleniyor', emptyTitle: 'Alarm kuralı yok', emptyDescription: 'Kural oluşturulduğunda arka plan değerlendiricisi etkin alarmları periyodik olarak denetler.', rule: 'Kural', target: 'Hedef', type: 'Tip', parameters: 'Parametreler', status: 'Durum', cooldown: 'Bekleme', updatedAt: 'Güncelleme', action: 'İşlem', source: 'Kaynak: {source}', allAccounts: 'Tüm hesaplar', accountTarget: 'Hesap {target}', enabled: 'Etkin', disabled: 'Devre dışı', coolingDown: 'Beklemede', notCoolingDown: 'Hazır', childTargetCooldown: 'Hedef bazlı bekleme tetik geçmişinde', test: 'Test Et', testing: 'Test ediliyor', disabling: 'Durduruluyor', enabling: 'Etkinleştiriliyor', disable: 'Durdur', enable: 'Etkinleştir', delete: 'Sil', cancel: 'İptal', scoreDropAtLeast: 'Skor düşüşü >= {value}', deleteAria: 'Sil {name}', deleteTitle: 'Alarm kuralını sil', deleteMessage: '"{name}" kuralı silinsin mi? Geçmiş tetikleme kayıtları korunur.' },
} as const;
export const ALERT_ENABLED_FILTER_OPTIONS: Record<UiLanguage, Array<Option<'all' | 'enabled' | 'disabled'>>> = {
  zh: [{ value: 'all', label: '全部状态' }, { value: 'enabled', label: '已启用' }, { value: 'disabled', label: '已停用' }],
  en: [{ value: 'all', label: 'All statuses' }, { value: 'enabled', label: 'Enabled' }, { value: 'disabled', label: 'Disabled' }],
  tr: [{ value: 'all', label: 'Tüm durumlar' }, { value: 'enabled', label: 'Etkin' }, { value: 'disabled', label: 'Devre dışı' }],
};
export const ALERT_TYPE_FILTER_OPTIONS: Record<UiLanguage, Array<Option<'all' | AlertType>>> = {
  zh: [{ value: 'all', label: '全部类型' }, ...alertTypes.map((value) => ({ value, label: ALERT_TYPE_LABELS.zh[value] }))],
  en: [{ value: 'all', label: 'All types' }, ...alertTypes.map((value) => ({ value, label: ALERT_TYPE_LABELS.en[value] }))],
  tr: [{ value: 'all', label: 'Tüm tipler' }, ...alertTypes.map((value) => ({ value, label: ALERT_TYPE_LABELS.tr[value] }))],
};
export const ALERT_FORM_TEXT = {
  zh: { accountLoadFailed: '账户加载失败', allAccounts: '全部账户', cardTitle: '创建告警规则', cardSubtitle: 'Web 告警中心', ruleName: '规则名称', ruleNamePlaceholder: '可选，例如 茅台价格突破', targetScope: '目标范围', targetCode: '标的代码', target: '目标', marketRegion: '市场区域', account: '账户', ruleType: '规则类型', severity: '严重级别', direction: '方向', priceThreshold: '价格阈值', changePctThreshold: '涨跌幅阈值（%）', volumeMultiplier: '成交量放大倍数', crossDirection: '交叉方向', thresholdDirection: '阈值方向', maDirection: '穿越方向', maWindow: '均线周期', rsiPeriod: 'RSI 周期', rsiThreshold: 'RSI 阈值', fastPeriod: '快线周期', slowPeriod: '慢线周期', signalPeriod: '信号周期', kdjPeriod: 'KDJ 周期', kPeriod: 'K 平滑周期', dPeriod: 'D 平滑周期', cciPeriod: 'CCI 周期', cciThreshold: 'CCI 阈值', stopLossMode: '止损模式', triggerStatus: '触发状态', scoreDropThreshold: 'Score 下降阈值', enableAfterCreate: '创建后立即启用', creating: '创建中...', create: '创建规则', positiveNumber: '{label}必须是大于 0 的数字', integerRange: '{label}必须是 {min} 到 {max} 的整数', required: '{label}不能为空', finiteNumber: '{label}必须是有效数字', rsiRange: 'RSI 阈值必须在 0 到 100 之间', requiredBarsLimit: '{label} 周期组合需要 {requiredBars} 根日线，最多支持 {max} 根', fastLessThanSlow: '快线周期必须小于慢线周期', noMarketStatus: '至少选择一个红绿灯状态', invalidStockCode: '股票代码格式不正确' },
  en: { accountLoadFailed: 'Account loading failed', allAccounts: 'All accounts', cardTitle: 'Create alert rule', cardSubtitle: 'Web alert center', ruleName: 'Rule name', ruleNamePlaceholder: 'Optional, e.g. Moutai price crossing', targetScope: 'Target scope', targetCode: 'Symbol', target: 'Target', marketRegion: 'Market region', account: 'Account', ruleType: 'Rule type', severity: 'Severity', direction: 'Direction', priceThreshold: 'Price threshold', changePctThreshold: 'Change threshold (%)', volumeMultiplier: 'Volume multiplier', crossDirection: 'Cross direction', thresholdDirection: 'Threshold direction', maDirection: 'Cross direction', maWindow: 'MA window', rsiPeriod: 'RSI period', rsiThreshold: 'RSI threshold', fastPeriod: 'Fast period', slowPeriod: 'Slow period', signalPeriod: 'Signal period', kdjPeriod: 'KDJ period', kPeriod: 'K smoothing period', dPeriod: 'D smoothing period', cciPeriod: 'CCI period', cciThreshold: 'CCI threshold', stopLossMode: 'Stop-loss mode', triggerStatus: 'Trigger status', scoreDropThreshold: 'Score drop threshold', enableAfterCreate: 'Enable immediately', creating: 'Creating...', create: 'Create rule', positiveNumber: '{label} must be a number greater than 0', integerRange: '{label} must be an integer from {min} to {max}', required: '{label} is required', finiteNumber: '{label} must be a valid number', rsiRange: 'RSI threshold must be between 0 and 100', requiredBarsLimit: '{label} requires {requiredBars} daily bars, up to {max} are supported', fastLessThanSlow: 'Fast period must be less than slow period', noMarketStatus: 'Select at least one traffic light status', invalidStockCode: 'Invalid stock code format' },
  tr: { accountLoadFailed: 'Hesaplar yüklenemedi', allAccounts: 'Tüm hesaplar', cardTitle: 'Alarm Kuralı Oluştur', cardSubtitle: 'Web Alarm Merkezi', ruleName: 'Kural adı', ruleNamePlaceholder: 'Opsiyonel, örn. NVDA fiyat kırılımı', targetScope: 'Hedef kapsamı', targetCode: 'Sembol', target: 'Hedef', marketRegion: 'Piyasa bölgesi', account: 'Hesap', ruleType: 'Kural tipi', severity: 'Önem derecesi', direction: 'Yön', priceThreshold: 'Fiyat eşiği', changePctThreshold: 'Değişim eşiği (%)', volumeMultiplier: 'Hacim çarpanı', crossDirection: 'Kesişim yönü', thresholdDirection: 'Eşik yönü', maDirection: 'Kesişim yönü', maWindow: 'HO penceresi', rsiPeriod: 'RSI periyodu', rsiThreshold: 'RSI eşiği', fastPeriod: 'Hızlı periyot', slowPeriod: 'Yavaş periyot', signalPeriod: 'Sinyal periyodu', kdjPeriod: 'KDJ periyodu', kPeriod: 'K düzeltme periyodu', dPeriod: 'D düzeltme periyodu', cciPeriod: 'CCI periyodu', cciThreshold: 'CCI eşiği', stopLossMode: 'Zarar kes modu', triggerStatus: 'Tetiklenme durumu', scoreDropThreshold: 'Skor düşüş eşiği', enableAfterCreate: 'Oluşturunca hemen etkinleştir', creating: 'Oluşturuluyor...', create: 'Kural Oluştur', positiveNumber: '{label} 0 dan büyük bir sayı olmalıdır', integerRange: '{label} {min} ile {max} arasında tam sayı olmalıdır', required: '{label} zorunludur', finiteNumber: '{label} geçerli bir sayı olmalıdır', rsiRange: 'RSI eşiği 0 ile 100 arasında olmalıdır', requiredBarsLimit: '{label} için {requiredBars} günlük bar gerekir (en fazla {max})', fastLessThanSlow: 'Hızlı periyot yavaş periyottan küçük olmalıdır', noMarketStatus: 'En az bir trafik ışığı durumu seçin', invalidStockCode: 'Geçersiz hisse kodu formatı' },
} as const;
export const ALERT_SYMBOL_TYPE_OPTIONS: Record<UiLanguage, Array<Option<AlertType>>> = {
  zh: symbolAlertTypes.map((value) => ({ value, label: ALERT_TYPE_LABELS.zh[value] })),
  en: symbolAlertTypes.map((value) => ({ value, label: ALERT_TYPE_LABELS.en[value] })),
  tr: symbolAlertTypes.map((value) => ({ value, label: ALERT_TYPE_LABELS.tr[value] })),
};
export const ALERT_PORTFOLIO_TYPE_OPTIONS: Record<UiLanguage, Array<Option<AlertType>>> = {
  zh: portfolioAlertTypes.map((value) => ({ value, label: ALERT_TYPE_LABELS.zh[value] })),
  en: portfolioAlertTypes.map((value) => ({ value, label: ALERT_TYPE_LABELS.en[value] })),
  tr: portfolioAlertTypes.map((value) => ({ value, label: ALERT_TYPE_LABELS.tr[value] })),
};
export const ALERT_MARKET_TYPE_OPTIONS: Record<UiLanguage, Array<Option<AlertType>>> = {
  zh: marketAlertTypes.map((value) => ({ value, label: ALERT_TYPE_LABELS.zh[value] })),
  en: marketAlertTypes.map((value) => ({ value, label: ALERT_TYPE_LABELS.en[value] })),
  tr: marketAlertTypes.map((value) => ({ value, label: ALERT_TYPE_LABELS.tr[value] })),
};
export const ALERT_TARGET_SCOPE_OPTIONS: Record<UiLanguage, Array<Option<AlertTargetScope>>> = {
  zh: Object.entries(ALERT_SCOPE_LABELS.zh).map(([value, label]) => ({ value: value as AlertTargetScope, label })),
  en: Object.entries(ALERT_SCOPE_LABELS.en).map(([value, label]) => ({ value: value as AlertTargetScope, label })),
  tr: Object.entries(ALERT_SCOPE_LABELS.tr).map(([value, label]) => ({ value: value as AlertTargetScope, label })),
};
export const ALERT_SEVERITY_OPTIONS: Record<UiLanguage, Array<Option<'info' | 'warning' | 'critical'>>> = {
  zh: Object.entries(ALERT_SEVERITY_LABELS.zh).map(([value, label]) => ({ value: value as 'info' | 'warning' | 'critical', label })),
  en: Object.entries(ALERT_SEVERITY_LABELS.en).map(([value, label]) => ({ value: value as 'info' | 'warning' | 'critical', label })),
  tr: Object.entries(ALERT_SEVERITY_LABELS.tr).map(([value, label]) => ({ value: value as 'info' | 'warning' | 'critical', label })),
};
export const ALERT_PRICE_DIRECTION_OPTIONS: Record<UiLanguage, Array<Option<'above' | 'below'>>> = {
  zh: [{ value: 'above', label: '上破' }, { value: 'below', label: '下破' }],
  en: [{ value: 'above', label: 'Crosses above' }, { value: 'below', label: 'Crosses below' }],
  tr: [{ value: 'above', label: 'Yukarı kırdı' }, { value: 'below', label: 'Aşağı kırdı' }],
};
export const ALERT_CHANGE_DIRECTION_OPTIONS: Record<UiLanguage, Array<Option<'up' | 'down'>>> = {
  zh: [{ value: 'up', label: '上涨达到' }, { value: 'down', label: '下跌达到' }],
  en: [{ value: 'up', label: 'Rises by' }, { value: 'down', label: 'Falls by' }],
  tr: [{ value: 'up', label: 'Yükseliş (%)' }, { value: 'down', label: 'Düşüş (%)' }],
};
export const ALERT_THRESHOLD_DIRECTION_OPTIONS: Record<UiLanguage, Array<Option<'above' | 'below'>>> = {
  zh: [{ value: 'above', label: '上穿' }, { value: 'below', label: '下穿' }],
  en: [{ value: 'above', label: 'Crosses above' }, { value: 'below', label: 'Crosses below' }],
  tr: [{ value: 'above', label: 'Yukarı kesti' }, { value: 'below', label: 'Aşağı kesti' }],
};
export const ALERT_CROSS_DIRECTION_OPTIONS: Record<UiLanguage, Array<Option<'bullish_cross' | 'bearish_cross'>>> = {
  zh: [{ value: 'bullish_cross', label: '金叉' }, { value: 'bearish_cross', label: '死叉' }],
  en: [{ value: 'bullish_cross', label: 'Bullish cross' }, { value: 'bearish_cross', label: 'Bearish cross' }],
  tr: [{ value: 'bullish_cross', label: 'Boğa kesişimi' }, { value: 'bearish_cross', label: 'Ayı kesişimi' }],
};
export const ALERT_STOP_LOSS_MODE_OPTIONS: Record<UiLanguage, Array<Option<PortfolioStopLossMode>>> = {
  zh: [{ value: 'near', label: '接近止损' }, { value: 'breach', label: '已触发止损' }],
  en: [{ value: 'near', label: 'Near stop loss' }, { value: 'breach', label: 'Stop loss breached' }],
  tr: [{ value: 'near', label: 'Zarar kes yakını' }, { value: 'breach', label: 'Zarar kes tetiklendi' }],
};
export const ALERT_MARKET_REGION_OPTIONS: Record<UiLanguage, Array<Option<MarketRegion>>> = {
  zh: [{ value: 'cn', label: 'A 股（cn）' }, { value: 'hk', label: '港股（hk）' }, { value: 'us', label: '美股（us）' }],
  en: [{ value: 'cn', label: 'A-shares (cn)' }, { value: 'hk', label: 'Hong Kong (hk)' }, { value: 'us', label: 'US (us)' }],
  tr: [{ value: 'us', label: 'ABD (us)' }, { value: 'cn', label: 'Çin A (cn)' }, { value: 'hk', label: 'Hong Kong (hk)' }],
};
export const ALERT_MARKET_LIGHT_STATUS_OPTIONS: Record<UiLanguage, Array<Option<MarketLightStatus>>> = {
  zh: [{ value: 'red', label: '红灯' }, { value: 'yellow', label: '黄灯' }],
  en: [{ value: 'red', label: 'Red' }, { value: 'yellow', label: 'Yellow' }],
  tr: [{ value: 'red', label: 'Kırmızı' }, { value: 'yellow', label: 'Sarı' }],
};

export const PORTFOLIO_TEXT = {
  zh: { documentTitle: '持仓分析 - DSA', title: '持仓管理', description: '组合快照、手工录入、CSV 导入与风险分析（支持全组合 / 单账户切换）', accountView: '账户视图', allAccounts: '全部账户', costMethod: '成本口径', fifo: '先进先出（FIFO）', avg: '均价成本（AVG）', collapseCreate: '收起新建', createAccount: '新建账户', deleteAccount: '删除账户', deletingAccount: '删除中...', deleteAccountTitle: '删除持仓账户', deleteAccountConfirm: '确认删除', deleteAccountMessage: '确认删除账户 {name}（#{id}）吗？删除后该账户会从默认列表、快照、风险和录入入口隐藏；历史流水不会物理删除。', refreshing: '刷新中...', refreshData: '刷新数据', noAccounts: '还没有可用账户，请先创建账户后再录入交易或导入 CSV。', riskDegraded: '风险模块降级', operationHint: '操作提示', analysisTask: '分析任务', snapshotPartialTitle: '组合估值限制', totalEquity: '总权益', totalMarketValue: '总市值', totalCash: '总现金', fxStatus: '汇率状态', refreshFx: '刷新汇率', stale: '过期', latest: '最新', fxRefreshResult: '汇率刷新结果', positionsTitle: '持仓明细', countItems: '共 {count} 项', noPositionsTitle: '当前无持仓数据', noPositionsDescription: '录入交易或导入 CSV 后，这里会展示按账户汇总的持仓明细。', account: '账户', code: '代码', quantity: '数量', avgCost: '均价', lastPrice: '现价', marketValue: '市值', unrealizedPnl: '未实现盈亏', returnPct: '收益率', action: '操作', submitting: '提交中', analyze: '分析', sectorConcentration: '行业集中度分布', positionConcentrationFallback: '行业数据暂不可用，当前展示个股集中度', noConcentrationTitle: '暂无集中度数据', noConcentrationDescription: '风险模块完成计算后，这里会展示行业或个股维度的集中度分布。', displayScope: '展示口径', sectorDimension: '行业维度', positionDimensionFallback: '个股维度（降级显示）', sectorAlert: '板块集中度告警', topWeight: 'Top1 权重', yes: '是', no: '否', writeBlocked: '当前处于“全部账户”视图。为避免误写，请先选择一个具体账户后再进行手工录入或 CSV 提交。', drawdownMonitor: '回撤监控', maxDrawdown: '最大回撤', currentDrawdown: '当前回撤', alert: '告警', stopLossWarning: '止损接近预警', triggeredCount: '触发数', nearCount: '接近数', scope: '口径', accountCount: '账户数', currency: '计价币种', costMethodShort: '成本法', aiRiskSignals: 'AI 风险信号', aiRiskUnavailable: '信号风险暂不可用', aiRiskTotal: '风险信号', sellSignals: '卖出', reduceSignals: '减仓', alertSignals: '预警', noAiRiskSignals: '暂无防御型信号' },
  en: { documentTitle: 'Portfolio Analysis - DSA', title: 'Portfolio management', description: 'Portfolio snapshots, manual entries, CSV import, and risk analysis with full-portfolio or single-account views', accountView: 'Account view', allAccounts: 'All accounts', costMethod: 'Cost method', fifo: 'FIFO', avg: 'Average cost', collapseCreate: 'Collapse', createAccount: 'New account', deleteAccount: 'Delete account', deletingAccount: 'Deleting...', deleteAccountTitle: 'Delete portfolio account', deleteAccountConfirm: 'Delete account', deleteAccountMessage: 'Delete account {name} (#{id})? It will be hidden from default lists, snapshots, risk views, and entry forms; historical ledger rows are not physically deleted.', refreshing: 'Refreshing...', refreshData: 'Refresh data', noAccounts: 'No accounts are available. Create an account before entering trades or importing CSV files.', riskDegraded: 'Risk module degraded', operationHint: 'Operation hint', analysisTask: 'Analysis task', snapshotPartialTitle: 'Portfolio valuation limitations', totalEquity: 'Total equity', totalMarketValue: 'Total market value', totalCash: 'Total cash', fxStatus: 'FX status', refreshFx: 'Refresh FX', stale: 'Stale', latest: 'Current', fxRefreshResult: 'FX refresh result', positionsTitle: 'Positions', countItems: '{count} items', noPositionsTitle: 'No positions', noPositionsDescription: 'After you enter trades or import CSV data, account-level positions appear here.', account: 'Account', code: 'Code', quantity: 'Quantity', avgCost: 'Avg cost', lastPrice: 'Last price', marketValue: 'Market value', unrealizedPnl: 'Unrealized P/L', returnPct: 'Return', action: 'Action', submitting: 'Submitting', analyze: 'Analyze', sectorConcentration: 'Sector concentration', positionConcentrationFallback: 'Sector data unavailable; showing position concentration', noConcentrationTitle: 'No concentration data', noConcentrationDescription: 'Sector or position concentration appears after the risk module finishes.', displayScope: 'Display scope', sectorDimension: 'Sector', positionDimensionFallback: 'Position fallback', sectorAlert: 'Sector concentration alert', topWeight: 'Top1 weight', yes: 'Yes', no: 'No', writeBlocked: 'You are viewing all accounts. Select a specific account before manual entry or CSV submission to avoid writing to the wrong scope.', drawdownMonitor: 'Drawdown monitor', maxDrawdown: 'Max drawdown', currentDrawdown: 'Current drawdown', alert: 'Alert', stopLossWarning: 'Stop-loss proximity warning', triggeredCount: 'Triggered', nearCount: 'Near', scope: 'Scope', accountCount: 'Accounts', currency: 'Quote currency', costMethodShort: 'Cost method', aiRiskSignals: 'AI risk signals', aiRiskUnavailable: 'Signal risk unavailable', aiRiskTotal: 'Risk signals', sellSignals: 'Sell', reduceSignals: 'Reduce', alertSignals: 'Alert', noAiRiskSignals: 'No defensive signals' },
  tr: { documentTitle: 'Portföy Analizi - DSA', title: 'Portföy Yönetimi', description: 'Portföy özetleri, manuel işlemler, CSV içe aktarım ve risk analizi', accountView: 'Hesap görünümü', allAccounts: 'Tüm hesaplar', costMethod: 'Maliyet yöntemi', fifo: 'FIFO', avg: 'Ortalama maliyet', collapseCreate: 'Kapat', createAccount: 'Yeni Hesap', deleteAccount: 'Hesabı Sil', deletingAccount: 'Siliniyor...', deleteAccountTitle: 'Portföy hesabını sil', deleteAccountConfirm: 'Hesabı sil', deleteAccountMessage: '{name} (#{id}) hesabı silinsin mi? Varsayılan listelerden gizlenir; geçmiş işlem kayıtları korunur.', refreshing: 'Yenileniyor...', refreshData: 'Verileri Yenile', noAccounts: 'Henüz hesap yok. İşlem girmeden önce bir hesap oluşturun.', riskDegraded: 'Risk modülü kısıtlı', operationHint: 'İşlem ipucu', analysisTask: 'Analiz görevi', snapshotPartialTitle: 'Portföy değerleme kısıtları', totalEquity: 'Toplam Özkaynak', totalMarketValue: 'Piyasa Değeri', totalCash: 'Toplam Nakit', fxStatus: 'Kur durumu', refreshFx: 'Kurları Yenile', stale: 'Eski', latest: 'Güncel', fxRefreshResult: 'Kur güncelleme sonucu', positionsTitle: 'Pozisyonlar', countItems: '{count} kalem', noPositionsTitle: 'Pozisyon bulunmuyor', noPositionsDescription: 'İşlem girdikten veya CSV yükledikten sonra pozisyonlar burada listelenir.', account: 'Hesap', code: 'Sembol', quantity: 'Adet', avgCost: 'Ort. Maliyet', lastPrice: 'Son Fiyat', marketValue: 'Değer', unrealizedPnl: 'Gerçekleşmemiş K/Z', returnPct: 'Getiri', action: 'İşlem', submitting: 'Gönderiliyor', analyze: 'Analiz Et', sectorConcentration: 'Sektör Yoğunlaşması', positionConcentrationFallback: 'Sektör verisi yok; hisse bazlı yoğunlaşma gösteriliyor', noConcentrationTitle: 'Yoğunlaşma verisi yok', noConcentrationDescription: 'Risk hesaplamasından sonra yoğunlaşma dağılımı görünür.', displayScope: 'Görünüm kapsamı', sectorDimension: 'Sektör', positionDimensionFallback: 'Hisse bazlı', sectorAlert: 'Sektör yoğunlaşma uyarısı', topWeight: 'En yüksek ağırlık', yes: 'Evet', no: 'Hayır', writeBlocked: 'Tüm hesaplar görünüyor. İşlem eklemeden önce belirli bir hesap seçin.', drawdownMonitor: 'Düşüş (Drawdown) Takibi', maxDrawdown: 'Maks. Düşüş', currentDrawdown: 'Mevcut Düşüş', alert: 'Uyarı', stopLossWarning: 'Zarar Kes Yakınlık Uyarısı', triggeredCount: 'Tetiklenen', nearCount: 'Yaklaşan', scope: 'Kapsam', accountCount: 'Hesaplar', currency: 'Para birimi', costMethodShort: 'Maliyet', aiRiskSignals: 'AI Risk Sinyalleri', aiRiskUnavailable: 'Risk sinyali yok', aiRiskTotal: 'Risk sinyali', sellSignals: 'Sat', reduceSignals: 'Azalt', alertSignals: 'Uyarı', noAiRiskSignals: 'Savunma sinyali yok' },
} as const;
export const PORTFOLIO_SIDE_LABELS: Record<UiLanguage, Record<PortfolioSide, string>> = {
  zh: { buy: '买入', sell: '卖出' },
  en: { buy: 'Buy', sell: 'Sell' },
  tr: { buy: 'Alış', sell: 'Satış' },
};
export const PORTFOLIO_CASH_DIRECTION_LABELS: Record<UiLanguage, Record<PortfolioCashDirection, string>> = {
  zh: { in: '流入', out: '流出' },
  en: { in: 'Inflow', out: 'Outflow' },
  tr: { in: 'Para Girişi', out: 'Para Çıkışı' },
};
export const PORTFOLIO_CORPORATE_ACTION_LABELS: Record<UiLanguage, Record<PortfolioCorporateActionType, string>> = {
  zh: { cash_dividend: '现金分红', split_adjustment: '拆并股调整' },
  en: { cash_dividend: 'Cash dividend', split_adjustment: 'Split adjustment' },
  tr: { cash_dividend: 'Nakit Temettü', split_adjustment: 'Bölünme / Bedelsiz' },
};
