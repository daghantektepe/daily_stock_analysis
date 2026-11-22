import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { BarChart3 } from 'lucide-react';
import { alphaApi, type QuantTearsheetResponse } from '../../api/alpha';
import { Badge, SectionCard } from '../common';

const MONTHS_TR = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];

const STRATEGY_OPTS = [
  { key: 'meta_a', label: 'Meta-Portföy A v2' },
  { key: 'v3_trp', label: 'v3 Risk Paritesi (19Y)' },
  { key: 'paa', label: 'PAA Çöküş Kalkanı' },
];

const heatCellClass = (val: number | null | undefined): string => {
  if (val == null || Number.isNaN(val)) return 'bg-background/30 text-secondary-text';
  if (val >= 5) return 'bg-emerald-500/30 text-emerald-200 border-emerald-500/40';
  if (val >= 1.5) return 'bg-emerald-500/18 text-emerald-300 border-emerald-500/25';
  if (val > 0) return 'bg-emerald-500/10 text-emerald-300';
  if (val <= -5) return 'bg-rose-500/30 text-rose-200 border-rose-500/40';
  if (val <= -1.5) return 'bg-rose-500/18 text-rose-300 border-rose-500/25';
  if (val < 0) return 'bg-rose-500/10 text-rose-300';
  return 'bg-background/40 text-secondary-text';
};

