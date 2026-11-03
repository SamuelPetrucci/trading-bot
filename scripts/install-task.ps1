# Register a Windows Scheduled Task that starts the bot at login and keeps it up.
# Run PowerShell as Administrator once:
#   powershell -ExecutionPolicy Bypass -File .\scripts\install-task.ps1

$Root = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $Root "scripts\run-24-7.ps1"
$TaskName = "TradingBotDesk"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Scheduled task '$TaskName' installed. It starts at login."
Write-Host "Start now: Start-ScheduledTask -TaskName $TaskName"
Write-Host "Remove later: Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
