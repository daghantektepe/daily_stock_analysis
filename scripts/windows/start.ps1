<#
.SYNOPSIS
  Start the web UI + daily schedule and the KAP watcher, each in its own window.

.DESCRIPTION
  Window 1: python main.py --serve --schedule   (web UI on http://127.0.0.1:8000,
            analysis at SCHEDULE_TIMES while the PC is on)
  Window 2: python scripts\kap_watch.py         (intraday KAP alerts)

  -RegisterAtLogon creates a Windows scheduled task that runs this script
  when you log in; -UnregisterAtLogon removes it.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1
  powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1 -RegisterAtLogon
#>
param(
  [switch]$NoWatch,
  [switch]$NoServe,
  [switch]$RegisterAtLogon,
  [switch]$UnregisterAtLogon
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $root '.venv\Scripts\python.exe'
$taskName = 'DailyStockAnalysis-BIST'

if ($UnregisterAtLogon) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed scheduled task $taskName."
  exit 0
}

if ($RegisterAtLogon) {
  $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -WorkingDirectory $root
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Force | Out-Null
  Write-Host "Registered ${taskName}: starts at every logon of $env:USERNAME."
  exit 0
}

if (-not (Test-Path $python)) { throw "No virtual environment at $python - run scripts\windows\install.ps1 first." }
if (-not (Test-Path (Join-Path $root '.env'))) { throw "No .env in $root - run scripts\windows\install.ps1 first." }

if (-not $NoServe) {
  Start-Process -FilePath $python -ArgumentList 'main.py', '--serve', '--schedule' -WorkingDirectory $root
  Write-Host 'Started web UI + schedule: http://127.0.0.1:8000'
}
if (-not $NoWatch) {
  Start-Process -FilePath $python -ArgumentList 'scripts\kap_watch.py' -WorkingDirectory $root
  Write-Host 'Started KAP watcher.'
}
Write-Host 'Close a window (or press Ctrl+C in it) to stop that part.'
