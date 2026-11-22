import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ClipboardCopy,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Terminal,
  Wallet,
  X,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  alphaApi,
  type SimpleBriefResponse,
  type SimpleProfileOption,
} from '../api/alpha';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, Button } from '../components/common';
import { PlainTermTooltip } from '../components/common/PlainTermTooltip';
import { openCopilotDrawer } from '../components/chat/copilotEvents';
import { cn } from '../utils/cn';

const TOUR_STORAGE_KEY = 'dsa.simpleWelcomeDismissed';

const TRY_PRESETS = [10_000, 50_000, 100_000, 500_000];
const USD_PRESETS = [1_000, 5_000, 10_000, 25_000];

const fmtMoney = (amount: number, currency: 'TRY' | 'USD'): string => {
  const formatted = amount.toLocaleString('tr-TR', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
  return currency === 'TRY' ? `${formatted} ₺` : `$${formatted}`;
};

const SimpleInvestorHomePage: React.FC = () => {
  const [brief, setBrief] = useState<SimpleBriefResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('balanced');
  const [currency, setCurrency] = useState<'TRY' | 'USD'>('TRY');
  const [budgetRaw, setBudgetRaw] = useState<string>('100000');
  const [copied, setCopied] = useState(false);
  const [showWelcome, setShowWelcome] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(TOUR_STORAGE_KEY) !== '1';
    } catch {
      return true;
    }
  });

  const loadBrief = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await alphaApi.getSimpleBrief();
      setBrief(data);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadBrief();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadBrief]);

  const dismissWelcome = () => {
    setShowWelcome(false);
    try {
      window.localStorage.setItem(TOUR_STORAGE_KEY, '1');
    } catch {
      // ignore storage errors
    }
  };

  const budgetNumber = useMemo(() => {
    const cleaned = budgetRaw.replace(/[^0-9.,]/g, '').replace(',', '.');
    const parsed = Number.parseFloat(cleaned);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  }, [budgetRaw]);

  const usdtry = brief?.usdtry_rate && brief.usdtry_rate > 0 ? brief.usdtry_rate : 50.56;

  const activeProfile: SimpleProfileOption | null = useMemo(() => {
    const list = brief?.profiles ?? [];
    if (list.length === 0) return null;
    return list.find((p) => p.id === selectedProfileId) ?? list.find((p) => p.recommended) ?? list[0];
  }, [brief, selectedProfileId]);

  const estimatedAnnualCost = useMemo(() => {
    if (!activeProfile || budgetNumber <= 0) return 0;
    return budgetNumber * (activeProfile.estimated_annual_cost_pct / 100);
  }, [activeProfile, budgetNumber]);

  const handleCurrencySwitch = (nextCurrency: 'TRY' | 'USD') => {
    if (nextCurrency === currency) return;
    setCurrency(nextCurrency);
    setBudgetRaw(nextCurrency === 'TRY' ? '100000' : '5000');
  };

  const buildShoppingListText = (): string => {
    if (!activeProfile || !brief) return '';
    const lines: string[] = [
      `Yatırım Sepeti Özeti (${brief.as_of_date}) — ${activeProfile.title}`,
      `Piyasa Hava Durumu: ${brief.weather.emoji} ${brief.weather.badge_label}`,
      `Bütçe: ${fmtMoney(budgetNumber, currency)} (Kur referansı: 1 $ ≈ ${usdtry.toFixed(2)} ₺)`,
      '',
    ];
    for (const item of activeProfile.assets) {
      const sliceAmount = (budgetNumber * item.weight_pct) / 100;
      const altAmount = currency === 'TRY' ? sliceAmount / usdtry : sliceAmount * usdtry;
      const altCurrency = currency === 'TRY' ? 'USD' : 'TRY';
      lines.push(
        `- %${item.weight_pct.toFixed(1)} → ${fmtMoney(sliceAmount, currency)} (~${fmtMoney(altAmount, altCurrency)}) | ${item.symbol} (${item.plain_name})`,
      );
      lines.push(`  Midas / Banka karşılığı: ${item.midas_hint}`);
    }
    lines.push('', 'Not: Yalnızca karar destek amaçlıdır; otomatik emir gönderilmez.');
    return lines.join('\n');
  };

  const handleCopyShoppingList = async () => {
    const text = buildShoppingListText();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2400);
    } catch {
      // Clipboard fallback ignored
    }
  };

  const askAssistantPlain = () => {
    const profileLabel = activeProfile?.title ?? 'Dengeli Kalkan';
    openCopilotDrawer(
      `Finans terimi kullanmadan, anneme anlatır gibi sade Türkçe ile açıkla: Bugünkü piyasa hava durumu (${brief?.weather.badge_label ?? 'güncel'}), "${profileLabel}" sepeti ve ${fmtMoney(budgetNumber, currency)} bütçe için neden bu dağılım öneriliyor? Midas veya Türk bankasındaki TEFAS fonlarıyla bunu nasıl sakin şekilde uygularım?`,
    );
  };

  const weatherToneClass =
    brief?.weather.status === 'sunny'
      ? 'border-emerald-500/40 bg-emerald-500/8'
      : brief?.weather.status === 'cloudy'
        ? 'border-sky-500/40 bg-sky-500/8'
        : 'border-amber-500/40 bg-amber-500/8';

  const weatherBadgeClass =
    brief?.weather.status === 'sunny'
      ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-400'
      : brief?.weather.status === 'cloudy'
        ? 'border-sky-500/40 bg-sky-500/15 text-sky-400'
        : 'border-amber-500/40 bg-amber-500/15 text-amber-400';

  return (
    <div className="mx-auto max-w-6xl space-y-5 px-3 pb-10 pt-2 sm:px-6 lg:px-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-400">
            <Sparkles className="h-3 w-3" />
            Basit Mod · Herkes İçin Sade Yatırım Rehberi
          </span>
          <h1 className="mt-1.5 text-xl font-bold tracking-tight text-foreground sm:text-2xl">
            Bugün Ne Yapmalıyım?
          </h1>
          <p className="mt-0.5 text-sm text-secondary-text">
            Karmaşık grafikler ve borsa jargonu olmadan, paranı koruyarak adım adım ne yapacağını gör.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Link
            to="/guide"
            className="inline-flex items-center gap-1.5 rounded-xl border border-border/70 bg-card px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-hover"
          >
            <BookOpen className="h-3.5 w-3.5 text-primary" />
            <span>30 Saniyede Öğren</span>
          </Link>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void loadBrief()}
            disabled={loading}
          >
            <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', loading && 'animate-spin')} />
            Yenile
          </Button>
        </div>
      </div>

      {error ? <ApiErrorAlert error={error} /> : null}

      {/* Dismissible 3-Step Welcome Tour */}
      {showWelcome ? (
        <div className="relative rounded-2xl border border-primary/35 bg-primary/5 p-4">
          <button
            type="button"
            onClick={dismissWelcome}
            aria-label="Hoş geldin rehberini gizle"
            className="absolute right-3 top-3 rounded-lg p-1 text-secondary-text hover:bg-hover hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
          <p className="text-xs font-semibold uppercase tracking-wide text-primary">
            İlk Kez Geliyorsan — 3 Adımda Başla
          </p>
          <div className="mt-2.5 grid grid-cols-1 gap-3 text-xs sm:grid-cols-3">
            <div className="rounded-xl border border-border/50 bg-card/80 p-3">
              <p className="font-semibold text-foreground">1. Hava Durumuna Bak</p>
              <p className="mt-1 text-secondary-text">
                Fırtınalıysa sistem kalkanı açar; güneşliyse büyüme sepetini önerir.
              </p>
            </div>
            <div className="rounded-xl border border-border/50 bg-card/80 p-3">
              <p className="font-semibold text-foreground">2. Bütçeni Yaz</p>
              <p className="mt-1 text-secondary-text">
                Aşağıya TL veya Dolar tutarını gir; program her kalemi kuruşu kuruşuna bölsün.
              </p>
            </div>
            <div className="rounded-xl border border-border/50 bg-card/80 p-3">
              <p className="font-semibold text-foreground">3. Ayda 1 Kez Kontrol Et</p>
              <p className="mt-1 text-secondary-text">
                Her gün ekran izleme. Anlamadığın her kelimenin yanındaki ? işaretine tıkla.
              </p>
            </div>
          </div>
        </div>
      ) : null}

      {/* Loading skeleton */}
      {loading && !brief ? (
        <div className="rounded-2xl border border-border/60 bg-card/70 p-8 text-center text-sm text-secondary-text">
          Güncel piyasa hava durumu ve güvenli sepetler hazırlanıyor...
        </div>
      ) : null}

      {brief ? (
        <>
          {/* CARD 1: Market Weather Traffic Light */}
          <section
            aria-label="Piyasa Hava Durumu"
            className={cn('rounded-3xl border p-5 shadow-soft-card sm:p-6', weatherToneClass)}
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex items-start gap-4">
                <div
                  className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-border/50 bg-card/90 text-3xl shadow-sm"
                  aria-hidden="true"
                >
                  {brief.weather.emoji}
                </div>
                <div className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={cn('rounded-full border px-2.5 py-0.5 text-xs font-semibold', weatherBadgeClass)}>
                      {brief.weather.badge_label}
                    </span>
                    <span className="text-xs text-secondary-text">
                      Veri tarihi: <strong className="text-foreground">{brief.as_of_date}</strong>
                    </span>
                    <PlainTermTooltip termKey="risk_off" label="Bu ne demek?" />
                  </div>
                  <h2 className="text-lg font-bold text-foreground sm:text-xl">
                    {brief.weather.headline}
                  </h2>
                  <p className="max-w-3xl text-sm leading-relaxed text-foreground/90">
                    {brief.weather.plain_summary}
                  </p>
                </div>
              </div>

              <div className="rounded-2xl border border-border/60 bg-card/85 px-4 py-3 text-right">
                <p className="text-[11px] font-medium text-secondary-text">Güvenli Liman Payı</p>
                <p className="mt-0.5 font-mono text-2xl font-bold text-foreground">
                  %{brief.weather.protection_pct.toFixed(0)}
                </p>
                <p className="text-[11px] text-emerald-400">Otomatik emir kapalı</p>
              </div>
            </div>

            <div className="mt-4 flex items-start gap-2.5 rounded-2xl border border-border/50 bg-card/75 px-4 py-3 text-xs leading-relaxed text-secondary-text">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
              <span>{brief.weather.behavioral_guard}</span>
            </div>
          </section>

          {/* CARD 2: Composer-Style Visual Decision Flow */}
          <section className="rounded-2xl border border-border/70 bg-card/80 p-5 shadow-soft-card">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-semibold text-foreground">
                  Robot Neden Bu Kararı Verdi?
                </h2>
                <p className="text-xs text-secondary-text">
                  Tahmin ya da duyum değil; 3 basit ve şeffaf kural adımı.
                </p>
              </div>
              <button
                type="button"
                onClick={askAssistantPlain}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-400 transition-colors hover:bg-emerald-500/20"
              >
                <Terminal className="h-3.5 w-3.5" />
                <span>Asistana Sade Anlattır</span>
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {brief.decision_steps.map((step, idx) => (
                <div
                  key={step.step}
                  className="relative flex flex-col justify-between rounded-2xl border border-border/60 bg-background/55 p-4"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-primary/15 font-mono text-xs font-bold text-primary">
                        {step.step}
                      </span>
                      {step.glossary_term ? <PlainTermTooltip termKey={step.glossary_term} /> : null}
                    </div>
                    <h3 className="mt-2.5 text-sm font-semibold text-foreground">{step.title}</h3>
                    <p className="mt-1 text-xs leading-relaxed text-secondary-text">{step.explanation}</p>
                  </div>
                  {idx < brief.decision_steps.length - 1 ? (
                    <ArrowRight
                      className="mt-3 hidden h-4 w-4 self-end text-secondary-text/50 md:block"
                      aria-hidden="true"
                    />
                  ) : null}
                </div>
              ))}
            </div>
          </section>

          {/* CARD 3: Interactive Budget Calculator & Turkish Equivalents */}
          <section className="rounded-2xl border border-border/70 bg-card/85 p-5 shadow-soft-card">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="flex items-center gap-2 text-base font-semibold text-foreground">
                  <Wallet className="h-4 w-4 text-primary" />
                  <span>Paramı Nasıl Böleyim? (Adım Adım Sepet Hesaplayıcı)</span>
                </h2>
                <p className="mt-0.5 text-xs text-secondary-text">
                  Tutarını yaz ve sana uyan sakinlik düzeyini seç — hem Midas ABD hem Türk Bankası TEFAS karşılığını gör.
                </p>
              </div>

              {/* Currency Switch */}
              <div className="inline-flex rounded-xl border border-border/70 bg-background/60 p-1 text-xs">
                <button
                  type="button"
                  onClick={() => handleCurrencySwitch('TRY')}
                  className={cn(
                    'cursor-pointer rounded-lg px-3 py-1 font-semibold transition-colors',
                    currency === 'TRY'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-secondary-text hover:text-foreground',
                  )}
                >
                  TL (₺)
                </button>
                <button
                  type="button"
                  onClick={() => handleCurrencySwitch('USD')}
                  className={cn(
                    'cursor-pointer rounded-lg px-3 py-1 font-semibold transition-colors',
                    currency === 'USD'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-secondary-text hover:text-foreground',
                  )}
                >
                  Dolar ($)
                </button>
              </div>
            </div>

            {/* Budget Input + Quick Presets */}
            <div className="mt-4 flex flex-wrap items-center gap-3 rounded-2xl border border-border/60 bg-background/50 p-3.5">
              <div className="min-w-[180px] flex-1">
                <label htmlFor="simple-budget-input" className="block text-[11px] font-medium text-secondary-text">
                  Yatırmayı düşündüğün tutar ({currency === 'TRY' ? 'Türk Lirası' : 'ABD Doları'})
                </label>
                <input
                  id="simple-budget-input"
                  type="text"
                  inputMode="decimal"
                  value={budgetRaw}
                  onChange={(e) => setBudgetRaw(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-border/70 bg-card px-3 py-2 font-mono text-base font-bold text-foreground focus:border-primary focus:outline-none"
                />
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {(currency === 'TRY' ? TRY_PRESETS : USD_PRESETS).map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => setBudgetRaw(String(preset))}
                    className={cn(
                      'cursor-pointer rounded-xl border px-2.5 py-1.5 font-mono text-xs font-medium transition-colors',
                      budgetNumber === preset
                        ? 'border-primary bg-primary/15 text-primary'
                        : 'border-border/60 bg-card text-secondary-text hover:bg-hover hover:text-foreground',
                    )}
                  >
                    {fmtMoney(preset, currency)}
                  </button>
                ))}
              </div>
              <p className="w-full text-[11px] text-secondary-text sm:w-auto">
                Yaklaşık karşılık:{' '}
                <strong className="font-mono text-foreground">
                  {currency === 'TRY'
                    ? fmtMoney(budgetNumber / usdtry, 'USD')
                    : fmtMoney(budgetNumber * usdtry, 'TRY')}
                </strong>{' '}
                (1 $ ≈ {usdtry.toFixed(2)} ₺)
              </p>
            </div>

            {/* 3 Risk Profile Selector Cards */}
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
              {brief.profiles.map((profile) => {
                const selected = activeProfile?.id === profile.id;
                return (
                  <button
                    key={profile.id}
                    type="button"
                    onClick={() => setSelectedProfileId(profile.id)}
                    className={cn(
                      'cursor-pointer rounded-2xl border p-4 text-left transition-all',
                      selected
                        ? 'border-primary bg-primary/10 ring-1 ring-primary/40'
                        : 'border-border/60 bg-background/45 hover:border-border hover:bg-hover/40',
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-lg" aria-hidden="true">{profile.emoji}</span>
                      {profile.recommended ? (
                        <span className="rounded-full border border-emerald-500/40 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                          Standart Öneri
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-2 text-sm font-bold text-foreground">{profile.title}</p>
                    <p className="mt-1 text-xs leading-relaxed text-secondary-text">{profile.subtitle}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-secondary-text">
                      <span>
                        En kötü kriz:{' '}
                        <strong className="font-mono text-foreground">
                          %{profile.historical_max_dd_pct.toFixed(1)}
                        </strong>
                      </span>
                      <span>·</span>
                      <span>{profile.rebalance_cadence}</span>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Concrete Basket Breakdown */}
            {activeProfile ? (
              <div className="mt-5 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border/50 bg-background/40 px-3.5 py-2.5 text-xs">
                  <div className="flex flex-wrap items-center gap-2 text-secondary-text">
                    <span>
                      Seçili sepet: <strong className="text-foreground">{activeProfile.title}</strong>
                    </span>
                    <span>·</span>
                    <span>
                      Tahmini yıllık işlem masrafı:{' '}
                      <strong className="font-mono text-foreground">
                        ~{fmtMoney(Math.max(1, Math.round(estimatedAnnualCost)), currency)}
                      </strong>{' '}
                      (%{activeProfile.estimated_annual_cost_pct.toFixed(2)})
                    </span>
                    <PlainTermTooltip termKey="slippage" />
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button variant="primary" size="sm" onClick={() => void handleCopyShoppingList()}>
                      {copied ? (
                        <>
                          <Check className="mr-1.5 h-3.5 w-3.5" />
                          Liste Kopyalandı!
                        </>
                      ) : (
                        <>
                          <ClipboardCopy className="mr-1.5 h-3.5 w-3.5" />
                          Midas / Banka Listesini Kopyala
                        </>
                      )}
                    </Button>
                  </div>
                </div>

                <div className="space-y-2.5">
                  {activeProfile.assets.map((asset) => {
                    const primaryAmt = (budgetNumber * asset.weight_pct) / 100;
                    const altAmt = currency === 'TRY' ? primaryAmt / usdtry : primaryAmt * usdtry;
                    const altCur = currency === 'TRY' ? 'USD' : 'TRY';
                    return (
                      <div
                        key={asset.symbol}
                        className="rounded-2xl border border-border/60 bg-background/55 p-4"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="rounded-lg bg-primary/15 px-2 py-0.5 font-mono text-xs font-bold text-primary">
                                {asset.symbol}
                              </span>
                              <span className="text-sm font-semibold text-foreground">{asset.plain_name}</span>
                              <span className="rounded-full border border-border/60 bg-card px-2 py-0.5 text-[10px] text-secondary-text">
                                Risk: {asset.risk_level}
                              </span>
                            </div>
                            <p className="mt-1 text-xs leading-relaxed text-secondary-text">{asset.role}</p>
                            <div className="mt-2 inline-flex flex-wrap items-center gap-1.5 rounded-xl border border-sky-500/30 bg-sky-500/8 px-2.5 py-1 text-[11px] text-sky-300">
                              <span className="font-semibold">Türkiye Banka / Midas Karşılığı:</span>
                              <span>{asset.tr_equivalent}</span>
                              <PlainTermTooltip termKey="tefas" />
                            </div>
                          </div>

                          <div className="shrink-0 text-right">
                            <p className="font-mono text-lg font-bold text-foreground">
                              {fmtMoney(primaryAmt, currency)}
                            </p>
                            <p className="font-mono text-xs text-secondary-text">
                              %{asset.weight_pct.toFixed(1)} · ~{fmtMoney(altAmt, altCur)}
                            </p>
                          </div>
                        </div>

                        <div className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-border/40">
                          <div
                            className="h-full rounded-full bg-primary"
                            style={{ width: `${Math.min(100, asset.weight_pct)}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
          </section>

          {/* CARD 4: Live 120-Day Forward Exam Transparency */}
          {brief.paper_exam.length > 0 ? (
            <section className="rounded-2xl border border-border/70 bg-card/80 p-5 shadow-soft-card">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="flex items-center gap-2 text-base font-semibold text-foreground">
                    <CheckCircle2 className="h-4 w-4 text-sky-400" />
                    <span>Sanal Kasa Canlı Sınavı (Şeffaflık Paneli)</span>
                    <PlainTermTooltip termKey="forward_gate" label="Nedir?" />
                  </h2>
                  <p className="mt-0.5 text-xs text-secondary-text">
                    Sadece geçmiş testlere güvenmiyoruz — dondurulmuş stratejiler gerçek piyasa fiyatlarıyla her gün sanal kasada sınanıyor.
                  </p>
                </div>
                <Link
                  to="/discover"
                  className="text-xs font-medium text-primary hover:underline"
                >
                  Detaylı Uzman Raporunu Aç →
                </Link>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {brief.paper_exam.map((item) => {
                  const pct = Math.min(100, Math.round((item.forward_days / item.target_days) * 100));
                  return (
                    <div
                      key={item.strategy_key}
                      className="rounded-2xl border border-border/60 bg-background/50 p-4"
                    >
                      <p className="text-sm font-semibold text-foreground">{item.plain_label}</p>
                      <p className="mt-0.5 text-[11px] text-secondary-text">{item.status_plain}</p>

                      <div className="mt-3 flex items-baseline justify-between">
                        <span className="font-mono text-lg font-bold text-foreground">
                          ${item.nav_usd.toLocaleString('tr-TR', { maximumFractionDigits: 0 })}
                        </span>
                        <span
                          className={cn(
                            'font-mono text-xs font-semibold',
                            item.return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400',
                          )}
                        >
                          {item.return_pct >= 0 ? '+' : ''}
                          {item.return_pct.toFixed(2)}%
                        </span>
                      </div>
                      {item.benchmark_return_pct !== null && item.benchmark_return_pct !== undefined ? (
                        <p className="mt-0.5 text-[11px] text-secondary-text">
                          Aynı sürede ABD Borsası (SPY):{' '}
                          <strong className="font-mono text-foreground">
                            {item.benchmark_return_pct >= 0 ? '+' : ''}
                            {item.benchmark_return_pct.toFixed(2)}%
                          </strong>
                        </p>
                      ) : null}

                      <div className="mt-3">
                        <div className="mb-1 flex justify-between font-mono text-[10px] text-secondary-text">
                          <span>120 Günlük Sınav</span>
                          <span>{item.forward_days} / {item.target_days}</span>
                        </div>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-border/50">
                          <div className="h-full rounded-full bg-sky-400" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          ) : null}

          {/* Honest Disclaimer Footer */}
          <div className="rounded-2xl border border-border/60 bg-background/50 px-4 py-3 text-xs leading-relaxed text-secondary-text">
            <strong className="text-foreground">Güvenlik & Şeffaflık Notu: </strong>
            {brief.disclaimer}
          </div>
        </>
      ) : null}
    </div>
  );
};

export default SimpleInvestorHomePage;
