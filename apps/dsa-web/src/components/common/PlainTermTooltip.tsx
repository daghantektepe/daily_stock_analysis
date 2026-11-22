import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import { HelpCircle, X } from 'lucide-react';
import { INVESTOR_GLOSSARY } from '../../i18n/investorGlossary';
import { cn } from '../../utils/cn';

interface PlainTermTooltipProps {
  termKey: string;
  label?: string;
  className?: string;
}

export const PlainTermTooltip: React.FC<PlainTermTooltipProps> = ({
  termKey,
  label,
  className,
}) => {
  const entry = INVESTOR_GLOSSARY[termKey];
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  if (!entry) return null;

  return (
    <span ref={wrapRef} className={cn('relative inline-flex items-center align-middle', className)}>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((prev) => !prev);
        }}
        aria-expanded={open}
        aria-label={`${entry.term} nedir?`}
        className="inline-flex cursor-pointer items-center gap-1 rounded-full border border-border/60 bg-background/70 px-1.5 py-0.5 text-[11px] font-medium text-secondary-text transition-colors hover:border-primary/50 hover:text-primary"
      >
        <HelpCircle className="h-3 w-3 shrink-0" />
        {label ? <span>{label}</span> : null}
      </button>

      {open ? (
        <div
          role="dialog"
          aria-label={`${entry.term} açıklaması`}
          onClick={(e) => e.stopPropagation()}
          className="absolute left-0 top-full z-50 mt-2 w-72 max-w-[85vw] rounded-2xl border border-border/80 bg-card p-3.5 text-left shadow-xl sm:w-80"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-xs font-semibold text-foreground">{entry.term}</p>
              <p className="text-[11px] font-medium text-primary">{entry.shortTitle}</p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Açıklamayı kapat"
              className="rounded-lg p-1 text-secondary-text hover:bg-hover hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-foreground/90">{entry.plainDefinition}</p>
          <div className="mt-2 rounded-xl border border-border/50 bg-background/60 p-2 text-[11px] leading-relaxed text-secondary-text">
            <span className="font-semibold text-foreground">Günlük örnek: </span>
            {entry.everydayExample}
          </div>
        </div>
      ) : null}
    </span>
  );
};
