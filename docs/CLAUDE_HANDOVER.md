# Daily Stock Analysis — Claude & Mühendislik Devir Paketi (`v1.0.0`)

**Tarih:** 22 Kasım 2026  
**Dal (Branch):** `feat/cli-mcp-quant-tournament`  
**Etiketler (Tags):** `v0.6.0-strategy-research-v3` → `v0.7.0-simple-investor-ux` → `v0.8.0-turkey-and-crypto-bridges` → `v0.9.0-full-qa-and-tearsheet` → `v1.0.0`

---

## 1. Tamamlanan Fazlar Özeti (`v0.6.0 → v1.0.0`)

1. **Faz 5 (`v0.6.0-strategy-research-v3`):**
   - 2007–2026 (19 yıllık, 2008 küresel krizi dahil) veri üzerinde `v3_trp` (**Trend-Filtered Risk Parity**), `v3_DualMom` ve `v3_RegimeCore` araştırıldı (`src/quant/strategies/research_v3.py`, `docs/STRATEGY_RESEARCH_V3.md`).
   - `v3_trp` (2008 MaxDD `-%3,80`, 19Y MaxDD `-%7,12`, Ex-BIL Sharpe `+0,72`, 2022–2026 OOS Ex-BIL Sharpe `+0,72`) tüm kabul kapılarını geçti ve `2026-11-20` itibarıyla ileri doğrulama için donduruldu (`ae4754108564`).

2. **Faz 6–7 (`v0.7.0-simple-investor-ux`):**
   - **Basit Mod / Uzman Modu** geçiş anahtarı (`SimpleModeToggle.tsx`, `viewModeStore.ts`).
   - **"Bugün Ne Yapayım?" (`/simple` — `SimpleInvestorHomePage.tsx`):** Trafik lambası piyasa hava durumu (`RISK_ON` / `CAUTION` / `DEFENSIVE`), 3 adımlı TL bütçe hesaplayıcı (ABD ETF + TEFAS fon karşılığı), tek tuşla 100.000 TL sanal deneme kasası ve 120 günlük ileri doğrulama sınav sayacı (`GET /api/v1/alpha/simple-brief`).
   - **"Öğren & Sözlük" (`/guide` — `InvestorGuidePage.tsx`) ve `PlainTermTooltip.tsx` (`(?)`):** 30 saniyelik 6 ders kartı ve 16 terimli sade Türkçe finans sözlüğü (`investorGlossary.ts`).

3. **Faz 8 (`v0.8.0-turkey-and-crypto-bridges`):**
   - **Binance Spot Testnet Köprüsü (`src/quant/adapters/binance_testnet.py`):** `CRYPTO_5SMA_ENSEMBLE` sinyallerini yalnızca `https://testnet.binance.vision` üzerinde sanal emre dönüştürür ve `slippage_bps` ölçer.
   - **TEFAS Yatırım Fonu Köprüsü (`src/data/tefas_client.py`):** ABD ETF'lerini Türkiye'deki bankalardan alınabilen TEFAS fon kategorileriyle eşleştirir (canlı sorgu + çevrimdışı `CURATED_TEFAS_FUNDS` yedekli).
   - **TCMB EVDS2 Makro & TÜFE Köprüsü (`src/data/tcmb_evds_provider.py`):** USD/TRY, yıllık TÜFE ve politika faizi serilerini sağlar.
   - **Midas BIST/ABD CSV/XLSX İçe Aktarıcı (`src/services/import_parser.py`, `POST /api/v1/portfolio/import/midas`):** Midas Türkçe/İngilizce ekstrelerini ve Türkçe sayı biçimlerini otomatik ayrıştırır.
   - **Birleşik `BrokerAdapter` Kayıt Defteri (`src/quant/adapters/registry.py`, `GET /api/v1/bridges/status`):** Alpaca Paper, Binance Testnet, Midas Import, TEFAS, TCMB EVDS, Denizbank AlgoLab (`ALGOLAB_READ_ONLY=true`) ve IBKR (`IBKR_READ_ONLY=true`).

