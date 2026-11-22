import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { Check, ClipboardCopy, Eye, Lock, Send } from 'lucide-react';
import {
  bridgesApi,
  type AdapterPreviewOrder,
  type AdapterPreviewResponse,
  type BrokerAdaptersResponse,
} from '../../api/bridges';
import { Badge, Button, ConfirmDialog, SectionCard } from '../common';

const STRATEGY_CHOICES = [
  { key: 'meta_a', label: 'Meta-Portföy A v2 (ABD ETF Şampiyonu)' },
  { key: 'v3_trp', label: 'Çok Temkinli Kalkan (v3 Risk Paritesi)' },
  { key: 'balanced', label: 'Dengeli Kalkan (%50 / %50 Harman)' },
  { key: 'paa', label: 'PAA Çöküş Kalkanı' },
  { key: 'crypto_5sma', label: 'Kripto 5-SMA Trend (BTC / ETH)' },
];

const BROKER_CHOICES = [
  { id: 'alpaca', label: 'Alpaca ABD Paper' },
  { id: 'binance', label: 'Binance Spot Testnet' },
  { id: 'algolab', label: 'AlgoLab BIST (Salt-Okunur)' },
  { id: 'ibkr', label: 'IBKR Paper 7497' },
];

export const BrokerAdaptersPanel: React.FC = () => {
  const [adaptersData, setAdaptersData] = useState<BrokerAdaptersResponse | null>(null);
  const [selectedBroker, setSelectedBroker] = useState<string>('alpaca');
  const [selectedStrategy, setSelectedStrategy] = useState<string>('meta_a');
  const [capitalInput, setCapitalInput] = useState<string>('10000');
  const [preview, setPreview] = useState<AdapterPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [pendingOrder, setPendingOrder] = useState<AdapterPreviewOrder | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const loadAdapters = useCallback(async () => {
    try {
      const data = await bridgesApi.getAdapters();
      setAdaptersData(data);
    } catch {
      // silent fail-open on status card
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadAdapters();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadAdapters]);

  const handlePreview = async () => {
    setPreviewLoading(true);
    setFeedback(null);
    const cap = Number.parseFloat(capitalInput.replace(',', '.'));
    try {
      const res = await bridgesApi.previewAdapterPlan({
        brokerId: selectedBroker,
        strategyKey: selectedStrategy,
        capital: Number.isFinite(cap) && cap > 0 ? cap : undefined,
      });
      setPreview(res);
      void loadAdapters();
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : 'Emir önizlemesi hesaplanamadı.');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleCopyList = async () => {
    if (!preview?.copyText) return;
    try {
      await navigator.clipboard.writeText(preview.copyText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setFeedback(preview.copyText);
    }
  };

  const confirmSubmitSandboxOrder = async () => {
    if (!pendingOrder || !preview) return;
    setSubmitting(true);
    setFeedback(null);
    try {
      const quoteAmt = Math.abs(
        pendingOrder.notionalUsdt ?? pendingOrder.deltaNotional ?? pendingOrder.targetNotional ?? 0,
      );
      await bridgesApi.submitAdapterPaperOrder(preview.brokerId, {
        symbol: pendingOrder.symbol,
        side: pendingOrder.side,
        quantity: pendingOrder.quantity,
        quoteOrderQty: quoteAmt > 0 ? quoteAmt : undefined,
        confirmed: true,
        testOnly: true,
      });
      setFeedback(`${pendingOrder.symbol} için sanal/test emri doğrulandı ve denetim günlüğüne kaydedildi.`);
      void loadAdapters();
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : 'Sanal emir reddedildi (güvenlik kilidi aktif olabilir).');
    } finally {
      setSubmitting(false);
      setPendingOrder(null);
    }
  };

  const canSendSandbox =
    preview && (preview.brokerId === 'alpaca' || preview.brokerId === 'binance') && preview.sandbox && !preview.readOnlyEnforced;

  return (
    <SectionCard
      title="Aracı Kurum Bağlantıları & Emir Önizleme"
      subtitle="Birleşik BrokerAdapter mimarisi · Tüm canlı işlemler çift kilitli · Denetim günlüğü aktif"
    >
      {/* 5 Adapter Status Cards */}
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-5">
        {(adaptersData?.adapters ?? []).map((item) => (
          <div
            key={item.brokerId}
            className="rounded-xl border border-border/60 bg-background/45 p-3 text-xs"
          >
            <div className="flex items-start justify-between gap-2">
              <span className="font-semibold text-foreground">{item.displayName}</span>
              <Badge variant={item.configured ? 'success' : item.readOnlyEnforced ? 'warning' : 'info'}>
                {item.modeLabel}
              </Badge>
            </div>
            <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-secondary-text">
              <Lock className="h-3 w-3 shrink-0" />
              <span>{item.readOnlyEnforced ? 'Salt-Okunur Kilitli' : item.sandbox ? 'Sanal Sandbox' : 'Özel Onaylı'}</span>
            </div>
            {item.note ? <p className="mt-1.5 text-[11px] leading-snug text-secondary-text">{item.note}</p> : null}
          </div>
        ))}
      </div>

      {/* Preview Controls */}
      <div className="mt-4 flex flex-wrap items-end gap-2.5 rounded-xl border border-border/50 bg-background/40 p-3">
        <div className="min-w-[180px] flex-1">
          <label className="mb-1 block text-[11px] text-secondary-text" htmlFor="adapter-broker-select">
            Hedef Aracı Kurum
          </label>
          <select
            id="adapter-broker-select"
            value={selectedBroker}
            onChange={(e) => setSelectedBroker(e.target.value)}
            className="input-surface h-9 w-full rounded-lg border px-2.5 text-xs"
          >
            {BROKER_CHOICES.map((b) => (
              <option key={b.id} value={b.id}>
                {b.label}
              </option>
            ))}
          </select>
        </div>

        <div className="min-w-[220px] flex-1">
          <label className="mb-1 block text-[11px] text-secondary-text" htmlFor="adapter-strategy-select">
            Strateji Sepeti
          </label>
          <select
            id="adapter-strategy-select"
            value={selectedStrategy}
            onChange={(e) => setSelectedStrategy(e.target.value)}
            className="input-surface h-9 w-full rounded-lg border px-2.5 text-xs"
          >
            {STRATEGY_CHOICES.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </div>

        <div className="w-32">
          <label className="mb-1 block text-[11px] text-secondary-text" htmlFor="adapter-capital-input">
            Sermaye Tutarı
          </label>
          <input
            id="adapter-capital-input"
            type="text"
            inputMode="decimal"
            value={capitalInput}
            onChange={(e) => setCapitalInput(e.target.value)}
            className="input-surface h-9 w-full rounded-lg border px-2.5 font-mono text-xs"
          />
        </div>

        <Button variant="primary" size="sm" onClick={() => void handlePreview()} disabled={previewLoading}>
          <Eye className="mr-1.5 h-3.5 w-3.5" />
          {previewLoading ? 'Hesaplanıyor...' : 'Emir Planını Hesapla (Sadece Önizle)'}
        </Button>
      </div>

      {feedback ? (
        <div className="mt-3 rounded-xl border border-sky-500/40 bg-sky-500/10 px-3 py-2 text-xs text-foreground">
          {feedback}
        </div>
      ) : null}

      {/* Preview Table */}
      {preview ? (
        <div className="mt-3 space-y-2 rounded-xl border border-border/60 bg-background/50 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <div>
              <strong className="text-foreground">Önizleme: {preview.brokerId.toUpperCase()}</strong>
              <span className="ml-2 text-secondary-text">
                Sermaye: {preview.capital.toLocaleString('tr-TR')} {preview.currency} · {preview.orders.length} kalem
              </span>
            </div>
            <Button variant="secondary" size="sm" onClick={() => void handleCopyList()}>
              {copied ? <Check className="mr-1 h-3.5 w-3.5 text-emerald-400" /> : <ClipboardCopy className="mr-1 h-3.5 w-3.5" />}
              {copied ? 'Kopyalandı' : 'Midas / Kurum İçin Kopyala'}
            </Button>
          </div>

          {preview.orders.length === 0 ? (
            <p className="text-xs text-secondary-text">Mevcut dağılım zaten hedef sepete uygun — ek işlem gerekmiyor.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border/60 text-[11px] text-secondary-text">
                    <th className="py-1.5 pr-3">Varlık</th>
                    <th className="py-1.5 pr-3">Yön</th>
                    <th className="py-1.5 pr-3 text-right">Hedef %</th>
                    <th className="py-1.5 pr-3 text-right">Tutar</th>
                    <th className="py-1.5 text-right">İşlem</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.orders.map((ord) => {
                    const amount = ord.notionalUsdt ?? ord.deltaNotional ?? ord.targetNotional ?? 0;
                    return (
                      <tr key={`${ord.symbol}-${ord.side}`} className="border-b border-border/30">
                        <td className="py-2 pr-3 font-mono font-semibold text-foreground">{ord.symbol}</td>
                        <td className="py-2 pr-3">
                          <Badge variant={ord.side.toUpperCase() === 'BUY' ? 'success' : 'warning'}>{ord.side}</Badge>
                        </td>
                        <td className="py-2 pr-3 text-right font-mono text-secondary-text">
                          {ord.targetWeightPct != null ? `%${ord.targetWeightPct.toFixed(1)}` : '—'}
                        </td>
                        <td className="py-2 pr-3 text-right font-mono text-foreground">
                          {Math.abs(amount).toLocaleString('tr-TR', { maximumFractionDigits: 2 })} {ord.currency || preview.currency}
                        </td>
                        <td className="py-2 text-right">
                          {canSendSandbox ? (
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => setPendingOrder(ord)}
                            >
                              <Send className="mr-1 h-3 w-3" />
                              Sanal Onay
                            </Button>
                          ) : (
                            <span className="text-[11px] text-secondary-text">Sadece Plan (Salt-Okunur)</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      <ConfirmDialog
        isOpen={pendingOrder !== null}
        title="Sanal / Testnet Emir Doğrulama Onayı"
        message={
          pendingOrder
            ? `${pendingOrder.symbol} için ${pendingOrder.side} emrini sanal/test ortamında (${preview?.brokerId.toUpperCase()}) doğrulamak istiyor musun? Gerçek para hesabı kullanılmaz.`
            : ''
        }
        confirmText={submitting ? 'Doğrulanıyor...' : 'Evet, Sanal Test Emrini Gönder'}
        cancelText="İptal"
        confirmDisabled={submitting}
        cancelDisabled={submitting}
        onConfirm={() => void confirmSubmitSandboxOrder()}
        onCancel={() => setPendingOrder(null)}
      />
    </SectionCard>
  );
};
