<#
.SYNOPSIS
  Standalone Browser Web App launcher for Daily Stock Analysis (zero Electron required).

.DESCRIPTION
  Starts the local FastAPI + React PWA server silently in the background (if not
  already healthy), waits for /api/v1/health, and opens Microsoft Edge or Google
  Chrome in borderless standalone Web App mode (--app=...) — or in a standard tab.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\web_app.ps1
  powershell -ExecutionPolicy Bypass -File scripts\windows\web_app.ps1 -Tab
  powershell -ExecutionPolicy Bypass -File scripts\windows\web_app.ps1 -Lan
  powershell -ExecutionPolicy Bypass -File scripts\windows\web_app.ps1 -Status
  powershell -ExecutionPolicy Bypass -File scripts\windows\web_app.ps1 -Stop
  powershell -ExecutionPolicy Bypass -File scripts\windows\web_app.ps1 -CreateShortcut
  powershell -ExecutionPolicy Bypass -File scripts\windows\web_app.ps1 -RegisterServer
#>
param(
  [string]$BindHost = '127.0.0.1',
  [int]$Port = 8000,
  [string]$Route = '/discover',
  [switch]$Tab,
  [switch]$Lan,
  [switch]$ServerOnly,
  [switch]$Status,
  [switch]$Stop,
  [switch]$CreateShortcut,
  [switch]$RegisterServer,
  [switch]$UnregisterServer
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$logDir = Join-Path $root 'logs'
$dataDir = Join-Path $root 'data'
$pidFile = Join-Path $dataDir 'web_app_server.pid'
$outLog = Join-Path $logDir 'web_app_server.log'
$errLog = Join-Path $logDir 'web_app_server.err.log'
$taskName = 'DailyStockAnalysis-WebAppServer'

if ($Lan) {
  $BindHost = '0.0.0.0'
}

$localBase = "http://127.0.0.1:$Port"
$healthUrl = "$localBase/api/v1/health"
$targetUrl = "$localBase$Route"

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
        & $cand -c "import fastapi, uvicorn" 2>$null
        if ($LASTEXITCODE -eq 0) { return $cand }
      } catch {}
    }
  }
  throw "No working Python environment with fastapi & uvicorn found. Set DSA_MCP_PYTHON or create .venv."
}

function Test-ServerHealthy {
  try {
    $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
    return ($resp.StatusCode -eq 200)
  } catch {
    return $false
  }
}

function Get-LanIpv4 {
  try {
    $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
      Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
      Select-Object -First 1 -ExpandProperty IPAddress
    return $ip
  } catch {
    return $null
  }
}

function Find-ChromiumBrowser {
  $paths = @(
    "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe"
  )
  foreach ($p in $paths) {
    if ($p -and (Test-Path $p)) { return $p }
  }
  return $null
}

if ($UnregisterServer) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed logon web server task $taskName."
  exit 0
}

if ($RegisterServer) {
  $null = Resolve-DsaPython
  $action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`" -ServerOnly -BindHost $BindHost -Port $Port" `
    -WorkingDirectory $root
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  Register-ScheduledTask `
    -TaskName $taskName `
    -Description 'Starts Daily Stock Analysis standalone browser Web App server in the background at user logon.' `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null
  Write-Host "Registered $taskName (starts Web App server automatically at logon on $localBase)."
  exit 0
}

if ($CreateShortcut) {
  $desktop = [Environment]::GetFolderPath('Desktop')
  $lnkPath = Join-Path $desktop 'DSA Web App.lnk'
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($lnkPath)
  $shortcut.TargetPath = 'powershell.exe'
  $shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Port $Port -Route `"$Route`""
  $shortcut.WorkingDirectory = $root
  $shortcut.Description = 'Daily Stock Analysis · Independent Browser Web App (Zero Electron)'
  $browserExe = Find-ChromiumBrowser
  if ($browserExe) {
    $shortcut.IconLocation = "$browserExe,0"
  }
  $shortcut.Save()
  Write-Host "Created desktop shortcut: $lnkPath"
  exit 0
}

if ($Stop) {
  $stopped = $false
  if (Test-Path $pidFile) {
    $savedPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ($savedPid -match '^\d+$') {
      try {
        Stop-Process -Id ([int]$savedPid) -Force -ErrorAction Stop
        Write-Host "Stopped DSA Web App server (PID $savedPid)."
        $stopped = $true
      } catch {}
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
  }
  if (-not $stopped) {
    Write-Host "No tracked Web App server PID found in $pidFile."
  }
  exit 0
}

if ($Status) {
  $healthy = Test-ServerHealthy
  $lanIp = Get-LanIpv4
  $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
  Write-Host "=== DSA Independent Web App Status ==="
  Write-Host "Web Server      : $(if ($healthy) { 'RUNNING' } else { 'STOPPED' })"
  Write-Host "Local URL       : $targetUrl"
  if ($lanIp) {
    Write-Host "LAN URL (if -Lan): http://${lanIp}:${Port}$Route"
  }
  Write-Host "Logon Autostart : $(if ($task) { $task.State } else { 'Not registered' })"
  exit $(if ($healthy) { 0 } else { 1 })
}

# Start FastAPI server silently if not already listening
if (-not (Test-ServerHealthy)) {
  $python = Resolve-DsaPython
  New-Item -ItemType Directory -Force -Path $logDir, $dataDir | Out-Null
  $env:PYTHONIOENCODING = 'utf-8'
  $env:PYTHONUTF8 = '1'
  $proc = Start-Process `
    -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'server:app', '--host', $BindHost, '--port', "$Port" `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru
  Set-Content -Path $pidFile -Value "$($proc.Id)" -Encoding ASCII

  $ready = $false
  for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 1
    if (Test-ServerHealthy) {
      $ready = $true
      break
    }
    if ($proc.HasExited) {
      throw "Web App server exited prematurely (code $($proc.ExitCode)). Check $errLog."
    }
  }
  if (-not $ready) {
    throw "Timed out waiting for DSA Web App server on $healthUrl. Check $errLog."
  }
  Write-Host "DSA Web App server started (PID $($proc.Id)) on $localBase"
} else {
  Write-Host "DSA Web App server already running on $localBase"
}

if ($Lan) {
  $lanIp = Get-LanIpv4
  if ($lanIp) {
    Write-Host "LAN / Mobile URL: http://${lanIp}:${Port}$Route"
    Write-Host "Security tip: enable ADMIN_AUTH_ENABLED=true in Settings before sharing over Wi-Fi."
  }
}

if ($ServerOnly) {
  exit 0
}

# Launch independent browser window (App Mode by default, or normal tab with -Tab)
if (-not $Tab) {
  $browser = Find-ChromiumBrowser
  if ($browser) {
    Start-Process -FilePath $browser -ArgumentList "--app=$targetUrl"
    Write-Host "Opened standalone browser app window: $targetUrl"
    exit 0
  }
}

Start-Process $targetUrl
Write-Host "Opened in default browser: $targetUrl"
exit 0
