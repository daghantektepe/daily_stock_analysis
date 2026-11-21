import type React from 'react';
import { useState } from 'react';
import { BookOpenCheck, RefreshCw, Scale, ShieldCheck, Terminal } from 'lucide-react';
import type { QuantPaperBookItem } from '../../api/alpha';
import { Button } from '../common';
import { openCopilotDrawer } from '../chat/copilotEvents';

interface QuantPaperBookCardProps {
  books: QuantPaperBookItem[];
  stepping: boolean;
  onStep: (opts: { forceRebalance?: boolean; forceRefreshPrices?: boolean }) => void;
}

const fmtSigned = (val: number, suffix = '%'): string =>
  `${val >= 0 ? '+' : ''}${val.toFixed(2)}${suffix}`;

export const QuantPaperBookCard: React.FC<QuantPaperBookCardProps> = ({
  books,
  stepping,
  onStep,
}) => {
  const [expandedTradesKey, setExpandedTradesKey] = useState<string | null>(null);

  if (!books || books.length === 0) {
    return null;
  }

  const askCopilotPaperReview = () => {
    openCopilotDrawer(
      'dsa_get_quant_paper_books ve dsa_get_paa_allocation araçlarıyla PAA Çöküş Kalkanı ile Meta-Portföy A günlük sanal portföy defterlerinin güncel NAV, SPY farkı, açık ETF ağırlıkları ve son işlemlerini değerlendir.',
    );
  };

  return (
    <div className="rounded-2xl border border-sky-500/25 bg-sky-500/[0.04] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <BookOpenCheck className="h-4 w-4 text-sky-400" />
            <h3 className="text-xs font-semibold text-foreground">
              Günlük Otomatik Sanal Portföy Defteri (PAA · Meta-Portföy A · 3-AI Konseyi)
            </h3>
            <span className="rounded-md border border-sky-500/35 bg-sky-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-sky-400">
              SADECE SİMÜLASYON
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-secondary-text">
            Her günlük kapanışta SPY kıyaslamalı net NAV güncellenir; ay başı / rejim değişiminde 5 bps maliyetle otomatik yeniden dengelenir (`data/strategy_paper/quant_*.json`).
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            onClick={askCopilotPaperReview}
          >
            <Terminal className="mr-1.5 h-3.5 w-3.5" />
            Defteri Yorumla
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={stepping}
            isLoading={stepping}
            onClick={() => onStep({ forceRebalance: false, forceRefreshPrices: true })}
          >
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            Bugünü İşle
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={stepping}
            onClick={() => onStep({ forceRebalance: true, forceRefreshPrices: true })}
          >
            <Scale className="mr-1.5 h-3.5 w-3.5" />
            Zorla Rebalance
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {books.map((book) => {
          const isTradesOpen = expandedTradesKey === book.strategy_key;
          return (
            <div
              key={book.strategy_key}
              className="rounded-xl border border-border/70 bg-card/85 p-3.5"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
                    <span className="text-xs font-semibold text-foreground">{book.label}</span>
                    {book.council_meta?.engine_label ? (
                      <span className="rounded border border-purple-500/35 bg-purple-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-purple-300">
                        {book.council_meta.rule_engine}
                      </span>
                    ) : null}
                    {book.council_meta?.council_v2 ? (
                      <span
                        data-testid={`council-v2-${book.strategy_key}`}
                        className={`rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                          book.council_meta.council_v2.verdict === 'PASS'
                            ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300'
                            : 'border-rose-500/40 bg-rose-500/15 text-rose-300'
                        }`}
                      >
                        Konsey v2: {book.council_meta.council_v2.verdict === 'PASS' ? 'geçti' : 'kaldı'}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-0.5 font-mono text-[10px] text-secondary-text">
                    {book.start_date || '—'} → {book.last_date || '—'} · {book.days} gün · mod:{' '}
                    {book.rebalance_mode} · {book.cost_bps} bps
                    {book.council_meta?.oos_backtest
                      ? ` · ${
                          book.council_meta.oos_backtest.excess_sharpe !== undefined
                            ? `OOS BIL üstü Sharpe ${Number(book.council_meta.oos_backtest.excess_sharpe).toFixed(2)}`
                            : `OOS Sharpe (Rf=0) ${Number(book.council_meta.oos_backtest.sharpe ?? 0).toFixed(2)}`
                        } · MaxDD ${Number(book.council_meta.oos_backtest.max_drawdown_pct ?? 0).toFixed(1)}%`
                      : ''}
                  </p>
                  {book.council_meta?.council_v2?.checks?.some((check) => !check.ok) ? (
                    <ul className="mt-1 space-y-0.5 text-[10px] leading-snug text-rose-300">
                      {book.council_meta.council_v2.checks
                        .filter((check) => !check.ok)
                        .map((check) => (
                          <li key={check.key}>
                            ✗ {check.label}: {check.value ?? '—'} (hedef {check.target})
                          </li>
                        ))}
                    </ul>
                  ) : null}
                  {book.council_meta?.thesis ? (
                    <p className="mt-1 text-[11px] leading-snug text-secondary-text">
                      {book.council_meta.thesis}
                    </p>
                  ) : null}
                </div>
                <div className="text-right">
                  <div className="font-mono text-sm font-semibold text-foreground">
                    ${book.nav.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <div
                    className={`font-mono text-[11px] font-medium ${
                      book.return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {fmtSigned(book.return_pct)} vs {book.benchmark_symbol} {fmtSigned(book.benchmark_return_pct)}
                  </div>
                </div>
              </div>

              <div className="mt-2.5 grid grid-cols-3 gap-2 rounded-lg border border-border/50 bg-background/40 px-2.5 py-2 font-mono text-[10px]">
                <div>
                  <span className="block text-secondary-text">Fark ({book.benchmark_symbol})</span>
                  <span
                    className={`font-semibold ${
                      book.excess_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {fmtSigned(book.excess_return_pct)}
                  </span>
                </div>
                <div>
                  <span className="block text-secondary-text">MaxDD / İşlem</span>
                  <span className="font-semibold text-foreground">
                    {book.max_drawdown_pct.toFixed(1)}% · {book.trade_count}
                  </span>
                </div>
                <div>
                  <span className="block text-secondary-text">Son Rebalance</span>
                  <span className="font-semibold text-foreground">
                    {book.last_rebalance_date || '—'}
                  </span>
                </div>
              </div>

              {/* Open ETF Positions */}
              <div className="mt-2.5">
                <div className="mb-1 flex items-center justify-between text-[10px] text-secondary-text">
                  <span>Açık ETF Pozisyonları</span>
                  <span className="font-mono">Nakit: %{book.cash_pct.toFixed(1)}</span>
                </div>
                {book.positions.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {book.positions.map((pos) => (
                      <span
                        key={pos.symbol}
                        className="inline-flex items-center gap-1 rounded-lg border border-border/70 bg-background/60 px-2 py-1 font-mono text-[11px] text-foreground"
                      >
                        <strong>{pos.symbol}</strong>
                        <span className="text-emerald-400">%{pos.weight_pct.toFixed(1)}</span>
                        <span className="text-[10px] text-secondary-text">
                          ({pos.shares.toFixed(2)} adet @ ${pos.last_price.toFixed(2)})
                        </span>
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-lg border border-border/50 bg-background/40 px-2.5 py-1.5 text-[11px] text-secondary-text">
                    %100 Nakit (henüz pozisyon açılmadı)
                  </div>
                )}
              </div>

              {/* Recent Simulated Trades Toggle */}
              {book.recent_trades.length > 0 ? (
                <div className="mt-2.5 border-t border-border/50 pt-2">
                  <button
                    type="button"
                    aria-label={`${book.label} son sanal işlemlerini göster`}
                    onClick={() =>
                      setExpandedTradesKey(isTradesOpen ? null : book.strategy_key)
                    }
                    className="text-[11px] font-medium text-primary hover:underline"
                  >
                    {isTradesOpen
                      ? 'Son işlemleri gizle'
                      : `Son sanal işlemleri göster (${book.recent_trades.length})`}
                  </button>
                  {isTradesOpen ? (
                    <div className="mt-2 max-h-40 space-y-1 overflow-y-auto pr-1 font-mono text-[10px]">
                      {book.recent_trades.map((tr, idx) => (
                        <div
                          key={`${tr.date}-${tr.symbol}-${idx}`}
                          className="flex items-center justify-between rounded-md bg-background/50 px-2 py-1"
                        >
                          <span>
                            <span className="text-secondary-text">{tr.date}</span>{' '}
                            <strong
                              className={
                                tr.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'
                              }
                            >
                              {tr.side}
                            </strong>{' '}
                            {tr.symbol} ({tr.shares.toFixed(2)} @ ${tr.price.toFixed(2)})
                          </span>
                          <span className="text-secondary-text">
                            ${tr.notional.toFixed(0)} · %{tr.target_weight_pct.toFixed(1)}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
};
