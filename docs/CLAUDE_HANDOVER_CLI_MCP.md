# Claude Handover — CLI-Native Copilot & DSA MCP Bridge

> **Prepared:** 2026-11-20 (base commit `0975548` / `claude/jolly-cray-fsps8k`)  
> **Scope:** CLI-Native Copilot + DSA MCP Bridge (15 tools) + `src/quant/` 25-Strategy Empirical Tournament + Recharts UI  
> **Status:** Implemented and verified end-to-end (unit tests, live MCP stdio, live Claude CLI strategic brief, live SEC Form 4 / KAP tools, ESLint, Vitest, production Vite build).

---

## 1. Executive Summary & Goal

The user requested a **direct, program-connected Chatbox** and a **CLI-native bridge** so that asking natural-language strategic questions such as:
> *"Para kazandırma ihtimali yüksek, şu an en güvenli stratejik trading önerini istiyorum"*

directly invokes local **Claude Code CLI** or **Gemini CLI**, which in turn calls the program's live quantitative screeners, market regime/risk gates, crypto trend strategy, SEC Form 4, PEAD, KAP alerts, and simulated paper portfolio via a standard **Model Context Protocol (MCP)** server (`src.mcp.server`).

All new components were built **modularly** (mostly standalone new files under `src/mcp/`, `src/quant/`, `apps/dsa-web/src/components/chat/`, and `apps/dsa-web/src/components/quant/`, plus minimal surgical edits) so they merge cleanly across machines and branches.

---

## 2. Exact File Inventory

### A. New Standalone Files (Copy/Transplant Directly — Zero Conflict with `v0.3`)

| File | Purpose |
| :--- | :--- |
| `src/mcp/__init__.py` | Package exports (lazy `__getattr__` for `server` so `python -m src.mcp.server` emits zero `runpy` warnings) |
| `src/mcp/server.py` | Zero-dependency pure-Python MCP stdio JSON-RPC 2.0 server (`dsa-quant-mcp`); supports both newline-delimited JSON-RPC and `Content-Length` framing; redirects stray tool `stdout` prints to `stderr` |
| `src/mcp/tools.py` | **15 live MCP tools** (all lazy-importing DSA services for `<150ms` boot) — includes `dsa_get_strategic_trading_brief`, `dsa_get_strategy_tournament`, and `dsa_get_paa_allocation` wired directly to `src/quant/` |
| `src/quant/` (`stats.py`, `data_loader.py`, `strategies/engine.py`, `strategies/library.py`, `portfolio.py`, `tournament.py`) + `scripts/run_strategy_tournament.py` | 25-strategy multi-universe zero-lookahead empirical tournament (US ETF / US Sectors / Crypto / BIST + PAA Crash-Shield + Meta-Portfolios A/B, cost-adjusted net returns, OOS 2022–present, DSR `N=25`, report generator) |
| `apps/dsa-web/src/components/quant/` (`StrategyEquityChart.tsx`, `TournamentLeaderboard.tsx`, `TournamentTabPanel.tsx`) | Recharts interactive equity curve comparison, universe/verdict filterable tournament leaderboard, and live PAA crash-shield cockpit wired into `/discover` (`🏆 Strateji Turnuvası & PAA`) |
| `tests/test_quant_tournament.py` | 7 quant engine invariant tests (zero lookahead perturbation test, transaction cost deduction, DSR monotonicity, PAA crash-shield defensive shift, 25-strategy offline run, BIST survivorship verdict, MCP tool exposure) |
| `src/mcp/config_gen.py` | Portable Python resolver (`DSA_MCP_PYTHON` → healthy `.venv` → `~/.dsa-venv` → `sys.executable`) + `.mcp.json` & `.gemini/settings.json` generator/merger |
| `src/agent/cli_bridge_common.py` | Cross-platform CLI resolver (prefers `.cmd`/`.exe` over `.ps1` on Windows), `<1ms` npm-shim version probe, Windows/POSIX process-tree reclamation, strategic trading MCP system prompt, and Turkish/English MCP tool display names |
| `src/agent/claude_cli_backend.py` | `ClaudeCliAgentBackend(AgentBackend)`: spawns `claude -p --output-format stream-json --verbose --mcp-config <tmp> --strict-mcp-config --tools "" --allowedTools mcp__dsa__* --permission-mode dontAsk --no-session-persistence --append-system-prompt ...`, streams `tool_start`/`tool_done`/`thinking`/`generating` SSE events |
| `src/agent/gemini_cli_backend.py` | `GeminiCliAgentBackend(AgentBackend)`: spawns `gemini -p ... --output-format stream-json --approval-mode yolo --allowed-mcp-server-names dsa --skip-trust` in an isolated temp workspace with `.gemini/settings.json` |
| `scripts/dsa_cli.py` | Terminal CLI-native launcher: `status`, `install-mcp`, `claude`, `gemini`, `ask`, `chat`, `mcp-serve`, `serve` |
| `dsa.cmd` | Windows batch wrapper in repo root (`.\dsa.cmd claude`, `.\dsa.cmd ask "..."`, `.\dsa.cmd status`, etc.) |
| `apps/dsa-web/src/components/chat/BackendSwitcher.tsx` | Reusable one-click engine switcher pills (`Claude CLI · MCP`, `Gemini CLI · MCP`, `LiteLLM API`) + live refresh button |
| `apps/dsa-web/src/components/chat/CopilotDrawer.tsx` | Global slide-over Copilot Chatbox mounted in `Shell.tsx` (`Ctrl+J` from any page, floating launcher pill, live MCP tool timeline, active page context, 4 strategic trading quick-prompt cards, Markdown/GFM rendering, Stop/New Chat/Fullscreen controls) |
| `apps/dsa-web/src/components/chat/copilotEvents.ts` | Separated event constant + `openCopilotDrawer()` helper (satisfies `react-refresh/only-export-components`) |
| `tests/test_mcp_and_cli_backends.py` | 12 unit + protocol + real MCP stdio subprocess tests (all 12 passing) |
| `docs/cli-native-mcp-bridge.md` | Full architecture, Web UI, CLI, env config, and safety guide |

