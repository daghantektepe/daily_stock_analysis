import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CommandPalette } from '../CommandPalette';
import { openCommandPalette } from '../commandPaletteEvents';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('../../../hooks/useStockIndex', () => ({
  useStockIndex: () => ({ index: [], loading: false }),
}));

describe('CommandPalette', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens on custom event, switches BIST suffix, navigates to manual stock analysis, and closes on Escape', () => {
    render(
      <MemoryRouter>
        <CommandPalette />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    act(() => {
      openCommandPalette();
    });
    expect(screen.getByRole('dialog', { name: 'Hızlı Arama ve Komut Paleti' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'BIST (TR)' }));
    const input = screen.getByPlaceholderText(/Hisse kodu/i);
    fireEvent.change(input, { target: { value: 'THYAO' } });

    const manualItem = screen.getByRole('button', { name: /THYAO\.IS kodunu doğrudan analiz et/i });
    fireEvent.click(manualItem);

    expect(navigateMock).toHaveBeenCalledWith('/', {
      state: expect.objectContaining({
        stockCode: 'THYAO.IS',
        autoAnalyze: true,
      }),
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    // Re-open and close cleanly via Escape
    act(() => {
      openCommandPalette();
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
