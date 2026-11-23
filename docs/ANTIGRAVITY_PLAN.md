# Antigravity Çalışma Planı (Kasım 2026 – Mayıs 2027)

**Hazırlayan:** Claude · **Tarih:** 24 Kasım 2026
**Dal:** `feat/cli-mcp-quant-tournament` (son commit `a7afca7`)
**Çalışma yeri:** `E:\daily_stock_analysis` (Windows, PowerShell 5.1)

> Önce `docs/HANDOVER_ANTIGRAVITY.md`'yi (durum, bulgular, kurallar) okuyun, sonra bu planı uygulayın. Bu dosya **ne yapılacağını, hangi sırayla ve ne zaman bitmiş sayılacağını** anlatır.

---

## 0. Hedef ve öncelik mantığı

Programın amacı kullanıcıya **gerçekten para kazandırıp kazandırmadığını dürüstçe ölçebilen** bir sistem olmak. Bugün iki soru cevapsız:

1. **Stratejiler (PAA, Meta-A, v3_trp) canlıda da çalışıyor mu?** Cevap 120 işlem günlük ileri sınavla gelecek, en erken **14 Mayıs 2027**. Bu süreçte stratejilere dokunulmaz; yalnızca izlenir.
2. **Yapay zekânın hisse al/sat sinyalleri endeksten iyi mi?** Ölçüm altyapısı yeni düzeltildi ama hâlâ eksik: endeks kıyası yok, örnek çok az.

Öncelik sırası: **ölçüm > güvenilirlik > görünürlük > yeni özellik.** Yeni strateji, opsiyon veya gerçek short, bu iki soru cevaplanmadan eklenmez.

## 1. Takvim

| Tarih (ABD işlem günü) | İleri sınav günü | Ne yapılır |
| :--- | :---: | :--- |
| 24–30 Kasım 2026 | ~1–5 | **Faz 0** (başlangıç ölçümü) ve **Faz 1** başlangıcı |
| Aralık 2026 | ~5–25 | Faz 1 ve Faz 2; ilk aylık dengeleme günü kayma ölçümü (G3.1) |
| 21 Aralık 2026 | 20 | İlk kontrol noktası (G3.2) |
| 6 Ocak 2027 | 30 | Kontrol noktası; sinyal örneği 30'a ulaştıysa ilk endeks kıyası raporu |
| 19 Şubat 2027 | 60 | Ara değerlendirme (yarı yol) |
| 2 Nisan 2027 | 90 | Son çeyrek kontrolü; kayma ölçümü en az 5 dolumda mı? |
| **14 Mayıs 2027** | **120** | **Kapı kararı** (G3.4) |

Kapı her gün kendini değerlendirir. Maksimum düşüş −%18'i aşarsa sınav takvim beklenmeden "kaldı" olur.

---

## 2. Faz 0 — Başlangıç ölçümü (1 gün, kod değişikliği yok)

Amaç, E:\'deki gerçek durumu kayda geçirmek. Her komut ayrı satırda ve `.venv` Python'uyla çalıştırılır.

| # | Komut | Beklenen / kaydedilecek |
| :--- | :--- | :--- |
| G0.1 | `git pull` | Fast-forward, çakışma yok |
| G0.2 | `.venv\Scripts\python.exe -m pytest tests/test_strategy_research_v4.py -q` | Geçmeli; dondurulmuş parmak izleri burada doğrulanır |
| G0.3 | `.venv\Scripts\python.exe scripts\quant_paper.py step` | Üç defter (paa, meta_a, v3_trp) ve "Strateji verisi: … yenilendi" satırı görünmeli |
| G0.4 | `powershell -ExecutionPolicy Bypass -File scripts\windows\daily_paper_step.ps1 -Status` | Görev kayıtlı ve son çalıştırması başarılı olmalı. Kayıtlı değilse kullanıcıya sorup `-Register` ile kaydedin |
| G0.5 | `.venv\Scripts\python.exe scripts\quant_forward.py status` | Üç stratejinin dondurma tarihi, parmak izi ve ileri gün sayısı |
| G0.6 | `.venv\Scripts\python.exe scripts\run_ai_strategy_council.py reevaluate` | Gerçek konsey tüzüklerinin v2 sonucu (geçti/kaldı ve nedeni) |
| G0.7 | `.venv\Scripts\python.exe scripts\paper_trading_report.py --details` | Sinyal dağılımı, yönlü sinyal sayısı, sonuçlanan kontroller |

