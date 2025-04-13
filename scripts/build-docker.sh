#!/bin/bash

# Get the absolute path of the script's directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Extract version from setup.py
VERSION=$(grep -oP "(?<=version=\").*?(?=\")" "$PROJECT_ROOT/setup.py")

# Build Docker image
docker build -t jarvis-ai-assistant:$VERSION -f "$PROJECT_ROOT/Dockerfile" "$PROJECT_ROOT"

echo "Successfully built jarvis-ai-assistant:$VERSION"
