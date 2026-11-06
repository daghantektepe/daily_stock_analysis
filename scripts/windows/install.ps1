<#
.SYNOPSIS
  Install daily_stock_analysis (Borsa Istanbul + Turkish reports) on this PC.

.DESCRIPTION
  Clones (or updates) the repository into -Target, creates a Python 3.11
  virtual environment, installs the Python requirements and, unless -SkipCli,
  the Claude Code / Gemini / Codex CLIs. Creates .env from the Turkish template
  when it does not exist yet (an existing .env is never overwritten).

  Safe to run again: it only updates what is missing or out of date.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install.ps1 -Target E:\daily_stock_analysis
#>
param(
  [string]$Target = 'E:\daily_stock_analysis',
  [string]$Branch = 'claude/jolly-cray-fsps8k',
  [string]$RepoUrl = 'https://github.com/daghantektepe/daily_stock_analysis.git',
  [string]$PythonVersion = '3.11',
  [switch]$SkipCli
)

$ErrorActionPreference = 'Stop'

function Invoke-Checked {
  param([string]$Description, [scriptblock]$Command)
  Write-Host "==> $Description" -ForegroundColor Cyan
  & $Command
  if ($LASTEXITCODE -ne 0) { throw "$Description failed (exit code $LASTEXITCODE)" }
}

function Test-Tool {
  param([string]$Name, [string]$Hint)
  if (Get-Command $Name -ErrorAction SilentlyContinue) { return $true }
  Write-Host "[missing] $Name  ->  $Hint" -ForegroundColor Yellow
  return $false
}

# 1. Prerequisites -------------------------------------------------------
$ready = Test-Tool 'git' 'winget install --id Git.Git -e'
$ready = (Test-Tool 'py' "winget install --id Python.Python.$PythonVersion -e") -and $ready
if (-not $SkipCli) {
  $ready = (Test-Tool 'npm' 'winget install --id OpenJS.NodeJS.LTS -e') -and $ready
}
if (-not $ready) {
  Write-Host 'Install the missing tools, open a NEW PowerShell window and run this script again.'
  exit 1
}

$drive = Split-Path -Qualifier $Target
if (-not (Test-Path "$drive\")) { throw "Drive $drive was not found." }

# 2. Code ----------------------------------------------------------------
if (Test-Path (Join-Path $Target '.git')) {
  Invoke-Checked 'git fetch' { git -C $Target fetch origin $Branch }
  Invoke-Checked "git checkout $Branch" { git -C $Target checkout $Branch }
  Invoke-Checked 'git pull' { git -C $Target pull --ff-only origin $Branch }
} else {
  Invoke-Checked "git clone into $Target" { git clone --branch $Branch $RepoUrl $Target }
}
Set-Location $Target

# 3. Python environment --------------------------------------------------
Invoke-Checked "Python $PythonVersion check" { py "-$PythonVersion" --version }
if (-not (Test-Path '.venv\Scripts\python.exe')) {
  Invoke-Checked 'create .venv' { py "-$PythonVersion" -m venv .venv }
}
$python = Join-Path $Target '.venv\Scripts\python.exe'
Invoke-Checked 'upgrade pip' { & $python -m pip install --upgrade pip }
Invoke-Checked 'install requirements' { & $python -m pip install -r requirements.txt }

# 4. Subscription CLIs ---------------------------------------------------
if (-not $SkipCli) {
  Invoke-Checked 'install Claude / Gemini / Codex CLIs' {
    npm install -g '@anthropic-ai/claude-code' '@google/gemini-cli' '@openai/codex'
  }
}

# 5. Configuration -------------------------------------------------------
if (-not (Test-Path '.env')) {
  Copy-Item 'scripts\windows\env.tr.template' '.env'
  Write-Host 'Created .env from scripts\windows\env.tr.template - edit STOCK_LIST and Telegram settings.' -ForegroundColor Green
} else {
  Write-Host '.env already exists; left unchanged.'
}
New-Item -ItemType Directory -Force -Path 'data', 'logs', 'reports' | Out-Null

Write-Host ''
Write-Host 'Done. Next steps (see docs\turkey-personal-setup.md):' -ForegroundColor Green
Write-Host '  1. Log in once:  claude   (/login, then /exit)'
Write-Host '                   gemini   (Login with Google, then /quit)'
Write-Host '                   codex login'
Write-Host '  2. Edit .env (notepad .env): STOCK_LIST, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID'
Write-Host '  3. Check models:  .venv\Scripts\python.exe scripts\check_env.py --backends'
Write-Host '  4. Start:         powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1'
