import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { alphaApi } from '../../../api/alpha';
import { QuantTearsheetCard } from '../QuantTearsheetCard';

vi.mock('../../../api/alpha', () => ({
  alphaApi: {
    getQuantTearsheet: vi.fn(),
  },
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AreaChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Area: () => null,
  Line: () => null,
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  ReferenceLine: () => null,
  Tooltip: () => null,
}));

describe('QuantTearsheetCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(alphaApi.getQuantTearsheet).mockResolvedValue({
      ok: true,
      strategy_key: 'meta_a',
      label: 'Meta-Portföy A v2',
      mode: 'backtest',
      metrics: {
        cagr_pct: 10.92,
        excess_sharpe: 0.83,
        max_drawdown_pct: -8.32,
        win_months_pct: 66.7,
        best_month_pct: 7.5,
        worst_month_pct: -3.2,
      },
      monthly_matrix: [
        { year: 2026, months: { '1': 1.2, '2': -0.8, '11': 0.5 }, ytd_pct: 4.1 },
      ],
      underwater: [
        { date: '2026-01-01', nav_idx: 100, drawdown_pct: 0, benchmark_dd_pct: 0 },
        { date: '2026-11-20', nav_idx: 104.1, drawdown_pct: -1.1, benchmark_dd_pct: -4.2 },
      ],
      currency_comparison: {
        usd_1y_return_pct: 11.0,
        usd_try_spot: 50.0,
        usd_try_1y_change_pct: 25.0,
        try_equivalent_1y_return_pct: 38.75,
        cpi_yoy_pct: 35.0,
        real_tufe_1y_return_pct: 2.78,
        cpi_source: 'tcmb_evds2',
      },
    });
  });

  it('renders KPI strip, heatmap, and switches strategy cleanly', async () => {
    render(<QuantTearsheetCard />);

    expect(await screen.findByText('2026')).toBeInTheDocument();
    expect(screen.getByText('+10.92%')).toBeInTheDocument();
    expect(screen.getByText('+4.1%')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Tearsheet Stratejisi'), { target: { value: 'v3_trp' } });
    await waitFor(() => {
      expect(alphaApi.getQuantTearsheet).toHaveBeenCalledWith('v3_trp', 'backtest');
    });
  });
});
