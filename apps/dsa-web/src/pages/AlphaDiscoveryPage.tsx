import type React from 'react';
import { useCallback, useState } from 'react';
import {
  BarChart3,
  Compass,
  ExternalLink,
  FileText,
  Play,
  RefreshCw,
  Sparkles,
  TrendingUp,
  Trophy,
  UserCheck,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  alphaApi,
  type BistCandidateItem,
  type CryptoTrendResponse,
  type Form4ClusterItem,
  type Form4StudyResponse,
  type KapContractItem,
  type PeadCandidateItem,
  type PeadStudyResponse,
  type UsQuantCandidateItem,
} from '../api/alpha';
import { analysisApi } from '../api/analysis';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  ApiErrorAlert,
  AppPage,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  InlineAlert,
  PageHeader,
  SectionCard,
  StatCard,
} from '../components/common';
import { TournamentTabPanel } from '../components/quant/TournamentTabPanel';

type DiscoverTab = 'tournament' | 'claude' | 'us' | 'form4' | 'pead' | 'bist';

function fmtPct(val?: number | null, digits = 1): string {
  if (val == null || Number.isNaN(val)) return '--';
  return `${val > 0 ? '+' : ''}${val.toFixed(digits)}%`;
}

function fmtUsd(val?: number | null): string {
  if (val == null || Number.isNaN(val)) return '--';
  if (Math.abs(val) >= 1_000_000) return `$${(val / 1_000_000).toFixed(2)}M`;
  if (Math.abs(val) >= 1_000) return `$${(val / 1_000).toFixed(0)}k`;
  return `$${val.toFixed(0)}`;
}

