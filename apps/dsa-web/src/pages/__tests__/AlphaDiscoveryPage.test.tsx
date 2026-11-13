import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { alphaApi } from '../../api/alpha';
import { analysisApi } from '../../api/analysis';
import AlphaDiscoveryPage from '../AlphaDiscoveryPage';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('../../api/alpha', () => ({
  alphaApi: {
    getOverview: vi.fn(),
    runUsScreen: vi.fn(),
    getForm4Live: vi.fn(),
    getPeadCandidates: vi.fn(),
    runPeadStudy: vi.fn(),
    runBistScreen: vi.fn(),
    getKapContracts: vi.fn(),
  },
}));

vi.mock('../../api/analysis', () => ({
  analysisApi: {
    analyzeAsync: vi.fn(),
  },
}));

describe('AlphaDiscoveryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('runs US High-Alpha screen and allows 1-click navigation and guarded bulk analysis', async () => {
    vi.mocked(alphaApi.runUsScreen).mockResolvedValue({
      count: 1,
      items: [
        {
          symbol: 'NVDA',
          score: 88.5,
          pead_score: 72,
          insider_score: 40,
          near_52w_high: 0.99,
          residual_momentum_z: 1.85,
          reasons: ['Yüksek rölatif güç'],
        },
      ],
    });
    vi.mocked(analysisApi.analyzeAsync).mockResolvedValue({
      taskId: 'task-1',
      status: 'pending',
    });

    render(
      <MemoryRouter>
        <AlphaDiscoveryPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: /^Taramayı Başlat$/i }));

    await waitFor(() => {
      expect(screen.getByText('NVDA')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /^Analiz Et$/i }));
    expect(navigateMock).toHaveBeenCalledWith('/', {
      state: expect.objectContaining({
        stockCode: 'NVDA',
        autoAnalyze: true,
        selectionSource: 'autocomplete',
      }),
    });

    expect(screen.getByLabelText('Seç NVDA')).toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: /Seçili 1 Hisseyi Analiz Et/i }));
    expect(screen.getByText(/Toplu AI Analiz Onayı/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Analizi Başlat$/i }));
    await waitFor(() => {
      expect(analysisApi.analyzeAsync).toHaveBeenCalledWith({
        stockCodes: ['NVDA'],
      });
    });
  });
});
