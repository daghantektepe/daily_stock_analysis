<#
.SYNOPSIS
  Build a standalone native Windows Desktop Application (.exe) for Daily Stock Analysis.

.DESCRIPTION
  Compiles desktop_app.py + embedded FastAPI + React UI (static/) + 25-strategy
  quant engine + PAA/Meta-A/3-AI Council StrategyPaperBook + 16-tool MCP server
  into a double-clickable Windows desktop executable:

      dist\DailyStockAnalysis\DailyStockAnalysis.exe

  Uses Windows' built-in Microsoft Edge WebView2 (via pywebview) — no Electron
  overhead, no Developer Mode required, no admin privileges required.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\build_desktop_exe.ps1
  powershell -ExecutionPolicy Bypass -File scripts\windows\build_desktop_exe.ps1 -RebuildWeb
#>
param(
  [switch]$RebuildWeb,
  [switch]$SkipSmokeTest,
  [string]$PythonBin = ''
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

function Resolve-DsaPython {
  $candidates = @()
  if ($PythonBin) { $candidates += $PythonBin }
  if ($env:PYTHON_BIN) { $candidates += $env:PYTHON_BIN }
  if ($env:DSA_MCP_PYTHON) { $candidates += $env:DSA_MCP_PYTHON }
  $candidates += (Join-Path $root '.venv\Scripts\python.exe')
  $candidates += (Join-Path $HOME '.dsa-venv\Scripts\python.exe')
  $pyCmd = Get-Command python -ErrorAction SilentlyContinue
  if ($pyCmd) { $candidates += $pyCmd.Source }

  foreach ($cand in $candidates) {
    if ($cand -and (Test-Path $cand)) {
      try {
        & $cand -c "import fastapi, uvicorn, webview, PyInstaller" 2>$null
        if ($LASTEXITCODE -eq 0) { return $cand }
      } catch {}
    }
  }
  throw "No Python environment with fastapi, uvicorn, pywebview, and pyinstaller found. Install with: pip install pyinstaller pywebview"
}

Push-Location $root
try {
  $python = Resolve-DsaPython
  Write-Host "=== Daily Stock Analysis Native Desktop .exe Build ==="
  Write-Host "Repo Root : $root"
  Write-Host "Python    : $python"

  # 1. Ensure compiled React static/ bundle exists
  if ($RebuildWeb -or -not (Test-Path 'static\index.html')) {
    Write-Host 'Building React UI (apps\dsa-web -> static\)...'
    Push-Location 'apps\dsa-web'
    try {
      if (-not (Test-Path 'node_modules')) { npm.cmd install }
      npm.cmd run build
      if ($LASTEXITCODE -ne 0) { throw "Frontend build failed with exit code $LASTEXITCODE" }
    } finally {
      Pop-Location
    }
  } else {
    Write-Host 'Using existing compiled static\ bundle (pass -RebuildWeb to recompile).'
  }

  & $python 'scripts\check_static_assets.py' 'static'
  if ($LASTEXITCODE -ne 0) { throw 'Static asset consistency check failed.' }

  # 2. Generate crisp multi-resolution Windows .ico icon
  $iconPath = Join-Path $root 'assets\dsa-desktop.ico'
  & $python 'scripts\windows\generate_icon.py' $iconPath
  if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }

  # 3. Stop any previously running DailyStockAnalysis.exe
  Get-Process -Name 'DailyStockAnalysis' -ErrorAction SilentlyContinue | Stop-Process -Force

  # 4. Run PyInstaller (--onedir --noconsole)
  $hiddenImports = @(
    'webview',
    'webview.platforms.edgechromium',
    'webview.platforms.winforms',
    'clr',
    'pythonnet',
    'clr_loader',
    'multipart',
    'multipart.multipart',
    'json_repair',
    'orjson',
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    'api',
    'api.app',
    'api.deps',
    'api.middlewares',
    'api.middlewares.auth',
    'api.middlewares.error_handler',
    'api.v1',
    'api.v1.router',
    'api.v1.endpoints',
    'api.v1.endpoints.agent',
    'api.v1.endpoints.alpha',
    'api.v1.endpoints.analysis',
    'api.v1.endpoints.alerts',
    'api.v1.endpoints.backtest',
    'api.v1.endpoints.decision_signals',
    'api.v1.endpoints.health',
    'api.v1.endpoints.history',
    'api.v1.endpoints.intelligence',
    'api.v1.endpoints.paper_trading',
    'api.v1.endpoints.portfolio',
    'api.v1.endpoints.screening',
    'api.v1.endpoints.stocks',
    'api.v1.endpoints.system_config',
    'api.v1.endpoints.usage',
    'src.quant',
    'src.quant.stats',
    'src.quant.data_loader',
    'src.quant.portfolio',
    'src.quant.tournament',
    'src.quant.paper_book',
    'src.quant.ai_council',
    'src.quant.strategies',
    'src.quant.strategies.engine',
    'src.quant.strategies.library',
    'src.mcp',
    'src.mcp.server',
    'src.mcp.tools',
    'src.mcp.config_gen',
    'src.agent.agent_backend',
    'src.agent.cli_bridge_common',
    'src.agent.claude_cli_backend',
    'src.agent.gemini_cli_backend',
    'src.agent.chat_executor',
    'src.agent.factory',
    'src.services.agent_backend_status_service',
    'src.services.crypto_trend_strategy',
    'src.services.strategy_paper_book',
    'src.services.paper_trading_service',
    'src.services.paper_trading_benchmark',
    'src.services.us_quant_screener',
    'src.services.pead_screener',
    'src.services.pead_event_study',
    'src.services.sec_form4_screener',
    'src.services.bist_screener',
    'src.services.kap_contract_screener',
    'src.services.kap_watch_service',
    'src.services.quant_risk_gate',
    'src.services.market_regime_service',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on'
  )

  $workDir = Join-Path $env:TEMP 'dsa-pyinstaller-build'
  $specDir = Join-Path $env:TEMP 'dsa-pyinstaller-spec'
  $stageDist = Join-Path $env:TEMP 'dsa-pyinstaller-dist'
  New-Item -ItemType Directory -Force -Path $workDir, $specDir, $stageDist | Out-Null

  $pyArgs = @(
    '-m', 'PyInstaller',
    '--name', 'DailyStockAnalysis',
    '--onedir',
    '--noconfirm',
    '--noconsole',
    '--icon', $iconPath,
    '--workpath', $workDir,
    '--specpath', $specDir,
    '--distpath', $stageDist,
    '--add-data', "$root\static;static",
    '--add-data', "$root\strategies;strategies",
    '--add-data', "$root\.env.example;.",
    '--collect-all', 'src.quant',
    '--collect-all', 'src.mcp',
    '--collect-all', 'webview',
    '--collect-all', 'pythonnet',
    '--collect-all', 'clr_loader',
    '--collect-data', 'tiktoken',
    '--collect-data', 'litellm',
    '--exclude-module', 'lark_oapi',
    '--exclude-module', 'matplotlib',
    '--exclude-module', 'tkinter',
    '--exclude-module', 'boto3',
    '--exclude-module', 'botocore',
    '--exclude-module', 's3transfer',
    '--exclude-module', 'pytest',
    '--exclude-module', 'IPython'
  )
  if (Test-Path 'src\assets\share_image') {
    $pyArgs += @('--add-data', "$root\src\assets\share_image;src/assets/share_image")
  }
  foreach ($imp in $hiddenImports) {
    $pyArgs += "--hidden-import=$imp"
  }
  $pyArgs += 'desktop_app.py'

  Write-Host 'Compiling DailyStockAnalysis.exe with PyInstaller...'
  & $python @pyArgs
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

  $stagedAppDir = Join-Path $stageDist 'DailyStockAnalysis'
  $finalAppDir = Join-Path $root 'dist\DailyStockAnalysis'
  New-Item -ItemType Directory -Force -Path $finalAppDir | Out-Null
  Write-Host "Syncing bundle to $finalAppDir ..."
  & robocopy $stagedAppDir $finalAppDir /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

  $exePath = Join-Path $finalAppDir 'DailyStockAnalysis.exe'
  if (-not (Test-Path $exePath)) {
    throw "Expected executable was not produced: $exePath"
  }
  $sizeMb = [math]::Round((Get-Item $exePath).Length / 1MB, 2)
  Write-Host "Built: $exePath ($sizeMb MB launcher + _internal/)"

  if (-not $SkipSmokeTest) {
    Write-Host 'Running live headless smoke test on compiled DailyStockAnalysis.exe...'
    $smokeOut = Join-Path $env:TEMP 'dsa-exe-smoke.out'
    $smokeErr = Join-Path $env:TEMP 'dsa-exe-smoke.err'
    $p = Start-Process -FilePath $exePath -ArgumentList '--smoke-test' -Wait -PassThru -RedirectStandardOutput $smokeOut -RedirectStandardError $smokeErr
    $outTxt = Get-Content $smokeOut -Raw -ErrorAction SilentlyContinue
    $errTxt = Get-Content $smokeErr -Raw -ErrorAction SilentlyContinue
    if ($outTxt) { Write-Host $outTxt.Trim() }
    if ($p.ExitCode -ne 0) {
      if ($errTxt) { Write-Error $errTxt }
      throw "Smoke test failed with exit code $($p.ExitCode)"
    }
  }

  Write-Host '=== Desktop .exe Build Completed Successfully ==='
} finally {
  Pop-Location
}
