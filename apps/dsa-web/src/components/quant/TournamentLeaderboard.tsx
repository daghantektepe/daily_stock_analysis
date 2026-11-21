import type React from 'react';
import { useMemo, useState } from 'react';
import { ArrowUpDown, Terminal } from 'lucide-react';
import type { TournamentStrategyRow } from '../../api/alpha';
import { cn } from '../../utils/cn';
import { openCopilotDrawer } from '../chat/copilotEvents';

interface TournamentLeaderboardProps {
  strategies: TournamentStrategyRow[];
}

type SortKey = 'sharpe' | 'cagr' | 'maxdd' | 'dsr' | 'recovery';

const VERDICT_STYLES: Record<string, string> = {
  PASS_ELITE: 'border-emerald-500/40 bg-emerald-500/15 text-emerald-400',
  PASS_SOLID: 'border-sky-500/40 bg-sky-500/15 text-sky-400',
  BENCHMARK: 'border-slate-400/40 bg-slate-500/15 text-slate-300',
  CAVEAT_SURVIVORSHIP: 'border-amber-500/40 bg-amber-500/15 text-amber-400',
  FAIL_WEAK: 'border-rose-500/40 bg-rose-500/15 text-rose-400',
};

const UNIVERSE_LABELS: Record<string, string> = {
  all: 'Tümü',
  us_etf: 'ABD ETF',
  meta: 'Meta-Portföy',
  us_sectors: 'ABD Sektör/Faktör',
  crypto: 'Kripto',
  bist: 'BIST (USD bazlı)',
};

interface HurdleView {
  cagr: number;
  sharpe: number;
  maxdd: number;
  recovery: number;
  /** TL CAGR shown under the USD one for BIST rows. */
  tlCagr?: number;
}

/**
 * Metrics on the same footing as the verdicts: Sharpe over BIL for USD strategies,
 * USDTRY-adjusted dollar metrics over BIL for BIST. Rf=0 Sharpe flatters strategies
 * that sit in T-bills, so it is never used for ranking.
 */
const hurdleView = (row: TournamentStrategyRow): HurdleView => {
  if (row.usd) {
    return {
      cagr: row.usd.cagr_pct,
      sharpe: row.usd.excess_sharpe ?? row.usd.sharpe,
      maxdd: row.usd.max_drawdown_pct,
      recovery: row.usd.recovery_factor,
      tlCagr: row.oos.cagr_pct,
    };
  }
  return {
    cagr: row.oos.cagr_pct,
    sharpe: row.currency === 'USD' ? (row.oos.excess_sharpe ?? row.oos.sharpe) : row.oos.sharpe,
    maxdd: row.oos.max_drawdown_pct,
    recovery: row.oos.recovery_factor,
  };
};

const fmtSigned = (value: number, digits = 1): string => `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`;

