param(
  [string]$RepoName = "fortnite-daily-shop",
  [ValidateSet("public", "private")]
  [string]$Visibility = "public"
)

$ErrorActionPreference = "Stop"
$LogPath = Join-Path $PSScriptRoot "publish.log"

try {
  Start-Transcript -Path $LogPath -Force | Out-Null
}
catch {
  $LogPath = $null
}

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
  param([string]$Message)
  Write-Host "OK  $Message" -ForegroundColor Green
}

function Write-Warn {
  param([string]$Message)
  Write-Host "!!  $Message" -ForegroundColor Yellow
}

function Test-NativeCommand {
  param(
    [string]$Command,
    [string[]]$Arguments = @()
  )

  $oldErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"

  try {
    & $Command @Arguments 1>$null 2>$null
    return $LASTEXITCODE -eq 0
  }
  catch {
    return $false
  }
  finally {
    $ErrorActionPreference = $oldErrorActionPreference
  }
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

  $winget = Find-CommandPath @("winget")
  if ($winget) {
    Write-Step "Installing Python with winget"
    winget install --id Python.Python.3.12 -e --source winget
    $python = Find-CommandPath @("python", "python3")
    if ($python) {
      return @{ Path = $python; Args = @() }
    }
  }

  throw "No Python was found. Install Python 3.12 or newer, then run this script again."
}

function Run-Python {
  param(
    [hashtable]$Python,
    [string[]]$Arguments
  )

  & $Python.Path @($Python.Args + $Arguments)
}

function Ensure-Git {
  if (-not (Find-CommandPath @("git"))) {
    $winget = Find-CommandPath @("winget")
    if ($winget) {
      Write-Step "Installing Git with winget"
      winget install --id Git.Git -e --source winget
    }

    if (-not (Find-CommandPath @("git"))) {
      throw "Git was not found. Install Git for Windows, then run this script again."
    }
  }
}

function Ensure-GitHubCli {
  if (-not (Find-CommandPath @("gh"))) {
    $winget = Find-CommandPath @("winget")
    if ($winget) {
      Write-Step "Installing GitHub CLI with winget"
      winget install --id GitHub.cli -e --source winget
    }

    if (-not (Find-CommandPath @("gh"))) {
      throw "GitHub CLI was not found. Install it from https://cli.github.com/ and run: gh auth login"
    }
  }
}

function Ensure-GitHubLogin {
  if (-not (Test-NativeCommand "gh" @("auth", "status", "-h", "github.com"))) {
    Write-Step "Signing in to GitHub"
    Write-Host "A browser window may open. Finish GitHub authorization, then return to this PowerShell window." -ForegroundColor Yellow
    gh auth login -h github.com -w -s repo

    if (-not (Test-NativeCommand "gh" @("auth", "status", "-h", "github.com"))) {
      throw "GitHub login did not complete. Run 'gh auth login -h github.com -w -s repo' once, then run this script again."
    }
  }
}

function Ensure-GitRepository {
  $userName = git config user.name
  if (-not $userName) {
    git config user.name "Fortnite Shop Publisher"
  }

  $userEmail = git config user.email
  if (-not $userEmail) {
    git config user.email "fortnite-shop@example.com"
  }

  if (-not (Test-Path ".git")) {
    git init | Out-Null
    git branch -M main | Out-Null
  }

  if (Test-NativeCommand "git" @("ls-files", "--error-unmatch", "publish.log")) {
    git rm --cached publish.log | Out-Null
  }

  git add -A | Out-Null

  git diff --cached --quiet
  if ($LASTEXITCODE -ne 0) {
    git commit -m "Initial Fortnite shop site" | Out-Null
  }
  else {
    Write-Ok "No local file changes to commit"
  }
}

