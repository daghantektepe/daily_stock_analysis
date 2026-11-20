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
  report_text?: string | null;
}

export interface Form4StudyResponse {
  quarters: string[];
  total_events: number;
  evaluated_events: number;
  report_text: string;
  horizons: Record<string, unknown>;
}

export interface CryptoTrendRow {
  label: string;
  strategy_cagr_pct: number;
  strategy_max_drawdown_pct: number;
  strategy_sharpe: number;
  buy_hold_cagr_pct: number;
  buy_hold_max_drawdown_pct: number;
  buy_hold_sharpe: number;
  start: string;
  end: string;
}

export interface CryptoTrendResponse {
  assets: string[];
  signals: Record<string, {
    date?: string;
    close?: number;
    weight?: number;
    averages?: Record<string, number>;
    reason?: string;
  }>;
  backtest_all: CryptoTrendRow[];
  backtest_oos: CryptoTrendRow[];
  yearly: Array<{ year: number; strategy_pct: number; buy_hold_pct: number }>;
  paper_report: string;
  report_text: string;
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

export interface StrategyPerformanceMetrics {
  start_date?: string | null;
  end_date?: string | null;
  trading_days: number;
  total_return_pct: number;
  cagr_pct: number;
  vol_pct: number;
  sharpe: number;
  sortino: number;
  max_drawdown_pct: number;
  calmar: number;
  recovery_factor: number;
  win_rate_pct: number;
  annual_turnover: number;
  dsr_pct: number;
}

export interface StrategyEquityPoint {
  date: string;
  equity: number;
  drawdown_pct: number;
}

export interface TournamentStrategyRow {
  strategy_id: string;
  name: string;
  universe: string;
  category: string;
  description: string;
  currency: string;
  cost_bps: number;
  is_benchmark: boolean;
  verdict: string;
  oos: StrategyPerformanceMetrics;
  full: StrategyPerformanceMetrics;
  current_weights: Record<string, number>;
  cash_weight_pct: number;
  latest_date?: string | null;
  signal_summary: string;
  equity_oos_points?: StrategyEquityPoint[];
}

export interface TournamentResponse {
  generated_at?: string | null;
  oos_start: string;
  latest_date?: string | null;
  total_strategies: number;
  total_assets: number;
  total_asset_days: number;
  pass_elite_count: number;
  pass_solid_count: number;
  champion?: TournamentStrategyRow | null;
  paa?: TournamentStrategyRow | null;
  meta_portfolio_a?: TournamentStrategyRow | null;
  meta_portfolio_b?: TournamentStrategyRow | null;
  featured_strategy_ids: string[];
  strategies: TournamentStrategyRow[];
  paper_snapshot?: Record<string, unknown> | null;
}

export interface PaaSignalResponse {
  as_of_date?: string | null;
  risk_assets_total: number;
  risk_assets_below_sma252: number;
  crash_protection_pct: number;
  regime_label: string;
  target_weights_pct: Record<string, number>;
  risk_asset_breadth: Array<{
    symbol: string;
    close: number;
    sma252: number;
    mom_vs_sma252_pct: number;
    above_sma252: boolean;
  }>;
}

export interface QuantPaperPositionItem {
  symbol: string;
  shares: number;
  avg_cost: number;
  last_price: number;
  market_value: number;
  weight_pct: number;
  unrealized_pnl_usd: number;
  unrealized_pnl_pct: number;
}

export interface QuantPaperTradeItem {
  date: string;
  symbol: string;
  side: 'BUY' | 'SELL' | string;
  shares: number;
  price: number;
  notional: number;
  cost: number;
  target_weight_pct: number;
  reason: string;
  late?: boolean;
}

export interface QuantPaperBookItem {
  name: string;
  strategy_key: string;
  strategy_id: string;
  label: string;
  benchmark_symbol: string;
  rebalance_mode: string;
  cost_bps: number;
  simulated_only: boolean;
  start_date?: string | null;
  last_date?: string | null;
  last_rebalance_date?: string | null;
  days: number;
  late_days: number;
  initial_capital: number;
  nav: number;
  cash: number;
  cash_pct: number;
  return_pct: number;
  benchmark_return_pct: number;
  excess_return_pct: number;
  max_drawdown_pct: number;
  benchmark_max_drawdown_pct: number;
  weights_pct: Record<string, number>;
  live_target_weights_pct: Record<string, number>;
  positions: QuantPaperPositionItem[];
  trade_count: number;
  processed_days: number;
  new_trades: QuantPaperTradeItem[];
  recent_trades: QuantPaperTradeItem[];
  history: Array<{
    date: string;
    nav: number;
    benchmark_nav: number;
    cash: number;
    rebalanced?: boolean;
    late?: boolean;
  }>;
  report_text: string;
  council_meta?: {
    member_key?: string;
    engine_label?: string;
    model?: string;
    rule_engine?: string;
    thesis?: string;
    risk_rules?: string;
    verdict?: string;
    oos_backtest?: {
      cagr_pct?: number;
      sharpe?: number;
      max_drawdown_pct?: number;
      dsr_pct?: number;
    };
  } | null;
}

export interface QuantPaperBooksResponse {
  ok: boolean;
  simulated_only: boolean;
  strategies: string[];
  total_new_trades: number;
  books: QuantPaperBookItem[];
  report_text: string;
  error?: string | null;
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

