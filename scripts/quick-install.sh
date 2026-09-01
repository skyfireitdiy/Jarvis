#!/bin/bash

# Jarvis 极简安装脚本
# 支持自动安装依赖工具和自动升级
#
# 国内用户拉取脚本（GitHub raw 可能超时）：
#   bash -c "$(curl -fsSL https://gitee.com/skyfireitdiy/Jarvis/raw/main/scripts/quick-install.sh)"

set -e

# ===== 配置 =====
GITHUB_URL="https://github.com/skyfireitdiy/Jarvis.git"
GITEE_URL="https://gitee.com/skyfireitdiy/Jarvis.git"
DEST_DIR="$HOME/Jarvis"
DEFAULT_BRANCH="main"

# 镜像配置（国内用户加速）
export UV_PYTHON_INSTALL_MIRROR="https://python-standalone.org/mirror/astral-sh/python-build-standalone/"
export UV_DEFAULT_INDEX="https://mirrors.aliyun.com/pypi/simple/"
export UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple/"
# 限制并行下载数，避免触发远端源限流（403）
export UV_CONCURRENT_DOWNLOADS=4

# ===== 颜色输出 =====
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ===== 断点续装状态标记 =====
STATE_FILE="$HOME/.jarvis/.install_state"

set_state() {
	mkdir -p "$(dirname "$STATE_FILE")"
	echo "$1" >>"$STATE_FILE"
}

check_state() {
	[ -f "$STATE_FILE" ] && grep -q "^$1$" "$STATE_FILE"
}

clear_state() {
	rm -f "$STATE_FILE"
}

# ===== 检测系统 =====
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
Linux) PLATFORM="unknown-linux-gnu" ;;
Darwin) PLATFORM="apple-darwin" ;;
*)
	echo_error "不支持的操作系统: $OS"
	exit 1
	;;
esac

case "$ARCH" in
x86_64) ARCH_TYPE="x86_64" ;;
aarch64 | arm64) ARCH_TYPE="aarch64" ;;
*)
	echo_error "不支持的架构: $ARCH"
	exit 1
	;;
esac

echo_info "检测到系统: $OS $ARCH"

# ===== 安装 uv（必须） =====
install_uv() {
	if check_state "uv"; then
		echo_info "uv 已安装，跳过"
		return 0
	fi

	if command -v uv &>/dev/null; then
		echo_info "uv 已安装: $(uv --version)"
		return 0
	fi

	echo_info "正在安装 uv..."

	# 尝试多个安装源：国内公益镜像 → 官方
	local UV_INSTALL_URLS=(
		"https://uv.agentsmirror.com/install-cn.sh"
		"https://astral.sh/uv/install.sh"
	)

	for url in "${UV_INSTALL_URLS[@]}"; do
		echo_info "尝试安装源: $url"
		if curl -LsSf "$url" -o /tmp/uv-install.sh 2>/dev/null && sh /tmp/uv-install.sh 2>/dev/null; then
			export PATH="$HOME/.local/bin:$PATH"
			echo_info "uv 安装成功"
			rm -f /tmp/uv-install.sh
			return 0
		fi
		rm -f /tmp/uv-install.sh
		echo_warn "安装源失败，尝试下一个..."
	done

	# 备用：手动下载二进制（多源重试）
	echo_warn "安装脚本方式失败，尝试手动下载..."
	local TEMP_DIR=$(mktemp -d)
	local UV_DOWNLOAD_URLS=(
		"https://uv.agentsmirror.com/github/astral-sh/uv/releases/download/latest/uv-${ARCH_TYPE}-${PLATFORM}.tar.gz"
		"https://github.com/astral-sh/uv/releases/latest/download/uv-${ARCH_TYPE}-${PLATFORM}.tar.gz"
	)

	for url in "${UV_DOWNLOAD_URLS[@]}"; do
		echo_info "尝试下载: $url"
		if curl -L "$url" | tar -xzf - -C "$TEMP_DIR" 2>/dev/null; then
			mkdir -p "$HOME/.local/bin"
			mv "$TEMP_DIR"/uv-* "$HOME/.local/bin/uv" 2>/dev/null || true
			chmod +x "$HOME/.local/bin/uv"
			export PATH="$HOME/.local/bin:$PATH"
			echo_info "uv 安装成功（手动下载方式）"
			rm -rf "$TEMP_DIR"
			return 0
		fi
		echo_warn "下载源失败，尝试下一个..."
	done

	rm -rf "$TEMP_DIR"
	echo_error "uv 安装失败，请手动安装: https://docs.astral.sh/uv/"
	return 1
}