function Ensure-GitHubRepository {
  param([string]$Name, [string]$RepoVisibility)

  $owner = gh api user --jq ".login"
  $fullName = "$owner/$Name"
  $visibilityFlag = "--$RepoVisibility"

  if (-not (Test-NativeCommand "gh" @("repo", "view", $fullName))) {
    Write-Step "Creating GitHub repository $fullName"
    gh repo create $Name --source . --remote origin $visibilityFlag --push | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "GitHub repository creation failed."
    }
  }
  else {
    Write-Step "Using existing GitHub repository $fullName"
    $remoteUrl = "https://github.com/$fullName.git"
    if (-not (Test-NativeCommand "git" @("remote", "get-url", "origin"))) {
      git remote add origin $remoteUrl | Out-Null
    }
    else {
      git remote set-url origin $remoteUrl | Out-Null
    }

    git push -u origin main | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "Git push failed."
    }
  }

  return @{
    Owner = $owner
    Name = $Name
    FullName = $fullName
  }
}

function Enable-Pages {
  param([hashtable]$Repo)

  Write-Step "Enabling GitHub Pages"

  if (Test-NativeCommand "gh" @("api", "repos/$($Repo.FullName)/pages")) {
    gh api "repos/$($Repo.FullName)/pages" `
      --method PUT `
      -f "source[branch]=main" `
      -f "source[path]=/" *> $null
  }
  else {
    gh api "repos/$($Repo.FullName)/pages" `
      --method POST `
      -f "source[branch]=main" `
      -f "source[path]=/" *> $null
  }

  Start-Sleep -Seconds 2
  $pageInfo = gh api "repos/$($Repo.FullName)/pages" --jq ".html_url"
  return $pageInfo
}

function Trigger-ShopUpdate {
  param([hashtable]$Repo)

  Write-Step "Running the first shop update on GitHub Actions"
  for ($attempt = 1; $attempt -le 6; $attempt++) {
    gh workflow run "Update Fortnite Shop" --repo $Repo.FullName --ref main *> $null
    if ($LASTEXITCODE -eq 0) {
      Write-Ok "GitHub Actions update was triggered"
      return
    }

    Start-Sleep -Seconds 10
  }

  Write-Warn "The first action run may take 1-3 minutes. Refresh the Actions page if the shop is still empty."
}

Push-Location $PSScriptRoot
try {
  Write-Step "Checking tools"
  Ensure-Git
  Ensure-GitHubCli
  Ensure-GitHubLogin
  $python = Find-Python
  Write-Ok "Tools are ready"

  Write-Step "Checking Python dependencies and script syntax"
  Run-Python $python @("-m", "pip", "install", "-r", "requirements.txt")
  Run-Python $python @("-m", "py_compile", "update_shop.py")
  Run-Python $python @("-m", "py_compile", "generate_shop_image.py")
  Write-Ok "Python side is ready"

  Write-Step "Trying to generate shop.json locally"
  try {
    Run-Python $python @("update_shop.py")
    Run-Python $python @("generate_shop_image.py")
    Write-Ok "shop.json was generated locally"
  }
  catch {
    Write-Warn "Local API request failed. GitHub Actions will still try again after publishing."
  }

  Write-Step "Preparing Git commit"
  Ensure-GitRepository
  Write-Ok "Local Git repository is ready"

  $repo = Ensure-GitHubRepository -Name $RepoName -RepoVisibility $Visibility
  Write-Ok "Repository is published: https://github.com/$($repo.FullName)"

  $pagesUrl = Enable-Pages -Repo $repo
  Trigger-ShopUpdate -Repo $repo

  Write-Host ""
  Write-Host "Done." -ForegroundColor Green
  Write-Host "GitHub repository: https://github.com/$($repo.FullName)"
  Write-Host "Website: $pagesUrl"
  Write-Host "Actions: https://github.com/$($repo.FullName)/actions"
}
finally {
  if ($LogPath) {
    try {
      Stop-Transcript | Out-Null
      Write-Host "Log saved to: $LogPath" -ForegroundColor DarkGray
    }
    catch {
    }
  }

  Pop-Location
}
