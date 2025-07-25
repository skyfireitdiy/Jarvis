#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- 1. Searching for a suitable Python interpreter (>= 3.9) ---"

# List of possible python commands to check
PYTHON_COMMANDS=("python3.12" "python3.11" "python3.10" "python3.9" "python3")
PYTHON_CMD=""

for cmd in "${PYTHON_COMMANDS[@]}"; do
    if command -v "$cmd" &> /dev/null; then
        echo "Checking version for '$cmd'..."
        VERSION_INFO=$("$cmd" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null || continue)
        MAJOR=$(echo "$VERSION_INFO" | cut -d. -f1)
        MINOR=$(echo "$VERSION_INFO" | cut -d. -f2)

        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 9 ]; then
            echo "Found suitable Python interpreter: $cmd (version $VERSION_INFO)"
            PYTHON_CMD="$cmd"
            break
        else
            echo "'$cmd' is version $VERSION_INFO, which does not meet the requirement."
        fi
    fi
done

# If no suitable python command was found, exit.
if [ -z "$PYTHON_CMD" ]; then
    echo "Error: Could not find a Python interpreter version 3.9 or higher."
    echo "Please install Python 3.9+ and ensure it's in your PATH."
    exit 1
fi

# Define repo URL and destination directory
REPO_URL="https://github.com/skyfireitdiy/Jarvis"
DEST_DIR="$HOME/Jarvis"

echo -e "\n--- 2. Cloning or updating the Jarvis repository ---"
if [ -d "$DEST_DIR" ]; then
    echo "Directory $DEST_DIR already exists. Pulling the latest changes..."
    cd "$DEST_DIR"
    git pull
else
    echo "Cloning repository to $DEST_DIR..."
    git clone "$REPO_URL" "$DEST_DIR"
fi

echo -e "\n--- 3. Installing Jarvis ---"
cd "$DEST_DIR"
echo "Installing project and dependencies from $PWD using $PYTHON_CMD..."
"$PYTHON_CMD" -m pip install .

echo -e "\n--- 4. Initializing Jarvis to generate config file ---"
# Check if jarvis is in the path, it should be after installation
# The actual executable might be in ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"
if ! command -v jarvis &> /dev/null
then
    echo "Warning: 'jarvis' command not found in PATH after installation."
    echo "Please add the Python scripts directory (e.g., ~/.local/bin) to your PATH."
    echo "Attempting to run '$PYTHON_CMD -m jarvis.main -h' as a fallback."
    "$PYTHON_CMD" -m jarvis.main -h
fi

echo -e "\n--- Installation and initialization complete! ---"
echo "You can now use the 'jarvis' command."
