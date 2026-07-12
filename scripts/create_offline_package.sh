#!/bin/bash

set -e

# ===== 离线安装包创建脚本 =====
# 用途：将Jarvis及其所有依赖打包成离线安装包
# 使用方法：./scripts/create_offline_package.sh [输出目录]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_DIR")" && pwd)"
OUTPUT_DIR="${1:-$PROJECT_ROOT/offline_package}"
PACKAGE_NAME="jarvis-offline-$(date +%Y%m%d-%H%M%S).tar.gz"

# ===== 颜色输出 =====
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ===== 检测系统架构 =====
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)
        ARCH_NAME="x86_64"
        ;;
    aarch64|arm64)
        ARCH_NAME="aarch64"
        ;;
    *)
        log_error "不支持的系统架构：$ARCH"
        exit 1
        ;;
esac

log_info "检测到系统架构：$ARCH_NAME"

# ===== 创建临时打包目录 =====
TEMP_DIR=$(mktemp -d)
PACKAGE_DIR="$TEMP_DIR/jarvis-offline"
mkdir -p "$PACKAGE_DIR"

log_info "创建临时打包目录：$PACKAGE_DIR"

# ===== 1. 打包项目源码 =====
log_info "步骤1: 打包项目源码..."

# 排除不必要的文件
EXCLUDE_PATTERNS="
--exclude=.git
--exclude=.venv
--exclude=node_modules
--exclude=__pycache__
--exclude=*.pyc
--exclude=*.pyo
--exclude=.pytest_cache
--exclude=.mypy_cache
--exclude=.ruff_cache
--exclude=offline_package
--exclude=*.tar.gz
--exclude=*.zip
"

rsync -a $EXCLUDE_PATTERNS "$PROJECT_ROOT/" "$PACKAGE_DIR/source/"

log_info "源码打包完成"

# ===== 2. 打包虚拟环境 =====
log_info "步骤2: 打包虚拟环境..."

if [ -d "$PROJECT_ROOT/.venv" ]; then
    # 复制虚拟环境，但排除缓存和编译文件
    rsync -a --exclude=__pycache__ --exclude='*.pyc' --exclude='*.pyo' --exclude=.pytest_cache --exclude='*.egg-info' "$PROJECT_ROOT/.venv/" "$PACKAGE_DIR/venv/"

    # 记录原始虚拟环境路径，用于安装时修复路径引用
    echo "$PROJECT_ROOT/.venv" > "$PACKAGE_DIR/venv_origin_path.txt"

    log_info "虚拟环境打包完成 ($(du -sh "$PACKAGE_DIR/venv" | cut -f1))"
else
    log_error "未找到虚拟环境，离线安装包必须包含虚拟环境"
    exit 1
fi

# ===== 3. 打包Python独立环境 =====
log_info "步骤3: 打包Python独立环境..."

# 使用uv下载Python 3.12独立环境
if command -v uv &> /dev/null; then
    UV_BIN="uv"
else
    # 使用内置的uv
    UV_BIN="$PROJECT_ROOT/src/jarvis/jarvis_data/deps/${ARCH_NAME}_linux/bin/uv"
    if [ ! -f "$UV_BIN" ]; then
        log_error "未找到uv工具"
        exit 1
    fi
fi

log_info "使用uv: $UV_BIN"

# 下载Python 3.12独立环境
PYTHON_DIR="$PACKAGE_DIR/python"
mkdir -p "$PYTHON_DIR"

$UV_BIN python install 3.12 --install-dir "$PYTHON_DIR" --no-cache

if [ -d "$PYTHON_DIR" ]; then
    log_info "Python环境打包完成 ($(du -sh "$PYTHON_DIR" | cut -f1))"
else
    log_warn "Python环境下载失败，将在安装时从镜像下载"
fi

# ===== 4. 打包内置依赖 =====
log_info "步骤4: 打包内置依赖..."

