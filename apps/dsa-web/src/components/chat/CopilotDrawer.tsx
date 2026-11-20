import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Compass,
  Loader2,
  Maximize2,
  RotateCcw,
  Send,
  ShieldCheck,
  Sparkles,
  Square,
  Terminal,
  Wrench,
  X,
} from 'lucide-react';
import { cn } from '../../utils/cn';
import { useAgentChatStore, type ProgressStep } from '../../stores/agentChatStore';
import { BackendSwitcher } from './BackendSwitcher';
import { OPEN_COPILOT_EVENT } from './copilotEvents';

const ROUTE_LABELS: Record<string, string> = {
  '/': 'Ana Kokpit',
  '/discover': 'Fırsat Bulucu (Alpha & Quant)',
  '/paper-trading': 'Sanal İşlem Defteri & KAP',
  '/portfolio': 'Portföy & Risk',
  '/decision-signals': 'AI Karar Sinyalleri',
  '/screening': 'Hisse Tarama',
  '/backtest': 'Backtest Doğrulama',
  '/alerts': 'Uyarı Kuralları',
  '/chat': 'Tam Ekran Chat',
  '/settings': 'Ayarlar',
};

const STRATEGIC_PROMPTS: Array<{
  id: string;
  tag: string;
  title: string;
  prompt: string;
}> = [
  {
    id: 'safest-strategic',
    tag: 'Stratejik Öneri',
    title: 'En güvenli yüksek olasılıklı trading önerisi',
    prompt:
      'Para kazandırma ihtimali yüksek, şu an piyasa rejimine göre en güvenli stratejik trading önerini istiyorum. Canlı piyasa rejimini (SPY/VIX), Kripto 5-SMA trendini, sanal portföy durumunu ve canlı ABD/BIST tarama fırsatlarını MCP araçlarıyla kontrol edip nakit oranı, pozisyon dağılımı ve stop-loss seviyeleriyle somut bir aksiyon planı çıkar.',
  },
  {
    id: 'risk-crypto-paper',
    tag: 'Rejim & Kripto',
    title: 'Piyasa rejimi + Kripto 5-SMA + Sanal portföy özeti',
    prompt:
      'Canlı piyasa rejimini (SPY SMA50/200 & VIX), Kripto 5-SMA Trend (BTC-USD / ETH-USD) güncel sinyallerini ve sanal portföyümdeki açık pozisyonların risk durumunu MCP üzerinden kontrol edip özetle.',
  },
  {
    id: 'us-alpha-form4-pead',
    tag: 'ABD Alfa',
    title: 'ABD Yüksek Alfa + SEC Form 4 + PEAD taraması',
    prompt:
      'ABD Yüksek Alfa çok faktörlü taramasını, canlı SEC Form 4 yönetici alımlarını ve PEAD bilanço sürprizi adaylarını MCP ile tara; risk/ödül açısından en güçlü 3 adayı gerekçeleriyle sırala.',
  },
  {
    id: 'bist-kap',
    tag: 'BIST & KAP',
    title: 'BIST teknik kırılım ve KAP ihale fırsatları',
    prompt:
      'BIST hisse tarayıcısını ve son 7 günlük KAP ihale/sözleşme bildirimlerini MCP üzerinden çalıştır; hacim ve katalizör destekli en güçlü BIST adaylarını listele.',
  },
];

