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

# Define repo URL and destination directory
$REPO_URL = "https://github.com/skyfireitdiy/Jarvis"
$DEST_DIR = "$env:USERPROFILE\Jarvis"
$VENV_DIR = "$DEST_DIR\.venv"

Write-Host "`n--- 2. Clone or update Jarvis repository ---" -ForegroundColor Green
if (Test-Path $DEST_DIR) {
    Write-Host "Directory $DEST_DIR exists, checking for updates..."
    Push-Location $DEST_DIR
    $status = git status --porcelain
    if ($status) {
        $choice = Read-Host "Detected uncommitted changes in '$DEST_DIR', discard changes and update? [y/N]"
        if ($choice -eq 'y' -or $choice -eq 'Y') {
            Write-Host "Discarding changes..."
            git checkout .
            Write-Host "Pulling latest code..."
            git pull
        }
        else {
            Write-Host "Skipping update to preserve uncommitted changes."
        }
    }
    else {
        Write-Host "Pulling latest code..."
        git pull
    }
    Pop-Location
}
else {
    Write-Host "Cloning repository to $DEST_DIR..."
    git clone $REPO_URL $DEST_DIR
}

Write-Host "`n--- 3. Set up virtual environment and install Jarvis ---" -ForegroundColor Green
Set-Location $DEST_DIR

if (-not (Test-Path $VENV_DIR)) {
    Write-Host "Creating virtual environment in $VENV_DIR..."
    uv venv
}
else {
    Write-Host "Virtual environment $VENV_DIR already exists."
}

Write-Host "Installing project and dependencies using uv..."

$choice = Read-Host "Install RAG features? (This will install heavy dependencies like PyTorch) [y/N]"
switch ($choice) {
    { $_ -eq 'y' -or $_ -eq 'Y' } {
        Write-Host "Installing core features and RAG dependencies..."
        uv pip install '.[rag]'
    }
    default {
        Write-Host "Installing core features..."
        uv pip install .
    }
}

Write-Host "`n--- 4. Initialize Jarvis ---" -ForegroundColor Green
$CONFIG_FILE = "$env:USERPROFILE\.jarvis\config.yaml"
if (Test-Path $CONFIG_FILE) {
    Write-Host "Configuration file $CONFIG_FILE exists, skipping initialization."
}
else {
    Write-Host "Running 'jarvis' to generate configuration file..."
    & "$VENV_DIR\Scripts\jarvis.exe"
}

Write-Host "`n--- 5. Installation and initialization complete! ---" -ForegroundColor Green
Write-Host "Run the following command to activate virtual environment:" -ForegroundColor Yellow
Write-Host "  $VENV_DIR\Scripts\Activate.ps1"
Write-Host ""
Write-Host "After activation, you can use the 'jarvis' command."
