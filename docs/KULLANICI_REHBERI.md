# Daily Stock Analysis (v1.0.0) — Sıfırdan Yatırımcı ve Kullanıcı Rehberi

Bu rehber, finans veya borsa terimlerini hiç bilmeyen standart bir kullanıcının ("Anneme verdiğimde bile tek bakışta anlayabilsin" ilkesiyle) programı güvenle kullanabilmesi için hazırlanmıştır.

---

## 1. Altın Kural: Bu Program Paranızı Otomatik Harcamaz

- **Gerçek Para Kilidi Her Zaman Aktiftir:** Program hiçbir banka, Midas, Alpaca veya Binance hesabınızdan sizin yerinize gerçek parayla otomatik alım-satım **yapmaz** (`ALPACA_PAPER=true`, `ALPACA_AUTO_EXECUTE=false`, `BINANCE_TESTNET=true`, `BINANCE_AUTO_EXECUTE=false`).
- **Ne İşe Yarar?** Piyasaların genel durumunu ("Hava Durumu") her gün kontrol eder, büyük krizlerde paranızı korumak için hangi varlık sepetinde (Nakit/Para Piyasası Fonu, Altın, Hisse) durmanın daha güvenli olduğunu sade Türkçe ile açıklar.

---

## 2. "Bugün Ne Yapayım?" Ekranı (`/simple`)

Programı açtığınızda sol menünün en üstünde veya üst çubuktaki **Basit Mod** düğmesinde **"Bugün Ne Yapayım?" (`/simple`)** ekranı yer alır. Bu ekran 5 sade bölümden oluşur:

### A. Piyasa Hava Durumu Trafik Lambası
- 🟢 **Güneşli (`RISK_ON` — Piyasa Sakin & Yükseliş Eğilimli):** Küresel borsalarda ana trend yukarı yönlüdür. Portföyde büyüme varlıklarına (ABD/Dünya hisse fonları ve altın) dengeli yer verilebilir.
- 🟡 **Parçalı Bulutlu (`CAUTION` — Dalgalı & Seçici Piyasa):** Bazı piyasalar zayıflamaya başlamıştır. Risk azaltılır, güvenli nakit/kısa vadeli tahvil oranı artırılır.
- 🛡️ **Fırtına Kalkanı (`DEFENSIVE` — Koruma Modu Aktif):** Piyasaların çoğunda düşüş trendi vardır. Büyük kayıplardan korunmak için kalkan devreye girer ve portföyün ağırlığı güvenli faiz/para piyasası fonlarına çekilir.

