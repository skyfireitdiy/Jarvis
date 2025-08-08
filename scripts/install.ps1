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

Write-Host "`n--- 4. Configure PowerShell Profile ---" -ForegroundColor Green
$PROFILE_FILE = $PROFILE
$ACTIVATE_COMMAND = "& `"$VENV_DIR\Scripts\Activate.ps1`""

$choice = Read-Host "Would you like to add virtual environment activation to your PowerShell profile? [y/N]"
if ($choice -eq 'y' -or $choice -eq 'Y') {
    # Create profile directory if it doesn't exist
    $profileDir = Split-Path -Parent $PROFILE_FILE
    if (-not (Test-Path $profileDir)) {
        New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    }
    
    # Check if activation command already exists in profile
    if (Test-Path $PROFILE_FILE) {
        $profileContent = Get-Content $PROFILE_FILE -Raw
        if ($profileContent -match [regex]::Escape($ACTIVATE_COMMAND)) {
            Write-Host "Virtual environment activation already exists in profile." -ForegroundColor Yellow
        }
        else {
            Add-Content -Path $PROFILE_FILE -Value "`n# Jarvis virtual environment activation`n$ACTIVATE_COMMAND"
            Write-Host "Added virtual environment activation to $PROFILE_FILE" -ForegroundColor Green
        }
    }
    else {
        Set-Content -Path $PROFILE_FILE -Value "# Jarvis virtual environment activation`n$ACTIVATE_COMMAND"
        Write-Host "Created $PROFILE_FILE with virtual environment activation" -ForegroundColor Green
    }
    Write-Host "The virtual environment will be automatically activated in new PowerShell sessions." -ForegroundColor Green
}
else {
    Write-Host "Skipping profile modification." -ForegroundColor Yellow
}

Write-Host "`n--- 5. Installation complete! ---" -ForegroundColor Green
Write-Host "To manually activate the virtual environment, run:" -ForegroundColor Yellow
Write-Host "  $VENV_DIR\Scripts\Activate.ps1"
Write-Host ""
Write-Host "After activation, you can use the 'jarvis' command."
Write-Host ""
Write-Host "To initialize Jarvis configuration, run:" -ForegroundColor Yellow
Write-Host "  jarvis"
