import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { alphaApi, type SimpleBriefResponse } from '../../api/alpha';
import SimpleInvestorHomePage from '../SimpleInvestorHomePage';

const openCopilotMock = vi.fn();

vi.mock('../../components/chat/copilotEvents', () => ({
  openCopilotDrawer: (...args: unknown[]) => openCopilotMock(...args),
}));

vi.mock('../../api/alpha', () => ({
  alphaApi: {
    getSimpleBrief: vi.fn(),
  },
}));

const MOCK_BRIEF: SimpleBriefResponse = {
  ok: true,
  simulated_only: true,
  as_of_date: '2026-11-20',
  usdtry_rate: 50.0,
  weather: {
    status: 'stormy',
    emoji: '⛈️',
    badge_label: 'Koruma Kalkanı Açık',
    headline: 'Piyasalar Şu An Fırtınalı — Paranı Güvende Tut',
    plain_summary: 'Sistem koruma kalkanını açtı.',
    behavioral_guard: 'Sakin kal ve panik işlem yapma.',
    protection_pct: 100,
  },
  decision_steps: [
    { step: 1, title: 'Piyasa Nabzı Kontrol Edildi', status: 'warning', explanation: 'Borsalar zayıf.', glossary_term: 'trend_kalkan' },
    { step: 2, title: 'Koruma Kalkanı Devreye Girdi', status: 'shield', explanation: 'Kalkan %100 açık.', glossary_term: 'risk_off' },
    { step: 3, title: 'Para Güvenli Limana Alındı', status: 'safe', explanation: 'Nakit/bono ağırlıklı.', glossary_term: 'bil_ppf' },
  ],
  profiles: [
    {
      id: 'cautious',
      emoji: '🛡️',
      title: 'Çok Temkinli (Önce Paramı Koru)',
      subtitle: 'Sakin uyku isteyenler için',
      recommended: false,
      engine_note: 'v3 Risk Paritesi',
      historical_max_dd_pct: -7.3,
      estimated_annual_cost_pct: 0.04,
      rebalance_cadence: 'Ayda 1 kez',
      assets: [
        {
          symbol: 'BIL',
          weight_pct: 80,
          plain_name: 'ABD Kısa Vadeli Hazine Bonosu',
          role: 'Güvenli liman',
          risk_level: 'çok düşük',
          tr_equivalent: 'TEFAS Para Piyasası Fonu (PPF)',
          midas_hint: 'Midas → BIL',
        },
        {
          symbol: 'UUP',
          weight_pct: 20,
          plain_name: 'ABD Doları Endeksi',
          role: 'Dolar kalkanı',
          risk_level: 'düşük',
          tr_equivalent: 'USD / Eurobond Fonu',
          midas_hint: 'Midas → UUP',
        },
      ],
    },
    {
      id: 'balanced',
      emoji: '⚖️',
      title: 'Dengeli Kalkan (Önerilen)',
      subtitle: 'Standart kullanıcı için',
      recommended: true,
      engine_note: 'Meta-A + v3',
      historical_max_dd_pct: -5.4,
      estimated_annual_cost_pct: 0.06,
      rebalance_cadence: 'Ayda 1 kez',
      assets: [
        {
          symbol: 'BIL',
          weight_pct: 90,
          plain_name: 'ABD Kısa Vadeli Hazine Bonosu',
          role: 'Güvenli liman',
          risk_level: 'çok düşük',
          tr_equivalent: 'TEFAS Para Piyasası Fonu (PPF)',
          midas_hint: 'Midas → BIL',
        },
        {
          symbol: 'SHY',
          weight_pct: 10,
          plain_name: 'ABD 1–3 Yıllık Devlet Tahvili',
          role: 'Kısa tahvil',
          risk_level: 'çok düşük',
          tr_equivalent: 'TEFAS Kısa Vadeli Tahvil Fonu',
          midas_hint: 'Midas → SHY',
        },
      ],
    },
  ],
  paper_exam: [
    {
      strategy_key: 'v3_trp',
      plain_label: 'Çok Temkinli Kalkan (v3 Risk Paritesi)',
      frozen_date: '2026-11-20',
      fingerprint: 'ae4754108564',
      forward_days: 0,
      target_days: 120,
      nav_usd: 10000,
      initial_capital_usd: 10000,
      return_pct: 0,
      benchmark_return_pct: -3.6,
      status_plain: 'Canlı sınav sürüyor (0/120 işlem günü)',
    },
  ],
  disclaimer: 'Yalnızca eğitim ve karar destek amaçlıdır.',
};

