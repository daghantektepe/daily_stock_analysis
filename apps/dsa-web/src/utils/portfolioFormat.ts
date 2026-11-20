import type {
  PortfolioCashDirection,
  PortfolioCorporateActionType,
  PortfolioFxRefreshResponse,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PortfolioPositionItem,
  PortfolioSide,
} from '../types/portfolio';
import { toDateInputValue } from './format';

export type FxRefreshFeedback = {
  tone: 'neutral' | 'success' | 'warning';
  text: string;
};

export type PortfolioAlertVariant = 'info' | 'success' | 'warning' | 'danger';

export function getTodayIso(): string {
  return toDateInputValue(new Date());
}

export function formatMoney(value: number | undefined | null, currency = 'CNY'): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${currency} ${Number(value).toLocaleString('tr-TR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${value.toFixed(2)}%`;
}

export function formatSignedPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function hasPositionPrice(row: PortfolioPositionItem): boolean {
  return row.priceAvailable !== false && row.priceSource !== 'missing';
}

export function formatPositionPrice(row: PortfolioPositionItem): string {
  if (!hasPositionPrice(row)) return '--';
  return row.lastPrice.toFixed(4);
}

export function formatPositionMoney(value: number, row: PortfolioPositionItem): string {
  if (!hasPositionPrice(row)) return '--';
  return formatMoney(value, row.valuationCurrency);
}

export function getPositionPriceLabel(row: PortfolioPositionItem): string {
  if (!hasPositionPrice(row)) return 'Fiyat Yok';
  if (row.priceSource === 'realtime_quote') {
    return row.priceProvider ? `Anlık · ${row.priceProvider}` : 'Anlık Fiyat';
  }
  if (row.priceSource === 'history_close') {
    return row.priceStale && row.priceDate ? `Kapanış · ${row.priceDate}` : 'Kapanış Fiyatı';
  }
  return row.priceSource || 'Bilinmeyen Kaynak';
}

export function formatSideLabel(value: PortfolioSide): string {
  return value === 'buy' ? 'Alış' : 'Satış';
}

export function formatCashDirectionLabel(value: PortfolioCashDirection): string {
  return value === 'in' ? 'Giriş' : 'Çıkış';
}

export function formatCorporateActionLabel(value: PortfolioCorporateActionType): string {
  return value === 'cash_dividend' ? 'Nakit Temettü' : 'Bölünme / Birleşme';
}

export function formatBrokerLabel(value: string, displayName?: string): string {
  if (displayName && displayName.trim()) return `${value}（${displayName.trim()}）`;
  if (value === 'huatai') return 'Huatai';
  if (value === 'citic') return 'CITIC';
  if (value === 'cmb') return 'CMB';
  return value;
}

export function buildFxRefreshFeedback(data: PortfolioFxRefreshResponse): FxRefreshFeedback {
  if (data.refreshEnabled === false) {
    return {
      tone: 'neutral',
      text: 'Çevrimiçi kur yenileme devre dışı.',
    };
  }

  if (data.pairCount === 0) {
    return {
      tone: 'neutral',
      text: 'Mevcut kapsamda yenilenecek kur çifti yok.',
    };
  }

  if (data.updatedCount > 0 && data.staleCount === 0 && data.errorCount === 0) {
    return {
      tone: 'success',
      text: `Döviz kurları yenilendi (${data.updatedCount} çift güncellendi).`,
    };
  }

  const summary = `${data.updatedCount} güncellendi, ${data.staleCount} eski kaldı, ${data.errorCount} başarısız.`;
  if (data.staleCount > 0) {
    return {
      tone: 'warning',
      text: `Yenileme denendi ancak bazı çiftler hâlâ yedek/eski kur kullanıyor. ${summary}`,
    };
  }

  return {
    tone: 'warning',
    text: `Çevrimiçi yenileme tam olarak tamamlanamadı. ${summary}`,
  };
}

export function getFxRefreshFeedbackVariant(tone: FxRefreshFeedback['tone']): PortfolioAlertVariant {
  if (tone === 'success') return 'success';
  if (tone === 'warning') return 'warning';
  return 'info';
}

export function getCsvParseVariant(result: PortfolioImportParseResponse): PortfolioAlertVariant {
  return result.errorCount > 0 || result.skippedCount > 0 ? 'warning' : 'info';
}

export function getCsvCommitVariant(result: PortfolioImportCommitResponse, isDryRun: boolean): PortfolioAlertVariant {
  if (isDryRun) return 'info';
  return result.failedCount > 0 || result.duplicateCount > 0 ? 'warning' : 'success';
}
