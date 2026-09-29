#!/usr/bin/env bash
# 安装 Jarvis 的 Git hooks（启用提交前凭据扫描防护）。
#
# 用法：
#   bash scripts/install-git-hooks.sh
#
# 每次克隆仓库后执行一次即可（core.hooksPath 是本地配置，不随仓库分发）。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d .githooks ]; then
    echo "错误：未找到 .githooks 目录，请确认在仓库根目录执行。" >&2
    exit 1
fi

# 确保 hook 脚本可执行
chmod +x .githooks/pre-commit

git config core.hooksPath .githooks

echo "✅ 已启用 Git hooks（core.hooksPath = .githooks）"
echo "   提交前将自动扫描暂存区中的疑似凭据。"
echo "   紧急绕过：JARVIS_ALLOW_SECRETS=1 git commit ..."
if ! command -v gitleaks >/dev/null 2>&1; then
    echo ""
    echo "ℹ️  未检测到 Gitleaks，提交前将使用自研轻量扫描器（规则较少）。"
    echo "   建议安装 Gitleaks 以获得更全面的检测：bash scripts/install-gitleaks.sh"
fi
