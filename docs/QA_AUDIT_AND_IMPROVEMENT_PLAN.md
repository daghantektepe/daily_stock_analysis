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


---

## Uygulama ve Doğrulama Özeti (Faz 1–4 Tamamlandı — 21 Kasım 2026)

| Faz | Git Etiketi | Yapılan İyileştirmeler | Doğrulama Sonucu |
|---|---|---|---|
| **Faz 1 (P0)** | `v0.5.1-p0-integrity` | `data_loader.py` yıkıcı olmayan önbellek birleştirme + kapsam doğrulaması (BUG-01); `config.py`/`analyzer.py` global `_LITELLM_IMPORT_LOCK` (BUG-02); gerçek `BIL` risksiz üstü `Excess Sharpe` + `min_oos_days=750` karar kapısı (BUG-03); AI Konsey kelime sınırında 1200 karakter kırpma (BUG-09) | 24/24 çekirdek test geçti; zehirlenen CSV temizlendi ve 2018–2026 tam geçmişle yeniden üretildi |
| **Faz 2 (P1)** | `v0.5.2-alpha-v2` | **Alpha v2**: `PAA v2` (`BIL/SHY/GLD`, `pf=1.35`, `top_n=4`), `QQQ Dual-SMA` (haftalık + histerezis + `BIL`), `Safe-Haven` (`BIL` eklendi), **Meta-Portföy A v2** (`%35 PAA v2 + %25 QQQ Dual-SMA + %20 Safe-Haven + %20 Vol-Target Trend`); BIST KAP borç/sukuk/leasing/faktoring SPV filtresi + 30 günlük delisted skip önbelleği (BUG-04) | **Şampiyon Meta-Portföy A v2 (OOS 2022–2026)**: **+%10,92 CAGR** (öncesi +%3,8), **ExRF Sharpe +0,73–0,75** (SPY +0,38'in ~2 katı, öncesi +0,03), **MaxDD -%8,32** (SPY -%24,5'in üçte biri) |
| **Faz 3 (P2)** | `v0.5.3-speed-stability` | `us_quant_screener.py` tek toplu paralel `yf.download` + 2 aşamalı skorlama; `pead_screener.py` `deadline_seconds=14.0`; `alpha.py` 20 dk disk TTL önbelleği + `crypto-trend` önbelleği + BIST `scanned_count`/`passed_count` eşleme düzeltmesi; `src/mcp/tools.py` `compact=True` varsayılanı (BUG-06); `search_service.py` 15 dk SearXNG mirror cooldown (BUG-08); `portfolio.py` `date`/`nav` alanları (BUG-11); temiz ASCII başlangıç logları | 116/116 test geçti; `POST /us-screen` **>30s zaman aşımı → 8,1s (önbellekte 16,6ms)**; `POST /bist-screen` **>30s → 13,3s (önbellekte 21,7ms)**; `GET /pead-candidates` **>25s → 14,3s**; MCP brifing **82,5 KB → 7,8 KB** (%90,6 küçülme) |
| **Faz 4 (P3)** | `v0.5.4-verified-release` | 4 ESLint hatası sıfırlandı (`CommandPalette.tsx` + `commandPaletteEvents.ts`, `ReportPriceChart.tsx`); 12 çekirdek Türkçe/uygulama Vitest dosyası (83/83 test, `CommandPalette.test.tsx` dahil) yeşile çekildi; `tests/test_qa_regression_guards.py` (8 yeni regresyon testi) eklendi; frontend `vite build` + `check_static_assets.py` + `DailyStockAnalysis.exe` yeniden derlendi ve canlı doğrulandı | **ESLint 0 hata**; **160/160 backend `pytest`** geçti; **30/30 canlı HTTP uç noktası `200 OK` (0 zaman aşımı)**; **16/16 MCP aracı aktif (`0 hata`)**; `desktop_exe.log` 3,8s soğuk başlangıç ve 0 deadlock; `ALPACA_PAPER=true` & `ALPACA_AUTO_EXECUTE=false` kilitleri doğrulandı |

> **Kalan Bilinen Not (Legacy Upstream Testler):** `apps/dsa-web` içinde `4271682` Türkçe yerelleştirmesi öncesinden kalan 42 eski üst-akış (upstream) Vitest dosyası hâlâ Çince metin (`韩股`, `持仓明细` vb.) beklediği için toplu `npm test` çalıştırmasında kalmaktadır; fonksiyonel bileşen regresyonu değildir. Tüm çekirdek uygulama/yönlendirme/mağaza/tema/dil/tarama testleri (`12 dosya / 83 test`) ve `npm run lint` + `npm run build` %100 yeşildir.


