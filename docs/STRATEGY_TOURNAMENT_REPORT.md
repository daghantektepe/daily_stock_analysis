# Çoklu Evren Ampirik Strateji Turnuvası Raporu

- **Oluşturulma:** `2026-11-20T08:30:55+00:00`
- **Örneklem Dışı (OOS) Dönem:** `2022-01-01 → 2026-11-20`
- **Toplam Strateji (N):** `25` · **Toplam Varlık:** `52` · **Varlık-Gün Gözlem:** `152,282`
- **Metodoloji:** Sıfır lookahead (`T` kapanış → `T+1` işlem), çift yönlü işlem maliyeti düşülmüş net getiri, Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR).

## Canlı Şampiyon & Meta-Portföy Dağılımları

- **Şampiyon (`SAFE_HAVEN_ROTATION`):** SHY %100 (OOS CAGR `13.69%`, Sharpe `0.84`, MaxDD `-20.78%`, DSR `%58.9`)
- **Meta-Portföy A (`META_US_ETF_ALL_WEATHER`):** SHY %80 · IEF %7.9 · TLT %4.5 · SPY %3.1 · DBC %2.5 (OOS CAGR `3.89%`, Sharpe `0.52`, MaxDD `-11.67%`)
- **Meta-Portföy B (`META_GLOBAL_ETF_CRYPTO_TREND`):** SHY %64 · IEF %6.3 · TLT %3.6 · SPY %2.5 · DBC %2 · Nakit %20 (OOS CAGR `4.92%`, Sharpe `0.63`, MaxDD `-13.68%`)

## Turnuva Liderlik Tablosu (OOS Net)

