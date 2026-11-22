export interface GlossaryEntry {
  key: string;
  term: string;
  shortTitle: string;
  plainDefinition: string;
  everydayExample: string;
  category: 'temel' | 'kalkan' | 'turkiye' | 'risk';
}

export interface GuideLessonCard {
  id: string;
  emoji: string;
  readTime: string;
  title: string;
  summary: string;
  bullets: string[];
}

export const INVESTOR_GLOSSARY: Record<string, GlossaryEntry> = {
  etf: {
    key: 'etf',
    term: 'ETF (Borsa Yatırım Fonu)',
    shortTitle: 'Hazır Sepet Fonu',
    plainDefinition:
      'Tek bir şirket yerine onlarca veya yüzlerce şirketi tek işlemle almanı sağlayan hazır yatırım sepetidir.',
    everydayExample:
      'Manavdan tek bir elma yerine mevsim meyveleri kasası almak gibidir; biri çürük çıksa bile diğerleri seni korur. Örnek: SPY (ABD’nin en büyük 500 şirketi).',
    category: 'temel',
  },
  bil_ppf: {
    key: 'bil_ppf',
    term: 'BIL / Para Piyasası Fonu (PPF)',
    shortTitle: 'Güvenli Nakit Park Yeri',
    plainDefinition:
      'Piyasalar fırtınalıyken paranın değer kaybetmeden kısa vadeli faiz/getiri üretip beklediği en güvenli araçtır.',
    everydayExample:
      'ABD borsasında BIL (1–3 aylık ABD devlet bonosu), Türkiye’de ise bankaların ve Midas’ın sunduğu TEFAS Para Piyasası Fonu (PPF) aynı görevi görür.',
    category: 'turkiye',
  },
  tefas: {
    key: 'tefas',
    term: 'TEFAS (Türkiye Fon Platformu)',
    shortTitle: 'Bankadan Alınabilen Hazır Fonlar',
    plainDefinition:
      'Türkiye’deki tüm bankaların ve aracı kurumların yatırım fonlarını (Para Piyasası, Altın, Hisse, Döviz) tek ekrandan karşılaştırıp alabilmeni sağlayan resmi devlet platformudur.',
    everydayExample:
      'Yurt dışı borsa hesabı açmadan bile Ziraat, Garanti, İş Bankası veya Midas üzerinden 30 saniyede TEFAS Altın Fonu veya Para Piyasası Fonu alabilirsin.',
    category: 'turkiye',
  },
  trend_kalkan: {
    key: 'trend_kalkan',
    term: 'Trend & 200 Günlük Ortalama',
    shortTitle: 'Piyasa Hava Durumu Ölçeri',
    plainDefinition:
      'Bir yatırım aracının bugünkü fiyatını son ~1 yıllık (200 iş günü) ortalama fiyatıyla kıyaslar. Fiyat ortalamanın altındaysa rüzgâr terse dönmüş demektir.',
    everydayExample:
      'Dışarı çıkmadan önce termometreye bakıp mont giymek gibidir; fırtına başlamadan koruma kalkanını açmamızı sağlar.',
    category: 'kalkan',
  },
  risk_off: {
    key: 'risk_off',
    term: 'Koruma Modu (Risk-Off)',
    shortTitle: 'Fırtınada Limana Sığınma',
    plainDefinition:
      'Borsaların geniş bölümü düşüşe geçtiğinde hisse ve kriptodan çıkıp güvenli nakit/bono araçlarına geçme kuralıdır.',
    everydayExample:
      'Dalgalar yükseldiğinde tekneyi açık denizde bırakmak yerine limana çekip fırtınanın dinmesini beklemek gibidir.',
    category: 'kalkan',
  },
  rebalance: {
    key: 'rebalance',
    term: 'Aylık Dengeleme (Rebalance)',
    shortTitle: 'Ayda 1 Kez Sepeti Düzenleme',
    plainDefinition:
      'Her gün al-sat yapmak yerine ayda sadece 1 kez (genelde ay başında) sepet oranlarını güncel hedefe göre düzenlemektir.',
    everydayExample:
      'Her gün ekran başında stres olmak ve yüksek komisyon ödemek yerine ayda 5 dakika ayırıp sepeti yenilemek çok daha kazançlı ve sakindir.',
    category: 'temel',
  },
  max_dd: {
    key: 'max_dd',
    term: 'En Büyük Düşüş (Max Drawdown)',
    shortTitle: 'En Kötü Gün Senaryosu',
    plainDefinition:
      'Bir stratejinin geçmişte zirve noktasından en dip noktasına kadar geçici olarak en fazla yüzde kaç değer kaybettiğini gösterir.',
    everydayExample:
      '100.000 TL’lik sepet en kötü krizde 93.000 TL’ye gerilediyse en büyük düşüş -%7’dir. S&P 500 borsası 2008 krizinde -%52 düşmüştü.',
    category: 'risk',
  },
  ex_bil_sharpe: {
    key: 'ex_bil_sharpe',
    term: 'BIL Üstü Sharpe (Risk Başına Gerçek Kazanç)',
    shortTitle: 'Aldığın Riske Değdi mi?',
    plainDefinition:
      'Bir stratejinin risksiz devlet bonosu/faiz (BIL) üzerinde ne kadar ek kazanç ürettiğini, yaşattığı dalgalanmaya bölerek ölçer.',
    everydayExample:
      '0,50 ve üzeri iyi, 0,70 ve üzeri çok güçlüdür. 0’ın altındaysa boşuna risk alınmış, parayı faizde bırakmak daha iyi olmuş demektir.',
    category: 'risk',
  },
  slippage: {
    key: 'slippage',
    term: 'Kayma & İşlem Maliyeti (bps)',
    shortTitle: 'Alım-Satım Komisyon ve Makas Payı',
    plainDefinition:
      'Ekranda gördüğün fiyat ile emrinin gerçekleştiği fiyat arasındaki küçük fark ve aracı kurum komisyonudur. 10 bps = %0,10 demektir.',
    everydayExample:
      '100.000 TL’lik işlemde %0,05 (5 bps) maliyet yaklaşık 50 TL tutar. Çok sık al-sat yapan robotlar bu masraflarla kârını eritir.',
    category: 'risk',
  },
  forward_gate: {
    key: 'forward_gate',
    term: '120 Günlük Canlı Sınav (İleri Doğrulama)',
    shortTitle: 'Gerçek Para Öncesi 6 Aylık Test',
    plainDefinition:
      'Strateji kurallarını kilitleyip (parmak izi alarak) 120 iş günü (~6 ay) boyunca gerçek piyasa fiyatlarıyla sanal kasada takip etme sürecidir.',
    everydayExample:
      'Geçmiş sınav sorularına çalışıp yüksek not almak kolaydır; asıl kanıt yeni gelecek gerçek sınavda (bugünden sonraki 6 ayda) geçmektir.',
    category: 'kalkan',
  },
  uup_dollar: {
    key: 'uup_dollar',
    term: 'UUP (ABD Dolar Endeksi)',
    shortTitle: 'Küresel Dolar Gücü Kalkanı',
    plainDefinition:
      'ABD Dolarının Euro, Yen ve Sterlin gibi büyük para birimlerine karşı değerini takip eden fondur.',
    everydayExample:
      '2022 yılında hem borsalar hem tahviller birlikte düşerken dolar güçlenmişti; v3 stratejimiz bu sayede 2022 krizinde bile artıda kaldı.',
    category: 'kalkan',
  },
  paper_trading: {
    key: 'paper_trading',
    term: 'Sanal İşlem (Paper Trading)',
    shortTitle: 'Gerçek Para Harcamadan Deneme',
    plainDefinition:
      'Gerçek piyasa fiyatlarını kullanarak ama sıfır gerçek para riske atarak sanal bir bütçeyle stratejiyi canlı takip etmektir.',
    everydayExample:
      'Uçak pilotlarının gerçek yolcu taşımadan önce simülatörde uçması gibidir; bu programda otomatik gerçek emir kilidi daima kapalıdır.',
    category: 'temel',
  },
  bist_usd: {
    key: 'bist_usd',
    term: 'BIST Dolar Bazlı Getiri',
    shortTitle: 'Enflasyondan Arındırılmış Gerçek Kazanç',
    plainDefinition:
      'Borsa İstanbul’da TL bazında %50 kazanmak, dolar aynı yıl %35 arttıysa gerçekte çok daha düşük dolar getirisi demektir.',
    everydayExample:
      'Bu yüzden program BIST hisselerini ve stratejilerini mutlaka Dolar bazlı gerçek alım gücüne çevirerek gösterir.',
    category: 'turkiye',
  },
  vix: {
    key: 'vix',
    term: 'VIX (Korku Endeksi)',
    shortTitle: 'Piyasa Panik Termometresi',
    plainDefinition:
      'ABD borsasındaki yatırımcıların önümüzdeki 30 gün için beklediği dalgalanmayı ölçer. 20 altı sakin, 30 üstü fırtınalı piyasa işaretidir.',
    everydayExample:
      'VIX 35 civarındaysa piyasada korku çok yüksektir; kalkanımızın koruma modunda kalması tamamen normal ve koruyucudur.',
    category: 'kalkan',
  },
};

