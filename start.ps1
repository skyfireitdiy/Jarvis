#!/usr/bin/env pwsh
# Windows PowerShell startup script

# Get the script directory as the project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = $ScriptDir

Write-Host "Starting Jarvis gateway and frontend..."
Write-Host "Project root: $ProjectRoot"

# Check Python environment
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "Error: Python was not found" -ForegroundColor Red
    exit 1
}

# Check npm environment
$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmCmd) {
    Write-Host "Error: npm was not found" -ForegroundColor Red
    exit 1
}

# Check whether the gateway password environment variable is set
$gatewayPasswordArgs = @()
if ($env:JARVIS_GATEWAY_PASSWORD) {
    Write-Host "Detected gateway password environment variable"
    $gatewayPasswordArgs = @("--gateway-password", $env:JARVIS_GATEWAY_PASSWORD)
}

# Check gateway host and port environment variables
$gatewayHost = if ($env:JARVIS_GATEWAY_HOST) { $env:JARVIS_GATEWAY_HOST } else { "127.0.0.1" }
$gatewayPort = if ($env:JARVIS_GATEWAY_PORT) { $env:JARVIS_GATEWAY_PORT } else { "8000" }

# Check frontend host and port environment variables
$frontendHost = if ($env:JARVIS_FRONTEND_HOST) { $env:JARVIS_FRONTEND_HOST } else { "127.0.0.1" }
$frontendPort = if ($env:JARVIS_FRONTEND_PORT) { $env:JARVIS_FRONTEND_PORT } else { "5173" }

# Start gateway in the background
Write-Host "Starting gateway service..."
$gatewayArgs = @("--host", $gatewayHost, "--port", $gatewayPort) + $gatewayPasswordArgs
$gatewayProcess = Start-Process -FilePath "jwg" -ArgumentList $gatewayArgs -PassThru -WindowStyle Hidden

Write-Host "Gateway started (PID: $($gatewayProcess.Id))"

# Wait for the gateway to start
Write-Host "Waiting for gateway service to become ready..."
Start-Sleep -Seconds 5

# Start frontend in preview mode
Write-Host "Starting frontend preview service..."
Set-Location "$ProjectRoot\frontend"

# Install frontend dependencies
Write-Host "Installing frontend dependencies..."
npm install
Write-Host "Frontend dependencies installed"

# Build frontend production bundle
Write-Host "Building frontend production bundle..."
npm run build
Write-Host "Frontend production build completed"

$frontendProcess = Start-Process -FilePath "npm" -ArgumentList "run","preview","--","--host","$frontendHost","--port","$frontendPort" -PassThru

Write-Host "Frontend preview service started (PID: $($frontendProcess.Id))"
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Jarvis services are fully started" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Gateway URL: http://$gatewayHost:$gatewayPort"
Write-Host "Frontend URL: http://$frontendHost:$frontendPort"
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Tip: Press Ctrl+C to stop all services"
Write-Host ""

# Capture exit signal and clean up background processes
$cleanup = {
    Write-Host ""
    Write-Host "Stopping services..."
    if ($gatewayProcess -and !$gatewayProcess.HasExited) {
        Stop-Process -Id $gatewayProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProcess -and !$frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    exit 0
}

# Register Ctrl+C handling
[Console]::TreatControlCAsInput = $false
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action $cleanup

# Wait for processes to exit
try {
    while (!$frontendProcess.HasExited -and !$gatewayProcess.HasExited) {
        Start-Sleep -Milliseconds 100
    }
} finally {
    & $cleanup
}
