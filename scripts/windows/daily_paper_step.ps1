<#
.SYNOPSIS
  Daily automated step for all simulated DSA StrategyPaperBook ledgers
  (PAA, Meta-Portfolio A, 3-AI Council: Claude/Codex/Gemini, and Crypto 5-SMA).

.DESCRIPTION
  Runs strictly simulated daily mark-to-market & scheduled rebalances
  (never places real broker orders):
    1. scripts\quant_paper.py step --refresh --notify
    2. scripts\crypto_trend.py paper --notify
    3. scripts\paper_trading_report.py --weekly-if-due

  Use -Register to install Windows Task Scheduler task
  `DailyStockAnalysis-DailyPaperStep` (runs daily at 00:30 after US close
  and 18:30 for Friday weekly reports, with StartWhenAvailable catch-up if
  the PC was asleep/off). Use -Status to inspect or -Unregister to remove.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\daily_paper_step.ps1
  powershell -ExecutionPolicy Bypass -File scripts\windows\daily_paper_step.ps1 -Register
  powershell -ExecutionPolicy Bypass -File scripts\windows\daily_paper_step.ps1 -Status
  powershell -ExecutionPolicy Bypass -File scripts\windows\daily_paper_step.ps1 -Unregister
#>
param(
  [switch]$Register,
  [switch]$Unregister,
  [switch]$Status,
  [string]$DailyTime = '00:30',
  [string]$EveningTime = '18:30',
  [switch]$NoRefresh
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$taskName = 'DailyStockAnalysis-DailyPaperStep'
$logDir = Join-Path $root 'logs'
$logFile = Join-Path $logDir 'daily_paper_step.log'

function Resolve-DsaPython {
  $candidates = @()
  if ($env:DSA_MCP_PYTHON) { $candidates += $env:DSA_MCP_PYTHON }
  $candidates += (Join-Path $root '.venv\Scripts\python.exe')
  $candidates += (Join-Path $HOME '.dsa-venv\Scripts\python.exe')
  $pyCmd = Get-Command python -ErrorAction SilentlyContinue
  if ($pyCmd) { $candidates += $pyCmd.Source }

  foreach ($cand in $candidates) {
    if ($cand -and (Test-Path $cand)) {
      try {
        & $cand -c "import pandas, yfinance" 2>$null
        if ($LASTEXITCODE -eq 0) {
          return $cand
        }
      } catch {
        # try next candidate
      }
    }
  }
  throw "No working Python environment with pandas & yfinance found. Set DSA_MCP_PYTHON or create .venv."
}

if ($Unregister) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed scheduled task $taskName."
  exit 0
}

if ($Status) {
  $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
  if (-not $task) {
    Write-Host "Scheduled task $taskName is NOT registered."
    exit 1
  }
  $info = Get-ScheduledTaskInfo -TaskName $taskName
  Write-Host "Task Name       : $taskName"
  Write-Host "State           : $($task.State)"
  Write-Host "Next Run Time   : $($info.NextRunTime)"
  Write-Host "Last Run Time   : $($info.LastRunTime)"
  Write-Host "Last Result     : $($info.LastTaskResult)"
  if (Test-Path $logFile) {
    Write-Host "--- Recent Log ($logFile) ---"
    Get-Content $logFile -Tail 25
  }
  exit 0
}

if ($Register) {
  $python = Resolve-DsaPython
  $action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`"" `
    -WorkingDirectory $root
  $triggers = @(
    (New-ScheduledTaskTrigger -Daily -At $DailyTime),
    (New-ScheduledTaskTrigger -Daily -At $EveningTime)
  )
  $settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

  Register-ScheduledTask `
    -TaskName $taskName `
    -Description 'Daily simulated paper book step for DSA (PAA, Meta-Portfolio A, 3-AI Council, Crypto 5-SMA) and Friday weekly report.' `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

  $info = Get-ScheduledTaskInfo -TaskName $taskName
  Write-Host "Registered $taskName (Python: $python)"
  Write-Host "Triggers        : Daily at $DailyTime & $EveningTime (StartWhenAvailable enabled)"
  Write-Host "Next Run Time   : $($info.NextRunTime)"
  exit 0
}

# --- Execution Mode ---
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$python = Resolve-DsaPython
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
if (-not $env:LITELLM_LOCAL_MODEL_COST_MAP) {
  $env:LITELLM_LOCAL_MODEL_COST_MAP = 'True'
}

function Write-Log([string]$msg) {
  $line = "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))] $msg"
  Add-Content -Path $logFile -Value $line -Encoding UTF8
  Write-Host $line
}

function Invoke-DsaStep([string[]]$StepArgs, [string]$Label) {
  # PowerShell 5.1 turns stderr lines from native exes under 2>&1 into terminating ErrorRecords
  # when $ErrorActionPreference = 'Stop'. Temporarily switch to 'Continue' and check $LASTEXITCODE.
  $prevPref = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $output = & $python @StepArgs 2>&1
    $code = $LASTEXITCODE
    foreach ($entry in $output) {
      Add-Content -Path $logFile -Value ("$entry") -Encoding UTF8
    }
  } finally {
    $ErrorActionPreference = $prevPref
  }
  Write-Log "$Label exit=$code"
  return $code
}

Push-Location $root
try {
  Write-Log "=== DSA Daily Paper Step Started (Python: $python) ==="

  $quantArgs = @('scripts\quant_paper.py', 'step', '--notify')
  if (-not $NoRefresh) { $quantArgs += '--refresh' }
  $qCode = Invoke-DsaStep -StepArgs $quantArgs -Label 'quant_paper.py'

  $cCode = Invoke-DsaStep -StepArgs @('scripts\crypto_trend.py', 'paper', '--notify') -Label 'crypto_trend.py'

  $wCode = Invoke-DsaStep -StepArgs @('scripts\paper_trading_report.py', '--weekly-if-due') -Label 'paper_trading_report.py --weekly-if-due'

  Write-Log "=== DSA Daily Paper Step Finished ==="
  if ($qCode -ne 0 -or $cCode -ne 0 -or $wCode -ne 0) {
    exit 1
  }
  exit 0
} finally {
  Pop-Location
}