# ===== 安装可选工具 =====
install_optional_tools() {
	if check_state "optional_tools"; then
		echo_info "可选工具已安装，跳过"
		return 0
	fi

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

		if command -v apt-get &>/dev/null; then
			sudo apt-get update -qq && sudo apt-get install -y -qq ripgrep fd-find fzf tmux tree 2>/dev/null || true
		elif command -v pacman &>/dev/null; then
			sudo pacman -Sy --noconfirm 2>/dev/null || true
			sudo pacman -S --noconfirm --needed ripgrep fd fzf tmux tree 2>/dev/null || true
		elif command -v brew &>/dev/null; then
			brew install ripgrep fd fzf tmux tree 2>/dev/null || true
		elif command -v yum &>/dev/null; then
			sudo yum install -y -q ripgrep fd-find fzf tmux tree 2>/dev/null || true
		else
			echo_warn "未检测到包管理器，跳过可选工具安装"
		fi

		set_state "optional_tools"
		echo_info "可选工具安装完成"
	fi
}

# ===== 获取最新版本 =====
get_latest_tag() {
	git ls-remote --refs --sort='-version:refname' --tags "$GITHUB_URL" 2>/dev/null | head -n 1 | awk -F/ '{print $NF}'
}

# ===== 克隆或更新源码 =====
prepare_source() {
	if check_state "source"; then
		echo_info "源码已就绪，跳过"
		return 0
	fi

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
		# 源码更新后需重新安装 Jarvis
		if check_state "jarvis"; then
			echo_warn "源码已更新，将重新安装 Jarvis"
			sed -i '/^jarvis$/d' "$STATE_FILE"
		fi
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
	if check_state "jarvis"; then
	echo_info "Jarvis 已安装，跳过"
	return 0
	fi

	# 多源重试：阿里云 → 清华 → 官方
	local PYPI_INDEXES=(
	"https://mirrors.aliyun.com/pypi/simple/"
	"https://pypi.tuna.tsinghua.edu.cn/simple"
	"https://pypi.org/simple/"
	)

	local INSTALL_OK=0

# 源码安装模式
cd "$DEST_DIR"
echo_info "正在从源码安装 Jarvis (Python 3.12)..."

for index in "${PYPI_INDEXES[@]}"; do
	echo_info "尝试 PyPI 源: $index"
	if uv tool install -e . --python 3.12 --default-index "$index"; then
		INSTALL_OK=1
		break
	fi
	echo_warn "PyPI 源失败，尝试下一个..."
done

	if [ "$INSTALL_OK" -ne 1 ]; then
	echo_error "Jarvis 安装失败"
	exit 1
	fi

	# 更新 shell 环境
	uv tool update-shell 2>/dev/null || true

	set_state "jarvis"
	echo_info "Jarvis 安装完成"
	}
# ===== 验证安装 =====
verify_installation() {
	export PATH="$HOME/.local/bin:$PATH"

	if command -v jarvis &>/dev/null; then
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
	command -v git &>/dev/null || {
	echo_error "需要 git，请先安装"
	exit 1
	}
	command -v curl &>/dev/null || {
	echo_error "需要 curl，请先安装"
	exit 1
	}

	# 执行安装
	install_uv || exit 1
	set_state "uv"

prepare_source
set_state "source"

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

echo "  3. 升级 Jarvis: cd $DEST_DIR && git fetch --depth 1 && git reset --hard origin/main && uv tool install -e . --python 3.12"

	echo ""
	echo "========================================"
	}

main
