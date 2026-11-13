import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  BarChart3,
  Bell,
  BriefcaseBusiness,
  Compass,
  Gauge,
  Home,
  MessageSquareQuote,
  Search,
  Settings2,
  Sparkles,
  TrendingUp,
  X,
} from 'lucide-react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useStockIndex } from '../../hooks/useStockIndex';
import type { Market, StockSuggestion } from '../../types/stockIndex';
import { searchStocks } from '../../utils/searchStocks';
import { cn } from '../../utils/cn';

export const OPEN_COMMAND_PALETTE_EVENT = 'dsa:open-command-palette';

export function openCommandPalette() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(OPEN_COMMAND_PALETTE_EVENT));
  }
}

type MarketFilter = 'ALL' | 'US' | 'TR' | 'HK' | 'CN';

type QuickActionItem = {
  id: string;
  label: string;
  description: string;
  to: string;
  keywords: string;
  icon: React.ComponentType<{ className?: string }>;
};

const QUICK_ROUTES: QuickActionItem[] = [
  {
    id: 'route-discover',
    label: 'Fırsat Bulucu (ABD Yüksek Alfa + PEAD + Form 4 + BIST)',
    description: 'Çok faktörlü taramalar, canlı Form 4 küme alımları ve bilanço sürprizleri',
    to: '/discover',
    keywords: 'discover tarama abd us bist form4 pead quant kap',
    icon: Compass,
  },
  {
    id: 'route-home',
    label: 'Ana Kokpit ve Hisse Analizi',
    description: 'Tekil hisse analizi başlat ve son AI karar raporlarını incele',
    to: '/',
    keywords: 'home ana sayfa analiz kokpit',
    icon: Home,
  },
  {
    id: 'route-paper',
    label: 'Sanal İşlem, BIST/SPY Kıyasları ve KAP Akışı',
    description: 'ATR zarar kes/kâr al takibi, sanal P&L ve çok kaynaklı haber uyarıları',
    to: '/paper-trading',
    keywords: 'paper trading sanal işlem kap kıyas benchmark',
    icon: TrendingUp,
  },
  {
    id: 'route-signals',
    label: 'AI Karar Sinyalleri',
    description: 'Üretilen AL/SAT sinyalleri ve sonuç kalibrasyonu',
    to: '/decision-signals',
    keywords: 'signals sinyaller karar ai',
    icon: Activity,
  },
  {
    id: 'route-portfolio',
    label: 'Portföy ve Risk Analizi',
    description: 'Gerçek portföy dağılımı, sektör yoğunluğu ve nakit defteri',
    to: '/portfolio',
    keywords: 'portfolio portföy risk sektör',
    icon: BriefcaseBusiness,
  },
  {
    id: 'route-backtest',
    label: 'Strateji Geriye Dönük Testi (Backtest)',
    description: 'Geçmiş AI tahminlerinin doğruluk ve getiri doğrulaması',
    to: '/backtest',
    keywords: 'backtest doğrulama geçmiş test',
    icon: BarChart3,
  },
  {
    id: 'route-alerts',
    label: 'Fiyat ve Teknik Uyarı Kuralları',
    description: 'Fiyat, RSI, MACD ve portföy alarm kuralları',
    to: '/alerts',
    keywords: 'alerts uyarı alarm bildirim',
    icon: Bell,
  },
  {
    id: 'route-chat',
    label: 'AI Hisse Sohbet Asistanı',
    description: 'Doğal dilde hisse ve strateji soruları sor',
    to: '/chat',
    keywords: 'chat sohbet ask ai',
    icon: MessageSquareQuote,
  },
  {
    id: 'route-usage',
    label: 'API ve Token Kullanımı',
    description: 'LLM model çağrıları ve kota takibi',
    to: '/usage',
    keywords: 'usage token kota api',
    icon: Gauge,
  },
  {
    id: 'route-settings',
    label: 'Sistem Ayarları ve Güvenlik',
    description: 'API anahtarları, Telegram bildirimleri, yetki koruması ve tarayıcılar',
    to: '/settings',
    keywords: 'settings ayarlar config güvenlik auth telegram',
    icon: Settings2,
  },
];

