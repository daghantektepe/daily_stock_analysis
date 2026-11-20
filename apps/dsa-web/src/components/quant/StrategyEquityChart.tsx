import type React from 'react';
import { useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TournamentStrategyRow } from '../../api/alpha';
import { cn } from '../../utils/cn';

interface StrategyEquityChartProps {
  strategies: TournamentStrategyRow[];
  featuredIds?: string[];
}

const LINE_PALETTE = [
  '#10b981', // emerald (PAA / Champion)
  '#38bdf8', // sky (Meta A)
  '#a78bfa', // violet (Meta B)
  '#f59e0b', // amber (Crypto 5-SMA)
  '#94a3b8', // slate (SPY Benchmark)
  '#64748b', // muted slate (60/40)
  '#fb7185', // rose (Crypto Buy & Hold)
];

const SHORT_NAMES: Record<string, string> = {
  PROTECTIVE_ASSET_ALLOCATION_PAA: 'PAA Çöküş Kalkanı',
  META_US_ETF_ALL_WEATHER: 'Meta-Portföy A (ETF)',
  META_GLOBAL_ETF_CRYPTO_TREND: 'Meta-Portföy B (ETF+Kripto)',
  CRYPTO_5SMA_ENSEMBLE: 'Kripto 5-SMA',
  BENCHMARK_SPY_BUY_HOLD: 'SPY Al-Tut',
  BENCHMARK_60_40: 'Klasik 60/40',
  BENCHMARK_CRYPTO_BUY_HOLD: 'Kripto Al-Tut',
};

export const StrategyEquityChart: React.FC<StrategyEquityChartProps> = ({
  strategies,
  featuredIds,
}) => {
  const [mode, setMode] = useState<'equity' | 'drawdown'>('equity');

  const curveStrategies = useMemo(() => {
    const withCurves = strategies.filter(
      (row) => Array.isArray(row.equity_oos_points) && row.equity_oos_points.length > 2,
    );
    if (featuredIds && featuredIds.length > 0) {
      const orderMap = new Map(featuredIds.map((id, idx) => [id, idx]));
      return [...withCurves].sort(
        (a, b) => (orderMap.get(a.strategy_id) ?? 99) - (orderMap.get(b.strategy_id) ?? 99),
      );
    }
    return withCurves.slice(0, 7);
  }, [featuredIds, strategies]);

  const [hiddenIds, setHiddenIds] = useState<Record<string, boolean>>({});

  const chartData = useMemo(() => {
    const dateMap = new Map<string, Record<string, string | number>>();
    for (const row of curveStrategies) {
      if (hiddenIds[row.strategy_id]) continue;
      for (const pt of row.equity_oos_points || []) {
        let entry = dateMap.get(pt.date);
        if (!entry) {
          entry = { date: pt.date };
          dateMap.set(pt.date, entry);
        }
        entry[row.strategy_id] = mode === 'equity' ? pt.equity : pt.drawdown_pct;
      }
    }
    return [...dateMap.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)));
  }, [curveStrategies, hiddenIds, mode]);

  if (curveStrategies.length === 0) {
    return null;
  }

  const toggleSeries = (id: string) => {
    setHiddenIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="space-y-3 rounded-2xl border border-border/60 bg-card/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-foreground">
            Örneklem Dışı (OOS) Kümülatif Performans & Çöküş Karşılaştırması
          </h3>
          <p className="text-xs text-secondary-text">
            {mode === 'equity'
              ? '100 başlangıç değerli, işlem maliyetleri düşülmüş net büyüme eğrileri (sıfır lookahead)'
              : 'Zirveden düşüş (Underwater Drawdown %) — çöküş kalkanının sermayeyi koruma gücü'}
          </p>
        </div>
        <div className="inline-flex rounded-xl border border-border/60 bg-background/60 p-0.5 text-xs">
          <button
            type="button"
            onClick={() => setMode('equity')}
            className={cn(
              'rounded-lg px-2.5 py-1 font-medium transition-colors',
              mode === 'equity'
                ? 'bg-primary text-primary-foreground'
                : 'text-secondary-text hover:text-foreground',
            )}
          >
            Büyüme (100)
          </button>
          <button
            type="button"
            onClick={() => setMode('drawdown')}
            className={cn(
              'rounded-lg px-2.5 py-1 font-medium transition-colors',
              mode === 'drawdown'
                ? 'bg-primary text-primary-foreground'
                : 'text-secondary-text hover:text-foreground',
            )}
          >
            Drawdown (%)
          </button>
        </div>
      </div>

      {/* Series Toggle Pills */}
      <div className="flex flex-wrap gap-1.5">
        {curveStrategies.map((row, idx) => {
          const color = LINE_PALETTE[idx % LINE_PALETTE.length];
          const hidden = Boolean(hiddenIds[row.strategy_id]);
          const label = SHORT_NAMES[row.strategy_id] ?? row.name;
          return (
            <button
              key={row.strategy_id}
              type="button"
              onClick={() => toggleSeries(row.strategy_id)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px] font-medium transition-all',
                hidden
                  ? 'border-border/40 bg-background/30 text-secondary-text/50 line-through'
                  : 'border-border/70 bg-background/70 text-foreground hover:border-primary/40',
              )}
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: hidden ? '#64748b' : color }}
              />
              <span>{label}</span>
              <span className="font-mono text-[10px] text-secondary-text">
                {row.oos.cagr_pct >= 0 ? `+${row.oos.cagr_pct.toFixed(1)}%` : `${row.oos.cagr_pct.toFixed(1)}%`}
              </span>
            </button>
          );
        })}
      </div>

      <div className="h-[320px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.16)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: '#94a3b8' }}
              minTickGap={36}
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#94a3b8' }}
              tickFormatter={(v) => (mode === 'equity' ? `${v}` : `${v}%`)}
              width={52}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'rgba(15, 23, 42, 0.94)',
                borderColor: 'rgba(148, 163, 184, 0.3)',
                borderRadius: '12px',
                fontSize: '12px',
              }}
              formatter={(value: unknown, name: unknown) => {
                const num = typeof value === 'number' ? value : Number(value);
                const id = String(name || '');
                const label = SHORT_NAMES[id] ?? id;
                const formatted = Number.isFinite(num)
                  ? mode === 'equity'
                    ? `${num.toFixed(1)}`
                    : `${num.toFixed(1)}%`
                  : '--';
                return [formatted, label];
              }}
            />
            {mode === 'equity' ? (
              <ReferenceLine y={100} stroke="rgba(148,163,184,0.4)" strokeDasharray="4 4" />
            ) : (
              <ReferenceLine y={0} stroke="rgba(148,163,184,0.4)" />
            )}
            {curveStrategies.map((row, idx) => {
              if (hiddenIds[row.strategy_id]) return null;
              const color = LINE_PALETTE[idx % LINE_PALETTE.length];
              return (
                <Line
                  key={row.strategy_id}
                  type="monotone"
                  dataKey={row.strategy_id}
                  name={row.strategy_id}
                  stroke={color}
                  strokeWidth={row.is_benchmark ? 1.5 : 2.2}
                  strokeDasharray={row.is_benchmark ? '5 4' : undefined}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
