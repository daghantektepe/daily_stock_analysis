# Daily Stock Analysis — Kapsamlı Kârlılık, Stabilite, Bug Denetimi ve Gelişim Planı

> **Denetim Tarihi:** 21 Kasım 2026  
> **Test Edilen Sürüm:** `E:\daily_stock_analysis` · dal `feat/cli-mcp-quant-tournament` · commit `7927dde` (`v0.4.1-desktop-exe-clean`)  
> **Test Ortamı:** Canlı çalışan paketli `DailyStockAnalysis.exe` (`http://127.0.0.1:8000`), 27 HTTP ucu, 16 MCP aracı, 15 backend `pytest` paketi (`104` test), 103 frontend `vitest` dosyası (`1.113` test), ESLint ve 2018–2026 temiz piyasa verisi.

---

## 1. Dürüst Kârlılık Cevabı: Program Şu An Gerçekten Kazançlı Öneriler Sunabiliyor mu?

**Kısa ve Dürüst Cevap:** **Kısmen — Kriz Koruması Güçlü, Ancak Aktif Kâr Üretimi (Alfa) Mevcut Kodda Ciddi Bozulmalar Nedeniyle Yetersiz.**

### A. İyi Çalışan Taraf (Gerçek Değer Üreten Özellikler)
1. **Canlı Kriz & Ayı Piyasası Kalkanı Gerçekten Çalışıyor:**
   - 21 Kasım 2026 canlı piyasa taramasında (`dsa_get_market_regime` & `dsa_get_strategic_trading_brief`) program mevcut krizi doğru yakaladı: **`regime: risk_off`**, **`position_scale: 0.0`**, **`SPY 689.81 < SMA200 730.29`**, **`VIX 35.89 (kriz eşiği >= 32)`**.
   - Kripto 5-SMA Trend (`BTC-USD` / `ETH-USD`) **%100 nakitte** durarak 2026'daki `-%39.1`'lik kripto çöküşünden sermayeyi tam korudu (`+0.7%` vs Al-Tut `-39.1%`).
2. **Düşük Devirli Trend Stratejileri İşlem Maliyetine Dayanıklı:**
   - 50 bps'lik ağır kayma/komisyon stres testinde bile **`SAFE_HAVEN_ROTATION`** (`+14.7%`), **`CRYPTO_BTC_200SMA`** (`+21.8%`), **`CRYPTO_5SMA_ENSEMBLE`** (`+13.2%`) ve **`PAA`** pozitif kalmayı başardı.

### B. Kritik Kârlılık Gerçeği — Temiz `2022–2026` OOS Denetimi (2022 Ayı Piyasası + Kasım 2026 VIX=36 Krizi Dahil)

Programdaki mevcut `src/quant/stats.py` Sharpe oranını **risksiz faizi (`BIL` T-Bill = yıllık `%+3.89`) düşmeden (`Rf = 0`)** hesaplıyor. Bu durum `%80` hazine bonosunda bekleyen düşük getirili stratejilerin yapay olarak yüksek Sharpe (`0.86–1.01`) alıp **"PASS_SOLID"** etiketi kazanmasına yol açıyor. Aşağıdaki tablo **gerçek risksiz faiz üstü Excess Sharpe (`vs BIL +3.89%`)** ile temiz 2018–2026 verisi üzerinden yeniden hesaplanmıştır.

