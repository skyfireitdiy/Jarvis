$ErrorActionPreference = "Stop"

$env:UV_PYTHON_INSTALL_MIRROR = "https://python-standalone.org/mirror/astral-sh/python-build-standalone/"
Write-Host "Python installation mirror set to: $($env:UV_PYTHON_INSTALL_MIRROR)" -ForegroundColor Cyan

$GITEE_URL = "https://gitee.com/skyfireitdiy/Jarvis.git"
$GITHUB_URL = "https://github.com/skyfireitdiy/Jarvis.git"
$DEST_DIR = "$env:USERPROFILE\Jarvis"
$DEFAULT_BRANCH = "main"
$DEPS_DIR_RELATIVE = "src\jarvis\jarvis_data\deps\x86_64_windows"

function Ensure-UvAvailable {
    Write-Host "--- 2. Check bundled uv environment ---" -ForegroundColor Green

    $depsDir = Join-Path $DEST_DIR $DEPS_DIR_RELATIVE
    if (-not (Test-Path $depsDir)) {
        Write-Host "Error: Current repository version does not contain bundled Windows dependencies: $depsDir" -ForegroundColor Red
        Write-Host "Please use a repository version that includes Windows bundled dependencies, or install uv manually and try again." -ForegroundColor Yellow
        exit 1
    }

    $env:Path = "$depsDir;" + $env:Path
    Write-Host "Added bundled dependency directory to PATH: $depsDir" -ForegroundColor Cyan

    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCommand) {
        Write-Host "Error: uv was not found in the bundled dependency directory." -ForegroundColor Red
        Write-Host "Please use a repository version that includes Windows bundled dependencies, or install uv manually and try again." -ForegroundColor Yellow
        exit 1
    }

    Write-Host "Found uv: $(uv --version)" -ForegroundColor Cyan
}

function Get-LatestTag {
    param([string]$RepoUrl)

    $tag = git ls-remote --refs --sort='-version:refname' --tags $RepoUrl 2>$null |
        Select-Object -First 1 |
        ForEach-Object { ($_ -split '/')[-1] }
    return $tag
}

function Resolve-SourceReference {
    $script:SOURCE_REF = Get-LatestTag -RepoUrl $GITEE_URL
    if ($script:SOURCE_REF) {
        $script:SOURCE_URL = $GITEE_URL
        return
    }

    $script:SOURCE_REF = Get-LatestTag -RepoUrl $GITHUB_URL
    if ($script:SOURCE_REF) {
        $script:SOURCE_URL = $GITHUB_URL
        return
    }

    $script:SOURCE_URL = $GITHUB_URL
    $script:SOURCE_REF = $DEFAULT_BRANCH
}

function Checkout-SourceReference {
    param([string]$SourceRef)

    try {
        git fetch --depth 1 origin "refs/tags/$SourceRef`:refs/tags/$SourceRef" 2>$null
        git checkout -f $SourceRef
        return
    }
    catch {
        git fetch --depth 1 origin $SourceRef
        git checkout -f FETCH_HEAD
    }
}

function Prepare-SourceTree {
    Write-Host "`n--- 1. Download Jarvis source code ---" -ForegroundColor Green
    Resolve-SourceReference
    Write-Host "Target version: $script:SOURCE_REF" -ForegroundColor Cyan
    Write-Host "Source URL: $script:SOURCE_URL" -ForegroundColor Cyan

    if ((Test-Path $DEST_DIR) -and -not (Test-Path "$DEST_DIR\.git")) {
        Write-Host "Warning: '$DEST_DIR' exists but is not a git repository" -ForegroundColor Red
        Write-Host "Please manually backup or delete this directory and run the installer again." -ForegroundColor Yellow
        exit 1
    }

    if (Test-Path "$DEST_DIR\.git") {
        Write-Host "Detected existing Jarvis source repository, switching to target version..." -ForegroundColor Cyan
        Push-Location $DEST_DIR
        $status = git status --porcelain
        if ($status) {
            Write-Host "Error: '$DEST_DIR' contains uncommitted changes. Please clean them first." -ForegroundColor Red
            Pop-Location
            exit 1
        }
        git remote set-url origin $script:SOURCE_URL
        Checkout-SourceReference -SourceRef $script:SOURCE_REF
        Pop-Location
        return
    }

    Write-Host "Cloning source code to $DEST_DIR..." -ForegroundColor Yellow
    try {
        git clone --depth 1 --branch $script:SOURCE_REF $script:SOURCE_URL $DEST_DIR
        return
    }
    catch {
        if ($script:SOURCE_URL -ne $GITHUB_URL) {
            $script:SOURCE_URL = $GITHUB_URL
            Write-Host "Gitee download failed, retrying from GitHub..." -ForegroundColor Yellow
            git clone --depth 1 --branch $script:SOURCE_REF $script:SOURCE_URL $DEST_DIR
            return
        }

        Write-Host "Source download failed, please check your network connection." -ForegroundColor Red
        exit 1
    }
}

function Install-Tools {
    Write-Host "`n--- 3. Install Jarvis from source ---" -ForegroundColor Green
    Set-Location $DEST_DIR
    uv tool install -e .
    uv tool install playwright
    uv tool install ddgr
}

Prepare-SourceTree
Ensure-UvAvailable
Install-Tools

Write-Host "`n--- 4. Installation complete! ---" -ForegroundColor Green
Write-Host "Jarvis has been globally installed successfully! You can now use the jarvis command directly." -ForegroundColor Cyan
Write-Host "Installed extra tools: playwright, ddgr" -ForegroundColor Cyan
Write-Host "Source directory: $DEST_DIR" -ForegroundColor Cyan
