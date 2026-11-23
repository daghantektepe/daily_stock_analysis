# Kişisel Kurulum Rehberi — Borsa İstanbul (BIST) + Türkçe Rapor

Bu rehber, sistemi **kendi bilgisayarında, kişisel kullanım için** çalıştırmayı anlatır: Claude / Gemini aboneliklerini ve Codex CLI'yi API anahtarı olmadan kullanmak, Grok'u isteğe bağlı eklemek, hassas işleri Ollama ile yerelde tutmak.

> Bu sistem yatırım tavsiyesi vermez. Çıktılar yapay zekâ tarafından üretilir ve hatalı olabilir. Önerilerin başkalarıyla paylaşılması (kanal, abonelik vb.) Türkiye'de SPK'nın yatırım danışmanlığı düzenlemelerine takılabilir; bu rehber yalnızca kişisel kullanımı hedefler.

## 1. Mimari: hangi model ne iş yapar?

| Sıra | Model | Nasıl bağlanır | Ne iş yapar |
|------|-------|----------------|-------------|
| 1 | **Claude** (Pro abonelik) | Claude Code CLI (`GENERATION_BACKEND=claude_code_cli`) | Ana günlük analiz |
| 2 | **Gemini** (Pro abonelik) | Gemini CLI (`gemini_cli`, deneysel) | Claude limiti dolarsa / hata verirse 1. yedek |
| 3 | **Codex** | Codex CLI (`codex_cli`) | 2. yedek |
| 4 | **API'li modeller** | LiteLLM (`litellm`): Gemini API anahtarı, isteğe bağlı Grok (xAI) ve Ollama | Son yedek + çok-agent (debate) modu |
| — | **Ollama** (yerel) | `ollama/...` | Görsel (ekran görüntüsü) okuma gibi buluta gitmesini istemediğin işler, son çare yedek |

Bilmen gereken üç kısıt:

1. **Abonelik CLI'ları yalnızca oturum açtığın makinede çalışır.** GitHub Actions, Docker veya bulut sunucusu senin Claude/Gemini/Codex oturumunu taşımaz. Bu yüzden abonelikli kurulum kendi bilgisayarında (ya da evdeki sürekli açık bir makinede) çalışmalı.
2. **CLI'lar yalnızca "metin üretir", araç çağıramaz.** Klasik günlük analiz (`AGENT_MODE=false`, varsayılan) CLI'larla çalışır. Çok-agent / boğa-ayı tartışması (`AGENT_ORCHESTRATOR_MODE=debate`) ve web'deki "hisseye sor" sohbeti araç çağırma ister, bu yüzden LiteLLM'e (API anahtarına) ihtiyaç duyar. Gemini Pro aboneliği API anahtarı **vermez**, ama [Google AI Studio](https://aistudio.google.com/apikey) üzerinden ayrı ve ücretsiz kotalı bir anahtar alınabilir.
3. **Grok aboneliği (X Premium / SuperGrok) API anahtarı içermez.** Grok'u kullanmak için [xAI Console](https://console.x.ai/)'dan ayrı, ücretli bir API anahtarı gerekir. Başlangıçta şart değil.

## 2. Kurulum

### 2.0 Windows: E: diskine tek komutla kurulum

Önce Git, Python 3.11 ve Node.js 20+ kurulu olmalı. Eksikse PowerShell'de:

```powershell
winget install --id Git.Git -e; winget install --id Python.Python.3.11 -e; winget install --id OpenJS.NodeJS.LTS -e
```

Yeni bir PowerShell penceresi açıp kurulum betiğini indir ve çalıştır:

```powershell
git clone --branch claude/jolly-cray-fsps8k https://github.com/daghantektepe/daily_stock_analysis.git E:\daily_stock_analysis
```

```powershell
powershell -ExecutionPolicy Bypass -File E:\daily_stock_analysis\scripts\windows\install.ps1 -Target E:\daily_stock_analysis
```

Betik şunları yapar:

- Python sanal ortamını (`.venv`) kurar ve gereksinimleri yükler.
- Claude / Gemini / Codex CLI'larını kurar (`-SkipCli` ile atlanır).
- `.env` dosyası yoksa `scripts\windows\env.tr.template` dosyasından oluşturur. Var olan `.env` dosyasına dokunmaz.

Tekrar çalıştırmak güvenlidir; güncelleme için de aynı komutu kullan. Sonra 2.2'deki girişleri yap ve 4. bölümle devam et. Başlatma:

```powershell
powershell -ExecutionPolicy Bypass -File E:\daily_stock_analysis\scripts\windows\start.ps1
```

İki pencere açılır: web arayüzü + zamanlanmış analiz, ve KAP izleyici (4.3). Oturum açılışında kendiliğinden başlaması için betiği `-RegisterAtLogon` ile bir kez çalıştır; kaldırmak için `-UnregisterAtLogon` kullan.

### 2.1 Proje (Linux / macOS ya da elle kurulum)

```bash
git clone https://github.com/daghantektepe/daily_stock_analysis.git
```

```bash
cd daily_stock_analysis && git checkout claude/jolly-cray-fsps8k
```

```bash
python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

Python 3.11 önerilir (CI ile aynı). Windows'ta `source .venv/bin/activate` yerine `.venv\Scripts\activate` kullan.

### 2.2 CLI'lar ve oturum açma

Node.js 20+ gerekir.

```bash
npm install -g @anthropic-ai/claude-code @google/gemini-cli @openai/codex
```

Her birini bir kez etkileşimli açıp aboneliğinle giriş yap:

```bash
claude
```

(`/login` → Claude Pro hesabın; sonra `/exit`)

```bash
gemini
```

("Login with Google" → Gemini Pro hesabın; sonra `/quit`)

```bash
codex login
```

### 2.3 Ollama (isteğe bağlı, yerel)

[ollama.com](https://ollama.com) üzerinden kur, sonra bir metin ve bir görsel modeli indir:

```bash
ollama pull qwen3:8b
```

```bash
ollama pull qwen2.5vl:7b
```

## 3. `.env` profili

Proje kökünde `.env` dosyası oluştur (`.env.example` tüm seçenekleri açıklar):

```env
# --- Hisseler ve dil ---
STOCK_LIST=THYAO.IS,ASELS.IS,GARAN.IS,BIMAS.IS,TUPRS.IS
REPORT_LANGUAGE=tr
REPORT_TYPE=full
# Günlük BIST piyasa değerlendirmesi (BIST 100 / BIST 30 / Banka endeksi + USD/TRY)
MARKET_REVIEW_ENABLED=true
MARKET_REVIEW_REGION=tr

# --- Üretim zinciri: Claude -> Gemini -> Codex -> API'li modeller ---
GENERATION_BACKEND=claude_code_cli
GENERATION_FALLBACK_BACKEND=gemini_cli,codex_cli,litellm
GENERATION_BACKEND_TIMEOUT_SECONDS=600

# --- LiteLLM (son yedek + çok-agent için) ---
# Google AI Studio ücretsiz anahtarı (Gemini Pro aboneliğinden ayrıdır)
GEMINI_API_KEY=
LITELLM_MODEL=gemini/gemini-2.5-flash
# Grok kullanacaksan XAI_API_KEY ekle ve LITELLM_FALLBACK_MODELS'e xai/<model> yaz (model adları: docs.x.ai)
# XAI_API_KEY=
OLLAMA_API_BASE=http://localhost:11434
LITELLM_FALLBACK_MODELS=ollama/qwen3:8b

# --- Gizlilik: ekran görüntüsü (portföy / hisse listesi) okumayı yerelde yap (Ollama görsel modeliyle henüz denenmedi) ---
VISION_MODEL=ollama/qwen2.5vl:7b

# --- Ek haber araması (isteğe bağlı; Türkçe haberler ve KAP zaten anahtarsız toplanır, bkz. 4.2) ---
TAVILY_API_KEYS=

# --- Bildirim ---
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# --- Sanal işlem (kâğıt üzerinde) ---
PAPER_TRADING_ENABLED=true
PAPER_TRADING_POSITION_SIZE=10000

# --- Zamanlama: bilgisayarın saat dilimine göre ---
# 09:15 açılış öncesi: kapanıştan sonra ve sabah gelen KAP bildirimleri, gece haberleri
# 18:30 kapanış sonrası: günün fiyatı, aracı kurum dağılımı ve akşam bildirimleri
SCHEDULE_ENABLED=true
SCHEDULE_TIMES=09:15,18:30
```

`GEMINI_API_KEY` boş bırakılırsa zincir yine çalışır: Claude → Gemini CLI → Codex → Ollama. Sadece çok-agent (debate) modu ve "hisseye sor" sohbeti kullanılamaz.

### 3.1 İsteğe bağlı: boğa/ayı tartışması (debate)

Gemini API anahtarı (veya xAI anahtarı) varsa:

```env
AGENT_MODE=true
AGENT_ARCH=multi
AGENT_ORCHESTRATOR_MODE=debate
AGENT_LITELLM_MODEL=gemini/gemini-2.5-flash
```

Bu modda analiz CLI aboneliklerini değil LiteLLM modelini kullanır ve hisse başına birkaç LLM çağrısı yapar. Önce klasik modla birkaç gün çalıştırıp raporları karşılaştırman önerilir.

Raporda "⚖️ Boğa / Ayı Tartışması" bölümü çıkar. Her iki tarafın tezi, kanıtlı argümanları ve güven düzeyi (yüksek/orta/düşük) gösterilir. Boğa tarafında katalizörler, en zayıf nokta ve tezi geçersiz kılacak durum yer alır. Ayı tarafında riskler, boğa argümanlarına çürütmeler ve ayının çürütemediği boğa argümanı yer alır. Klasik modda bu bölüm yoktur; yerine "En Güçlü Yükseliş / Düşüş Sinyali" satırları vardır.

## 4. İlk çalıştırma ve kontrol

1. Hangi modellerin gerçekten çalıştığını gör (her biri için küçük bir gerçek istek gönderir, az miktarda kota harcar):

```bash
python scripts/check_env.py --backends
```

Beklenen: her satırda `✅ 通过`. `login_required` görürsen ilgili CLI'da tekrar giriş yap; `command_not_found` görürsen CLI kurulu değil veya `PATH`'te değil.

2. LLM kullanmadan fiyat verisi akışını dene (yalnızca Yahoo Finance'ten BIST günlük verisini çeker; KAP ve haber adımları bu modda çalışmaz):

```bash
python main.py --dry-run --stocks THYAO.IS --no-market-review
```

3. Tek hisseyle gerçek analiz (bildirim göndermeden):

```bash
python main.py --stocks THYAO.IS --no-notify --no-market-review
```

Rapor `reports/` klasörüne yazılır. Türkçe çıktının kalitesini burada kontrol et.

4. Bildirimi dene:

```bash
python scripts/check_env.py --notify
```

5. Web arayüzü + zamanlanmış çalıştırma (bilgisayar açık kaldığı sürece her gün `SCHEDULE_TIMES` saatlerinde çalışır; her çalıştırma hisse başına bir CLI isteği harcar):

```bash
python main.py --serve --schedule
```

Web arayüzü: <http://127.0.0.1:8000>. Ağda başkalarına açacaksan `ADMIN_AUTH_ENABLED=true` yap.

### 4.1 Web arayüzünde hisse arama

Web arayüzünün arama kutusu yaklaşık 800 BIST hissesini tanır: `THYAO`, `Türk Hava`, `turk hava yollari` yazman yeterli; seçince `THYAO.IS` olarak eklenir. Liste KAP'tan üretilir; yeni halka arzlar için güncellemek istersen:

```bash
python scripts/fetch_kap_stock_list.py
```

```bash
python scripts/generate_index_from_csv.py --merge-markets TR
```

### 4.2 Haberler: nereden geliyor, nasıl doğrulanıyor?

`.IS` hisseleri için API anahtarı gerekmeden üç kaynak birleştirilir:

1. **KAP bildirimleri**: şirketin kendi Özel Durum Açıklamaları ve finansal raporları (son 14 gün).
   - En yeni 3 bildirimin metni de okunur: sözleşme tutarı, karşı taraf, geri alım büyüklüğü gibi bilgiler.
   - Her bildirim olay türüyle etiketlenir: bilanço, temettü, geri alım, sözleşme, pay satışı, devre kesici...
   - Borsa İstanbul'un hisse bazında devre kesici ve tedbir bildirimleri, anormal oynaklık uyarısı olarak eklenir.
   - MKK'nın pay dönüşümü duyuruları da eklenir. Payların borsada satılabilir tipe dönüştürülmesi, çoğu zaman büyük bir ortağın satışından önceki adımdır.
2. **Google News Türkiye araması**: hisse kodu ve şirket/marka adıyla (ör. `THYAO OR "Türk Hava Yolları"`). Onlarca yayını kapsar; Midas, Paratic, Bloomberg HT, Investing, Dünya, finans blogları dahil.
3. **15 ekonomi masası RSS'i**: Bloomberg HT, AA, Dünya, Ekonomim, Paratic, BorsaGündem, Ekonomist, Investing.com Türkiye, Habertürk, Sözcü, Cumhuriyet, Yeni Şafak, Haber Global, CNN Türk ve TRT Haber. Makro başlıklar (TCMB, enflasyon, kur, CDS, BIST) da buradan gelir.

Sistem başlıkları şöyle işler:

- **Ayıklar:** hisse kodu ya da şirket adı başlıkta geçmeyen haberleri atar. Spor ve sponsorluk haberlerini de atar (ör. "VakıfBank–Türk Hava Yolları voleybol maçı").
- **Birleştirir:** aynı olayı farklı yayınlardan tek hikâyede toplar. Örneğin bir bilanço açıklaması 18 kaynaklı tek hikâye olur.
- **Etiketler:** her hikâyeye bir doğrulama seviyesi verir.

| Seviye | Anlamı | Modelin kullanımı |
|--------|--------|-------------------|
| `OFFICIAL` (Resmî) | Resmî kurum ya da KAP bildirimine dayandığını söyleyen ana akım yayın | Karar için kullanılır |
| `CONFIRMED` (Doğrulanmış) | En az bir birinci kademe finans yayını dahil 2+ kaynak ya da 3+ ana akım kaynak | Karar için kullanılır |
| `REPORTED` (Tek kaynak) | Tek bir finans ya da ana akım yayın | "Doğrulanmamış" diye anılır |
| `WEAK` (Zayıf) | Yalnızca küçük siteler veya bloglar | "Doğrulanmamış" diye anılır |
| `RUMOR` (Söylenti) | Başlıkların yarısından fazlasında "iddia", "kulis", "duyum" gibi ifadeler var ve resmî teyit yok | Asla gerçek gibi ele alınmaz |

Bilmen gereken sınırlar:

- Sistem haberin **doğru olup olmadığını** bilemez. Yalnızca kaç güvenilir yayının aynı şeyi yazdığını ölçer.
- Aynı ajans (AA, DHA, İHA) haberini kopyalayan siteler bağımsız teyit sayılmaz.
- Eski haberler genelde fiyata çoktan yansımıştır.
- Söylentiye dayanarak işlem yapmak risklidir. İçeriden öğrenilen bilgiyle işlem SPK mevzuatına göre suçtur.

Midas uygulamasının sayfaları doğrudan çekilmez, çünkü kullanım koşulları belirsiz. Midas'ın yayımladığı haberler zaten Google News üzerinden gelir. KAP bildirimlerini de sistem KAP'tan kendisi okur.

### 4.3 KAP ve haber izleyici: seans içi uyarılar

Günlük analiz günde birkaç kez çalışır. Saat 11:00'de gelen bir sözleşme, geri alım, devre kesici ya da birden çok güvenilir yayında aynı anda çıkan bir haber bir sonraki çalıştırmayı beklememeli. İzleyici `STOCK_LIST`'teki `.IS` hisselerini `KAP_WATCH_INTERVAL_SECONDS` saniyede bir (varsayılan 300) kontrol eder. `KAP_WATCH_HOURS` (İstanbul saati, varsayılan `08:00-23:00`) içinde çalışır; akşam yayımlanan bildirimler ve haberler de böylece yakalanır. Yeni önemli bir gelişme gelince Telegram'a (ya da `.env`'de ayarlı kanala) tek mesaj gönderir.

```bash
python scripts/kap_watch.py
```

- **Resmî KAP bildirimleri:** bilanço, temettü, bedelsiz/bedelli, geri alım, pay/ortaklık değişikliği, sözleşme/iş ilişkisi, tedbir, derecelendirme, devre kesici. Varant fiyatı gibi rutin bildirimler kaydedilir ama gönderilmez.
- **Çok kaynaklı teyitli haberler (`CONFIRMED` / `OFFICIAL`):** En az 2 farklı yayında (en az biri Bloomberg HT, Dünya, Ekonomim, AA gibi birinci kademe ekonomi kaynağı veya 3 ana akım kaynak) aynı anda çıkan sözleşme, bilanço, hedef fiyat, yabancı akışı gibi haberler `📰 Çok kaynaklı haber` olarak bildirilir.
- **Yayılan söylenti uyarısı (`RUMOR`):** Kulis/iddia/söylenti niteliğindeki bir haber en az 2 farklı yayına yayıldığında `⚠️ SÖYLENTİ — resmî teyit yok` etiketiyle uyarılır; böylece piyasada dolaşan söylentiden haberdar olursun ama resmî bildirimle karıştırmazsın (`--no-news` veya `KAP_WATCH_NEWS_ENABLED=false` ile kapatılabilir).
- **İlk çalıştırma:** mevcut bildirimleri ve haberleri yalnızca kaydeder, eski haber yağmuru olmaz. Durum ve son uyarılar `data/kap_watch_state.json` dosyasında tutulur; Web arayüzündeki **Sanal İşlem / KAP** sayfası da buradan beslenir.
- **Önce deneme:** `--once` tek tur kontrol eder ve göndermeden ekrana yazar.

Uyarı bilgi amaçlıdır. Habere hemen işlem yapmak yerine fiyatın tepkisine ve haberin teyidine bak.

### 4.4 BIST taraması: ~800 hisseden günün en ilginç 5–10 adayını seçme

Sabit 5 hisse yerine her gün ~800 BIST hissesini tarayıp yalnızca teknik kurulumu, hacim artışı veya yeni KAP bildirimi olan en ilginç 5–10 hisseyi derin analize sokabilirsin. Böylece fırsat kaçırmaz ve CLI kotasını tüm tahtalara harcamazsın:

```bash
python scripts/bist_screener.py --top 8
```

Tarama üç sinyali birleştirir:

- **Teknik kurulum:** `MA5 > MA20` yükseliş trendi, `MA5`'e yakın dengeli giriş, 20 günlük zirve kırılımı, `RSI(14)` güçlenme (52–68) veya aşırı satımdan hacimli dönüş (<35). Günlük +%8,5 üzeri (tavana yakın) veya `MA5`'ten aşırı uzaklaşmış hisseler elenir/cezalandırılır.
- **Hacim artışı:** Son gün hacminin önceki 20 gün ortalamasına oranı (`>= 1,5x`) ve sığ tahtaları elemek için minimum günlük işlem hacmi (varsayılan 5 milyon TL; önemli KAP olayı varsa muaf).
- **Yeni KAP olayı:** Tek bir KAP sorgusuyla son 2 gündeki tüm BIST bildirimleri taranır; sözleşme, geri alım, bedelsiz, temettü ve bilanço bildirimleri puanı artırır, devre kesici ve tedbir bildirimleri puan düşürür.

Günlük analizde otomatik kullanmak için `.env` dosyasına ekle (veya `python main.py --screen-bist` ile çalıştır):

```env
BIST_SCREENER_ENABLED=true
BIST_SCREENER_TOP_N=8
```

Tarama veri çekemezse veya eşiği geçen aday bulamazsa sistem otomatik olarak `STOCK_LIST` listesine döner.

## 5. Gizlilik: buluta ne gider?

- Claude / Gemini / Codex / Grok kullanıldığında **hisse kodları, fiyat verisi, haberler, KAP bildirimleri ve (Portföy'e girdiysen) pozisyon bilgilerin** ilgili sağlayıcıya gider. Bunlar çoğunlukla zaten açık piyasa verisidir.
- **Pozisyonlarının buluta gitmesini istemiyorsan** gerçek pozisyonlarını Portföy modülüne girme; sanal işlem (`PAPER_TRADING_ENABLED`) analize pozisyon bilgisi göndermez.
- **Ekran görüntüleri** (aracı kurum ekranından hisse içe aktarma) `VISION_MODEL=ollama/...` ile yerelde işlenir.
- API anahtarların ve `.env` dosyan CLI alt süreçlerine aktarılmaz; sistem CLI'ları boş bir geçici klasörde, araç ve MCP kullanımı kapalı olarak çalıştırır.

## 6. Sorun giderme

| Belirti | Olası neden | Çözüm |
|---------|-------------|-------|
| `login_required` | CLI oturumu düşmüş | `claude` / `gemini` / `codex login` ile tekrar giriş |
| `command_not_found` | CLI kurulu değil veya `PATH` farklı | `npm install -g ...`; zamanlayıcı/servis farklı kullanıcıyla çalışıyorsa `PATH`'i kontrol et |
| `timeout` | Uzun prompt, yavaş yanıt | `GENERATION_BACKEND_TIMEOUT_SECONDS=900` |
| Rapor Çince/İngilizce çıkıyor | `REPORT_LANGUAGE` okunmamış | `.env`'de `REPORT_LANGUAGE=tr` olduğundan emin ol, servisi yeniden başlat |
| KAP bildirimi yok | KAP geçici erişilemez | Analiz durmaz; birkaç dakika sonra tekrar dener (5 dk devre kesici) |
| `The token '&&' is not a valid statement separator` | Windows PowerShell 5.1 `&&` desteklemez | Komutları ayrı satırlarda çalıştır (örn. önce `cd apps/dsa-web`, sonra `npm run build`) ya da PowerShell 7 (`pwsh`) kullan |
| Abonelik limiti doldu | Claude Pro kullanım limiti | Zincir otomatik olarak Gemini → Codex → API'ye geçer; log'da `trying next fallback backend` görünür |

## 7. Gerçek parayla işlemden önce: ölç

Bu sistem kazanç garantisi vermez. Bir sinyalin işe yarayıp yaramadığını ancak ölçerek öğrenirsin:

1. **En az 4–6 hafta yalnızca sanal işlem, ATR risk yönetimi ve otomatik haftalık rapor** (`PAPER_TRADING_ENABLED=true`). Sanal işlem motoru her yeni `buy`/`add` sinyalinde 14 günlük ATR volatilitesini (veya sinyalin kendi zarar kes seviyesini) kullanarak pozisyon büyüklüğünü `PAPER_TRADING_RISK_PCT` (varsayılan `%5`) risk bütçesine göre otomatik ölçekler; yüksek volatiliteli hissede daha az lot alır. Açık pozisyonlar sonraki günlerin dip/zirve fiyatlarında **zarar kes (`stop_loss`, varsayılan `2 × ATR`)** veya **kâr al (`take_profit`, varsayılan `3 × ATR`)** seviyesine değdiğinde sanal defterde otomatik olarak kapatılır. Özet için:

```bash
python scripts/paper_trading_report.py
```

   `--notify` eklersen özet Telegram'a da gider. Sistem her günlük analizden sonra bekleyen sinyal isabetlerini (`1/3/5/10` işlem günü, ±%2 nötr bant) kendiliğinden hesaplar ve **her Cuma 18:00 sonrası** çalıştırmada sanal işlem özetini, BIST 100 ve dolar kıyasını ve sinyal isabet oranlarını otomatik olarak Telegram'a gönderir (haftada bir kez, `data/weekly_report_state.json`). Ayrıca Web arayüzündeki **Sanal İşlem / KAP** (`/paper-trading`) sayfasından açık pozisyonları, ATR zarar kes / kâr al seviyelerini, BIST 100 & dolar kıyasını ve KAP / haber uyarılarını doğrudan görebilirsin.
2. **Sinyal isabeti:** her al/sat sinyali, sonraki günlerin kapanış fiyatıyla karşılaştırılır (1/3/5/10 gün, ±%2 nötr bant). Hisse yalnızca bir kez analiz edildiyse sonraki kapanışlar veritabanında yoktur. Rapor, günlük çalıştırma ve web API'si bu eksik kapanışları veri sağlayıcısından kendiliğinden tamamlar (hisse ve sinyal günü başına bir kez; ufku henüz dolmamış sinyaller için ağa çıkılmaz). Rapor sonuçlanmayan kontrolleri "ileri kapanış bekliyor" ve "değerlendirilemedi (neden)" diye ayırır. Yönlü sonuç sayısı 30'un altındaysa isabet oranının henüz anlamlı olmadığını belirtir. Artık günlük çalıştırmalarda ve `paper_trading_report.py` içinde kendiliğinden hesaplanır; istersen API üzerinden de tetikleyebilirsin:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/decision-signals/outcomes/run -H "Content-Type: application/json" -d '{"market": "tr"}'
```

   Windows PowerShell'de:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/decision-signals/outcomes/run -ContentType 'application/json' -Body '{"market":"tr"}'
```

   İsabet oranları: <http://127.0.0.1:8000/api/v1/decision-signals/outcomes/stats>
3. **KAP olaylarının geçmiş etkisi (Event Study):** Sözleşme, geri alım, bedelsiz, temettü ve bilanço gibi KAP bildirimlerinden sonra hissenin `1`, `5` ve `20` işlem gününde ortalama ne yaptığını ve BIST 100'e göre farkını (alfa) ölçmek için:

```bash
python scripts/kap_event_study.py --days 365
```

   Saat 18:00'den sonra gelen bildirimler (seans kapandığı için) ertesi işlem günü kapanışından başlatılır; böylece gerçekte alamayacağın kapanış fiyatı hesaba katılmaz. `--stocks THYAO.IS,ASELS.IS` ile hisse listesini değiştirebilir, `--notify` ile sonucu Telegram'a gönderebilirsin.
4. **Kıyasla:** Stratejin BIST 100'ü ve doları geçemiyorsa, TL bazlı nominal kâr yanıltıcıdır. Yüksek enflasyonda bu çok olasıdır. Rapordaki "fark" ve "dolar bazında" satırlarına bak.
5. **Gerçek paraya geçersen küçük başla.** Pozisyon büyüklüğünü ve zarar kes seviyesini önceden belirle. Tek bir habere ya da söylentiye dayanarak işlem yapma.

### 7.1 ABD stratejilerini geçmiş veriyle sına (kendi bilgisayarında)

Bu testler SEC ve Yahoo'dan veri çeker; bulut sunucularından genelde engellenir, ev bağlantısında çalışır. Önce `.env` dosyasına SEC'in istediği iletişim bilgisini ekle (yalnızca sec.gov'a gönderilir):

```env
SEC_EDGAR_USER_AGENT=DailyStockAnalysis/1.0 (contact: senin@epostan.com)
```

Yönetici alımları (Form 4), 2023 başından bugüne, tüm olaylar:

```bash
python scripts/sec_form4_study.py --quarters 2023q1..2026q3 --min-value 50000
```

Bilanço sonrası sürüklenme (PEAD), S&P 400 ve S&P 600 hisselerinden rastgele 400 tanesi:

```bash
python scripts/pead_study.py --universe smid --sample 400
```

İlk çalıştırma fiyatları indirdiği için uzun sürebilir (10–40 dk); fiyatlar `data/cache` altına kaydedilir, sonraki çalıştırmalar hızlıdır. Raporu okurken:

- **Fazla getiri iki endekse göre ölçülür:** S&P 500 (SPY) ve küçük şirketler (IWM). Kararlar zor olana, yani düşük çıkana göre verilir.
- **"✅ anlamlı"** yalnızca şu durumda yazar: aynı aydaki olaylar tek gözlem sayıldıktan ve tüm alt gruplar birlikte çoklu test düzeltmesinden (Holm) geçtikten sonra da sonuç tesadüften ayrılıyorsa, ve en az 12 aya yayılıyorsa. Bu çıtanın altındaki "iyi görünen" sonuçlar karar için yeterli değildir.
- **Borsadan çıkan hisseler** son fiyatından çıkış yapar. Fiyatı hiç bulunamayan olaylar için rapor, bunların %-30 kaybettiği varsayımıyla düzeltilmiş ortalamayı da gösterir.
- PEAD testi bilerek bugünün kazananlarından seçilmiş izleme listelerini değil endeks bileşenlerini kullanır; aksi halde sonuç geriye bakarak seçim yüzünden şişer.

Çıktıyı buraya yapıştırırsan birlikte yorumlarız. Bir strateji maliyet sonrası zor kıyasta anlamlı pozitif değilse sanal işleme bile alınmaz.

### 7.2 Kripto trend stratejisi (BTC / ETH, sanal)

Kural basit ve tahmin yapmaz: her coin için sermaye beş parçaya bölünür. Her parça, coin 50 / 100 / 150 / 200 / 250 günlük ortalamalardan kendisininkinin üstündeyse coin'de, altındaysa nakitte durur. Amaç yarını bilmek değil, BTC ve ETH'nin −%70 ile −%90 arası büyük çöküşlerinin büyük kısmını nakitte geçirmektir.

Tek bir "en iyi" ortalama yerine beşinin birlikte kullanılması bilinçli bir tercih: geçmişe en iyi uyan parametreyi seçmek, gelecekte tutmayan bir kural üretir.

Geçmiş test (Yahoo Finance günlük kapanış, işlem başına %0,15 maliyet, BTC + ETH eşit ağırlık):

| Dönem | Strateji: yıllık / en büyük düşüş / Sharpe | Al-tut: yıllık / en büyük düşüş / Sharpe |
|---|---|---|
| 2018 – Kasım 2026 | %41 / −%50 / 1,02 | %24 / −%77 / 0,67 |
| 2022 – Kasım 2026 (örneklem dışı) | %17 / −%31 / 0,65 | −%2 / −%69 / 0,24 |

Beş ortalamanın her biri tek başına da al-tut'u geçiyor; maliyet %0,5'e çıksa bile yıllık %35. Bilmen gerekenler:

- Güçlü boğa yıllarında geride kalır: 2020'de strateji +%190, al-tut +%338.
- Çöküşlerde korur: 2022'de strateji −%27, al-tut −%66.
- En büyük düşüş hâlâ −%50 civarı. Bu risk küçülmez, yalnızca al-tut'tan daha sığdır.
- Geçmiş sonuç geleceği garanti etmez.

Komutlar:

```bash
python scripts/crypto_trend.py backtest
```

```bash
python scripts/crypto_trend.py signal
```

```bash
python scripts/crypto_trend.py paper --notify
```

Günlük analizden sonra kendiliğinden ilerlemesi için `.env`:

```env
CRYPTO_TREND_ENABLED=true
CRYPTO_TREND_ASSETS=BTC-USD,ETH-USD
CRYPTO_TREND_CAPITAL=10000
```

Sanal defter `data/strategy_paper/crypto_trend.json` dosyasında tutulur ve geçmiş testle aynı kodu kullanır, yani ikisinin sonuçları birebir karşılaştırılabilir. Pozisyon değişince Telegram'a mesaj gelir; özet haftalık rapora da eklenir. Bilgisayar kapalıyken geçen günler sonradan işlenir ve raporda "sonradan işlendi" olarak ayrıca gösterilir.

### 7.3 İleri doğrulama kapısı (PAA, Meta-Portföy A ve v3_trp)

Meta-Portföy A v2'nin 2022–2026 sonucu, parametreler aynı dönem görülerek ayarlandığı için gerçek örneklem dışı değildir. Temiz kanıt yalnızca stratejinin dondurulmasından sonra gelen veridir.

- **Takip edilen stratejiler:** Varsayılan `QUANT_PAPER_STRATEGIES=paa,meta_a,v3_trp`. Kayıt defterinde (`forward_validation.json`) dondurulmuş bir strateji, `.env` listesinde olmasa bile her gün işlenir; böylece eski bir `.env` sınavı yarıda kesemez.
- **Günlük veri yenileme:** Aynı adım, `/simple` ekranının okuduğu turnuva ve v3 araştırma dosyalarını (`data/quant_cache/*_latest.json`) da yeniler (yaklaşık 25 sn; 20 saatten yeni dosya atlanır; başarısız olursa eski veri korunur). `docs/` altındaki raporlara dokunmaz. Kapatmak için `--no-snapshot-refresh`.
- **Dondurma:** `quant_paper.py step` ilk çalıştığında stratejiler kendiliğinden dondurulur. Ağırlık fonksiyonunun, kullandığı tüm yardımcı fonksiyonların ve sabitlerin, ayrıca maliyet ve dengeleme ayarlarının parmak izi `data/strategy_paper/forward_validation.json` dosyasına yazılır. Yalnızca dondurma gününden sonraki işlem günleri sayılır.
- **Geçersiz sayılma:** Dondurmadan sonra bu kod ya da ayarlar değişirse kayıt "geçersiz" olur. Yeni test bilerek başlatılır:

```bash
python scripts/quant_forward.py freeze --strategy meta_a --reset
```

- **Kapı:** QA planındaki kriterler kullanılır.
  - En az 120 ileri işlem günü.
  - BIL üstü Sharpe ≥ 0,50.
  - En büyük düşüş −%18'den kötü değil. Bu sınır aşılırsa test 120 günü beklemeden "kaldı" olur.
  - Günlerin en fazla %10'u sonradan işlenmiş.
  - Ölçülen ortalama kayma ≤ 20 bps.
- **Backtest kıyası:** İleri getiri, donmuş backtest'teki aynı uzunluktaki dönemlerle karşılaştırılır. Geçmiş dönemlerin %5'inden kötüyse aşırı uyum uyarısı çıkar.
- **Durum:** Günlük adım raporunda, MCP'de `dsa_get_forward_validation` aracında ve şu komutta görünür:

```bash
python scripts/quant_forward.py status
```

**Kayma ölçümü (isteğe bağlı, Alpaca sanal hesabı).** Kapının kayma kriteri gerçek dolum gerektirir. Bunun için Alpaca'nın ücretsiz Paper Trading anahtarlarını `.env`'e ekle (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER=true`). Sonra aylık dengeleme günlerinde:

```bash
python scripts/quant_forward.py alpaca-plan --strategy meta_a --capital 10000
```

```bash
python scripts/quant_forward.py alpaca-submit-paper --strategy meta_a --capital 10000
```

```bash
python scripts/quant_forward.py alpaca-reconcile
```

- **Komutların işi:** `alpaca-plan` yalnızca okur ve emir planını gösterir. `alpaca-submit-paper` onay ister, emirleri **yalnızca sanal hesaba** gönderir, gerçek hesapta reddeder. `alpaca-reconcile` dolum fiyatını, gönderim anındaki fiyatla karşılaştırıp kaymayı kaydeder.
- **Kilitler:** Zamanlanmış görev hiçbir zaman emir göndermez. `ALPACA_PAPER=true` ve `ALPACA_AUTO_EXECUTE=false` değişmez.
- **Hata payı:** 120 günlük bir Sharpe tahmininin hata payı ±1,4 civarındadır. Kapıyı geçmek kanıtın başlangıcıdır, garantisi değil.

### 7.4 BIST stratejileri dolar bazında

TL getirisi lira değer kaybını da içerir. 2022–2026'da USD/TRY yaklaşık 13,4'ten 50,6'ya çıktı (yıllık ~%31). Bu yüzden TL'de %50 kazandıran bir strateji dolar bazında çok daha az kazanmış olabilir.

- **Turnuvada BIST:** Turnuva BIST stratejilerinin günlük TL getirisini `TRY=X` kuruyla dolara çevirir ve ABD stratejileriyle aynı eşikle, `BIL` üstü Sharpe ile değerlendirir.
- **Karar kuralı:** `CAVEAT_SURVIVORSHIP` için kur etkisi çıkarılmış getirinin BIL üstü Sharpe'ı ≥ 0,15 olmalı ve dolar getirisi BIL'i aşmalı. Değilse karar `FAIL_WEAK` olur. Kur verisi alınamazsa eski TL kuralı geçerli kalır.
- **Nerede görünür:**
  - Web turnuva tablosu: BIST satırlarında CAGR, BIL üstü Sharpe, MaxDD ve Recovery dolar bazındadır; TL CAGR altta küçük yazılır. Tablonun altında kur ve XU100 TL/USD karşılaştırması bulunur.
  - Rapor: `docs/STRATEGY_TOURNAMENT_REPORT.md` içinde "Gerçek Dolar (USD) Karşılığı" bölümü, yıllara göre dolar getirileriyle.
  - MCP: `dsa_get_strategy_tournament` aracındaki `usd_*` alanları.
- **Güncelleme:** Turnuvayı web arayüzünden yenile ya da şunu çalıştır:

```bash
python scripts/run_strategy_tournament.py
```

### 7.5 AI Konseyi v2: tüzükleri yeniden değerlendir

Claude, Codex ve Gemini'nin yazdığı tüzükler artık üç kontrolle değerlendirilir. "Konsey v2: geçti" için üçü de sağlanmalı:

1. 2022+ örneklem dışı kararı `PASS_ELITE` ya da `PASS_SOLID` olmalı. Bu karar `BIL` üstü getiriye göre verilir.
2. 25 bps işlem maliyetinde de BIL üstü Sharpe ≥ 0,15 ve pozitif fazla getiri olmalı. 50 bps yalnızca bilgi olarak raporlanır.
3. 2022 ayı piyasasında SPY'dan az kaybetmeli.

Önceden kurulmuş tüzükleri CLI'ları yeniden çağırmadan değerlendirmek için:

```bash
python scripts/run_ai_strategy_council.py reevaluate
```

- **Ne değişir:** Yalnızca değerlendirme alanları (`oos_backtest`, `verdict`, `council_v2`). Tüzük kuralları ve sanal defterler değişmez.
- **Nerede görünür:** Sonuç web'deki sanal defter kartında "Konsey v2: geçti/kaldı" rozeti ve kalınan kontrollerle gösterilir. Kartta artık Rf=0 Sharpe değil, BIL üstü Sharpe yer alır.
- **Yeni tüzükler:** `convene` ile kurulan yeni tüzükler v2 ile değerlendirilir. CLI'lara giden istemde bu kriterler açıkça yazar.

## 8. Sonraki adımlar

- 2–3 gün klasik modla çalıştırıp Türkçe raporları değerlendir; sorunlu ifadeleri not al (prompt iyileştirmesi için).
- Gemini API anahtarı ekleyip debate modunu klasik modla karşılaştır.