| Strateji | Evren | OOS CAGR | BIL Farkı | `SR (Rf=0)` | **Gerçek `SR (ExRF)`** | MaxDD | 2022 | 2023 | 2024 | 2025 | 2026 | Değerlendirme |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| *Referans: Risksiz Hazine Bonosu (`BIL`)* | `us_etf` | **+3.9%** | 0.0% | 18.44 | **0.00** | -0.0% | — | — | — | — | — | **Taban Eşik** (bunu geçemeyen strateji başarısızdır) |
| **Safe-Haven Altın & Tahvil Rotasyonu** | `us_etf` | **+13.8%** | **+9.9%** | 0.85 | **+0.62** | -20.8% | -5.3% | +10.8% | +5.2% | **+63.7%** | +0.9% | **En Yüksek ExRF Sharpe** *(UYARI: Getirinin çoğu tek yıl 2025 Altın rallisinden)* |
| **Gemini AI Konseyi (`paa_custom`, `pf=1.0`)** | `us_etf` | **+8.4%** | **+4.5%** | 0.75 | **+0.53** | -14.5% | — | — | — | — | — | **En Dengeli AI Konseyi Stratejisi** (dengeli koruma `pf=1.0`) |
| **Nasdaq-100 (`QQQ`) 50/200G Çift Trend** | `us_etf` | **+9.1%** | **+5.2%** | 0.73 | **+0.44** | -17.3% | -10.4% | +31.8% | +15.4% | +14.3% | -0.9% | İyi ama **devir çok yüksek (`27.1x/yıl`)**, 50 bps'de `-1.9%`'a düşüyor |
| **Kripto BTC-USD 200G SMA Trend** | `crypto` | **+24.8%** | **+20.9%** | 0.83 | **+0.38** | -32.2% | 0.0% | +93.9% | +80.1% | -17.8% | +2.7% | Yüksek getiri + ayı koruması; yüksek volatilite (uydu kolu) |
| *Referans: S&P 500 Al-Tut (`SPY`)* | `us_etf` | **+9.3%** | +5.4% | 0.59 | **+0.38** | -24.5% | -18.2% | +26.2% | +24.9% | +17.7% | +1.9% | **Ana Hisse Kıyaslaması** |
| **Vol-Target Multi-Asset Trend (`%10`)** | `us_etf` | +5.9% | +2.0% | 1.01 | **+0.36** | **-6.9%** | -6.6% | +10.4% | +11.1% | +13.5% | +0.9% | En düşük düşüş + en yüksek DSR (`%72.7`), getiri mütevazı |
| **ABD Faktör Rotasyonu (`MTUM/QUAL/USMV`)** | `us_sectors` | +8.2% | +4.3% | 0.57 | +0.33 | -24.0% | -18.6% | +13.4% | +17.2% | +18.0% | **+15.0%** | 2026 krizinde güçlü (`USMV`), ancak 2022 düşüşü SPY kadar derin |
| **ABD Sektör Momentum Top-3** | `us_sectors` | +7.2% | +3.3% | 0.49 | +0.27 | -18.1% | **+5.8%** | +4.9% | +20.7% | +15.3% | -7.1% | 2022'de pozitif kaldı; 2026'da geriledi |
| **Kripto 5-SMA Trend Ensemble (BTC+ETH)** | `crypto` | +17.8% | +13.9% | 0.68 | +0.26 | -30.6% | -22.1% | +71.6% | +54.2% | +7.9% | +0.7% | Al-Tut (`-4.7%` / `-68.4%` MaxDD) karşısında çok üstün |
| *Referans: Klasik 60/40 (`SPY/IEF`)* | `us_etf` | +5.3% | +1.5% | 0.52 | +0.18 | -20.7% | -16.4% | +17.0% | +14.2% | +14.3% | +0.8% | Dengeli kıyaslama |
| **PAA Çöküş Kalkanı (`pf=2.0`, `E:` versiyonu)** | `us_etf` | +5.1% | +1.2% | 0.59 | **+0.17** | -12.8% | -9.9% | **-0.1%** | +9.1% | +13.4% | +13.4% | **Aşırı defansif!** `pf=2.0` + `GLD`/`BIL` hariç tutulduğu için 2023'ü kaçırdı |
| **Meta-Portföy A (Aktif Sanal Defter!)** | `meta` | **+3.8%** | **-0.1%** | 0.51 | **+0.03** | -11.7% | -11.0% | +5.3% | +4.7% | +12.8% | +7.7% | **BAŞARISIZ!** İçine sabitlenen `%20 VAA` + `%20 GTAA-5` + `%20 RP` yüzünden `BIL`'in altında! |
| **Claude AI Konseyi (`vol_target %8`)** | `us_etf` | **+3.6%** | **-0.3%** | 0.94 | +0.15 | -4.4% | — | — | — | — | — | `Rf=0` Sharpe tuzağı: nakit `BIL` (`+3.9%`) altında kaldı |
| **Codex AI Konseyi (`vol_target %10`)** | `us_etf` | **+3.0%** | **-0.9%** | 0.59 | +0.25 | -8.8% | — | — | — | — | — | `Rf=0` Sharpe tuzağı: nakit `BIL` (`+3.9%`) altında kaldı |
| **SPY RSI(2) Ortalamaya Dönüş** | `us_etf` | +3.7% | -0.2% | 0.49 | +0.01 | -9.5% | -5.8% | +2.7% | +14.4% | +7.3% | +0.8% | **Maliyet tuzağı (`55x/yıl` devir):** 25 bps'de `-4.1%`, 50 bps'de `-16.4%`! |
| **VAA / GTAA-5 / All-Weather RP / Low-Vol** | `us_etf` | -1.8%..+3.5% | **Negatif** | <0.46 | **<= 0.00** | -10.7..-25.2% | — | — | — | — | — | **Elenmeli** — risksiz nakdi dahi yenemiyor |

