import type React from 'react';
import { useMemo, useState } from 'react';
import { BookOpen, MessageSquareQuote, Search, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  GUIDE_LESSONS,
  INVESTOR_GLOSSARY,
  SIMPLE_CHAT_STARTERS,
  type GlossaryEntry,
} from '../i18n/investorGlossary';
import { openCopilotDrawer } from '../components/chat/copilotEvents';
import { cn } from '../utils/cn';

type CategoryFilter = 'all' | GlossaryEntry['category'];

const CATEGORY_LABELS: Array<{ id: CategoryFilter; label: string }> = [
  { id: 'all', label: 'Tümü' },
  { id: 'temel', label: 'Temel Kavramlar' },
  { id: 'kalkan', label: 'Koruma Kalkanı' },
  { id: 'turkiye', label: 'Türkiye & TEFAS' },
  { id: 'risk', label: 'Risk & Maliyet' },
];

const InvestorGuidePage: React.FC = () => {
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<CategoryFilter>('all');

  const glossaryItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return Object.values(INVESTOR_GLOSSARY).filter((entry) => {
      if (category !== 'all' && entry.category !== category) return false;
      if (!q) return true;
      return (
        entry.term.toLowerCase().includes(q)
        || entry.shortTitle.toLowerCase().includes(q)
        || entry.plainDefinition.toLowerCase().includes(q)
        || entry.everydayExample.toLowerCase().includes(q)
      );
    });
  }, [category, search]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-3 pb-10 pt-2 sm:px-6 lg:px-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-sky-400">
            <BookOpen className="h-3 w-3" />
            Sıfırdan Yatırım Rehberi & Sözlük
          </span>
          <h1 className="mt-1.5 text-xl font-bold tracking-tight text-foreground sm:text-2xl">
            30 Saniyelik Kartlarla Yatırımı Anla
          </h1>
          <p className="mt-0.5 text-sm text-secondary-text">
            Hiç finans eğitimi almadan, günlük hayattan örneklerle bu programın nasıl çalıştığını öğren.
          </p>
        </div>

        <Link
          to="/simple"
          className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/10 px-3.5 py-2 text-xs font-semibold text-primary transition-colors hover:bg-primary/20"
        >
          ← Bugün Ne Yapayım? Ekranına Dön
        </Link>
      </div>

      {/* 6 Bite-Sized 30-Second Lessons */}
      <section aria-label="30 Saniyelik Ders Kartları" className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {GUIDE_LESSONS.map((lesson) => (
          <article
            key={lesson.id}
            className="flex flex-col rounded-2xl border border-border/70 bg-card/80 p-5 shadow-soft-card"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-2xl" aria-hidden="true">{lesson.emoji}</span>
              <span className="rounded-full border border-border/60 bg-background/60 px-2.5 py-0.5 font-mono text-[10px] text-secondary-text">
                Okuma: {lesson.readTime}
              </span>
            </div>
            <h2 className="mt-2.5 text-sm font-bold text-foreground">{lesson.title}</h2>
            <p className="mt-1 text-xs font-medium text-primary/90">{lesson.summary}</p>
            <ul className="mt-3 space-y-1.5 text-xs leading-relaxed text-secondary-text">
              {lesson.bullets.map((b, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary/70" />
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </section>

      {/* Ask Assistant Ready Questions */}
      <section className="rounded-2xl border border-emerald-500/30 bg-emerald-500/6 p-5">
        <div className="flex items-center gap-2">
          <MessageSquareQuote className="h-4 w-4 text-emerald-400" />
          <h2 className="text-sm font-bold text-foreground">Aklına Takılanı Tek Tıkla Asistana Sor</h2>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {SIMPLE_CHAT_STARTERS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => openCopilotDrawer(q)}
              className="cursor-pointer rounded-xl border border-border/60 bg-card/85 px-3.5 py-2.5 text-left text-xs text-foreground transition-colors hover:border-emerald-500/50 hover:bg-hover"
            >
              “{q}”
            </button>
          ))}
        </div>
      </section>

      {/* Searchable Plain-Turkish Glossary */}
      <section className="rounded-2xl border border-border/70 bg-card/80 p-5 shadow-soft-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-foreground">Sade Türkçe Yatırım Sözlüğü</h2>
            <p className="text-xs text-secondary-text">
              Ekranda gördüğün herhangi bir terimi arat; günlük örnekli karşılığını hemen gör.
            </p>
          </div>
          <div className="relative min-w-[220px] flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-secondary-text" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Terim ara (örn. TEFAS, ETF, BIL, VIX)..."
              aria-label="Sözlükte terim ara"
              className="w-full rounded-xl border border-border/70 bg-background/60 py-1.5 pl-8 pr-3 text-xs text-foreground placeholder:text-muted-text focus:border-primary focus:outline-none"
            />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {CATEGORY_LABELS.map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => setCategory(cat.id)}
              className={cn(
                'cursor-pointer rounded-xl px-2.5 py-1 text-xs font-medium transition-colors',
                category === cat.id
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border/60 bg-background/50 text-secondary-text hover:bg-hover hover:text-foreground',
              )}
            >
              {cat.label}
            </button>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          {glossaryItems.length === 0 ? (
            <p className="col-span-full py-6 text-center text-xs text-secondary-text">
              Aradığın terimle eşleşen kayıt bulunamadı.
            </p>
          ) : (
            glossaryItems.map((entry) => (
              <div
                key={entry.key}
                className="rounded-2xl border border-border/60 bg-background/50 p-4"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-bold text-foreground">{entry.term}</h3>
                    <p className="text-xs font-medium text-primary">{entry.shortTitle}</p>
                  </div>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-foreground/90">{entry.plainDefinition}</p>
                <p className="mt-2 rounded-xl border border-border/50 bg-card/70 p-2.5 text-[11px] leading-relaxed text-secondary-text">
                  <strong className="text-foreground">Örnek: </strong>
                  {entry.everydayExample}
                </p>
              </div>
            ))
          )}
        </div>
      </section>

      <div className="flex items-start gap-2.5 rounded-2xl border border-border/60 bg-background/50 px-4 py-3 text-xs text-secondary-text">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
        <span>
          Hatırlatma: Yatırım kararları kişisel risk profiline göre verilmelidir. Kısa vadede ihtiyacın olan acil durum paranla asla dalgalı varlıklara girme.
        </span>
      </div>
    </div>
  );
};

export default InvestorGuidePage;
