import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { QuantPaperBookItem, StrategyPerformanceMetrics, TournamentStrategyRow } from '../../../api/alpha';
import { QuantPaperBookCard } from '../QuantPaperBookCard';
import { TournamentLeaderboard } from '../TournamentLeaderboard';

const metrics = (overrides: Partial<StrategyPerformanceMetrics>): StrategyPerformanceMetrics => ({
  trading_days: 1200,
  total_return_pct: 0,
  cagr_pct: 0,
  vol_pct: 10,
  sharpe: 0,
  sortino: 0,
  max_drawdown_pct: -10,
  calmar: 0,
  recovery_factor: 1,
  win_rate_pct: 50,
  annual_turnover: 1,
  dsr_pct: 50,
  ...overrides,
});

const row = (overrides: Partial<TournamentStrategyRow>): TournamentStrategyRow => ({
  strategy_id: 'X',
  name: 'X',
  universe: 'us_etf',
  category: 'c',
  description: 'd',
  currency: 'USD',
  cost_bps: 5,
  is_benchmark: false,
  verdict: 'PASS_SOLID',
  oos: metrics({}),
  full: metrics({}),
  current_weights: {},
  cash_weight_pct: 0,
  signal_summary: '',
  ...overrides,
});

const rowsInOrder = () =>
  screen
    .getAllByRole('row')
    .slice(1)
    .map((tr) => within(tr).getAllByRole('cell')[0].textContent ?? '');

describe('TournamentLeaderboard', () => {
  it('ranks on Sharpe over BIL, not on Rf=0 Sharpe', () => {
    render(
      <TournamentLeaderboard
        strategies={[
          row({ strategy_id: 'CASH', name: 'Cash Hugger', oos: metrics({ sharpe: 0.94, excess_sharpe: 0.15 }) }),
          row({ strategy_id: 'TREND', name: 'Real Trend', oos: metrics({ sharpe: 0.73, excess_sharpe: 0.44 }) }),
        ]}
      />,
    );
    expect(screen.getAllByText('BIL üstü Sharpe').length).toBeGreaterThan(0);
    expect(rowsInOrder()[0]).toContain('Real Trend');
    expect(screen.getByText('+0.44')).toBeInTheDocument();
    expect(screen.queryByText('0.94')).not.toBeInTheDocument();
  });

  it('shows BIST in dollars with the TL figure underneath', () => {
    render(
      <TournamentLeaderboard
        strategies={[
          row({
            strategy_id: 'BIST',
            name: 'BIST Momentum',
            universe: 'bist',
            currency: 'TRY',
            verdict: 'CAVEAT_SURVIVORSHIP',
            oos: metrics({ cagr_pct: 50.5, sharpe: 1.39, max_drawdown_pct: -30, recovery_factor: 21.5 }),
            usd: metrics({ cagr_pct: 15.4, excess_sharpe: 0.33, max_drawdown_pct: -39.8, recovery_factor: 2.1 }),
          }),
        ]}
      />,
    );
    const cells = within(screen.getAllByRole('row')[1]).getAllByRole('cell');
    expect(cells[3].textContent).toContain('+15.4% USD');
    expect(cells[3].textContent).toContain('TL +50.5%');
    expect(cells[4].textContent).toBe('+0.33');
    expect(cells[5].textContent).toBe('-39.8%');
    expect(cells[6].textContent).toBe('2.10x');
  });
});

describe('QuantPaperBookCard council v2', () => {
  const book = (council_meta: QuantPaperBookItem['council_meta']): QuantPaperBookItem =>
    ({
      name: 'council_gemini',
      strategy_key: 'council_gemini',
      strategy_id: 'COUNCIL_GEMINI',
      label: 'Gemini · PAA Barbell',
      benchmark_symbol: 'SPY',
      rebalance_mode: 'monthly',
      cost_bps: 5,
      simulated_only: true,
      days: 3,
      late_days: 0,
      initial_capital: 10000,
      nav: 10010,
      cash: 0,
      cash_pct: 0,
      return_pct: 0.1,
      benchmark_return_pct: 0,
      excess_return_pct: 0.1,
      max_drawdown_pct: 0,
      benchmark_max_drawdown_pct: 0,
      weights_pct: {},
      live_target_weights_pct: {},
      positions: [],
      trade_count: 0,
      processed_days: 0,
      new_trades: [],
      recent_trades: [],
      history: [],
      report_text: '',
      council_meta,
    }) as QuantPaperBookItem;

  it('shows the v2 verdict, BIL Sharpe and the failed checks', () => {
    render(
      <QuantPaperBookCard
        stepping={false}
        onStep={() => undefined}
        books={[
          book({
            engine_label: 'Google Gemini CLI',
            rule_engine: 'paa_custom',
            oos_backtest: { sharpe: 0.75, excess_sharpe: 0.19, max_drawdown_pct: -15.4 },
            council_v2: {
              version: 2,
              verdict: 'FAIL',
              checks: [
                { key: 'oos_verdict', label: 'OOS kararı', value: 'PASS_SOLID', target: 'PASS', ok: true },
                { key: 'cost_stress', label: '25 bps maliyette BIL üstü Sharpe', value: 0.04, target: '>= 0.15', ok: false },
              ],
            },
          }),
        ]}
      />,
    );
    expect(screen.getByTestId('council-v2-council_gemini')).toHaveTextContent('Konsey v2: kaldı');
    expect(screen.getByText(/OOS BIL üstü Sharpe 0\.19/)).toBeInTheDocument();
    expect(screen.getByText(/25 bps maliyette BIL üstü Sharpe: 0.04/)).toBeInTheDocument();
    expect(screen.queryByText(/OOS kararı:/)).not.toBeInTheDocument();
  });

  it('keeps legacy council books without v2 readable', () => {
    render(
      <QuantPaperBookCard
        stepping={false}
        onStep={() => undefined}
        books={[book({ engine_label: 'Claude', rule_engine: 'vol_target_trend', oos_backtest: { sharpe: 0.94 } })]}
      />,
    );
    expect(screen.queryByTestId('council-v2-council_gemini')).not.toBeInTheDocument();
    expect(screen.getByText(/OOS Sharpe \(Rf=0\) 0\.94/)).toBeInTheDocument();
    expect(screen.queryByText(/BIL üstü/)).not.toBeInTheDocument();
  });
});