describe('SimpleInvestorHomePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.mocked(alphaApi.getSimpleBrief).mockResolvedValue(MOCK_BRIEF);
  });

  it('renders plain-Turkish weather, computes exact TL budget slices, switches profile, and opens Copilot', async () => {
    render(
      <MemoryRouter>
        <SimpleInvestorHomePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Piyasalar Şu An Fırtınalı — Paranı Güvende Tut')).toBeInTheDocument();
    // Default budget 100,000 TL on balanced (90% BIL = 90.000 ₺, 10% SHY = 10.000 ₺)
    expect(screen.getByText('90.000 ₺')).toBeInTheDocument();
    expect(screen.getAllByText('10.000 ₺').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('TEFAS Para Piyasası Fonu (PPF)')).toBeInTheDocument();

    // Switch to cautious profile (80% BIL = 80.000 ₺, 20% UUP = 20.000 ₺)
    fireEvent.click(screen.getByRole('button', { name: /Çok Temkinli/i }));
    await waitFor(() => {
      expect(screen.getByText('80.000 ₺')).toBeInTheDocument();
      expect(screen.getByText('20.000 ₺')).toBeInTheDocument();
    });

    // Open plain-Turkish glossary tooltip
    fireEvent.click(screen.getAllByRole('button', { name: /Koruma Modu \(Risk-Off\) nedir\?/i })[0]);
    expect(screen.getByRole('dialog', { name: /Koruma Modu \(Risk-Off\) açıklaması/i })).toBeInTheDocument();

    // Open plain Copilot explanation
    fireEvent.click(screen.getByRole('button', { name: /Asistana Sade Anlattır/i }));
    expect(openCopilotMock).toHaveBeenCalledTimes(1);
    expect(String(openCopilotMock.mock.calls[0]?.[0])).toContain('anneme anlatır gibi');
  });

  it('shows a stale-data warning and never shows the banner when data is fresh', async () => {
    vi.mocked(alphaApi.getSimpleBrief).mockResolvedValue({
      ...MOCK_BRIEF,
      data_status: {
        state: 'stale',
        message: 'Veriler güncel değil: Strateji turnuvası 25 gün önceye ait (2026-11-20).',
        stale_after_days: 5,
        sources: [],
      },
    });
    const { unmount } = render(
      <MemoryRouter>
        <SimpleInvestorHomePage />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('simple-data-status')).toHaveTextContent('25 gün önceye ait');
    unmount();

    vi.mocked(alphaApi.getSimpleBrief).mockResolvedValue({
      ...MOCK_BRIEF,
      data_status: { state: 'ok', message: '', stale_after_days: 5, sources: [] },
    });
    render(
      <MemoryRouter>
        <SimpleInvestorHomePage />
      </MemoryRouter>,
    );
    expect(await screen.findByText('Piyasalar Şu An Fırtınalı — Paranı Güvende Tut')).toBeInTheDocument();
    expect(screen.queryByTestId('simple-data-status')).not.toBeInTheDocument();
  });

  it('renders an honest empty state without snapshots or FX', async () => {
    vi.mocked(alphaApi.getSimpleBrief).mockResolvedValue({
      ...MOCK_BRIEF,
      ok: false,
      as_of_date: '',
      usdtry_rate: null,
      data_status: {
        state: 'missing',
        message: 'Strateji verisi bulunamadı; bu ekran şu an öneri gösteremez.',
        stale_after_days: 5,
        sources: [],
      },
      weather: {
        status: 'unknown',
        emoji: '❔',
        badge_label: 'Veri Yok',
        headline: 'Piyasa Durumu Bilinmiyor — Önce Strateji Verisini Güncelle',
        plain_summary: 'Sinyaller okunamadı.',
        behavioral_guard: 'Değişiklik yapma.',
        protection_pct: null,
      },
      profiles: [],
    });
    render(
      <MemoryRouter>
        <SimpleInvestorHomePage />
      </MemoryRouter>,
    );
    expect(await screen.findByText('Piyasa Durumu Bilinmiyor — Önce Strateji Verisini Güncelle')).toBeInTheDocument();
    expect(screen.getByTestId('simple-data-status')).toHaveTextContent('Strateji verisi bulunamadı');
    expect(screen.getByTestId('simple-no-profiles')).toBeInTheDocument();
    expect(screen.getByText(/kur verisi yok/)).toBeInTheDocument();
    expect(screen.getByText(/Veri tarihi:/)).toHaveTextContent('bilinmiyor');
    expect(screen.queryByText(/50[.,]56/)).not.toBeInTheDocument();
    expect(screen.queryByText('90.000 ₺')).not.toBeInTheDocument();
  });

  it('shows signal accuracy states honestly (missing, insufficient n/30, and proven)', async () => {
    vi.mocked(alphaApi.getSimpleBrief).mockResolvedValue({
      ...MOCK_BRIEF,
      signal_accuracy: {
        data_status: 'insufficient',
        n: 0,
        min_sample: 30,
        summary_line: 'Yapay zekâ önerilerinin başarısı henüz ölçülüyor (0/30)',
        preview_line: "Erken ön izleme (1g): son 3 yönlü önerinin %33'i endeksi geçti (10 günlük ana ölçüm bekleniyor).",
        weekly_watch_line: "Bu hafta: 27 sinyal, %82'si izle",
      },
    });
    const { unmount } = render(
      <MemoryRouter>
        <SimpleInvestorHomePage />
      </MemoryRouter>,
    );
    const insBox = await screen.findByTestId('simple-signal-accuracy');
    expect(insBox).toHaveTextContent('0/30');
    expect(insBox).toHaveTextContent("Erken ön izleme (1g): son 3 yönlü önerinin %33'i endeksi geçti");
    expect(insBox).toHaveTextContent("Bu hafta: 27 sinyal, %82'si izle");
    expect(screen.getByText(/100\.000 ₺ başlangıçla karşılığı:/)).toBeInTheDocument();
    unmount();

    vi.mocked(alphaApi.getSimpleBrief).mockResolvedValue({
      ...MOCK_BRIEF,
      signal_accuracy: {
        data_status: 'ok',
        n: 30,
        min_sample: 30,
        beat_rate_pct: 53,
        proven_vs_benchmark: false,
        summary_line: "Son 30 al/sat önerisinden %53'i 10 günde endeksten iyi çıktı.",
      },
    });
    const { unmount: unmountUnproven } = render(
      <MemoryRouter>
        <SimpleInvestorHomePage />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('simple-signal-accuracy')).toHaveTextContent('başarısı kanıtlanmadı');
    unmountUnproven();

    vi.mocked(alphaApi.getSimpleBrief).mockResolvedValue({
      ...MOCK_BRIEF,
      signal_accuracy: {
        data_status: 'ok',
        n: 30,
        min_sample: 30,
        beat_rate_pct: 70,
        proven_vs_benchmark: true,
        summary_line: "Son 30 al/sat önerisinden %70'i 10 günde endeksten iyi çıktı.",
      },
    });
    render(
      <MemoryRouter>
        <SimpleInvestorHomePage />
      </MemoryRouter>,
    );
    const okBox = await screen.findByTestId('simple-signal-accuracy');
    expect(okBox).toHaveTextContent(
      "Son 30 al/sat önerisinden %70'i 10 günde endeksten iyi çıktı.",
    );
    expect(okBox).toHaveTextContent('endeksi geçti (%90 GA)');
  });
});