**Kabul:** `docs/HANDOVER_ANTIGRAVITY.md` sonuna "E:\ ölçüm kaydı — <tarih>" tablosu eklenir: her komutun özeti ve ham çıktıdan önemli satırlar. Bir komut beklenenden farklıysa kod düzeltmeye geçmeden önce kullanıcıya bildirilir.

---

## 3. Faz 1 — Sinyal kalitesini ölçülebilir yap (en yüksek değer)

### G1.1 Endekse göre sinyal başarısı

- **Neden:** "İsabet %X" tek başına yanıltıcı. Kriz döneminde "azalt" sinyallerinin çoğu doğru çıkar, çünkü her şey düşer. Asıl soru: sinyal, aynı dönemde endeksi tutmaktan daha iyi miydi?
- **Dosyalar:**
  - `src/services/paper_trading_benchmark.py`: `evaluate_signal_outcomes()`, `BENCHMARKS` ve `yfinance_history` burada; yeniden kullanın, paralel kod yazmayın.
  - `tests/test_paper_trading.py`
- **Yapılacak:**
  1. Sonuçlanan her yönlü kontrol için aynı başlangıç ve bitiş günlerinde endeks getirisini hesaplayın: `tr` → `XU100.IS`, `us` → `SPY`. Diğer pazarlar için endeks tanımlı değilse "endeks yok" deyin; tahmin uydurmayın.
  2. Endeks üstü getiri = hisse getirisi − endeks getirisi. Al/ekle sinyalinde pozitif olması, azalt/sat/uzak dur sinyalinde negatif olması başarıdır.
  3. Rapora şu satırı ekleyin: `Endekse göre: al sinyallerinin %X'i 10 günde endeksi geçti (n=…, ort. fark +…%)`. Aynı satır azalt/sat için de olmalı.
  4. n ≥ 30 ise basit bir bootstrap ile %90 güven aralığı ekleyin. n < 30 ise "örnek yetersiz" yazın.
- **Kabul:**
  - Testler sahte endeks geçmişiyle çevrimdışı çalışır: `_offline_signal_outcome_bar_refill` fixture'ı mevcut; endeks için `history_provider` parametresi ekleyin.
  - Aynı gün tekrarlanan sinyaller tek sayılır; mevcut `_dedupe_repeated_signal_outcomes` kullanılır.
  - Hafta sonu sinyali kuralı korunur.
- **Yasak:** Web'deki karar sinyali istatistiğinin asıl projeden gelen hesaplama yöntemini değiştirmeyin. Ekleme yalnızca Türkçe rapor katmanında yapılır.

### G1.2 Sinyal görünürlüğü (`/simple` ve haftalık rapor)

- **Dosyalar:** `src/services/simple_investor_brief.py`, `src/services/simple_notification.py`, `apps/dsa-web/src/pages/SimpleInvestorHomePage.tsx`, API şeması `api/v1/schemas/alpha.py`.
- **Yapılacak:** Yönlü sinyal sayısı 30'a ulaşınca sade bir satır gösterin: "Son 30 al/sat önerisinden %X'i 10 günde endeksten iyi çıktı." Örnek 30'dan azsa "Yapay zekâ önerilerinin başarısı henüz ölçülüyor (n/30)" yazın.
- **Kabul:**
  - Alan eklemeli olur; eski istemciler bozulmaz.
  - Veri yoksa açıkça "veri yok" denir. Sessiz bir varsayılan değer kullanılmaz (`data_status` kuralı).
  - Web: vitest, lint ve build geçer. Ekran görüntüsü PR açıklamasına konur, repoya eklenmez.

### G1.3 "İzle" oranını izle (analiz, kod değişikliği küçük)

- **Bulgu:** 40 sinyalden 30'u "izle"; yapay zekâ çoğunlukla yön vermiyor.
- **Yapılacak:** Haftalık rapora "bu hafta: N sinyal, %Y'si izle" satırı ekleyin. Dört hafta boyunca izleyin.
- **Kabul:** Oran dört hafta üst üste %70'in üzerindeyse bunu kullanıcıya rapor olarak sunun. Prompt değişikliği yüksek riskli bir alandır; **kullanıcı onayı olmadan yapılmaz.**

---