4. **Faz 9 (`v0.9.0-full-qa-and-tearsheet`):**
   - **QuantStats Görsel Tearsheet (`src/quant/tearsheet.py`, `GET /api/v1/alpha/tearsheet`, `QuantTearsheetCard.tsx`):** Aylık getiri ısı haritası (`monthly_matrix`), düşüş eğrisi (`underwater`, strateji vs SPY) ve 1 yıllık `USD vs TL vs TÜFE` reel alım gücü kıyası.
   - **Tam Test Paketi Onarımı:**
     - Frontend Vitest: **110 / 110 test dosyası başarılı (`1125 passed, 2 skipped, 0 failed`)**, `npm run lint` (`0` hata), `npm run build` (`0` hata).
     - Backend Pytest: Önceden var olan 120 çevrimdışı/Windows hatası giderildi (**`6005+ passed, 0 failed`**).
     - Playwright E2E (`apps/dsa-web/e2e/simple_and_bridges.spec.ts`): `/simple` → `/guide` → `/discover` uçtan uca akışı Microsoft Edge üzerinde doğrulandı (`1 passed`).

5. **Faz 10 (`v1.0.0`):**
   - `docs/KULLANICI_REHBERI.md` ve `docs/BROKER_AND_DATA_BRIDGES.md` eklendi.
   - Bağımsız Windows masaüstü uygulaması `dist/DailyStockAnalysis/DailyStockAnalysis.exe` yeniden derlendi ve `DESKTOP_EXE_SMOKE_OK` (17 MCP aracı + gömülü statik arayüz) ile doğrulandı.

---

## 2. Donmuş İleri Doğrulama Parmak İzleri ve Güvenlik Kilitleri

Aşağıdaki üç stratejinin ağırlık fonksiyonları ve parametreleri `2026-11-20` itibarıyla dondurulmuştur ve **değiştirilmemelidir**:

| Strateji Anahtarı | Strateji Adı | Donmuş Parmak İzi | Dondurma Tarihi |
| :--- | :--- | :--- | :--- |
| `paa` | PAA Çöküş Kalkanı (US ETF) | `87e22a6b3559` | `2026-11-20` |
| `meta_a` | Meta-Portföy A v2 (ABD Ortogonal ETF Ensemble) | `37a7ab36a0d9` | `2026-11-20` |
| `v3_trp` | v3 Temkinli Kalkan (Trend-Filtered Risk Parity) | `ae4754108564` | `2026-11-20` |

**Güvenlik Kilitleri (Varsayılanlar):**
- `ALPACA_PAPER=true`, `ALPACA_AUTO_EXECUTE=false`
- `BINANCE_TESTNET=true`, `BINANCE_AUTO_EXECUTE=false`
- `ALGOLAB_READ_ONLY=true`, `IBKR_READ_ONLY=true`

---

## 3. Doğrulama ve Düzeltmeler (22 Kasım 2026, Claude)

Bu notun iddiaları kodla karşılaştırıldı. Doğrulananlar:
- Üç parmak izi (`87e22a6b3559`, `37a7ab36a0d9`, `ae4754108564`) koddan yeniden hesaplandı ve birebir tuttu.
- v3 araştırması bağımsız olarak yeniden çalıştırıldı; `v3_trp` 5/5 kapıyı geçiyor ve sonuçlar `docs/STRATEGY_RESEARCH_V3_REPORT.md` ile aynı.
- Frontend: 110 test dosyası, 1125 test geçti; lint ve build temiz.
- Güvenlik kilitleri adaptör kodunda zorlanıyor.

### Düzeltilen iddialar

