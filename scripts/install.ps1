$ErrorActionPreference = "Stop"

# ===== 全局变量 =====
$INSTALL_STATUS_FILE = "$env:USERPROFILE\.jarvis_install_status"
$FORCE_REINSTALL = $false
$RESUME_INSTALL = $true

# ===== 解析命令行参数 =====
param(
    [switch]$Force,
    [switch]$NoResume,
    [switch]$Help
)

if ($Help) {
    Write-Host "用法：powershell -File install.ps1 [选项]" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "选项:" -ForegroundColor Yellow
    Write-Host "  -Force, -f       强制重新安装，忽略之前的安装状态"
    Write-Host "  -NoResume, -n    不恢复安装，从头开始"
    Write-Host "  -Help, -h        显示此帮助信息"
    Write-Host ""
    Write-Host "示例:" -ForegroundColor Yellow
    Write-Host "  powershell -File install.ps1              # 正常安装（自动检测断点）"
    Write-Host "  powershell -File install.ps1 -Force       # 强制重新安装"
    Write-Host "  powershell -File install.ps1 -NoResume    # 不恢复，从头开始"
    exit 0
}

if ($Force) {
    $FORCE_REINSTALL = $true
    $RESUME_INSTALL = $false
}

if ($NoResume) {
    $RESUME_INSTALL = $false
}

# ===== 安装状态管理函数 =====
function Init-StatusFile {
    if ($FORCE_REINSTALL) {
        Write-Host "强制重装模式：清除之前的安装状态..." -ForegroundColor Cyan
        if (Test-Path $INSTALL_STATUS_FILE) {
            Remove-Item $INSTALL_STATUS_FILE -Force
        }
    }
}

function Check-StepCompleted {
    param([string]$StepName)
    if ((Test-Path $INSTALL_STATUS_FILE) -and (Select-String -Path $INSTALL_STATUS_FILE -Pattern "^$StepName$" -Quiet)) {
        return $true
    }
    return $false
}

function Mark-StepCompleted {
    param([string]$StepName)
    Add-Content -Path $INSTALL_STATUS_FILE -Value $StepName
}

function Cleanup-StatusFile {
    if (Test-Path $INSTALL_STATUS_FILE) {
        Remove-Item $INSTALL_STATUS_FILE -Force
    }
}

function Show-InstallStatus {
    Write-Host "`n--- 检查安装状态 ---" -ForegroundColor Green
    if (-not (Test-Path $INSTALL_STATUS_FILE)) {
        Write-Host "未检测到之前的安装记录" -ForegroundColor Cyan
        return
    }
    
    $steps = @("prerequisites_checked", "source_downloaded", "uv_verified", "tools_installed")
    $stepNames = @("前置检查", "源码下载", "UV 验证", "工具安装")
    $hasCompleted = $false
    
    for ($i = 0; $i -lt $steps.Length; $i++) {
        if (Check-StepCompleted -StepName $steps[$i]) {
            Write-Host "  ✓ $($stepNames[$i]) (已完成)" -ForegroundColor Green
            $hasCompleted = $true
        } else {
            Write-Host "  ○ $($stepNames[$i]) (待执行)" -ForegroundColor Yellow
        }
    }
    
    if ($hasCompleted -and $RESUME_INSTALL) {
        Write-Host ""
        $confirm = Read-Host "检测到未完成的安装，是否从断点继续？[Y/n]"
        if ($confirm -match "^[Nn]") {
            $script:RESUME_INSTALL = $false
            Write-Host "将重新开始安装..." -ForegroundColor Cyan
        }
    } elseif ($hasCompleted -and -not $RESUME_INSTALL) {
        Write-Host ""
        Write-Host "将跳过已完成的步骤或重新开始安装..." -ForegroundColor Cyan
    }
}

$env:UV_PYTHON_INSTALL_MIRROR = "https://python-standalone.org/mirror/astral-sh/python-build-standalone/"
Write-Host "Python installation mirror set to: $($env:UV_PYTHON_INSTALL_MIRROR)" -ForegroundColor Cyan

$GITEE_URL = "https://gitee.com/skyfireitdiy/Jarvis.git"
$GITHUB_URL = "https://github.com/skyfireitdiy/Jarvis.git"
$DEST_DIR = "$env:USERPROFILE\Jarvis"
$DEFAULT_BRANCH = "main"
$DEPS_DIR_RELATIVE = "src\jarvis\jarvis_data\deps\x86_64_windows"