## 4. Faz 2 — Güvenilirlik ve teknik borç

### G2.1 Elle çalıştırılan raporlar `git pull`'u bozmasın

- **Sorun:** `scripts/run_strategy_tournament.py`, `run_strategy_research_v3.py` ve `run_strategy_research_v4.py` repoda izlenen `docs/*_REPORT.md` dosyalarını yeniden yazıyor. Kullanıcı bu yüzden `git pull` çakışması yaşadı.
- **Yapılacak:**
  - Varsayılan çıktı `data/reports/<ad>.md` olsun (`data/` zaten izlenmiyor).
  - `docs/` yalnızca `--publish` bayrağıyla güncellensin.
  - Turnuva için `run_tournament(write_report=...)` ve v3/v4 için `write_report` / `report_path` parametreleri zaten var; yalnızca betikleri değiştirin.
- **Kabul:** Üç betik bayraksız çalıştırıldıktan sonra `git status` temiz kalır. `turkey-personal-setup.md` güncellenir.

### G2.2 Ortama bağlı testler

- **Dosyalar:** `tests/test_report_schema.py` (2 test `.env` dil ayarına bağlı; Çince etiket dönüyor) ve `tests/test_intelligence_service.py::test_fetch_enabled_sources_is_fail_open` (paralel çalışmada kararsız).
- **Kabul:** `pytest -m "not network" -n 4` hem Linux'ta hem Windows'ta 0 hatayla geçer. Test, dil ayarını kendisi belirler (monkeypatch ile); `.env`'e bağlı kalmaz.

### G2.3 Rapor çıktısındaki gürültü

- **Sorun:** `paper_trading_report.py` çalışırken Çin veri kaynaklarının (efinance, akshare, pytdx) uyarıları ekranı dolduruyor.
- **Yapılacak:**
  - Betik varsayılan olarak yalnızca kendi özetini göstersin; sağlayıcı günlükleri `--verbose` ile açılsın. Günlük seviyesini yalnızca bu betikte ayarlayın; genel yapılandırmaya dokunmayın.
  - Kullanıcıya STOCK_LIST'te gerçekten Çin hisseleri (örneğin 588200) isteyip istemediğini sorun.
- **Kabul:** Normal çalıştırmada çıktı yalnızca Türkçe özet satırlarından oluşur.

### G2.4 Küçük temizlikler

- Kullanılmayan import'lar: `src/quant/strategies/engine.py` (`asdict`) ve `src/quant/tournament.py` (`US_ETF_SAFE_ASSETS`).
- `scripts/run_strategy_tournament.py` çıktısı hâlâ Rf=0 Sharpe yazıyor; BIL üstü Sharpe göstersin (web ve MCP ile tutarlı olsun).

### G2.5 v4 sonucunu web'de göster

- **Yapılacak:** `research_v4_latest.json`'u okuyan yalnızca okuma yapan bir uç ve Turnuva sekmesinde (`TournamentTabPanel.tsx`) küçük bir kart: "Short testi (ters ETF): değer katmıyor, krizde korur ama toplamda Sharpe 0,51'e karşı 0,68." Veri yoksa kart gizlenir.
- **Kabul:** Dosya yoksa uç `ok=false` döner; kart görünmez. Testler yazılır.

---

## 5. Faz 3 — İleri sınav dönemi (Aralık 2026 – Mayıs 2027)

Bu fazda **strateji koduna dokunulmaz.** İş, izlemek ve kanıt toplamak.

### G3.1 Kayma ölçümü (aylık, kullanıcı onayıyla)

- **Neden:** Kapının "kayma ≤ 20 bps" kriteri gerçek sanal dolum ister; en az 5 dolum gerekir.
- **Ön koşul:** Kullanıcının ücretsiz Alpaca Paper anahtarları `.env`'de olmalı (`ALPACA_PAPER=true` kalır).
- **Her ayın ilk işlem günü:**
  1. `.venv\Scripts\python.exe scripts\quant_forward.py alpaca-plan --strategy meta_a --capital 10000` (yalnızca okur).
  2. Kullanıcı onaylarsa `alpaca-submit-paper` çalıştırılır; komut onay ister ve yalnızca sanal hesaba gönderir.
  3. Birkaç dakika sonra `alpaca-reconcile` çalıştırılır.
