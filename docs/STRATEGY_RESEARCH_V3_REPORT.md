# Strateji Araştırması v3 (Öncelik D) — 19 Yıllık Çok-Rejimli Doğrulama Raporu

> **Oluşturulma:** 2026-11-21T21:33:49+00:00  
> **Değerlendirme Aralığı:** `2008-01-01` → günümüz (4 makro rejim: 2008 GFC, 2013–19 QE, 2020–21 COVID, 2022–26 Faiz Şoku)  
> **Kümülatif Çoklu Test Sayısı (`DSR N`):** `28` (25 mevcut turnuva stratejisi + yeni v3 adayları)  
> **İzolasyon Güvencesi:** Dondurulmuş `PAA v2` ve `Meta-Portföy A v2` fonksiyonlarına dokunulmadı; parmak izleri korunmuştur. `ALPACA_PAPER=true` & `ALPACA_AUTO_EXECUTE=false`.

---

## 1. Özet Karar Tablosu (`2008–2026`, Net Maliyet, `BIL` Risksiz Faiz Üstü)

| Strateji | Karar | Kapı | 2008+ CAGR | ExBIL CAGR | ExBIL Sharpe (5bps) | ExBIL Sharpe (25bps) | MaxDD | Devir | Meta-A Kor. | Canlı Hedef |
| :--- | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| *Referans: S&P 500 (`SPY`)* | BENCHMARK | — | +10.61% | +9.29% | +0.54 | — | -51.9% | 0.0x | — | SPY %100 |
| *Referans: T-Bill (`BIL`)* | RISK-FREE | — | +1.32% | 0.00% | 0.00 | 0.00 | -0.8% | 0.0x | — | BIL %100 |
| **V3_TSMOM_CROSS_ASSET** | ❌ RED | 4/5 | +5.20% | +3.89% | +0.62 | +0.46 | -9.5% | 5.1x | 0.76 | BIL %38.7 · UUP %30 · IEF %14.8 · EFA %5.9 · SPY %5.5 |
| **V3_TREND_RISK_PARITY_BIL** | ✅ TERFİ | 5/5 | +3.80% | +2.49% | +0.63 | +0.47 | -7.3% | 3.2x | 0.61 | BIL %83.3 · UUP %16.7 |
| **V3_SECTOR_FACTOR_BREADTH_BIL** | ✅ TERFİ | 5/5 | +5.84% | +4.53% | +0.46 | +0.30 | -20.1% | 8.9x | 0.46 | BIL %66.7 · XLV %11.1 · XLE %11.1 · USMV %11.1 |

## 2. Rejim Bazlı (4 Makro Dönem) ExBIL Performans

| Strateji | 2008–12 GFC (ExCAGR / ExSh) | 2013–19 QE (ExCAGR / ExSh) | 2020–21 COVID (ExCAGR / ExSh) | 2022–26 Faiz (ExCAGR / ExSh) |
| :--- | :---: | :---: | :---: | :---: |
| **V3_TSMOM_CROSS_ASSET** | +5.81% / +0.81 | +2.05% / +0.40 | +8.20% / +1.10 | +2.62% / +0.42 |
| **V3_TREND_RISK_PARITY_BIL** | +2.41% / +0.47 | +1.66% / +0.57 | +5.79% / +1.27 | +2.26% / +0.67 |
| **V3_SECTOR_FACTOR_BREADTH_BIL** | +4.20% / +0.42 | +6.78% / +0.71 | +13.17% / +0.83 | -2.24% / -0.17 |

## 3. Maliyet Stresi (`5 / 15 / 25 / 50 bps`) ve Kapı Detayları

### V3_TSMOM_CROSS_ASSET — v3 Çapraz-Varlık TSMOM / Managed Futures Vekili (BIL) (`REJECTED`)
- **Açıklama:** 5 varlık sınıfında (SPY/EFA, TLT/IEF, GLD, DBC, UUP) 1-3-6-12A BIL üstü sürekli zaman serisi momentum + 63G ters-volatilite (%10 hedef vol) + BIL nakit.
- **Maliyet Stresi:** 5bps: CAGR +5.20% · ExBIL +3.89% · ExSh +0.62 | 15bps: CAGR +4.66% · ExBIL +3.35% · ExSh +0.54 | 25bps: CAGR +4.13% · ExBIL +2.82% · ExSh +0.46 | 50bps: CAGR +2.80% · ExBIL +1.49% · ExSh +0.26
- **Meta-A v2 Ortogonallik (2018-01-02 → 2026-11-20):** Korelasyon `0.756` (2022+: `0.806`) · Optimizasyonsuz 50/50 Harman ExSh `+0.74` (MaxDD `-7.9%`) vs Tekil Meta-A `+0.83` (MaxDD `-8.3%`)
  - `✓` **gate1_multi_era_and_concentration:** 4/4 rejim pozitif ExBIL (hedef >=3); en iyi yıl (2011) payı %16.9 (hedef <=%50)
  - `✓` **gate2_cost_stress_5_and_25bps:** 5bps ExSh=+0.62 (>=0.35); 25bps ExSh=+0.46 (>=0.20), ExCAGR=+2.82%
  - `✓` **gate3_crisis_protection:** 2022: -1.51% vs SPY -18.18%; 2008 MaxDD: -5.27% (>=-25%); Genel MaxDD: -9.5% (>=-22%)
  - `✓` **gate4_parameter_plateau:** 9/9 komşu geçti (%100, hedef >=%75)
  - `✗` **gate5_orthogonality_vs_meta_a:** Korelasyon=0.756 (<0.70); 50/50 harman ExSh=0.74 vs Meta-A=0.83

