# Çoklu Evren Ampirik Strateji Turnuvası Raporu

- **Oluşturulma:** `2026-11-21T21:27:40+00:00`
- **Örneklem Dışı (OOS) Dönem:** `2022-01-01 → 2026-11-21`
- **Toplam Strateji (N):** `25` · **Toplam Varlık:** `52` · **Varlık-Gün Gözlem:** `152,337`
- **Metodoloji:** Sıfır lookahead (`T` kapanış → `T+1` işlem), çift yönlü işlem maliyeti düşülmüş net getiri, Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR).

## Canlı Şampiyon & Meta-Portföy Dağılımları

- **Şampiyon (`META_US_ETF_ALL_WEATHER`):** BIL %80 · SHY %20 (OOS CAGR `10.92%`, Sharpe `1.13`, MaxDD `-8.32%`, DSR `%63.5`)
- **Meta-Portföy A (`META_US_ETF_ALL_WEATHER`):** BIL %80 · SHY %20 (OOS CAGR `10.92%`, Sharpe `1.13`, MaxDD `-8.32%`)
- **Meta-Portföy B (`META_GLOBAL_ETF_CRYPTO_TREND`):** BIL %64 · SHY %16 · Nakit %20 (OOS CAGR `8.81%`, Sharpe `0.98`, MaxDD `-9.57%`)

## Turnuva Liderlik Tablosu (OOS Net · Risksiz Faiz `BIL` Üstü Excess Sharpe)

| Strateji | Evren | Karar | OOS CAGR | ExRF CAGR | ExRF Sharpe | MaxDD | Recovery | DSR (`N=25`) | Güncel Hedef |
| :--- | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| **Meta-Portföy A v2 (ABD Ortogonal ETF Ensemble)** | `meta` | `PASS_ELITE` | +10.9% | +7.0% | +0.73 | -8.3% | 7.88x | %63.5 | BIL %80 · SHY %20 |
| **Nasdaq-100 (QQQ) 50/200G Çift Trend** | `us_etf` | `PASS_ELITE` | +13.0% | +9.1% | +0.69 | -13.6% | 5.95x | %61.5 | BIL %100 |
| **Meta-Portföy B (Küresel ETF + Kripto Trend)** | `meta` | `PASS_ELITE` | +8.8% | +4.9% | +0.66 | -9.6% | 8.55x | %63.2 | BIL %64 · SHY %16 · Nakit %20 |
| **Safe-Haven Altın & Tahvil Rotasyonu** | `us_etf` | `PASS_ELITE` | +12.6% | +8.7% | +0.57 | -19.6% | 3.98x | %47.2 | BIL %100 |
| **Protective Asset Allocation (PAA Çöküş Kalkanı)** | `us_etf` | `PASS_ELITE` | +10.3% | +6.5% | +0.56 | -12.9% | 4.76x | %49.3 | BIL %100 |
| **Kripto BTC-USD 200G SMA Trend** | `crypto` | `PASS_ELITE` | +24.8% | +19.1% | +0.46 | -32.2% | 6.05x | %52.8 | %100 Nakit (savunma/trend dışı) |
| **Vol-Target Multi-Asset Trend (%10 Hedef Vol)** | `us_etf` | `PASS_SOLID` | +5.9% | +2.0% | +0.36 | -6.9% | 4.65x | %30.6 | SHY %100 |
| **ABD Faktör ETF Rotasyonu (MTUM/QUAL/USMV/VLUE)** | `us_sectors` | `PASS_SOLID` | +8.2% | +4.3% | +0.33 | -24.0% | 1.95x | %30.4 | USMV %100 |
| **Kripto 5-SMA Trend Ensemble (BTC+ETH)** | `crypto` | `PASS_SOLID` | +17.8% | +12.1% | +0.31 | -30.6% | 4.02x | %39.3 | %100 Nakit (savunma/trend dışı) |
| **ABD Sektör Momentum Top-3 (Trend Filtreli)** | `us_sectors` | `PASS_SOLID` | +7.2% | +3.3% | +0.27 | -18.1% | 2.22x | %27.8 | XLV %33.3 · XLF %33.3 · XLE %33.3 |
| **S&P 500 (SPY) 200G SMA Zamanlama** | `us_etf` | `PASS_SOLID` | +6.3% | +2.4% | +0.25 | -22.6% | 1.52x | %25.3 | SHY %100 |
| **Dual Momentum (Antonacci GEM)** | `us_etf` | `PASS_SOLID` | +5.0% | +1.1% | +0.15 | -27.8% | 0.97x | %18.4 | VGK %100 |
| **Referans: Buy & Hold S&P 500 (SPY)** | `us_etf` | `BENCHMARK` | +9.3% | +5.4% | +0.38 | -24.5% | 2.20x | %34.3 | SPY %100 |
| **Referans: Klasik 60/40 (SPY/IEF)** | `us_etf` | `BENCHMARK` | +5.3% | +1.4% | +0.18 | -20.7% | 1.39x | %19.7 | SPY %60 · IEF %40 |
| **Referans: Kripto Al-Tut (50/50 BTC+ETH)** | `crypto` | `BENCHMARK` | -4.5% | -10.1% | -0.01 | -68.4% | -0.29x | %12.0 | BTC-USD %50 · ETH-USD %50 |
| **BIST 52H Zirve + Düşük-Vol Trend Top-5 (TL)** | `bist` | `CAVEAT_SURVIVORSHIP` | +60.3% | +18.8% (USD) | +0.51 (USD) | -26.9% | 33.01x | %59.5 | THYAO.IS %25 · GARAN.IS %25 · YKBNK.IS %25 · PGSUS.IS %25 |
| **BIST 6-1A Momentum Trend Top-5 (TL)** | `bist` | `CAVEAT_SURVIVORSHIP` | +50.5% | +11.6% (USD) | +0.33 (USD) | -29.1% | 21.55x | %42.7 | TUPRS.IS %100 |
| **Kripto BTC/ETH Dual Momentum (100G Trend)** | `crypto` | `FAIL_WEAK` | +11.7% | +6.0% | +0.30 | -56.2% | 1.28x | %26.3 | %100 Nakit (savunma/trend dışı) |
| **Defensive Asset Allocation (DAA Kanarya)** | `us_etf` | `FAIL_WEAK` | +4.7% | +0.8% | +0.12 | -13.7% | 1.82x | %15.8 | BIL %100 |
| **Accelerated Dual Momentum (ADM)** | `us_etf` | `FAIL_WEAK` | +3.7% | -0.2% | +0.08 | -25.6% | 0.76x | %14.7 | SHY %100 |
| **SPY RSI(2) Ortalamaya Dönüş** | `us_etf` | `FAIL_WEAK` | +3.7% | -0.2% | +0.01 | -9.5% | 2.03x | %11.8 | SPY %100 |
| **All-Weather Risk Parity (Vol-Weighted)** | `us_etf` | `FAIL_WEAK` | +3.5% | -0.4% | -0.00 | -18.4% | 0.99x | %9.6 | IEF %39.3 · TLT %22.8 · SPY %14.7 · DBC %13.2 · GLD %10 |
| **Vigilant Asset Allocation (VAA Kanarya Kalkanı)** | `us_etf` | `FAIL_WEAK` | +1.8% | -2.1% | -0.09 | -15.6% | 0.58x | %6.9 | SHY %100 |
| **Faber GTAA-5 (200G Trend Takibi)** | `us_etf` | `FAIL_WEAK` | +2.9% | -1.0% | -0.10 | -10.7% | 1.37x | %7.0 | SHY %100 |
| **ABD Düşük Volatilite Sektör Top-4** | `us_sectors` | `FAIL_WEAK` | -1.8% | -5.7% | -0.32 | -25.2% | -0.33x | %2.8 | XLV %50 · XLP %50 |

