# Keep the trading dashboard + bot loop running on this PC.
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File .\scripts\run-24-7.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
$env:AUTO_START = "true"

Write-Host "Desk 24/7 runner"
Write-Host "Project: $Root"
Write-Host "Dashboard: http://127.0.0.1:8787"
Write-Host "Ctrl+C stops. For true always-on, install as a Windows service (see README)."

while ($true) {
  try {
    uv run trading-dashboard
  } catch {
    Write-Host "Dashboard exited: $_"
  }
  Write-Host "Restarting in 5s..."
  Start-Sleep -Seconds 5
}