| Strateji | Evren | Karar | OOS CAGR | OOS Sharpe | OOS MaxDD | Recovery | DSR (`N=25`) | Güncel Hedef |
| :--- | :---: | :---: | ---: | ---: | ---: | ---: | ---: | :--- |
| **Safe-Haven Altın & Tahvil Rotasyonu** | `us_etf` | `PASS_ELITE` | +13.7% | 0.84 | -20.8% | 4.17x | %58.9 | SHY %100 |
| **Kripto BTC-USD 200G SMA Trend** | `crypto` | `PASS_ELITE` | +24.8% | 0.83 | -32.2% | 6.05x | %48.1 | %100 Nakit (savunma/trend dışı) |
| **Nasdaq-100 (QQQ) 50/200G Çift Trend** | `us_etf` | `PASS_ELITE` | +9.1% | 0.73 | -17.3% | 3.02x | %53.4 | SHY %100 |
| **Kripto 5-SMA Trend Ensemble (BTC+ETH)** | `crypto` | `PASS_ELITE` | +17.8% | 0.68 | -30.6% | 4.02x | %35.4 | %100 Nakit (savunma/trend dışı) |
| **Vol-Target Multi-Asset Trend (%10 Hedef Vol)** | `us_etf` | `PASS_SOLID` | +5.8% | 1.00 | -6.9% | 4.59x | %72.9 | SHY %100 |
| **Meta-Portföy B (Küresel ETF + Kripto Trend)** | `meta` | `PASS_SOLID` | +4.9% | 0.63 | -13.7% | 2.96x | %42.4 | SHY %64 · IEF %6.3 · TLT %3.6 · SPY %2.5 · DBC %2 · Nakit %20 |
| **ABD Faktör ETF Rotasyonu (MTUM/QUAL/USMV/VLUE)** | `us_sectors` | `PASS_SOLID` | +8.8% | 0.61 | -24.0% | 2.12x | %41.4 | USMV %100 |
| **SPY RSI(2) Ortalamaya Dönüş** | `us_etf` | `PASS_SOLID` | +4.5% | 0.60 | -9.5% | 2.50x | %41.7 | SPY %100 |
| **Protective Asset Allocation (PAA Çöküş Kalkanı)** | `us_etf` | `PASS_SOLID` | +5.2% | 0.59 | -12.8% | 2.17x | %38.8 | SHY %100 |
| **S&P 500 (SPY) 200G SMA Zamanlama** | `us_etf` | `PASS_SOLID` | +6.2% | 0.58 | -22.6% | 1.51x | %40.0 | SHY %100 |
| **ABD Sektör Momentum Top-3 (Trend Filtreli)** | `us_sectors` | `PASS_SOLID` | +7.9% | 0.53 | -18.1% | 2.47x | %37.6 | XLV %33.3 · XLF %33.3 · XLE %33.3 |
| **Meta-Portföy A (ABD Ortogonal ETF Ensemble)** | `meta` | `PASS_SOLID` | +3.9% | 0.52 | -11.7% | 1.75x | %32.4 | SHY %80 · IEF %7.9 · TLT %4.5 · SPY %3.1 · DBC %2.5 |
| **Kripto BTC/ETH Dual Momentum (100G Trend)** | `crypto` | `PASS_SOLID` | +11.7% | 0.47 | -56.2% | 1.28x | %20.9 | %100 Nakit (savunma/trend dışı) |
| **All-Weather Risk Parity (Vol-Weighted)** | `us_etf` | `PASS_SOLID` | +3.6% | 0.47 | -18.4% | 1.03x | %28.9 | IEF %39.4 · TLT %22.5 · SPY %15.5 · DBC %12.7 · GLD %10 |
| **Faber GTAA-5 (200G Trend Takibi)** | `us_etf` | `PASS_SOLID` | +3.2% | 0.47 | -10.7% | 1.54x | %30.0 | SHY %100 |
| **Referans: Buy & Hold S&P 500 (SPY)** | `us_etf` | `BENCHMARK` | +10.1% | 0.64 | -24.5% | 2.44x | %45.0 | SPY %100 |
| **Referans: Klasik 60/40 (SPY/IEF)** | `us_etf` | `BENCHMARK` | +5.7% | 0.55 | -20.7% | 1.51x | %37.0 | SPY %60 · IEF %40 |
| **Referans: Kripto Al-Tut (50/50 BTC+ETH)** | `crypto` | `BENCHMARK` | -3.4% | 0.22 | -68.4% | -0.23x | %8.8 | BTC-USD %50 · ETH-USD %50 |
| **BIST 52H Zirve + Düşük-Vol Trend Top-5 (TL)** | `bist` | `CAVEAT_SURVIVORSHIP` | +60.4% | 1.64 | -26.8% | 33.21x | %98.3 | GARAN.IS %25 · PGSUS.IS %25 · THYAO.IS %25 · YKBNK.IS %25 |
| **BIST 6-1A Momentum Trend Top-5 (TL)** | `bist` | `CAVEAT_SURVIVORSHIP` | +50.6% | 1.39 | -29.1% | 21.59x | %94.4 | TUPRS.IS %100 |
| **Defensive Asset Allocation (DAA Kanarya)** | `us_etf` | `FAIL_WEAK` | +4.7% | 0.43 | -13.7% | 1.82x | %26.4 | BIL %100 |
| **Dual Momentum (Antonacci GEM)** | `us_etf` | `FAIL_WEAK` | +5.5% | 0.39 | -27.8% | 1.08x | %24.7 | VGK %100 |
| **Accelerated Dual Momentum (ADM)** | `us_etf` | `FAIL_WEAK` | +4.2% | 0.33 | -25.6% | 0.87x | %20.9 | SHY %100 |
| **Vigilant Asset Allocation (VAA Kanarya Kalkanı)** | `us_etf` | `FAIL_WEAK` | +1.6% | 0.19 | -15.6% | 0.52x | %12.2 | SHY %100 |
| **ABD Düşük Volatilite Sektör Top-4** | `us_sectors` | `FAIL_WEAK` | -1.5% | -0.03 | -25.2% | -0.28x | %5.7 | XLV %25 · XLP %25 · XLU %25 · XLY %25 |

> *Not: Tüm sonuçlar geriye dönük ampirik simülasyondur; BIST stratejileri hayatta kalma yanlılığı ve TL enflasyonu nedeniyle `CAVEAT_SURVIVORSHIP` etiketi taşır. Yatırım tavsiyesi değildir.*