---

## Faz 5 (A) — İleri Doğrulama Başladı (21 Kasım 2026)

- `src/quant/forward_validation.py` + `scripts/quant_forward.py`: PAA ve Meta-A, ilk `quant_paper.py step` çalıştırmasında parmak iziyle dondurulur; yalnızca dondurma sonrası günler sayılır, kod/ayar değişirse kayıt `INVALIDATED` olur.
- Kapı (Faz 4 kriterleri koda bağlandı): ≥120 ileri işlem günü, BIL üstü Sharpe ≥0,50 (± standart hata ile raporlanır), MaxDD ≤%18 (aşılırsa erken `FAIL`), sonradan işlenen gün ≤%10, Alpaca sanal dolumlarında ortalama kayma ≤20 bps.
- **Not:** 2022–2026 penceresi PAA v2 / QQQ histerezisi / Meta-A v2 karışımı ayarlanırken görüldüğü için Meta-A v2'nin +%10,92 CAGR'ı örneklem dışı kanıt sayılmaz; kanıt bu ileri kayıttan gelecektir.
- Canlı veriyle ilk dondurma (bulut doğrulaması, 20 Kasım 2026 kapanışı): Meta-A donmuş backtest 120 günlük getiri bandı p5 %−3,2 · p50 %+4,9 · p95 %+16,5; iki strateji de risk-off modda (BIL/SHY).
- Web: Strateji Turnuvası sekmesinde "İleri Doğrulama Kapısı" kartı ve `GET /api/v1/alpha/forward-validation`.

## Faz 5 (B) — BIST Dolar Bazlı Metrikler ve AI Konseyi v2 (21 Kasım 2026)

### BIST gerçek dolar karşılığı

- `src/quant/bist_usd.py`: BIST stratejilerinin net günlük TL getirisi `TRY=X` ile USD'ye çevrilir. Formül `r_usd = (1+r_tl)/(1+r_kur) − 1`; kur BIST takvimine ileri doldurulur, böylece bayram günündeki kur hareketi kaybolmaz.
- USD metrikleri ABD stratejileriyle aynı eşikle, `BIL` üstü getiriyle hesaplanır.
- Kararda artık TL Sharpe ≥0,5 değil, USD BIL üstü Sharpe ≥0,15 ve pozitif USD fazla getiri aranır (`CAVEAT_SURVIVORSHIP`). DSR ve sıralama da bu USD serisini kullanır.
- Kur verisi yoksa eski TL kuralı geçerlidir.

**Canlı veriyle sonuç (OOS 2022-01 → 2026-11-20):** USD/TRY 13,36 → 50,56, yıllık %+31,4.

| | TL CAGR | USD CAGR | USD MaxDD | BIL üstü USD Sharpe | 2022 | 2023 | 2024 | 2025 | 2026 (USD) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| XU100 (referans) | +43,7% | +9,8% | −36,4% | +0,17 | +110,7% | −14,1% | +10,0% | −5,8% | −16,0% |
| BIST 52H Zirve + Düşük-Vol Top-5 | +60,3% | +22,6% | −43,5% | +0,51 | +176,3% | +7,4% | +29,7% | −15,4% | −17,3% |
| BIST 6-1A Momentum Top-5 | +50,5% | +15,4% | −39,8% | +0,33 | +92,8% | −4,1% | +7,7% | +2,1% | −1,2% |

**Değerlendirme:**
- İki BIST stratejisinin dolar getirisinin çoğu 2022'den geliyor.
- 2025–2026'da 52H stratejisi dolar bazında kayıpta; Momentum ise yatay.
- Evren bugünkü likit hisselerden oluştuğu için hayatta kalma yanlılığı sürüyor.

### AI Konseyi v2

`council_v2_robustness()` bir tüzüğe "PASS" vermek için üç koşul arar:
- `BIL` üstü OOS kararı `PASS_ELITE` veya `PASS_SOLID` olmalı;
- 25 bps maliyette BIL üstü Sharpe ≥0,15 ve pozitif fazla getiri olmalı (50 bps yalnızca bilgi olarak raporlanır);
- 2022 takvim yılında SPY'dan az kaybetmeli. 2022 verisi eksikse sonuç FAIL olur.

Diğer değişiklikler:
- `run_ai_strategy_council.py reevaluate`: kayıtlı tüzükleri CLI çağırmadan yeniden değerlendirir; kurallar ve sanal defterler değişmez.
- CLI istemine v2 kriterleri eklendi.
- Web kartı Rf=0 Sharpe yerine BIL üstü Sharpe ve v2 rozetini gösterir.
- Turnuva tablosu ve MCP özeti de BIL üstü Sharpe ile sıralar ve raporlar; böylece "Rf=0 Sharpe tuzağı" arayüzden kalktı.

