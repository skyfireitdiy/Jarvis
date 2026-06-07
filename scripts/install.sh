#!/bin/bash

set -e

# ===== 全局变量声明 =====
GITEE_URL="https://gitee.com/skyfireitdiy/Jarvis.git"
GITHUB_URL="https://github.com/skyfireitdiy/Jarvis.git"
DEST_DIR="$HOME/Jarvis"
DEFAULT_BRANCH="main"
SOURCE_URL=""
SOURCE_REF=""

# ===== 镜像配置 =====
export UV_PYTHON_INSTALL_MIRROR="https://python-standalone.org/mirror/astral-sh/python-build-standalone/"
echo "已设置 Python 安装镜像：$UV_PYTHON_INSTALL_MIRROR"

export UV_INDEX_URL="https://pypi.mirrors.ustc.edu.cn/simple/"
echo "已设置 PyPI 镜像 (中科大): $UV_INDEX_URL"

# 检测系统架构并设置对应的依赖目录
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)
        DEPS_DIR_RELATIVE="src/jarvis/jarvis_data/deps/x86_64_linux"
        ;;
    aarch64|arm64)
        DEPS_DIR_RELATIVE="src/jarvis/jarvis_data/deps/aarch64_linux"
        ;;
    *)
        echo "错误：不支持的系统架构：$ARCH"
        echo "当前支持的架构：x86_64, aarch64"
        exit 1
        ;;
esac

# ===== 前置检查函数 =====
check_prerequisites() {
    echo -e "\n--- 0. 检查前置条件 ---"
    
    # 检查 git 是否可用
    if ! command -v git &> /dev/null; then
        echo "错误：未找到 git 命令，请先安装 git"
        exit 1
    fi
    echo "✓ git 可用：$(git --version)"
    
    # 检查磁盘空间（至少需要 1GB）
    local available_space
    available_space=$(df -P "$HOME" | awk 'NR==2 {print $4}')
    if [ "$available_space" -lt 1048576 ]; then
        echo "错误：$HOME 目录可用空间不足 1GB (当前：$((available_space/1024))MB)"
        exit 1
    fi
    echo "✓ 磁盘空间充足：$((available_space/1024))MB 可用"
    
    # 检查 DEST_DIR 父目录写权限
    local parent_dir
    parent_dir=$(dirname "$DEST_DIR")
    if [ ! -w "$parent_dir" ]; then
        echo "错误：无写入权限：$parent_dir"
        exit 1
    fi
    echo "✓ 目录权限正常：$parent_dir 可写入"
}

ensure_uv_available() {
    echo -e "\n--- 1. 检查内置 uv 环境 ---"
    
    # 注意：此函数需要在源码下载后调用，因为 deps_dir 在源码仓库中
    local deps_dir="$DEST_DIR/$DEPS_DIR_RELATIVE"
    if [ ! -d "$deps_dir" ]; then
        echo "错误：当前仓库版本未找到内置依赖目录：$deps_dir"
        echo "请确认当前平台受支持，或手动安装 uv 后重试。"
        exit 1
    fi

    export PATH="$PATH:$deps_dir"
    echo "已将内置依赖目录加入 PATH: $deps_dir"

    if ! command -v uv &> /dev/null; then
        echo "错误：未在仓库内置依赖目录中找到 uv。"
        echo "请确认当前平台受支持，或手动安装 uv 后重试。"
        exit 1
    fi

    echo "发现 uv: $(uv --version)"
}

get_latest_tag() {
    local repo_url="$1"
    git ls-remote --refs --sort='-version:refname' --tags "$repo_url" 2>/dev/null \
        | head -n 1 \
        | awk -F/ '{print $NF}'
}