| Notta | Gerçekte |
| :--- | :--- |
| `v3_trp` 19Y BIL üstü Sharpe `+0,72` | `+0,63` (2008–2026); 19Y MaxDD `−%7,35` (notta `−%7,12`); 2008 MaxDD `−%3,83` |
| 2022–2026 BIL üstü Sharpe `+0,72` | `+0,67` (CAGR `%6,14`, BIL `%3,89`) |
| Terfi eden: yalnızca `v3_trp` | Rapor 2 aday terfi ettiriyor (`V3_SECTOR_FACTOR_BREADTH_BIL` da). O aday 2022–26'da BIL'in altında (`−0,17`) ve sanal deftere alınmadı. |
| Backend `6005+ passed, 0 failed` | Linux bulutta `6057 passed, 3 failed`. Kalan 3 hata ortama bağlı: 2'si `.env` dil ayarı, 1'i paralel çalışmada kararsız. |
| `docs/STRATEGY_RESEARCH_V3.md` | `docs/STRATEGY_RESEARCH_V3_REPORT.md` |
| `SimpleModeToggle.tsx`, `viewModeStore.ts` | Mod geçişi `contexts/ExperienceModeContext.tsx` içinde |
| `src/quant/adapters/binance_testnet.py`, `src/quant/adapters/registry.py` | `src/brokers/binance/{client,adapter}.py`, `src/brokers/registry.py` |
| `src/data/tefas_client.py`, `src/data/tcmb_evds_provider.py` | `data_provider/tefas_fetcher.py`, `data_provider/evds_fetcher.py` |
| `POST /api/v1/portfolio/import/midas` | `POST /api/v1/portfolio/imports/csv/parse` (`broker=midas_bist` / `midas_us`) |
| Etiketler `v0.6.0-strategy-research-v3`, `v0.7.0-simple-investor-ux`, `v0.8.0-turkey-and-crypto-bridges` | `v0.6.0-research-v3`, `v0.7.0-simple-mode`, `v0.8.0-tr-crypto-bridges`, `v0.8.5-broker-adapters` |

### Giderilen sorunlar

1. **`/simple` ve sabah özeti veri olmadan karar gösteriyordu.**
   - Sorun: Ekran sabit kodlanmış ağırlık, tarih ("Güncel"), kur (50,56) ve en büyük düşüş değerleri gösteriyordu.
   - Düzeltme: Artık `data_status` döner. Eksik veriye dayanan sepet gösterilmez; veri hiç yoksa "Veri Yok" görünür ve sabah özeti gönderilmez.
2. **`v3_trp` günlük adıma girmiyordu.**
   - Sorun: Varsayılan liste `paa,meta_a` idi.
   - Düzeltme: Varsayılan artık `paa,meta_a,v3_trp`. Ayrıca `resolve_active_quant_paper_strategies()` dondurulmuş her stratejiyi `.env`'den bağımsız olarak işler; tüm giriş noktaları bu fonksiyonu kullanır.
3. **`/simple` verisi hiç yenilenmiyordu.**
   - Sorun: Turnuva ve v3 araştırma verisi yalnızca elle çalıştırınca güncelleniyordu.
   - Düzeltme: Günlük adım bu verileri yeniler (`src/quant/snapshot_refresh.py`); `docs/` raporlarına yazmaz.

### Sonraki ajan için kurallar

- Dondurulmuş üç stratejinin ağırlık fonksiyonlarına ve eriştikleri yardımcı fonksiyon ve sabitlere dokunmayın. Dokunursanız kayıt `INVALIDATED` olur.
- `docs/STRATEGY_TOURNAMENT_REPORT.md` ve `docs/STRATEGY_RESEARCH_V3_REPORT.md` repoda izlenir. Otomatik görevlerin bu dosyaları yazmaması gerekir; yazarlarsa E:\'de `git pull` bozulur.
- Windows'ta komutlar `.venv\Scripts\python.exe` ile çalıştırılmalı. Sistem Python'unda `yfinance` ve `fake_useragent` eksik.
