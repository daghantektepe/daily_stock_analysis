# Çoklu Evren Ampirik Strateji Turnuvası Raporu

- **Oluşturulma:** `2026-11-21T11:34:11+00:00`
- **Örneklem Dışı (OOS) Dönem:** `2022-01-01 → 2026-11-21`
- **Toplam Strateji (N):** `25` · **Toplam Varlık:** `52` · **Varlık-Gün Gözlem:** `152,337`
- **Metodoloji:** Sıfır lookahead (`T` kapanış → `T+1` işlem), çift yönlü işlem maliyeti düşülmüş net getiri, Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR).

## Canlı Şampiyon & Meta-Portföy Dağılımları

- **Şampiyon (`META_US_ETF_ALL_WEATHER`):** BIL %80 · SHY %20 (OOS CAGR `10.92%`, Sharpe `1.13`, MaxDD `-8.32%`, DSR `%36.3`)
- **Meta-Portföy A (`META_US_ETF_ALL_WEATHER`):** BIL %80 · SHY %20 (OOS CAGR `10.92%`, Sharpe `1.13`, MaxDD `-8.32%`)
- **Meta-Portföy B (`META_GLOBAL_ETF_CRYPTO_TREND`):** BIL %64 · SHY %16 · Nakit %20 (OOS CAGR `8.81%`, Sharpe `0.98`, MaxDD `-9.57%`)

## Turnuva Liderlik Tablosu (OOS Net · Risksiz Faiz `BIL` Üstü Excess Sharpe)

