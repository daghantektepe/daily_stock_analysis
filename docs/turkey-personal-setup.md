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

### 2.1 Proje

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
# BIST için genel piyasa değerlendirmesi henüz yok; ilk aşamada kapalı tut
MARKET_REVIEW_ENABLED=false

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

# --- Haber araması (önerilir; ücretsiz katman yeterli) ---
TAVILY_API_KEYS=

# --- Bildirim ---
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# --- Sanal işlem (kâğıt üzerinde) ---
PAPER_TRADING_ENABLED=true
PAPER_TRADING_POSITION_SIZE=10000

# --- Zamanlama: BIST kapanışı (18:00) ve kapanış seansından sonra; bilgisayarın saat dilimine göre ---
SCHEDULE_ENABLED=true
SCHEDULE_TIME=18:30
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

5. Web arayüzü + zamanlanmış çalıştırma (bilgisayar açık kaldığı sürece her gün `SCHEDULE_TIME`'da çalışır):

```bash
python main.py --serve --schedule
```

Web arayüzü: <http://127.0.0.1:8000>. Ağda başkalarına açacaksan `ADMIN_AUTH_ENABLED=true` yap.

### 4.1 Web arayüzünde hisse arama

Web arayüzünün arama kutusu yaklaşık 800 BIST hissesini tanır: `THYAO`, `Türk Hava`, `turk hava yollari` yazman yeterli; seçince `THYAO.IS` olarak eklenir. Liste KAP'tan üretilir; yeni halka arzlar için güncellemek istersen:

```bash
python scripts/fetch_kap_stock_list.py && python scripts/generate_index_from_csv.py --merge-markets TR
```

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

## 7. Sonraki adımlar

- 2–3 gün klasik modla çalıştırıp Türkçe raporları değerlendir; sorunlu ifadeleri not al (prompt iyileştirmesi için).
- Sanal işlem sonuçlarını `GET /api/v1/paper-trading/summary` ile izle.
- Gemini API anahtarı ekleyip debate modunu klasik modla karşılaştır.