### Veri tarihi ve "veri yok" uyarısı
- Ekrandaki hava durumu ve sepetler, `data/quant_cache/tournament_latest.json` (turnuva) ve `data/quant_cache/research_v3_latest.json` (v3 araştırması) dosyalarındaki **gerçek** hedef ağırlıklardan gelir. Bu dosyaları günlük sanal defter görevi (`scripts/quant_paper.py step`, Windows'ta `daily_paper_step.ps1`) her gün yeniler.
- Dosyalar **5 günden eskiyse** sarı "veriler güncel değil" uyarısı çıkar; öneri o günün piyasasını yansıtır.
- Bir dosya **yoksa** ona dayanan sepet gösterilmez; ikisi de yoksa ekran "Veri Yok" der ve hiçbir dağılım önermez. Program tahmini ya da hazır bir sepet uydurmaz.
- Kur bilgisi canlı TCMB/piyasa verisinden ya da turnuva dosyasından gelir; ikisi de yoksa TL↔USD karşılığı gizlenir ("kur verisi yok").

### B. 3 Adımlı TL Bütçe Hesaplayıcı ve Sepet Planı
1. **Bütçenizi Girin:** Örneğin `50.000 TL` veya `250.000 TL` yazın ya da hazır bütçe düğmelerine tıklayın.
2. **Risk Profilinizi Seçin:**
   - **Çok Temkinli (`v3_trp` — 19 Yıllık Kriz Testli):** 2008 küresel krizini (`-%3,8` maksimum düşüş) ve 2022 ayı piyasasını (`+%3,6`) atlatmış, oynaklığı en düşük koruma sepeti. Bedeli düşük getiri: 2008–2026'da yıllık yaklaşık `%3,8` (nakit BIL `%1,3`).
   - **Dengeli Kalkan (önerilen — Meta-Portföy A v2 + `v3_trp`, %50/%50):** Krizde koruma ile yükselişte katılımı dengeleyen harman sepet.
   - **Büyüme + Kripto Uydu (Meta-Portföy B v2):** %80 dengeli ETF kalkanı + %20 kripto trend dilimi (kripto düşerken nakitte bekler).
   - "En kötü kriz" değeri her sepet için strateji verisinden okunur; veri yoksa `—` görünür.
3. **Nereden Alacağınızı Görün:** Tabloda her satırın yanında hem **Midas / ABD ETF Kodu** (`BIL`, `SHY`, `GLD`, `SPY`, `QQQ`) hem de **Türk Bankası / TEFAS Fon Karşılığı** (*Para Piyasası Fonu*, *Altın Fonu*, *Yabancı Hisse Fonu*) ve tam **TL tutarı** yazar.

### C. Tek Tuşla 100.000 TL Sanal Deneme Kasası
- Cebinizden tek kuruş çıkmadan sanal `100.000 TL` ile bugünkü önerilen sepeti başlatabilir, gerçek fiyatlarla her gün nasıl ilerlediğini takip edebilirsiniz.

### D. 120 İşlem Günlük Canlı Sınav Sayacı (İleri Doğrulama)
- Geçmiş testlerde başarılı olan stratejilerimiz **20 Kasım 2026** tarihinde kodları ve parametreleri kilitlenerek (`paa: 87e22a6b3559`, `meta_a: 37a7ab36a0d9`, `v3_trp: ae4754108564`) **120 işlem günlük (yaklaşık 6 aylık)** canlı sınava alınmıştır.
- Sınav sayacı `120 / 120` günü tamamlayıp tüm güvenlik kriterlerini geçmeden gerçek parayla otomatik işlem kilidi açılmaz.

### E. Midas ve Türkiye Köprüleri Özeti
- **Midas Ekstresi Yükle (CSV / XLSX):** Midas veya aracı kurumunuzdan indirdiğiniz işlem ekstresini yükleyip portföyünüzü tek tıkla içe aktarabilirsiniz.
- **Canlı TEFAS Fon Karşılaştırması:** Bankanızdan alabileceğiniz Para Piyasası, Altın, Eurobond ve Yabancı Hisse fonlarının güncel getirilerini görebilirsiniz.
- **Sanal Kripto Testnet (Binance) & Sanal ABD Borsası (Alpaca):** Kripto ve ABD ETF stratejilerinin sanal emir ve kayma (slippage) ölçümlerini izleyebilirsiniz.

---

## 3. "Öğren & Sözlük" Ekranı (`/guide`)

Sol menüdeki **Öğren & Sözlük (`/guide`)** sayfasında:
- **30 Saniyelik 6 Ders Kartı:**
  1. *Bu Program Ne Yapar, Ne Yapmaz?*
  2. *Neden Büyük Kayıplardan Korunmak En Önemlisidir? (%50 düşüşün matematiği)*
  3. *Midas veya Türk Bankasında Nasıl Uygulanır?*
  4. *Neden Her Gün Al-Sat Yapmıyoruz? (Ayda 1 kez dengeleme disiplini)*
  5. *120 Günlük Canlı Sınav Nedir?*
  6. *Haberler ve Sosyal Medya (X/Twitter) Dedikodularına Karşı Kalkan*
- **Sade Türkçe Finans Sözlüğü:** Arama kutusuna `CAGR`, `Sharpe`, `MaxDD`, `TEFAS`, `ETF`, `Kayma`, `Sanal Defter` gibi herhangi bir terimi yazdığınızda günlük hayattan örneklerle açıklamasını bulabilirsiniz.
- Ayrıca programın her yerinde terimlerin yanındaki **`(?)`** ikonuna tıkladığınızda aynı sade Türkçe açıklama penceresi açılır.

---

## 4. Basit Mod ve Uzman Modu Arasında Geçiş

- Üst çubuğun sağ tarafında **[Basit Mod | Uzman]** anahtarı bulunur.
- **Basit Mod** seçildiğinde karmaşık teknik menüler gizlenir; yalnızca günlük kullanım için gereken temel sayfalar (*Bugün Ne Yapayım?*, *Öğren & Sözlük*, *Portföy*, *Sanal İşlem*, *AI Sor*) görünür.
- **Uzman** moduna geçtiğinizde 25 stratejili turnuva liderlik tablosu, **QuantStats Görsel Tearsheet** (aylık getiri ısı haritası, düşüş eğrisi, TL/USD/TÜFE reel alım gücü kıyası), SEC Form 4, PEAD 2.0 ve BIST/KAP taramaları açılır.

---

## 5. Sık Sorulan Sorular

1. **Bu programı kullanmak için her gün ekran başında durmam gerekir mi?**
   Hayır. Temel stratejilerimiz (`v3_trp`, `paa`, `meta_a`) **ayda 1 kez** (ay başında) kontrol edilmek üzere tasarlanmıştır.
2. **İnternetteki veya X (Twitter) üzerindeki hisse duyumlarına göre mi alım yapıyor?**
   Hayır. Sosyal medya söylentileri matematiksel ağırlıkları asla değiştiremez. Yalnızca resmi KAP bildirimleri, SEC Form 4 yönetici işlemleri ve resmi haber akışı kontrol amaçlı taranır.
3. **ABD borsası hesabım yok, sadece Türkiye'deki bankamı kullanıyorum. Yine de yararlanabilir miyim?**
   Evet. `/simple` ekranındaki bütçe tablosunda her varlığın yanında Türkiye'deki tüm bankalardan alabileceğiniz **TEFAS fon kategorisi karşılığı** yer alır.
