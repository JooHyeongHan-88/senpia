# packaging/release.ps1
#
# Steps:
#   1. Sync version from pyproject.toml -> backend/_version.py
#   2. Frontend build (Vite)             -> build/web/
#   3. Updater.exe build                 -> build/updater/Updater.exe
#   4. App EXE build                     -> release/{AppName}.exe
#   5. Compute sha256 + generate          release/latest.json
#   6. Upload to Nexus raw repo (requires -Upload flag)
#
# App name is read automatically from the name= field in packaging/App.spec.
# To rename the output EXE, change name='...' in packaging/App.spec — no other edits needed.
#
# Output layout:
#   build/    intermediate artifacts (bundled into the EXE, never uploaded)
#   release/  final artifacts (uploaded to Nexus)
#
# Usage:
#   pwsh packaging/release.ps1
#   pwsh packaging/release.ps1 -Upload -NexusBaseUrl https://nexus.internal/repository/myapp -NexusUser foo -NexusPass bar

param(
    [switch]$Upload,
    [switch]$Force,
    [string]$NexusBaseUrl = "",
    [string]$NexusUser,
    [string]$NexusPass,
    [string]$Notes = ""
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

# Helper for network retries
function Invoke-WithRetry {
    param (
        [scriptblock]$Action,
        [int]$MaxRetries = 3,
        [int]$DelaySeconds = 5
    )
    $attempt = 1
    while ($true) {
        try {
            & $Action
            return
        } catch {
            if ($attempt -ge $MaxRetries) {
                throw "Failed after $MaxRetries attempts: $_"
            }
            Write-Host "    -> Error: $_. Retrying in $DelaySeconds seconds (Attempt $attempt of $MaxRetries)..." -ForegroundColor Yellow
            Start-Sleep -Seconds $DelaySeconds
            $attempt++
        }
    }
}

# 0. Pre-flight checks
if (-not $Force) {
    # Check for uncommitted changes
    $gitStatus = git status --porcelain
    if ($gitStatus) {
        Write-Host "ERROR: Git working directory is not clean. Commit your changes before releasing, or use -Force to bypass." -ForegroundColor Red
        Write-Host $gitStatus -ForegroundColor Yellow
        exit 1
    }
}

# Ensure output directories exist.
New-Item -ItemType Directory -Force -Path "build", "release" | Out-Null

# Load .env file into environment variables
$envPath = Join-Path $root ".env"
if (Test-Path $envPath) {
    Write-Host "==> loading .env configuration"
    Get-Content $envPath -Encoding UTF8 | Where-Object { $_ -match '^\s*([^#\s][^=]*)=(.*)$' } | ForEach-Object {
        $key = $Matches[1].Trim()
        # Strip inline comment (e.g. "MyAgent  # description") then remove surrounding quotes
        $val = ($Matches[2] -split '\s+#', 2)[0].Trim().Trim('"').Trim("'")
        if (-not (Test-Path "env:$key")) {
            [Environment]::SetEnvironmentVariable($key, $val)
        }
    }
}

# Detect AppName from environment (set by .env)
$AppName = $env:APP_NAME
if (-not $AppName) {
    $AppName = "MyAgent"
}
Write-Host "==> app name  : $AppName"

# Fall back to a sensible Nexus default if not provided.
if (-not $NexusBaseUrl) {
    if ($env:APP_NEXUS_BASE_URL) {
        $NexusBaseUrl = $env:APP_NEXUS_BASE_URL
    } else {
        $NexusBaseUrl = "https://nexus.internal/repository/$($AppName.ToLower())"
    }
}

# 1. version sync: pyproject.toml -> backend/_version.py
$pyproject = Get-Content "pyproject.toml" -Raw
if ($pyproject -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
    throw "version field not found in pyproject.toml"
}
$version = $Matches[1]
Write-Host "==> version   : $version"

[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location).Path "backend/_version.py"),
    "__version__ = `"$version`"`n",
    (New-Object System.Text.UTF8Encoding $false)
)

