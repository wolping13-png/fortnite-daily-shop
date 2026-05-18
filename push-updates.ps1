param(
  [string]$Message = "Add cloud QQ automation"
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
  param([string[]]$Arguments)

  git @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "git $($Arguments -join ' ') failed."
  }
}

Push-Location $PSScriptRoot
try {
  git status --short

  Invoke-Git @("add", "-A")

  git diff --cached --quiet
  if ($LASTEXITCODE -eq 0) {
    Write-Host "No changes to commit." -ForegroundColor Yellow
  }
  else {
    Invoke-Git @("commit", "-m", $Message)
  }

  Write-Host "Syncing remote changes..." -ForegroundColor Cyan
  Invoke-Git @("pull", "--rebase", "--autostash", "origin", "main")

  Write-Host "Pushing updates..." -ForegroundColor Cyan
  Invoke-Git @("push", "origin", "main")

  Write-Host "Updates pushed." -ForegroundColor Green
}
finally {
  Pop-Location
}
