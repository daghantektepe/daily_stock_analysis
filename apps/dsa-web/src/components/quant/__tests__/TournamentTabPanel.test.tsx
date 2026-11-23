import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { alphaApi } from '../../../api/alpha';
import { TournamentTabPanel } from '../TournamentTabPanel';

vi.mock('../../../api/alpha', () => ({
  alphaApi: {
    getTournament: vi.fn(),
    getPaaSignal: vi.fn(),
    getQuantPaperBooks: vi.fn(),
    getForwardValidation: vi.fn(),
    getResearchV4Summary: vi.fn(),
    getQuantTearsheet: vi.fn(),
    runTournament: vi.fn(),
    stepQuantPaperBooks: vi.fn(),
  },
}));

vi.mock('../QuantTearsheetCard', () => ({
  QuantTearsheetCard: () => <div data-testid="mock-tearsheet-card" />,
}));

vi.mock('../StrategyEquityChart', () => ({
  StrategyEquityChart: () => <div data-testid="mock-equity-chart" />,
}));

vi.mock('../TournamentLeaderboard', () => ({
  TournamentLeaderboard: () => <div data-testid="mock-leaderboard" />,
}));

vi.mock('../QuantPaperBookCard', () => ({
  QuantPaperBookCard: () => <div data-testid="mock-paper-book" />,
}));

vi.mock('../ForwardValidationCard', () => ({
  ForwardValidationCard: () => <div data-testid="mock-forward-card" />,
}));

vi.mock('../../chat/copilotEvents', () => ({
  openCopilotDrawer: vi.fn(),
}));

describe('TournamentTabPanel v4 short card', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(alphaApi.getTournament).mockResolvedValue({
      total_strategies: 25,
      total_assets: 42,
      total_asset_days: 1000,
      oos_start: '2022-01-01',
      latest_date: '2026-11-20',
      pass_elite_count: 1,
      pass_solid_count: 2,
      featured_strategy_ids: [],
      strategies: [],
    });
    vi.mocked(alphaApi.getPaaSignal).mockResolvedValue({
      as_of_date: '2026-11-20',
      risk_assets_total: 0,
      risk_assets_below_sma252: 0,
      crash_protection_pct: 100,
      regime_label: 'FULL_CRASH_SHIELD',
      target_weights_pct: {},
      risk_asset_breadth: [],
    });
    vi.mocked(alphaApi.getQuantPaperBooks).mockResolvedValue({
      ok: true,
      simulated_only: true,
      strategies: [],
      total_new_trades: 0,
      books: [],
      report_text: '',
    });
    vi.mocked(alphaApi.getForwardValidation).mockResolvedValue({
      ok: true,
      simulated_only: true,
      items: [],
      report_text: '',
    });
  });

  it('shows the compact v4 short card when ok=true and hides it when ok=false', async () => {
    vi.mocked(alphaApi.getResearchV4Summary).mockResolvedValue({
      ok: true,
      data_start: '2008-01-01',
      data_end: '2026-11-20',
      short_vs_control: {
        long_short: { excess_sharpe_5bps: 0.51, return_2008_pct: 17.4 },
        long_only_control: { excess_sharpe_5bps: 0.68, return_2008_pct: 11.3 },
        short_adds_value: false,
        reasons: [],
      },
    });

    const { unmount } = render(<TournamentTabPanel />);
    const card = await screen.findByTestId('research-v4-card');
    expect(card).toHaveTextContent('Short testi (ters ETF): değer katmıyor');
    expect(card).toHaveTextContent('0,51');
    expect(card).toHaveTextContent('0,68');
    unmount();

    vi.mocked(alphaApi.getResearchV4Summary).mockResolvedValue({
      ok: false,
      error: 'Veri yok',
    });
    render(<TournamentTabPanel />);
    await waitFor(() => {
      expect(alphaApi.getResearchV4Summary).toHaveBeenCalledTimes(2);
    });
    expect(screen.queryByTestId('research-v4-card')).not.toBeInTheDocument();
  });
});
