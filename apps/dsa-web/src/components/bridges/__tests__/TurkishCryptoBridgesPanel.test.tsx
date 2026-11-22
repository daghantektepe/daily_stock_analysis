import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { bridgesApi } from '../../../api/bridges';
import { TurkishCryptoBridgesPanel } from '../TurkishCryptoBridgesPanel';

vi.mock('../../../api/bridges', () => ({
  bridgesApi: {
    getStatus: vi.fn(),
    getMacroTr: vi.fn(),
    getTefasFunds: vi.fn(),
    getBinancePreview: vi.fn(),
  },
}));

describe('TurkishCryptoBridgesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(bridgesApi.getStatus).mockResolvedValue({
      ok: true,
      checkedLive: false,
      bridges: [
        {
          id: 'binance',
          name: 'Binance Spot & Testnet',
          kind: 'crypto',
          configured: false,
          sandboxOrReadonly: true,
          modeLabel: 'Testnet Sanal',
          liveReachable: null,
          note: 'Kripto test kilidi açık',
          details: {},
        },
      ],
    });
    vi.mocked(bridgesApi.getMacroTr).mockResolvedValue({
      ok: true,
      evdsConfigured: false,
      usdTry: 50.0,
      usdTry1yChangePct: 25.0,
      usdTryAsOf: '2026-11-20',
      usdTrySource: 'yahoo_try_x_fallback',
      cpiYoyPct: 35.0,
      cpiMomPct: 2.0,
      cpiAsOf: '2026-10',
      cpiSource: 'tcmb_evds2',
      cached: false,
      purchasingPower: {
        nominalReturnPct: 45.0,
        usdBasedReturnPct: 16.0,
        realTufeReturnPct: 7.41,
        beatsInflation: true,
      },
    });
    vi.mocked(bridgesApi.getTefasFunds).mockResolvedValue({
      ok: true,
      count: 2,
      liveCount: 2,
      funds: [
        {
          code: 'PPZ',
          title: 'Azimut Para Piyasası Fonu',
          category: 'Para Piyasası',
          bucket: 'ppf',
          globalProxy: 'BIL',
          priceTry: 7.193,
          dailyReturnPct: 0.09,
          fundSizeTry: 9_900_000_000,
          investors: 7000,
          categoryRank: 25,
          categoryTotal: 86,
          marketSharePct: 0.62,
          source: 'tefas_live',
        },
        {
          code: 'AFT',
          title: 'Ak Portföy Yeni Teknolojiler',
          category: 'Hisse',
          bucket: 'yabanci',
          globalProxy: 'QQQ',
          priceTry: 0.8591,
          dailyReturnPct: 2.35,
          fundSizeTry: 14_000_000_000,
          investors: 120000,
          categoryRank: 101,
          categoryTotal: 201,
          marketSharePct: 10.0,
          source: 'tefas_live',
        },
      ],
    });
    vi.mocked(bridgesApi.getBinancePreview).mockResolvedValue({
      ok: true,
      testnet: true,
      configured: false,
      autoExecute: false,
      tickers: [
        {
          asset: 'BTC-USD',
          symbol: 'BTCUSDT',
          lastPrice: 90000,
          bid: 89995,
          ask: 90005,
          spreadBps: 1.11,
          priceChangePct24h: 1.25,
          quoteVolumeUsdt24h: 1000000,
          source: 'binance_public',
        },
      ],
      account: null,
    });
  });

  it('renders EVDS purchasing power, Binance ticker, and filters TEFAS buckets', async () => {
    render(<TurkishCryptoBridgesPanel />);

    expect(await screen.findByText('PPZ')).toBeInTheDocument();
    expect(screen.getByText('AFT')).toBeInTheDocument();
    expect(screen.getByText('BTCUSDT')).toBeInTheDocument();
    expect(screen.getByText('+16.00%')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Para Piyasası (PPF)' }));
    await waitFor(() => {
      expect(screen.getByText('PPZ')).toBeInTheDocument();
      expect(screen.queryByText('AFT')).not.toBeInTheDocument();
    });
  });
});
