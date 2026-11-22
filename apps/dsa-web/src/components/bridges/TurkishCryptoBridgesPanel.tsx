import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw, ShieldCheck } from 'lucide-react';
import {
  bridgesApi,
  type BinancePreviewResponse,
  type BridgesStatusResponse,
  type MacroTrResponse,
  type TefasFundsResponse,
} from '../../api/bridges';
import { Card } from '../common';

const TEFAS_BUCKETS: Array<{ id: string; label: string }> = [
  { id: 'all', label: 'Tümü' },
  { id: 'ppf', label: 'Para Piyasası (PPF)' },
  { id: 'altin', label: 'Altın Fonları' },
  { id: 'bist', label: 'BIST Hisse' },
  { id: 'yabanci', label: 'Yabancı / Teknoloji' },
  { id: 'degisken_doviz', label: 'Döviz / Değişken' },
];

const fmtTry = (v: number | null | undefined, digits = 2): string => {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return `${v.toLocaleString('tr-TR', { minimumFractionDigits: digits, maximumFractionDigits: digits })} ₺`;
};

const fmtSignedPct = (v: number | null | undefined): string => {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
};

const fmtCompactTry = (v: number | null | undefined): string => {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)} Mr ₺`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(0)} Mn ₺`;
  return `${v.toLocaleString('tr-TR', { maximumFractionDigits: 0 })} ₺`;
};

interface TurkishCryptoBridgesPanelProps {
  compact?: boolean;
}