export const TournamentLeaderboard: React.FC<TournamentLeaderboardProps> = ({ strategies }) => {
  const [universeFilter, setUniverseFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<SortKey>('sharpe');

  const universes = useMemo(() => {
    const found = new Set(strategies.map((s) => s.universe));
    return ['all', ...['us_etf', 'meta', 'us_sectors', 'crypto', 'bist'].filter((u) => found.has(u))];
  }, [strategies]);

  const filtered = useMemo(() => {
    const base =
      universeFilter === 'all'
        ? strategies
        : strategies.filter((s) => s.universe === universeFilter);
    return [...base].sort((a, b) => {
      const va = hurdleView(a);
      const vb = hurdleView(b);
      if (sortBy === 'cagr') return vb.cagr - va.cagr;
      if (sortBy === 'maxdd') return vb.maxdd - va.maxdd;
      if (sortBy === 'dsr') return b.oos.dsr_pct - a.oos.dsr_pct;
      if (sortBy === 'recovery') return vb.recovery - va.recovery;
      return vb.sharpe - va.sharpe;
    });
  }, [sortBy, strategies, universeFilter]);

  const askCopilot = (row: TournamentStrategyRow) => {
    openCopilotDrawer(
      `Turnuva stratejisi "${row.name}" (${row.strategy_id}, karar: ${row.verdict}, OOS CAGR ${hurdleView(row).cagr}%${row.usd ? ' (USD)' : ''}, BIL üstü Sharpe ${hurdleView(row).sharpe}, MaxDD ${hurdleView(row).maxdd}%, güncel hedef: ${row.signal_summary}) bugünkü canlı piyasa rejimine göre uygulanmalı mı? Risklerini ve alternatifini analiz et.`,
    );
  };

  return (
    <div className="space-y-3 rounded-2xl border border-border/60 bg-card/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {universes.map((u) => (
            <button
              key={u}
              type="button"
              onClick={() => setUniverseFilter(u)}
              className={cn(
                'rounded-xl px-2.5 py-1 text-xs font-medium transition-colors',
                universeFilter === u
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border/60 bg-background/60 text-secondary-text hover:bg-hover hover:text-foreground',
              )}
            >
              {UNIVERSE_LABELS[u] ?? u}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1.5 text-xs text-secondary-text">
          <ArrowUpDown className="h-3.5 w-3.5" />
          <span>Sırala:</span>
          {(
            [
              ['sharpe', 'BIL üstü Sharpe'],
              ['cagr', 'CAGR'],
              ['maxdd', 'En Az Düşüş'],
              ['dsr', 'DSR'],
              ['recovery', 'Recovery'],
            ] as Array<[SortKey, string]>
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setSortBy(key)}
              className={cn(
                'rounded-lg px-2 py-0.5 text-[11px] font-medium transition-colors',
                sortBy === key
                  ? 'bg-primary/20 text-primary'
                  : 'text-secondary-text hover:text-foreground',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-border/60 text-[11px] uppercase tracking-wider text-secondary-text">
              <th className="py-2 pr-3">Strateji</th>
              <th className="px-2 py-2 text-center">Evren</th>
              <th className="px-2 py-2 text-center">Karar</th>
              <th className="px-2 py-2 text-right">OOS CAGR</th>
              <th className="px-2 py-2 text-right">BIL üstü Sharpe</th>
              <th className="px-2 py-2 text-right">MaxDD</th>
              <th className="px-2 py-2 text-right">Recovery</th>
              <th className="px-2 py-2 text-right">DSR</th>
              <th className="px-2 py-2">Güncel Sinyal</th>
              <th className="py-2 pl-2 text-right">Copilot</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {filtered.map((row) => {
              const view = hurdleView(row);
              return (
              <tr key={row.strategy_id} className="transition-colors hover:bg-hover/40">
                <td className="py-2.5 pr-3">
                  <div className="font-semibold text-foreground">{row.name}</div>
                  <div className="mt-0.5 line-clamp-1 text-[11px] text-secondary-text">
                    {row.description}
                  </div>
                </td>
                <td className="px-2 py-2.5 text-center">
                  <span className="rounded-md border border-border/60 bg-background/60 px-1.5 py-0.5 font-mono text-[10px] text-secondary-text">
                    {row.universe}
                  </span>
                </td>
                <td className="px-2 py-2.5 text-center">
                  <span
                    className={cn(
                      'inline-block rounded-md border px-1.5 py-0.5 font-mono text-[10px] font-semibold',
                      VERDICT_STYLES[row.verdict] ?? 'border-border/60 text-secondary-text',
                    )}
                  >
                    {row.verdict}
                  </span>
                </td>
                <td
                  className={cn(
                    'px-2 py-2.5 text-right font-mono font-semibold',
                    view.cagr >= 0 ? 'text-emerald-400' : 'text-rose-400',
                  )}
                >
                  {fmtSigned(view.cagr)}%{row.usd ? ' USD' : ''}
                  {view.tlCagr !== undefined ? (
                    <div className="text-[10px] font-normal text-secondary-text">TL {fmtSigned(view.tlCagr)}%</div>
                  ) : null}
                </td>
                <td className="px-2 py-2.5 text-right font-mono text-foreground">
                  {fmtSigned(view.sharpe, 2)}
                </td>
                <td className="px-2 py-2.5 text-right font-mono text-rose-400">
                  {view.maxdd.toFixed(1)}%
                </td>
                <td className="px-2 py-2.5 text-right font-mono text-foreground">
                  {view.recovery.toFixed(2)}x
                </td>
                <td className="px-2 py-2.5 text-right font-mono text-secondary-text">
                  %{row.oos.dsr_pct.toFixed(1)}
                </td>
                <td className="max-w-[200px] px-2 py-2.5">
                  <span className="line-clamp-2 text-[11px] text-foreground/90">
                    {row.signal_summary}
                  </span>
                </td>
                <td className="py-2.5 pl-2 text-right">
                  <button
                    type="button"
                    onClick={() => askCopilot(row)}
                    aria-label={`${row.name} stratejisini Copilot'a sor`}
                    className="inline-flex items-center gap-1 rounded-lg border border-primary/40 bg-primary/10 px-2 py-1 text-[11px] font-medium text-primary transition-colors hover:bg-primary/20"
                  >
                    <Terminal className="h-3 w-3" />
                    <span>Sor</span>
                  </button>
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
