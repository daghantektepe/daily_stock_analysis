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
  paper_exam: [],
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

    await page.goto('/discover');
    await page.getByRole('button', { name: /Strateji Turnuvası & PAA/i }).click();
    await expect(page.getByText(/QuantStats Görsel Tearsheet/i).first()).toBeVisible();
  });
});
