# Türkiye & Küresel Veri / Aracı Kurum Köprüleri (`v1.0.0`)

Bu belge, Faz 8–10 kapsamında eklenen Türkiye yerelleştirme katmanı (TEFAS, TCMB EVDS2, Midas CSV/XLSX), Binance Spot Testnet sanal işlem köprüsü ve birleşik `BrokerAdapter` mimarisini açıklar.

---

## 1. Güvenlik Mimarisi ve Değişmez Kilitler

Tüm aracı kurum ve borsa bağlantıları (`src/quant/adapters/` ve `src/quant/alpaca_bridge.py`) **varsayılan olarak sanal (paper/testnet) veya salt-okunur (read-only)** modda çalışır:

| Köprü / Adaptör | Varsayılan Ortam Değişkenleri | Gerçek Para Kilidi |
| :--- | :--- | :--- |
| **Alpaca (ABD ETF)** | `ALPACA_PAPER=true`, `ALPACA_AUTO_EXECUTE=false` | `ALPACA_LIVE_TRADING_CONFIRMED=true` olmadan gerçek hesaba bağlanmaz; zamanlayıcı asla emir göndermez. |
| **Binance Spot Testnet** | `BINANCE_TESTNET=true`, `BINANCE_AUTO_EXECUTE=false` | Yalnızca `https://testnet.binance.vision` uç noktasını kullanır; `testnet.binance.vision` dışındaki tüm host'lar kod seviyesinde (`ValueError`) reddedilir. |
| **Denizbank AlgoLab (BIST)** | `ALGOLAB_READ_ONLY=true` | Salt-okunur pozisyon/fiyat adaptörü; canlı emir gönderimi kapalıdır. |
| **Interactive Brokers (IBKR)** | `IBKR_READ_ONLY=true` | Salt-okunur Web API adaptörü; canlı emir gönderimi kapalıdır. |
| **Midas (BIST + ABD)** | Dosya İçe Aktarma (`CSV` / `XLSX`) | Midas'ın halka açık bireysel işlem API'si bulunmadığından ekstre içe aktarma ve emir kartı kopyalama köprüsü kullanılır. |

---

## 2. REST API Uç Noktaları (`/api/v1/bridges/*` ve `/api/v1/alpha/*`)

### A. Tüm Köprülerin Canlı Durumu
- **`GET /api/v1/bridges/status`**
  - Modül: `src/quant/adapters/registry.py` → `get_all_bridges_status()`
  - Döndürdüğü alanlar: `adapters` (`alpaca_paper`, `binance_testnet`, `midas_import`, `tefas_funds`, `tcmb_evds`, `algolab_bist`, `ibkr_readonly`), yapılandırma durumu, `paper_only` / `read_only` bayrakları ve Türkçe durum notları.

### B. Binance Spot Testnet Köprüsü (`src/quant/adapters/binance_testnet.py`)
- **`GET /api/v1/bridges/binance/plan`**
  - `CRYPTO_5SMA_ENSEMBLE` (BTC & ETH 50/100/150/200/250-günlük SMA topluluğu) sinyallerini canlı/önbellek fiyatlarla hesaplar ve hedef Testnet dağılımını (`BTCUSDT`, `ETHUSDT`, `USDT`) oluşturur.
- **`POST /api/v1/bridges/binance/submit-testnet`**
  - İstek gövdesi: `{"notional_usdt": 1000.0, "confirm_testnet": true, "dry_run": true}`
  - `dry_run=true` iken emirleri simüle eder; `dry_run=false` ve Testnet API anahtarları tanımlıysa yalnızca `https://testnet.binance.vision/api/v3/order` adresine sanal Testnet emri gönderir ve beklenen fiyat ile gerçekleşen dolum arasındaki kaymayı (`slippage_bps`) ölçer.

