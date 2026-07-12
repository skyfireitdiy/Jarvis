#!/bin/bash

# ===== 离线安装包测试脚本 =====
# 用途：测试离线安装包的基本功能
# 使用方法：./scripts/test_offline_package.sh [离线包路径]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_DIR")" && pwd)"

# ===== 颜色输出 =====
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ===== 参数检查 =====
if [ $# -lt 1 ]; then
    log_error "用法: $0 <离线包路径>"
    log_info "示例: $0 offline_package/jarvis-offline-*.tar.gz"
    exit 1
fi

PACKAGE_FILE="$1"

if [ ! -f "$PACKAGE_FILE" ]; then
    log_error "离线包文件不存在: $PACKAGE_FILE"
    exit 1
fi

log_info "测试离线包: $PACKAGE_FILE"

# ===== 创建测试环境 =====
TEST_DIR=$(mktemp -d)
log_info "创建测试环境: $TEST_DIR"

# ===== 1. 解压测试 =====
log_info "步骤1: 测试解压..."

cd "$TEST_DIR"
tar -xzf "$PACKAGE_FILE"

if [ ! -d "jarvis-offline" ]; then
    log_error "解压失败：未找到jarvis-offline目录"
    exit 1
fi

log_info "✓ 解压成功"

# ===== 2. 文件结构检查 =====
log_info "步骤2: 检查文件结构..."

cd jarvis-offline

# 检查必需文件
REQUIRED_FILES="source install.sh README.md"
MISSING_FILES=""

for file in $REQUIRED_FILES; do
    if [ ! -e "$file" ]; then
        MISSING_FILES="$MISSING_FILES $file"
    fi
done

if [ -n "$MISSING_FILES" ]; then
    log_error "缺少必需文件: $MISSING_FILES"
    exit 1
fi

log_info "✓ 文件结构检查通过"

# ===== 3. 安装脚本检查 =====
log_info "步骤3: 检查安装脚本..."

if [ ! -x "install.sh" ]; then
    log_error "install.sh 不可执行"
    exit 1
fi

# 检查安装脚本语法
if ! bash -n install.sh; then
    log_error "install.sh 语法错误"
    exit 1
fi

log_info "✓ 安装脚本检查通过"

# ===== 4. 源码检查 =====
log_info "步骤4: 检查源码..."

if [ ! -f "source/pyproject.toml" ]; then
    log_error "缺少pyproject.toml"
    exit 1
fi

if [ ! -d "source/src" ]; then
    log_error "缺少src目录"
    exit 1
fi

log_info "✓ 源码检查通过"

# ===== 5. 虚拟环境检查 =====
log_info "步骤5: 检查虚拟环境..."

if [ -d "venv" ]; then
    VENV_SIZE=$(du -sh venv | cut -f1)
    log_info "虚拟环境大小: $VENV_SIZE"
    
    # 检查关键文件
    if [ ! -f "venv/bin/python" ]; then
        log_warn "虚拟环境中缺少python可执行文件"
    fi
    
    log_info "✓ 虚拟环境检查通过"
else
    log_warn "离线包中未包含虚拟环境"
fi

# ===== 6. 内置依赖检查 =====
log_info "步骤6: 检查内置依赖..."

if [ -d "deps" ]; then
    DEPS_SIZE=$(du -sh deps | cut -f1)
    log_info "内置依赖大小: $DEPS_SIZE"
    
    # 检查架构目录
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64) ARCH_DIR="x86_64_linux"; ;;
        aarch64|arm64) ARCH_DIR="aarch64_linux"; ;;
        *) log_warn "未知架构: $ARCH"; ;;
    esac
    
    if [ -n "$ARCH_DIR" ] && [ -d "deps/$ARCH_DIR" ]; then
        # 检查关键工具
        if [ -f "deps/$ARCH_DIR/bin/uv" ]; then
            log_info "✓ 找到uv工具"
        else
            log_warn "缺少uv工具"
        fi
    fi
    
    log_info "✓ 内置依赖检查通过"
else
    log_warn "离线包中未包含内置依赖"
fi

# ===== 7. 包大小统计 =====
log_info "步骤7: 统计包大小..."

TOTAL_SIZE=$(du -sh . | cut -f1)
log_info "离线包总大小: $TOTAL_SIZE"

# 各部分大小
echo ""
echo "各部分大小统计："
echo "----------------"
du -sh source venv python deps frontend 2>/dev/null | while read size path; do
    echo "  $path: $size"
done

# ===== 8. 清理测试环境 =====
log_info "步骤8: 清理测试环境..."

cd "$PROJECT_ROOT"
rm -rf "$TEST_DIR"

log_info "✓ 测试环境清理完成"

# ===== 测试完成 =====
log_info "========================================"
log_info "✓ 离线包测试通过！"
log_info "========================================"
log_info "离线包文件: $PACKAGE_FILE"
log_info "总大小: $TOTAL_SIZE"
log_info ""
log_info "可以使用以下命令安装："
log_info "  tar -xzf $PACKAGE_FILE"
log_info "  cd jarvis-offline"
log_info "  ./install.sh"
log_info ""
log_info "========================================"