export const TurkishCryptoBridgesPanel: React.FC<TurkishCryptoBridgesPanelProps> = ({ compact = false }) => {
  const [statusData, setStatusData] = useState<BridgesStatusResponse | null>(null);
  const [macroData, setMacroData] = useState<MacroTrResponse | null>(null);
  const [tefasData, setTefasData] = useState<TefasFundsResponse | null>(null);
  const [binanceData, setBinanceData] = useState<BinancePreviewResponse | null>(null);
  const [bucket, setBucket] = useState<string>('all');
  const [nominalInput, setNominalInput] = useState<string>('45');
  const [loading, setLoading] = useState<boolean>(false);
  const [testingLive, setTestingLive] = useState<boolean>(false);

  const loadAll = useCallback(async (forceRefresh = false, checkLive = false) => {
    setLoading(true);
    const parsedNom = Number.parseFloat(nominalInput.replace(',', '.'));
    const nominalParam = Number.isFinite(parsedNom) ? parsedNom : undefined;
    try {
      const [statusRes, macroRes, tefasRes, binanceRes] = await Promise.allSettled([
        bridgesApi.getStatus(checkLive),
        bridgesApi.getMacroTr({ nominalReturnPct: nominalParam, forceRefresh }),
        bridgesApi.getTefasFunds({ forceRefresh }),
        bridgesApi.getBinancePreview('BTC-USD,ETH-USD'),
      ]);
      if (statusRes.status === 'fulfilled') setStatusData(statusRes.value);
      if (macroRes.status === 'fulfilled') setMacroData(macroRes.value);
      if (tefasRes.status === 'fulfilled') setTefasData(tefasRes.value);
      if (binanceRes.status === 'fulfilled') setBinanceData(binanceRes.value);
    } finally {
      setLoading(false);
    }
  }, [nominalInput]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadAll(false, false);
    }, 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRecalcPower = async () => {
    const parsedNom = Number.parseFloat(nominalInput.replace(',', '.'));
    if (!Number.isFinite(parsedNom)) return;
    try {
      const next = await bridgesApi.getMacroTr({ nominalReturnPct: parsedNom });
      setMacroData(next);
    } catch {
      // keep existing macro view
    }
  };

  const handleTestLive = async () => {
    setTestingLive(true);
    try {
      await loadAll(true, true);
    } finally {
      setTestingLive(false);
    }
  };

  const filteredFunds = useMemo(() => {
    const list = tefasData?.funds ?? [];
    if (bucket === 'all') return list;
    return list.filter((f) => f.bucket === bucket);
  }, [tefasData, bucket]);

  return (
    <section aria-label="Türkiye & Kripto Veri Köprüleri" className="space-y-3">
      <Card padding="md">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              <span>Türkiye & Kripto Veri Köprüleri (TEFAS · TCMB EVDS · Binance · Midas)</span>
            </h3>
            <p className="mt-0.5 text-xs text-secondary">
              Tüm aracı kurum yazma uçları sanal / manuel onay kilitlidir; veriler yerel önbellek desteklidir.
            </p>
          </div>
          <button
            type="button"
            className="btn-secondary !px-3 !py-1.5 !text-xs inline-flex items-center gap-1.5"
            disabled={loading || testingLive}
            onClick={() => void handleTestLive()}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading || testingLive ? 'animate-spin' : ''}`} />
            {testingLive ? 'Test Ediliyor...' : 'Canlı Veriyi Yenile'}
          </button>
        </div>

        {/* Status Pills */}
        {statusData?.bridges && statusData.bridges.length > 0 ? (
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
            {statusData.bridges.map((b) => (
              <div
                key={b.id}
                className="rounded-xl border border-border/60 bg-background/40 px-3 py-2 text-xs"
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="font-semibold text-foreground truncate">{b.name}</span>
                  <span
                    className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                      b.liveReachable === false
                        ? 'bg-amber-500/15 text-amber-300'
                        : b.configured
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : 'bg-sky-500/15 text-sky-300'
                    }`}
                  >
                    {b.modeLabel}
                  </span>
                </div>
                {b.note ? <p className="mt-1 text-[11px] leading-snug text-secondary">{b.note}</p> : null}
              </div>
            ))}
          </div>
        ) : null}
      </Card>

      {/* Row 2: TCMB EVDS Reel Kazanç + Binance Live Ticker */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card padding="md">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h4 className="text-sm font-semibold text-foreground">Gerçek Kazanç Kartı (TL vs USD vs TÜFE)</h4>
              <p className="text-[11px] text-secondary">
                Kaynak: {macroData?.usdTrySource === 'tcmb_evds2' ? 'TCMB EVDS2 Resmi' : 'Yahoo TRY=X Yedek'}
                {!macroData?.evdsConfigured ? ' · EVDS_API_KEY tanımlanırsa yıllık TÜFE otomatik gelir' : ''}
              </p>
            </div>
            <div className="text-right font-mono text-xs">
              <div className="font-semibold text-foreground">
                1 $ = {macroData?.usdTry ? `${macroData.usdTry.toFixed(2)} ₺` : '—'}
              </div>
              <div className="text-[11px] text-secondary">
                1Y Kur: {fmtSignedPct(macroData?.usdTry1yChangePct)} · TÜFE: {macroData?.cpiYoyPct !== null && macroData?.cpiYoyPct !== undefined ? `%${macroData.cpiYoyPct.toFixed(1)}` : '—'}
              </div>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="text-xs text-secondary" htmlFor="evds-nominal-input">
              Yıllık TL Getirin (%):
            </label>
            <input
              id="evds-nominal-input"
              type="text"
              inputMode="decimal"
              value={nominalInput}
              onChange={(e) => setNominalInput(e.target.value)}
              className="w-24 rounded-lg border border-border/70 bg-background px-2.5 py-1 font-mono text-xs text-foreground"
            />
            <button
              type="button"
              onClick={() => void handleRecalcPower()}
              className="btn-secondary !px-2.5 !py-1 !text-xs"
            >
              Hesapla
            </button>
          </div>

          {macroData?.purchasingPower ? (
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-xl border border-border/50 bg-background/40 p-2">
                <div className="text-[11px] text-secondary">Nominal TL</div>
                <div className="mt-0.5 font-mono text-sm font-bold text-foreground">
                  {fmtSignedPct(macroData.purchasingPower.nominalReturnPct)}
                </div>
              </div>
              <div className="rounded-xl border border-border/50 bg-background/40 p-2">
                <div className="text-[11px] text-secondary">Dolar Bazlı Net</div>
                <div
                  className={`mt-0.5 font-mono text-sm font-bold ${
                    (macroData.purchasingPower.usdBasedReturnPct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {fmtSignedPct(macroData.purchasingPower.usdBasedReturnPct)}
                </div>
              </div>
              <div className="rounded-xl border border-border/50 bg-background/40 p-2">
                <div className="text-[11px] text-secondary">TÜFE Reel Güç</div>
                <div
                  className={`mt-0.5 font-mono text-sm font-bold ${
                    macroData.purchasingPower.realTufeReturnPct === null
                      ? 'text-secondary'
                      : macroData.purchasingPower.realTufeReturnPct >= 0
                        ? 'text-emerald-400'
                        : 'text-rose-400'
                  }`}
                >
                  {fmtSignedPct(macroData.purchasingPower.realTufeReturnPct)}
                </div>
              </div>
            </div>
          ) : null}
        </Card>

        <Card padding="md">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h4 className="text-sm font-semibold text-foreground">Binance Spot Canlı Veri & Testnet Kilidi</h4>
              <p className="text-[11px] text-secondary">
                Kripto 5-SMA stratejisi birincil kaynağı · Mod:{' '}
                <strong className="text-foreground">
                  {binanceData?.testnet !== false ? 'Testnet Sanal Ortam' : 'Canlı Salt-Okunur'}
                </strong>
              </p>
            </div>
            <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
              Otomatik Emir Kapalı
            </span>
          </div>

          <div className="mt-3 space-y-2">
            {(binanceData?.tickers ?? []).map((t) => (
              <div
                key={t.symbol}
                className="flex items-center justify-between rounded-xl border border-border/50 bg-background/40 px-3 py-2 text-xs"
              >
                <div>
                  <span className="font-mono font-bold text-foreground">{t.symbol}</span>
                  <span className="ml-2 text-[11px] text-secondary">
                    Bid/Ask: {t.bid ? t.bid.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'} /{' '}
                    {t.ask ? t.ask.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'}
                    {t.spreadBps !== null ? ` (${t.spreadBps} bps)` : ''}
                  </span>
                </div>
                <div className="text-right font-mono">
                  <div className="font-semibold text-foreground">
                    {t.lastPrice ? `$${t.lastPrice.toLocaleString('en-US', { maximumFractionDigits: 2 })}` : '—'}
                  </div>
                  <div
                    className={`text-[11px] ${
                      (t.priceChangePct24h ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {fmtSignedPct(t.priceChangePct24h)} (24s)
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Row 3: Live TEFAS Benchmark Funds */}
      {!compact ? (
        <Card padding="md">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h4 className="text-sm font-semibold text-foreground">Canlı TEFAS Benchmark Fonları</h4>
              <p className="text-[11px] text-secondary">
                Global ETF sepetinin (BIL / GLD / QQQ / SPY / BIST) Türkiye banka & Midas TEFAS karşılıkları · 6 saat önbellek
              </p>
            </div>
            <div className="flex flex-wrap gap-1">
              {TEFAS_BUCKETS.map((b) => (
                <button
                  key={b.id}
                  type="button"
                  onClick={() => setBucket(b.id)}
                  className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition-colors ${
                    bucket === b.id
                      ? 'bg-primary/20 text-primary border border-primary/40'
                      : 'border border-border/60 bg-background/40 text-secondary hover:text-foreground'
                  }`}
                >
                  {b.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border/60 text-[11px] text-secondary">
                  <th className="py-1.5 pr-3">Kod</th>
                  <th className="py-1.5 pr-3">Fon Adı</th>
                  <th className="py-1.5 pr-3">Küresel Eşdeğer</th>
                  <th className="py-1.5 pr-3 text-right">Birim Fiyat</th>
                  <th className="py-1.5 pr-3 text-right">Günlük %</th>
                  <th className="py-1.5 pr-3 text-right">Fon Büyüklüğü</th>
                  <th className="py-1.5 text-right">Kaynak</th>
                </tr>
              </thead>
              <tbody>
                {filteredFunds.map((f) => (
                  <tr key={f.code} className="border-b border-border/30">
                    <td className="py-2 pr-3 font-mono font-bold text-foreground">{f.code}</td>
                    <td className="py-2 pr-3 text-foreground">{f.title}</td>
                    <td className="py-2 pr-3 font-mono text-[11px] text-secondary">{f.globalProxy || '—'}</td>
                    <td className="py-2 pr-3 text-right font-mono text-foreground">{fmtTry(f.priceTry, 4)}</td>
                    <td
                      className={`py-2 pr-3 text-right font-mono font-semibold ${
                        (f.dailyReturnPct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {fmtSignedPct(f.dailyReturnPct)}
                    </td>
                    <td className="py-2 pr-3 text-right font-mono text-secondary">{fmtCompactTry(f.fundSizeTry)}</td>
                    <td className="py-2 text-right text-[11px] text-secondary">
                      {f.source === 'tefas_live'
                        ? 'TEFAS Canlı'
                        : f.source === 'tefas_cached'
                          ? 'Önbellek'
                          : 'Katalog Yedeği'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}
    </section>
  );
};
