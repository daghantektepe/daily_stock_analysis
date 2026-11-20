import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, ShieldCheck, Sparkles, Terminal, Trophy } from 'lucide-react';
import {
  alphaApi,
  type PaaSignalResponse,
  type QuantPaperBookItem,
  type TournamentResponse,
} from '../../api/alpha';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { ApiErrorAlert, Button, SectionCard, StatCard } from '../common';
import { openCopilotDrawer } from '../chat/copilotEvents';
import { QuantPaperBookCard } from './QuantPaperBookCard';
import { StrategyEquityChart } from './StrategyEquityChart';
import { TournamentLeaderboard } from './TournamentLeaderboard';

export const TournamentTabPanel: React.FC = () => {
  const [tournament, setTournament] = useState<TournamentResponse | null>(null);
  const [paa, setPaa] = useState<PaaSignalResponse | null>(null);
  const [paperBooks, setPaperBooks] = useState<QuantPaperBookItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [steppingPaper, setSteppingPaper] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const loadCached = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tData, paaData, paperData] = await Promise.all([
        alphaApi.getTournament(true),
        alphaApi.getPaaSignal(false).catch(() => null),
        alphaApi.getQuantPaperBooks(true).catch(() => null),
      ]);
      setTournament(tData);
      if (paaData) setPaa(paaData);
      if (paperData && Array.isArray(paperData.books)) setPaperBooks(paperData.books);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadCached();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadCached]);

  const handleForceRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [tData, paaData, paperData] = await Promise.all([
        alphaApi.runTournament({ force_refresh: true }),
        alphaApi.getPaaSignal(true).catch(() => null),
        alphaApi.stepQuantPaperBooks({ force_refresh_prices: false }).catch(() => null),
      ]);
      setTournament(tData);
      if (paaData) setPaa(paaData);
      if (paperData && Array.isArray(paperData.books)) setPaperBooks(paperData.books);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setRefreshing(false);
    }
  };

  const handleStepPaper = async (opts: { forceRebalance?: boolean; forceRefreshPrices?: boolean }) => {
    setSteppingPaper(true);
    setError(null);
    try {
      const res = await alphaApi.stepQuantPaperBooks({
        force_rebalance: Boolean(opts.forceRebalance),
        force_refresh_prices: Boolean(opts.forceRefreshPrices),
      });
      if (Array.isArray(res.books)) {
        setPaperBooks(res.books);
      }
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSteppingPaper(false);
    }
  };

  const askCopilotStrategicPlan = () => {
    openCopilotDrawer(
      'dsa_get_strategy_tournament ve dsa_get_paa_allocation MCP araçlarını kullanarak 25 stratejilik turnuva şampiyonlarını (PAA Çöküş Kalkanı, Meta-Portföy A/B) ve canlı piyasa rejimini birlikte yorumla; bugün için en güvenli sermaye dağılımını çıkar.',
    );
  };

  return (
    <div className="space-y-4">
      {error ? <ApiErrorAlert error={error} /> : null}

      <SectionCard
        title="25 Stratejili Çoklu Evren Ampirik Turnuvası & PAA Çöküş Kalkanı"
        subtitle="Örneklem dışı (2022 → bugün) sıfır lookahead, çift yönlü işlem maliyeti düşülmüş net performans ve Bailey–López de Prado DSR (N=25)"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={askCopilotStrategicPlan}
            >
              <Terminal className="mr-1.5 h-3.5 w-3.5" />
              Copilot ile Yorumla
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={loading || refreshing}
              isLoading={refreshing}
              onClick={() => void handleForceRefresh()}
            >
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              Canlı Veriyle Yenile
            </Button>
          </div>
        }
      >
        {loading && !tournament ? (
          <div className="py-10 text-center text-xs text-secondary-text">
            25 strateji turnuva verisi yükleniyor...
          </div>
        ) : tournament && tournament.strategies.length > 0 ? (
          <div className="space-y-4">
            {/* Top KPI Cards */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="Turnuva Kapsamı"
                value={`${tournament.total_strategies} Strateji`}
                hint={`${tournament.total_assets} varlık · ${tournament.total_asset_days.toLocaleString('tr-TR')} varlık-gün`}
                icon={<Trophy className="h-4 w-4 text-primary" />}
              />
              <StatCard
                label="PAA Çöküş Kalkanı"
                value={tournament.paa ? `${tournament.paa.oos.cagr_pct >= 0 ? '+' : ''}${tournament.paa.oos.cagr_pct.toFixed(1)}%` : '--'}
                hint={
                  tournament.paa
                    ? `Sharpe ${tournament.paa.oos.sharpe.toFixed(2)} · MaxDD ${tournament.paa.oos.max_drawdown_pct.toFixed(1)}%`
                    : ''
                }
                icon={<ShieldCheck className="h-4 w-4 text-emerald-400" />}
                tone="success"
              />
              <StatCard
                label="Meta-Portföy B (ETF+Kripto)"
                value={
                  tournament.meta_portfolio_b
                    ? `${tournament.meta_portfolio_b.oos.cagr_pct >= 0 ? '+' : ''}${tournament.meta_portfolio_b.oos.cagr_pct.toFixed(1)}%`
                    : '--'
                }
                hint={
                  tournament.meta_portfolio_b
                    ? `Sharpe ${tournament.meta_portfolio_b.oos.sharpe.toFixed(2)} · MaxDD ${tournament.meta_portfolio_b.oos.max_drawdown_pct.toFixed(1)}%`
                    : ''
                }
                icon={<Sparkles className="h-4 w-4 text-sky-400" />}
                tone="primary"
              />
              <StatCard
                label="Genel OOS Şampiyon"
                value={tournament.champion ? `Sharpe ${tournament.champion.oos.sharpe.toFixed(2)}` : '--'}
                hint={tournament.champion?.name || ''}
                icon={<Trophy className="h-4 w-4 text-amber-400" />}
                tone="warning"
              />
            </div>

            {/* Live PAA Crash-Shield Breadth Strip */}
            {paa && paa.risk_assets_total > 0 ? (
              <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4 text-emerald-400" />
                      <span className="text-xs font-semibold text-foreground">
                        Canlı PAA Çöküş Kalkanı ({paa.as_of_date})
                      </span>
                      <span className="rounded-md border border-emerald-500/40 bg-emerald-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-400">
                        {paa.regime_label}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-secondary-text">
                      12 riskli ETF&apos;den <strong>{paa.risk_assets_below_sma252}</strong> tanesi 252G ortalamasının altında → Koruma oranı: <strong>%{paa.crash_protection_pct}</strong>
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(paa.target_weights_pct).map(([sym, pct]) => (
                      <span
                        key={sym}
                        className="rounded-lg border border-border/70 bg-card/90 px-2.5 py-1 font-mono text-xs font-semibold text-foreground"
                      >
                        {sym} %{pct}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}

            {/* Daily Automated PAA & Meta-Portfolio A StrategyPaperBook */}
            <QuantPaperBookCard
              books={paperBooks}
              stepping={steppingPaper}
              onStep={(opts) => void handleStepPaper(opts)}
            />

            {/* OOS Equity / Drawdown Comparison Chart */}
            <StrategyEquityChart
              strategies={tournament.strategies}
              featuredIds={tournament.featured_strategy_ids}
            />

            {/* Full 25-Strategy Sortable Leaderboard */}
            <TournamentLeaderboard strategies={tournament.strategies} />
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-secondary-text">
            Turnuva henüz çalıştırılmadı. Sağ üstteki &ldquo;Canlı Veriyle Yenile&rdquo; butonuna tıklayın.
          </div>
        )}
      </SectionCard>
    </div>
  );
};
