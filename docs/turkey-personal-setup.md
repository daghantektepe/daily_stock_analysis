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
python scripts/fetch_kap_stock_list.py && python scripts/generate_index_from_csv.py --merge-markets TR
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

### 4.3 KAP izleyici: seans içi uyarılar

Günlük analiz günde birkaç kez çalışır. Saat 11:00'de gelen bir sözleşme, geri alım ya da devre kesici bildirimi bir sonraki çalıştırmayı beklememeli. İzleyici `STOCK_LIST`'teki `.IS` hisselerini KAP'ta `KAP_WATCH_INTERVAL_SECONDS` saniyede bir (varsayılan 300) kontrol eder. `KAP_WATCH_HOURS` (İstanbul saati, varsayılan `08:00-23:00`) içinde çalışır; akşam yayımlanan bildirimler de böylece yakalanır. Yeni ve önemli bir bildirim gelince Telegram'a (ya da `.env`'de ayarlı kanala) tek mesaj gönderir.

```bash
python scripts/kap_watch.py
```

- **Önemli sayılanlar:** bilanço, temettü, bedelsiz/bedelli, geri alım, pay/ortaklık değişikliği, sözleşme/iş ilişkisi, tedbir, derecelendirme, devre kesici. Varant fiyatı gibi rutin bildirimler kaydedilir ama gönderilmez.
- **Mesajın içeriği:** bildirimin metninden tutar, karşı taraf gibi ayrıntılar.
- **İlk çalıştırma:** mevcut bildirimleri yalnızca kaydeder, eski bildirim yağmuru olmaz. Durum `data/kap_watch_state.json` dosyasında tutulur, yeniden başlatınca tekrar göndermez.
- **Önce deneme:** `--once` tek tur kontrol eder ve göndermeden ekrana yazar.

Uyarı bilgi amaçlıdır. Habere hemen işlem yapmak yerine fiyatın tepkisine ve haberin teyidine bak.

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
| Abonelik limiti doldu | Claude Pro kullanım limiti | Zincir otomatik olarak Gemini → Codex → API'ye geçer; log'da `trying next fallback backend` görünür |

## 7. Gerçek parayla işlemden önce: ölç

Bu sistem kazanç garantisi vermez. Bir sinyalin işe yarayıp yaramadığını ancak ölçerek öğrenirsin:

1. **En az 4–6 hafta yalnızca sanal işlem** (`PAPER_TRADING_ENABLED=true`). Özet için:

```bash
python scripts/paper_trading_report.py
```

   `--notify` eklersen özet Telegram'a da gider. Haftada bir çalıştırmak yeterli. Özet gerçekleşen/gerçekleşmeyen kâr-zararı ve kazanma oranını gösterir. Aynı tarihlerde aynı tutarla BIST 100 alınsaydı ne olacağıyla da kıyaslar, ve dolar bazında getiriyi verir (her nakit akışı o günün USD/TRY kuruyla çevrilir). Aynı bilgi `GET /api/v1/paper-trading/summary` uç noktasında `benchmarks` alanında da var.
2. **Sinyal isabeti:** her al/sat sinyali, sonraki günlerin kapanış fiyatıyla karşılaştırılır (1/3/5/10 gün, ±%2 nötr bant). Gerekli fiyat geçmişi günlük çalıştırmalarla birikir. Hesaplama kendiliğinden yapılmaz, servis açıkken şu komutla tetiklenir:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/decision-signals/outcomes/run -H "Content-Type: application/json" -d '{"market": "tr"}'
```

   Windows PowerShell'de:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/decision-signals/outcomes/run -ContentType 'application/json' -Body '{"market":"tr"}'
```

   İsabet oranları: <http://127.0.0.1:8000/api/v1/decision-signals/outcomes/stats>
3. **Kıyasla:** Stratejin BIST 100'ü ve doları geçemiyorsa, TL bazlı nominal kâr yanıltıcıdır. Yüksek enflasyonda bu çok olasıdır. Rapordaki "fark" ve "dolar bazında" satırlarına bak.
4. **Gerçek paraya geçersen küçük başla.** Pozisyon büyüklüğünü ve zarar kes seviyesini önceden belirle. Tek bir habere ya da söylentiye dayanarak işlem yapma.

## 8. Sonraki adımlar

- 2–3 gün klasik modla çalıştırıp Türkçe raporları değerlendir; sorunlu ifadeleri not al (prompt iyileştirmesi için).
- Gemini API anahtarı ekleyip debate modunu klasik modla karşılaştır.