const AlphaDiscoveryPage: React.FC = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<DiscoverTab>('claude');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Claude Verification & Crypto Trend state
  const [cryptoData, setCryptoData] = useState<CryptoTrendResponse | null>(null);
  const [cryptoLoading, setCryptoLoading] = useState(false);

  const [form4Quarters, setForm4Quarters] = useState('2023q1..2026q3');
  const [form4StudyMinVal, setForm4StudyMinVal] = useState(50000);
  const [form4StudyLimit, setForm4StudyLimit] = useState(0);
  const [form4StudyRes, setForm4StudyRes] = useState<Form4StudyResponse | null>(null);
  const [form4StudyLoading, setForm4StudyLoading] = useState(false);

  const [peadUnbiasedUniv, setPeadUnbiasedUniv] = useState<'smid' | 'sp400' | 'sp600' | 'sp500'>('smid');
  const [peadUnbiasedSample, setPeadUnbiasedSample] = useState(400);
  const [peadUnbiasedRes, setPeadUnbiasedRes] = useState<PeadStudyResponse | null>(null);
  const [peadUnbiasedLoading, setPeadUnbiasedLoading] = useState(false);

  // US Quant state
  const [usTopN, setUsTopN] = useState(12);
  const [includePead, setIncludePead] = useState(true);
  const [includeForm4, setIncludeForm4] = useState(true);
  const [useSecXbrl, setUseSecXbrl] = useState(true);
  const [usItems, setUsItems] = useState<UsQuantCandidateItem[]>([]);
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);

  // Batch confirmation safety dialog
  const [batchConfirmOpen, setBatchConfirmOpen] = useState(false);
  const [batchRunning, setBatchRunning] = useState(false);

  // Form 4 state
  const [form4MinVal, setForm4MinVal] = useState(10000);
  const [form4Items, setForm4Items] = useState<Form4ClusterItem[]>([]);

  // PEAD + Event Study state
  const [peadUniverse, setPeadUniverse] = useState<'all' | 'midcap' | 'megacap'>('all');
  const [peadMaxDays, setPeadMaxDays] = useState(21);
  const [peadItems, setPeadItems] = useState<PeadCandidateItem[]>([]);
  const [studySymbolsInput, setStudySymbolsInput] = useState('NVDA, META, AMZN, AVGO, AXON');
  const [studyResult, setStudyResult] = useState<PeadStudyResponse | null>(null);
  const [studyLoading, setStudyLoading] = useState(false);

  // BIST + KAP state
  const [bistCandidates, setBistCandidates] = useState<BistCandidateItem[]>([]);
  const [bistScanned, setBistScanned] = useState<number>(0);
  const [kapContracts, setKapContracts] = useState<KapContractItem[]>([]);

  const goAnalyze = useCallback(
    (code: string, name?: string) => {
      navigate('/', {
        state: {
          stockCode: code,
          stockName: name || '',
          autoAnalyze: true,
          selectionSource: 'autocomplete',
        },
      });
    },
    [navigate]
  );

  const toggleSelect = useCallback((symbol: string) => {
    setSelectedSymbols((prev) =>
      prev.includes(symbol) ? prev.filter((s) => s !== symbol) : [...prev, symbol]
    );
  }, []);

  const runUsScreen = async () => {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const res = await alphaApi.runUsScreen({
        top_n: usTopN,
        include_pead: includePead,
        include_form4: includeForm4,
        use_sec_xbrl: useSecXbrl,
      });
      setUsItems(res.items || []);
      setSelectedSymbols((res.items || []).slice(0, 5).map((x) => x.symbol));
      setNotice(`ABD Yüksek Alfa taraması tamamlandı: ${res.count} aday bulundu.`);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const runForm4Live = async () => {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const res = await alphaApi.getForm4Live({
        count: 80,
        max_filings: 40,
        min_value: form4MinVal,
      });
      setForm4Items(res.items || []);
      setNotice(`Canlı SEC EDGAR Form 4 taraması tamamlandı: ${res.count} alım kümesi.`);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const runPeadScreen = async () => {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const res = await alphaApi.getPeadCandidates({
        universe: peadUniverse,
        max_days: peadMaxDays,
        min_score: 40,
        top_n: 15,
      });
      setPeadItems(res.items || []);
      if (res.items.length > 0) {
        setStudySymbolsInput(res.items.slice(0, 8).map((x) => x.symbol).join(', '));
      }
      setNotice(`PEAD 2.0 taraması tamamlandı: ${res.count} bilanço sürprizi.`);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const runPeadEventStudy = async () => {
    const syms = studySymbolsInput
      .split(',')
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (syms.length === 0) return;

    setStudyLoading(true);
    setError(null);
    try {
      const res = await alphaApi.runPeadStudy({
        symbols: syms,
        min_surprise_pct: 5.0,
        benchmark_symbol: 'SPY',
        estimated_slippage_pct: 0.25,
      });
      setStudyResult(res);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setStudyLoading(false);
    }
  };

  const runBistAndKap = async () => {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const [bistRes, kapRes] = await Promise.all([
        alphaApi.runBistScreen({ top_n: 10, min_score: 25, include_kap: true }),
        alphaApi.getKapContracts({ days_back: 7, min_score: 30, top_n: 15 }),
      ]);
      setBistCandidates(bistRes.candidates || []);
      setBistScanned(bistRes.scanned_count || 0);
      setKapContracts(kapRes.items || []);
      setNotice(
        `BIST taraması (${bistRes.scanned_count} hisse) ve KAP sözleşme akışı güncellendi.`
      );
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const executeBatchAnalyze = async () => {
    if (selectedSymbols.length === 0) return;
    setBatchRunning(true);
    setError(null);
    try {
      await analysisApi.analyzeAsync({
        stockCodes: selectedSymbols,
      });
      setBatchConfirmOpen(false);
      setNotice(`${selectedSymbols.length} hisse için derin AI analizi kuyruğa alındı.`);
      navigate('/');
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setBatchRunning(false);
    }
  };

  const runCryptoTrend = async () => {
    setCryptoLoading(true);
    setError(null);
    try {
      const res = await alphaApi.getCryptoTrend(true);
      setCryptoData(res);
      setNotice('Kripto Trend sinyali, geçmiş testi ve sanal defter güncellendi.');
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setCryptoLoading(false);
    }
  };

  const runForm4HistoricalStudy = async () => {
    setForm4StudyLoading(true);
    setError(null);
    setNotice('SEC Form 4 geçmiş testi başlatıldı. İlk çalıştırmada fiyatlar indirildiği için birkaç dakika sürebilir...');
    try {
      const res = await alphaApi.runForm4Study({
        quarters: form4Quarters,
        min_value: form4StudyMinVal,
        limit: form4StudyLimit,
      });
      setForm4StudyRes(res);
      setNotice(`SEC Form 4 geçmiş testi tamamlandı: ${res.evaluated_events} / ${res.total_events} olay ölçüldü.`);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setForm4StudyLoading(false);
    }
  };

  const runPeadUnbiasedHistoricalStudy = async () => {
    setPeadUnbiasedLoading(true);
    setError(null);
    setNotice('PEAD (S&P 400/600) geçmiş testi başlatıldı. İlk çalıştırmada fiyatlar indirildiği için birkaç dakika sürebilir...');
    try {
      const res = await alphaApi.runPeadUnbiasedStudy({
        universe: peadUnbiasedUniv,
        sample: peadUnbiasedSample,
      });
      setPeadUnbiasedRes(res);
      setNotice(`PEAD geçmiş testi tamamlandı: ${res.evaluated_events} / ${res.total_events} bilanço olayı ölçüldü.`);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setPeadUnbiasedLoading(false);
    }
  };

  const copyText = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setNotice(`${label} panoya kopyalandı! Doğrudan Claude'a yapıştırabilirsiniz.`);
    } catch {
      setNotice('Panoya kopyalanamadı, metin kutusundan seçip kopyalayabilirsiniz.');
    }
  };

  const tabButton = (id: DiscoverTab, label: string, icon: React.ReactNode) => (
    <button
      key={id}
      type="button"
      onClick={() => {
        setActiveTab(id);
        setError(null);
      }}
      className={`inline-flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition-all ${
        activeTab === id
          ? 'bg-primary text-primary-foreground shadow-sm'
          : 'border border-border/60 bg-card/60 text-secondary-text hover:bg-hover hover:text-foreground'
      }`}
    >
      {icon}
      <span>{label}</span>
    </button>
  );

  return (
    <AppPage>
      <PageHeader
        title="Fırsat Bulucu & Yüksek Alfa Tarama Merkezi"
        description="Akademik temelli ABD kantitatif faktörler, canlı SEC Form 4 yönetici alımları, PEAD 2.0 bilanço sürprizleri ve BIST/KAP taramaları tek ekranda."
        actions={
          selectedSymbols.length > 0 && activeTab === 'us' ? (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setBatchConfirmOpen(true)}
            >
              <Play className="mr-1.5 h-3.5 w-3.5" />
              Seçili {selectedSymbols.length} Hisseyi Analiz Et
            </Button>
          ) : null
        }
      />

      {/* Tabs */}
      <div className="mb-4 flex flex-wrap gap-2">
        {tabButton('tournament', '🏆 Strateji Turnuvası & PAA', <Trophy className="h-4 w-4" />)}
        {tabButton('claude', '🧪 Claude Doğrulama & Kripto Trend', <Sparkles className="h-4 w-4" />)}
        {tabButton('us', 'ABD Yüksek Alfa (Quant)', <Compass className="h-4 w-4" />)}
        {tabButton('form4', 'Canlı SEC Form 4', <UserCheck className="h-4 w-4" />)}
        {tabButton('pead', 'PEAD 2.0 & Event Study', <TrendingUp className="h-4 w-4" />)}
        {tabButton('bist', 'BIST & KAP Sözleşmeleri', <FileText className="h-4 w-4" />)}
      </div>

      {error ? <ApiErrorAlert error={error} /> : null}
      {notice ? <InlineAlert variant="success" title="Bilgi" message={notice} /> : null}

      {/* TAB: Strategy Tournament & PAA */}
      {activeTab === 'tournament' ? <TournamentTabPanel /> : null}

      {/* TAB 0: Claude Verification & Crypto Trend */}
      {activeTab === 'claude' ? (
        <div className="space-y-4">
          <SectionCard
            title="1. Kripto Trend Stratejisi (BTC & ETH — 50/100/150/200/250 Günlük Ortalamalar)"
            subtitle="Tahmin yapmadan büyük çöküşlerde nakitte kalmayı hedefleyen 5 hareketli ortalama topluluğu (Ensemble) ve sanal defter"
            actions={
              <div className="flex items-center gap-2">
                {cryptoData?.report_text ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => void copyText(cryptoData.report_text, 'Kripto Trend raporu')}
                  >
                    📋 Raporu Kopyala
                  </Button>
                ) : null}
                <Button variant="primary" size="sm" onClick={() => void runCryptoTrend()} disabled={cryptoLoading}>
                  <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${cryptoLoading ? 'animate-spin' : ''}`} />
                  {cryptoLoading ? 'Hesaplanıyor...' : 'Güncel Sinyal & Backtest Çalıştır'}
                </Button>
              </div>
            }
          >
            {!cryptoData ? (
              <EmptyState
                title="Kripto Trend Motoru Hazır"
                description="BTC ve ETH için bugünkü 50/100/150/200/250 günlük ortalama sinyallerini, 2018-bugün geçmiş testini ve sanal defteri görmek için sağ üstteki butona tıklayın."
              />
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {Object.entries(cryptoData.signals).map(([asset, sig]) => (
                    <Card key={asset} variant="bordered" padding="sm">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-sm font-bold text-foreground">{asset}</span>
                        <Badge variant={(sig.weight ?? 0) > 0 ? 'success' : 'warning'} glow>
                          Hedef: %{((sig.weight ?? 0) * 100).toFixed(0)} Coin / %{(100 - (sig.weight ?? 0) * 100).toFixed(0)} Nakit
                        </Badge>
                      </div>
                      <div className="mt-1.5 text-xs text-secondary-text">
                        Son Kapanış ({sig.date || '--'}):{' '}
                        <strong className="text-foreground">
                          ${sig.close != null ? sig.close.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '--'}
                        </strong>
                      </div>
                      {sig.averages ? (
                        <div className="mt-1 flex flex-wrap gap-1.5 text-[11px] text-secondary-text">
                          {Object.entries(sig.averages).map(([k, v]) => (
                            <span key={k} className="rounded bg-background/70 px-1.5 py-0.5 font-mono">
                              SMA{k}: ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </Card>
                  ))}
                </div>
                <pre className="max-h-80 overflow-auto rounded-xl border border-border/60 bg-background/80 p-3 font-mono text-xs text-foreground whitespace-pre-wrap">
                  {cryptoData.report_text}
                </pre>
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="2. ABD Testi 1 — SEC Form 4 Yönetici Alımları Geçmiş Testi (sec_form4_study.py)"
            subtitle="SEC EDGAR çeyreklik veri setleri · S&P 500 (SPY) ve Russell 2000 (IWM) kıyası · Aylık kümeleme & Holm çoklu test düzeltmesi"
            actions={
              <div className="flex flex-wrap items-center gap-2">
                {form4StudyRes?.report_text ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => void copyText(form4StudyRes.report_text, 'SEC Form 4 test çıktısı')}
                  >
                    📋 Çıktıyı Kopyala (Claude İçin)
                  </Button>
                ) : null}
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void runForm4HistoricalStudy()}
                  disabled={form4StudyLoading}
                >
                  <Play className="mr-1.5 h-3.5 w-3.5" />
                  {form4StudyLoading ? 'SEC & Fiyatlar İndiriliyor...' : 'Form 4 Testini Çalıştır'}
                </Button>
              </div>
            }
          >
            <div className="mb-3 flex flex-wrap items-center gap-3 rounded-xl border border-border/60 bg-background/50 p-3 text-xs">
              <label className="flex items-center gap-1.5">
                <span className="text-secondary-text">Çeyrekler:</span>
                <input
                  type="text"
                  value={form4Quarters}
                  onChange={(e) => setForm4Quarters(e.target.value)}
                  className="w-40 rounded-lg border border-border/70 bg-card px-2 py-1 font-mono text-foreground"
                />
              </label>
              <label className="flex items-center gap-1.5">
                <span className="text-secondary-text">Min Alım ($):</span>
                <select
                  value={form4StudyMinVal}
                  onChange={(e) => setForm4StudyMinVal(Number(e.target.value))}
                  className="rounded-lg border border-border/70 bg-card px-2 py-1 text-foreground"
                >
                  <option value={25000}>$25,000</option>
                  <option value={50000}>$50,000 (Claude Önerisi)</option>
                  <option value={100000}>$100,000</option>
                </select>
              </label>
              <label className="flex items-center gap-1.5">
                <span className="text-secondary-text">Olay Sınırı:</span>
                <select
                  value={form4StudyLimit}
                  onChange={(e) => setForm4StudyLimit(Number(e.target.value))}
                  className="rounded-lg border border-border/70 bg-card px-2 py-1 text-foreground"
                >
                  <option value={0}>0 — Tüm Olaylar (Claude Önerisi, 10-30 dk)</option>
                  <option value={250}>250 Olay (Hızlı Önizleme, ~2-4 dk)</option>
                  <option value={100}>100 Olay (Çok Hızlı Test, ~1 dk)</option>
                </select>
              </label>
            </div>

            {form4StudyRes?.report_text ? (
              <pre className="max-h-96 overflow-auto rounded-xl border border-border/60 bg-background/80 p-3 font-mono text-xs text-foreground whitespace-pre-wrap">
                {form4StudyRes.report_text}
              </pre>
            ) : (
              <EmptyState
                title="SEC Form 4 Geçmiş Testi Hazır"
                description="E-postanız (xavrail@gmail.com) .env dosyasına tanımlandı. 'Form 4 Testini Çalıştır' butonuna basarak testi başlatabilir ve bitince 'Çıktıyı Kopyala' butonuyla Claude'a gönderebilirsiniz."
              />
            )}
          </SectionCard>

          <SectionCard
            title="3. ABD Testi 2 — PEAD Bilanço Sürüklenmesi Geçmiş Testi (pead_study.py)"
            subtitle="Seçim yanlılığını önlemek için S&P 400 (MidCap) ve S&P 600 (SmallCap) endeks bileşenleri üzerinde SPY & IWM kıyaslı test"
            actions={
              <div className="flex flex-wrap items-center gap-2">
                {peadUnbiasedRes?.report_text ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => void copyText(peadUnbiasedRes.report_text || '', 'PEAD test çıktısı')}
                  >
                    📋 Çıktıyı Kopyala (Claude İçin)
                  </Button>
                ) : null}
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void runPeadUnbiasedHistoricalStudy()}
                  disabled={peadUnbiasedLoading}
                >
                  <Play className="mr-1.5 h-3.5 w-3.5" />
                  {peadUnbiasedLoading ? 'Bilanço & Fiyatlar Ölçülüyor...' : 'PEAD Testini Çalıştır'}
                </Button>
              </div>
            }
          >
            <div className="mb-3 flex flex-wrap items-center gap-3 rounded-xl border border-border/60 bg-background/50 p-3 text-xs">
              <label className="flex items-center gap-1.5">
                <span className="text-secondary-text">Evren:</span>
                <select
                  value={peadUnbiasedUniv}
                  onChange={(e) => setPeadUnbiasedUniv(e.target.value as 'smid' | 'sp400' | 'sp600' | 'sp500')}
                  className="rounded-lg border border-border/70 bg-card px-2 py-1 text-foreground"
                >
                  <option value="smid">smid — S&P 400 + S&P 600 (Claude Önerisi)</option>
                  <option value="sp600">sp600 — S&P 600 SmallCap</option>
                  <option value="sp400">sp400 — S&P 400 MidCap</option>
                  <option value="sp500">sp500 — S&P 500 LargeCap</option>
                </select>
              </label>
              <label className="flex items-center gap-1.5">
                <span className="text-secondary-text">Hisse Örneklemi:</span>
                <select
                  value={peadUnbiasedSample}
                  onChange={(e) => setPeadUnbiasedSample(Number(e.target.value))}
                  className="rounded-lg border border-border/70 bg-card px-2 py-1 text-foreground"
                >
                  <option value={400}>400 Hisse (Claude Önerisi, 10-25 dk)</option>
                  <option value={100}>100 Hisse (Hızlı Önizleme, ~3-5 dk)</option>
                  <option value={40}>40 Hisse (Çok Hızlı Test, ~1 dk)</option>
                </select>
              </label>
            </div>

            {peadUnbiasedRes?.report_text ? (
              <pre className="max-h-96 overflow-auto rounded-xl border border-border/60 bg-background/80 p-3 font-mono text-xs text-foreground whitespace-pre-wrap">
                {peadUnbiasedRes.report_text}
              </pre>
            ) : (
              <EmptyState
                title="PEAD Tarafsız Evren Testi Hazır"
                description="'PEAD Testini Çalıştır' butonuna basarak S&P 400 ve S&P 600 hisseleri üzerinde geçmiş bilanço sürprizi testini çalıştırabilir, sonucu tek tıkla kopyalayabilirsiniz."
              />
            )}
          </SectionCard>
        </div>
      ) : null}

      {/* TAB 1: US High Alpha */}
      {activeTab === 'us' ? (
        <SectionCard
          title="ABD Çok Faktörlü Yüksek Alfa Taraması"
          subtitle="Residual Momentum (vs SPY) · 52W High · Frog-in-the-Pan · Nakit Kârlılık · PEAD + Form 4"
          actions={
            <Button variant="primary" size="sm" onClick={() => void runUsScreen()} disabled={loading}>
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              {loading ? 'Taranıyor...' : 'ABD Taramasını Başlat'}
            </Button>
          }
        >
          <div className="mb-4 flex flex-wrap items-center gap-4 rounded-xl border border-border/60 bg-background/50 p-3 text-xs">
            <label className="flex items-center gap-2">
              <span className="text-secondary-text">Aday Sayısı:</span>
              <select
                value={usTopN}
                onChange={(e) => setUsTopN(Number(e.target.value))}
                className="rounded-lg border border-border/70 bg-card px-2 py-1 text-foreground"
              >
                <option value={8}>Top 8</option>
                <option value={12}>Top 12</option>
                <option value={20}>Top 20</option>
              </select>
            </label>
            <label className="flex cursor-pointer items-center gap-1.5">
              <input type="checkbox" checked={includePead} onChange={(e) => setIncludePead(e.target.checked)} />
              <span>PEAD 2.0 Bonusu</span>
            </label>
            <label className="flex cursor-pointer items-center gap-1.5">
              <input type="checkbox" checked={includeForm4} onChange={(e) => setIncludeForm4(e.target.checked)} />
              <span>Canlı Form 4 Bonusu</span>
            </label>
            <label className="flex cursor-pointer items-center gap-1.5">
              <input type="checkbox" checked={useSecXbrl} onChange={(e) => setUseSecXbrl(e.target.checked)} />
              <span>SEC XBRL Nakit Kârlılık</span>
            </label>
          </div>

          {usItems.length === 0 ? (
            <EmptyState
              title="ABD Yüksek Alfa Taraması Hazır"
              description="Likidite filtreli ABD evreninde Residual Momentum, 52 Hafta Zirve, FIP, Nakit Kârlılık, PEAD ve Form 4 kümelerini birleştirerek en iyi adayları çıkarmak için taramayı başlatın."
              action={
                <Button variant="primary" size="sm" onClick={() => void runUsScreen()} disabled={loading}>
                  <Sparkles className="mr-1.5 h-4 w-4" />
                  Taramayı Başlat
                </Button>
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border/60 text-secondary-text">
                    <th className="pb-2 pr-2">Seç</th>
                    <th className="pb-2 px-2">Hisse</th>
                    <th className="pb-2 px-2 text-right">Skor</th>
                    <th className="pb-2 px-2 text-right">ResidMom z</th>
                    <th className="pb-2 px-2 text-right">52W Zirve</th>
                    <th className="pb-2 px-2 text-right">FIP (ID)</th>
                    <th className="pb-2 px-2 text-right">Nakit Kâr.</th>
                    <th className="pb-2 px-2 text-right">Vol Ölçek</th>
                    <th className="pb-2 px-2">Sinyal Nedenleri</th>
                    <th className="pb-2 pl-2 text-right">İşlem</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {usItems.map((item) => {
                    const checked = selectedSymbols.includes(item.symbol);
                    return (
                      <tr key={item.symbol} className="hover:bg-hover/40">
                        <td className="py-2.5 pr-2">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleSelect(item.symbol)}
                            aria-label={`Seç ${item.symbol}`}
                          />
                        </td>
                        <td className="py-2.5 px-2">
                          <span className="font-mono text-sm font-bold text-foreground">{item.symbol}</span>
                          {item.last_close != null ? (
                            <span className="ml-1.5 text-[11px] text-secondary-text">${item.last_close.toFixed(2)}</span>
                          ) : null}
                        </td>
                        <td className="py-2.5 px-2 text-right">
                          <Badge variant={item.score >= 60 ? 'success' : 'info'} glow>
                            {item.score.toFixed(1)}
                          </Badge>
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-foreground">
                          {item.residual_momentum_z != null ? item.residual_momentum_z.toFixed(2) : '--'}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-foreground">
                          {item.near_52w_high != null ? `%${(item.near_52w_high * 100).toFixed(1)}` : '--'}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono">
                          <span className={(item.fip_id ?? 0) < 0 ? 'text-emerald-400' : 'text-secondary-text'}>
                            {item.fip_id != null ? item.fip_id.toFixed(3) : '--'}
                          </span>
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-foreground">
                          {item.cash_op_profitability != null ? `%${(item.cash_op_profitability * 100).toFixed(1)}` : '--'}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-secondary-text">
                          {item.vol_scale_weight != null ? `${item.vol_scale_weight.toFixed(2)}x` : '--'}
                        </td>
                        <td className="py-2.5 px-2 text-secondary-text">
                          <div className="flex flex-wrap gap-1">
                            {item.reasons.slice(0, 3).map((r) => (
                              <Badge key={r} variant="default">{r}</Badge>
                            ))}
                          </div>
                        </td>
                        <td className="py-2.5 pl-2 text-right">
                          <Button variant="secondary" size="sm" onClick={() => goAnalyze(item.symbol)}>
                            Analiz Et
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      ) : null}

      {/* TAB 2: Live Form 4 */}
      {activeTab === 'form4' ? (
        <SectionCard
          title="Canlı SEC EDGAR Form 4 Açık Piyasa Alımları"
          subtitle="Gerçek zamanlı XML ayrıştırma · Çoklu yönetici kümelenmesi · C-Suite ve rutin dışı (CMP) filtresi"
          actions={
            <div className="flex items-center gap-2">
              <select
                value={form4MinVal}
                onChange={(e) => setForm4MinVal(Number(e.target.value))}
                className="rounded-xl border border-border/70 bg-card px-2.5 py-1.5 text-xs text-foreground"
              >
                <option value={10000}>Min $10k</option>
                <option value={50000}>Min $50k</option>
                <option value={100000}>Min $100k</option>
              </select>
              <Button variant="primary" size="sm" onClick={() => void runForm4Live()} disabled={loading}>
                <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                {loading ? 'SEC Taranıyor...' : 'Canlı Form 4 Tara'}
              </Button>
            </div>
          }
        >
          {form4Items.length === 0 ? (
            <EmptyState
              title="Canlı SEC Form 4 Verisi Çekilmedi"
              description="SEC EDGAR üzerinden son bildirilen yönetici açık piyasa alımlarını çekip küme ve C-Suite puanlaması yapmak için butona tıklayın."
            />
          ) : (
            <div className="space-y-2.5">
              {form4Items.map((item) => (
                <Card key={`${item.symbol}-${item.filing_date}`} variant="bordered" padding="sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm font-bold text-primary">{item.symbol}</span>
                      <span className="text-xs font-medium text-foreground">{item.company_name}</span>
                      {item.is_cluster ? <Badge variant="success" glow>Küme ({item.insider_count} Yönetici)</Badge> : null}
                      {item.has_c_level ? <Badge variant="info">C-Suite</Badge> : null}
                      {item.has_10b51 ? <Badge variant="warning">10b5-1 Plan</Badge> : null}
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="success">Skor: {item.score.toFixed(0)}</Badge>
                      <Button variant="secondary" size="sm" onClick={() => goAnalyze(item.symbol, item.company_name)}>
                        Analiz Et
                      </Button>
                    </div>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-secondary-text">
                    <span>
                      Toplam Alım: <strong className="text-foreground">{fmtUsd(item.total_value)}</strong> · Ort. Fiyat: ${item.avg_price.toFixed(2)} · Ünvanlar: {item.primary_titles.join(', ') || '--'}
                    </span>
                    {item.sec_url ? (
                      <a href={item.sec_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                        SEC Dosyası <ExternalLink className="h-3 w-3" />
                      </a>
                    ) : null}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </SectionCard>
      ) : null}

      {/* TAB 3: PEAD 2.0 + Event Study */}
      {activeTab === 'pead' ? (
        <div className="space-y-4">
          <SectionCard
            title="PEAD 2.0 — Bilanço Sürprizi Sonrası Sürüklenme Tarayıcısı"
            subtitle="BMO/AMC seans hizalaması · SUE & gelir büyümesi · Hacim patlaması"
            actions={
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={peadUniverse}
                  onChange={(e) => setPeadUniverse(e.target.value as 'all' | 'midcap' | 'megacap')}
                  className="rounded-xl border border-border/70 bg-card px-2.5 py-1.5 text-xs text-foreground"
                >
                  <option value="all">Tümü (Midcap + Megacap)</option>
                  <option value="midcap">Mid/Small-Cap (Güçlü PEAD)</option>
                  <option value="megacap">Mega-Cap</option>
                </select>
                <select
                  value={peadMaxDays}
                  onChange={(e) => setPeadMaxDays(Number(e.target.value))}
                  className="rounded-xl border border-border/70 bg-card px-2.5 py-1.5 text-xs text-foreground"
                >
                  <option value={14}>Son 14 Gün</option>
                  <option value={21}>Son 21 Gün</option>
                  <option value={45}>Son 45 Gün</option>
                </select>
                <Button variant="primary" size="sm" onClick={() => void runPeadScreen()} disabled={loading}>
                  <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                  {loading ? 'Taranıyor...' : 'PEAD Tara'}
                </Button>
              </div>
            }
          >
            {peadItems.length === 0 ? (
              <EmptyState
                title="PEAD 2.0 Taraması Bekliyor"
                description="Son bilançosunda güçlü EPS/SUE sürprizi yapıp 52 haftalık zirvesine yakın seyreden ABD hisselerini tarayın."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-border/60 text-secondary-text">
                      <th className="pb-2 pr-2">Hisse</th>
                      <th className="pb-2 px-2">Bilanço</th>
                      <th className="pb-2 px-2 text-right">EPS Sürpriz</th>
                      <th className="pb-2 px-2 text-right">SUE</th>
                      <th className="pb-2 px-2 text-right">Gün-1 %</th>
                      <th className="pb-2 px-2 text-right">Sürüklenme %</th>
                      <th className="pb-2 px-2 text-right">Hacim</th>
                      <th className="pb-2 px-2 text-right">Skor</th>
                      <th className="pb-2 pl-2 text-right">İşlem</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {peadItems.map((item) => (
                      <tr key={item.symbol} className="hover:bg-hover/40">
                        <td className="py-2.5 pr-2">
                          <div className="font-mono font-bold text-foreground">{item.symbol}</div>
                          <div className="text-[11px] text-secondary-text">{item.company_name}</div>
                        </td>
                        <td className="py-2.5 px-2 text-secondary-text">
                          {item.earnings_date || '--'}{' '}
                          <Badge variant="default">{item.announcement_session}</Badge>
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono font-semibold text-emerald-400">
                          {fmtPct(item.eps_surprise_pct)}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono">
                          {item.sue_score != null ? item.sue_score.toFixed(2) : '--'}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono">{fmtPct(item.day1_return_pct)}</td>
                        <td className="py-2.5 px-2 text-right font-mono">{fmtPct(item.total_drift_pct)}</td>
                        <td className="py-2.5 px-2 text-right font-mono">
                          {item.volume_surge_ratio != null ? `${item.volume_surge_ratio.toFixed(1)}x` : '--'}
                        </td>
                        <td className="py-2.5 px-2 text-right">
                          <Badge variant={item.score >= 70 ? 'success' : 'info'}>{item.score.toFixed(0)}</Badge>
                        </td>
                        <td className="py-2.5 pl-2 text-right">
                          <Button variant="secondary" size="sm" onClick={() => goAnalyze(item.symbol, item.company_name)}>
                            Analiz Et
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="Tarihsel PEAD Event Study Doğrulayıcısı (vs SPY, Kayma Düşülmüş)"
            subtitle="Bilanço günü kapanışından sonra 1, 5, 20 ve 40 işlem gününde SPY'a göre net fazla getiri ve t-istatistiği"
          >
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="text"
                value={studySymbolsInput}
                onChange={(e) => setStudySymbolsInput(e.target.value)}
                placeholder="NVDA, META, AMZN, AVGO, AXON"
                className="min-w-[260px] flex-1 rounded-xl border border-border/70 bg-background/60 px-3 py-2 text-xs text-foreground focus:outline-none"
              />
              <Button variant="secondary" size="sm" onClick={() => void runPeadEventStudy()} disabled={studyLoading}>
                <BarChart3 className="mr-1.5 h-3.5 w-3.5" />
                {studyLoading ? 'Ölçülüyor...' : 'Event Study Çalıştır'}
              </Button>
            </div>

            {studyResult ? (
              <div className="mt-4 space-y-3">
                <div className="text-xs text-secondary-text">
                  Değerlendirilen Olay: <strong className="text-foreground">{studyResult.evaluated_events}</strong> / {studyResult.total_events} · Kıyas: <strong className="text-foreground">{studyResult.benchmark_symbol}</strong> · Kayma Maliyeti: %{studyResult.estimated_slippage_pct}
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {Object.entries(studyResult.horizons).map(([hKey, stat]) => (
                    <StatCard
                      key={hKey}
                      label={`${hKey} Net Fazla Getiri (vs SPY)`}
                      value={fmtPct(stat.net_excess_return_pct, 2)}
                      hint={`n=${stat.count} · Kazanma: %${stat.win_rate_pct ?? '--'} · t=${stat.net_t_stat?.toFixed(2) ?? '--'}${stat.is_significant ? ' ✓ Anlamlı' : ''}`}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </SectionCard>
        </div>
      ) : null}

      {/* TAB 4: BIST & KAP Contracts */}
      {activeTab === 'bist' ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <SectionCard
            title="BIST Teknik + KAP Taraması"
            subtitle={bistScanned > 0 ? `${bistScanned} BIST hissesi tarandı` : '~800 BIST hissesi içinde hacim ve kırılım taraması'}
            actions={
              <Button variant="primary" size="sm" onClick={() => void runBistAndKap()} disabled={loading}>
                <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                {loading ? 'Taranıyor...' : 'BIST + KAP Tara'}
              </Button>
            }
          >
            {bistCandidates.length === 0 ? (
              <EmptyState
                title="BIST Taraması Bekliyor"
                description="Borsa İstanbul genelinde teknik kurulum, hacim artışı ve yeni KAP olaylarını taramak için butona basın."
              />
            ) : (
              <div className="space-y-2">
                {bistCandidates.map((c) => (
                  <Card key={c.code} variant="bordered" padding="sm">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <span className="font-mono text-sm font-bold text-foreground">{c.code}</span>
                        {c.name ? <span className="ml-2 text-xs text-secondary-text">{c.name}</span> : null}
                      </div>
                      <div className="flex items-center gap-2">
                        {c.score != null ? <Badge variant="success">Skor: {c.score}</Badge> : null}
                        <Button variant="secondary" size="sm" onClick={() => goAnalyze(c.code, c.name)}>
                          Analiz Et
                        </Button>
                      </div>
                    </div>
                    {Array.isArray(c.reasons) && c.reasons.length > 0 ? (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {c.reasons.slice(0, 4).map((r) => (
                          <Badge key={r} variant="default">{r}</Badge>
                        ))}
                      </div>
                    ) : null}
                  </Card>
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="KAP Yeni İş İlişkisi & Sözleşme Katalizörleri"
            subtitle="Yıllık ciroya oranlı yüksek tutarlı ihale / sözleşme bildirimleri"
          >
            {kapContracts.length === 0 ? (
              <EmptyState
                title="Henüz Sözleşme Listelenmedi"
                description="'BIST + KAP Tara' butonuna basarak son 7 günün önemli yeni iş ilişkisi bildirimlerini puanlayın."
              />
            ) : (
              <div className="space-y-2">
                {kapContracts.map((k) => (
                  <Card key={`${k.symbol}-${k.disclosure_index}`} variant="bordered" padding="sm">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-bold text-primary">{k.symbol}</span>
                        <Badge variant={k.conviction_tier === 'MEGA' || k.conviction_tier === 'STRONG' ? 'success' : 'info'}>
                          {k.conviction_tier} ({k.score})
                        </Badge>
                      </div>
                      <Button variant="secondary" size="sm" onClick={() => goAnalyze(k.symbol, k.company_name)}>
                        Analiz Et
                      </Button>
                    </div>
                    <p className="mt-1 text-xs font-medium text-foreground">{k.title}</p>
                    <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2 text-[11px] text-secondary-text">
                      <span>
                        {k.published_date}
                        {k.contract_to_revenue_pct != null ? ` · Ciro Oranı: %${k.contract_to_revenue_pct.toFixed(1)}` : ''}
                      </span>
                      {k.url ? (
                        <a href={k.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
                          KAP <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : null}
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </SectionCard>
        </div>
      ) : null}

      {/* Safety Guardrail Confirmation Modal */}
      <ConfirmDialog
        isOpen={batchConfirmOpen}
        title="Toplu AI Analiz Onayı (Güvenli İşlem)"
        message={`${selectedSymbols.length} hisse (${selectedSymbols.join(', ')}) için derin AI + Boğa/Ayı analizi başlatılacak. Bu işlem LLM/API kotanızdan ${selectedSymbols.length} çağrı tüketir. Onaylıyor musunuz?`}
        confirmText={batchRunning ? 'Gönderiliyor...' : 'Analizi Başlat'}
        cancelText="Vazgeç"
        confirmDisabled={batchRunning}
        cancelDisabled={batchRunning}
        onConfirm={() => void executeBatchAnalyze()}
        onCancel={() => setBatchConfirmOpen(false)}
      />
    </AppPage>
  );
};

export default AlphaDiscoveryPage;
