# Strateji Araştırması v5 — Korelasyon-Duyarlı (Min-Corr) Ağırlıklandırma 1/vol'e Göre Değer Katıyor mu?

> **Oluşturulma:** 2026-11-24T19:31:52+00:00 · **Veri:** 2007-01-03 → 2026-11-24 · **Değerlendirme:** 2008-01-01+ · **Kümülatif deneme sayısı:** 32

Aynı 10 makro ETF (`SPY, QQQ, EFA, EEM, VNQ, TLT, IEF, GLD, DBC, UUP`) ve `BIL` nakit kalkanı üzerinde aynı trend kuralı (`SMA200` + `12A > BIL`) ve aynı `%8` hedef volatilite kullanıldı; iki aday yalnızca `use_corr_penalty` anahtarında ayrılır. Parametreler sonuç görülmeden önce sabitlendi.

## Sonuç

**Min-Corr ağırlıklandırma 1/vol kontrol grubuna göre değer katıyor mu? HAYIR (kanıt yetersiz)**

- 5 bps'de BIL üstü Sharpe farkı +0.00 (gereken ≥ +0.05).
- 25 bps'de BIL üstü Sharpe farkı -0.04 (gereken ≥ +0.05).

| | Min-Corr Trend Risk Paritesi | Basit 1/vol Kontrol |
| :--- | ---: | ---: |
| Karar | `PROMOTE_TO_FORWARD_PAPER` | `PROMOTE_TO_FORWARD_PAPER` |
| CAGR (2008+) | +3.97% | +4.30% |
| BIL üstü Sharpe (5 bps) | +0.61 | +0.61 |
| BIL üstü Sharpe (25 bps) | +0.43 | +0.47 |
| En büyük düşüş | -5.83% | -6.33% |
| 2008 getirisi | +2.80% | +4.53% |
| 2022 getirisi | +1.17% | +0.13% |

## V5_MINCORR_TREND_RISK_PARITY — `PROMOTE_TO_FORWARD_PAPER` (5/5 kapı)

- ✅ `gate1_multi_era_and_concentration`: 4/4 rejim pozitif ExBIL (hedef >=3); en iyi yıl (2021) payı %17.1 (hedef <=%50)
- ✅ `gate2_cost_stress_5_and_25bps`: 5bps ExSh=+0.61 (>=0.35); 25bps ExSh=+0.43 (>=0.20), ExCAGR=+1.86%
- ✅ `gate3_crisis_protection`: 2022: 1.17% vs SPY -18.18%; 2008 MaxDD: -2.46% (>=-25%); Genel MaxDD: -5.8% (>=-22%)
- ✅ `gate4_parameter_plateau`: 9/9 komşu geçti (%100, hedef >=%75)
- ✅ `gate5_orthogonality_vs_meta_a`: Korelasyon=0.662 (<0.70); 50/50 harman ExSh=0.82 vs Meta-A=0.83

| Rejim | CAGR | BIL üstü | BIL üstü Sharpe | MaxDD |
| :--- | ---: | ---: | ---: | ---: |
| Rejim 1: GFC & Sıfır Faiz (2008–2012) | +2.98% | +2.71% | +0.57 | -4.81% |
| Rejim 2: QE Boğası & 2018 Şoku (2013–2019) | +2.67% | +2.06% | +0.56 | -5.83% |
| Rejim 3: COVID Çöküş & V-Toparlanma (2020–2021) | +6.37% | +6.23% | +1.04 | -5.39% |
| Rejim 4: Faiz Şoku & 2026 Krizi (2022–2026) | +5.64% | +1.76% | +0.43 | -4.44% |

- **Küme dağılımı (aktif risk içinde):** Hisse kümesi (`SPY/QQQ/EFA/EEM/VNQ`) %38.5 · Çeşitlendirici küme (`TLT/IEF/GLD/DBC/UUP`) %61.5 · Ortalama toplam risk ağırlığı %52.4.
- **Bugünkü hedef:** BIL %80 · UUP %15 · VNQ %5

## V5_INVVOL_TREND_CONTROL — `PROMOTE_TO_FORWARD_PAPER` (5/5 kapı)

- ✅ `gate1_multi_era_and_concentration`: 4/4 rejim pozitif ExBIL (hedef >=3); en iyi yıl (2021) payı %17.3 (hedef <=%50)
- ✅ `gate2_cost_stress_5_and_25bps`: 5bps ExSh=+0.61 (>=0.35); 25bps ExSh=+0.47 (>=0.20), ExCAGR=+2.25%
- ✅ `gate3_crisis_protection`: 2022: 0.13% vs SPY -18.18%; 2008 MaxDD: -2.18% (>=-25%); Genel MaxDD: -6.3% (>=-22%)
- ✅ `gate4_parameter_plateau`: 9/9 komşu geçti (%100, hedef >=%75)
- ✅ `gate5_orthogonality_vs_meta_a`: Korelasyon=0.698 (<0.70); 50/50 harman ExSh=0.79 vs Meta-A=0.83

| Rejim | CAGR | BIL üstü | BIL üstü Sharpe | MaxDD |
| :--- | ---: | ---: | ---: | ---: |
| Rejim 1: GFC & Sıfır Faiz (2008–2012) | +3.20% | +2.93% | +0.54 | -5.88% |
| Rejim 2: QE Boğası & 2018 Şoku (2013–2019) | +3.17% | +2.56% | +0.64 | -6.13% |
| Rejim 3: COVID Çöküş & V-Toparlanma (2020–2021) | +6.83% | +6.69% | +1.06 | -6.33% |
| Rejim 4: Faiz Şoku & 2026 Krizi (2022–2026) | +5.73% | +1.84% | +0.39 | -5.32% |

- **Küme dağılımı (aktif risk içinde):** Hisse kümesi (`SPY/QQQ/EFA/EEM/VNQ`) %45.5 · Çeşitlendirici küme (`TLT/IEF/GLD/DBC/UUP`) %54.5 · Ortalama toplam risk ağırlığı %53.0.
- **Bugünkü hedef:** BIL %80 · UUP %15 · VNQ %5

> *Geçmiş test sonucudur, gelecek getirinin garantisi değildir. Dondurulmuş ileri doğrulama stratejileri (`paa`, `meta_a`, `v3_trp`) bu araştırmadan etkilenmez.*
