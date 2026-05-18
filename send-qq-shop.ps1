param(
  [switch]$UpdateFirst
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$ConfigPath = Join-Path $Root "qq_bot_config.json"

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Find-CommandPath {
  param([string[]]$Names)

  foreach ($name in $Names) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command) {
      return $command.Source
    }
  }

  return $null
}

function Find-Python {
  $python = Find-CommandPath @("python", "python3")
  if ($python) {
    return @{ Path = $python; Args = @() }
  }

  $py = Find-CommandPath @("py")
  if ($py) {
    return @{ Path = $py; Args = @("-3") }
  }

  $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if (Test-Path $codexPython) {
    return @{ Path = $codexPython; Args = @() }
  }

  throw "Python was not found. Install Python 3.12 or newer."
}

function Run-Python {
  param(
    [hashtable]$Python,
    [string[]]$Arguments
  )

  & $Python.Path @($Python.Args + $Arguments)
}

function Ensure-Config {
  if (Test-Path $ConfigPath) {
    return
  }

  Write-Step "Creating QQ bot config"
  $baseUrl = Read-Host "NapCat OneBot HTTP address [http://127.0.0.1:3000]"
  if (-not $baseUrl) {
    $baseUrl = "http://127.0.0.1:3000"
  }

  $groupId = Read-Host "QQ group ID"
  if (-not $groupId) {
    throw "QQ group ID is required."
  }

  $token = Read-Host "Access token, press Enter if none"
  $caption = Read-Host "Caption [Fortnite Daily Shop]"
  if (-not $caption) {
    $caption = "Fortnite Daily Shop"
  }

  $config = [ordered]@{
    onebot_http_url = $baseUrl
    access_token = $token
    group_ids = @($groupId)
    caption = $caption
    image_url = ""
  }

  $config | ConvertTo-Json -Depth 4 | Set-Content -Path $ConfigPath -Encoding UTF8
  Write-Host "Saved config to $ConfigPath" -ForegroundColor Green
}

Push-Location $Root
try {
  $python = Find-Python
  Ensure-Config

  Write-Step "Installing Python dependencies"
  Run-Python $python @("-m", "pip", "install", "-r", "requirements.txt")

  if ($UpdateFirst) {
    Write-Step "Updating shop data and image"
    Run-Python $python @("update_shop.py")
    Run-Python $python @("generate_shop_image.py")
  }
  elseif (-not (Test-Path (Join-Path $Root "shop.png"))) {
    Write-Step "Generating shop image"
    Run-Python $python @("generate_shop_image.py")
  }

  Write-Step "Sending QQ group image"
  Run-Python $python @("send_qq_shop.py")
  Write-Host ""
  Write-Host "Done." -ForegroundColor Green
}
finally {
  Pop-Location
}
