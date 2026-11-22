import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { bridgesApi } from '../../../api/bridges';
import { BrokerAdaptersPanel } from '../BrokerAdaptersPanel';

vi.mock('../../../api/bridges', () => ({
  bridgesApi: {
    getAdapters: vi.fn(),
    previewAdapterPlan: vi.fn(),
    submitAdapterPaperOrder: vi.fn(),
  },
}));

describe('BrokerAdaptersPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(bridgesApi.getAdapters).mockResolvedValue({
      ok: true,
      adapters: [
        {
          brokerId: 'alpaca',
          displayName: 'Alpaca ABD Hisse & ETF (Paper)',
          configured: false,
          sandbox: true,
          readOnlyEnforced: false,
          modeLabel: 'Paper Sanal',
          note: 'ABD ETF planı',
        },
        {
          brokerId: 'algolab',
          displayName: 'Deniz Yatırım AlgoLab (BIST)',
          configured: false,
          sandbox: true,
          readOnlyEnforced: true,
          modeLabel: 'Salt-Okunur (BIST)',
          note: 'Yalnızca önizleme',
        },
      ],
      auditTail: [],
    });
    vi.mocked(bridgesApi.previewAdapterPlan).mockResolvedValue({
      ok: true,
      brokerId: 'alpaca',
      strategyKey: 'meta_a',
      sandbox: true,
      readOnlyEnforced: false,
      currency: 'USD',
      capital: 10000,
      targetWeights: { BIL: 80, SHY: 20 },
      orders: [
        { symbol: 'BIL', side: 'BUY', targetWeightPct: 80, deltaNotional: 8000, currency: 'USD' },
        { symbol: 'SHY', side: 'BUY', targetWeightPct: 20, deltaNotional: 2000, currency: 'USD' },
      ],
      copyText: 'ALPACA PREVIEW: BIL BUY $8000',
    });
  });

  it('loads unified adapters and calculates rebalance order preview on demand', async () => {
    render(<BrokerAdaptersPanel />);

    expect(await screen.findByText('Alpaca ABD Hisse & ETF (Paper)')).toBeInTheDocument();
    expect(screen.getByText('Deniz Yatırım AlgoLab (BIST)')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Emir Planını Hesapla/i }));

    await waitFor(() => {
      expect(bridgesApi.previewAdapterPlan).toHaveBeenCalledWith({
        brokerId: 'alpaca',
        strategyKey: 'meta_a',
        capital: 10000,
      });
      expect(screen.getByText('BIL')).toBeInTheDocument();
      expect(screen.getByText('SHY')).toBeInTheDocument();
    });
  });
});
