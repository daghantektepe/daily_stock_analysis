# Claude Code Handover — Daily Stock Analysis (`v0.6.0-research-v3`)

> **Date:** 2026-11-22  
> **Active Workspace:** `E:\daily_stock_analysis` (Windows 11, PowerShell, Python 3.11.9 `.venv`)  
> **Git Branch:** `feat/cli-mcp-quant-tournament`  
> **Latest Release Tag:** `v0.6.0-research-v3` (pushed to `origin` and fast-forwarded to `C:\Users\dagha\.gemini\antigravity\scratch\daily_stock_analysis`)  
> **Pre-Audit Rollback Anchor:** `backup/pre-phase1-qa-fixes` (`7927dde`)  
> **User Language:** **Turkish** for all responses, reports, and UI copy; **English** for git commit messages (per `CLAUDE.md` / `AGENTS.md`).

---

## 1. Non-Negotiable Safety & Engineering Guardrails

1. **Simulated / Paper Trading Double-Locks (NEVER violate):**
   - `.env` keeps `ALPACA_PAPER=true` and `ALPACA_AUTO_EXECUTE=false`; `ALPACA_LIVE_TRADING_CONFIRMED` is never enabled.
   - Never submit real-money broker orders or allow the daily scheduler to place Alpaca orders.
2. **Frozen Strategy Isolation (CRITICAL for Forward Validation):**
   - `PAA v2` (`87e22a6b3559`), `Meta-Portfolio A v2` (`37a7ab36a0d9`), and `v3_trp` (`ae4754108564`) are **frozen** at `2026-11-20` in `data/strategy_paper/forward_validation.json`.
   - **NEVER** alter `compute_paa_weights`, `compute_meta_a_weights`, `compute_v3_trend_risk_parity_bil_weights`, or any helper/constant they call unless intentionally restarting a 120-day forward test (`freeze --reset`).
   - Any new experimental strategy research MUST live in an isolated module and never import/modify `library.py` or `research_v3.py`.
3. **Empirical Honesty:**
   - Always evaluate USD strategies **net of transaction costs (5–50 bps)** and **against risk-free T-Bills (`BIL`)** using `Excess CAGR` and `Excess Sharpe`.
   - Note that the `2022–2026` tournament window was used while tuning `PAA v2` / `Meta-A v2`, so true out-of-sample evidence for those two comes from the `forward_validation.json` forward clock started on `2026-11-20`.
   - BIST strategies are evaluated in **USD via `TRY=X`** against `BIL` (`CAVEAT_SURVIVORSHIP` applies due to current-constituent universe).
4. **PyInstaller & Windows Runtime Pitfalls:**
   - Always use `.\.venv\Scripts\python.exe` (never bare system `python`) on `E:\daily_stock_analysis`.
   - Always set `$env:LITELLM_LOCAL_MODEL_COST_MAP = "True"` before building or launching `DailyStockAnalysis.exe`.
   - Remember Windows PowerShell 5.1 does not support `&&` — run commands on separate lines or `; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }`.

---

## 2. Current Verified System State (`v0.6.0-research-v3`)

