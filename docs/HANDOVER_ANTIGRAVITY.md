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