### V3_TREND_RISK_PARITY_BIL — v3 Vol-Yönetimli Trend-Frenli Risk Paritesi (BIL) (`PROMOTE_TO_FORWARD_PAPER`)
- **Açıklama:** SPY/TLT/IEF/GLD/DBC/UUP makro havuzunda SMA200 + BIL trend filtresi, ters-volatilite ağırlığı, Moreira-Muir 21G volatilite freni (%8) ve %10 histerezis.
- **Maliyet Stresi:** 5bps: CAGR +3.80% · ExBIL +2.49% · ExSh +0.63 | 15bps: CAGR +3.47% · ExBIL +2.16% · ExSh +0.55 | 25bps: CAGR +3.13% · ExBIL +1.82% · ExSh +0.47 | 50bps: CAGR +2.30% · ExBIL +0.99% · ExSh +0.26
- **Meta-A v2 Ortogonallik (2018-01-02 → 2026-11-20):** Korelasyon `0.612` (2022+: `0.679`) · Optimizasyonsuz 50/50 Harman ExSh `+0.91` (MaxDD `-5.4%`) vs Tekil Meta-A `+0.83` (MaxDD `-8.3%`)
  - `✓` **gate1_multi_era_and_concentration:** 4/4 rejim pozitif ExBIL (hedef >=3); en iyi yıl (2008) payı %14.3 (hedef <=%50)
  - `✓` **gate2_cost_stress_5_and_25bps:** 5bps ExSh=+0.63 (>=0.35); 25bps ExSh=+0.47 (>=0.20), ExCAGR=+1.82%
  - `✓` **gate3_crisis_protection:** 2022: 3.59% vs SPY -18.18%; 2008 MaxDD: -3.83% (>=-25%); Genel MaxDD: -7.3% (>=-22%)
  - `✓` **gate4_parameter_plateau:** 9/9 komşu geçti (%100, hedef >=%75)
  - `✓` **gate5_orthogonality_vs_meta_a:** Korelasyon=0.612 (<0.70); 50/50 harman ExSh=0.91 vs Meta-A=0.83

### V3_SECTOR_FACTOR_BREADTH_BIL — v3 Genişlik-Kalkanlı Sektör & Faktör Risk-Ayarlı Momentum (BIL) (`PROMOTE_TO_FORWARD_PAPER`)
- **Açıklama:** Dinamik kuruluş filtreli 11 S&P sektörü + 4 faktör (MTUM/QUAL/USMV/VLUE) havuzunda SMA200 + 6-1A risk-ayarlı momentum Top-3 + doğrusal genişlik kalkanı (BIL).
- **Maliyet Stresi:** 5bps: CAGR +5.93% · ExBIL +4.62% · ExSh +0.46 | 15bps: CAGR +4.99% · ExBIL +3.68% · ExSh +0.38 | 25bps: CAGR +4.06% · ExBIL +2.75% · ExSh +0.30 | 50bps: CAGR +1.76% · ExBIL +0.45% · ExSh +0.10
- **Meta-A v2 Ortogonallik (2018-01-02 → 2026-11-20):** Korelasyon `0.463` (2022+: `0.538`) · Optimizasyonsuz 50/50 Harman ExSh `+0.59` (MaxDD `-12.4%`) vs Tekil Meta-A `+0.83` (MaxDD `-8.3%`)
  - `✓` **gate1_multi_era_and_concentration:** 3/4 rejim pozitif ExBIL (hedef >=3); en iyi yıl (2013) payı %29.5 (hedef <=%50)
  - `✓` **gate2_cost_stress_5_and_25bps:** 5bps ExSh=+0.46 (>=0.35); 25bps ExSh=+0.30 (>=0.20), ExCAGR=+2.75%
  - `✓` **gate3_crisis_protection:** 2022: -10.67% vs SPY -18.18%; 2008 MaxDD: -2.71% (>=-25%); Genel MaxDD: -20.1% (>=-22%)
  - `✓` **gate4_parameter_plateau:** 9/9 komşu geçti (%100, hedef >=%75)
  - `✓` **gate5_orthogonality_vs_meta_a:** Korelasyon=0.463 (<0.70); 50/50 harman ExSh=0.59 vs Meta-A=0.83
