# Strateji Araştırması v4 — Short (Ters ETF) Gerçekten Değer Katıyor mu?

> **Oluşturulma:** 2026-11-23T17:40:04+00:00 · **Veri:** 2007-01-03 → 2026-11-23 · **Değerlendirme:** 2008-01-01+ · **Kümülatif deneme sayısı:** 30

Short pozisyon yalnızca **ters ETF satın alarak** alınır (SH, PSQ, EFZ, TBF): kredili hesap, ödünç pay ya da opsiyon yok; bir pozisyonda en fazla yatırılan para kaybedilir. Ters ETF fiyatları günlük sıfırlama kaybını ve yönetim ücretini zaten içerir. Parametreler sonuç görülmeden önce sabitlendi.

## Sonuç

**Short değer katıyor mu? HAYIR (kanıt yetersiz)**

- 5 bps'de BIL üstü Sharpe farkı -0.17 (gereken ≥ +0.05).
- 25 bps'de BIL üstü Sharpe farkı -0.18 (gereken ≥ +0.05).

| | Long/Short (ters ETF) | Long-Only Kontrol |
| :--- | ---: | ---: |
| Karar | `PROMOTE_TO_FORWARD_PAPER` | `REJECTED` |
| CAGR (2008+) | +4.37% | +4.97% |
| BIL üstü Sharpe (5 bps) | +0.51 | +0.68 |
| BIL üstü Sharpe (25 bps) | +0.38 | +0.56 |
| En büyük düşüş | -8.66% | -7.64% |
| 2008 getirisi | +17.39% | +11.27% |
| 2022 getirisi | +2.52% | -1.70% |

## V4_TREND_LONG_SHORT_INVERSE — `PROMOTE_TO_FORWARD_PAPER` (5/5 kapı)

- ✅ `gate1_multi_era_and_concentration`: 4/4 rejim pozitif ExBIL (hedef >=3); en iyi yıl (2008) payı %27.2 (hedef <=%50)
- ✅ `gate2_cost_stress_5_and_25bps`: 5bps ExSh=+0.51 (>=0.35); 25bps ExSh=+0.38 (>=0.20), ExCAGR=+2.22%
- ✅ `gate3_crisis_protection`: 2022: 2.52% vs SPY -18.18%; 2008 MaxDD: -5.01% (>=-25%); Genel MaxDD: -8.7% (>=-22%)
- ✅ `gate4_parameter_plateau`: 9/9 komşu geçti (%100, hedef >=%75)
- ✅ `gate5_orthogonality_vs_meta_a`: Korelasyon=0.666 (<0.70); 50/50 harman ExSh=0.72 vs Meta-A=0.83

| Rejim | CAGR | BIL üstü | BIL üstü Sharpe | MaxDD |
| :--- | ---: | ---: | ---: | ---: |
| Rejim 1: GFC & Sıfır Faiz (2008–2012) | +4.61% | +4.34% | +0.57 | -8.66% |
| Rejim 2: QE Boğası & 2018 Şoku (2013–2019) | +2.82% | +2.21% | +0.50 | -7.31% |
| Rejim 3: COVID Çöküş & V-Toparlanma (2020–2021) | +5.29% | +5.15% | +0.86 | -4.65% |
| Rejim 4: Faiz Şoku & 2026 Krizi (2022–2026) | +5.68% | +1.79% | +0.31 | -7.49% |

- **Short dilimi:** günlerin %47.1'inde aktif; aktifken ortalama ağırlık %16.8 (en çok %47.1); portföye yıllık katkısı -0.30 puan.
- **ETF bazında yıllık katkı (puan):** SH -0.10, PSQ -0.06, EFZ -0.06, TBF -0.08
- **Bugünkü hedef:** BIL %80.9 · TBF %19.1

## V4_TREND_LONG_ONLY_CONTROL — `REJECTED` (4/5 kapı)

- ✅ `gate1_multi_era_and_concentration`: 4/4 rejim pozitif ExBIL (hedef >=3); en iyi yıl (2008) payı %14.3 (hedef <=%50)
- ✅ `gate2_cost_stress_5_and_25bps`: 5bps ExSh=+0.68 (>=0.35); 25bps ExSh=+0.56 (>=0.20), ExCAGR=+2.98%
- ✅ `gate3_crisis_protection`: 2022: -1.7% vs SPY -18.18%; 2008 MaxDD: -3.6% (>=-25%); Genel MaxDD: -7.6% (>=-22%)
- ✅ `gate4_parameter_plateau`: 9/9 komşu geçti (%100, hedef >=%75)
- ❌ `gate5_orthogonality_vs_meta_a`: Korelasyon=0.767 (<0.70); 50/50 harman ExSh=0.78 vs Meta-A=0.83

| Rejim | CAGR | BIL üstü | BIL üstü Sharpe | MaxDD |
| :--- | ---: | ---: | ---: | ---: |
| Rejim 1: GFC & Sıfır Faiz (2008–2012) | +4.58% | +4.30% | +0.68 | -6.85% |
| Rejim 2: QE Boğası & 2018 Şoku (2013–2019) | +3.98% | +3.37% | +0.79 | -6.80% |
| Rejim 3: COVID Çöküş & V-Toparlanma (2020–2021) | +6.91% | +6.77% | +1.06 | -7.64% |
| Rejim 4: Faiz Şoku & 2026 Krizi (2022–2026) | +5.69% | +1.80% | +0.35 | -5.58% |
- **Bugünkü hedef:** BIL %100

> *Geçmiş test sonucudur, gelecek getirinin garantisi değildir. Ters ETF'ler uzun süre tutulduğunda değer kaybeder (örn. SH 2010–2026: %−90); yalnızca trend kuralıyla ve kısa süreli kullanılmalıdır.*