- **Kabul:** 2 Nisan 2027'ye kadar en az 5 dolum. Ortalama kayma kapı kartında görünür.
- **Yasak:** Otomatik gönderim yok. `ALPACA_AUTO_EXECUTE=false` değişmez. Gönderim zamanlayıcıya bağlanmaz.

### G3.2 Kontrol noktaları (20 / 30 / 60 / 90. gün)

- **Her kontrol noktasında:**
  - `quant_forward.py status` çalıştırın.
  - Kayıt edin: ileri getiri, SPY, BIL üstü Sharpe ± hata payı, en büyük düşüş ve backtest bandındaki konum (yüzdelik).
- **Kayıt yeri:** `docs/HANDOVER_ANTIGRAVITY.md` içindeki ölçüm tablosu.
- **Kural:** İleri sonuç backtest'in %5 diliminin altına düşerse **kodu değiştirmeyin.** Değişiklik kaydı geçersiz kılar ve sınavı sıfırlar. Durumu kullanıcıya "aşırı uyum uyarısı" olarak bildirin.

### G3.3 Sinyal ölçümü (Faz 1 tamamlandıktan sonra, haftalık)

- Her Cuma haftalık rapor gider. Ayda bir endekse göre sinyal başarısı özetlenir.
- n ≥ 30 olduğunda ilk anlamlı karar: Sinyaller endeksi güven aralığıyla geçiyor mu? Geçmiyorsa web'de sinyallerin yanında "başarısı kanıtlanmadı" etiketi gösterilir (G1.2).

### G3.4 Kapı kararı (14 Mayıs 2027)

- **PASS:** Kullanıcıya **küçük sermayeli, elle verilen emirlerle** gerçek para planı önerilir. Plan, Midas'ta kullanıcının kendi uygulayacağı aylık bir alışveriş listesi şeklinde olur. Otomatik emir yine yoktur. Kilitlerin açılması ayrı ve açık bir kullanıcı kararıdır.
- **PASS_PENDING_SLIPPAGE:** Kayma ölçümü tamamlanana kadar beklenir.
- **FAIL:** Neden raporlanır. Yeni araştırma (Faz 4) önceden kayıtlı parametrelerle ve kontrol grubuyla başlar. Eski kayıt "previous" olarak arşivlenir (`freeze --reset`).

---

## 6. Faz 4 — Koşullu / ertelenen işler

Bunlar ancak belirtilen koşul sağlanınca başlar:

| İş | Koşul | Not |
| :--- | :--- | :--- |
| Yeni strateji araştırması (v5) | Kullanıcı ister **ya da** kapı FAIL olur | Ayrı modül, önceden sabitlenmiş parametreler, **kontrol grubu şart**, aynı 5 kapı, kümülatif deneme sayısı artırılır (v4 örneği: `research_v4.py` + `research_v4_lab.py`) |
| Opsiyonlar (koruyucu put, covered call) | Kapı PASS + ücretli geçmiş opsiyon verisi + Alpaca paper opsiyon hesabı | Sentetik (Black-Scholes) geçmişle test yapılmaz |
| Gerçek açığa satış | Önerilmez | Ters ETF testi bile toplamda değer katmadı; kaybı sınırsız ve kredili hesap gerektiriyor |
| Kaldıraçlı ETF (2x/3x) | Önerilmez | Günlük sıfırlama kaybı çok yüksek |
| Gerçek para otomasyonu | Yapılmaz | Kilitler kullanıcı kararıyla açılır; zamanlayıcı asla emir göndermez |

---

## 7. Her görev için "bitti" tanımı

1. Değişiklik yalnızca görevin gerektirdiği dosyalarla sınırlıdır; ilgisiz yeniden düzenleme yapılmaz.
2. Testler yazılır ve çalıştırılır. Ağ gerektiren testler `@pytest.mark.network` ile işaretlenir; birim testleri çevrimdışıdır.
3. Doğrulama çalıştırılır:
   - `.venv\Scripts\python.exe -m pytest -m "not network"`
   - Web değiştiyse: `cd apps/dsa-web`, sonra `npm run lint`, sonra `npm run build`, sonra `cd ..\..`
