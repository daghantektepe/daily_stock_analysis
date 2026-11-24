import { expect, test } from '@playwright/test';

const MOCK_BRIEF = {
  ok: true,
  simulated_only: true,
  as_of_date: '2026-11-22',
  usdtry_rate: 50.5,
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
  ],
  profiles: [
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
          midas_hint: 'Midas -> BIL',
        },
        {
          symbol: 'SHY',
          weight_pct: 10,
          plain_name: 'ABD 1-3 Yıllık Tahvil',
          role: 'Kısa tahvil',
          risk_level: 'çok düşük',
          tr_equivalent: 'TEFAS Kısa Vadeli Tahvil Fonu',
          midas_hint: 'Midas -> SHY',
        },
      ],
    },
  ],
  paper_exam: [
    {
      strategy_key: 'meta_a',
      plain_label: 'Dengeli Şampiyon (Meta-A v2)',
      frozen_date: '2026-11-20',
      fingerprint: '37a7ab36a0d9',
      forward_days: 1,
      target_days: 120,
      nav_usd: 10025.42,
      initial_capital_usd: 10000,
      return_pct: 0.16,
      benchmark_return_pct: 4.71,
      status_plain: 'Canlı sınav sürüyor (1/120 işlem günü)',
    },
  ],
  signal_accuracy: {
    data_status: 'insufficient',
    n: 0,
    min_sample: 30,
    summary_line: 'Yapay zekâ önerilerinin başarısı henüz ölçülüyor (0/30)',
    preview_line: "Erken ön izleme (1g): son 3 yönlü önerinin %33'i endeksi geçti (10 günlük ana ölçüm bekleniyor).",
    weekly_watch_line: "Bu hafta: 27 sinyal, %82'si izle",
  },
  disclaimer: 'Yalnızca eğitim ve karar destek amaçlıdır.',
};

test.describe('Phase 6-9 End-to-End Smoke (Mocked API)', () => {
  test.skip(!process.env.DSA_RUN_MOCK_E2E, 'Set DSA_RUN_MOCK_E2E=1 with vite dev/preview running to execute browser E2E.');

  test('navigates Simple Mode -> Guide -> Discover QuantStats Tearsheet & Paper Adapters', async ({ page }) => {
    await page.route('**/api/v1/auth/status', async (route) => {
      await route.fulfill({ json: { authEnabled: false, loggedIn: true } });
    });
    await page.route('**/api/v1/alpha/simple-brief', async (route) => {
      await route.fulfill({ json: MOCK_BRIEF });
    });
    await page.route('**/api/v1/bridges/**', async (route) => {
      const url = route.request().url();
      if (url.includes('/macro-tr')) {
        await route.fulfill({ json: { ok: true, evds_configured: false, usd_try: 50.5, usd_try_source: 'yahoo_try_x_fallback' } });
      } else if (url.includes('/tefas')) {
        await route.fulfill({ json: { ok: true, count: 1, live_count: 1, funds: [{ code: 'PPZ', title: 'Azimut PPF', bucket: 'ppf', global_proxy: 'BIL', price_try: 7.2, daily_return_pct: 0.09, source: 'tefas_live' }] } });
      } else if (url.includes('/adapters')) {
        await route.fulfill({ json: { ok: true, adapters: [{ broker_id: 'alpaca', display_name: 'Alpaca Paper', configured: false, sandbox: true, read_only_enforced: false, mode_label: 'Paper Sanal' }], audit_tail: [] } });
      } else {
        await route.fulfill({ json: { ok: true, bridges: [] } });
      }
    });
    await page.route('**/api/v1/alpha/tearsheet*', async (route) => {
      await route.fulfill({
        json: {
          ok: true,
          strategy_key: 'meta_a',
          label: 'Meta-A v2',
          mode: 'backtest',
          metrics: { cagr_pct: 10.92, excess_sharpe: 0.83, max_drawdown_pct: -8.32, win_months_pct: 66.7, best_month_pct: 6.4, worst_month_pct: -3.1 },
          monthly_matrix: [{ year: 2026, months: { '1': 1.2, '11': 0.8 }, ytd_pct: 4.1 }],
          underwater: [{ date: '2026-01-01', nav_idx: 100, drawdown_pct: 0, benchmark_dd_pct: 0 }],
        },
      });
    });

    await page.goto('/simple');
    await expect(page.getByText('Piyasalar Şu An Fırtınalı — Paranı Güvende Tut')).toBeVisible();
    await expect(page.getByText('90.000 ₺')).toBeVisible();
    await expect(page.getByText(/100\.000 ₺ başlangıçla karşılığı:/)).toBeVisible();
    await expect(page.getByTestId('simple-signal-accuracy')).toContainText('0/30');
    await expect(page.getByTestId('simple-signal-accuracy')).toContainText('Erken ön izleme (1g)');
    await expect(page.getByTestId('simple-signal-accuracy')).toContainText("Bu hafta: 27 sinyal, %82'si izle");

    await page.goto('/guide');
    await expect(page.getByRole('heading', { name: /30 Saniyelik Kartlarla Yatırımı Anla/i })).toBeVisible();

    await page.route('**/api/v1/alpha/tournament*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_strategies: 25,
          total_assets: 42,
          total_asset_days: 120000,
          featured_strategy_ids: ['v3_trp'],
          strategies: [],
        }),
      });
    });
    await page.route('**/api/v1/alpha/paa*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ risk_assets_total: 0, target_weights_pct: {} }),
      });
    });
    await page.route('**/api/v1/alpha/quant-paper*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ books: [] }),
      });
    });
    await page.route('**/api/v1/alpha/research-v4*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          data_start: '2008-01-01',
          data_end: '2026-11-20',
          short_vs_control: {
            long_short: { excess_sharpe_5bps: 0.51, return_2008_pct: 17.4 },
            long_only_control: { excess_sharpe_5bps: 0.68, return_2008_pct: 11.3 },
            short_adds_value: false,
            reasons: [],
          },
        }),
      });
    });
    await page.route('**/api/v1/alpha/research-v5*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          data_start: '2007-01-03',
          data_end: '2026-11-24',
          mincorr_vs_control: {
            mincorr: { excess_sharpe_5bps: 0.61, excess_sharpe_25bps: 0.43, return_2022_pct: 1.2 },
            invvol_control: { excess_sharpe_5bps: 0.61, excess_sharpe_25bps: 0.47, return_2022_pct: 0.1 },
            mincorr_adds_value: false,
            reasons: [],
          },
        }),
      });
    });

    await page.goto('/discover');
    await page.getByRole('button', { name: /Strateji Turnuvası & PAA/i }).click();
    await expect(page.getByText(/QuantStats Görsel Tearsheet/i).first()).toBeVisible();
    await expect(page.getByTestId('research-v4-card')).toContainText('Short testi (ters ETF): değer katmıyor');
    await expect(page.getByTestId('research-v5-card')).toContainText('Korelasyon testi (Min-Corr vs 1/vol): değer katmıyor');
  });
});