const ToolStepsTimeline: React.FC<{
  steps: ProgressStep[];
  live?: boolean;
}> = ({ steps, live = false }) => {
  const [expanded, setExpanded] = useState(live);

  if (steps.length === 0) return null;

  const toolSteps = steps.filter(
    (s) => s.type === 'tool_start' || s.type === 'tool_done' || s.type === 'thinking' || s.type === 'generating',
  );
  if (toolSteps.length === 0) return null;

  // Pair tool_start and tool_done into compact rows
  const toolRows: Array<{
    key: string;
    label: string;
    tool?: string;
    state: 'running' | 'done' | 'error' | 'info';
    duration?: number;
  }> = [];

  for (let i = 0; i < toolSteps.length; i += 1) {
    const step = toolSteps[i];
    if (step.type === 'tool_start') {
      const label = step.display_name || step.tool || 'MCP Aracı';
      toolRows.push({
        key: `tool-${step.tool || i}-${i}`,
        label,
        tool: step.tool,
        state: 'running',
      });
    } else if (step.type === 'tool_done') {
      const label = step.display_name || step.tool || 'MCP Aracı';
      const existing = [...toolRows].reverse().find((r) => r.tool === step.tool && r.state === 'running');
      if (existing) {
        existing.state = step.success === false ? 'error' : 'done';
        existing.duration = step.duration;
      } else {
        toolRows.push({
          key: `tool-done-${step.tool || i}-${i}`,
          label,
          tool: step.tool,
          state: step.success === false ? 'error' : 'done',
          duration: step.duration,
        });
      }
    } else if (live && (step.type === 'thinking' || step.type === 'generating') && step.message) {
      toolRows.push({
        key: `info-${i}`,
        label: step.message,
        state: 'info',
      });
    }
  }

  const completedToolCount = toolRows.filter((r) => r.state === 'done' || r.state === 'error').length;

  return (
    <div className="mb-2 rounded-xl border border-border/60 bg-background/60 text-xs">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-secondary-text transition-colors hover:text-foreground"
      >
        <span className="flex items-center gap-1.5 font-medium">
          {live ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
          ) : (
            <Wrench className="h-3.5 w-3.5 text-primary" />
          )}
          <span>
            {live
              ? 'Canlı MCP Araç Akışı'
              : `Kullanılan DSA MCP Araçları (${completedToolCount || toolRows.length})`}
          </span>
        </span>
        {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
      </button>

      {expanded ? (
        <div className="space-y-1 border-t border-border/50 px-3 py-2">
          {toolRows.map((row) => (
            <div key={row.key} className="flex items-center justify-between gap-2 text-[11px]">
              <span className="flex min-w-0 items-center gap-1.5">
                {row.state === 'running' ? (
                  <Loader2 className="h-3 w-3 shrink-0 animate-spin text-primary" />
                ) : row.state === 'done' ? (
                  <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-400" />
                ) : row.state === 'error' ? (
                  <AlertCircle className="h-3 w-3 shrink-0 text-rose-400" />
                ) : (
                  <Sparkles className="h-3 w-3 shrink-0 text-primary/80" />
                )}
                <span className="truncate text-foreground/90">{row.label}</span>
              </span>
              {row.duration !== undefined ? (
                <span className="shrink-0 font-mono text-[10px] text-secondary-text">
                  {row.duration.toFixed(1)}s
                </span>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
};

export const CopilotDrawer: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const copilotOpen = useAgentChatStore((s) => s.copilotOpen) ?? false;
  const copilotPrefill = useAgentChatStore((s) => s.copilotPrefill) ?? null;
  const messages = useAgentChatStore((s) => s.messages) ?? [];
  const loading = useAgentChatStore((s) => s.loading) ?? false;
  const stopping = useAgentChatStore((s) => s.stopping) ?? false;
  const progressSteps = useAgentChatStore((s) => s.progressSteps) ?? [];
  const chatError = useAgentChatStore((s) => s.chatError) ?? null;
  const terminalStatus = useAgentChatStore((s) => s.terminalStatus) ?? null;
  const completionBadge = useAgentChatStore((s) => s.completionBadge) ?? false;
  const selectedBackend = useAgentChatStore((s) => s.selectedBackend) ?? null;
  const backends = useAgentChatStore((s) => s.backends);
  const sessionId = useAgentChatStore((s) => s.sessionId) ?? '';

  const openCopilot = useAgentChatStore((s) => s.openCopilot);
  const closeCopilot = useAgentChatStore((s) => s.closeCopilot);
  const toggleCopilot = useAgentChatStore((s) => s.toggleCopilot);
  const consumeCopilotPrefill = useAgentChatStore((s) => s.consumeCopilotPrefill);
  const loadBackends = useAgentChatStore((s) => s.loadBackends);
  const loadInitialSession = useAgentChatStore((s) => s.loadInitialSession);
  const startNewChat = useAgentChatStore((s) => s.startNewChat);
  const startStream = useAgentChatStore((s) => s.startStream);
  const stopStream = useAgentChatStore((s) => s.stopStream);

  const [input, setInput] = useState('');
  const [showTemplates, setShowTemplates] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const activeBackendMeta = useMemo(() => {
    const safeBackends = Array.isArray(backends) ? backends : [];
    return safeBackends.find((b) => b.id === selectedBackend) ?? safeBackends.find((b) => b.available) ?? null;
  }, [backends, selectedBackend]);
  const pageLabel = ROUTE_LABELS[location.pathname] ?? location.pathname;

  // Load CLI backends and session metadata on mount
  useEffect(() => {
    if (typeof loadBackends === 'function') {
      void loadBackends();
    }
    if (typeof loadInitialSession === 'function') {
      void loadInitialSession();
    }
  }, [loadBackends, loadInitialSession]);

  // Global keyboard shortcut Ctrl+J / Cmd+J and custom event listener
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        toggleCopilot?.();
      } else if (e.key === 'Escape' && useAgentChatStore.getState()?.copilotOpen) {
        closeCopilot?.();
      }
    };
    const onOpenEvent = (e: Event) => {
      const custom = e as CustomEvent<{ prefill?: string }>;
      openCopilot?.(custom.detail?.prefill);
    };
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener(OPEN_COPILOT_EVENT, onOpenEvent);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener(OPEN_COPILOT_EVENT, onOpenEvent);
    };
  }, [closeCopilot, openCopilot, toggleCopilot]);

  // Focus composer and apply any prefill text when drawer opens
  useEffect(() => {
    if (!copilotOpen) return;
    const timer = window.setTimeout(() => {
      if (copilotPrefill) {
        const consumed = consumeCopilotPrefill();
        if (consumed) {
          setInput(consumed);
        }
      }
      inputRef.current?.focus();
    }, 30);
    return () => window.clearTimeout(timer);
  }, [copilotOpen, copilotPrefill, consumeCopilotPrefill]);

  // Auto-scroll to bottom on new messages or progress steps
  useEffect(() => {
    if (!copilotOpen || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [copilotOpen, messages.length, progressSteps.length, loading]);

  const handleSend = useCallback(
    async (overridePrompt?: string) => {
      const text = (overridePrompt ?? input).trim();
      if (!text || loading) return;
      if (!overridePrompt) {
        setInput('');
      }
      setShowTemplates(false);
      await startStream(
        {
          message: text,
          session_id: sessionId,
          backend: selectedBackend ?? undefined,
          context: {
            page_route: location.pathname,
            page_label: pageLabel,
          },
        },
        {
          skillName: activeBackendMeta?.label || 'DSA Copilot',
        },
      );
    },
    [activeBackendMeta?.label, input, loading, location.pathname, pageLabel, selectedBackend, sessionId, startStream],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  // Floating launcher when drawer is closed (hidden on full /chat page)
  const launcher = !copilotOpen && location.pathname !== '/chat' ? (
    <button
      type="button"
      onClick={() => openCopilot()}
      className="fixed bottom-5 right-5 z-50 inline-flex items-center gap-2 rounded-2xl border border-primary/40 bg-card/92 px-3.5 py-2.5 text-xs font-semibold text-foreground shadow-xl backdrop-blur-xl transition-all hover:scale-[1.02] hover:border-primary hover:bg-card"
      aria-label="DSA AI Copilot aç"
    >
      <span className="relative flex h-2.5 w-2.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" />
      </span>
      <Terminal className="h-4 w-4 text-primary" />
      <span>{activeBackendMeta?.mcpEnabled ? activeBackendMeta.label : 'AI Copilot'}</span>
      <kbd className="hidden rounded border border-border/70 bg-background/80 px-1.5 py-0.5 font-mono text-[10px] text-secondary-text sm:inline">
        Ctrl+J
      </kbd>
      {completionBadge ? (
        <span className="ml-0.5 h-2 w-2 rounded-full bg-primary" aria-label="Yeni yanıt" />
      ) : null}
    </button>
  ) : null;

  const drawerContent = copilotOpen ? (
    <div className="fixed inset-0 z-[75] flex justify-end" role="presentation">
      <div
        className="absolute inset-0 bg-background/55 backdrop-blur-[2px]"
        onClick={closeCopilot}
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label="DSA CLI-Native Copilot"
        className="relative flex h-full w-full flex-col border-l border-border/80 bg-card/95 shadow-2xl backdrop-blur-xl sm:w-[560px]"
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-primary/30 bg-primary/15 text-primary">
              <Terminal className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="truncate text-sm font-semibold text-foreground">DSA Copilot</h2>
                <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[10px] font-medium text-emerald-400">
                  MCP · dsa
                </span>
              </div>
              <p className="truncate text-[11px] text-secondary-text">
                Claude / Gemini CLI ile canlı quant araçlarına doğrudan bağlı
              </p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={() => startNewChat?.()}
              aria-label="Yeni sohbet başlat"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border/60 bg-background/60 text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => {
                closeCopilot?.();
                navigate('/chat');
              }}
              aria-label="Tam ekran Chat sayfasına geç"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border/60 bg-background/60 text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => closeCopilot?.()}
              aria-label="Copilot panelini kapat"
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border/60 bg-background/60 text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Engine Switcher & Active Page Context */}
        <div className="space-y-2 border-b border-border/50 bg-background/40 px-4 py-2.5">
          <BackendSwitcher compact />
          <div className="flex items-center justify-between gap-2 text-[11px] text-secondary-text">
            <span className="inline-flex items-center gap-1.5 truncate">
              <Compass className="h-3 w-3 shrink-0 text-primary" />
              <span className="truncate">Aktif sayfa bağlamı: {pageLabel}</span>
            </span>
            <button
              type="button"
              onClick={() => setShowTemplates((v) => !v)}
              className="shrink-0 font-medium text-primary hover:underline"
            >
              {showTemplates ? 'Şablonları gizle' : 'Hazır strateji soruları'}
            </button>
          </div>
        </div>

        {/* Optional collapsible prompt templates bar */}
        {showTemplates ? (
          <div className="grid grid-cols-1 gap-1.5 border-b border-border/50 bg-background/50 p-3">
            {STRATEGIC_PROMPTS.map((item) => (
              <button
                key={item.id}
                type="button"
                disabled={loading}
                onClick={() => void handleSend(item.prompt)}
                className="flex items-start justify-between gap-2 rounded-xl border border-border/60 bg-card/80 px-3 py-2 text-left transition-colors hover:border-primary/50 hover:bg-hover disabled:opacity-50"
              >
                <div className="min-w-0">
                  <div className="text-xs font-medium text-foreground">{item.title}</div>
                </div>
                <span className="shrink-0 rounded-md bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                  {item.tag}
                </span>
              </button>
            ))}
          </div>
        ) : null}

        {/* Messages Scroll Area */}
        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
          {messages.length === 0 && !loading ? (
            <div className="space-y-4 py-3">
              <div className="rounded-2xl border border-primary/25 bg-primary/5 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-primary">
                  <Sparkles className="h-4 w-4" />
                  <span>Programa Doğrudan Bağlı CLI-Native Asistan</span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-secondary-text">
                  Claude Code CLI veya Gemini CLI, arka planda <code className="rounded bg-background/80 px-1 py-0.5 font-mono text-[11px] text-foreground">dsa</code> MCP sunucusuyla canlı tarayıcıları, piyasa rejimini, Kripto 5-SMA trendini ve sanal portföyünü doğrudan çalıştırır.
                </p>
              </div>

              <div className="space-y-2">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-secondary-text">
                  Tek Tık Stratejik Komutlar
                </div>
                {STRATEGIC_PROMPTS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => void handleSend(item.prompt)}
                    className="group flex w-full flex-col gap-1 rounded-2xl border border-border/60 bg-background/60 p-3 text-left transition-all hover:border-primary/50 hover:bg-hover/70"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-foreground group-hover:text-primary">
                        {item.title}
                      </span>
                      <span className="shrink-0 rounded-md bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                        {item.tag}
                      </span>
                    </div>
                    <p className="line-clamp-2 text-[11px] text-secondary-text">{item.prompt}</p>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {messages.map((msg) => (
            <div
              key={msg.id}
              className={cn(
                'flex flex-col',
                msg.role === 'user' ? 'items-end' : 'items-start',
              )}
            >
              {msg.role === 'assistant' && msg.thinkingSteps && msg.thinkingSteps.length > 0 ? (
                <div className="w-full max-w-[96%]">
                  <ToolStepsTimeline steps={msg.thinkingSteps} />
                </div>
              ) : null}

              <div
                className={cn(
                  'max-w-[96%] rounded-2xl px-3.5 py-2.5 text-xs leading-relaxed',
                  msg.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'w-full border border-border/60 bg-background/70 text-foreground',
                )}
              >
                {msg.role === 'user' ? (
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                ) : (
                  <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:my-2 prose-headings:text-sm prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-table:my-2 prose-table:text-[11px] prose-th:px-2 prose-th:py-1 prose-td:px-2 prose-td:py-1 prose-code:text-[11px]">
                    <Markdown remarkPlugins={[remarkGfm]}>{msg.content}</Markdown>
                  </div>
                )}
              </div>

              {msg.backend ? (
                <span className="mt-1 px-1 font-mono text-[10px] text-secondary-text/75">
                  {msg.role === 'assistant' ? `via ${msg.backend}` : ''}
                </span>
              ) : null}
            </div>
          ))}

          {loading ? (
            <div className="space-y-2">
              <ToolStepsTimeline steps={progressSteps} live />
              {progressSteps.length === 0 ? (
                <div className="flex items-center gap-2 rounded-xl border border-border/60 bg-background/60 px-3 py-2 text-xs text-secondary-text">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                  <span>{activeBackendMeta?.label || 'Copilot'} MCP köprüsü başlatılıyor…</span>
                </div>
              ) : null}
            </div>
          ) : null}

          {terminalStatus === 'cancelled' ? (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
              İstek kullanıcı tarafından durduruldu.
            </div>
          ) : null}

          {terminalStatus === 'timeout' ? (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
              İstek zaman aşımına uğradı; daha dar bir tarama isteğiyle tekrar deneyebilirsin.
            </div>
          ) : null}

          {chatError ? (
            <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
              <div className="font-semibold">{chatError.title || 'Bağlantı / Motor Hatası'}</div>
              <div className="mt-0.5 text-[11px] opacity-90">{chatError.message}</div>
            </div>
          ) : null}
        </div>

        {/* Composer */}
        <div className="border-t border-border/60 bg-background/60 p-3">
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder="Örn: Şu an en güvenli stratejik trading önerini ver, NVDA analiz et veya BIST tara..."
              disabled={loading}
              className="max-h-32 min-h-[44px] flex-1 resize-none rounded-xl border border-border/70 bg-card/90 px-3 py-2 text-xs text-foreground placeholder:text-secondary-text/70 focus:border-primary focus:outline-none disabled:opacity-60"
            />
            {loading ? (
              <button
                type="button"
                disabled={stopping}
                onClick={() => void stopStream()}
                className="inline-flex h-[44px] shrink-0 items-center gap-1.5 rounded-xl border border-rose-500/50 bg-rose-500/15 px-3 text-xs font-semibold text-rose-300 transition-colors hover:bg-rose-500/25 disabled:opacity-50"
              >
                <Square className="h-3.5 w-3.5 fill-current" />
                <span>{stopping ? 'Duruyor' : 'Durdur'}</span>
              </button>
            ) : (
              <button
                type="button"
                disabled={!input.trim()}
                onClick={() => void handleSend()}
                className="inline-flex h-[44px] shrink-0 items-center gap-1.5 rounded-xl bg-primary px-3.5 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
              >
                <Send className="h-3.5 w-3.5" />
                <span>Gönder</span>
              </button>
            )}
          </div>
          <div className="mt-2 flex items-center justify-between gap-2 text-[10px] text-secondary-text/80">
            <span className="inline-flex items-center gap-1">
              <ShieldCheck className="h-3 w-3 text-emerald-400" />
              <span>Yalnızca analiz & sanal defter · Gerçek emir göndermez</span>
            </span>
            <span className="font-mono">Enter Gönder · Esc Kapat</span>
          </div>
        </div>
      </aside>
    </div>
  ) : null;

  if (typeof document === 'undefined') {
    return null;
  }

  return createPortal(
    <>
      {launcher}
      {drawerContent}
    </>,
    document.body,
  );
};
