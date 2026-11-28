# Antigravity Devir Notu — Program Durumu ve Yapılacaklar

**Tarih:** 23 Kasım 2026 · **Hazırlayan:** Claude (bulut oturumu)
**Dal:** `feat/cli-mcp-quant-tournament`
**Kurulum:** Kullanıcı `E:\daily_stock_analysis` üzerinde Windows PowerShell 5.1 kullanıyor.

**Uygulama planı:** sırayla yapılacak işler, takvim ve kabul ölçütleri `docs/ANTIGRAVITY_PLAN.md`'dedir.

Bu not `docs/CLAUDE_HANDOVER.md`'nin devamıdır. O dosyanın 3. bölümü, v1.0.0 notundaki doğrulanamayan iddiaların düzeltmelerini içerir; önce onu okuyun. Buradaki her sayı bu oturumda koddan ya da gerçek veriyle yeniden üretildi.

---

## 1. Tek cümlelik durum

Program çalışıyor ve risk yönetimi tarafında güvenilir. Gerçek parayla kazanç sağladığına dair **henüz kanıt yok**:
- strateji sonuçları geçmiş testten geliyor;
- canlı sanal sınav 0/120 günde, en erken **14 Mayıs 2027**'de biter;
- yapay zekâ ile üretilen hisse al/sat sinyallerinin isabeti hiç ölçülmedi.

## 2. Program bugün ne öneriyor? (23 Kasım 2026, gerçek veri)

