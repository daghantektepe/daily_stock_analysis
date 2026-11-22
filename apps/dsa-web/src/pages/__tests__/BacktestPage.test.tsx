import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import { UI_LANGUAGE_STORAGE_KEY } from '../../utils/uiLanguage';
import BacktestPage from '../BacktestPage';

const {
  mockGetResults,
  mockGetOverallPerformance,
  mockGetStockPerformance,
  mockRun,
} = vi.hoisted(() => ({
  mockGetResults: vi.fn(),
  mockGetOverallPerformance: vi.fn(),
  mockGetStockPerformance: vi.fn(),
  mockRun: vi.fn(),
}));

vi.mock('../../api/backtest', () => ({
  backtestApi: {
    getResults: mockGetResults,
    getOverallPerformance: mockGetOverallPerformance,
    getStockPerformance: mockGetStockPerformance,
    run: mockRun,
  },
}));

const basePerformance = {
  scope: 'overall',
  evalWindowDays: 10,
  engineVersion: 'test-engine',
  totalEvaluations: 3,
  completedCount: 2,
  insufficientCount: 1,
  longCount: 2,
  cashCount: 1,
  winCount: 1,
  lossCount: 1,
  neutralCount: 0,
  directionAccuracyPct: 66.7,
  winRatePct: 50,
  neutralRatePct: 0,
  avgStockReturnPct: 2.4,
  avgSimulatedReturnPct: 1.2,
  stopLossTriggerRate: 10,
  takeProfitTriggerRate: 20,
  ambiguousRate: 0,
  avgDaysToFirstHit: 3.5,
  adviceBreakdown: {},
  diagnostics: {},
};

const baseResultItem = {
  analysisHistoryId: 101,
  code: '600519',
  stockName: '贵州茅台',
  analysisDate: '2026-03-20',
  evalWindowDays: 10,
  engineVersion: 'test-engine',
  evalStatus: 'completed',
  operationAdvice: '继续持有',
  action: 'watch',
  actionLabel: '观望',
  trendPrediction: '震荡偏多',
  actualMovement: 'up',
  actualReturnPct: 3.8,
  directionExpected: 'long',
  directionCorrect: true,
  outcome: 'win',
  simulatedReturnPct: 3.8,
};

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  mockGetOverallPerformance.mockResolvedValue(basePerformance);
  mockGetStockPerformance.mockResolvedValue(null);
  mockGetResults.mockResolvedValue({
    total: 1,
    page: 1,
    limit: 20,
    items: [baseResultItem],
  });
  mockRun.mockResolvedValue({
    processed: 1,
    saved: 1,
    completed: 1,
    insufficient: 0,
    errors: 0,
  });
});