const MARKET_PILLS: Array<{ id: MarketFilter; label: string }> = [
  { id: 'ALL', label: 'Tümü' },
  { id: 'US', label: 'ABD (US)' },
  { id: 'TR', label: 'BIST (TR)' },
  { id: 'HK', label: 'HK' },
  { id: 'CN', label: 'CN' },
];

export const CommandPalette: React.FC = () => {
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [market, setMarket] = useState<MarketFilter>('ALL');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Lazy load stock index only after user opens the command palette
  const { index, loading } = useStockIndex(isOpen);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setIsOpen((prev) => !prev);
      } else if (event.key === 'Escape' && isOpen) {
        event.preventDefault();
        setIsOpen(false);
      }
    };
    const onCustomOpen = () => setIsOpen(true);

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener(OPEN_COMMAND_PALETTE_EVENT, onCustomOpen);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener(OPEN_COMMAND_PALETTE_EVENT, onCustomOpen);
    };
  }, [isOpen]);

  useEffect(() => {
    if (isOpen) {
      setActiveIndex(0);
      window.setTimeout(() => inputRef.current?.focus(), 20);
    } else {
      setQuery('');
    }
  }, [isOpen]);

  const filteredRoutes = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return QUICK_ROUTES.slice(0, 6);
    return QUICK_ROUTES.filter(
      (item) =>
        item.label.toLowerCase().includes(q)
        || item.description.toLowerCase().includes(q)
        || item.keywords.toLowerCase().includes(q)
    );
  }, [query]);

  const stockMatches: StockSuggestion[] = useMemo(() => {
    const q = query.trim();
    if (!q || index.length === 0) return [];
    const pool = market === 'ALL' ? index : index.filter((item) => item.market === (market as Market));
    return searchStocks(q, pool, { limit: 8 });
  }, [index, market, query]);

  const manualSymbol = useMemo(() => {
    const q = query.trim().toUpperCase();
    if (!q || q.includes(' ') || q.length > 16) return '';
    if (!/^[A-Z0-9._-]+$/.test(q)) return '';
    if (market === 'TR' && !q.endsWith('.IS')) return `${q}.IS`;
    return q;
  }, [market, query]);

  type PaletteEntry =
    | { kind: 'stock'; key: string; code: string; title: string; subtitle: string; market: string }
    | { kind: 'manual'; key: string; code: string; title: string; subtitle: string }
    | { kind: 'route'; key: string; route: QuickActionItem };

  const entries: PaletteEntry[] = useMemo(() => {
    const list: PaletteEntry[] = [];
    for (const s of stockMatches) {
      list.push({
        kind: 'stock',
        key: `stock-${s.canonicalCode}`,
        code: s.canonicalCode,
        title: s.canonicalCode,
        subtitle: s.nameZh && s.nameZh !== s.canonicalCode ? s.nameZh : `${s.market} hissesi`,
        market: s.market,
      });
    }
    if (manualSymbol && !stockMatches.some((s) => s.canonicalCode.toUpperCase() === manualSymbol)) {
      list.push({
        kind: 'manual',
        key: `manual-${manualSymbol}`,
        code: manualSymbol,
        title: `${manualSymbol} kodunu doğrudan analiz et`,
        subtitle: 'Kokpite git ve AI analizini başlat',
      });
    }
    for (const r of filteredRoutes) {
      list.push({
        kind: 'route',
        key: r.id,
        route: r,
      });
    }
    return list;
  }, [filteredRoutes, manualSymbol, stockMatches]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query, market]);

  const executeEntry = useCallback(
    (entry: PaletteEntry) => {
      setIsOpen(false);
      if (entry.kind === 'stock' || entry.kind === 'manual') {
        navigate('/', {
          state: {
            stockCode: entry.code,
            stockName: entry.kind === 'stock' ? entry.subtitle : '',
            autoAnalyze: true,
            selectionSource: 'autocomplete',
          },
        });
      } else {
        navigate(entry.route.to);
      }
    },
    [navigate]
  );

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (entries.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % entries.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((prev) => (prev - 1 + entries.length) % entries.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const target = entries[activeIndex] ?? entries[0];
      if (target) executeEntry(target);
    }
  };

  if (!isOpen) return null;

  const modal = (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-black/60 px-3 pt-[10vh] backdrop-blur-sm"
      onClick={() => setIsOpen(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Hızlı Arama ve Komut Paleti"
        className="w-full max-w-2xl overflow-hidden rounded-2xl border border-border/80 bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-border/60 px-4 py-3">
          <Search className="h-5 w-5 shrink-0 text-primary" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleInputKeyDown}
            placeholder="Hisse kodu / şirket adı yazın (örn. NVDA, AAPL, THYAO) veya sayfa arayın..."
            className="w-full bg-transparent text-sm text-foreground placeholder:text-muted-text focus:outline-none"
          />
          <button
            type="button"
            onClick={() => setIsOpen(false)}
            className="rounded-lg p-1 text-secondary-text hover:bg-hover hover:text-foreground"
            aria-label="Kapat"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 bg-background/40 px-4 py-2 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            {MARKET_PILLS.map((pill) => (
              <button
                key={pill.id}
                type="button"
                onClick={() => setMarket(pill.id)}
                className={cn(
                  'rounded-lg px-2.5 py-1 font-medium transition-colors',
                  market === pill.id
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-card/80 text-secondary-text hover:bg-hover hover:text-foreground'
                )}
              >
                {pill.label}
              </button>
            ))}
          </div>
          {loading ? <span className="text-[11px] text-secondary-text">Hisse indeksi yükleniyor...</span> : null}
        </div>

        <div className="max-h-[55vh] overflow-y-auto p-2">
          {entries.length === 0 ? (
            <div className="px-4 py-8 text-center text-xs text-secondary-text">
              Eşleşen hisse veya komut bulunamadı.
            </div>
          ) : (
            <div className="space-y-1">
              {entries.map((entry, idx) => {
                const active = idx === activeIndex;
                if (entry.kind === 'stock' || entry.kind === 'manual') {
                  return (
                    <button
                      key={entry.key}
                      type="button"
                      onMouseEnter={() => setActiveIndex(idx)}
                      onClick={() => executeEntry(entry)}
                      className={cn(
                        'flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left transition-colors',
                        active ? 'bg-primary/15 text-foreground' : 'hover:bg-hover/60'
                      )}
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
                          <Sparkles className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold text-foreground">{entry.title}</div>
                          <div className="truncate text-xs text-secondary-text">{entry.subtitle}</div>
                        </div>
                      </div>
                      <span className="shrink-0 rounded-md border border-border/60 bg-background/70 px-2 py-0.5 text-[11px] font-medium text-primary">
                        {entry.kind === 'stock' ? `${entry.market} · Analiz Et` : 'Analiz Et'}
                      </span>
                    </button>
                  );
                }

                const Icon = entry.route.icon;
                return (
                  <button
                    key={entry.key}
                    type="button"
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() => executeEntry(entry)}
                    className={cn(
                      'flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left transition-colors',
                      active ? 'bg-primary/15 text-foreground' : 'hover:bg-hover/60'
                    )}
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-background/60 text-secondary-text">
                        <Icon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-foreground">{entry.route.label}</div>
                        <div className="truncate text-xs text-secondary-text">{entry.route.description}</div>
                      </div>
                    </div>
                    <span className="shrink-0 text-[11px] text-secondary-text">Git →</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-border/50 bg-background/40 px-4 py-2 text-[11px] text-secondary-text">
          <span>↑↓ Gezin · Enter Seç · Esc Kapat</span>
          <span>ABD · BIST · HK · CN</span>
        </div>
      </div>
    </div>
  );

  return typeof document !== 'undefined' ? createPortal(modal, document.body) : modal;
};