DEPS_SRC="$PROJECT_ROOT/src/jarvis/jarvis_data/deps"
if [ -d "$DEPS_SRC" ]; then
    # 只复制当前架构的依赖目录，减小离线包体积
    mkdir -p "$PACKAGE_DIR/deps"
    if [ -d "$DEPS_SRC/${ARCH_NAME}_linux" ]; then
        rsync -a "$DEPS_SRC/${ARCH_NAME}_linux/" "$PACKAGE_DIR/deps/${ARCH_NAME}_linux/"
        log_info "内置依赖打包完成 ($(du -sh "$PACKAGE_DIR/deps" | cut -f1))"
    else
        log_warn "未找到当前架构的内置依赖目录: ${ARCH_NAME}_linux"
    fi
else
    log_warn "未找到内置依赖目录"
fi

# ===== 5. 打包前端构建产物 =====
log_info "步骤5: 打包前端构建产物..."

FRONTEND_DIST="$PROJECT_ROOT/src/jarvis/jarvis_service/frontend/dist"
if [ -d "$FRONTEND_DIST" ]; then
    mkdir -p "$PACKAGE_DIR/frontend"
    rsync -a "$FRONTEND_DIST/" "$PACKAGE_DIR/frontend/dist/"
    log_info "前端构建产物打包完成 ($(du -sh "$PACKAGE_DIR/frontend/dist" | cut -f1))"
else
    log_warn "未找到前端构建产物，跳过打包"
fi

# ===== 6. 创建安装脚本 =====
log_info "步骤6: 创建安装脚本..."

INSTALL_SCRIPT="$PACKAGE_DIR/install.sh"
cat > "$INSTALL_SCRIPT" << 'INSTALL_EOF'
#!/bin/bash

set -e

# ===== 离线安装脚本 =====
# 用途：从离线包安装Jarvis
# 使用方法：./install.sh [安装目录]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${1:-$HOME/Jarvis}"

# ===== 颜色输出 =====
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ===== 检测系统架构 =====
ARCH=$(uname -m)
case "$ARCH" in
    x86_64) ARCH_NAME="x86_64"; ;;
    aarch64|arm64) ARCH_NAME="aarch64"; ;;
    *) log_error "不支持的架构：$ARCH"; exit 1; ;;
esac

log_info "检测到系统架构：$ARCH_NAME"

# ===== 1. 解压源码 =====
log_info "步骤1: 安装源码到 $INSTALL_DIR..."

if [ -d "$INSTALL_DIR" ]; then
    log_warn "目标目录已存在，将备份旧目录"
    mv "$INSTALL_DIR" "$INSTALL_DIR.backup.$(date +%Y%m%d%H%M%S)"
fi

mkdir -p "$INSTALL_DIR"
rsync -a "$SCRIPT_DIR/source/" "$INSTALL_DIR/"

log_info "源码安装完成"

# ===== 2. 安装虚拟环境 =====
log_info "步骤2: 安装虚拟环境..."

