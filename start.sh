#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

cd "$PROJECT_ROOT"

# 忽略 SIGUSR1 和 SIGUSR2 信号，让 jarvis-service 自己处理
trap '' SIGUSR1 SIGUSR2

exec jarvis-service
