import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  ExternalLink,
  Pencil,
  Plus,
  RefreshCw,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  paperTradingApi,
  type KapAlertItem,
  type PaperEquityPoint,
  type PaperManualOrderPayload,
  type PaperPositionItem,
  type PaperTradeItem,
  type PaperTradingSummaryResponse,
} from '../api/paperTrading';
import {
  ApiErrorAlert,
  AppPage,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  PageHeader,
  SectionCard,
  StatCard,
} from '../components/common';

function fmtNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return '--';
  return value.toLocaleString('tr-TR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtPct(value: number | null | undefined, signed = true): string {
  if (value == null || Number.isNaN(value)) return '--';
  const sign = signed && value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

function actionBadge(action: string) {
  const norm = (action || '').toLowerCase();
  switch (norm) {
    case 'buy':
      return <Badge variant="success">AL (Buy)</Badge>;
    case 'add':
      return <Badge variant="success">EKLE (Add)</Badge>;
    case 'reduce':
      return <Badge variant="warning">AZALT (Reduce)</Badge>;
    case 'sell':
      return <Badge variant="danger">SAT (Sell)</Badge>;
    case 'stop_loss':
      return <Badge variant="danger" glow>ZARAR KES (Stop)</Badge>;
    case 'take_profit':
      return <Badge variant="success" glow>KÂR AL (Target)</Badge>;
    default:
      return <Badge variant="default">{action}</Badge>;
  }
}

function alertKindBadge(item: KapAlertItem) {
  if (item.kind === 'rumor') {
    return <Badge variant="warning" glow>SÖYLENTİ ({item.source_count} kaynak)</Badge>;
  }
  if (item.kind === 'news') {
    return <Badge variant="info" glow>ÇOK KAYNAKLI HABER ({item.source_count} kaynak)</Badge>;
  }
  return <Badge variant="success">RESMÎ KAP</Badge>;
}

function computeStopRangeProgress(pos: PaperPositionItem): number | null {
  const sl = pos.stop_loss;
  const tp = pos.take_profit;
  const price = pos.last_close ?? pos.avg_cost;
  if (sl == null || tp == null || price == null || tp <= sl) {
    return null;
  }
  const pct = ((price - sl) / (tp - sl)) * 100;
  return Math.max(0, Math.min(100, pct));
}

type PendingTradeConfirm = {
  title: string;
  message: string;
  payload: PaperManualOrderPayload;
};

const PaperTradingPage: React.FC = () => {
  const [summary, setSummary] = useState<PaperTradingSummaryResponse | null>(null);
  const [trades, setTrades] = useState<PaperTradeItem[]>([]);
  const [kapAlerts, setKapAlerts] = useState<KapAlertItem[]>([]);
  const [equityPoints, setEquityPoints] = useState<PaperEquityPoint[]>([]);
  const [equityCurrencies, setEquityCurrencies] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [livePolling, setLivePolling] = useState<boolean>(true);

  // Quick manual order composer
  const [showOrderBox, setShowOrderBox] = useState<boolean>(false);
  const [orderCode, setOrderCode] = useState<string>('');
  const [orderQty, setOrderQty] = useState<string>('');
  const [orderPrice, setOrderPrice] = useState<string>('');
  const [orderStopLoss, setOrderStopLoss] = useState<string>('');
  const [orderTakeProfit, setOrderTakeProfit] = useState<string>('');

  // Inline ZK / KA editor per stock_code
  const [editingStopsCode, setEditingStopsCode] = useState<string | null>(null);
  const [editSlValue, setEditSlValue] = useState<string>('');
  const [editTpValue, setEditTpValue] = useState<string>('');
  const [savingAction, setSavingAction] = useState<boolean>(false);

  // ConfirmDialog state
  const [pendingConfirm, setPendingConfirm] = useState<PendingTradeConfirm | null>(null);

  const loadAll = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }
    setError(null);
    try {
      const [summaryRes, tradesRes, alertsRes, equityRes] = await Promise.all([
        paperTradingApi.getSummary(true, true),
        paperTradingApi.listTrades(100),
        paperTradingApi.listKapAlerts(30, true),
        paperTradingApi.getEquityCurve(90).catch(() => ({ points: [], currencies: [] })),
      ]);
      setSummary(summaryRes);
      setTrades(tradesRes.items || []);
      setKapAlerts(alertsRes.items || []);
      setEquityPoints(equityRes.points || []);
      setEquityCurrencies(equityRes.currencies || []);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!livePolling) return undefined;
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        void loadAll(true);
      }
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [livePolling, loadAll]);

  const executeConfirmedOrder = async () => {
    if (!pendingConfirm) return;
    setSavingAction(true);
    setError(null);
    setActionMsg(null);
    try {
      const res = await paperTradingApi.placeOrder(pendingConfirm.payload);
      setActionMsg(
        `Sanal emir işlendi: ${res.action.toUpperCase()} ${res.stock_code} x${res.quantity} @ ${fmtNumber(res.price)}`,
      );
      setPendingConfirm(null);
      setShowOrderBox(false);
      setOrderCode('');
      setOrderQty('');
      setOrderPrice('');
      setOrderStopLoss('');
      setOrderTakeProfit('');
      await loadAll(true);
    } catch (err) {
      setError(getParsedApiError(err));
      setPendingConfirm(null);
    } finally {
      setSavingAction(false);
    }
  };

  const handleOpenManualOrderConfirm = (e: React.FormEvent) => {
    e.preventDefault();
    const code = orderCode.trim().toUpperCase();
    if (!code) return;
    const qty = orderQty.trim() ? Number(orderQty) : undefined;
    const price = orderPrice.trim() ? Number(orderPrice) : undefined;
    const sl = orderStopLoss.trim() ? Number(orderStopLoss) : undefined;
    const tp = orderTakeProfit.trim() ? Number(orderTakeProfit) : undefined;

    setPendingConfirm({
      title: `Sanal AL Emri Onayı: ${code}`,
      message: `${code} için sanal AL emri girilsin mi?${qty ? ` Adet: ${qty}.` : ' Adet ATR risk planına göre otomatik hesaplanacak.'}${price ? ` Fiyat: ${price}.` : ' Fiyat son kapanışa göre alınacak.'}`,
      payload: {
        stock_code: code,
        action: 'buy',
        quantity: qty,
        price,
        stop_loss: sl,
        take_profit: tp,
      },
    });
  };

  const handleSaveStops = async (stockCode: string) => {
    setSavingAction(true);
    setError(null);
    setActionMsg(null);
    try {
      const sl = editSlValue.trim() ? Number(editSlValue) : undefined;
      const tp = editTpValue.trim() ? Number(editTpValue) : undefined;
      await paperTradingApi.updatePositionStops(stockCode, {
        stop_loss: sl,
        take_profit: tp,
      });
      setActionMsg(`${stockCode} için Zarar Kes / Kâr Al hedefleri güncellendi.`);
      setEditingStopsCode(null);
      await loadAll(true);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSavingAction(false);
    }
  };

  const benchmarks = Object.entries(summary?.benchmarks || {});
  const currencies = Object.entries(summary?.totals_by_currency || {});
  const outcomes = summary?.signal_outcomes;
  const horizonLabels: Record<string, string> = {
    '1d': '1 Gün',
    '3d': '3 Gün',
    '5d': '5 Gün',
    '10d': '10 Gün',
  };

  return (
    <AppPage>
      <PageHeader
        title="Sanal İşlem, Kıyaslar ve KAP / Haber Uyarıları"
        description="Karar sinyallerinin sanal işlem defteri, ATR bazlı zarar kes / kâr al takibi, BIST 100 & SPY kıyasları ve canlı KAP / haber akışı."
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setLivePolling((prev) => !prev)}
              className={`inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs transition ${
                livePolling
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                  : 'border-border bg-card/70 text-secondary-text'
              }`}
              title="Görünür sekmede 30 saniyede bir otomatik güncelleme"
            >
              <Activity className="h-3.5 w-3.5" />
              {livePolling ? 'Canlı 30s Açık' : 'Canlı 30s Kapalı'}
            </button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowOrderBox((prev) => !prev)}
            >
              <Plus className="mr-1.5 h-4 w-4" />
              Yeni Sanal Emir
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void loadAll()}
              disabled={loading}
            >
              <RefreshCw className={`mr-1.5 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
          </div>
        )}
      />

      {error ? <ApiErrorAlert error={error} /> : null}
      {actionMsg ? (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-xs text-emerald-200 flex items-center justify-between">
          <span>{actionMsg}</span>
          <button type="button" onClick={() => setActionMsg(null)} aria-label="Kapat">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ) : null}

      {/* Quick Manual Order Box */}
      {showOrderBox ? (
        <SectionCard title="Yeni Sanal İşlem Emri (Simülasyon)" subtitle="Gerçek Emir Gönderilmez">
          <form onSubmit={handleOpenManualOrderConfirm} className="grid grid-cols-1 gap-3 sm:grid-cols-6 items-end">
            <div>
              <label className="mb-1 block text-[11px] text-secondary-text">Hisse Kodu *</label>
              <input
                type="text"
                required
                value={orderCode}
                onChange={(e) => setOrderCode(e.target.value)}
                placeholder="NVDA, THYAO.IS..."
                className="input-surface h-9 w-full rounded-lg border border-border bg-base/50 px-3 text-xs uppercase text-foreground"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-secondary-text">Adet (Opsiyonel)</label>
              <input
                type="number"
                step="any"
                min="0.01"
                value={orderQty}
                onChange={(e) => setOrderQty(e.target.value)}
                placeholder="ATR otomatik"
                className="input-surface h-9 w-full rounded-lg border border-border bg-base/50 px-3 text-xs text-foreground"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-secondary-text">Fiyat (Opsiyonel)</label>
              <input
                type="number"
                step="any"
                min="0.01"
                value={orderPrice}
                onChange={(e) => setOrderPrice(e.target.value)}
                placeholder="Son kapanış"
                className="input-surface h-9 w-full rounded-lg border border-border bg-base/50 px-3 text-xs text-foreground"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-secondary-text">Zarar Kes (ZK)</label>
              <input
                type="number"
                step="any"
                min="0.01"
                value={orderStopLoss}
                onChange={(e) => setOrderStopLoss(e.target.value)}
                placeholder="ATR 2x"
                className="input-surface h-9 w-full rounded-lg border border-border bg-base/50 px-3 text-xs text-foreground"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-secondary-text">Kâr Al (KA)</label>
              <input
                type="number"
                step="any"
                min="0.01"
                value={orderTakeProfit}
                onChange={(e) => setOrderTakeProfit(e.target.value)}
                placeholder="ATR 3x"
                className="input-surface h-9 w-full rounded-lg border border-border bg-base/50 px-3 text-xs text-foreground"
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" size="sm" variant="primary" className="flex-1">
                Sanal AL
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => setShowOrderBox(false)}>
                Vazgeç
              </Button>
            </div>
          </form>
        </SectionCard>
      ) : null}

      {/* Top KPI Cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          label="Sanal İşlem Durumu"
          value={summary?.enabled ? 'Aktif' : 'Pasif'}
          hint={`Bütçe: ${fmtNumber(summary?.position_size, 0)} | Risk: %${fmtNumber(summary?.risk_pct, 1)}`}
        />
        <StatCard
          label="Toplam / Açık İşlem"
          value={`${summary?.trade_count ?? 0} / ${summary?.open_position_count ?? 0}`}
          hint={`Kapanan: ${summary?.closed_trade_count ?? 0}`}
        />
        <StatCard
          label="Kazanma Oranı"
          value={summary?.win_rate_pct != null ? `%${summary.win_rate_pct.toFixed(0)}` : '--'}
          hint={`ZK: ${summary?.stop_loss_count ?? 0} | KA: ${summary?.take_profit_count ?? 0}`}
        />
        <StatCard
          label="Sinyal İsabeti (±%2)"
          value={outcomes?.hit_rate_pct != null ? `%${outcomes.hit_rate_pct.toFixed(0)}` : '--'}
          hint={`${outcomes?.completed ?? 0} değerlendirme (${outcomes?.hit ?? 0} doğru / ${outcomes?.miss ?? 0} yanlış)`}
        />
        <StatCard
          label="KAP & Haber Uyarıları"
          value={`${kapAlerts.length}`}
          hint="Son önemli bildirim, teyitli haber ve söylentiler"
        />
      </div>

      {/* Equity Curve Chart */}
      {equityPoints.length > 0 ? (
        <SectionCard
          title="Sanal Portföy Getiri & K/Z Eğrisi (Son 90 Gün)"
          subtitle={equityCurrencies.length > 0 ? `Birimler: ${equityCurrencies.join(', ')}` : 'Simülasyon Performansı'}
        >
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={equityPoints} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="paperReturnGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.14)" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: '#94a3b8' }}
                  tickFormatter={(val: string) => (typeof val === 'string' ? val.slice(5) : '')}
                  minTickGap={24}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: '#94a3b8' }}
                  tickFormatter={(v: number) => `${v}%`}
                  width={48}
                />
                <ReferenceLine y={0} stroke="rgba(148,163,184,0.4)" strokeDasharray="3 3" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderColor: 'rgba(148,163,184,0.25)',
                    borderRadius: '10px',
                    fontSize: '12px',
                  }}
                  formatter={(val, name) => {
                    const num = typeof val === 'number' ? val : Number(val);
                    if (name === 'Getiri %') return [`${Number.isFinite(num) ? num.toFixed(2) : '--'}%`, name];
                    return [fmtNumber(num), name];
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="return_pct"
                  name="Getiri %"
                  stroke="#10b981"
                  strokeWidth={2}
                  fill="url(#paperReturnGrad)"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      ) : null}

      {/* Currency Totals & Benchmark Comparison */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SectionCard
          title="Para Birimi Bazında Kâr / Zarar"
          subtitle="Sanal Muhasebe"
        >
          {currencies.length === 0 ? (
            <EmptyState
              title="Henüz sanal işlem kaydı yok"
              description="PAPER_TRADING_ENABLED=true iken yeni analiz sinyalleri otomatik olarak sanal deftere işlenir."
            />
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {currencies.map(([currency, totals]) => (
                <Card key={currency} variant="bordered" padding="sm">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-foreground">{currency} Portföyü</span>
                    <Badge variant={totals.realized_pnl + totals.unrealized_pnl >= 0 ? 'success' : 'danger'}>
                      Toplam: {fmtNumber(totals.realized_pnl + totals.unrealized_pnl)} {currency}
                    </Badge>
                  </div>
                  <div className="mt-3 space-y-1.5 text-xs text-secondary-text">
                    <div className="flex justify-between">
                      <span>Açık Maliyet:</span>
                      <span className="font-mono text-foreground">{fmtNumber(totals.cost)} {currency}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Piyasa Değeri:</span>
                      <span className="font-mono text-foreground">{fmtNumber(totals.market_value)} {currency}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Gerçekleşen K/Z:</span>
                      <span className={`font-mono ${totals.realized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {fmtNumber(totals.realized_pnl)} {currency}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Gerçekleşmeyen K/Z:</span>
                      <span className={`font-mono ${totals.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {fmtNumber(totals.unrealized_pnl)} {currency}
                      </span>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard
          title="Endeks & Dolar Kıyaslaması"
          subtitle="BIST 100 / SPY / USD Bazlı"
        >
          {benchmarks.length === 0 ? (
            <EmptyState
              title="Kıyas verisi bekleniyor"
              description="İşlemler biriktikçe strateji getirisi endeks ve USD bazında karşılaştırılır."
            />
          ) : (
            <div className="space-y-3">
              {benchmarks.map(([marketKey, bm]) => (
                <Card key={marketKey} variant="bordered" padding="sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <TrendingUp className="h-4 w-4 text-primary" />
                      <span className="text-sm font-semibold text-foreground">
                        {marketKey.toUpperCase()} vs {bm.benchmark_name}
                      </span>
                    </div>
                    <Badge variant={(bm.excess_return_pct ?? 0) >= 0 ? 'success' : 'danger'} glow>
                      Endekse Fark: {fmtPct(bm.excess_return_pct)}
                    </Badge>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
                    <div>
                      <p className="text-secondary-text">Strateji Getirisi ({bm.currency})</p>
                      <p className={`mt-0.5 font-mono text-sm font-semibold ${bm.strategy_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {fmtPct(bm.strategy_return_pct)}
                      </p>
                    </div>
                    <div>
                      <p className="text-secondary-text">{bm.benchmark_name} Gölge Getirisi</p>
                      <p className="mt-0.5 font-mono text-sm font-semibold text-foreground">
                        {fmtPct(bm.benchmark_return_pct)}
                      </p>
                    </div>
                    <div>
                      <p className="text-secondary-text">Dolar Bazında Getiri (USD)</p>
                      <p className={`mt-0.5 font-mono text-sm font-semibold ${(bm.usd_return_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {fmtPct(bm.usd_return_pct)}
                      </p>
                    </div>
                    <div>
                      <p className="text-secondary-text">USD/TRY Kur Değişimi</p>
                      <p className="mt-0.5 font-mono text-xs text-foreground">{fmtPct(bm.fx_change_pct)}</p>
                    </div>
                    <div>
                      <p className="text-secondary-text">Bağlanan Sermaye</p>
                      <p className="mt-0.5 font-mono text-xs text-foreground">
                        {fmtNumber(bm.capital_deployed)} {bm.currency}
                      </p>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}

          {outcomes && (outcomes.completed ?? 0) > 0 ? (
            <div className="mt-3 rounded-xl border border-border/60 bg-card/50 p-3 text-xs">
              <p className="font-semibold text-foreground">Ufuk Bazında Sinyal İsabeti (±%2 nötr bant)</p>
              <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {Object.entries(horizonLabels).map(([hKey, hLabel]) => {
                  const bucket = outcomes.by_horizon?.[hKey];
                  return (
                    <div key={hKey} className="rounded-lg border border-border/40 px-2.5 py-1.5">
                      <span className="text-secondary-text">{hLabel}</span>
                      <p className="mt-0.5 font-mono text-sm font-semibold text-foreground">
                        {bucket?.hit_rate_pct != null ? `%${bucket.hit_rate_pct.toFixed(0)}` : '--'}
                      </p>
                      <p className="text-[11px] text-secondary-text">
                        Ort: {fmtPct(bucket?.avg_stock_return_pct)} ({bucket?.hit ?? 0}/{(bucket?.hit ?? 0) + (bucket?.miss ?? 0)})
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}
        </SectionCard>
      </div>

      {/* Open Positions with ATR Risk Management + Interactive Controls */}
      <SectionCard
        title="Açık Pozisyonlar ve ATR Risk Seviyeleri"
        subtitle="ZK ← Fiyat → KA Takibi & Hızlı Kontrol"
      >
        {(summary?.positions?.length ?? 0) === 0 ? (
          <EmptyState
            title="Açık sanal pozisyon bulunmuyor"
            description="Yeni bir AL sinyali oluştuğunda veya üstten 'Yeni Sanal Emir' girdiğinizde pozisyon burada listelenir."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border/60 text-secondary-text">
                  <th className="pb-2 pr-3 font-medium">Hisse</th>
                  <th className="pb-2 px-3 font-medium text-right">Adet</th>
                  <th className="pb-2 px-3 font-medium text-right">Maliyet / Son Fiyat</th>
                  <th className="pb-2 px-3 font-medium min-w-[160px]">ZK ← Konum → KA</th>
                  <th className="pb-2 px-3 font-medium text-right">ATR / Maks. Risk</th>
                  <th className="pb-2 px-3 font-medium text-right">Gerçekleşmeyen K/Z</th>
                  <th className="pb-2 pl-3 font-medium text-right">İşlem</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {summary?.positions.map((pos: PaperPositionItem) => {
                  const progressPct = computeStopRangeProgress(pos);
                  const isEditing = editingStopsCode === pos.stock_code;
                  return (
                    <tr key={pos.stock_code} className="hover:bg-hover/40">
                      <td className="py-2.5 pr-3">
                        <div className="font-semibold text-foreground">{pos.stock_code}</div>
                        {pos.stock_name ? <div className="text-[11px] text-secondary-text">{pos.stock_name}</div> : null}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-foreground">{pos.quantity}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-foreground">
                        <div>{fmtNumber(pos.avg_cost)}</div>
                        <div className="text-[11px] text-secondary-text">
                          {pos.last_close != null ? `${fmtNumber(pos.last_close)} ${pos.currency || ''}` : 'Maliyette'}
                        </div>
                      </td>
                      <td className="py-2.5 px-3">
                        {isEditing ? (
                          <div className="flex flex-col gap-1">
                            <div className="flex items-center gap-1">
                              <input
                                type="number"
                                step="any"
                                value={editSlValue}
                                onChange={(e) => setEditSlValue(e.target.value)}
                                placeholder="ZK"
                                className="w-20 rounded border border-border bg-base/60 px-1.5 py-0.5 font-mono text-[11px] text-rose-300"
                              />
                              <input
                                type="number"
                                step="any"
                                value={editTpValue}
                                onChange={(e) => setEditTpValue(e.target.value)}
                                placeholder="KA"
                                className="w-20 rounded border border-border bg-base/60 px-1.5 py-0.5 font-mono text-[11px] text-emerald-300"
                              />
                            </div>
                            <div className="flex gap-1">
                              <button
                                type="button"
                                disabled={savingAction}
                                onClick={() => void handleSaveStops(pos.stock_code)}
                                className="rounded bg-primary/20 px-2 py-0.5 text-[10px] text-primary hover:bg-primary/30"
                              >
                                Kaydet
                              </button>
                              <button
                                type="button"
                                onClick={() => setEditingStopsCode(null)}
                                className="rounded bg-hover px-2 py-0.5 text-[10px] text-secondary-text"
                              >
                                İptal
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div>
                            <div className="flex justify-between font-mono text-[10px]">
                              <span className="text-rose-400">{fmtNumber(pos.stop_loss)}</span>
                              <span className="text-emerald-400">{fmtNumber(pos.take_profit)}</span>
                            </div>
                            <div className="relative mt-1 h-2 w-full overflow-hidden rounded-full bg-border/60">
                              {progressPct != null ? (
                                <div
                                  className="h-full rounded-full bg-gradient-to-r from-rose-500 via-sky-400 to-emerald-500"
                                  style={{ width: `${progressPct}%` }}
                                />
                              ) : null}
                            </div>
                          </div>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-secondary-text">
                        <div>{pos.atr_pct != null ? `%${pos.atr_pct.toFixed(1)}` : '--'}</div>
                        <div className="text-[11px]">
                          {pos.max_loss_amount != null ? `${fmtNumber(pos.max_loss_amount)} ${pos.currency || ''}` : '--'}
                        </div>
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono">
                        <span className={pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                          {fmtNumber(pos.unrealized_pnl)} ({fmtPct(pos.unrealized_pnl_pct)})
                        </span>
                      </td>
                      <td className="py-2.5 pl-3 text-right">
                        <div className="inline-flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => {
                              setEditingStopsCode(pos.stock_code);
                              setEditSlValue(pos.stop_loss != null ? String(pos.stop_loss) : '');
                              setEditTpValue(pos.take_profit != null ? String(pos.take_profit) : '');
                            }}
                            className="rounded border border-border/70 px-1.5 py-1 text-[11px] text-secondary-text hover:text-foreground"
                            title="ZK / KA Düzenle"
                          >
                            <Pencil className="h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setPendingConfirm({
                                title: `${pos.stock_code} Pozisyonunu Yarıla`,
                                message: `${pos.stock_code} açık pozisyonunun yaklaşık yarısı (${Math.floor(pos.quantity / 2) || pos.quantity} adet) sanal olarak satılsın mı?`,
                                payload: { stock_code: pos.stock_code, action: 'reduce' },
                              })
                            }
                            className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300 hover:bg-amber-500/20"
                          >
                            -%50
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setPendingConfirm({
                                title: `${pos.stock_code} Pozisyonunu Kapat`,
                                message: `${pos.stock_code} (${pos.quantity} adet) tamamen sanal olarak satılsın mı?`,
                                payload: { stock_code: pos.stock_code, action: 'sell' },
                              })
                            }
                            className="inline-flex items-center gap-1 rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-[11px] text-rose-300 hover:bg-rose-500/20"
                          >
                            <TrendingDown className="h-3 w-3" />
                            Kapat
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {/* KAP Disclosures, Multi-Source News & Rumor Alerts */}
      <SectionCard
        title="KAP Bildirimleri, Çok Kaynaklı Haberler ve Söylenti Uyarıları"
        subtitle="Canlı Bildirim & Haber Akışı"
      >
        {kapAlerts.length === 0 ? (
          <EmptyState
            title="Henüz KAP veya haber uyarısı yok"
            description="İzlenen BIST hisseleri için yeni önemli KAP bildirimi, çok kaynaklı haber veya söylenti tespit edildiğinde burada listelenir."
          />
        ) : (
          <div className="space-y-2.5">
            {kapAlerts.map((item, idx) => (
              <Card key={`${item.stock_code}-${item.index ?? item.story_key ?? idx}`} variant="bordered" padding="sm">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-bold text-primary">{item.stock_code}</span>
                    {alertKindBadge(item)}
                    {item.tag_labels_tr?.map((tagLabel) => (
                      <Badge key={tagLabel} variant="default">{tagLabel}</Badge>
                    ))}
                  </div>
                  <span className="text-[11px] text-secondary-text">{item.published_date}</span>
                </div>
                <p className="mt-1.5 text-sm font-medium text-foreground">{item.title}</p>
                {item.kind === 'rumor' ? (
                  <p className="mt-1 flex items-center gap-1.5 text-xs text-amber-400">
                    <ShieldAlert className="h-3.5 w-3.5 shrink-0" />
                    Resmî KAP teyidi yoktur; birden fazla yayında geçen kulis/iddia haberidir.
                  </p>
                ) : null}
                {item.details ? (
                  <p className="mt-1 text-xs text-secondary-text line-clamp-2">{item.details}</p>
                ) : null}
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-secondary-text">
                  <span>
                    Kaynaklar: <strong className="text-foreground">{(item.sources || []).join(', ') || 'KAP'}</strong>
                  </span>
                  {item.url ? (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      Kaynağı Aç <ExternalLink className="h-3 w-3" />
                    </a>
                  ) : null}
                </div>
              </Card>
            ))}
          </div>
        )}
      </SectionCard>

      {/* Recent Paper Trades History */}
      <SectionCard
        title="Sanal İşlem Geçmişi"
        subtitle="Gerçekleşen Emirler"
      >
        {trades.length === 0 ? (
          <EmptyState
            title="Henüz işlem gerçekleşmedi"
            description="Sanal işlem defterinde kayıtlı alım veya satım bulunmuyor."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border/60 text-secondary-text">
                  <th className="pb-2 pr-3 font-medium">Tarih</th>
                  <th className="pb-2 px-3 font-medium">Hisse</th>
                  <th className="pb-2 px-3 font-medium">İşlem Türü</th>
                  <th className="pb-2 px-3 font-medium text-right">Adet</th>
                  <th className="pb-2 px-3 font-medium text-right">Fiyat</th>
                  <th className="pb-2 px-3 font-medium text-right">Zarar Kes / Kâr Al</th>
                  <th className="pb-2 pl-3 font-medium text-right">Tutar</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {trades.map((trade) => (
                  <tr key={trade.id} className="hover:bg-hover/40">
                    <td className="py-2 pr-3 font-mono text-secondary-text">{trade.trade_date || '--'}</td>
                    <td className="py-2 px-3 font-semibold text-foreground">{trade.stock_code}</td>
                    <td className="py-2 px-3">{actionBadge(trade.action)}</td>
                    <td className="py-2 px-3 text-right font-mono text-foreground">{trade.quantity}</td>
                    <td className="py-2 px-3 text-right font-mono text-foreground">
                      {fmtNumber(trade.price)} {trade.currency}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-secondary-text">
                      {trade.stop_loss != null || trade.take_profit != null
                        ? `${fmtNumber(trade.stop_loss)} / ${fmtNumber(trade.take_profit)}`
                        : '--'}
                    </td>
                    <td className="py-2 pl-3 text-right font-mono text-foreground">
                      {fmtNumber(trade.quantity * trade.price)} {trade.currency}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <ConfirmDialog
        isOpen={pendingConfirm !== null}
        title={pendingConfirm?.title || 'Sanal Emir Onayı'}
        message={pendingConfirm?.message || ''}
        confirmText={savingAction ? 'Uygulanıyor...' : 'Evet, Sanal İşlemi Uygula'}
        cancelText="İptal"
        confirmDisabled={savingAction}
        cancelDisabled={savingAction}
        onConfirm={() => void executeConfirmedOrder()}
        onCancel={() => setPendingConfirm(null)}
      />
    </AppPage>
  );
};

export default PaperTradingPage;