export const GUIDE_LESSONS: GuideLessonCard[] = [
  {
    id: 'lesson-1',
    emoji: '🌤️',
    readTime: '30 sn',
    title: '1. Bu Program Ne Yapar, Ne Yapmaz?',
    summary: 'Sihirli zengin olma makinesi değil; panik yapmanı engelleyen disiplinli bir koruma ve rehberlik sistemidir.',
    bullets: [
      'Her gün piyasaların hava durumuna bakar: Güneşliyse büyüme sepetini, fırtınalıysa güvenli nakit/bono kalkanını önerir.',
      'Hiçbir banka veya aracı kurum hesabından senin onayın olmadan tek kuruşluk gerçek işlem yapmaz.',
      'Hedefi bir gecede katlamak değil, büyük krizlerde (-%50 düşüşlerde) paranı koruyup yıllar içinde enflasyonun ve faizin üstünde büyütmektir.',
    ],
  },
  {
    id: 'lesson-2',
    emoji: '🛡️',
    readTime: '30 sn',
    title: '2. Neden Büyük Kayıplardan Korunmak En Önemlisidir?',
    summary: 'Matematik basittir: %50 kaybedersen eski parana dönmek için %100 kazanman gerekir.',
    bullets: [
      '100.000 TL paran %50 düşerse 50.000 TL kalır; tekrar 100.000 TL olmak için tam 2 katına çıkması gerekir.',
      'Oysa kalkan sayesinde düşüşü -%7 civarında sınırlayabilirsen, piyasa normale döndüğünde çok hızlı artıya geçersin.',
      'v3 Temkinli Kalkan stratejimiz 2008 küresel krizinde sadece -%3,8 düştü, 2022 ayı piyasasında ise +%3,6 artıda kapattı.',
    ],
  },
  {
    id: 'lesson-3',
    emoji: '🏦',
    readTime: '45 sn',
    title: '3. Midas veya Türk Bankasında Nasıl Uygulanır?',
    summary: 'Yurt dışı hesabın olmasa bile Türkiye’deki her bankadan benzer güvenli sepet kurulabilir.',
    bullets: [
      'Midas ABD hesabın varsa: Bütçe hesaplayıcıdaki BIL, SHY, UUP, GLD veya SPY kodlarını doğrudan Midas → ABD Borsaları’ndan görebilirsin.',
      'Sadece Türk bankası (Ziraat, İş, Garanti vb.) veya Midas Fon kullanıyorsan: Her satırın yanında yazan TEFAS karşılığını (Para Piyasası Fonu, Altın Fonu, Yabancı Hisse Fonu) tercih edebilirsin.',
      'Ayda 1 kez (ay başında) "Bugün Ne Yapayım?" ekranına bakıp oranlar ciddi değiştiyse güncellemen yeterlidir.',
    ],
  },
  {
    id: 'lesson-4',
    emoji: '📆',
    readTime: '30 sn',
    title: '4. Neden Her Gün Al-Sat Yapmıyoruz?',
    summary: 'Çok sık al-sat yapan stratejiler komisyon, makas (kayma) ve duygusal hatalarla kârını eritir.',
    bullets: [
      'Geçmiş testlerimizde yılda 55 kez işlem yapan kısa vadeli stratejiler, işlem maliyeti eklendiğinde zarar etti.',
      'Ayda 1 kez dengelenen disiplinli sepetlerimiz yılda yalnızca 3–4 kez küçük ayarlama yapar; yıllık masrafı binde 1’in altındadır.',
    ],
  },
  {
    id: 'lesson-5',
    emoji: '🧪',
    readTime: '30 sn',
    title: '5. "120 Günlük Canlı Sınav" Neden Önemli?',
    summary: 'Geçmiş grafiklere bakıp hemen tüm parayla girmek yerine stratejiyi canlı piyasada sınamalıyız.',
    bullets: [
      'Stratejilerimiz 20 Kasım 2026 itibarıyla donduruldu ve dijital parmak iziyle mühürlendi.',
      '120 iş günü (~6 ay) boyunca gerçek fiyatlarla sanal kasada takip ediliyor; beklenmedik bir sapma olursa sistem uyarı veriyor.',
      'Gerçek parayla denemeye geçsen bile asla acil durum paranı veya kısa vadede ihtiyacın olacak borç/kira paranı riske atma.',
    ],
  },
  {
    id: 'lesson-6',
    emoji: '💬',
    readTime: '30 sn',
    title: '6. Sosyal Medya Duyumlarına Neden Güvenmiyoruz?',
    summary: 'X (Twitter) ve Telegram’daki "tüyo / kulis" paylaşımları çoğu zaman küçük yatırımcıyı tuzağa çeker.',
    bullets: [
      'Ana yatırım sepetlerimiz (Meta-A v2, PAA v2, v3_trp) asla dedikodu veya sosyal medya tüyosuyla hareket etmez; sadece matematiksel fiyat ve risk kurallarına uyar.',
      'Program ayrıca BIST haberlerini tararken "iddia / kulis / duyum" içeren metinleri özel olarak SÖYLENTİ (RUMOR) etiketiyle ayırır.',
    ],
  },
];

export const SIMPLE_CHAT_STARTERS: string[] = [
  'Finans terimi kullanmadan anlat: Bugün piyasa güvenli mi, elimdeki parayı nasıl bölmeliyim?',
  'Midas veya Türk bankasından TEFAS fonlarıyla bugünkü koruma sepetini nasıl kurarım?',
  '100.000 TL ile en düşük riskli (Çok Temkinli) stratejiyi uygulasam en kötü senaryoda ne olur?',
  'Altın, Dolar ve Para Piyasası Fonu arasında bugün sistem hangisini neden seçiyor?',
];