#### BIST Stratejilerinin Gerçek Dolar (USD) Bazlı Karşılığı (`USD/TRY: 13.36 → 50.56`, Yıllık `%+31.6` Kur Artışı)
| BIST Stratejisi | TL CAGR | **Gerçek USD CAGR** | USD MaxDD | USD `ExBIL` Sharpe | Not |
| :--- | ---: | ---: | ---: | ---: | :--- |
| *Referans: BIST 100 (`XU100.IS`)* | +43.6% | **+9.1%** | — | — | Reel dolar getirisi S&P 500'e yakın |
| **BIST 52H Zirve + Düşük-Vol Top-5** | +60.3% | **+21.8%** | -43.5% | **+0.66** | Hayatta kalma yanlılıklı; **2025 (`+2.9%` TL) ve 2026 (`-2.7%` TL) reel USD kayıp!** |
| **BIST 6-1A Momentum Top-5** | +50.5% | **+14.4%** | -39.8% | **+0.46** | `5/5` pozitif yıl (`2025: +24.2%`, `2026: +16.3%` TL) — daha istikrarlı |

---

## 2. Tespit Edilen Bug'lar, Stabilite ve İşlevsellik Bulguları (11 Somut Bulgu)

### P0 — Kritik Veri Bozulması, Çökme ve Kârlılık Hataları
1. **BUG-01 (Cache Poisoning):** `src/quant/tournament.py:258` (`get_live_paa_signal()`) ve `src/quant/paper_book.py:101` paylaşılan `closes_us_etf_and_sectors.csv` ve `closes_us_etf.csv` önbelleklerini daha kısa tarih (`2023-01-01`/`2024-01-01`) ve eksik sütunlarla (15/30) eziyor; bu durum 2022 ayı piyasasını ve 15 sektör/faktör ETF'sini siliyor, Gemini AI Konseyi testini yalnızca `2025-01-02` (472 gün) üzerinden çalıştırıyor.
2. **BUG-02 (`litellm` Deadlock / Circular Import):** `logs/desktop_exe.log:184-204` & `logs/api_server_20261120.log:3841` — `RuntimeScheduler` ile `/api/v1/system/config` aynı anda `litellm` import ettiğinde `_DeadlockError` / `partially initialized module 'litellm._logging'` hatası oluşuyor.
3. **BUG-03 (`Rf=0` Sharpe Körlüğü & Başarısız `Meta-Portföy A`):** `src/quant/stats.py:184` risksiz faizi düşmüyor; `src/quant/portfolio.py:42` başarısız `VAA`/`GTAA-5`/`RP` bacaklarını içerdiği için `Meta-A` risksiz nakdin (`BIL`) altında kalıyor.

### P1 — Yüksek Öncelikli Stabilite, Zaman Aşımı ve Test Hataları
4. **BUG-04 (BIST Tarayıcı Kirli KAP Evreni):** `POST /api/v1/alpha/bist-screen` borsada payı işlem görmeyen yüzlerce faktoring/varlık kiralama ihraççısını (`HALKF.IS`, `GARFL.IS`, `KOCFN.IS`, `KLVKS.IS` vb.) Yahoo Finance'ten sorguluyor ve >30 sn zaman aşımına düşüyor.
5. **BUG-05 (Canlı Tarama Uçları Timeout):** `pead-candidates` (>25s), `us-screen` (>30s), `bist-screen` (>30s) Axios 30s limitini aşıyor; `kap-contracts` 23.6s, `form4-live` 14.9s (boş `22B`), `crypto-trend` 11.1s sürüyor.
6. **BUG-06 (Kırık Frontend CI):** ESLint **4 hata** (`CommandPalette.tsx` x3, `ReportPriceChart.tsx` x1); Vitest **508 fail / 603 pass** (51 legacy test hâlâ Çince etiket bekliyor).