### Git Tag Progression
| Tag | Scope |
|---|---|
| `v0.5.1-p0-integrity` | **Phase 1 (P0):** Non-destructive CSV cache merging, `_LITELLM_IMPORT_LOCK` deadlock fix, true `BIL` Excess Sharpe + `min_oos_days=750`, AI Council 1200-char word-boundary trim. |
| `v0.5.2-alpha-v2` | **Phase 2 (P1):** Alpha v2 (`PAA v2`, `QQQ Dual-SMA Hysteresis`, `Safe-Haven + BIL`, `Meta-Portfolio A v2`) + BIST KAP non-equity SPV filter & 30d delisted cache. |
| `v0.5.3-speed-stability` | **Phase 3 (P2):** Batched US/BIST screeners, PEAD 14s budget, 20-min disk TTL cache, compact `7.8 KB` MCP brief, SearXNG 15-min cooldown, ASCII startup logs. |
| `v0.5.4-verified-release` | **Phase 4 (P3):** Zero ESLint errors, 12 core Vitest suites green, 8 QA regression guards, `.exe` live audit (`30/30 HTTP 200`, `16 MCP tools`). |
| `f49270b` *(Claude 5A+5B)* | **Phase 5A & 5B:** Forward Validation Gate (`src/quant/forward_validation.py`, `scripts/quant_forward.py`, `GET /api/v1/alpha/forward-validation`, `dsa_get_forward_validation`, WebUI Forward Gate Card); BIST USD deflation (`src/quant/bist_usd.py`, `TRY=X`), AI Council v2 25bps+2022 robustness gate, `ExBIL` Sharpe across UI & MCP (**17 MCP tools** total). |
| `v0.6.0-research-v3` | **Phase 5D (Priority D):** 19-year (`2008–2026`, 4 macro eras) pre-registered Strategy Research v3 lab (`research_v3.py`, `research_lab.py`, `scripts/run_strategy_research_v3.py`); standout winner **`V3_TREND_RISK_PARITY_BIL` (`v3_trp`)** independently frozen (`ae4754108564`), **112/112** quant/alpha/MCP/research pytest passing, `DailyStockAnalysis.exe` rebuilt (`DESKTOP_EXE_SMOKE_OK`, `17 MCP tools`). |

### Live Empirical Results (`2026-11-22`, Verified on `E:` `.venv`)
1. **19-Year Pre-Registered Strategy Research v3 (`2008–2026`, 4 Macro Eras, Net of Costs, vs `BIL`):**
   - **`V3_TREND_RISK_PARITY_BIL` (`v3_trp`) — PROMOTED (`5/5` gates) & Independently Frozen:**
     - **4/4 eras positive ExBIL** (`2008–12 GFC: +2.41% / +0.47`, `2013–19 QE: +1.66% / +0.57`, `2020–21 COVID: +5.79% / +1.27`, `2022–26 Rates: +2.26% / +0.67`).
     - Cost stress: `5 bps` ExSh **`+0.63`**, `25 bps` ExSh **`+0.47`** (ExCAGR `+1.82%`), `50 bps` ExSh **`+0.26`**.
     - Crisis shield: `2008 GFC MaxDD` **`-3.83%`** (vs SPY `-51.9%`), `2022` **`+3.59%`** (vs SPY `-18.18%`), overall `MaxDD` **`-7.3%`**.
     - Parameter plateau (`±20%`): **`9/9` (`100%`)** neighbors pass.
     - Orthogonality vs `Meta-A v2`: daily corr **`0.612`**; **unoptimized 50/50 blend lifts `Meta-A v2` ExBIL Sharpe `+0.83 → +0.91` and cuts MaxDD `-8.3% → -5.4%`**.
     - Live signal: `BIL 83.3% · UUP 16.7%`.
   - `V3_TSMOM_CROSS_ASSET` — **REJECTED (`4/5` gates)**: strong standalone (`+0.62` ExSh, 4/4 eras), failed Gate 5 (`corr=0.756 >= 0.70`, 50/50 blend did not improve Meta-A).
   - `V3_SECTOR_FACTOR_BREADTH_BIL` — Secondary `5/5` technical pass **not enrolled** due to negative `2022–26` era (`-2.24%` ExBIL) and diluting `Meta-A v2` in 50/50 blend (`0.59 vs 0.83`).
2. **Real AI Council v2 Re-Evaluation on `E:` (`ai_council_charters.json`):**
   - **Google Gemini CLI (`paa_custom`, `pf=1.0`):** **✅ PASS (`PASS_ELITE`)** — OOS 2022+ `CAGR +8.4%`, `ExBIL +4.5%`, `ExSh +0.42` (`25 bps +0.31`, `50 bps +0.16`), `2022 +0.6%` vs `SPY -18.2%`.
   - Claude Code CLI (`vol_target %8`): `FAIL` (`ExSh -0.05` @5bps, `-0.21` @25bps).
   - OpenAI Codex CLI (`vol_target %10`): `FAIL` (`ExSh -0.14` @5bps, `-0.27` @25bps).
