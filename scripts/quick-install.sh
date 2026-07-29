#!/bin/bash

# Jarvis 极简安装脚本
# 支持自动安装依赖工具和自动升级

set -e

# ===== 配置 =====
GITHUB_URL="https://github.com/skyfireitdiy/Jarvis.git"
GITEE_URL="https://gitee.com/skyfireitdiy/Jarvis.git"
DEST_DIR="$HOME/Jarvis"
DEFAULT_BRANCH="main"

# 镜像配置（国内用户加速）
export UV_PYTHON_INSTALL_MIRROR="https://python-standalone.org/mirror/astral-sh/python-build-standalone/"
export UV_INDEX_URL="https://pypi.mirrors.ustc.edu.cn/simple/"

# ===== 颜色输出 =====
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ===== 检测系统 =====
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Linux) PLATFORM="unknown-linux-gnu" ;;
    Darwin) PLATFORM="apple-darwin" ;;
    *) echo_error "不支持的操作系统: $OS"; exit 1 ;;
esac

case "$ARCH" in
    x86_64) ARCH_TYPE="x86_64" ;;
    aarch64|arm64) ARCH_TYPE="aarch64" ;;
    *) echo_error "不支持的架构: $ARCH"; exit 1 ;;
esac

echo_info "检测到系统: $OS $ARCH"

# ===== 安装 uv（必须） =====
install_uv() {
    if command -v uv &> /dev/null; then
        echo_info "uv 已安装: $(uv --version)"
        return 0
    fi

    echo_info "正在安装 uv..."
    
    # 尝试官方安装脚本
    if curl -LsSf https://astral.sh/uv/install.sh | sh 2>/dev/null; then
        export PATH="$HOME/.local/bin:$PATH"
        echo_info "uv 安装成功"
        return 0
    fi

    # 备用：手动下载
    echo_warn "官方安装失败，尝试备用方式..."
    local UV_URL="https://github.com/astral-sh/uv/releases/latest/download/uv-${ARCH_TYPE}-${PLATFORM}.tar.gz"
    local TEMP_DIR=$(mktemp -d)
    
    if curl -L "$UV_URL" | tar -xzf - -C "$TEMP_DIR" 2>/dev/null; then
        mkdir -p "$HOME/.local/bin"
        mv "$TEMP_DIR"/uv-* "$HOME/.local/bin/uv" 2>/dev/null || true
        chmod +x "$HOME/.local/bin/uv"
        export PATH="$HOME/.local/bin:$PATH"
        echo_info "uv 安装成功（备用方式）"
        rm -rf "$TEMP_DIR"
        return 0
    fi

    echo_error "uv 安装失败，请手动安装: https://docs.astral.sh/uv/"
    return 1
}

# ===== 安装可选工具 =====
install_optional_tools() {
    local tools=("rg:ripgrep" "fd:fd-find" "fzf:fzf" "tmux:tmux" "tree:tree")
    
    echo ""
    echo_info "可选工具安装（提升使用体验）"
    echo "以下工具可提升 Jarvis 使用体验，是否安装？"
    echo "  - rg (ripgrep): 快速搜索工具"
    echo "  - fd: 快速文件查找"
    echo "  - fzf: 模糊搜索工具"
    echo "  - tmux: 终端复用"
    echo "  - tree: 目录树显示"
    echo ""
    read -p "安装可选工具？[Y/n]: " install_choice
    
    if [[ ! "$install_choice" =~ ^[Nn]$ ]]; then
        echo_info "正在安装可选工具..."
        
        if command -v apt-get &> /dev/null; then
            sudo apt-get update -qq && sudo apt-get install -y -qq ripgrep fd-find fzf tmux tree 2>/dev/null || true
        elif command -v brew &> /dev/null; then
            brew install ripgrep fd fzf tmux tree 2>/dev/null || true
        elif command -v yum &> /dev/null; then
            sudo yum install -y -q ripgrep fd-find fzf tmux tree 2>/dev/null || true
        else
            echo_warn "未检测到包管理器，跳过可选工具安装"
        fi
        
        echo_info "可选工具安装完成"
    fi
}

# ===== 获取最新版本 =====
get_latest_tag() {
    git ls-remote --refs --sort='-version:refname' --tags "$GITHUB_URL" 2>/dev/null | head -n 1 | awk -F/ '{print $NF}'
}

# ===== 克隆或更新源码 =====
prepare_source() {
    local tag=$(get_latest_tag)
    local source_url="$GITHUB_URL"
    local ref="${tag:-$DEFAULT_BRANCH}"
    
    echo_info "目标版本: $ref"
    
    if [ -d "$DEST_DIR/.git" ]; then
        echo_info "检测到已有仓库，正在更新..."
        cd "$DEST_DIR"
        git fetch --depth 1 origin "$ref" 2>/dev/null || git fetch origin 2>/dev/null
        git checkout -f "$ref" 2>/dev/null || git checkout -f "origin/$ref" 2>/dev/null
        echo_info "源码更新完成"
    else
        echo_info "正在克隆源码到 $DEST_DIR..."
        rm -rf "$DEST_DIR"
        
        if git clone --depth 1 --branch "$ref" "$source_url" "$DEST_DIR" 2>/dev/null; then
            echo_info "源码克隆成功"
        else
            echo_warn "GitHub 克隆失败，尝试 Gitee..."
            rm -rf "$DEST_DIR"
            git clone --depth 1 --branch "$ref" "$GITEE_URL" "$DEST_DIR" 2>/dev/null || {
                echo_error "源码克隆失败，请检查网络连接"
                exit 1
            }
        fi
    fi
}

# ===== 安装 Jarvis =====
install_jarvis() {
    cd "$DEST_DIR"
    
    echo_info "正在安装 Jarvis (Python 3.12)..."
    uv tool install -e . --python 3.12 || {
        echo_error "Jarvis 安装失败"
        exit 1
    }
    
    # 更新 shell 环境
    uv tool update-shell 2>/dev/null || true
    
    echo_info "Jarvis 安装完成"
}

# ===== 验证安装 =====
verify_installation() {
    export PATH="$HOME/.local/bin:$PATH"
    
    if command -v jarvis &> /dev/null; then
        echo_info "✓ Jarvis 已安装: $(jarvis --version 2>&1 || echo '未知版本')"
    else
        echo_warn "jarvis 命令未找到，请执行: source ~/.bashrc 或重新打开终端"
    fi
}

# ===== 主流程 =====
main() {
    echo ""
    echo "========================================"
    echo "  Jarvis AI 助手 - 极简安装"
    echo "========================================"
    echo ""
    
    # 检查前置条件
    command -v git &> /dev/null || { echo_error "需要 git，请先安装"; exit 1; }
    command -v curl &> /dev/null || { echo_error "需要 curl，请先安装"; exit 1; }
    
    # 执行安装
    install_uv || exit 1
    prepare_source
    install_jarvis
    install_optional_tools
    verify_installation
    
    echo ""
    echo "========================================"
    echo "✓ 安装完成！"
    echo "========================================"
    echo "安装位置: $DEST_DIR"
    echo ""
    echo "快速开始:"
    echo "  1. 如 jarvis 命令不可用，执行: source ~/.bashrc"
    echo "  2. 启动 Jarvis: jarvis"
    echo "  3. 升级 Jarvis: cd $DEST_DIR && git pull && uv tool install -e . --python 3.12"
    echo ""
    echo "========================================"
}

main "$@"