### P2 — Orta Öncelikli Ürün, Performans ve Yerelleştirme Bug'ları
7. **BUG-07 (CJK Sızıntıları & Log Encoding):** `/api/v1/system/config` ve `/schema`'da 884 Çince karakter (`config_registry.py`); `/api/v1/decision-signals`'ta `利好1:`; `desktop_exe.log`'da mojibake.
8. **BUG-08 (MCP Payload Şişkinliği):** `dsa_get_strategic_trading_brief` tek çağrıda `82.5 KB` (~20k+ token) ve `13.8 sn` sürüyor.
9. **BUG-09 (`ai_council_charters.json` Metin Kesilmesi):** `risk_rules` 400 karakterde kelime ortasında kesiliyor (`"...uygulanır v"`).
10. **BUG-10 (Kırık SearXNG Mirror'ları):** `TAVILY_API_KEYS` olmasına rağmen `src/search_service.py` SSL/429/bot-wall veren public SearXNG sunucularında zaman kaybediyor.
11. **BUG-11 (`quant_champion.json` Şema Tutarsızlığı & Drift):** `quant_champion.json` geçmişi `QuantAllocationPaperBook` şemasından farklı; vektörize backtest ay içi ağırlık kaymasını (`drift`) ihmal ediyor.

---

## 3. Öncelikli Gelişim Planı (P0 → P3)

### Faz 1 (P0) — Acil Veri & Çökme Onarımları
- `data_loader.py` cache izolasyonu + kapsam koruması (`start_date` ve sütun sayısı azalırken ezme yasak).
- `src/config.py` `litellm` thread-safe import kilidi (deadlock sıfırlama).
- `src/quant/stats.py` gerçek `Excess Sharpe (vs BIL)` + minimum `1.000` gün OOS doğrulama kuralı.

### Faz 2 (P1) — Gerçek Para Kazandıran Strateji Motoru (Alfa v2)
- **PAA v2 (`pf=1.25–1.50` + `safe_assets=("BIL","SHY","GLD")`):** 2023/2024 boğasını kaçırmadan çöküş koruması.
- **Düşük Devirli Histerezis (`QQQ` / Sektör Momentum):** Devri `27x → <6x/yıl`'a indirerek 25–50 bps maliyete dayanıklılık.
- **Meta-Portföy A v2:** Başarısız `VAA`/`GTAA-5`/`RP` yerine `PAA v2 (%35) + Çok Faktörlü Sektör/Faktör Momentum (%25) + Safe-Haven GLD/BIL Rotasyonu (%25) + [Meta-B'de %15 Kripto Trend]`.
- **3-AI Konseyi v2:** `Excess Sharpe vs BIL` + 2022 ayı piyasası + maliyet stres testi kriterleriyle yeniden değerlendirme ve metin kesilmesinin kaldırılması.
- **BIST Temiz Pay Havuzu + Reel USD Kıyaslama:** Yalnızca BIST pay piyasası hisseleri + `TRY=X` USD bazlı raporlama.

### Faz 3 (P2) — Hız, Stabilite ve MCP İyileştirmeleri
- `us-screen`, `bist-screen`, `pead-candidates`, `form4-live`, `kap-contracts` için disk/TTL önbellek ve paralel batch (hedef `<2 sn`).
- `dsa_get_strategic_trading_brief` kompakt çıktı (`82.5 KB → <8 KB`).
- `TAVILY_API_KEYS` öncelikli arama + kırık SearXNG kara listesi + kalan 884 Çince şema metni & UTF-8 log düzeltmesi.

### Faz 4 (P3) — CI / Test Sağlığı & Canlıya Geçiş Kapısı
- 4 ESLint hatası + 51 kırık frontend Vitest testinin TR/EN uyarlanması.
- Cache-poisoning, `litellm` deadlock ve `Excess Sharpe` regresyon testleri.
- 120 işlem günü (6 ay) Alpaca Paper / `StrategyPaperBook` canlı ileri doğrulaması (`Excess Sharpe > 0.50`, `MaxDD <= %18`, kayma `<= 20 bps`) tamamlanana kadar `ALPACA_PAPER=true` & `ALPACA_AUTO_EXECUTE=false` kilidinin korunması.
