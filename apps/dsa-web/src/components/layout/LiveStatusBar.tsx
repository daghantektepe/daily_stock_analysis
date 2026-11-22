import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { Bell, Compass, Download, Search, ShieldAlert, Sparkles, Terminal, TrendingUp, Zap } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { alphaApi, type AlphaOverviewResponse } from '../../api/alpha';
import { useExperienceMode } from '../../contexts/ExperienceModeContext';
import { OPEN_COMMAND_PALETTE_EVENT } from './commandPaletteEvents';
import { openCopilotDrawer } from '../chat/copilotEvents';

const POLL_INTERVAL_MS = 30000;

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

export const LiveStatusBar: React.FC = () => {
  const { isSimple, setMode } = useExperienceMode();
  const navigate = useNavigate();
  const location = useLocation();
  const [overview, setOverview] = useState<AlphaOverviewResponse | null>(null);
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);

  const handleSelectSimple = () => {
    setMode('simple');
    if (location.pathname !== '/simple') {
      navigate('/simple');
    }
  };

  const handleSelectPro = () => {
    setMode('pro');
    if (location.pathname === '/simple' || location.pathname === '/guide') {
      navigate('/discover');
    }
  };

  useEffect(() => {
    const onBeforeInstall = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as BeforeInstallPromptEvent);
    };
    const onAppInstalled = () => {
      setInstallPrompt(null);
    };
    window.addEventListener('beforeinstallprompt', onBeforeInstall);
    window.addEventListener('appinstalled', onAppInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall);
      window.removeEventListener('appinstalled', onAppInstalled);
    };
  }, []);

  const handleInstallPwa = async () => {
    if (!installPrompt) return;
    try {
      await installPrompt.prompt();
      await installPrompt.userChoice;
    } finally {
      setInstallPrompt(null);
    }
  };

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
        <div
          role="group"
          aria-label="Görünüm modu seçimi"
          className="inline-flex items-center rounded-xl border border-border/70 bg-background/70 p-0.5"
        >
          <button
            type="button"
            onClick={handleSelectSimple}
            aria-pressed={isSimple}
            className={`inline-flex cursor-pointer items-center gap-1 rounded-lg px-2 py-0.5 text-[11px] font-semibold transition-colors ${
              isSimple
                ? 'bg-emerald-500/20 text-emerald-400'
                : 'text-secondary-text hover:text-foreground'
            }`}
          >
            <Sparkles className="h-3 w-3" />
            <span>Basit Mod</span>
          </button>
          <button
            type="button"
            onClick={handleSelectPro}
            aria-pressed={!isSimple}
            className={`inline-flex cursor-pointer items-center gap-1 rounded-lg px-2 py-0.5 text-[11px] font-semibold transition-colors ${
              !isSimple
                ? 'bg-primary/20 text-primary'
                : 'text-secondary-text hover:text-foreground'
            }`}
          >
            <Zap className="h-3 w-3" />
            <span>Uzman</span>
          </button>
        </div>

        {installPrompt ? (
          <button
            type="button"
            onClick={() => void handleInstallPwa()}
            aria-label="Bağımsız tarayıcı uygulaması olarak yükle (PWA)"
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-sky-500/40 bg-sky-500/10 px-2.5 py-1 font-medium text-sky-400 transition-colors hover:bg-sky-500/20"
          >
            <Download className="h-3.5 w-3.5" />
            <span>Uygulama Yükle</span>
          </button>
        ) : null}

        <button
          type="button"
          onClick={() => openCopilotDrawer()}
          className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 font-medium text-emerald-400 transition-colors hover:bg-emerald-500/20"
          aria-label="Claude / Gemini CLI + MCP Copilot Chatbox (Ctrl+J)"
        >
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <Terminal className="h-3.5 w-3.5" />
          <span>AI Copilot</span>
          <kbd className="hidden rounded border border-emerald-500/30 bg-background/60 px-1 py-0.2 font-mono text-[10px] sm:inline">
            Ctrl+J
          </kbd>
        </button>

        {!isSimple ? (
          <>
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
              aria-label="Yalnızca sanal işlem defteri; gerçek emir gönderilmez"
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
                aria-label="Yönetici şifresi kapalı; uzak erişimde ayarlardan aktifleştirin"
              >
                <ShieldAlert className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Auth Kapalı</span>
              </Link>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
};