const fmtSigned = (v: number | null | undefined, digits = 2): string => {
  if (v == null || !Number.isFinite(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`;
};

export const QuantTearsheetCard: React.FC = () => {
  const [strategy, setStrategy] = useState<string>('meta_a');
  const [mode, setMode] = useState<'backtest' | 'paper'>('backtest');
  const [data, setData] = useState<QuantTearsheetResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const loadTearsheet = useCallback(async (strat: string, srcMode: 'backtest' | 'paper') => {
    setLoading(true);
    try {
      const res = await alphaApi.getQuantTearsheet(strat, srcMode);
      setData(res);
    } catch {
      // fail-open if tearsheet cache not ready
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadTearsheet(strategy, mode);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadTearsheet, strategy, mode]);

  const m = data?.metrics ?? {};
  const cc = data?.currency_comparison;

  return (
    <SectionCard
      title="QuantStats Görsel Tearsheet (Aylık Isı Haritası & Düşüş Grafiği)"
      subtitle="Gerçek örneklem + 2008–2026 takvim tutarlılığı · Düşüş (Underwater) eğrisi ve TL vs USD vs TÜFE karşılaştırması"
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Tearsheet Stratejisi"
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="rounded-lg border border-border/70 bg-card px-2.5 py-1 text-xs text-foreground"
          >
            {STRATEGY_OPTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
          <select
            aria-label="Tearsheet Kaynak Modu"
            value={mode}
            onChange={(e) => setMode(e.target.value as 'backtest' | 'paper')}
            className="rounded-lg border border-border/70 bg-card px-2.5 py-1 text-xs text-foreground"
          >
            <option value="backtest">Tam Tarihsel Test</option>
            <option value="paper">Canlı Sanal Kasa</option>
          </select>
        </div>
      }
    >
      {loading && !data ? (
        <div className="py-6 text-center text-xs text-secondary-text">QuantStats görsel raporu hesaplanıyor...</div>
      ) : data ? (
        <div className="space-y-4">
          {/* Top KPI Summary Strip */}
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6 text-xs">
            <div className="rounded-xl border border-border/50 bg-background/40 p-2.5">
              <div className="text-[11px] text-secondary-text">Yıllık Getiri (CAGR)</div>
              <div className="mt-0.5 font-mono text-sm font-bold text-foreground">
                {fmtSigned(m.cagr_pct as number | undefined)}
              </div>
            </div>
            <div className="rounded-xl border border-border/50 bg-background/40 p-2.5">
              <div className="text-[11px] text-secondary-text">BIL Üstü Sharpe</div>
              <div className="mt-0.5 font-mono text-sm font-bold text-emerald-400">
                {typeof m.excess_sharpe === 'number' ? m.excess_sharpe.toFixed(2) : '—'}
              </div>
            </div>
            <div className="rounded-xl border border-border/50 bg-background/40 p-2.5">
              <div className="text-[11px] text-secondary-text">En Kötü Düşüş (MaxDD)</div>
              <div className="mt-0.5 font-mono text-sm font-bold text-rose-400">
                {fmtSigned(m.max_drawdown_pct as number | undefined)}
              </div>
            </div>
            <div className="rounded-xl border border-border/50 bg-background/40 p-2.5">
              <div className="text-[11px] text-secondary-text">Kârlı Aylar Oranı</div>
              <div className="mt-0.5 font-mono text-sm font-bold text-foreground">
                {typeof m.win_months_pct === 'number' ? `%${m.win_months_pct.toFixed(1)}` : '—'}
              </div>
            </div>
            <div className="rounded-xl border border-border/50 bg-background/40 p-2.5">
              <div className="text-[11px] text-secondary-text">En İyi Ay</div>
              <div className="mt-0.5 font-mono text-sm font-bold text-emerald-400">
                {fmtSigned(m.best_month_pct as number | undefined)}
              </div>
            </div>
            <div className="rounded-xl border border-border/50 bg-background/40 p-2.5">
              <div className="text-[11px] text-secondary-text">En Kötü Ay</div>
              <div className="mt-0.5 font-mono text-sm font-bold text-rose-400">
                {fmtSigned(m.worst_month_pct as number | undefined)}
              </div>
            </div>
          </div>

          {/* TL vs USD vs TÜFE 1Y Check */}
          {cc ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-sky-500/30 bg-sky-500/5 px-3 py-2 text-xs">
              <div className="flex items-center gap-2 font-medium text-foreground">
                <BarChart3 className="h-4 w-4 text-sky-400" />
                <span>Son 1 Yıl Kur & Alım Gücü Özeti:</span>
              </div>
              <div className="flex flex-wrap items-center gap-3 font-mono text-[11px]">
                <span>USD Getiri: <strong>{fmtSigned(cc.usd_1y_return_pct)}</strong></span>
                <span>TL Karşılığı: <strong>{fmtSigned(cc.try_equivalent_1y_return_pct)}</strong></span>
                {cc.cpi_yoy_pct != null ? (
                  <Badge variant={(cc.real_tufe_1y_return_pct ?? 0) >= 0 ? 'success' : 'warning'}>
                    TÜFE Reel: {fmtSigned(cc.real_tufe_1y_return_pct)}
                  </Badge>
                ) : (
                  <span className="text-secondary-text">TÜFE için EVDS_API_KEY isteğe bağlı</span>
                )}
              </div>
            </div>
          ) : null}

          {/* Underwater Drawdown Chart */}
          {(data.underwater ?? []).length > 1 ? (
            <div>
              <p className="mb-1.5 text-xs font-semibold text-foreground">
                Düşüş (Underwater Drawdown %) — Strateji vs S&P 500 (SPY)
              </p>
              <div className="h-44 w-full rounded-xl border border-border/50 bg-background/40 p-2">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data.underwater} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.12)" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94a3b8' }} minTickGap={36} />
                    <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={(v: number) => `${v}%`} width={44} />
                    <ReferenceLine y={0} stroke="rgba(148,163,184,0.35)" />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0f172a', borderRadius: '8px', fontSize: '11px' }}
                      formatter={(val, name) => [`${Number(val).toFixed(2)}%`, String(name)]}
                    />
                    <Area
                      type="monotone"
                      dataKey="drawdown_pct"
                      name="Strateji Düşüşü"
                      stroke="#10b981"
                      fill="#10b981"
                      fillOpacity={0.22}
                      strokeWidth={1.8}
                    />
                    <Line
                      type="monotone"
                      dataKey="benchmark_dd_pct"
                      name="SPY Düşüşü"
                      stroke="#f43f5e"
                      dot={false}
                      strokeWidth={1.2}
                      strokeDasharray="4 2"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : null}

          {/* Monthly Returns Calendar Heatmap */}
          {(data.monthly_matrix ?? []).length > 0 ? (
            <div className="overflow-x-auto">
              <p className="mb-1.5 text-xs font-semibold text-foreground">Aylık Getiri Isı Haritası (%)</p>
              <table className="w-full border-collapse text-center font-mono text-[11px]">
                <thead>
                  <tr className="border-b border-border/60 text-secondary-text">
                    <th className="py-1 pr-2 text-left">Yıl</th>
                    {MONTHS_TR.map((mo) => (
                      <th key={mo} className="px-1 py-1">{mo}</th>
                    ))}
                    <th className="py-1 pl-2 text-right">Yıllık</th>
                  </tr>
                </thead>
                <tbody>
                  {data.monthly_matrix.slice(0, 12).map((row) => (
                    <tr key={row.year} className="border-b border-border/30">
                      <td className="py-1 pr-2 text-left font-bold text-foreground">{row.year}</td>
                      {MONTHS_TR.map((_, idx) => {
                        const val = row.months?.[String(idx + 1)];
                        return (
                          <td key={idx} className="p-0.5">
                            <span
                              className={`block rounded border border-transparent px-1 py-0.5 ${heatCellClass(val)}`}
                            >
                              {val != null ? `${val >= 0 ? '+' : ''}${val.toFixed(1)}` : '—'}
                            </span>
                          </td>
                        );
                      })}
                      <td
                        className={`py-1 pl-2 text-right font-bold ${
                          (row.ytd_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        {row.ytd_pct != null ? `${row.ytd_pct >= 0 ? '+' : ''}${row.ytd_pct.toFixed(1)}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </SectionCard>
  );
};
