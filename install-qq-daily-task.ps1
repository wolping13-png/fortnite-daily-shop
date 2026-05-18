param(
  [string]$Time = "08:15"
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$TaskName = "FortniteDailyShopQQ"
$ScriptPath = Join-Path $Root "send-qq-shop.ps1"

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -UpdateFirst" `
  -WorkingDirectory $Root

$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Description "Update Fortnite shop image and send it to QQ through NapCat OneBot." `
  -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName at $Time every day." -ForegroundColor Green
Write-Host "Keep NapCatQQ running before that time, or the send step will fail." -ForegroundColor Yellow
