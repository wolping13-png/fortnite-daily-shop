param(
  [string]$Message = "Add cloud QQ automation"
)

$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
  git status --short

  git add -A

  git diff --cached --quiet
  if ($LASTEXITCODE -eq 0) {
    Write-Host "No changes to commit." -ForegroundColor Yellow
  }
  else {
    git commit -m $Message
  }

  git push
  Write-Host "Updates pushed." -ForegroundColor Green
}
finally {
  Pop-Location
}
