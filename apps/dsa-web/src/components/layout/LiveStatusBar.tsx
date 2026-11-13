import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { Bell, Compass, Search, ShieldAlert, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { alphaApi, type AlphaOverviewResponse } from '../../api/alpha';
import { OPEN_COMMAND_PALETTE_EVENT } from './CommandPalette';

const POLL_INTERVAL_MS = 30000;

export const LiveStatusBar: React.FC = () => {
  const [overview, setOverview] = useState<AlphaOverviewResponse | null>(null);

  const loadOverview = useCallback(async () => {
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
      return;
    }
    try {
      const data = await alphaApi.getOverview();
      setOverview(data);
    } catch {
      // Fail-open: status bar silently stays optional if backend is initializing
    }
  }, []);

  useEffect(() => {
    void loadOverview();
    const timer = window.setInterval(() => {
      void loadOverview();
    }, POLL_INTERVAL_MS);
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        void loadOverview();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [loadOverview]);

  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border/60 bg-card/75 px-3 py-2 shadow-soft-card backdrop-blur-md">
      <button
        type="button"
        onClick={() => window.dispatchEvent(new Event(OPEN_COMMAND_PALETTE_EVENT))}
        className="flex min-w-[210px] flex-1 items-center justify-between gap-2 rounded-xl border border-border/60 bg-background/60 px-3 py-1.5 text-left text-xs text-secondary-text transition-colors hover:border-primary/50 hover:text-foreground sm:max-w-md"
      >
        <span className="flex items-center gap-2 truncate">
          <Search className="h-3.5 w-3.5 shrink-0 text-primary" />
          <span className="truncate">Hızlı arama: Hisse (NVDA, AAPL, THYAO), tarama veya sayfa...</span>
        </span>
        <kbd className="hidden shrink-0 rounded border border-border/70 bg-card px-1.5 py-0.5 font-mono text-[10px] text-secondary-text sm:inline">
          Ctrl+K
        </kbd>
      </button>

      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <Link
          to="/discover"
          className="inline-flex items-center gap-1.5 rounded-xl border border-primary/30 bg-primary/10 px-2.5 py-1 font-medium text-primary transition-colors hover:bg-primary/20"
        >
          <Compass className="h-3.5 w-3.5" />
          <span>Fırsat Bulucu</span>
        </Link>

        <Link
          to="/paper-trading"
          className="inline-flex items-center gap-1.5 rounded-xl border border-border/60 bg-background/60 px-2.5 py-1 font-medium text-foreground transition-colors hover:bg-hover"
          title="Yalnızca sanal işlem defteri; gerçek emir gönderilmez"
        >
          <span
            className={`h-2 w-2 rounded-full ${
              overview?.paper_trading_enabled ? 'bg-emerald-400 animate-pulse' : 'bg-secondary-text/50'
            }`}
          />
          <TrendingUp className="h-3.5 w-3.5 text-secondary-text" />
          <span>
            SANAL DEFTER{overview ? ` · ${overview.open_position_count} Açık` : ''}
          </span>
        </Link>

        {overview && overview.recent_alerts_count > 0 ? (
          <Link
            to="/paper-trading"
            className="inline-flex items-center gap-1 rounded-xl border border-border/60 bg-background/60 px-2.5 py-1 text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
          >
            <Bell className="h-3.5 w-3.5 text-primary" />
            <span>{overview.recent_alerts_count} KAP/Haber</span>
          </Link>
        ) : null}

        {overview && !overview.auth_enabled ? (
          <Link
            to="/settings"
            className="inline-flex items-center gap-1 rounded-xl border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-amber-400 transition-colors hover:bg-amber-500/20"
            title="Yönetici şifresi kapalı; uzak erişimde ayarlardan aktifleştirin"
          >
            <ShieldAlert className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Auth Kapalı</span>
          </Link>
        ) : null}
      </div>
    </div>
  );
};