### C. TEFAS Yatırım Fonu Köprüsü (`src/data/tefas_client.py`)
- **`GET /api/v1/bridges/tefas/summary?category=Para+Piyasası`**
  - ABD ETF koruma/büyüme varlıklarını (`BIL`, `SHY`, `IEF`, `TLT`, `GLD`, `SPY`, `QQQ`) Türkiye'deki tüm banka ve aracı kurumlardan alınabilen **TEFAS** fon kategorileriyle (*Para Piyasası Fonu*, *Kısa Vadeli Borçlanma*, *Altın Fonu*, *Eurobond Fonu*, *Yabancı Hisse Senedi Fonu*) eşleştirir.
  - Canlı TEFAS HTTP sorgusu başarısız olursa veya çevrimdışı ortamda çalışılıyorsa, yerleşik referans fon kataloğuna (`CURATED_TEFAS_FUNDS`) kesintisiz (fail-open) geçiş yapar.

### D. TCMB EVDS2 Makro & Enflasyon Köprüsü (`src/data/tcmb_evds_provider.py`)
- **`GET /api/v1/bridges/macro/tr`**
  - `USD/TRY` kuru, yıllık TÜFE enflasyonu (`TP.FE.OKTG01`) ve TCMB politika faizi özetini döndürür.
  - `EVDS_API_KEY` ortam değişkeni tanımlıysa TCMB EVDS2 resmi API'sinden (`https://evds2.tcmb.gov.tr/service/evds/`) çeker; tanımlı değilse yerel/Yahoo Finance `USDTRY=X` fiyat önbelleği ve referans makro göstergelerle çalışır.

### E. Midas BIST & ABD Ekstre İçe Aktarıcı (`src/services/import_parser.py`)
- **`POST /api/v1/portfolio/imports/csv/parse`** (`broker=midas_bist` veya `midas_us`; desteklenen aracı kurumlar `GET /api/v1/portfolio/imports/csv/brokers`, örnek şablon `GET /api/v1/portfolio/imports/csv/template`)
  - Midas Türkçe (`Sembol / Hisse Kodu`, `İşlem Tipi: Alış/Satış`, `Adet`, `Birim Fiyat`, `Para Birimi`, `Tarih`) ve İngilizce sütun başlıklarını, Türkçe sayı biçimlerini (`1.234,56`) ve BIST/ABD pazar ayrımını otomatik tanır.

### F. Sade Yatırımcı Özeti ve QuantStats Görsel Tearsheet
- **`GET /api/v1/alpha/simple-brief`** (parametre almaz; bütçe hesabı tarayıcıda yapılır)
  - `/simple` ekranını besleyen trafik lambası rejimi, sade Türkçe özet, sepet ağırlıkları (ABD ETF + TEFAS karşılıkları), 19 yıllık kriz karnesi ve 120 günlük canlı ileri doğrulama durumunu tek pakette döndürür.
  - `data_status` (`ok` / `stale` / `partial` / `missing`) hangi strateji verisinin eksik ya da 5 günden eski olduğunu söyler. Veri yoksa `weather.status=unknown`, `protection_pct=null`, `usdtry_rate=null` döner ve ilgili sepetler listelenmez.
- **`GET /api/v1/alpha/tearsheet?strategy=meta_a&mode=backtest`**
  - `src/quant/tearsheet.py` tarafından hesaplanan aylık getiri ısı haritası (`monthly_matrix`), düşüş eğrisi (`underwater`, strateji vs `SPY`), en iyi/en kötü aylar, kârlı ay oranı ve 1 yıllık `USD vs TL vs TÜFE` reel alım gücü kıyasını döndürür.

---

## 3. MCP Araçları (Claude / Gemini CLI & AI Copilot)

MCP sunucusu (`python main.py --mcp-serve`) üzerinden tüm strateji, ileri doğrulama, tearsheet ve köprü verileri doğrudan sorgulanabilir:
- `dsa_get_strategy_tournament`
- `dsa_get_paa_allocation`
- `dsa_get_quant_paper_book`
- `dsa_step_quant_paper_book`
- `dsa_get_forward_validation`
- `dsa_get_crypto_trend`
- `dsa_list_high_alpha_us`
- `dsa_list_bist_Notify_and_alpha`
