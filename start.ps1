#!/usr/bin/env pwsh
# Windows PowerShell 启动脚本

# 获取脚本所在目录作为项目根目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = $ScriptDir

Write-Host "🚀 启动 Jarvis 网关和前端..."
Write-Host "📁 项目根目录: $ProjectRoot"

# 检查 Python 环境
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "❌ 错误: 未找到 Python 环境" -ForegroundColor Red
    exit 1
}

# 检查 npm 环境
$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmCmd) {
    Write-Host "❌ 错误: 未找到 npm 环境" -ForegroundColor Red
    exit 1
}

# 检查是否设置了网关密码环境变量
$gatewayPasswordArgs = ""
if ($env:JARVIS_GATEWAY_PASSWORD) {
    Write-Host "🔐 检测到网关密码环境变量"
    $gatewayPasswordArgs = "--gateway-password $env:JARVIS_GATEWAY_PASSWORD"
}

# 检查网关 host 和 port 环境变量
$gatewayHost = if ($env:JARVIS_GATEWAY_HOST) { $env:JARVIS_GATEWAY_HOST } else { "127.0.0.1" }
$gatewayPort = if ($env:JARVIS_GATEWAY_PORT) { $env:JARVIS_GATEWAY_PORT } else { "8000" }

# 检查前端 host 和 port 环境变量
$frontendHost = if ($env:JARVIS_FRONTEND_HOST) { $env:JARVIS_FRONTEND_HOST } else { "127.0.0.1" }
$frontendPort = if ($env:JARVIS_FRONTEND_PORT) { $env:JARVIS_FRONTEND_PORT } else { "5173" }

# 启动网关（后台运行）
Write-Host "📡 启动网关服务..."
$gatewayProcess = Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","jarvis.jarvis_web_gateway.app:create_app","--host","$gatewayHost","--port","$gatewayPort","$gatewayPasswordArgs" -PassThru -WindowStyle Hidden

Write-Host "✅ 网关已启动 (PID: $($gatewayProcess.Id))"

# 等待网关启动
Write-Host "⏳ 等待网关服务就绪..."
Start-Sleep -Seconds 5

# 启动前端（开发模式）
Write-Host "🎨 启动前端服务..."
Set-Location "$ProjectRoot\frontend"

# 检查并安装前端依赖
if (-not (Test-Path "node_modules")) {
    Write-Host "📦 首次启动，安装前端依赖..."
    npm install
    Write-Host "✅ 前端依赖安装完成"
} else {
    Write-Host "✅ 前端依赖已存在，跳过安装"
}

$frontendProcess = Start-Process -FilePath "npm" -ArgumentList "run","dev","--","--host","$frontendHost","--port","$frontendPort" -PassThru

Write-Host "✅ 前端已启动 (PID: $($frontendProcess.Id))"
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "✨ Jarvis 服务已全部启动！" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "📡 网关地址: http://$gatewayHost:$gatewayPort"
Write-Host "🎨 前端地址: http://$frontendHost:$frontendPort"
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "💡 提示: 按 Ctrl+C 停止所有服务"
Write-Host ""

# 捕获退出信号，清理后台进程
$cleanup = {
    Write-Host ""
    Write-Host "🛑 正在停止服务..."
    if ($gatewayProcess -and !$gatewayProcess.HasExited) {
        Stop-Process -Id $gatewayProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProcess -and !$frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    exit 0
}

# 注册 Ctrl+C 处理
[Console]::TreatControlCAsInput = $false
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action $cleanup

# 等待进程结束
try {
    while (!$frontendProcess.HasExited -and !$gatewayProcess.HasExited) {
        Start-Sleep -Milliseconds 100
    }
} finally {
    & $cleanup
}