4. `docs/CHANGELOG.md` `[Unreleased]` bölümüne düz liste biçiminde bir satır eklenir. Yeni yapılandırma varsa `.env.example` ve `docs/turkey-personal-setup.md` güncellenir.
5. Commit mesajı İngilizce yazılır, `Co-Authored-By` içermez. Push yalnızca `feat/cli-mcp-quant-tournament` dalına yapılır.
6. `docs/HANDOVER_ANTIGRAVITY.md` içindeki ilerleme tablosu (aşağıda) güncellenir. Teslimde şunlar yazılır: ne değişti, neden, doğrulama, doğrulanamayanlar, risk ve geri alma yolu.

## 8. Bozulmaması gerekenler (özet)

- **Dondurulmuş kod:** `library.py` ve `research_v3.py` içindeki dondurulmuş fonksiyonlara, eriştikleri yardımcı fonksiyonlara ve sabitlere dokunulmaz. Parmak izleri: `87e22a6b3559`, `37a7ab36a0d9`, `ae4754108564`.
- **Kilitler:** `ALPACA_PAPER=true`, `ALPACA_AUTO_EXECUTE=false`, Binance yalnızca testnet, AlgoLab ve IBKR yalnızca okuma.
- **Uydurma yok:** Veri yoksa ekranda açıkça "veri yok" yazılır; sabit kodlanmış "örnek" değer gösterilmez.
- **Windows:** Komutlar `.venv\Scripts\python.exe` ile çalıştırılır; PowerShell 5.1'de `&&` kullanılmaz.

## 9. İlerleme tablosu

| Görev | Durum | Commit | Not |
| :--- | :--- | :--- | :--- |
| G0.1–G0.7 Başlangıç ölçümü | ✅ | `3887fd4` | `2026-11-23` gerçek E:\ ölçümü `HANDOVER_ANTIGRAVITY.md` §7'ye işlendi; tüm komutlar exit 0 |
| G1.1 Endekse göre sinyal başarısı | ✅ | `abadf17` | `evaluate_signal_outcomes(history_provider=...)`, 10g `XU100.IS`/`SPY` kıyası, bootstrap %90 GA (`n>=30`), bilinmeyen pazar `endeks yok`, 30/30 test geçti |
| G1.2 Sinyal görünürlüğü | ✅ | (sonraki commit) | `SimpleBriefResponse.signal_accuracy` (eklemeli), `/simple` dürüst veri durumu (`veri yok` / `n/30` / `%X`), 3 satırlık bildirim & Vitest/build yeşil |
| G1.3 "İzle" oranı | ✅ | (sonraki commit) | `evaluate_weekly_watch_ratio()` + haftalık rapor `"Bu hafta: N sinyal, %Y'si izle"` + 4 hafta >%70 prompt onay uyarısı (`weekly_report_state.json`) |
| G2.1 Raporlar `data/reports`'a | ⏳ | — | |
| G2.2 Ortama bağlı testler | ⏳ | — | |
| G2.3 Rapor gürültüsü | ⏳ | — | |
| G2.4 Küçük temizlikler | ⏳ | — | |
| G2.5 v4 kartı | ⏳ | — | |
| G3.1 Kayma ölçümü (aylık) | ⏳ | — | İlk: Aralık başı |
| G3.2 Kontrol noktaları | ⏳ | — | 21 Ara, 6 Oca, 19 Şub, 2 Nis |
| G3.4 Kapı kararı | ⏳ | — | 14 Mayıs 2027 |

---

## Ek: Antigravity'ye verilecek başlangıç mesajı

> `E:\daily_stock_analysis` reposunda `feat/cli-mcp-quant-tournament` dalındasın. Önce `docs/HANDOVER_ANTIGRAVITY.md`'yi, sonra `docs/ANTIGRAVITY_PLAN.md`'yi oku ve plana sırayla uy.
> Faz 0 ile başla (kod değişikliği yok). Sonuçları handover notundaki ölçüm tablosuna yaz ve bana özetle. Sonra Faz 1 G1.1'e geç.
> Kurallar:
> - Dondurulmuş strateji koduna dokunma.
> - `ALPACA_PAPER=true` ve `ALPACA_AUTO_EXECUTE=false` asla değişmez.
> - Veri yoksa uydurma, "veri yok" de.
> - Komutları `.venv\Scripts\python.exe` ile ve ayrı satırlarda çalıştır.
> - Commit mesajları İngilizce olsun, `Co-Authored-By` olmasın. Push yalnızca bu dala.
> - Her görevden sonra planın 9. bölümündeki ilerleme tablosunu güncelle.
> - İletişim dili Türkçe.