if [ -d "$SCRIPT_DIR/venv" ]; then
    mkdir -p "$INSTALL_DIR/.venv"
    rsync -a "$SCRIPT_DIR/venv/" "$INSTALL_DIR/.venv/"

    # 修复虚拟环境路径
    cd "$INSTALL_DIR"

    # 读取原始虚拟环境路径
    ORIGIN_VENV_PATH=""
    if [ -f "$SCRIPT_DIR/venv_origin_path.txt" ]; then
        ORIGIN_VENV_PATH=$(cat "$SCRIPT_DIR/venv_origin_path.txt")
    fi

    # 如果有原始路径，替换原始路径为安装路径；否则替换解压路径
    if [ -n "$ORIGIN_VENV_PATH" ]; then
        SEARCH_PATH="$ORIGIN_VENV_PATH"
    else
        SEARCH_PATH="$SCRIPT_DIR/.venv"
    fi

    # 更新bin目录中的脚本shebang路径
    for script in .venv/bin/*; do
        if [ -f "$script" ]; then
            sed -i "s|$SEARCH_PATH|$INSTALL_DIR/.venv|g" "$script" 2>/dev/null || true
        fi
    done

    # 更新activate脚本中的VIRTUAL_ENV变量
    if [ -f ".venv/bin/activate" ]; then
        sed -i "s|VIRTUAL_ENV=.*|VIRTUAL_ENV=\"$INSTALL_DIR/.venv\"|g" ".venv/bin/activate"
    fi

    # 更新pyvenv.cfg
    if [ -f ".venv/pyvenv.cfg" ]; then
        sed -i "s|home = .*|home = $INSTALL_DIR/.venv/bin|g" ".venv/pyvenv.cfg"
    fi

    log_info "虚拟环境安装完成"
else
    log_error "离线包中未包含虚拟环境，离线安装必须包含虚拟环境"
    exit 1
fi

# ===== 3. 安装Python环境 =====
log_info "步骤3: 配置Python环境..."

if [ -d "$SCRIPT_DIR/python" ]; then
    # uv python install --install-dir 创建的目录结构为 cpython-3.12.x-linux-x86_64-gnu/bin/python3.12
    # 需要将cpython子目录内的bin/和lib/内容提升复制到.venv/对应位置
    log_info "复制Python独立环境..."
    
    # 查找cpython子目录（通配符匹配）
    CPYTHON_DIR=$(find "$SCRIPT_DIR/python" -maxdepth 1 -type d -name "cpython-*" | head -n 1)
    
    if [ -n "$CPYTHON_DIR" ] && [ -d "$CPYTHON_DIR" ]; then
        # 复制bin目录内容到.venv/bin/
        if [ -d "$CPYTHON_DIR/bin" ]; then
            mkdir -p "$INSTALL_DIR/.venv/bin"
            rsync -a "$CPYTHON_DIR/bin/" "$INSTALL_DIR/.venv/bin/" --exclude='*.pyc' --exclude='__pycache__'
        fi
        
        # 复制lib目录内容到.venv/lib/
        if [ -d "$CPYTHON_DIR/lib" ]; then
            mkdir -p "$INSTALL_DIR/.venv/lib"
            rsync -a "$CPYTHON_DIR/lib/" "$INSTALL_DIR/.venv/lib/" --exclude='*.pyc' --exclude='__pycache__'
        fi
        
        log_info "Python环境配置完成"
    else
        log_warn "未找到cpython子目录，跳过Python环境复制"
    fi
fi

# ===== 4. 安装内置依赖 =====
log_info "步骤4: 安装内置依赖..."

if [ -d "$SCRIPT_DIR/deps" ]; then
    DEPS_DEST="$INSTALL_DIR/src/jarvis/jarvis_data/deps"
    mkdir -p "$DEPS_DEST"
    rsync -a "$SCRIPT_DIR/deps/" "$DEPS_DEST/"
    
    # 将内置工具添加到PATH
    export PATH="$DEPS_DEST/${ARCH_NAME}_linux/bin:$PATH"
    log_info "内置依赖安装完成"
fi

# ===== 5. 安装前端构建产物 =====
log_info "步骤5: 安装前端构建产物..."

if [ -d "$SCRIPT_DIR/frontend/dist" ]; then
    FRONTEND_DEST="$INSTALL_DIR/src/jarvis/jarvis_service/frontend"
    mkdir -p "$FRONTEND_DEST"
    rsync -a "$SCRIPT_DIR/frontend/dist/" "$FRONTEND_DEST/dist/"
    log_info "前端构建产物安装完成"
fi

# ===== 6. 安装Jarvis =====
log_info "步骤6: 安装Jarvis到系统..."

cd "$INSTALL_DIR"

# 激活虚拟环境
source .venv/bin/activate

# 安装Jarvis（使用已存在的虚拟环境，无需下载依赖）
# 离线安装：只使用已存在的虚拟环境依赖，不尝试在线安装
pip install -e . --no-deps || {
    log_error "离线安装失败，请确保虚拟环境包含所有必需依赖"
    exit 1
}

log_info "Jarvis安装完成"

# ===== 7. 配置Shell环境 =====
log_info "步骤7: 配置Shell环境..."

# 检测当前shell
SHELL_NAME=$(basename "$SHELL")
SHELL_CONFIG=""

case "$SHELL_NAME" in
    bash) SHELL_CONFIG="$HOME/.bashrc"; ;;
    zsh) SHELL_CONFIG="$HOME/.zshrc"; ;;
    fish) SHELL_CONFIG="$HOME/.config/fish/config.fish"; ;;
    *) log_warn "未知shell类型，请手动配置"; ;;
esac

# 添加PATH配置
if [ -n "$SHELL_CONFIG" ]; then
    PATH_LINE="export PATH=\"$INSTALL_DIR/.venv/bin:\$PATH\""
    if ! grep -q "$PATH_LINE" "$SHELL_CONFIG" 2>/dev/null; then
        echo "" >> "$SHELL_CONFIG"
        echo "# Jarvis offline installation" >> "$SHELL_CONFIG"
        echo "$PATH_LINE" >> "$SHELL_CONFIG"
        log_info "已更新 $SHELL_CONFIG"
    fi
fi

# ===== 8. 验证安装 =====
log_info "步骤8: 验证安装..."

export PATH="$INSTALL_DIR/.venv/bin:$PATH"

if command -v jarvis &> /dev/null; then
    JARVIS_VERSION=$(jarvis --version 2>&1 || echo "未知版本")
    log_info "✓ Jarvis已安装：$JARVIS_VERSION"
else
    log_warn "jarvis命令未找到，请手动source配置文件"
fi

# ===== 安装完成 =====
log_info "========================================"
log_info "✓ Jarvis离线安装完成！"
log_info "========================================"
log_info "安装位置：$INSTALL_DIR"
log_info "虚拟环境：$INSTALL_DIR/.venv"
log_info ""
log_info "快速开始："
log_info "  1. 执行以下命令激活环境："
log_info "     source $SHELL_CONFIG"
log_info "     或"
log_info "     source $INSTALL_DIR/.venv/bin/activate"
log_info ""
log_info "  2. 启动Jarvis："
log_info "     jarvis"
log_info ""
log_info "========================================"
INSTALL_EOF

chmod +x "$INSTALL_SCRIPT"

log_info "安装脚本创建完成"

# ===== 7. 创建README =====
log_info "步骤7: 创建README文档..."

README_FILE="$PACKAGE_DIR/README.md"
cat > "$README_FILE" << 'README_EOF'
# Jarvis 离线安装包

## 包含内容

- **source**: Jarvis源码
- **venv**: Python虚拟环境（包含所有依赖）
- **python**: Python 3.12独立环境
- **deps**: 内置工具（uv, rg, fd, tmux等）
- **frontend**: 前端构建产物
- **install.sh**: 安装脚本

## 安装方法

1. 解压离线包：
   ```bash
   tar -xzf jarvis-offline-*.tar.gz
   cd jarvis-offline
   ```

2. 运行安装脚本：
   ```bash
   ./install.sh [安装目录]
   ```
   默认安装到 `$HOME/Jarvis`

3. 激活环境：
   ```bash
   source ~/.bashrc  # 或 source ~/.zshrc
   ```

4. 启动Jarvis：
   ```bash
   jarvis
   ```

## 系统要求

- Linux系统（x86_64或aarch64架构）
- 至少2GB可用磁盘空间
- Git（可选，用于版本管理）

## 注意事项

- 此离线包为特定架构编译，请确保架构匹配
- 安装后首次启动可能需要配置API密钥
- 如遇到问题，请查看安装日志

README_EOF

log_info "README文档创建完成"

# ===== 8. 打包压缩 =====
log_info "步骤8: 打包压缩..."

mkdir -p "$OUTPUT_DIR"
PACKAGE_FILE="$OUTPUT_DIR/$PACKAGE_NAME"

cd "$TEMP_DIR"
tar -czf "$PACKAGE_FILE" jarvis-offline

PACKAGE_SIZE=$(du -sh "$PACKAGE_FILE" | cut -f1)

log_info "离线包创建完成：$PACKAGE_FILE"
log_info "离线包大小：$PACKAGE_SIZE"

# ===== 9. 清理临时文件 =====
log_info "步骤9: 清理临时文件..."

rm -rf "$TEMP_DIR"

log_info "临时文件清理完成"

# ===== 完成 =====
log_info "========================================"
log_info "✓ 离线安装包创建成功！"
log_info "========================================"
log_info "输出文件：$PACKAGE_FILE"
log_info "包大小：$PACKAGE_SIZE"
log_info "架构：$ARCH_NAME"
log_info ""
log_info "使用方法："
log_info "  1. 将离线包传输到目标机器"
log_info "  2. 解压：tar -xzf $PACKAGE_NAME"
log_info "  3. 安装：./install.sh"
log_info ""
log_info "========================================"
