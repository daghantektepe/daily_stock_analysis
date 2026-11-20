import type React from 'react';
import { useEffect } from 'react';
import { Cpu, RefreshCw, Terminal } from 'lucide-react';
import { cn } from '../../utils/cn';
import { useAgentChatStore } from '../../stores/agentChatStore';
import type { AgentBackendId } from '../../api/agent';

interface BackendSwitcherProps {
  compact?: boolean;
  className?: string;
}

const BACKEND_SHORT_LABELS: Record<string, string> = {
  claude_cli: 'Claude CLI',
  gemini_cli: 'Gemini CLI',
  litellm: 'LiteLLM',
  codex_app_server: 'Codex',
};

export const BackendSwitcher: React.FC<BackendSwitcherProps> = ({
  compact = false,
  className,
}) => {
  const backends = useAgentChatStore((s) => s.backends) ?? [];
  const selectedBackend = useAgentChatStore((s) => s.selectedBackend);
  const loading = useAgentChatStore((s) => s.loading);
  const loadBackends = useAgentChatStore((s) => s.loadBackends);
  const setSelectedBackend = useAgentChatStore((s) => s.setSelectedBackend);

  useEffect(() => {
    if (typeof loadBackends === 'function') {
      void loadBackends();
    }
  }, [loadBackends]);

  if (backends.length === 0) {
    return null;
  }

  return (
    <div className={cn('flex flex-wrap items-center gap-1.5', className)}>
      {backends.map((item) => {
        const isSelected = selectedBackend === item.id;
        const shortLabel = BACKEND_SHORT_LABELS[item.id] ?? item.label;
        const ariaDesc = [
          item.label,
          item.version ? `v${item.version}` : null,
          !item.available && item.message ? item.message : null,
        ]
          .filter(Boolean)
          .join(' · ');

        return (
          <button
            key={item.id}
            type="button"
            disabled={!item.available || loading}
            onClick={() => setSelectedBackend?.(item.id as AgentBackendId)}
            aria-label={ariaDesc}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-xl border font-medium transition-all',
              compact ? 'px-2 py-1 text-[11px]' : 'px-2.5 py-1.5 text-xs',
              isSelected
                ? 'border-primary/70 bg-primary/15 text-foreground shadow-sm'
                : item.available
                  ? 'border-border/60 bg-background/60 text-secondary-text hover:border-primary/40 hover:bg-hover hover:text-foreground'
                  : 'cursor-not-allowed border-border/40 bg-background/30 text-secondary-text/50 opacity-60',
            )}
          >
            <span
              className={cn(
                'h-1.5 w-1.5 shrink-0 rounded-full',
                item.available
                  ? isSelected
                    ? 'bg-emerald-400 animate-pulse'
                    : 'bg-emerald-400/80'
                  : 'bg-rose-400/60',
              )}
            />
            {item.mcpEnabled ? (
              <Terminal className="h-3 w-3 shrink-0 text-primary" />
            ) : (
              <Cpu className="h-3 w-3 shrink-0 text-secondary-text" />
            )}
            <span>{compact ? shortLabel : item.label}</span>
            {item.mcpEnabled ? (
              <span className="rounded bg-primary/15 px-1 py-0.2 font-mono text-[9px] font-semibold uppercase tracking-wide text-primary">
                MCP
              </span>
            ) : null}
          </button>
        );
      })}
      <button
        type="button"
        disabled={loading}
        onClick={() => {
          if (typeof loadBackends === 'function') {
            void loadBackends(true);
          }
        }}
        aria-label="CLI motor durumunu yenile"
        className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-border/50 bg-background/50 text-secondary-text transition-colors hover:bg-hover hover:text-foreground disabled:opacity-40"
      >
        <RefreshCw className="h-3 w-3" />
      </button>
    </div>
  );
};
