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
$VENV_DIR = "$DEST_DIR\.venv"

Write-Host "`n--- 2. Select installation method ---" -ForegroundColor Green
Write-Host "Please select installation method:"
Write-Host "  1) Direct install (recommended) - Fast and simple, no source code download"
Write-Host "  2) Clone install - Download source code locally for viewing and modification"
$choice = Read-Host "Please enter your choice [1/2, default 1]"
$INSTALL_TYPE = "direct"
switch ($choice) {
    "2" {
        $INSTALL_TYPE = "clone"
        Write-Host "Selected: Clone install (source will be downloaded to $DEST_DIR)" -ForegroundColor Yellow
    }
    default {
        Write-Host "Selected: Direct install (fast, no source code)" -ForegroundColor Yellow
    }
}

Write-Host "`n--- 3. Clone or update Jarvis repository ---" -ForegroundColor Green
if ($INSTALL_TYPE -eq "clone") {
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
}

Write-Host "`n--- 4. Globally install Jarvis ---" -ForegroundColor Green

Write-Host "Installing project and dependencies using uv globally..."

$ragChoice = Read-Host "Install RAG features? (This will install heavy dependencies like PyTorch) [y/N]"

switch ($INSTALL_TYPE) {
    "clone" {
        Set-Location $DEST_DIR
        switch ($ragChoice) {
            { $_ -eq 'y' -or $_ -eq 'Y' } {
                Write-Host "Installing core features and RAG dependencies from local..."
                uv tool install '.[rag]'
            }
            default {
                Write-Host "Installing core features from local..."
                uv tool install .
            }
        }
    }
    "direct" {
        switch ($ragChoice) {
            { $_ -eq 'y' -or $_ -eq 'Y' } {
                Write-Host "Installing core features and RAG dependencies from repository..."
                # Try Gitee first, fallback to GitHub
                try {
                    uv tool install "git+$GITEE_URL[rag]"
                    Write-Host "Installed from Gitee successfully" -ForegroundColor Green
                }
                catch {
                    Write-Host "Gitee installation failed, trying from GitHub..." -ForegroundColor Yellow
                    try {
                        uv tool install "git+$GITHUB_URL[rag]"
                        Write-Host "Installed from GitHub successfully" -ForegroundColor Green
                    }
                    catch {
                        Write-Host "GitHub installation also failed, please check network connection." -ForegroundColor Red
                        exit 1
                    }
                }
            }
            default {
                Write-Host "Installing core features from repository..."
                # Try Gitee first, fallback to GitHub
                try {
                    uv tool install "git+$GITEE_URL"
                    Write-Host "Installed from Gitee successfully" -ForegroundColor Green
                }
                catch {
                    Write-Host "Gitee installation failed, trying from GitHub..." -ForegroundColor Yellow
                    try {
                        uv tool install "git+$GITHUB_URL"
                        Write-Host "Installed from GitHub successfully" -ForegroundColor Green
                    }
                    catch {
                        Write-Host "GitHub installation also failed, please check network connection." -ForegroundColor Red
                        exit 1
                    }
                }
            }
        }
    }
}

Write-Host "`n--- 5. Installation complete! ---" -ForegroundColor Green
switch ($INSTALL_TYPE) {
    "clone" {
        Write-Host "Jarvis has been globally installed successfully! You can now use the jarvis command directly."
        Write-Host "Source code has been downloaded to: $DEST_DIR"
    }
    "direct" {
        Write-Host "Jarvis has been globally installed successfully! You can now use the jarvis command directly."
        Write-Host "Note: Using direct install method, source code is not downloaded locally."
        Write-Host "To view or modify the source code, manually clone the repository: git clone $GITHUB_URL"
    }
}

Write-Host "`n--- 6. Install command completion (optional) ---" -ForegroundColor Green
Write-Host "You can install command-line auto-completion for common commands to improve efficiency."
$choice = Read-Host "Would you like to install command-line auto-completion? [y/N]"
if ($choice -eq 'y' -or $choice -eq 'Y') {
    Write-Host "Installing auto-completion..."

    # Install completion for all tools
    $tools = @("jvs", "jvsd", "ja", "jca", "jcad", "jcr", "jgc", "jgs", "jsec", "jc2r", "jrg", "jpm", "jma", "jcfg", "jqc", "jt", "jm", "jss", "jst", "jmo")
    foreach ($tool in $tools) {
        Write-Host "Installing auto-completion for $tool..."
        try {
            & $tool --install-completion | Out-Null
            Write-Host "$tool auto-completion installed successfully." -ForegroundColor Green
        }
        catch {
            Write-Host "Warning: $tool auto-completion installation failed." -ForegroundColor Yellow
        }
    }

    Write-Host "Auto-completion installation has been attempted for all tools."
    Write-Host "Please restart your PowerShell session for changes to take effect."
}
else {
    Write-Host "Skipping auto-completion installation."
}
