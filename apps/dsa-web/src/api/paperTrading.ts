import apiClient from './index';

export interface PaperPositionItem {
  stock_code: string;
  stock_name?: string | null;
  market?: string | null;
  currency?: string | null;
  quantity: number;
  avg_cost: number;
  last_close?: number | null;
  last_close_date?: string | null;
  price_stale: boolean;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct?: number | null;
  realized_pnl: number;
  stop_loss?: number | null;
  take_profit?: number | null;
  stops_enforced?: boolean;
  atr14?: number | null;
  atr_pct?: number | null;
  recommended_quantity?: number | null;
  max_loss_amount?: number | null;
}

export interface PaperCurrencyTotals {
  cost: number;
  market_value: number;
  realized_pnl: number;
  unrealized_pnl: number;
}

export interface PaperBenchmarkItem {
  benchmark: string;
  benchmark_name: string;
  currency: string;
  capital_deployed: number;
  strategy_return_pct: number;
  benchmark_return_pct?: number | null;
  excess_return_pct?: number | null;
  usd_return_pct?: number | null;
  fx_change_pct?: number | null;
}

export interface SignalOutcomeBucket {
  completed?: number;
  hit?: number;
  miss?: number;
  neutral?: number;
  hit_rate_pct?: number | null;
  avg_stock_return_pct?: number | null;
}

export interface SignalOutcomesSummary {
  evaluated?: number;
  total?: number;
  completed?: number;
  unable?: number;
  hit?: number;
  miss?: number;
  neutral?: number;
  hit_rate_pct?: number | null;
  avg_stock_return_pct?: number | null;
  by_horizon?: Record<string, SignalOutcomeBucket>;
  by_action?: Record<string, SignalOutcomeBucket>;
}

export interface MarketRegimeInfo {
  regime: 'risk_on' | 'caution' | 'risk_off' | 'neutral';
  position_scale: number;
  spy_close?: number | null;
  spy_sma50?: number | null;
  spy_sma200?: number | null;
  vix_level?: number | null;
  reasons?: string[];
}

export interface PaperRiskStatus {
  max_open_positions?: number | null;
  max_sector_positions?: number | null;
  max_drawdown_pct?: number | null;
  current_drawdown_pct?: number | null;
  circuit_breaker_triggered?: boolean;
  market_regime_filter?: boolean;
  quant_gate_enabled?: boolean;
  quant_min_score?: number;
  live_quotes_applied?: boolean;
  market_regime?: MarketRegimeInfo | null;
}

export interface AlpacaStatusResponse {
  configured: boolean;
  paper: boolean;
  auto_execute: boolean;
  account?: {
    status?: string;
    currency?: string;
    cash?: number;
    buying_power?: number;
    equity?: number;
    portfolio_value?: number;
  } | null;
  clock?: {
    is_open?: boolean;
    next_open?: string | null;
    next_close?: string | null;
  } | null;
  positions: Array<{
    symbol: string;
    qty: number;
    avg_entry_price: number;
    current_price: number;
    unrealized_pl: number;
    unrealized_plpc?: number | null;
  }>;
  open_orders: Array<{
    id?: string;
    symbol: string;
    side?: string;
    qty: number;
    type?: string;
    status?: string;
  }>;
  error?: string | null;
}

export interface PaperTradingSummaryResponse {
  enabled: boolean;
  position_size: number;
  risk_pct: number;
  trade_count: number;
  open_position_count: number;
  closed_trade_count: number;
  stop_loss_count: number;
  take_profit_count: number;
  win_rate_pct?: number | null;
  positions: PaperPositionItem[];
  totals_by_currency: Record<string, PaperCurrencyTotals>;
  benchmarks: Record<string, PaperBenchmarkItem>;
  signal_outcomes?: SignalOutcomesSummary;
  risk_status?: PaperRiskStatus;
}

export interface PaperTradeItem {
  id: number;
  signal_id: number;
  stock_code: string;
  stock_name?: string | null;
  market?: string | null;
  currency?: string | null;
  action: string;
  side: string;
  quantity: number;
  price: number;
  stop_loss?: number | null;
  take_profit?: number | null;
  trade_date?: string | null;
}

export interface PaperTradeListResponse {
  items: PaperTradeItem[];
}

export interface KapAlertItem {
  stock_code: string;
  kind: 'kap' | 'news' | 'rumor' | string;
  index?: number | null;
  story_key?: string | null;
  title: string;
  published_date: string;
  class_label?: string | null;
  verification?: string | null;
  sources: string[];
  source_count: number;
  tags: string[];
  tag_labels_tr: string[];
  details?: string | null;
  url?: string | null;
  alerted_at?: string | null;
}

export interface KapAlertListResponse {
  items: KapAlertItem[];
}

export interface PaperEquityPoint {
  date: string;
  total_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  market_value: number;
  capital_deployed: number;
  return_pct: number;
}

export interface PaperEquityCurveResponse {
  points: PaperEquityPoint[];
  currencies: string[];
}

export interface PaperManualOrderPayload {
  stock_code: string;
  action: 'buy' | 'reduce' | 'sell';
  quantity?: number;
  price?: number;
  stop_loss?: number;
  take_profit?: number;
  stock_name?: string;
  market?: string;
}

export interface PaperUpdateStopsPayload {
  stop_loss?: number;
  take_profit?: number;
}

export const paperTradingApi = {
  async getSummary(benchmark = true, outcomes = true): Promise<PaperTradingSummaryResponse> {
    const response = await apiClient.get<PaperTradingSummaryResponse>('/api/v1/paper-trading/summary', {
      params: { benchmark, outcomes },
    });
    return response.data;
  },

  async listTrades(limit = 100): Promise<PaperTradeListResponse> {
    const response = await apiClient.get<PaperTradeListResponse>('/api/v1/paper-trading/trades', {
      params: { limit },
    });
    return response.data;
  },

  async listKapAlerts(limit = 30, live = true): Promise<KapAlertListResponse> {
    const response = await apiClient.get<KapAlertListResponse>('/api/v1/paper-trading/kap-alerts', {
      params: { limit, live },
    });
    return response.data;
  },

  async getEquityCurve(days = 90): Promise<PaperEquityCurveResponse> {
    const response = await apiClient.get<PaperEquityCurveResponse>('/api/v1/paper-trading/equity-curve', {
      params: { days },
    });
    return response.data;
  },

  async placeOrder(payload: PaperManualOrderPayload): Promise<PaperTradeItem> {
    const response = await apiClient.post<PaperTradeItem>('/api/v1/paper-trading/orders', payload);
    return response.data;
  },

  async updatePositionStops(stockCode: string, payload: PaperUpdateStopsPayload): Promise<PaperTradeItem> {
    const response = await apiClient.patch<PaperTradeItem>(
      `/api/v1/paper-trading/positions/${encodeURIComponent(stockCode)}/stops`,
      payload,
    );
    return response.data;
  },

  async getAlpacaStatus(): Promise<AlpacaStatusResponse> {
    const response = await apiClient.get<AlpacaStatusResponse>('/api/v1/paper-trading/alpaca/status');
    return response.data;
  },
};

