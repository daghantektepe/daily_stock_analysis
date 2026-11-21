import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ForwardValidationItem } from '../../../api/alpha';
import { ForwardValidationCard } from '../ForwardValidationCard';

const gate = {
  min_trading_days: 120,
  min_excess_sharpe: 0.5,
  max_drawdown_pct: 18,
  max_slippage_bps: 20,
  max_late_ratio: 0.1,
  min_slippage_fills: 5,
};

const item = (overrides: Partial<ForwardValidationItem>): ForwardValidationItem => ({
  strategy_key: 'meta_a',
  label: 'Meta-Portföy A',
  status: 'COLLECTING',
  frozen_date: '2026-11-20',
  fingerprint: '37a7ab36a0d9',
  forward_days: 30,
  late_days: 0,
  late_ratio: 0,
  forward_return_pct: 1.25,
  benchmark_return_pct: -2.1,
  excess_sharpe: 0.62,
  excess_sharpe_se: 2.9,
  max_drawdown_pct: -2.4,
  backtest_percentile: 64,
  slippage: { fills: 0, avg_bps: null, worst_bps: null },
  gate,
  expectation: { horizon_days: 120, band_pct: { p5: -3.16, p50: 4.93, p95: 16.5 } },
  reasons: ['30/120 ileri işlem günü toplandı.'],
  warnings: [],
  ...overrides,
});

describe('ForwardValidationCard', () => {
  it('renders nothing without items or error', () => {
    const { container } = render(<ForwardValidationCard items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows progress, thresholds, backtest band and reasons for a collecting strategy', () => {
    render(<ForwardValidationCard items={[item({})]} />);
    const card = screen.getByTestId('forward-item-meta_a');
    expect(within(card).getByText('Veri toplanıyor')).toBeInTheDocument();
    expect(within(card).getByText('30 / 120')).toBeInTheDocument();
    expect(within(card).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '25');
    expect(within(card).getByText('0.62 ± 2.9')).toBeInTheDocument();
    expect(within(card).getByText('-3.16% … +16.50% (medyan +4.93%)')).toBeInTheDocument();
    expect(within(card).getByText('• 30/120 ileri işlem günü toplandı.')).toBeInTheDocument();
    expect(within(card).getByLabelText('henüz ölçülmedi')).toBeInTheDocument(); // slippage not measured yet
  });

  it('labels failing, invalidated and pending-slippage states and shows warnings', () => {
    render(
      <ForwardValidationCard
        items={[
          item({ strategy_key: 'paa', label: 'PAA', status: 'FAIL', max_drawdown_pct: -21.3, reasons: ['En büyük düşüş %-21.3, sınır -%18.'] }),
          item({ status: 'INVALIDATED', forward_days: 0, reasons: ['Dondurmadan sonra strateji kod değişti.'] }),
        ]}
      />,
    );
    const paa = screen.getByTestId('forward-item-paa');
    expect(within(paa).getByText('Kapıdan kaldı')).toBeInTheDocument();
    expect(within(paa).getAllByLabelText('eşik karşılanmıyor').length).toBeGreaterThan(0);
    expect(screen.getByText('Geçersiz · strateji değişti')).toBeInTheDocument();
  });

  it('shows the soft API error', () => {
    render(<ForwardValidationCard items={[]} error="İleri doğrulama okunamadı: no prices" />);
    expect(screen.getByText('İleri doğrulama okunamadı: no prices')).toBeInTheDocument();
    expect(screen.getByTestId('forward-validation-card')).toBeInTheDocument();
  });

  it('marks a pending-slippage pass and an overfitting warning', () => {
    render(
      <ForwardValidationCard
        items={[item({ status: 'PASS_PENDING_SLIPPAGE', forward_days: 125, warnings: ['Aşırı uyum belirtisi olabilir.'] })]}
      />,
    );
    expect(screen.getByText('Getiri geçti · kayma ölçülmedi')).toBeInTheDocument();
    expect(screen.getByText('⚠ Aşırı uyum belirtisi olabilir.')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
  });
});
