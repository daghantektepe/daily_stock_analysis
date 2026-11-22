import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import { AlertRuleForm } from '../AlertRuleForm';

const { getAccounts } = vi.hoisted(() => ({
  getAccounts: vi.fn(),
}));

vi.mock('../../../api/portfolio', () => ({
  portfolioApi: {
    getAccounts,
  },
}));

describe('AlertRuleForm', () => {
  const onSubmit = vi.fn();

  beforeEach(() => {
    onSubmit.mockReset();
    onSubmit.mockResolvedValue(undefined);
    getAccounts.mockReset();
    window.localStorage.clear();
    getAccounts.mockResolvedValue({ accounts: [{ id: 9, name: 'Main', market: 'us', baseCurrency: 'USD', isActive: true }] });
  });

  function renderEnglishForm() {
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');
    render(
      <UiLanguageProvider>
        <AlertRuleForm onSubmit={onSubmit} />
      </UiLanguageProvider>,
    );
  }

  it('submits a price_cross rule payload', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Kural adı'), { target: { value: '茅台价格突破' } });
    fireEvent.change(screen.getByLabelText('Sembol'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('Fiyat eşiği'), { target: { value: '1800' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        name: '茅台价格突破',
        targetScope: 'single_symbol',
        target: '600519',
        alertType: 'price_cross',
        parameters: { direction: 'above', price: 1800 },
        severity: 'warning',
        enabled: true,
      });
    });
  });

  it('submits a price_change_percent rule payload', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Sembol'), { target: { value: 'aapl' } });
    fireEvent.change(screen.getByLabelText('Kural tipi'), { target: { value: 'price_change_percent' } });
    fireEvent.change(screen.getByLabelText('Yön'), { target: { value: 'down' } });
    fireEvent.change(screen.getByLabelText('Değişim eşiği (%)'), { target: { value: '3.5' } });
    fireEvent.change(screen.getByLabelText('Önem derecesi'), { target: { value: 'critical' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        target: 'AAPL',
        alertType: 'price_change_percent',
        parameters: { direction: 'down', changePct: 3.5 },
        severity: 'critical',
      }));
    });
  });

  it('submits a volume_spike rule payload and supports disabled creation', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Sembol'), { target: { value: 'msft' } });
    fireEvent.change(screen.getByLabelText('Kural tipi'), { target: { value: 'volume_spike' } });
    fireEvent.change(screen.getByLabelText('Hacim çarpanı'), { target: { value: '2.5' } });
    fireEvent.click(screen.getByLabelText('Oluşturunca hemen etkinleştir'));
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        target: 'MSFT',
        alertType: 'volume_spike',
        parameters: { multiplier: 2.5 },
        enabled: false,
      }));
    });
  });

  it('submits technical indicator rule payloads', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Sembol'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('Kural tipi'), { target: { value: 'macd_cross' } });
    fireEvent.change(screen.getByLabelText('Kesişim yönü'), { target: { value: 'bearish_cross' } });
    fireEvent.change(screen.getByLabelText('Hızlı periyot'), { target: { value: '6' } });
    fireEvent.change(screen.getByLabelText('Yavaş periyot'), { target: { value: '13' } });
    fireEvent.change(screen.getByLabelText('Sinyal periyodu'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        target: '600519',
        alertType: 'macd_cross',
        parameters: {
          direction: 'bearish_cross',
          fastPeriod: 6,
          slowPeriod: 13,
          signalPeriod: 5,
        },
      }));
    });
  });

  it('rejects invalid technical indicator boundaries before submit', () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Sembol'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('Kural tipi'), { target: { value: 'rsi_threshold' } });
    fireEvent.change(screen.getByLabelText('RSI eşiği'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    expect(screen.getByRole('alert')).toHaveTextContent('RSI eşiği 0 ile 100 arasında olmalıdır');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects indicator period combinations that exceed fetchable history', () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Sembol'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('Kural tipi'), { target: { value: 'macd_cross' } });
    fireEvent.change(screen.getByLabelText('Hızlı periyot'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Yavaş periyot'), { target: { value: '250' } });
    fireEvent.change(screen.getByLabelText('Sinyal periyodu'), { target: { value: '250' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    expect(screen.getByRole('alert')).toHaveTextContent('MACD için 501 günlük bar gerekir (en fazla 365)');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects empty required technical indicator thresholds before submit', () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Sembol'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('Kural tipi'), { target: { value: 'rsi_threshold' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    expect(screen.getByRole('alert')).toHaveTextContent('RSI eşiği zorunludur');
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('Kural tipi'), { target: { value: 'cci_threshold' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    expect(screen.getByRole('alert')).toHaveTextContent('CCI eşiği zorunludur');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects invalid numeric thresholds before submit', () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Sembol'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('Fiyat eşiği'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    expect(screen.getByRole('alert')).toHaveTextContent('Fiyat eşiği 0 dan büyük bir sayı olmalıdır');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects invalid stock code format before submit', () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Sembol'), { target: { value: 'aapl-2026' } });
    fireEvent.change(screen.getByLabelText('Fiyat eşiği'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    expect(screen.getByRole('alert')).toHaveTextContent('Geçersiz hisse kodu formatı');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('filters alert types and submits a watchlist rule payload', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Hedef kapsamı'), { target: { value: 'watchlist' } });
    expect(screen.queryByText('Portföy zarar kes')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Fiyat eşiği'), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        targetScope: 'watchlist',
        target: 'default',
        alertType: 'price_cross',
        parameters: { direction: 'above', price: 10 },
      }));
    });
  });

  it('loads accounts and submits portfolio stop-loss mode', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Hedef kapsamı'), { target: { value: 'portfolio_account' } });
    await waitFor(() => expect(getAccounts).toHaveBeenCalledWith(false));
    expect(screen.queryByText('Fiyat kesişimi')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Hesap'), { target: { value: '9' } });
    fireEvent.change(screen.getByLabelText('Zarar kes modu'), { target: { value: 'breach' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        targetScope: 'portfolio_account',
        target: '9',
        alertType: 'portfolio_stop_loss',
        parameters: { mode: 'breach' },
      }));
    });
  });

  it('renders portfolio alert type options in English UI mode', async () => {
    renderEnglishForm();

    fireEvent.change(screen.getByLabelText('Target scope'), { target: { value: 'portfolio_account' } });

    await waitFor(() => expect(getAccounts).toHaveBeenCalledWith(false));
    expect(screen.getByRole('option', { name: 'Portfolio drawdown' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Portfolio stop loss' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Info' })).toBeInTheDocument();
    expect(screen.queryByText('Portföy düşüşü (Drawdown)')).not.toBeInTheDocument();
  });

  it('shows supported market region options in Turkish UI mode', () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Hedef kapsamı'), { target: { value: 'market' } });

    expect(screen.getByRole('option', { name: 'Çin A (cn)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Hong Kong (hk)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'ABD (us)' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /\(jp\)/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /\(kr\)/i })).not.toBeInTheDocument();
  });

  it('submits a market light status rule payload', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Hedef kapsamı'), { target: { value: 'market' } });
    expect(screen.getByRole('option', { name: 'Çin A (cn)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Hong Kong (hk)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'ABD (us)' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Piyasa bölgesi'), { target: { value: 'hk' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        targetScope: 'market',
        target: 'hk',
        alertType: 'market_light_status',
        parameters: { statuses: ['red', 'yellow'] },
      }));
    });
  });

  it('keeps JP/KR out of market light options in English UI mode', () => {
    renderEnglishForm();

    fireEvent.change(screen.getByLabelText('Target scope'), { target: { value: 'market' } });

    expect(screen.getByRole('option', { name: 'A-shares (cn)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Hong Kong (hk)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'US (us)' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Japan (jp)' })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Korea (kr)' })).not.toBeInTheDocument();
  });

  it('submits a market light score-drop rule payload', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Hedef kapsamı'), { target: { value: 'market' } });
    fireEvent.change(screen.getByLabelText('Piyasa bölgesi'), { target: { value: 'us' } });
    fireEvent.change(screen.getByLabelText('Kural tipi'), { target: { value: 'market_light_score_drop' } });
    fireEvent.change(screen.getByLabelText('Skor düşüş eşiği'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        targetScope: 'market',
        target: 'us',
        alertType: 'market_light_score_drop',
        parameters: { minDrop: 12 },
      }));
    });
  });

  it('keeps all account option when account loading fails', async () => {
    getAccounts.mockRejectedValueOnce(new Error('boom'));
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Hedef kapsamı'), { target: { value: 'portfolio_holdings' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
    expect(screen.getByLabelText('Hesap')).toHaveValue('all');
  });

  it('keeps form values when submit reports failure', async () => {
    onSubmit.mockResolvedValueOnce(false);
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Sembol'), { target: { value: 'aapl' } });
    fireEvent.change(screen.getByLabelText('Fiyat eşiği'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kural Oluştur' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(screen.getByLabelText('Sembol')).toHaveValue('aapl');
    expect(screen.getByLabelText('Fiyat eşiği')).toHaveValue(200);
  });
});