| Strateji | Evren | Karar | OOS CAGR | ExRF CAGR | ExRF Sharpe | MaxDD | Recovery | DSR (`N=25`) | Güncel Hedef |
| :--- | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| **Meta-Portföy A v2 (ABD Ortogonal ETF Ensemble)** | `meta` | `PASS_ELITE` | +10.9% | +7.0% | +0.73 | -8.3% | 7.88x | %36.3 | BIL %80 · SHY %20 |
| **Nasdaq-100 (QQQ) 50/200G Çift Trend** | `us_etf` | `PASS_ELITE` | +13.0% | +9.1% | +0.69 | -13.6% | 5.95x | %34.3 | BIL %100 |
| **Meta-Portföy B (Küresel ETF + Kripto Trend)** | `meta` | `PASS_ELITE` | +8.8% | +4.9% | +0.66 | -9.6% | 8.55x | %30.6 | BIL %64 · SHY %16 · Nakit %20 |
| **Safe-Haven Altın & Tahvil Rotasyonu** | `us_etf` | `PASS_ELITE` | +12.6% | +8.7% | +0.57 | -19.6% | 3.98x | %22.3 | BIL %100 |
| **Protective Asset Allocation (PAA Çöküş Kalkanı)** | `us_etf` | `PASS_ELITE` | +10.3% | +6.5% | +0.56 | -12.9% | 4.76x | %23.7 | BIL %100 |
| **Kripto BTC-USD 200G SMA Trend** | `crypto` | `PASS_ELITE` | +24.8% | +19.1% | +0.46 | -32.2% | 6.05x | %21.5 | %100 Nakit (savunma/trend dışı) |
| **Vol-Target Multi-Asset Trend (%10 Hedef Vol)** | `us_etf` | `PASS_SOLID` | +5.9% | +2.0% | +0.36 | -6.9% | 4.65x | %11.3 | SHY %100 |
| **ABD Faktör ETF Rotasyonu (MTUM/QUAL/USMV/VLUE)** | `us_sectors` | `PASS_SOLID` | +8.2% | +4.3% | +0.33 | -24.0% | 1.95x | %11.2 | USMV %100 |
| **Kripto 5-SMA Trend Ensemble (BTC+ETH)** | `crypto` | `PASS_SOLID` | +17.8% | +12.1% | +0.31 | -30.6% | 4.02x | %13.0 | %100 Nakit (savunma/trend dışı) |
| **ABD Sektör Momentum Top-3 (Trend Filtreli)** | `us_sectors` | `PASS_SOLID` | +7.2% | +3.3% | +0.27 | -18.1% | 2.22x | %9.8 | XLV %33.3 · XLF %33.3 · XLE %33.3 |
| **S&P 500 (SPY) 200G SMA Zamanlama** | `us_etf` | `PASS_SOLID` | +6.3% | +2.4% | +0.25 | -22.6% | 1.52x | %8.6 | SHY %100 |
| **Dual Momentum (Antonacci GEM)** | `us_etf` | `PASS_SOLID` | +5.0% | +1.1% | +0.15 | -27.8% | 0.97x | %5.5 | VGK %100 |
| **Referans: Buy & Hold S&P 500 (SPY)** | `us_etf` | `BENCHMARK` | +9.3% | +5.4% | +0.38 | -24.5% | 2.20x | %13.3 | SPY %100 |
| **Referans: Klasik 60/40 (SPY/IEF)** | `us_etf` | `BENCHMARK` | +5.3% | +1.4% | +0.18 | -20.7% | 1.39x | %6.0 | SPY %60 · IEF %40 |
| **Referans: Kripto Al-Tut (50/50 BTC+ETH)** | `crypto` | `BENCHMARK` | -4.5% | -10.1% | -0.01 | -68.4% | -0.29x | %2.1 | BTC-USD %50 · ETH-USD %50 |
| **BIST 52H Zirve + Düşük-Vol Trend Top-5 (TL)** | `bist` | `CAVEAT_SURVIVORSHIP` | +60.3% | TRY | 1.64 (TL) | -26.9% | 33.01x | %95.8 | THYAO.IS %25 · GARAN.IS %25 · YKBNK.IS %25 · PGSUS.IS %25 |
| **BIST 6-1A Momentum Trend Top-5 (TL)** | `bist` | `CAVEAT_SURVIVORSHIP` | +50.5% | TRY | 1.39 (TL) | -29.1% | 21.55x | %88.3 | TUPRS.IS %100 |
| **Kripto BTC/ETH Dual Momentum (100G Trend)** | `crypto` | `FAIL_WEAK` | +11.7% | +6.0% | +0.30 | -56.2% | 1.28x | %6.9 | %100 Nakit (savunma/trend dışı) |
| **Defensive Asset Allocation (DAA Kanarya)** | `us_etf` | `FAIL_WEAK` | +4.7% | +0.8% | +0.12 | -13.7% | 1.82x | %4.4 | BIL %100 |
| **Accelerated Dual Momentum (ADM)** | `us_etf` | `FAIL_WEAK` | +3.7% | -0.2% | +0.08 | -25.6% | 0.76x | %4.0 | SHY %100 |
| **SPY RSI(2) Ortalamaya Dönüş** | `us_etf` | `FAIL_WEAK` | +3.7% | -0.2% | +0.01 | -9.5% | 2.03x | %3.0 | SPY %100 |
| **All-Weather Risk Parity (Vol-Weighted)** | `us_etf` | `FAIL_WEAK` | +3.5% | -0.4% | -0.00 | -18.4% | 0.99x | %2.2 | IEF %39.3 · TLT %22.8 · SPY %14.7 · DBC %13.2 · GLD %10 |
| **Vigilant Asset Allocation (VAA Kanarya Kalkanı)** | `us_etf` | `FAIL_WEAK` | +1.8% | -2.1% | -0.09 | -15.6% | 0.58x | %1.4 | SHY %100 |
| **Faber GTAA-5 (200G Trend Takibi)** | `us_etf` | `FAIL_WEAK` | +2.9% | -1.0% | -0.10 | -10.7% | 1.37x | %1.5 | SHY %100 |
| **ABD Düşük Volatilite Sektör Top-4** | `us_sectors` | `FAIL_WEAK` | -1.8% | -5.7% | -0.32 | -25.2% | -0.33x | %0.4 | XLV %50 · XLP %50 |

> *Not: Tüm sonuçlar geriye dönük ampirik simülasyondur; BIST stratejileri hayatta kalma yanlılığı ve TL enflasyonu nedeniyle `CAVEAT_SURVIVORSHIP` etiketi taşır. Yatırım tavsiyesi değildir.*
