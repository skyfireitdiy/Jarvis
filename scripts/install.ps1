# Jarvis Installation Script for Windows PowerShell
# Exit on any error
$ErrorActionPreference = "Stop"

# 设置 Python 构建镜像以加速安装
$env:UV_PYTHON_INSTALL_MIRROR = "https://python-standalone.org/mirror/astral-sh/python-build-standalone/"
Write-Host "已设置 Python 安装镜像: $($env:UV_PYTHON_INSTALL_MIRROR)" -ForegroundColor Cyan

Write-Host "--- 1. 检查或安装 uv 环境 ---" -ForegroundColor Green
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCommand) {
    Write-Host "'uv' 未安装，正在尝试自动安装..." -ForegroundColor Yellow
    
    # 优先尝试 pip3
    $pip3Command = Get-Command pip3 -ErrorAction SilentlyContinue
    if ($pip3Command) {
        Write-Host "尝试使用 'pip3 install uv --user'..."
        try {
            pip3 install uv --user
            # 重新获取命令
            $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
            if ($uvCommand) {
                Write-Host "uv 使用 pip3 安装成功。" -ForegroundColor Green
            } else {
                # 如果pip安装后找不到命令，可能在用户路径下，我们继续尝试irm
                throw "pip3 install uv succeeded but uv command not found in current session's PATH."
            }
        } catch {
            Write-Host "pip3 安装失败或未在 PATH 中找到, 回退到 irm 安装..." -ForegroundColor Yellow
            try {
                irm https://astral.sh/uv/install.ps1 | iex
            } catch {
                # 忽略错误，让最后的检查来处理失败情况
            }
        }
    } else {
        Write-Host "未找到 pip3，使用 irm 安装 uv..." -ForegroundColor Yellow
        try {
            irm https://astral.sh/uv/install.ps1 | iex
        } catch {
            # 忽略错误，让最后的检查来处理失败情况
        }
    }
    
    # 再次检查 uv 是否成功安装
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCommand) {
        Write-Host "错误: 'uv' 自动安装失败。" -ForegroundColor Red
        Write-Host "请访问 https://github.com/astral-sh/uv#installation 手动安装后重试。" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "uv 已安装."
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
