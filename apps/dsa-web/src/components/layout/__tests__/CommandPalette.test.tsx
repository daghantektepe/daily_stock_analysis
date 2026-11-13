import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CommandPalette } from '../CommandPalette';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('../../../hooks/useStockIndex', () => ({
  useStockIndex: () => ({
    index: [
      {
        canonicalCode: 'NVDA',
        displayCode: 'NVDA',
        nameZh: 'NVIDIA',
        nameEn: 'NVIDIA Corp',
        pinyinFull: 'nvidia',
        pinyinAbbr: 'nvda',
        aliases: [],
        market: 'US',
        assetType: 'stock',
        active: true,
        popularity: 100,
      },
      {
        canonicalCode: 'THYAO.IS',
        displayCode: 'THYAO',
        nameZh: 'Türk Hava Yolları',
        nameEn: 'Turk Hava Yollari',
        pinyinFull: 'thyao',
        pinyinAbbr: 'thy',
        aliases: [],
        market: 'TR',
        assetType: 'stock',
        active: true,
        popularity: 95,
      },
    ],
    loading: false,
    loaded: true,
  }),
}));

describe('CommandPalette', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens on Ctrl+K, filters by market, and navigates to Home with autoAnalyze', async () => {
    render(
      <MemoryRouter>
        <CommandPalette />
      </MemoryRouter>,
    );

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });

    const input = await screen.findByPlaceholderText(/Hisse kodu \/ şirket adı yazın/i);
    expect(input).toBeInTheDocument();

    fireEvent.change(input, { target: { value: 'NVDA' } });

    await waitFor(() => {
      expect(screen.getByText('NVIDIA')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('NVIDIA'));

    expect(navigateMock).toHaveBeenCalledWith('/', {
      state: {
        stockCode: 'NVDA',
        stockName: 'NVIDIA',
        autoAnalyze: true,
        selectionSource: 'autocomplete',
      },
    });
  });
});