### B. Modified Existing Files (Surgical Edits — Merge Carefully with `v0.3`)

| File | What Changed | Merge Note for `v0.3` (`636ba16`) |
| :--- | :--- | :--- |
| `src/agent/agent_backend.py` | Added `"claude_cli"`, `"gemini_cli"` to `AGENT_BACKEND_IDS`; made `LLMToolAdapter` & `run_agent_loop` lazy inside `LiteLLMAgentBackend` | `v0.2` already made `litellm` lazy here — keep `v0.2` lazy imports + add `"claude_cli"`, `"gemini_cli"` to `AGENT_BACKEND_IDS` |
| `src/agent/chat_executor.py` | Changed `strict_initial_stock_scope=self.backend.runtime_owns_loop` → `self.backend.backend_id == "codex_app_server"` so CLI MCP backends work without requiring a stock code | Clean 1-line edit |
| `src/agent/factory.py` | Added optional `backend_override` & `page_route` kwargs to `build_agent_chat_executor(...)` and wired `ClaudeCliAgentBackend` / `GeminiCliAgentBackend` | Clean merge |
| `src/config.py` | Added `"claude_cli"`, `"gemini_cli"` to `SUPPORTED_AGENT_BACKENDS`; added optional `claude_cli_model` (`DSA_CLAUDE_CLI_MODEL`) and `gemini_cli_model` (`DSA_GEMINI_CLI_MODEL`) | Clean merge |
| `src/services/generation_backend_status_service.py` | Deferred `from src.analyzer import GeminiAnalyzer` into default factory (matches `v0.2` lazy `litellm` speedup) | Already lazy in `v0.2` |
| `src/services/market_light_service.py` | Inlined `MARKET_REVIEW_HISTORY_CODE` / `MARKET_REVIEW_REPORT_TYPE` constants and deferred `MarketAnalyzer` import inside `build_current_snapshot` (matches `v0.2` lazy speedup) | Already lazy in `v0.2` |
| `src/services/agent_backend_status_service.py` | Updated `evaluate_agent_backend_config` + `get_status` for `claude_cli`/`gemini_cli`; added `list_backends()` for `/api/v1/agent/backends` | Clean merge |
| `api/v1/endpoints/agent.py` | Added `GET /api/v1/agent/backends`, optional `ChatRequest.backend`, merged `MCP_TOOL_DISPLAY_NAMES` into `TOOL_DISPLAY_NAMES`, enabled server-side stream cancellation for `claude_cli`/`gemini_cli`, preserved 2-arg `_build_executor(config, skills)` call when no override/route is set | Clean merge |
| `apps/dsa-web/src/api/agent.ts` | Added `AgentBackendId`, `AgentBackendOption`, `AgentBackendsResponse`, optional `backend` on `ChatRequest`, and `agentApi.getBackends()` | Clean merge |
| `apps/dsa-web/src/stores/agentChatStore.ts` | Added `selectedBackend`, `backends`, `recommendedBackend`, `copilotOpen`, `copilotPrefill`, `loadBackends()`, accepted `claude_cli`/`gemini_cli` in SSE `accepted` event and `serverCancellation` | Clean merge |
| `apps/dsa-web/src/components/layout/Shell.tsx` | Mounted `<CopilotDrawer />` alongside `<CommandPalette />` | 2-line addition |
| `apps/dsa-web/src/components/layout/LiveStatusBar.tsx` | Added `AI Copilot · Ctrl+J` trigger button (uses `aria-label`, no native `title=` per `tests/ui_governance.test.ts`) | Clean merge |
| `apps/dsa-web/src/pages/ChatPage.tsx` | Added `<BackendSwitcher compact />`, `cliBackendSelected` availability override, `Claude CLI · MCP` / `Gemini CLI · MCP` message badges, and Stop button enablement | Clean merge |
| `.env.example` | Documented `claude_cli`/`gemini_cli` for `AGENT_BACKEND` and optional `DSA_CLAUDE_CLI_*` / `DSA_GEMINI_CLI_*` / `DSA_MCP_PYTHON` overrides | Clean merge |
| `.gitignore` | Ignored locally generated `/.mcp.json` and `/.gemini/` | Clean merge |
| `docs/CHANGELOG.md`, `docs/INDEX.md`, `docs/INDEX_EN.md` | Added flat `[Unreleased]` entry and doc index links | Clean merge |