describe('BacktestPage', () => {
  function renderEnglishPage() {
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');
    render(
      <UiLanguageProvider>
        <BacktestPage />
      </UiLanguageProvider>,
    );
  }

  it('renders shared surface inputs and prediction tracking outputs', async () => {
    render(<BacktestPage />);

    const filterInput = await screen.findByPlaceholderText('Sembole göre filtrele (tümü için boş bırakın)');
    const windowInput = screen.getByPlaceholderText('10');

    expect(filterInput).toHaveClass('input-surface');
    expect(filterInput).toHaveClass('input-focus-glow');
    expect(windowInput).toHaveClass('input-surface');
    expect(windowInput).toHaveClass('input-focus-glow');

    expect(await screen.findByText('Kazanç')).toBeInTheDocument();
    expect(screen.getByText('Tamamlandı')).toBeInTheDocument();
    expect(screen.getByText('600519')).toBeInTheDocument();
    expect(screen.getByText('贵州茅台')).toBeInTheDocument();
    const resultRow = screen.getByText('600519').closest('tr');
    expect(resultRow).not.toBeNull();
    const rowScope = within(resultRow as HTMLElement);
    expect(rowScope.getByText('Watch')).toBeInTheDocument();
    expect(rowScope.getByText('震荡偏多')).toBeInTheDocument();
    expect(rowScope.getByText('继续持有')).toBeInTheDocument();
    expect(screen.getByText('Yükseliş')).toBeInTheDocument();
    expect(screen.getByText('Pencere getirisi')).toBeInTheDocument();
    expect(screen.getByText('Yön eşleşmesi')).toBeInTheDocument();
    expect(screen.getByText('Alım (Long)')).toBeInTheDocument();
    expect(screen.getAllByLabelText('Evet').length).toBeGreaterThan(0);
    expect(screen.getByText('Yön isabet oranı')).toBeInTheDocument();
    expect(screen.getByText('Ort. simüle getiri')).toBeInTheDocument();
  });

  it('falls back to the taxonomy label when backtest actionLabel is missing', async () => {
    mockGetResults.mockResolvedValueOnce({
      total: 1,
      page: 1,
      limit: 20,
      items: [
        {
          ...baseResultItem,
          action: 'watch',
          actionLabel: null,
        },
      ],
    });

    render(<BacktestPage />);

    const codeCell = await screen.findByText('600519');
    const resultRow = codeCell.closest('tr');
    expect(resultRow).not.toBeNull();
    const rowScope = within(resultRow as HTMLElement);
    expect(rowScope.getByText('Watch')).toBeInTheDocument();
    expect(rowScope.getByText('继续持有')).toBeInTheDocument();
  });

  it('uses localized taxonomy labels before server labels in English UI mode', async () => {
    mockGetResults.mockResolvedValueOnce({
      total: 1,
      page: 1,
      limit: 20,
      items: [
        {
          ...baseResultItem,
          operationAdvice: 'continue holding',
          action: 'watch',
          actionLabel: '观望',
          trendPrediction: 'range-bound',
        },
      ],
    });

    renderEnglishPage();

    const codeCell = await screen.findByText('600519');
    const resultRow = codeCell.closest('tr');
    expect(resultRow).not.toBeNull();
    const rowScope = within(resultRow as HTMLElement);
    expect(rowScope.getByText('Watch')).toBeInTheDocument();
    expect(rowScope.getByText('continue holding')).toBeInTheDocument();
    expect(rowScope.queryByText('观望')).not.toBeInTheDocument();
  });

  it('keeps operation advice visible when backtest action fields are absent for multi-guard advice', async () => {
    mockGetResults.mockResolvedValueOnce({
      total: 1,
      page: 1,
      limit: 20,
      items: [
        {
          ...baseResultItem,
          operationAdvice: 'risk alert, avoid buying',
          action: null,
          actionLabel: null,
        },
      ],
    });

    render(<BacktestPage />);

    const codeCell = await screen.findByText('600519');
    const resultRow = codeCell.closest('tr');
    expect(resultRow).not.toBeNull();
    const rowScope = within(resultRow as HTMLElement);
    expect(rowScope.getByText('震荡偏多')).toBeInTheDocument();
    expect(rowScope.getByText('risk alert, avoid buying')).toBeInTheDocument();
    expect(rowScope.queryByText('Avoid')).not.toBeInTheDocument();
    expect(rowScope.queryByText('Alert')).not.toBeInTheDocument();
  });

  it('renders backtest controls and result headings in English UI mode', async () => {
    renderEnglishPage();

    expect(await screen.findByPlaceholderText('Filter by stock code (leave empty for all)')).toBeInTheDocument();
    expect(screen.getByText('Evaluation window')).toBeInTheDocument();
    expect(screen.getAllByText('Phase').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Run backtest' })).toBeInTheDocument();
    expect(screen.getByText('Window return')).toBeInTheDocument();
    expect(screen.getByText('Direction match')).toBeInTheDocument();
    expect(screen.getByText('Direction accuracy')).toBeInTheDocument();
    expect(screen.queryByText('Testi Çalıştır')).not.toBeInTheDocument();
    expect(screen.queryByText('Pencere getirisi')).not.toBeInTheDocument();
  });

  it('filters results with stock code, window, phase, and analysis date range when clicking Filter', async () => {
    render(<BacktestPage />);

    const filterInput = await screen.findByPlaceholderText('Sembole göre filtrele (tümü için boş bırakın)');
    const windowInput = screen.getByPlaceholderText('10');
    const phaseSelect = screen.getByDisplayValue('Tüm fazlar');
    const fromInput = screen.getByLabelText('Analiz başlangıç tarihi');
    const toInput = screen.getByLabelText('Analiz bitiş tarihi');

    fireEvent.change(filterInput, { target: { value: 'aapl' } });
    fireEvent.change(windowInput, { target: { value: '20' } });
    fireEvent.change(phaseSelect, { target: { value: 'intraday' } });
    fireEvent.change(fromInput, { target: { value: '2026-03-01' } });
    fireEvent.change(toInput, { target: { value: '2026-03-31' } });
    fireEvent.click(screen.getByRole('button', { name: 'Filtrele' }));

    await waitFor(() => {
      expect(mockGetResults).toHaveBeenLastCalledWith({
        code: 'AAPL',
        evalWindowDays: 20,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: 'intraday',
        page: 1,
        limit: 20,
      });
      expect(mockGetStockPerformance).toHaveBeenLastCalledWith('AAPL', {
        evalWindowDays: 20,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: 'intraday',
      });
    });
  });

  it('runs a backtest and refreshes results using the shared filter values', async () => {
    mockRun.mockResolvedValueOnce({
      processed: 0,
      saved: 0,
      completed: 0,
      insufficient: 0,
      errors: 0,
      message: '未找到符合条件的历史分析记录',
      diagnostics: { emptyReason: 'no_matching_analysis' },
    });
    render(<BacktestPage />);

    const filterInput = await screen.findByPlaceholderText('Sembole göre filtrele (tümü için boş bırakın)');
    const windowInput = screen.getByPlaceholderText('10');
    const fromInput = screen.getByLabelText('Analiz başlangıç tarihi');
    const toInput = screen.getByLabelText('Analiz bitiş tarihi');

    fireEvent.change(filterInput, { target: { value: '600519.SH' } });
    fireEvent.change(windowInput, { target: { value: '15' } });
    fireEvent.change(fromInput, { target: { value: '2026-03-01' } });
    fireEvent.change(toInput, { target: { value: '2026-03-31' } });
    fireEvent.click(screen.getByRole('button', { name: 'Testi Çalıştır' }));

    await waitFor(() => {
      expect(mockRun).toHaveBeenCalledWith({
        code: '600519.SH',
        force: undefined,
        minAgeDays: undefined,
        evalWindowDays: 15,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
      });
    });

    await waitFor(() => {
      expect(mockGetResults).toHaveBeenLastCalledWith({
        code: '600519.SH',
        evalWindowDays: 15,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: undefined,
        page: 1,
        limit: 20,
      });
      expect(mockGetStockPerformance).toHaveBeenLastCalledWith('600519.SH', {
        evalWindowDays: 15,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: undefined,
      });
    });

    expect(await screen.findByText('İşlenen:')).toBeInTheDocument();
    expect(screen.getByText('Kaydedilen:')).toBeInTheDocument();
    expect(screen.getByText('未找到符合条件的历史分析记录')).toBeInTheDocument();
  });

  it('uses backend-applied eval window when run input is empty', async () => {
    mockRun.mockResolvedValueOnce({
      processed: 0,
      saved: 0,
      completed: 0,
      insufficient: 0,
      errors: 0,
      appliedEvalWindowDays: 10,
      message: '未找到符合条件的历史分析记录',
      diagnostics: { emptyReason: 'no_matching_analysis' },
    });
    render(<BacktestPage />);

    const filterInput = await screen.findByPlaceholderText('Sembole göre filtrele (tümü için boş bırakın)');
    const windowInput = screen.getByPlaceholderText('10');
    const fromInput = screen.getByLabelText('Analiz başlangıç tarihi');
    const toInput = screen.getByLabelText('Analiz bitiş tarihi');

    fireEvent.change(filterInput, { target: { value: '600519.SH' } });
    fireEvent.change(windowInput, { target: { value: '' } });
    fireEvent.change(fromInput, { target: { value: '2026-03-01' } });
    fireEvent.change(toInput, { target: { value: '2026-03-31' } });
    fireEvent.click(screen.getByRole('button', { name: 'Testi Çalıştır' }));

    await waitFor(() => {
      expect(mockRun).toHaveBeenCalledWith({
        code: '600519.SH',
        force: undefined,
        minAgeDays: undefined,
        evalWindowDays: undefined,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
      });
    });

    await waitFor(() => {
      expect(windowInput).toHaveValue(10);
      expect(mockGetResults).toHaveBeenLastCalledWith({
        code: '600519.SH',
        evalWindowDays: 10,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: undefined,
        page: 1,
        limit: 20,
      });
      expect(mockGetStockPerformance).toHaveBeenLastCalledWith('600519.SH', {
        evalWindowDays: 10,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: undefined,
      });
      expect(mockGetOverallPerformance).toHaveBeenLastCalledWith({
        evalWindowDays: 10,
        analysisDateFrom: '2026-03-01',
        analysisDateTo: '2026-03-31',
        analysisPhase: undefined,
      });
    });

    expect(await screen.findByText('未找到符合条件的历史分析记录')).toBeInTheDocument();
  });

  it('switches to next-day validation with the 1D shortcut', async () => {
    render(<BacktestPage />);

    await screen.findByPlaceholderText('Sembole göre filtrele (tümü için boş bırakın)');
    fireEvent.click(screen.getByRole('button', { name: '1G doğrulama' }));

    await waitFor(() => {
      expect(mockGetResults).toHaveBeenLastCalledWith({
        code: undefined,
        evalWindowDays: 1,
        analysisDateFrom: undefined,
        analysisDateTo: undefined,
        analysisPhase: undefined,
        page: 1,
        limit: 20,
      });
      expect(mockGetOverallPerformance).toHaveBeenLastCalledWith({
        evalWindowDays: 1,
        analysisDateFrom: undefined,
        analysisDateTo: undefined,
        analysisPhase: undefined,
      });
    });

    expect(screen.getByText('Gerçekleşen')).toBeInTheDocument();
    expect(screen.getByText('İsabet')).toBeInTheDocument();
    expect(screen.getByText('1G doğrulama modu AI tahminlerini bir sonraki işlem günü kapanışıyla karşılaştırır.')).toBeInTheDocument();
  });
});
