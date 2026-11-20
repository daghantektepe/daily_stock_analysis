import type {
  AnalysisPhase,
  MarketPhaseSummary,
  MarketPhaseValue,
  ReportLanguage,
} from '../types/analysis';
import { normalizeReportLanguage } from './reportLanguage';

const REQUEST_PHASE_LABELS: Record<ReportLanguage, Record<AnalysisPhase, string>> = {
  zh: {
    auto: 'Otomatik Seans',
    premarket: 'Seans Öncesi',
    intraday: 'Seans İçi',
    postmarket: 'Seans Sonrası',
  },
  en: {
    auto: 'Auto',
    premarket: 'Pre-market',
    intraday: 'Intraday',
    postmarket: 'Post-market',
  },
  ko: {
    auto: '자동 단계',
    premarket: '장 시작 전',
    intraday: '장중',
    postmarket: '장 마감 후',
  },
  tr: {
    auto: 'Otomatik',
    premarket: 'Seans öncesi',
    intraday: 'Seans içi',
    postmarket: 'Seans sonrası',
  },
};

const MARKET_PHASE_LABELS: Record<ReportLanguage, Record<MarketPhaseValue, string>> = {
  zh: {
    premarket: 'Seans Öncesi',
    intraday: 'Seans İçi',
    lunch_break: 'Öğle Arası',
    closing_auction: 'Kapanış Müzayedesi',
    postmarket: 'Seans Sonrası',
    non_trading: 'İşlem Günü Değil',
    unknown: 'Seans Bilinmiyor',
  },
  en: {
    premarket: 'Pre-market',
    intraday: 'Intraday',
    lunch_break: 'Lunch break',
    closing_auction: 'Near close',
    postmarket: 'Post-market',
    non_trading: 'Non-trading',
    unknown: 'Unknown phase',
  },
  ko: {
    premarket: '장 시작 전',
    intraday: '장중',
    lunch_break: '점심 휴장',
    closing_auction: '마감 임박',
    postmarket: '장 마감 후',
    non_trading: '비거래일',
    unknown: '단계 불명',
  },
  tr: {
    premarket: 'Seans öncesi',
    intraday: 'Seans içi',
    lunch_break: 'Öğle arası',
    closing_auction: 'Kapanışa yakın',
    postmarket: 'Seans sonrası',
    non_trading: 'İşlem günü değil',
    unknown: 'Aşama bilinmiyor',
  },
};

const TEXT = {
  zh: {
    requestPrefix: 'İstenen Seans',
    finalPrefix: 'Piyasa Seansı',
    partialBar: 'Günlük Bar Tamamlanmadı',
  },
  en: {
    requestPrefix: 'Requested phase',
    finalPrefix: 'Market phase',
    partialBar: 'Partial bar',
  },
  ko: {
    requestPrefix: '요청 단계',
    finalPrefix: '시장 단계',
    partialBar: '일봉 미완성',
  },
  tr: {
    requestPrefix: 'İstenen aşama',
    finalPrefix: 'Piyasa aşaması',
    partialBar: 'Gün tamamlanmadı',
  },
} as const;

export const getRequestedPhaseLabel = (
  phase?: AnalysisPhase | null,
  language?: ReportLanguage | null,
): string | null => {
  if (!phase) {
    return null;
  }

  const reportLanguage = normalizeReportLanguage(language);
  const label = REQUEST_PHASE_LABELS[reportLanguage][phase];
  if (!label) {
    return null;
  }

  return `${TEXT[reportLanguage].requestPrefix}: ${label}`;
};

export const getMarketPhaseSummaryLabel = (
  summary?: MarketPhaseSummary | null,
  language?: ReportLanguage | null,
): string | null => {
  if (!summary) {
    return null;
  }

  const reportLanguage = normalizeReportLanguage(language);
  const phaseLabel = MARKET_PHASE_LABELS[reportLanguage][summary.phase];
  if (!phaseLabel) {
    return null;
  }

  const market = (summary.market || '').trim().toUpperCase();
  const value = market ? `${market} · ${phaseLabel}` : phaseLabel;
  return `${TEXT[reportLanguage].finalPrefix}: ${value}`;
};

export const getPartialBarLabel = (language?: ReportLanguage | null): string =>
  TEXT[normalizeReportLanguage(language)].partialBar;