### C. Pre-Existing Dirty Files on `F:\` (NOT Part of This CLI-MCP Task)

These 4 files were **already modified** on `F:\daily_stock_analysis` prior to this session (from an earlier *"Claude Doğrulama & Kripto Trend"* session on `0975548`). **Do NOT blindly overwrite `v0.3`'s versions of these 4 files** — compare them against `v0.3-strategy-tournament` first:
- `api/v1/endpoints/alpha.py`
- `api/v1/schemas/alpha.py`
- `apps/dsa-web/src/api/alpha.ts`
- `apps/dsa-web/src/pages/AlphaDiscoveryPage.tsx`

*(Also `static/` was rebuilt by `npm run build`, and gitignored `.mcp.json` / `.gemini/settings.json` were generated locally for the work PC.)*

---

## 3. Immediate Integration Tasks for Claude on Personal Laptop (`v0.3` → `v0.4`)

When continuing on another machine (e.g., personal laptop with local Python 3.11 `.venv`):

1. **Sync / Re-bind Local MCP Configs:**
   - Pull or merge this feature branch cleanly.
   - Run `python scripts/dsa_cli.py install-mcp` on the target machine so gitignored `.mcp.json` and `.gemini/settings.json` point to that machine's local Python `.venv`.

2. **Optional Next Roadmap Items (`v0.4` → `v0.5`):**
   - Continue unifying `AlphaDiscoveryPage.tsx` with `UnifiedPortfolioCockpit.tsx` / `CatalystAndBistPanel.tsx` and wire direct `openCopilotDrawer("...")` buttons onto individual screener/tournament rows.
   - Optionally connect the live PAA / Meta-Portfolio A target weights (`data/strategy_paper/quant_champion.json`) directly into automated daily paper-portfolio rebalancing.
   - Re-verify live `Gemini CLI` turn once Google's upstream 503 capacity spike subsides (handshake, config generation, 503 diagnostics, and `stream-json` parser tests are already passing).

---

## 4. Verification Summary

- **Quant & MCP Pytest Suites (`tests/test_quant_tournament.py` + `tests/test_mcp_and_cli_backends.py`):** **19/19 PASSED** (`7/7` quant invariants including zero-lookahead perturbation, transaction cost deduction, DSR monotonicity, PAA crash-shield defensive shift, 25-strategy offline execution, BIST survivorship caveat + `12/12` MCP stdio JSON-RPC & CLI backend tests).
- **Backend Agent Regression Suite:** `test_agent_backend.py` (**19/19**), `test_agent_chat_api.py` (**37/37**), `test_agent_chat_executor.py` (**8/8**), `test_agent_models_api.py` (**18/18**), and Windows-compatible `test_agent_backend_status_service.py` (**5/5**) = **106/106 PASSED**.
- **Live Empirical Tournament (`scripts/run_strategy_tournament.py`):** Executed across **25 strategies · 52 assets · 152,282 asset-days** (OOS `2022-01-01 → 2026-11-20`), emitting `data/quant_cache/tournament_latest.json`, `data/strategy_paper/quant_champion.json`, and `docs/STRATEGY_TOURNAMENT_REPORT.md`.
- **Live End-to-End Claude CLI ↔ DSA MCP:** Verified both via `scripts/dsa_cli.py ask --engine claude` and via live FastAPI SSE `POST /api/v1/agent/chat/stream` (`backend: "claude_cli"`). Also verified live `dsa_scan_sec_form4_live` and `dsa_scan_kap_contracts`.
- **Gemini CLI Status:** Installed binary (`0.65.0`), `.gemini/settings.json` config, `stream-json` parser, and `init` handshake verified; live generation encountered temporary upstream Google HTTP 503 (`high demand`), which is now caught cleanly with actionable diagnostics in `GeminiCliAgentBackend`.
- **Frontend Verification:** ESLint **0 errors** across all new/modified chat and quant UI files; Vitest `ui_governance.test.ts` + `agentChatStore.test.ts` + chat/shell suites passing; production `tsc -b && vite build` clean.