# Resolve credentials and pre-flight check Nexus version existence
if ($Upload) {
    if (-not $NexusUser) { $NexusUser = $env:NEXUS_USER }
    if (-not $NexusUser) { $NexusUser = $env:APP_NEXUS_USER } # support .env prefix
    
    if (-not $NexusPass) { $NexusPass = $env:NEXUS_PASSWORD }
    if (-not $NexusPass) { $NexusPass = $env:APP_NEXUS_PASSWORD } # support .env prefix
    
    if (-not $NexusUser -or -not $NexusPass) {
        Write-Host "Nexus credentials not provided via parameters or environment variables (NEXUS_USER/NEXUS_PASSWORD)."
        $NexusUser = Read-Host "Enter Nexus Username"
        $securePass = Read-Host "Enter Nexus Password" -AsSecureString
        $NexusPass = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePass))
    }
    
    $global:headers = @{}
    if ($NexusUser -and $NexusPass) {
        $pair = "$NexusUser`:$NexusPass"
        $b64  = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pair))
        $global:headers["Authorization"] = "Basic $b64"
    }

    $versionedName = "$AppName-$version.exe"
    Write-Host "==> checking if $versionedName already exists on Nexus..."
    try {
        $null = Invoke-RestMethod -Uri "$NexusBaseUrl/$versionedName" -Method Head -Headers $global:headers -ErrorAction Stop
        # If no error, the file already exists (200 OK)
        if (-not $Force) {
            Write-Host "ERROR: Version $version ($versionedName) already exists on Nexus. Increment version or use -Force." -ForegroundColor Red
            exit 1
        } else {
            Write-Host "WARNING: Version $version already exists, but -Force is specified. Proceeding to overwrite." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "    -> Not found on server (or check failed). Clear to proceed." -ForegroundColor Green
    }
}

# 2. frontend build -> build/web/
Write-Host "==> frontend build  (-> build/web/)"
Push-Location frontend
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "frontend build failed" }
Pop-Location

# 3. Updater.exe -> build/updater/Updater.exe
Write-Host "==> updater build   (-> build/updater/)"
uv run pyinstaller --noconfirm --clean `
    --distpath build/updater `
    --workpath build/pyi-updater `
    packaging/Updater.spec
if ($LASTEXITCODE -ne 0) { throw "updater build failed" }

if (-not (Test-Path "build/updater/Updater.exe")) {
    throw "build/updater/Updater.exe was not created"
}

# 4. App EXE -> release/{AppName}.exe
Write-Host "==> app build       (-> release/)"
uv run pyinstaller --noconfirm --clean `
    --distpath release `
    --workpath build/pyi-app `
    packaging/App.spec
if ($LASTEXITCODE -ne 0) { throw "app build failed" }

$exePath = "release/$AppName.exe"
if (-not (Test-Path $exePath)) {
    throw "$exePath was not created"
}

# 5. sha256 + latest.json
$sha256 = (Get-FileHash $exePath -Algorithm SHA256).Hash.ToLower()
$size   = (Get-Item $exePath).Length
$releasedAt = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")

$versionedName = "$AppName-$version.exe"
$versionedPath = "release/$versionedName"
Copy-Item $exePath $versionedPath -Force

$latest = [ordered]@{
    version               = $version
    url                   = "$NexusBaseUrl/$versionedName"
    sha256                = $sha256
    size                  = $size
    released_at           = $releasedAt
    min_supported_version = "0.0.0"
    notes                 = $Notes
}

$latestJsonPath = "release/latest.json"
# Must write UTF-8 without BOM: PowerShell 5.1 Set-Content -Encoding utf8 adds BOM,
# which breaks Invoke-RestMethod JSON parsing on the receiving end.
$jsonContent = $latest | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location).Path $latestJsonPath),
    $jsonContent,
    (New-Object System.Text.UTF8Encoding $false)
)

Write-Host ""
Write-Host "==> artifacts"
Write-Host "    $versionedPath  ($size bytes)"
Write-Host "    sha256 : $sha256"
Write-Host "    $latestJsonPath"

# 6. upload
if ($Upload) {
    if (-not $NexusUser -or -not $NexusPass) {
        Write-Host "WARNING: Nexus credentials still missing; proceeding with anonymous PUT." -ForegroundColor Yellow
    }

    # Upload EXE first -- latest.json must go last so clients never see a metadata
    # pointer to a non-existent file.
    Write-Host "==> uploading $versionedName"
    Invoke-WithRetry -Action {
        Invoke-WebRequest -Uri "$NexusBaseUrl/$versionedName" `
            -Method Put -InFile $versionedPath -Headers $global:headers `
            -ContentType "application/octet-stream" | Out-Null
    }

    Write-Host "==> uploading latest.json"
    Invoke-WithRetry -Action {
        Invoke-WebRequest -Uri "$NexusBaseUrl/latest.json" `
            -Method Put -InFile $latestJsonPath -Headers $global:headers `
            -ContentType "application/json" | Out-Null
    }

    Write-Host "uploaded: $NexusBaseUrl/$versionedName"
    Write-Host "uploaded: $NexusBaseUrl/latest.json"
} else {
    Write-Host ""
    Write-Host "Skipping upload. Add -Upload flag to push to Nexus."
}
