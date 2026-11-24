import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import PaperTradingPage from '../PaperTradingPage';

vi.mock('../../components/bridges/BrokerAdaptersPanel', () => ({
  BrokerAdaptersPanel: () => <div data-testid="mock-broker-adapters-panel" />,
}));

vi.mock('../../api/paperTrading', () => ({
  paperTradingApi: {
    getSummary: vi.fn().mockResolvedValue({
      enabled: true,
      position_size: 10000,
      risk_pct: 5,
      trade_count: 0,
      open_position_count: 0,
      closed_trade_count: 0,
      stop_loss_count: 0,
      take_profit_count: 0,
      win_rate_pct: null,
      positions: [],
      totals_by_currency: {},
      benchmarks: {},
      signal_outcomes: {
        total: 16,
        completed: 4,
        hit: 0,
        miss: 3,
        neutral: 1,
        hit_rate_pct: 0,
        avg_stock_return_pct: 4.39,
        duplicate_checks_merged: 168,
        by_horizon: {
          '1d': { completed: 4, hit: 0, miss: 3, neutral: 1, hit_rate_pct: 0, avg_stock_return_pct: 4.39 },
        },
        benchmark_comparison: {
          primary_horizon: '10d',
          min_sample: 30,
          groups: {
            buy: { n: 0, beats: 0, beat_rate_pct: null, avg_excess_pct: null, sample_sufficient: false },
            sell: { n: 0, beats: 0, beat_rate_pct: null, avg_excess_pct: null, sample_sufficient: false },
          },
          by_horizon: {
            '1d': {
              buy: { n: 0, beats: 0, beat_rate_pct: null, avg_excess_pct: null, sample_sufficient: false },
              sell: { n: 3, beats: 1, beat_rate_pct: 33.3, avg_excess_pct: 0.86, sample_sufficient: false },
            },
          },
          no_benchmark_markets: ['cn'],
          no_benchmark_count: 1,
        },
        weekly_watch: {
          week: '2026-W48',
          total: 27,
          watch: 22,
          watch_pct: 81.5,
          line: "Bu hafta: 27 sinyal, %82'si izle",
          alert_four_weeks_over_70: false,
          alert_line: null,
        },
      },
      risk_status: {},
    }),
    listTrades: vi.fn().mockResolvedValue({ items: [] }),
    listKapAlerts: vi.fn().mockResolvedValue({ items: [] }),
    getEquityCurve: vi.fn().mockResolvedValue({ points: [], currencies: [] }),
    getAlpacaStatus: vi.fn().mockResolvedValue(null),
  },
}));

describe('PaperTradingPage', () => {
  it('renders 1d benchmark preview, duplicate merge count, and weekly watch ratio', async () => {
    render(<PaperTradingPage />);

    const benchBox = await screen.findByTestId('paper-signal-benchmark');
    expect(benchBox).toHaveTextContent('Endekse Göre Sinyal Başarısı (10g henüz dolmadı · 1 Gün ön izleme)');
    expect(benchBox).toHaveTextContent('%33 endeksi geçti');
    expect(benchBox).toHaveTextContent('n=3 · ort. fark +0.86% · örnek yetersiz (<30)');
    expect(benchBox).toHaveTextContent('Endekse göre: cn pazarı için endeks yok (n=1)');

    expect(screen.getByText('Aynı gün tekrarlanan 168 kontrol birleştirildi')).toBeInTheDocument();
    expect(screen.getByTestId('paper-weekly-watch')).toHaveTextContent("Bu hafta: 27 sinyal, %82'si izle");
  });
});
