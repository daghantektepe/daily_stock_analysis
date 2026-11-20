# CLI-Native Copilot & DSA MCP Server Bridge

This guide explains how **Daily Stock Analysis (DSA)** connects directly to your local **Claude Code CLI** and **Gemini CLI** through a built-in, zero-dependency **Model Context Protocol (MCP)** server (`src.mcp.server`) — both inside the Web UI chatbox and natively from your terminal.

---

## Architecture Overview

```
Web UI (Global Copilot Drawer Ctrl+J / Fullscreen /chat)
    │  POST /api/v1/agent/chat/stream  (backend: claude_cli | gemini_cli | litellm)
    ▼
FastAPI Agent Endpoint (api/v1/endpoints/agent.py)
    │
    ├── ClaudeCliAgentBackend  ──▶ claude -p --output-format stream-json --mcp-config <tmp>
    ├── GeminiCliAgentBackend  ──▶ gemini -p ... --output-format stream-json (--allowed-mcp-server-names dsa)
    └── LiteLLMAgentBackend    ──▶ Configured API key path (default when AGENT_BACKEND=auto)
             │
             ▼  MCP stdio JSON-RPC 2.0
    DSA MCP Server (python -m src.mcp.server · server name: "dsa")
             │
             ├── dsa_get_strategic_trading_brief  (SPY/VIX regime + Crypto 5-SMA + Paper + optional scans)
             ├── dsa_get_market_regime            (SPY SMA50/200 + VIX + portfolio drawdown)
             ├── dsa_get_crypto_trend_signal      (BTC-USD / ETH-USD 5-SMA ensemble & paper book)
             ├── dsa_screen_us_alpha              (US Residual Momentum + 52W High + FIP + Profitability)
             ├── dsa_screen_bist_stocks           (BIST technical breakouts + volume + KAP catalysts)
             ├── dsa_scan_sec_form4_live          (Live SEC EDGAR Form 4 executive insider buying clusters)
             ├── dsa_scan_pead_candidates         (US Post-Earnings Announcement Drift 2.0)
             ├── dsa_scan_kap_contracts           (BIST KAP new contract/tender disclosures & alerts)
             ├── dsa_get_paper_portfolio          (Simulated paper ledger, open positions & benchmarks)
             ├── dsa_place_paper_order            (Simulated paper order entry; never real broker orders)
             ├── dsa_analyze_stock                (Live quote, trend, MAs, fundamentals & entry risk gate)
             ├── dsa_get_decision_signals         (Recent persisted AI decision signals)
             ├── dsa_get_strategy_tournament      (25-strategy multi-universe OOS tournament + DSR leaderboard)
             ├── dsa_get_paa_allocation           (Live Protective Asset Allocation crash-shield target weights)
             ├── dsa_get_quant_paper_books        (Daily PAA & Meta-Portfolio A StrategyPaperBook ledgers)
             └── dsa_get_system_overview          (Live cockpit health & counts)
```

---

## 1. Web UI Direct Chatbox (Global Copilot Drawer)

- Press **`Ctrl+J`** (or click **`AI Copilot`** in the top status bar or bottom-right floating launcher) from **any page** in the Web UI.
- Switch engines in one click between **`Claude CLI (MCP)`**, **`Gemini CLI (MCP)`**, and **`LiteLLM API`** via the engine switcher pills (available in both the Global Copilot Drawer and `/chat`).
- The active page route (e.g., `/discover`, `/paper-trading`, `/portfolio`) is forwarded as context.
- Every live MCP tool invocation is streamed in real time into the collapsible **Canlı MCP Araç Akışı** timeline with duration and status.

## 2. Terminal CLI-Native Usage (`dsa.cmd` / `scripts/dsa_cli.py`)

Run directly from the repository root:

```powershell
# Check Claude CLI, Gemini CLI, Python, MCP server, and Web UI status
.\dsa.cmd status

# Generate/update local .mcp.json (Claude Code) and .gemini/settings.json (Gemini CLI)
.\dsa.cmd install-mcp

# Launch native interactive Claude Code CLI pre-wired to all 16 DSA MCP tools
.\dsa.cmd claude

# Launch native interactive Gemini CLI pre-wired to all 16 DSA MCP tools
.\dsa.cmd gemini

# One-shot strategic trading recommendation via Claude CLI + MCP
.\dsa.cmd ask "Para kazandırma ihtimali yüksek şu an en güvenli stratejik trading önerini istiyorum" --engine claude

# Interactive multi-turn terminal chatbox (supports /strategy, /switch claude|gemini, /new, /status)
.\dsa.cmd chat --engine claude

# Start the stdio MCP server directly (used by MCP clients)
.\dsa.cmd mcp-serve

# Start the Web UI + FastAPI server
.\dsa.cmd serve --port 8000
```

## 3. Environment Configuration (Optional)

Everything works with **zero configuration** when `claude` or `gemini` CLI is installed and signed in on your machine. Optional `.env` overrides:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `AGENT_BACKEND` | Default Chat backend (`auto`, `litellm`, `claude_cli`, `gemini_cli`, `codex_app_server`) | `auto` (`litellm`) |
| `DSA_CLAUDE_CLI_MODEL` | Optional `--model` override passed to Claude CLI | CLI default |
| `DSA_GEMINI_CLI_MODEL` | Optional `-m` override passed to Gemini CLI | CLI default |
| `DSA_CLAUDE_CLI_PATH` | Explicit path to `claude` / `claude.cmd` binary | Auto-detected on `PATH` |
| `DSA_GEMINI_CLI_PATH` | Explicit path to `gemini` / `gemini.cmd` binary | Auto-detected on `PATH` |
| `DSA_MCP_PYTHON` | Explicit Python interpreter for spawning `src.mcp.server` | Auto-detected (`.venv`, `~/.dsa-venv`, or current Python) |

## 4. Safety Guardrails

- Claude CLI runs with `--tools ""`, `--strict-mcp-config`, `--allowedTools "mcp__dsa__*"`, and `--permission-mode dontAsk`, confining it strictly to DSA MCP tools (no shell execution or file editing during chat).
- Gemini CLI runs in an isolated temporary workspace with `--allowed-mcp-server-names dsa`.
- All paper trading tools operate strictly on the simulated virtual ledger and never send real broker orders.
