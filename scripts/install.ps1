# Jarvis Installation Script for Windows PowerShell
# Exit on any error
$ErrorActionPreference = "Stop"

Write-Host "--- 1. 检查 uv 环境 ---" -ForegroundColor Green
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCommand) {
    Write-Host "错误: 'uv' 未安装." -ForegroundColor Red
    Write-Host "请先运行以下命令安装:"
    Write-Host "powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`"" -ForegroundColor Yellow
    exit 1
}
Write-Host "发现 uv: $(uv --version)"

# Define repo URL and destination directory
$REPO_URL = "https://github.com/skyfireitdiy/Jarvis"
$DEST_DIR = "$env:USERPROFILE\Jarvis"
$VENV_DIR = "$DEST_DIR\.venv"

Write-Host "`n--- 2. 克隆或更新 Jarvis 仓库 ---" -ForegroundColor Green
if (Test-Path $DEST_DIR) {
    Write-Host "目录 $DEST_DIR 已存在，正在检查更新..."
    Push-Location $DEST_DIR
    $status = git status --porcelain
    if ($status) {
        $choice = Read-Host "检测到 '$DEST_DIR' 存在未提交的更改，是否放弃这些更改并更新？ [y/N]"
        if ($choice -eq 'y' -or $choice -eq 'Y') {
            Write-Host "正在放弃更改..."
            git checkout .
            Write-Host "正在拉取最新代码..."
            git pull
        }
        else {
            Write-Host "跳过更新以保留未提交的更改。"
        }
    }
    else {
        Write-Host "正在拉取最新代码..."
        git pull
    }
    Pop-Location
}
else {
    Write-Host "正在克隆仓库到 $DEST_DIR..."
    git clone $REPO_URL $DEST_DIR
}

Write-Host "`n--- 3. 设置虚拟环境并安装 Jarvis ---" -ForegroundColor Green
Set-Location $DEST_DIR

if (-not (Test-Path $VENV_DIR)) {
    Write-Host "正在 $VENV_DIR 创建虚拟环境..."
    uv venv
}
else {
    Write-Host "虚拟环境 $VENV_DIR 已存在."
}

Write-Host "正在使用 uv 安装项目和依赖..."

$choice = Read-Host "是否安装 RAG 功能? (这将安装 PyTorch 等较重的依赖) [y/N]"
switch ($choice) {
    { $_ -eq 'y' -or $_ -eq 'Y' } {
        Write-Host "正在安装核心功能及 RAG 依赖..."
        uv pip install '.[rag]'
    }
    default {
        Write-Host "正在安装核心功能..."
        uv pip install .
    }
}

Write-Host "`n--- 4. 初始化 Jarvis ---" -ForegroundColor Green
$CONFIG_FILE = "$env:USERPROFILE\.jarvis\config.yaml"
if (Test-Path $CONFIG_FILE) {
    Write-Host "配置文件 $CONFIG_FILE 已存在，跳过初始化。"
}
else {
    Write-Host "正在运行 'jarvis' 来生成配置文件..."
    & "$VENV_DIR\Scripts\jarvis.exe"
}

Write-Host "`n--- 5. 安装与初始化完成! ---" -ForegroundColor Green
Write-Host "请运行以下命令激活虚拟环境:" -ForegroundColor Yellow
Write-Host "  $VENV_DIR\Scripts\Activate.ps1"
Write-Host ""
Write-Host "激活后，您就可以使用 'jarvis' 命令。"
