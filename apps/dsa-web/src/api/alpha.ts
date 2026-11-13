import apiClient from './index';

export interface AlphaOverviewResponse {
  paper_trading_enabled: boolean;
  auth_enabled: boolean;
  open_position_count: number;
  trade_count: number;
  win_rate_pct?: number | null;
  totals_by_currency: Record<string, {
    cost: number;
    market_value: number;
    realized_pnl: number;
    unrealized_pnl: number;
  }>;
  recent_alerts_count: number;
  us_screener_enabled: boolean;
  bist_screener_enabled: boolean;
}

export interface UsQuantCandidateItem {
  symbol: string;
  score: number;
  residual_momentum_z?: number | null;
  raw_12_1m_return_pct?: number | null;
  near_52w_high?: number | null;
  fip_id?: number | null;
  cash_op_profitability?: number | null;
  accruals_ratio?: number | null;
  realized_vol_ann?: number | null;
  vol_scale_weight?: number | null;
  avg_dollar_volume?: number | null;
  last_close?: number | null;
  pead_score: number;
  insider_score: number;
  reasons: string[];
}

export interface Form4ClusterItem {
  symbol: string;
  company_name: string;
  filing_date?: string | null;
  insider_count: number;
  officer_director_count: number;
  total_value: number;
  total_shares: number;
  avg_price: number;
  has_c_level: boolean;
  is_opportunistic: boolean;
  is_cluster: boolean;
  cmp_class: string;
  has_10b51: boolean;
  primary_titles: string[];
  trend_regime: string;
  score: number;
  reasons: string[];
  sec_url: string;
}

export interface PeadCandidateItem {
  symbol: string;
  company_name: string;
  earnings_date?: string | null;
  days_since_earnings: number;
  eps_estimate?: number | null;
  eps_reported?: number | null;
  eps_surprise_pct?: number | null;
  sue_score?: number | null;
  revenue_growth_pct?: number | null;
  near_52w_high?: number | null;
  avg_dollar_volume?: number | null;
  announcement_session: string;
  day1_return_pct?: number | null;
  total_drift_pct?: number | null;
  volume_surge_ratio?: number | null;
  trend_regime: string;
  conviction_tier: string;
  score: number;
  reasons: string[];
}

export interface PeadStudyHorizonStat {
  count: number;
  avg_stock_return_pct?: number | null;
  avg_excess_return_pct?: number | null;
  net_excess_return_pct?: number | null;
  median_excess_return_pct?: number | null;
  win_rate_pct?: number | null;
  beat_benchmark_rate_pct?: number | null;
  t_stat?: number | null;
  net_t_stat?: number | null;
  is_significant?: boolean;
}

export interface PeadStudyResponse {
  total_events: number;
  evaluated_events: number;
  benchmark_symbol: string;
  estimated_slippage_pct: number;
  horizons: Record<string, PeadStudyHorizonStat>;
  segments: Record<string, unknown>;
}

export interface BistCandidateItem {
  code: string;
  name?: string;
  close?: number;
  change_pct?: number;
  volume_ratio?: number;
  score?: number;
  reasons?: string[];
  kap_count?: number;
  [key: string]: unknown;
}

export interface BistScreenResponse {
  selected_codes: string[];
  scanned_count: number;
  passed_count: number;
  candidates: BistCandidateItem[];
  errors: string[];
}

export interface KapContractItem {
  symbol: string;
  ticker: string;
  company_name: string;
  disclosure_index: string;
  published_date: string;
  title: string;
  contract_amount?: number | null;
  contract_currency?: string | null;
  contract_amount_try?: number | null;
  contract_to_revenue_pct?: number | null;
  conviction_tier: string;
  score: number;
  reasons: string[];
  url: string;
  counterparty?: string | null;
  details_condensed?: string;
}

export const alphaApi = {
  async getOverview(): Promise<AlphaOverviewResponse> {
    const res = await apiClient.get<AlphaOverviewResponse>('/api/v1/alpha/overview', {
      timeout: 15000,
    });
    return res.data;
  },

  async runUsScreen(params: {
    symbols?: string[];
    top_n?: number;
    include_pead?: boolean;
    include_form4?: boolean;
    use_sec_xbrl?: boolean;
  } = {}): Promise<{ count: number; items: UsQuantCandidateItem[] }> {
    const res = await apiClient.post('/api/v1/alpha/us-screen', params, {
      timeout: 120000,
    });
    return res.data;
  },

  async getForm4Live(params: {
    count?: number;
    max_filings?: number;
    min_value?: number;
  } = {}): Promise<{ count: number; items: Form4ClusterItem[] }> {
    const res = await apiClient.get('/api/v1/alpha/form4-live', {
      params,
      timeout: 90000,
    });
    return res.data;
  },

  async getPeadCandidates(params: {
    universe?: 'all' | 'midcap' | 'megacap';
    max_days?: number;
    min_score?: number;
    top_n?: number;
  } = {}): Promise<{ count: number; universe: string; items: PeadCandidateItem[] }> {
    const res = await apiClient.get('/api/v1/alpha/pead-candidates', {
      params,
      timeout: 90000,
    });
    return res.data;
  },

  async runPeadStudy(params: {
    symbols: string[];
    min_surprise_pct?: number;
    benchmark_symbol?: string;
    estimated_slippage_pct?: number;
  }): Promise<PeadStudyResponse> {
    const res = await apiClient.post('/api/v1/alpha/pead-study', params, {
      timeout: 120000,
    });
    return res.data;
  },

  async runBistScreen(params: {
    top_n?: number;
    min_score?: number;
    include_kap?: boolean;
  } = {}): Promise<BistScreenResponse> {
    const res = await apiClient.post('/api/v1/alpha/bist-screen', params, {
      timeout: 120000,
    });
    return res.data;
  },

  async getKapContracts(params: {
    days_back?: number;
    min_score?: number;
    top_n?: number;
  } = {}): Promise<{ count: number; items: KapContractItem[] }> {
    const res = await apiClient.get('/api/v1/alpha/kap-contracts', {
      params,
      timeout: 90000,
    });
    return res.data;
  },
};