resolve_source_reference() {
    local latest_tag
    latest_tag="$(get_latest_tag "$GITHUB_URL")"
    if [ -n "$latest_tag" ]; then
        SOURCE_URL="$GITHUB_URL"
        SOURCE_REF="$latest_tag"
        echo "已选择 GitHub 最新 tag: $SOURCE_REF"
        return
    fi

    latest_tag="$(get_latest_tag "$GITEE_URL")"
    if [ -n "$latest_tag" ]; then
        SOURCE_URL="$GITEE_URL"
        SOURCE_REF="$latest_tag"
        echo "已选择 Gitee 最新 tag: $SOURCE_REF"
        return
    fi

    SOURCE_URL="$GITHUB_URL"
    SOURCE_REF="$DEFAULT_BRANCH"
    echo "未找到 tag，将使用默认分支：$SOURCE_REF"
}

checkout_source_ref() {
    local source_ref="$1"
    
    # 尝试先获取 tag
    if git fetch --depth 1 origin "refs/tags/$source_ref:refs/tags/$source_ref" 2>/dev/null; then
        git checkout -f "$source_ref" 2>/dev/null && return
    fi
    
    # 回退到分支名
    if git fetch --depth 1 origin "$source_ref" 2>/dev/null; then
        git checkout -f FETCH_HEAD && return
    fi
    
    echo "错误：无法获取版本 $source_ref"
    exit 1
}

prepare_source_tree() {
    echo -e "\n--- 2. 下载 Jarvis 源码 ---"
    resolve_source_reference
    echo "目标版本：$SOURCE_REF"
    echo "下载源：$SOURCE_URL"

    if [ -d "$DEST_DIR" ] && [ ! -d "$DEST_DIR/.git" ]; then
        echo "警告：'$DEST_DIR' 存在但不是 git 仓库"
        echo "请手动备份或删除该目录后重新安装。"
        exit 1
    fi

    if [ -d "$DEST_DIR/.git" ]; then
        echo "检测到已存在 Jarvis 源码仓库，正在切换到目标版本..."
        cd "$DEST_DIR"
        if [ -n "$(git status --porcelain)" ]; then
            echo "警告：'$DEST_DIR' 存在未提交的更改"
            read -r -p "是否强制覆盖？(这将丢失未提交的更改) [y/N]: " confirm
            if [[ "$confirm" =~ ^[Yy]$ ]]; then
                git reset --hard HEAD >/dev/null 2>&1
                git clean -fd >/dev/null 2>&1
                echo "已清理未提交的更改"
            else
                echo "错误：请先手动处理未提交的更改后重试"
                exit 1
            fi
        fi
        git remote set-url origin "$SOURCE_URL"
        checkout_source_ref "$SOURCE_REF"
        return
    fi

    echo "正在浅克隆源码到 $DEST_DIR..."
    local clone_success=false
    
    # 尝试从首选源克隆
    if git clone --progress --depth 1 --branch "$SOURCE_REF" "$SOURCE_URL" "$DEST_DIR" 2>&1 | tee /dev/tty | grep -q "Cloning into"; then
        clone_success=true
    fi
    
    # 如果失败且不是 Gitee，尝试切换到 Gitee
    if [ "$clone_success" = false ] && [ "$SOURCE_URL" != "$GITEE_URL" ]; then
        local fallback_url="$GITEE_URL"
        echo "GitHub 下载失败，尝试从 Gitee 获取同版本源码..."
        rm -rf "$DEST_DIR"
        if git clone --progress --depth 1 --branch "$SOURCE_REF" "$fallback_url" "$DEST_DIR" 2>&1 | tee /dev/tty | grep -q "Cloning into"; then
            clone_success=true
            SOURCE_URL="$fallback_url"
        fi
    fi
    
    if [ "$clone_success" = false ]; then
        echo "错误：源码下载失败，请检查网络连接后重试"
        echo "当前源：$SOURCE_URL"
        exit 1
    fi
    
    echo "✓ 源码下载成功"
}

