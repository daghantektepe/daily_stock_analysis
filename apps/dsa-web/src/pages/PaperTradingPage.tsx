import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { ExternalLink, RefreshCw, ShieldAlert, TrendingUp } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  paperTradingApi,
  type KapAlertItem,
  type PaperPositionItem,
  type PaperTradeItem,
  type PaperTradingSummaryResponse,
} from '../api/paperTrading';
import { ApiErrorAlert, AppPage, Badge, Button, Card, EmptyState, PageHeader, SectionCard, StatCard } from '../components/common';

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
    return <Badge variant="warning" glow>⚠️ SÖYLENTİ ({item.source_count} kaynak)</Badge>;
  }
  if (item.kind === 'news') {
    return <Badge variant="info" glow>📰 ÇOK KAYNAKLI HABER ({item.source_count} kaynak)</Badge>;
  }
  return <Badge variant="success">🔔 RESMÎ KAP</Badge>;
}

const PaperTradingPage: React.FC = () => {
  const [summary, setSummary] = useState<PaperTradingSummaryResponse | null>(null);
  const [trades, setTrades] = useState<PaperTradeItem[]>([]);
  const [kapAlerts, setKapAlerts] = useState<KapAlertItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<ParsedApiError | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryRes, tradesRes, alertsRes] = await Promise.all([
        paperTradingApi.getSummary(true, true),
        paperTradingApi.listTrades(100),
        paperTradingApi.listKapAlerts(30, true),
      ]);
      setSummary(summaryRes);
      setTrades(tradesRes.items || []);
      setKapAlerts(alertsRes.items || []);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

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
        description="Karar sinyallerinin sanal işlem defteri, ATR bazlı zarar kes / kâr al takibi, BIST 100 & USD/TRY kıyasları ve canlı KAP / çok kaynaklı haber akışı."
        actions={(
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void loadAll()}
            disabled={loading}
          >
            <RefreshCw className={`mr-1.5 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Yenile
          </Button>
        )}
      />

      {error ? <ApiErrorAlert error={error} /> : null}

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
          title="BIST 100 ve Dolar (USD/TRY) Kıyaslaması"
          subtitle="Gölge Portföy & Reel Getiri"
        >
          {benchmarks.length === 0 ? (
            <EmptyState
              title="Kıyas verisi henüz oluşmadı"
              description="Borsa İstanbul (.IS) sanal işlemleri gerçekleştikçe BIST 100 gölge portföyü ve USD getirisi burada hesaplanır."
            />
          ) : (
            <div className="space-y-3">
              {benchmarks.map(([market, bm]) => (
                <Card key={market} variant="bordered" padding="sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <TrendingUp className="h-4 w-4 text-primary" />
                      <span className="text-sm font-semibold text-foreground">
                        {bm.benchmark_name} ({bm.benchmark}) Kıyaslaması
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

      {/* Open Positions with ATR Risk Management */}
      <SectionCard
        title="Açık Pozisyonlar ve ATR Risk Seviyeleri"
        subtitle="Volatilite & Zarar Kes / Kâr Al"
      >
        {(summary?.positions?.length ?? 0) === 0 ? (
          <EmptyState
            title="Açık sanal pozisyon bulunmuyor"
            description="Yeni bir AL (buy/add) sinyali oluştuğunda ATR bazlı pozisyon büyüklüğü ve zarar kes seviyeleriyle burada listelenir."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border/60 text-secondary-text">
                  <th className="pb-2 pr-3 font-medium">Hisse</th>
                  <th className="pb-2 px-3 font-medium text-right">Adet</th>
                  <th className="pb-2 px-3 font-medium text-right">Maliyet</th>
                  <th className="pb-2 px-3 font-medium text-right">Son Fiyat</th>
                  <th className="pb-2 px-3 font-medium text-right">Zarar Kes (ZK)</th>
                  <th className="pb-2 px-3 font-medium text-right">Kâr Al (KA)</th>
                  <th className="pb-2 px-3 font-medium text-right">ATR (14g)</th>
                  <th className="pb-2 px-3 font-medium text-right">Maks. Risk</th>
                  <th className="pb-2 pl-3 font-medium text-right">Gerçekleşmeyen K/Z</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {summary?.positions.map((pos: PaperPositionItem) => (
                  <tr key={pos.stock_code} className="hover:bg-hover/40">
                    <td className="py-2.5 pr-3">
                      <div className="font-semibold text-foreground">{pos.stock_code}</div>
                      {pos.stock_name ? <div className="text-[11px] text-secondary-text">{pos.stock_name}</div> : null}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-foreground">{pos.quantity}</td>
                    <td className="py-2.5 px-3 text-right font-mono text-foreground">
                      {fmtNumber(pos.avg_cost)} {pos.currency}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-foreground">
                      {pos.last_close != null ? `${fmtNumber(pos.last_close)} ${pos.currency}` : 'Maliyette'}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-rose-400">
                      {fmtNumber(pos.stop_loss)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-emerald-400">
                      {fmtNumber(pos.take_profit)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-secondary-text">
                      {pos.atr_pct != null ? `%${pos.atr_pct.toFixed(1)}` : '--'}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-secondary-text">
                      {pos.max_loss_amount != null ? `${fmtNumber(pos.max_loss_amount)} ${pos.currency}` : '--'}
                    </td>
                    <td className="py-2.5 pl-3 text-right font-mono">
                      <span className={pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                        {fmtNumber(pos.unrealized_pnl)} ({fmtPct(pos.unrealized_pnl_pct)})
                      </span>
                    </td>
                  </tr>
                ))}
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
    </AppPage>
  );
};

export default PaperTradingPage;