  async runForm4Study(params: {
    quarters?: string;
    min_value?: number;
    min_price?: number;
    limit?: number;
    slippage?: number;
  } = {}): Promise<Form4StudyResponse> {
    const res = await apiClient.post('/api/v1/alpha/form4-study', params, {
      timeout: 600000,
    });
    return res.data;
  },

  async runPeadUnbiasedStudy(params: {
    universe?: 'smid' | 'sp400' | 'sp600' | 'sp500';
    sample?: number;
    min_surprise_pct?: number | null;
    slippage?: number;
    seed?: number;
  } = {}): Promise<PeadStudyResponse> {
    const res = await apiClient.post('/api/v1/alpha/pead-unbiased-study', params, {
      timeout: 600000,
    });
    return res.data;
  },

  async getCryptoTrend(stepPaper = true): Promise<CryptoTrendResponse> {
    const res = await apiClient.get('/api/v1/alpha/crypto-trend', {
      params: { step_paper: stepPaper },
      timeout: 90000,
    });
    return res.data;
  },

  async getTournament(autoRun = true): Promise<TournamentResponse> {
    const res = await apiClient.get<TournamentResponse>('/api/v1/alpha/tournament', {
      params: { auto_run: autoRun },
      timeout: 180000,
    });
    return res.data;
  },

  async runTournament(params: {
    oos_start?: string;
    force_refresh?: boolean;
  } = {}): Promise<TournamentResponse> {
    const res = await apiClient.post<TournamentResponse>('/api/v1/alpha/tournament/run', params, {
      timeout: 240000,
    });
    return res.data;
  },

  async getPaaSignal(refresh = false): Promise<PaaSignalResponse> {
    const res = await apiClient.get<PaaSignalResponse>('/api/v1/alpha/paa', {
      params: { refresh },
      timeout: 60000,
    });
    return res.data;
  },

  async getQuantPaperBooks(autoStep = true): Promise<QuantPaperBooksResponse> {
    const res = await apiClient.get<QuantPaperBooksResponse>('/api/v1/alpha/quant-paper', {
      params: { auto_step: autoStep },
      timeout: 60000,
    });
    return res.data;
  },

  async stepQuantPaperBooks(params: {
    strategies?: string[];
    force_rebalance?: boolean;
    force_refresh_prices?: boolean;
  } = {}): Promise<QuantPaperBooksResponse> {
    const res = await apiClient.post<QuantPaperBooksResponse>('/api/v1/alpha/quant-paper/step', params, {
      timeout: 90000,
    });
    return res.data;
  },
};