install_tools() {
    echo -e "\n--- 3. 安装 Jarvis 及附加工具 ---"
    cd "$DEST_DIR"
    
    # 验证 uv 和 Python 版本
    local uv_version
    uv_version=$(uv --version 2>&1)
    echo "✓ 使用 uv: $uv_version"
    
    echo "正在安装 Jarvis (Python 3.12)..."
    uv tool install -e . --python 3.12 || {
        echo "错误：Jarvis 安装失败"
        exit 1
    }
    
    echo "正在安装 playwright..."
    uv tool install playwright || {
        echo "警告：playwright 安装失败，可稍后手动安装"
    }
    
    echo "正在安装 ddgr..."
    uv tool install ddgr || {
        echo "警告：ddgr 安装失败，可稍后手动安装"
    }

    echo -e "\n--- 更新 shell 环境配置 ---"
    
    # 检测当前 shell 类型并配置对应的配置文件
    local shell_name
    shell_name=$(basename "$SHELL")
    local shell_config=""
    
    case "$shell_name" in
        bash)
            shell_config="$HOME/.bashrc"
            ;;
        zsh)
            shell_config="$HOME/.zshrc"
            ;;
        fish)
            shell_config="$HOME/.config/fish/config.fish"
            ;;
        *)
            echo "提示：未知 shell 类型 ($shell_name)，请手动配置环境变量"
            shell_config=""
            ;;
    esac
    
    # 执行 uv tool update-shell
    if uv tool update-shell; then
        echo "✓ Shell 环境已更新"
    else
        echo "提示：uv tool update-shell 执行失败，将尝试手动配置"
    fi
    
    # 如果检测到配置文件，提示用户 source
    if [ -n "$shell_config" ] && [ -f "$shell_config" ]; then
        echo "✓ 已更新配置文件：$shell_config"
        echo "提示：如需要立即生效，请执行：source $shell_config"
    fi
    
    echo "✓ 工具安装完成"
}

# ===== 主执行流程 =====
check_prerequisites
prepare_source_tree
ensure_uv_available
install_tools

# ===== 环境验证 =====
verify_installation() {
    echo -e "\n--- 4. 验证安装结果 ---"
    
    # 重新加载 PATH 确保能访问新安装的命令
    export PATH="$HOME/.local/bin:$PATH"
    
    # 验证 jarvis 命令
    if command -v jarvis &> /dev/null; then
        local jarvis_version
        jarvis_version=$(jarvis --version 2>&1 || echo "未知版本")
        echo "✓ Jarvis 已安装：$jarvis_version"
    else
        echo "⚠ 警告：jarvis 命令未在 PATH 中找到"
        echo "  请执行以下命令之一："
        echo "    - source ~/.bashrc  (bash 用户)"
        echo "    - source ~/.zshrc   (zsh 用户)"
        echo "    - export PATH=\"$HOME/.local/bin:\$PATH\""
        return 1
    fi
    
    # 验证附加工具
    for tool in playwright ddgr; do
        if command -v "$tool" &> /dev/null; then
            echo "✓ $tool 已安装"
        else
            echo "⚠ $tool 未安装（可选）"
        fi
    done
    
    return 0
}

# ===== 主执行流程 =====
init_status_file
show_install_status

# 如果选择不恢复且已有部分完成，清理状态文件
if [ "$RESUME_INSTALL" = false ] && [ -f "$INSTALL_STATUS_FILE" ]; then
    echo "清理之前的安装状态..."
    rm -f "$INSTALL_STATUS_FILE"
fi

check_prerequisites
prepare_source_tree
ensure_uv_available
install_tools
verify_installation

# 安装成功，清理状态文件
cleanup_status_file

echo -e "\n--- 5. 配置摘要 ---"
echo "========================================"
echo "✓ Jarvis 安装完成！"
echo "========================================"
echo "安装位置：$DEST_DIR"
echo "数据目录：$DEST_DIR/$DEPS_DIR_RELATIVE"
echo "Python 镜像：$UV_PYTHON_INSTALL_MIRROR"
echo "PyPI 镜像：$UV_INDEX_URL"
echo ""
echo "快速开始："
echo "  1. 如果 jarvis 命令不可用，请执行："
echo "     source ~/.bashrc  # 或 source ~/.zshrc"
echo ""
echo "  2. 启动 Jarvis："
echo "     jarvis"
echo ""
echo "========================================"