## BIST Stratejilerinin Gerçek Dolar (USD) Karşılığı

- **USD/TRY:** `13.3566 → 50.5623` (2022-01-03 → 2026-11-20, yıllık `%+31.4` kur değişimi)
- **Referans XU100.IS:** TL CAGR `+43.7%` → USD CAGR `+9.8%`, BIL üstü USD Sharpe `+0.17`, USD MaxDD `-36.4%`

| BIST Stratejisi | TL CAGR | USD CAGR | USD MaxDD | BIL üstü USD Sharpe | Karar | 2022 USD | 2023 USD | 2024 USD | 2025 USD | 2026 USD |
| :--- | ---: | ---: | ---: | ---: | :---: | ---: | ---: | ---: | ---: | ---: |
| **BIST 52H Zirve + Düşük-Vol Trend Top-5 (TL)** | +60.3% | +22.6% | -43.5% | +0.51 | `CAVEAT_SURVIVORSHIP` | +176.3% | +7.4% | +29.7% | -15.4% | -17.3% |
| **BIST 6-1A Momentum Trend Top-5 (TL)** | +50.5% | +15.4% | -39.8% | +0.33 | `CAVEAT_SURVIVORSHIP` | +92.8% | -4.1% | +7.7% | +2.1% | -1.2% |

> *BIST kararı TL Sharpe ile değil, kur etkisi çıkarılmış USD getirinin `BIL` üstü Sharpe'ı ile verilir (`≥ 0.15` ve pozitif USD fazla getiri). Evren bugünkü likit hisselerden oluştuğu için hayatta kalma yanlılığı sürer.*

> *Not: Tüm sonuçlar geriye dönük ampirik simülasyondur; BIST stratejileri hayatta kalma yanlılığı ve TL enflasyonu nedeniyle `CAVEAT_SURVIVORSHIP` etiketi taşır. Yatırım tavsiyesi değildir.*
