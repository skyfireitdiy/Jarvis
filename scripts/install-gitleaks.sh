#!/usr/bin/env bash
# 安装 Gitleaks 凭据扫描器（用户级，无需 sudo）。
#
# Gitleaks 是提交前钩子 .githooks/pre-commit 的首选扫描器；未安装时
# 钩子会自动降级到自研轻量扫描器（规则较少）。本脚本用于补齐 Gitleaks。
#
# 用法：
#   bash scripts/install-gitleaks.sh          # 安装最新版
#   GITLEAKS_VERSION=8.30.1 bash scripts/install-gitleaks.sh   # 指定版本
#
# 安装位置：$HOME/.local/bin/gitleaks（若该目录在 PATH 中，安装后即可用）
set -euo pipefail

VERSION="${GITLEAKS_VERSION:-8.30.1}"
INSTALL_DIR="${GITLEAKS_INSTALL_DIR:-$HOME/.local/bin}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# 解析操作系统与架构
case "$(uname -s)" in
    Linux)  OS="linux" ;;
    Darwin) OS="darwin" ;;
    *) echo "错误：不支持的操作系统 $(uname -s)" >&2; exit 1 ;;
esac
case "$(uname -m)" in
    x86_64|amd64)  ARCH="x64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    armv7l)        ARCH="armv7" ;;
    armv6l)        ARCH="armv6" ;;
    *) echo "错误：不支持的架构 $(uname -m)" >&2; exit 1 ;;
esac

URL="https://github.com/gitleaks/gitleaks/releases/download/v${VERSION}/gitleaks_${VERSION}_${OS}_${ARCH}.tar.gz"
echo "下载 Gitleaks v${VERSION} (${OS}/${ARCH}) ..."
echo "  $URL"

curl -fSL --retry 3 -o "$TMP_DIR/gitleaks.tar.gz" "$URL"
tar -xzf "$TMP_DIR/gitleaks.tar.gz" -C "$TMP_DIR"

mkdir -p "$INSTALL_DIR"
install -m 0755 "$TMP_DIR/gitleaks" "$INSTALL_DIR/gitleaks"

"$INSTALL_DIR/gitleaks" version

echo ""
echo "✅ 已安装到 $INSTALL_DIR/gitleaks"
if ! echo ":$PATH:" | grep -q ":$INSTALL_DIR:"; then
    echo "⚠️  注意：$INSTALL_DIR 不在 PATH 中。"
    echo "   请将以下一行加入 ~/.bashrc（或 ~/.zshrc）后重新登录："
    echo "   export PATH=\"$INSTALL_DIR:\$PATH\""
    echo "   或直接运行： bash scripts/install-git-hooks.sh 后手动指定 gitleaks 路径。"
fi
echo "   提交前钩子将自动检测并使用 gitleaks。"