function Ensure-UvAvailable {
    if ($RESUME_INSTALL -and (Check-StepCompleted -StepName "uv_verified")) {
        Write-Host "`n--- 2. Check bundled uv environment (Skipped) ---" -ForegroundColor Green
        $depsDir = Join-Path $DEST_DIR $DEPS_DIR_RELATIVE
        if ((Test-Path $depsDir) -and (Get-Command uv -ErrorAction SilentlyContinue)) {
            Write-Host "✓ UV environment already verified" -ForegroundColor Cyan
            $env:Path = "$depsDir;" + $env:Path
            return
        } else {
            Write-Host "⚠ UV environment not available, will re-verify..." -ForegroundColor Yellow
        }
    }
    
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
    
    Mark-StepCompleted -StepName "uv_verified"
}

function Get-LatestTag {
    param([string]$RepoUrl)

    $tag = git ls-remote --refs --sort='-version:refname' --tags $RepoUrl 2>$null |
        Select-Object -First 1 |
        ForEach-Object { ($_ -split '/')[-1] }
    return $tag
}

function Resolve-SourceReference {
    $script:SOURCE_REF = Get-LatestTag -RepoUrl $GITHUB_URL
    if ($script:SOURCE_REF) {
        $script:SOURCE_URL = $GITHUB_URL
        return
    }

    $script:SOURCE_REF = Get-LatestTag -RepoUrl $GITEE_URL
    if ($script:SOURCE_REF) {
        $script:SOURCE_URL = $GITEE_URL
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
    if ($RESUME_INSTALL -and (Check-StepCompleted -StepName "source_downloaded")) {
        Write-Host "`n--- 1. Download Jarvis source code (Skipped) ---" -ForegroundColor Green
        if ((Test-Path $DEST_DIR) -and (Test-Path "$DEST_DIR\.git")) {
            Write-Host "✓ Source directory already exists: $DEST_DIR" -ForegroundColor Cyan
            return
        } else {
            Write-Host "⚠ Source directory not found, will re-download..." -ForegroundColor Yellow
        }
    }
    
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
        
        Mark-StepCompleted -StepName "source_downloaded"
        return
    }

    Write-Host "Cloning source code to $DEST_DIR..." -ForegroundColor Yellow
    try {
        git clone --depth 1 --branch $script:SOURCE_REF $script:SOURCE_URL $DEST_DIR
        
        Mark-StepCompleted -StepName "source_downloaded"
        return
    }
    catch {
        if ($script:SOURCE_URL -ne $GITEE_URL) {
            $script:SOURCE_URL = $GITEE_URL
            Write-Host "GitHub download failed, retrying from Gitee..." -ForegroundColor Yellow
            git clone --depth 1 --branch $script:SOURCE_REF $script:SOURCE_URL $DEST_DIR
            return
        }

        Write-Host "Source download failed, please check your network connection." -ForegroundColor Red
        exit 1
    }
}

function Install-Tools {
    if ($RESUME_INSTALL -and (Check-StepCompleted -StepName "tools_installed")) {
        Write-Host "`n--- 3. Install Jarvis from source (Skipped) ---" -ForegroundColor Green
        if (Get-Command jarvis -ErrorAction SilentlyContinue) {
            Write-Host "✓ Jarvis already installed" -ForegroundColor Cyan
            return
        } else {
            Write-Host "⚠ Jarvis command not found, will re-install..." -ForegroundColor Yellow
        }
    }
    
    Write-Host "`n--- 3. Install Jarvis from source ---" -ForegroundColor Green
    Set-Location $DEST_DIR
    uv tool install -e . --python 3.12
    uv tool install playwright
    uv tool install ddgr
    
    Write-Host "`n--- Update shell environment configuration ---" -ForegroundColor Green
    uv tool update-shell
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Note: If you need to configure manually, please run: uv tool update-shell" -ForegroundColor Yellow
    }
    
    Mark-StepCompleted -StepName "tools_installed"
}

# ===== 主执行流程 =====
Init-StatusFile
Show-InstallStatus

# 如果选择不恢复且已有部分完成，清理状态文件
if (-not $RESUME_INSTALL -and (Test-Path $INSTALL_STATUS_FILE)) {
    Write-Host "清理之前的安装状态..." -ForegroundColor Cyan
    Remove-Item $INSTALL_STATUS_FILE -Force
}

Prepare-SourceTree
Ensure-UvAvailable
Install-Tools

# 安装成功，清理状态文件
Cleanup-StatusFile

Write-Host "`n--- 4. Installation complete! ---" -ForegroundColor Green
Write-Host "Jarvis has been globally installed successfully! You can now use the jarvis command directly." -ForegroundColor Cyan
Write-Host "Installed extra tools: playwright, ddgr" -ForegroundColor Cyan
Write-Host "Source directory: $DEST_DIR" -ForegroundColor Cyan