3. **BIST USD-Deflated Tournament Results (`2022–2026`, `USD/TRY 13.36 → 50.56`):**
   - `XU100.IS`: `+43.7%` TRY → `+9.8%` USD (`ExBIL Sharpe +0.17`, `2025 -5.8%`, `2026 -16.0%`).
   - `BIST_52W_HIGH_LOWVOL_TOP5`: `+60.3%` TRY → `+22.6%` USD (`+0.51`, `CAVEAT_SURVIVORSHIP`, negative in USD 2025–2026).
   - `BIST_MOMENTUM_TOP5`: `+50.5%` TRY → `+15.4%` USD (`+0.33`, `CAVEAT_SURVIVORSHIP`, `+2.1%` / `-1.2%`).
4. **Frozen Forward Validation Fingerprints (`2026-11-20` baseline):**
   - `paa`: `87e22a6b3559` · `meta_a`: `37a7ab36a0d9` · `v3_trp`: `ae4754108564` (all `COLLECTING` cleanly).

---

## 3. Recommended Next Development Priorities (`v0.6.0` → `v0.7.x`)

1. **Priority C — Frontend Quality & Remaining Legacy Upstream Tests:**
   - Fix nested `<button>` hydration warning in `apps/dsa-web/src/components/history/StockBarItem.tsx`.
   - Migrate remaining **42 legacy upstream Chinese Vitest suites** to TR/i18n assertions (also clean up pre-existing `test_system_config_service` failures noted in full backend suite).
   - Wire 1-click `openCopilotDrawer("...")` buttons onto tournament/screener candidate rows and expose `v3_trp` in the WebUI Paper/Forward cards (or via `QUANT_PAPER_STRATEGIES=paa,meta_a,v3_trp`).
2. **Priority A2 — Forward Operations & Alpaca Paper Slippage Loop:**
   - Optional inclusion of `v3_trp` in `daily_paper_step.ps1` / `QUANT_PAPER_STRATEGIES` once desired by the user.
   - Run manual `quant_forward.py alpaca-plan` / `alpaca-submit-paper` / `alpaca-reconcile` on monthly rebalance dates after Alpaca Paper keys are configured in `.env`.
3. **Optional Event-Driven SMID Lab (`V3_EVENT_CATALYST_PEAD_FORM4`):**
   - Walk-forward constrained-capital portfolio simulator (`max 10 slots`, `T+1`, `25–50 bps` slippage, idle cash in `BIL`) combining PEAD 2.0 + Form 4 opportunistic clusters.

---

## 4. Quick Verification Commands (PowerShell on `E:\daily_stock_analysis`)

```powershell
# Quant / Research v3 / Forward Gate / BIST USD / MCP Suite (112 tests)
Set-Location E:\daily_stock_analysis
.\.venv\Scripts\python.exe -m pytest `
  tests\test_strategy_research_v3.py tests\test_forward_validation.py `
  tests\test_bist_usd_and_council_v2.py tests\test_qa_regression_guards.py `
  tests\test_quant_tournament.py tests\test_quant_paper_book.py `
  tests\test_mcp_and_cli_backends.py tests\test_us_quant_screener.py `
  tests\test_pead_screener.py tests\test_bist_screener.py `
  tests\test_paper_trading.py tests\test_crypto_trend.py `
  tests\test_sec_form4.py tests\test_kap_watch.py -q

# Re-run 19-year Strategy Research v3 Lab
.\.venv\Scripts\python.exe scripts\run_strategy_research_v3.py

# Check Frozen Forward Validation Gate (all 3 frozen books)
.\.venv\Scripts\python.exe scripts\quant_forward.py status --strategy paa,meta_a,v3_trp

# Rebuild & Launch Desktop .exe
$env:LITELLM_LOCAL_MODEL_COST_MAP = "True"
powershell -ExecutionPolicy Bypass -File scripts\windows\build_desktop_exe.ps1
Start-Process -FilePath "E:\daily_stock_analysis\dist\DailyStockAnalysis\DailyStockAnalysis.exe" -WorkingDirectory "E:\daily_stock_analysis"
```
