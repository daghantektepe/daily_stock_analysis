import apiClient from './index';
import { toCamelCase } from './utils';

export interface BridgeItemStatus {
  id: string;
  name: string;
  kind: string;
  configured: boolean;
  sandboxOrReadonly: boolean;
  modeLabel: string;
  liveReachable: boolean | null;
  note?: string | null;
  details: Record<string, unknown>;
}

export interface BridgesStatusResponse {
  ok: boolean;
  checkedLive: boolean;
  bridges: BridgeItemStatus[];
}

export interface TefasFundItem {
  code: string;
  title: string;
  category: string;
  bucket: string;
  globalProxy: string;
  priceTry: number | null;
  dailyReturnPct: number | null;
  fundSizeTry: number | null;
  investors: number | null;
  categoryRank: number | null;
  categoryTotal: number | null;
  marketSharePct: number | null;
  source: string;
}

export interface TefasFundsResponse {
  ok: boolean;
  count: number;
  liveCount: number;
  funds: TefasFundItem[];
}

export interface PurchasePowerResult {
  nominalReturnPct: number;
  usdBasedReturnPct: number | null;
  realTufeReturnPct: number | null;
  beatsInflation: boolean | null;
}

export interface MacroTrResponse {
  ok: boolean;
  evdsConfigured: boolean;
  usdTry: number | null;
  usdTry1yChangePct: number | null;
  usdTryAsOf: string | null;
  usdTrySource: string;
  cpiYoyPct: number | null;
  cpiMomPct: number | null;
  cpiAsOf: string | null;
  cpiSource: string;
  cached: boolean;
  purchasingPower: PurchasePowerResult | null;
}

export interface BinancePreviewTicker {
  asset: string;
  symbol: string;
  lastPrice: number | null;
  bid: number | null;
  ask: number | null;
  spreadBps: number | null;
  priceChangePct24h: number | null;
  quoteVolumeUsdt24h: number | null;
  source: string;
  error?: string | null;
}

export interface BinancePreviewResponse {
  ok: boolean;
  testnet: boolean;
  configured: boolean;
  autoExecute: boolean;
  tickers: BinancePreviewTicker[];
  account: Record<string, unknown> | null;
}

export const bridgesApi = {
  async getStatus(checkLive = false): Promise<BridgesStatusResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/bridges/status', {
      params: checkLive ? { check_live: true } : undefined,
    });
    return toCamelCase<BridgesStatusResponse>(response.data);
  },

  async getTefasFunds(params: { bucket?: string; codes?: string; forceRefresh?: boolean } = {}): Promise<TefasFundsResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/bridges/tefas', {
      params: {
        bucket: params.bucket || undefined,
        codes: params.codes || undefined,
        force_refresh: params.forceRefresh || undefined,
      },
    });
    return toCamelCase<TefasFundsResponse>(response.data);
  },

  async getMacroTr(params: { nominalReturnPct?: number; forceRefresh?: boolean } = {}): Promise<MacroTrResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/bridges/macro-tr', {
      params: {
        nominal_return_pct: params.nominalReturnPct,
        force_refresh: params.forceRefresh || undefined,
      },
    });
    return toCamelCase<MacroTrResponse>(response.data);
  },

  async getBinancePreview(assets = 'BTC-USD,ETH-USD'): Promise<BinancePreviewResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/bridges/binance/preview', {
      params: { assets },
    });
    return toCamelCase<BinancePreviewResponse>(response.data);
  },
};