| Kaynak | Bugünkü öneri | Kanıt düzeyi |
| :--- | :--- | :--- |
| PAA Çöküş Kalkanı | BIL %100 (12 riskli varlıktan 9'u SMA252 altında, `FULL_CRASH_SHIELD`) | Geçmiş test, 2022–26 BIL üstü Sharpe 0,56; ileri sınav 0/120 |
| Meta-Portföy A v2 | BIL %80 · SHY %20 | Geçmiş test 0,73, **ama 2022–26 görülerek ayarlandı**; ileri sınav 0/120 |
| v3_trp (temkinli) | BIL %83 · UUP %17 | Önceden kayıtlı araştırma, 2008–26 BIL üstü Sharpe 0,63, CAGR %3,8; ileri sınav 0/120 |
| Sektör momentumu Top-3 | XLV · XLF · XLE | Geçmiş test 0,27 (zayıf) |
| Faktör rotasyonu | USMV | Geçmiş test 0,33 |
| BIST 52H Düşük-Vol | THYAO · GARAN · YKBNK · PGSUS | USD bazında 0,51; **hayatta kalma yanlılığı var**; 2025–26 dolar bazında kayıpta |
| BIST Momentum | TUPRS | USD bazında 0,33 |
| Kripto trend (BTC/ETH) | %100 nakit | Geçmiş test |
| Yapay zekâ ile hisse analizi (al/sat/tut) | Hisse başına rapor | **İsabet ölçülmedi.** Altyapı var, sonuçlar yalnızca E:\ veritabanında |

Özet: Sistem bugün "kriz modu, nakitte bekle" diyor. Bu bir kâr önerisi değil; sermayeyi koruma önerisi.

## 3. Bu oturumda yapılanlar (sırayla)

| Commit | İçerik |
| :--- | :--- |
| `456436b` | Web'e ileri doğrulama kapısı kartı ve `GET /api/v1/alpha/forward-validation` |
| `f49270b` | BIST getirileri USD'ye çevrildi (`TRY=X`); AI Konseyi v2: 25/50 bps maliyet stresi, 2022 testi ve `reevaluate` komutu |
| `5d4f7ab` | `/simple` ekranında sessiz sabit değerler kaldırıldı (`data_status` eklendi); v3_trp günlük adıma alındı ve dondurulmuş stratejiler her zaman işleniyor; turnuva ve v3 verisi her gün yenileniyor |
| (bu commit) | **Araştırma v4:** ters ETF ile short gerçekten değer katıyor mu? Ayrıca bu not |

### Araştırma v4 sonucu: short değer katmıyor

Kullanıcı short ve opsiyon gibi araçları değerli buluyor. Short fikri, kredili hesap gerektirmeyen ve kaybı yatırılan parayla sınırlı tek güvenli yoldan, ters ETF'lerle test edildi (SH, PSQ, EFZ, TBF). Test ayrıntıları:
- Kural önceden sabitlendi: yükseliş trendinde varlık, düşüş trendinde ters ETF, ikisi de değilse BIL.
- Aynı kuralın short kapalı hâli kontrol grubu olarak kullanıldı.
- Rapor: `docs/STRATEGY_RESEARCH_V4_REPORT.md`; komut: `scripts/run_strategy_research_v4.py`.

| 2008–2026 | Long/Short (ters ETF) | Long-Only Kontrol |
| :--- | ---: | ---: |
| BIL üstü Sharpe (5 / 25 bps) | 0,51 / 0,38 | **0,68 / 0,56** |
| CAGR | %4,4 | **%5,0** |
| En büyük düşüş | −%8,7 | **−%7,6** |
| 2008 / 2022 | **%+17,4 / %+2,5** | %+11,3 / %−1,7 |

- **Yorum:** Short krizde ödüyor, ama yılda −0,30 puan maliyeti var (trend dönüşleri ve ters ETF değer kaybı). Tam bir sigorta gibi: prim pahalı.
- **Kapı tuzağı:** Long/short aday 5/5 kapıyı yalnızca Meta-A ile korelasyonu daha düşük olduğu için geçti. Kontrol grubu olmasaydı yanlış sonuca varılırdı. **Yeni her araştırmada kontrol grubu şart.**
- **Karar:** v4 sanal sınava **alınmadı**. Sürekli tutulan ters ETF felaket olur (SH 2010–2026: %−90).

### 3.1 Araştırma v5 Özeti — Korelasyon-Duyarlı (Min-Corr) Ağırlıklandırma `1/vol`'e Göre Değer Katıyor mu?

- **Ne test edildi (`src/quant/strategies/research_v5.py`, `src/quant/research_v5_lab.py`):** 10 makro ETF (`SPY, QQQ, EFA, EEM, VNQ, TLT, IEF, GLD, DBC, UUP`) + `BIL` üzerinde aynı trend filtresi (`SMA200` + `12A > BIL`) ve aynı `%8` hedef volatilite ile iki aday karşılaştırıldı (kümülatif deneme sayısı `32`):
  - **Min-Corr (`use_corr_penalty=True`):** Aktif varlıkları `max(0.10, 1 - ort_korelasyon) / vol` ile ağırlıklandırır.
  - **Kontrol grubu (`use_corr_penalty=False`):** Aynı kural, yalnızca korelasyon cezası kapalı (saf `1/vol`).
- **Gerçek veri sonucu (2008–2026):**
  - Her iki aday da 5/5 kapıdan geçti (`4/4` rejim pozitif ExBIL, `9/9` komşuluk platosu).
  - Min-Corr hisse kümesi yoğunluğunu `%45,5`'ten `%38,5`'e düşürerek en büyük düşüşü (`-%5,83` vs `-%6,33`) ve 2022 kriz getirisini (`+%1,17` vs `+%0,13`) iyileştirdi.
  - **Ancak** BIL üstü Sharpe'ta `5 bps`'de kontrol grubuyla berabere kaldı (`+0,61` vs `+0,61`, fark `0,00 < +0,05`) ve `25 bps`'de korelasyon kaynaklı ek işlem dönüşü nedeniyle kontrol grubunun gerisine düştü (`+0,43` vs `+0,47`, fark `-0,04`; CAGR `+%3,97` vs `+%4,30`).
- **Karar:** **Hayır (kanıt yetersiz).** Yapısal 3-rejim sepeti (`v3_trp`, `5/25 bps` BIL üstü Sharpe `+0,74/+0,61`) dinamik korelasyon cezasından hem daha basit hem daha yüksek net Sharpe üretiyor. Sanal deftere alınmadı; dondurulmuş 3 strateji (`paa`, `meta_a`, `v3_trp`) korundu.
- **Tam rapor:** `docs/STRATEGY_RESEARCH_V5_REPORT.md` · **Tekrar çalıştırma:** `.venv\Scripts\python.exe scripts\run_strategy_research_v5.py`

## 4. Doğrulanmış teknik durum

- **Testler:**
  - Backend: `pytest -m "not network"` → 6074 geçti, 3 kaldı. Üçü de ortama bağlı:
    - `test_report_schema` içindeki 2 test `.env` dil ayarına bağlı;
    - `test_intelligence_service` paralel çalışmada kararsız.
  - Frontend: 110 dosya, 1127 test geçti; ESLint ve build temiz.
- **Dondurulmuş parmak izleri** (değişmemeli; `tests/test_strategy_research_v4.py` her çalıştırmada kontrol eder):
  - `paa` `87e22a6b3559`
  - `meta_a` `37a7ab36a0d9`
  - `v3_trp` `ae4754108564`
- **Güvenlik kilitleri:** `ALPACA_PAPER=true`, `ALPACA_AUTO_EXECUTE=false`, Binance yalnızca testnet, AlgoLab ve IBKR yalnızca okuma. Kilitler adaptör kodunda zorlanıyor. Zamanlayıcı hiçbir zaman emir göndermiyor. Web'den emir yalnızca sanal hesaba ve açık onayla gidebiliyor.
- **Günlük akış** (`daily_paper_step.ps1` → `quant_paper.py step`):
  - stratejiler `resolve_active_quant_paper_strategies()` ile belirlenir: yapılandırılanlar + dondurulmuş olanlar;
  - sanal defterler ilerler ve ileri doğrulama kapısı değerlendirilir;
  - turnuva ve v3 verisi yenilenir (`docs/` dosyalarına yazmaz).

## 5. Yapılacaklar (öncelik sırasıyla)

### P0 — E:\ üzerinde gerçek durumu ölç (kod yok, yalnızca çalıştır ve raporla)

1. `git pull`, ardından `.venv\Scripts\python.exe scripts\quant_paper.py step`. Çıktıda üç defter (paa, meta_a, v3_trp) ve "Strateji verisi: … yenilendi" satırı görünmeli.
2. `powershell -ExecutionPolicy Bypass -File scripts\windows\daily_paper_step.ps1 -Status`. Zamanlanmış görev kayıtlı mı ve son çalıştırma başarılı mı?
3. **Yapay zekâ sinyal isabetini çıkar:** `.venv\Scripts\python.exe scripts\paper_trading_report.py`. Ayrıca `/paper-trading` sayfasındaki isabet istatistikleri: her grupta tamamlanmış sinyal sayısı, isabet oranı, ortalama yönlü getiri.
   - **Kabul:** Sayılar `docs/HANDOVER_ANTIGRAVITY.md`'ye eklenir. Örnek 30'dan azsa bu açıkça yazılır.
4. `.venv\Scripts\python.exe scripts\run_ai_strategy_council.py reevaluate` ile kullanıcının gerçek konsey tüzüklerinin v2 sonucunu kaydet.

**P0-3 güncellemesi (23 Kasım 2026):**
- **E:\ çıktısı:** `İşlem: 0` ve `160 bekleyen kontrol`, tamamlanan yok.
- **Kök neden:** Değerlendirici fiyatı yalnızca yerel veritabanından okuyordu. Bir kez analiz edilen hissenin sonraki kapanışları hiç kaydedilmediği için kontroller sonsuza kadar sonuçsuz kalıyordu. Rapor da "değerlendirilemedi" durumunu "bekliyor" diye gösteriyordu.
- **Düzeltme:** `evaluate_signal_outcomes()` eksik kapanışları veri sağlayıcısından tamamlıyor; rapor nedenleri ayrı gösteriyor.
- **Sonraki adım:** Kullanıcı `paper_trading_report.py`'yi yeniden çalıştırıp gerçek isabeti bu nota eklemeli.
- **Düzeltme sonrası E:\\ çıktısı:** 160 kontrol = 40 sinyal. 30 sinyal "izle" (120 kontrol), yani yönsüz ve puanlanamaz. 10 yönlü sinyalden 9'u ileri kapanış bekliyor (36), 1'inin sinyal günü fiyatı yok (4). Bulgu: yapay zekâ çoğunlukla yön vermiyor. Ayrıntı için kullanıcıdan `paper_trading_report.py --details` çıktısı istendi.
- **`--details` sonucu (23 Kasım 2026):**
  - Yönlü sinyaller: 9 ABD sinyali (URI, AMD, PANW), hepsi 20 Kasım Cuma tarihli. Bekliyorlar, çünkü Pazartesi kapanışı henüz oluşmadı; bu doğru davranış.
  - 588200 (Çin ETF'i): 22 Kasım Pazar sinyali. Hafta sonu için Cuma kapanışı başlangıç fiyatı olarak kullanılmaya başlandı.
  - Tekrarlar: Aynı gün URI ×4, AMD ×3, PANW ×2 sinyal vardı. Rapor istatistiğinde artık tek sayılıyor.
  - Sinyal dağılımı: izle 30, azalt 8, al 1, sat 1. Yapay zekâ kriz rejiminde çok temkinli.
- **Kontrol edilmesi gerekenler (eski):** Sinyal günü fiyatı olmayan sinyal hafta sonu ya da tatil gününe mi bağlı? Eğer öyleyse anchor kuralı upstream'de bilinçli olarak "tam gün" seçilmiş; değiştirmeden önce upstream sözleşmesini (`get_daily_on_date`) değerlendirin. Bekleyen 9 sinyal gerçekten son günlerden mi?
- **`İşlem: 0` neden:** Sinyallerden sanal işlem açılması isteğe bağlı (`PAPER_TRADING_ENABLED=false` varsayılan).

### P1 — Al/sat sinyallerinin değerini kanıtla ya da göster

- **Karşılaştırma:** P0-3'te yeterli örnek varsa yapay zekâ "al" sinyallerinin 5 ve 10 günlük getirisini aynı günlerde endeksle (BIST için XU100, ABD için SPY) ve rastgele hisse seçimiyle kıyasla.
  - **Kabul:** Rapor, endeks üstü fark ve güven aralığıyla verilir.
  - **Fark anlamlı değilse:** Web'de sinyallerin yanına "isabeti kanıtlanmadı" etiketi konur.
- **Görünürlük:** Sinyal isabetini `/simple` ekranında sade dille göster: "Son 30 al sinyalinin %X'i 10 günde endeksi geçti."

### P2 — Teknik borç

- **İzlenen raporlar:** `scripts/run_strategy_tournament.py`, `run_strategy_research_v3.py` ve `run_strategy_research_v4.py` elle çalıştırılınca repoda izlenen `docs/*_REPORT.md` dosyalarını yazıyor. Bu E:\'de `git pull` çakışmasına yol açıyor (kullanıcı bunu yaşadı).
  - **Öneri:** Varsayılan olarak `data/reports/` altına yaz; `docs/` yalnızca `--publish` ile güncellensin.
- **Ortama bağlı testler:** `test_report_schema` testleri dil ayarını kendisi belirlemeli, `.env`'e bağlı kalmamalı.
- **Kullanılmayan import'lar:** `src/quant/strategies/engine.py` (`asdict`) ve `src/quant/tournament.py` (`US_ETF_SAFE_ASSETS`).
- **v4 sonucu web'de görünmüyor:** Turnuva sekmesine küçük bir "Short testi: değer katmıyor" kartı eklenebilir. Yalnızca okuma yapan bir uç (`research_v4_latest.json`) yeterli.

### P3 — Opsiyon ve gerçek short (şimdilik yapılmamalı)

- **Gerçek açığa satış:** Kredili hesap ve ödünç pay gerektirir; teorik kayıp sınırsızdır. Bu programın hedef kullanıcısına (yeni başlayan) uygun değil. Ters ETF testi bile short'un toplamda değer katmadığını gösterdi.
- **Opsiyonlar** (koruyucu put, covered call):
  - Güvenilir geçmiş opsiyon fiyatı ücretsiz değil; yfinance yalnızca güncel zinciri verir.
  - Black-Scholes ile sentetik geçmiş üretmek, ölçmeyi değil uydurmayı test eder.
  - **Önkoşullar:**
    1. İleri sınav PASS (en erken 14 Mayıs 2027);
    2. ücretli geçmiş opsiyon verisi (ör. OptionMetrics, ORATS);
    3. Alpaca paper opsiyon hesabı.
  - O zaman ilk aday: "kriz anında koruyucu put" ile "BIL'de bekleme"yi aynı kapılarla kıyaslamak.
- **Kaldıraçlı ETF'ler** (2x veya 3x): Önerilmez. Günlük sıfırlama kaybı ters ETF'lerden daha büyüktür.

### Takvim

- **14 Mayıs 2027:** 120 işlem günlük ileri sınavın en erken bitişi. Kapı geçilmeden `ALPACA_PAPER` ve `ALPACA_AUTO_EXECUTE` kilitleri açılmaz.
- **Ara değerlendirme:** Kapı her gün kendini değerlendirir. MaxDD −%18'i aşarsa sınav erken "kaldı" olur.

## 6. Kurallar (bozulmamalı)

1. `src/quant/strategies/library.py` ve `research_v3.py` içinde dondurulmuş fonksiyonlara, eriştikleri yardımcı fonksiyonlara ve sabitlere dokunmayın. Dokunursanız kayıt `INVALIDATED` olur. Yeni araştırma ayrı modülde yapılır (örnek: `research_v4.py`).
2. Yeni strateji önceden sabitlenmiş parametrelerle, kontrol grubuyla ve aynı 5 kapıyla değerlendirilir. Sonucu görüp parametre değiştirmek yasak; değiştirirseniz kümülatif deneme sayısını artırın.
3. Commit mesajları İngilizce olur ve `Co-Authored-By` içermez. `CHANGELOG [Unreleased]` düz liste biçiminde tutulur. Yeni yapılandırma eklerseniz `.env.example` ve doküman güncellenir.
4. Windows'ta komutlar `.venv\Scripts\python.exe` ile çalıştırılır; sistem Python'unda bağımlılıklar eksik. PowerShell 5.1 `&&` desteklemez; komutlar ayrı satırlarda yazılır.
5. Doğrulama komutları:
   - `python -m pytest -m "not network"`
   - `cd apps/dsa-web`, ardından `npm run lint` ve `npm run build`
   - `python scripts/check_ai_assets.py` (AI yönetim dosyaları değişirse)

---

## 7. E:\ ölçüm kaydı — 2026-11-23

| Komut | Çıkış | Özet ve önemli ham satırlar |
| :--- | :---: | :--- |
| G0.1 `git pull` | 0 | Fast-forward (`aafa1f1..a45344c`), çakışma yok. |
| G0.2 `pytest tests/test_strategy_research_v4.py -q` | 0 | `8 passed in 18.02s`; dondurulmuş parmak izleri doğrulandı. |
| G0.3 `scripts\quant_paper.py step` | 0 | 6 defter işlendi: `paa` `$10,023.25` (%+0.23, hedef `BIL %100.0`), `meta_a` `$10,009.81` (%+0.10, hedef `BIL %80.0 · SHY %20.0`), `v3_trp` `$9,995.00` (%-0.05, `BIL %83.3 · UUP %16.7`), AI Konseyi 3 defter güncel. `Strateji verisi: Strateji turnuvası: güncel (3.3 saat önce yenilenmiş) \| v3 araştırması: güncel (3.3 saat önce yenilenmiş)`. |
| G0.4 `daily_paper_step.ps1 -Status` | 0 | Görev: `DailyStockAnalysis-DailyPaperStep` (`Ready`), Son çalıştırma: `2026-11-23 19:09:15`, `Last Result: 0`, Sonraki: `2026-11-24 00:30:00`. Kripto trend: `$10,000.00` (%100 nakit, BTC `$61,271.08`, ETH `$1,724.33`, 0/5 SMA). |
| G0.5 `scripts\quant_forward.py status` | 0 | Üç strateji de `2026-11-20` tarihinde dondurulmuş (`paa`: `87e22a6b3559`, `meta_a`: `37a7ab36a0d9`, `v3_trp`: `ae4754108564`), ileri gün `0/120` (ilk kapanış bekleniyor). |
| G0.6 `run_ai_strategy_council.py reevaluate` | 0 | `Claude Code CLI` (`vol_target_trend`): `FAIL` (`FAIL_WEAK`, OOS Ex-BIL Sharpe `-0.05`, 25 bps `-0.21`); `OpenAI Codex CLI` (`vol_target_trend`): `FAIL` (`FAIL_WEAK`, OOS Ex-BIL Sharpe `-0.14`, 25 bps `-0.27`); `Google Gemini CLI` (`paa_custom`): `PASS` (`PASS_ELITE`, OOS CAGR `+8.4%`, Ex-BIL `+4.5%`, Sharpe `+0.42`, MaxDD `-14.4%`, 25 bps Sharpe `+0.31`, 2022 ayı `+%0.6` vs SPY `-18.2%`). |
| G0.7 `paper_trading_report.py --details` | 0 | `İşlem: 0 \| Açık: 0 \| Kapanan: 0`. `Sinyal isabeti (±%2 nötr bant): 1 değerlendirme \| isabet n/a (0 doğru / 0 yanlış / 1 nötr) \| ort. getiri +0.86%`. Sinyal dağılımı: `izle 30, azalt 8, al 1, sat 1` (tekrar eden 108 kontrol birleştirildi). `#40 588200 al` (2026-11-22 Paz) 1d nötr (`+0.86%`), 3d/5d/10d bekliyor; 9 ABD sinyali (`URI`, `AMD`, `PANW` — 2026-11-20 Cum) Pazartesi kapanışı bekliyor. Not: `588200` çekilirken `efinance`/`akshare`/`pytdx` uyarı/hata logları çıktı. |

### 2026-11-24 — İleri sınav 1/120. gün kaydı

- **Otomatik görev (`DailyStockAnalysis-DailyPaperStep`):** `2026-11-24 20:50:22` tarihinde otomatik çalıştı (`Last Result: 0`).
- **`scripts\quant_forward.py status`:** Dondurulmuş 3 strateji de **`1/120`** ileri işlem gününe (`2026-11-20 → 2026-11-23`) ulaştı (parmak izleri korundu):
  - **PAA (korumacı varlık dağılımı):** `1/120 gün | getiri %-0.05 (SPY %+4.71)` (`$10,018.34`, en büyük düşüş `%-0.1`)
  - **Meta-A (%55 PAA + %45 çift momentum):** `1/120 gün | getiri %+0.16 (SPY %+4.71)` (`$10,025.42`, en büyük düşüş `%0.0`)
  - **Araştırma v3 — Üçlü rejim portföyü (`v3_trp`):** `1/120 gün | getiri %+0.10 (SPY %+4.71)` (`$10,004.91`, en büyük düşüş `%-0.1`)
- **`scripts\paper_trading_report.py --details`:** `2026-11-20` tarihli ABD `azalt` sinyallerinin (`URI`, `AMD`, `PANW`) `1d` kontrolü tamamlandı; aynı gün tekrarlanan sinyaller detay listesinde ve haftalık izle oranında da tekilleştirildi, 10 günlük ufuk dolana kadar `1g ön izleme` endeks karşılaştırma satırı eklendi.

### 2026-11-25 — AI Sinyal Güvenilirliği Sertleştirme ve Walk-Forward (%80 Kabul Kapısı) Doğrulaması

- **Fail-Closed Güvenilirlik & Risk Kapısı:**
  - `src/services/signal_reliability_gate.py` eklendi (`SIGNAL_RELIABILITY_GATE_ENABLED=false` varsayılan korumalı opt-in); RiskAgent bozulması, bayat intraday veri, eksik/`R/R < 1.5` fiyat planı veya trend çelişkisinde `buy`/`add` sinyallerini `watch`'a düşürür ve sanitize edilmiş `diagnostic_summary` ekler (`adr-0001`).
  - `src/services/quant_risk_gate.py` BIST (`*.IS` → `XU100.IS`) ve ABD (`SPY`/`^VIX`) rejim/kıyas ayrımı yapacak şekilde güncellendi; `quant_gate_enabled=True` iken bar/skor eksikse artık sessizce izin vermek yerine `quant_score_unavailable_fail_closed` ile engeller (`adr-0002`).
  - `src/brokers/binance/adapter.py` ve `src/services/paper_trading_service.py` içindeki sessiz hata yutma noktaları `logger.warning` + `data/broker_audit.jsonl` kaydına bağlandı; `src/brokers/registry.py` içine salt-okunur `run_broker_dry_run_reconciliation()` eklendi.
- **İzole Walk-Forward Doğrulama (`scripts\run_signal_walkforward.py --cost-bps 10`):**
  - Dondurulmuş `library.py` / `research_v3.py` parmak izlerine dokunulmadan gerçek ABD ETF verisiyle (`2018–2021` IS, `2022+` 6 aylık OOS pencereleri) koşuldu → Karar **`UNPROVEN`** (`N=86`, Precision `56.98% < %80.0`, CI alt `47.7% <= %65.0`, Endeks geçme `37.87%`, Net PF `1.13 < 1.50`, MaxDD `-7.52%`). Yönlü AI sinyal doğruluk hedefi (%80) henüz kanıtlanmamıştır; `ALPACA_PAPER=true` ve `ALPACA_AUTO_EXECUTE=false` kilitleri korunur.

### 2026-11-27 — Ondalık Ölçek Koruması, Watchlist Birleştirme ve Kapanış Barı Eşitlemesi

- **`US_SCREENER` + `STOCK_LIST` Birleştirme (`2243a38f`):** `SCREENER_MERGE_WITH_STOCK_LIST=true` (`src/config.py`, `_merge_screener_stock_codes()` in `main.py`) ile `US_SCREENER_ENABLED=true` açıkken bile `STOCK_LIST` ezilmez; canlıda `43` `STOCK_LIST` + `4` ABD tarama adayı = `47/47` sembol üretildi (`86 passed`).
- **Türkçe Ondalık Virgülü & Ölçek Sapma Koruması:**
  - `src/utils/sniper_points.py` (`parse_sniper_value`) `"152,28 TL"`, `"248,67 USD"`, `"1.234,56 TL"` gibi yerel ondalık virgülleri binlik ayırıcı sanıp `×100` büyütmeyecek şekilde düzeltildi; `decision_signal_extractor.py` ham sayısal `×100` sapmalarını normalize eder (`sniper_scale_normalized_fields`), `signal_reliability_gate.py` ise referans fiyata göre `>4x` / `<0.25x` planları `price_plan_scale_mismatch` ile `watch`'a çeker. Önceki 7 kaydın ham JSON tekrar çözümlemesi `7/7` doğrulandı (`PGSUS.IS` `152.28`, `AMZN` `248.67`, `TOST` `33.0` vb.).
- **Otomatik Kapanış Barı Eşitlemesi (`--sync-bars`):**
  - `src/services/paper_trading_benchmark.py` (`sync_signal_and_watchlist_bars()`), `scripts/paper_trading_report.py --sync-bars` ve `scripts/windows/daily_paper_step.ps1` güncellendi; LLM maliyeti olmadan bekleyen sinyal + `STOCK_LIST` + `XU100.IS`/`SPY` barlarını yeniler. Canlı test: `[sync-bars] requested=48 synced=48 rows=645 failed=0`; `228 passed` (`pytest` 10 modül).

### 2026-11-28 — 32 Satır DB Onarımı (Adım A) ve İzole `AGENT_MODE=true` A/B Testi (Adım B)

- **Adım A (`stock_analysis.db` Onarımı):**
  - `sniper_points.py` içine `;` öncesi para birimi önceliği, ISO tarih (`2026-11-23`) ve yüzde (`%0,6` / `%2`) temizleme eklendi; `stock_analysis.db.bak-20261128` (`11,1 MB`) yedeği alındıktan sonra `decision_signals` içinde `32` ve `analysis_history` içinde `32` hatalı ölçekli kayıt (`1040.0 URI`, `1386.44 LLY`, `480.13 MSFT`, `292.72/304.0 NET`, `152.28 PGSUS.IS`, `321.96 ASELS.IS` vb.) onarıldı → taramada kalan ölçek dışı satır **`0`**.
- **Adım B (`AGENT_MODE=true` + `AGENT_ARCH=multi` + Yerel `ollama/qwen3:8b` Sanal A/B Testi):**
  - `litellm 1.108.3`'ün kurulu olmayan `mcp` paketini araç çağrılarında import etmesini önleyen `_should_skip_litellm_mcp_handler()` (`_skip_mcp_handler=True`, `src/agent/llm_adapter.py`) eklendi (yeni paket eklemeden yerel Ollama araç çağrısı çalıştırıldı).
  - İzole kopya DB üzerinde `THYAO.IS`, `AAPL`, `NVDA` koşturuldu: `THYAO.IS` (`60s`, `watch 52`, `plan_quality=minimal`) ve `AAPL` (`174s`, `watch 58`, `plan_quality=partial`, `diagnostic_summary` tam) tamamlanırken, `NVDA` `max_steps=6` sınırına takılarak fail etti; `RiskAgent` ise eksik alt-ajan kanıtı nedeniyle `no_risk_evidence` geçildi.
  - **Karar:** Tekil `gemini_cli` modu tüm test hisselerinde `plan_quality='complete'` ürettiği için `.env` varsayılanı şimdilik **`GENERATION_BACKEND=gemini_cli` + `AGENT_MODE=false`** bırakıldı; Pazartesi (`2026-11-30`) kapanışlarıyla `2026-11-27`'de üretilen `12` yönlü sinyalin `1g/3g/5g/10g` sonuçları izlenecek.


