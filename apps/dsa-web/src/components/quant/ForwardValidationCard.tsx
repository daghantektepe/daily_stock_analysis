import type React from 'react';
import { FlaskConical, Lock, Terminal } from 'lucide-react';
import type { ForwardValidationItem, ForwardValidationStatus } from '../../api/alpha';
import { Button } from '../common';
import { PlainTermTooltip } from '../common/PlainTermTooltip';
import { openCopilotDrawer } from '../chat/copilotEvents';

interface ForwardValidationCardProps {
  items: ForwardValidationItem[];
  error?: string | null;
}

const STATUS_META: Record<ForwardValidationStatus, { label: string; className: string }> = {
  NOT_FROZEN: { label: 'Dondurulmadı', className: 'border-border/70 bg-background/60 text-secondary-text' },
  COLLECTING: { label: 'Veri toplanıyor', className: 'border-sky-500/40 bg-sky-500/15 text-sky-300' },
  PASS: { label: 'Kapıyı geçti', className: 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300' },
  PASS_PENDING_SLIPPAGE: {
    label: 'Getiri geçti · kayma ölçülmedi',
    className: 'border-amber-500/40 bg-amber-500/15 text-amber-300',
  },
  FAIL: { label: 'Kapıdan kaldı', className: 'border-rose-500/40 bg-rose-500/15 text-rose-300' },
  INVALIDATED: {
    label: 'Geçersiz · strateji değişti',
    className: 'border-orange-500/40 bg-orange-500/15 text-orange-300',
  },
};

const DEFAULT_GATE = {
  min_trading_days: 120,
  min_excess_sharpe: 0.5,
  max_drawdown_pct: 18,
  max_slippage_bps: 20,
  max_late_ratio: 0.1,
  min_slippage_fills: 5,
};

const fmtPct = (value?: number | null): string =>
  value === null || value === undefined ? '—' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;

const fmtNum = (value?: number | null, digits = 2): string =>
  value === null || value === undefined ? '—' : value.toFixed(digits);

interface CheckRowProps {
  label: string;
  value: string;
  target: string;
  ok: boolean | null;
  glossaryTerm?: string;
}

const CheckRow: React.FC<CheckRowProps> = ({ label, value, target, ok, glossaryTerm }) => (
  <div className="flex items-center justify-between gap-2 rounded-md border border-border/50 bg-background/40 px-2.5 py-1.5">
    <span className="inline-flex min-w-0 items-center gap-1 text-secondary-text">
      <span>{label}</span>
      {glossaryTerm ? <PlainTermTooltip termKey={glossaryTerm} /> : null}
    </span>
    <span className="flex shrink-0 items-center gap-1.5 whitespace-nowrap">
      <span className="font-semibold text-foreground">{value}</span>
      <span className="text-secondary-text">/ {target}</span>
      <span
        aria-label={ok === null ? 'henüz ölçülmedi' : ok ? 'eşik karşılanıyor' : 'eşik karşılanmıyor'}
        className={`inline-block h-2 w-2 rounded-full ${
          ok === null ? 'bg-secondary-text/40' : ok ? 'bg-emerald-400' : 'bg-rose-400'
        }`}
      />
    </span>
  </div>
);

const ForwardItem: React.FC<{ item: ForwardValidationItem }> = ({ item }) => {
  const gate = { ...DEFAULT_GATE, ...item.gate };
  const meta = STATUS_META[item.status] ?? STATUS_META.NOT_FROZEN;
  const progress = Math.min(100, Math.round((item.forward_days / gate.min_trading_days) * 100));
  const hasData = item.forward_days > 0;
  const band = item.expectation?.band_pct ?? {};
  const slipFills = item.slippage?.fills ?? 0;
  const slipAvg = item.slippage?.avg_bps;

  return (
    <div className="rounded-xl border border-border/70 bg-card/85 p-3.5" data-testid={`forward-item-${item.strategy_key ?? 'unknown'}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <span className="text-xs font-semibold text-foreground">{item.label || item.strategy_key}</span>
          <p className="mt-0.5 font-mono text-[10px] text-secondary-text">
            {item.frozen_date ? `Dondurma: ${item.frozen_date} · parmak izi ${item.fingerprint ?? '—'}` : 'Henüz dondurulmadı'}
          </p>
        </div>
        <span className={`rounded-md border px-2 py-0.5 font-mono text-[10px] font-semibold ${meta.className}`}>
          {meta.label}
        </span>
      </div>

      <div className="mt-3">
        <div className="mb-1 flex justify-between font-mono text-[10px] text-secondary-text">
          <span>İleri işlem günü</span>
          <span>
            {item.forward_days} / {gate.min_trading_days}
          </span>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-background/70"
          role="progressbar"
          aria-label="İleri doğrulama ilerlemesi"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
        >
          <div className="h-full rounded-full bg-sky-400" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-1.5 font-mono text-[10px] sm:grid-cols-2">
        <CheckRow
          label="BIL üstü Sharpe"
          glossaryTerm="ex_bil_sharpe"
          value={hasData ? `${fmtNum(item.excess_sharpe)} ± ${fmtNum(item.excess_sharpe_se, 1)}` : '—'}
          target={`≥ ${gate.min_excess_sharpe.toFixed(2)}`}
          ok={hasData && item.excess_sharpe !== null && item.excess_sharpe !== undefined
            ? item.excess_sharpe >= gate.min_excess_sharpe
            : null}
        />
        <CheckRow
          label="En büyük düşüş"
          glossaryTerm="max_dd"
          value={hasData ? fmtPct(item.max_drawdown_pct) : '—'}
          target={`-%${gate.max_drawdown_pct.toFixed(0)}`}
          ok={hasData && item.max_drawdown_pct !== null && item.max_drawdown_pct !== undefined
            ? item.max_drawdown_pct >= -gate.max_drawdown_pct
            : null}
        />
        <CheckRow
          label="Kayma (Alpaca)"
          glossaryTerm="slippage"
          value={slipAvg !== null && slipAvg !== undefined ? `${slipAvg.toFixed(1)} bps · ${slipFills} dolum` : `${slipFills} dolum`}
          target={`≤ ${gate.max_slippage_bps} bps`}
          ok={slipFills >= gate.min_slippage_fills && slipAvg !== null && slipAvg !== undefined
            ? slipAvg <= gate.max_slippage_bps
            : null}
        />
        <CheckRow
          label="Sonradan işlenen gün"
          value={hasData ? `${item.late_days}` : '—'}
          target={`≤ %${Math.round(gate.max_late_ratio * 100)}`}
          ok={hasData ? item.late_ratio <= gate.max_late_ratio : null}
        />
      </div>

      <div className="mt-2.5 grid grid-cols-2 gap-2 rounded-lg border border-border/50 bg-background/40 px-2.5 py-2 font-mono text-[10px]">
        <div>
          <span className="block text-secondary-text">İleri getiri / SPY</span>
          <span className="font-semibold text-foreground">
            {hasData ? `${fmtPct(item.forward_return_pct)} / ${fmtPct(item.benchmark_return_pct)}` : '—'}
          </span>
        </div>
        <div>
          <span className="block text-secondary-text">
            Backtest bandı ({item.expectation?.horizon_days ?? gate.min_trading_days} gün)
          </span>
          <span className="font-semibold text-foreground">
            {band.p5 !== undefined && band.p95 !== undefined
              ? `${fmtPct(band.p5)} … ${fmtPct(band.p95)} (medyan ${fmtPct(band.p50)})`
              : '—'}
          </span>
          {item.backtest_percentile !== null && item.backtest_percentile !== undefined ? (
            <span className="block text-secondary-text">
              ileri sonuç geçmiş dönemlerin %{item.backtest_percentile.toFixed(0)}&apos;inden iyi
            </span>
          ) : null}
        </div>
      </div>

      {(item.reasons ?? []).length > 0 || (item.warnings ?? []).length > 0 ? (
        <ul className="mt-2.5 space-y-1 text-[11px] leading-snug">
          {(item.reasons ?? []).map((reason) => (
            <li key={reason} className="text-secondary-text">
              • {reason}
            </li>
          ))}
          {(item.warnings ?? []).map((warning) => (
            <li key={warning} className="text-amber-300">
              ⚠ {warning}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};

export const ForwardValidationCard: React.FC<ForwardValidationCardProps> = ({ items, error }) => {
  if (!error && (!items || items.length === 0)) {
    return null;
  }

  const askCopilot = () => {
    openCopilotDrawer(
      'dsa_get_forward_validation aracıyla PAA ve Meta-Portföy A ileri doğrulama kapısının durumunu yorumla: kaç gün toplandı, BIL üstü Sharpe ve hata payı, en büyük düşüş, backtest bandına göre konum ve gerçek paraya geçmeden önce eksik kalanlar.',
    );
  };

  return (
    <div className="rounded-2xl border border-violet-500/25 bg-violet-500/[0.04] p-4" data-testid="forward-validation-card">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4 text-violet-400" />
            <h3 className="text-xs font-semibold text-foreground">İleri Doğrulama Kapısı (dondurulmuş strateji)</h3>
          </div>
          <p className="mt-0.5 text-[11px] text-secondary-text">
            Yalnızca dondurmadan sonraki günler sayılır; strateji kodu ya da ayarları değişirse kayıt geçersiz olur.
            Gerçek paraya geçiş için tüm eşiklerin karşılanması gerekir.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={askCopilot}>
          <Terminal className="mr-1.5 h-3.5 w-3.5" />
          Kapıyı Yorumla
        </Button>
      </div>

      {error ? (
        <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-300">{error}</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {items.map((item) => (
            <ForwardItem key={item.strategy_key ?? item.label ?? 'item'} item={item} />
          ))}
        </div>
      )}

      <p className="mt-3 flex items-center gap-1.5 text-[10px] text-secondary-text">
        <Lock className="h-3 w-3" />
        Kapı geçilmeden ALPACA_PAPER=true ve ALPACA_AUTO_EXECUTE=false kalır. 120 günlük Sharpe tahmininin hata payı ±1,4
        civarındadır; kapıyı geçmek kanıtın başlangıcıdır, garantisi değil.
      </p>
    </div>
  );
};
