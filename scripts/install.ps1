# Jarvis Installation Script for Windows PowerShell (in English)
# Exit on any error
$ErrorActionPreference = "Stop"

# Set Python build mirror to speed up installation
$env:UV_PYTHON_INSTALL_MIRROR = "https://python-standalone.org/mirror/astral-sh/python-build-standalone/"
Write-Host "Python installation mirror set to: $($env:UV_PYTHON_INSTALL_MIRROR)" -ForegroundColor Cyan

Write-Host "--- 1. Check or install uv environment ---" -ForegroundColor Green
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCommand) {
    Write-Host "'uv' not found, attempting automatic installation..." -ForegroundColor Yellow
    
    # Try pip3 first
    $pip3Command = Get-Command pip3 -ErrorAction SilentlyContinue
    if ($pip3Command) {
        Write-Host "Trying 'pip3 install uv --user'..."
        try {
            pip3 install uv --user
            # Re-acquire the command
            $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
            if ($uvCommand) {
                Write-Host "uv installed successfully using pip3." -ForegroundColor Green
            } else {
                # If pip installation succeeds but the command is not found in PATH, continue with irm installation
                throw "pip3 install uv succeeded but uv command not found in current session's PATH."
            }
        } catch {
            Write-Host "pip3 installation failed or not found in PATH, falling back to irm installation..." -ForegroundColor Yellow
            try {
                irm https://astral.sh/uv/install.ps1 | iex
            } catch {
                # Ignore errors and let the final check handle failures
            }
        }
    } else {
        Write-Host "pip3 not found, using irm to install uv..." -ForegroundColor Yellow
        try {
            irm https://astral.sh/uv/install.ps1 | iex
        } catch {
            # Ignore errors and let the final check handle failures
        }
    }
    
    # Check again if uv was installed successfully
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCommand) {
        Write-Host "Error: 'uv' automatic installation failed." -ForegroundColor Red
        Write-Host "Please visit https://github.com/astral-sh/uv#installation to install manually and try again." -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "uv is already installed."
}
Write-Host "Found uv: $(uv --version)"

# Define repo URLs and destination directory
# Try Gitee mirror first (faster in China), fallback to GitHub
$GITEE_URL = "https://gitee.com/skyfireitdiy/Jarvis.git"
$GITHUB_URL = "https://github.com/skyfireitdiy/Jarvis.git"
$DEST_DIR = "$env:USERPROFILE\Jarvis"

Write-Host "`n--- 2. Clone or update Jarvis repository ---" -ForegroundColor Green
if (Test-Path $DEST_DIR) {
    Write-Host "Directory $DEST_DIR exists" -ForegroundColor Yellow
    
    # Check if it's a git repository
    if (Test-Path "$DEST_DIR\.git") {
        Write-Host "Detected existing Jarvis source code repository" -ForegroundColor Cyan
        Push-Location $DEST_DIR
        
        # Check for uncommitted changes
        $status = git status --porcelain
        if ($status) {
            $choice = Read-Host "Detected uncommitted changes in '$DEST_DIR', discard changes and update? [y/N]"
            if ($choice -eq 'y' -or $choice -eq 'Y') {
                Write-Host "Discarding changes..." -ForegroundColor Yellow
                git checkout .
                Write-Host "Pulling latest code..." -ForegroundColor Yellow
                git pull
            }
            else {
                Write-Host "Keeping uncommitted changes, skipping update." -ForegroundColor Yellow
            }
        }
        else {
            Write-Host "Pulling latest code..." -ForegroundColor Yellow
            git pull
        }
        Pop-Location
    }
    else {
        Write-Host "Warning: '$DEST_DIR' exists but is not a git repository" -ForegroundColor Red
        Write-Host "Please manually backup or delete this directory and run the installer again," -ForegroundColor Yellow
        Write-Host "or run 'uv tool install -e .' in that directory directly." -ForegroundColor Yellow
        exit 1
    }
}
else {
    Write-Host "Cloning repository to $DEST_DIR..." -ForegroundColor Yellow
    # Try Gitee mirror first, fallback to GitHub
    try {
        git clone $GITEE_URL $DEST_DIR
        Write-Host "Gitee mirror clone successful" -ForegroundColor Green
    }
    catch {
        Write-Host "Gitee mirror clone failed, trying from GitHub..." -ForegroundColor Yellow
        try {
            git clone $GITHUB_URL $DEST_DIR
            Write-Host "GitHub clone successful" -ForegroundColor Green
        }
        catch {
            Write-Host "GitHub clone also failed, please check network connection or download manually." -ForegroundColor Red
            exit 1
        }
    }
}

Write-Host "`n--- 3. Install Jarvis from source ---" -ForegroundColor Green
Set-Location $DEST_DIR
Write-Host "Installing project using uv from source..." -ForegroundColor Yellow
uv tool install -e .

Write-Host "`n--- 4. Installation complete! ---" -ForegroundColor Green
Write-Host "Jarvis has been globally installed successfully! You can now use the jarvis command directly." -ForegroundColor Cyan
Write-Host "Source directory: $DEST_DIR" -ForegroundColor Cyan