**Denetimdeki tüzük tiplerinin örnek parametrelerle değerlendirmesi:**

| Tüzük | Sonuç | 25 bps'de BIL üstü Sharpe | 2022 |
| :--- | :--- | ---: | :--- |
| vol-target %8 | FAIL | −0,12 | −3,1% (SPY −18,2%) |
| vol-target %10 | FAIL | −0,05 | −2,9% |
| PAA custom pf=1,0 | FAIL (Rf=0 döneminde PASS_SOLID idi) | +0,04 | −13,6% |

Gerçek tüzükler için E:\ üzerinde `reevaluate` çalıştırılmalıdır.


## Faz 5 (D) — 19 Yıllık Çok-Rejimli Strateji Araştırması v3 (`2008–2026`, Sıfır Optimizasyon)

Claude'un aşırı uyum uyarısına uygun olarak tüm v3 adayları dondurulmuş `PAA v2` (`87e22a6b3559`) ve `Meta-Portföy A v2` (`37a7ab36a0d9`) kodlarından tamamen izole yeni [research_v3.py](file:///E:/daily_stock_analysis/src/quant/strategies/research_v3.py) ve [research_lab.py](file:///E:/daily_stock_analysis/src/quant/research_lab.py) modüllerinde, ön-kayıtlı (pre-registered) akademik parametrelerle 4 ayrı makro rejimde (`2008–12 GFC`, `2013–19 QE`, `2020–21 COVID`, `2022–26 Faiz Şoku`) ve `5/15/25/50 bps` maliyet stresinde değerlendirildi (`docs/STRATEGY_RESEARCH_V3_REPORT.md`).

| Aday | Karar | Kapı | 2008+ ExBIL CAGR | ExSh (5 / 25 / 50 bps) | MaxDD (2008 / Genel) | 2022 Getiri | Plato (±%20) | Meta-A Kor. / 50-50 ExSh |
| :--- | :---: | :---: | ---: | :---: | :---: | ---: | :---: | :---: |
| **`V3_TREND_RISK_PARITY_BIL`** *(Öne Çıkan Kazanan)* | **✅ TERFİ** | **5/5** | **+2,49%** (`4/4` rejim +) | **+0,63 / +0,47 / +0,26** | **-%3,8 / -%7,3** | **+%3,59** *(SPY -%18,2)* | **9/9 (%100)** | **0,61** / **+0,91** *(vs +0,83, DD -%5,4)* |
| `V3_SECTOR_FACTOR_BREADTH_BIL` *(İkincil / Uyarı)* | ✅ TERFİ* | 5/5 | +4,53% (`3/4` rejim +) | +0,46 / +0,30 / +0,10 | -%2,7 / -%20,1 | -%10,67 | 9/9 (%100) | 0,46 / +0,59 *(2022–26 ExBIL -%2,24)* |
| `V3_TSMOM_CROSS_ASSET` | ❌ RED | 4/5 | +3,89% (`4/4` rejim +) | +0,62 / +0,46 / +0,26 | -%5,3 / -%9,5 | -%1,51 | 9/9 (%100) | 0,76 *(>=0,70 eşiği)* / +0,74 |

- **Önemli Ayrım:** `V3_TREND_RISK_PARITY_BIL` (`v3_trp`) hem 4/4 makro rejimde pozitif `ExBIL` üreten, hem 2022 ayı piyasasında `+%3,59` pozitif kalan, hem de optimizasyonsuz 50/50 harmanda `Meta-A v2`'nin Sharpe'ını `+0,83 → +0,91`'e çıkarıp MaxDD'sini `-%8,3 → -%5,4`'e düşüren tek adaydır. Yalnızca `v3_trp` bağımsız dondurulmuş sanal defter (`quant_v3_trp.json`) olarak `ForwardRegistry`'ye alınmıştır; `PAA v2` ve `Meta-A v2` parmak izleri değişmemiştir.
- **Faz 0 Yerel `.venv` Gerçek AI Konseyi v2 Sonucu:** E:\ üzerindeki gerçek tüzüklerin `reevaluate` sonucu: Claude (`FAIL`, ExSh -0,05), Codex (`FAIL`, ExSh -0,14), **Gemini (`PASS | PASS_ELITE`, 2022 `+%0,6` vs SPY `-%18,2`, 25 bps ExSh `+0,31`, 50 bps ExSh `+0,16`)**.
