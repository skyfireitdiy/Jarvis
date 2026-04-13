#!/bin/bash

set -e

export UV_PYTHON_INSTALL_MIRROR="https://python-standalone.org/mirror/astral-sh/python-build-standalone/"
echo "已设置 Python 安装镜像: $UV_PYTHON_INSTALL_MIRROR"

export UV_INDEX_URL="https://pypi.mirrors.ustc.edu.cn/simple/"
echo "已设置 PyPI 镜像 (中科大): $UV_INDEX_URL"

GITEE_URL="https://gitee.com/skyfireitdiy/Jarvis.git"
GITHUB_URL="https://github.com/skyfireitdiy/Jarvis.git"
DEST_DIR="$HOME/Jarvis"
DEFAULT_BRANCH="main"
DEPS_DIR_RELATIVE="src/jarvis/jarvis_data/deps/x86_64_linux"

ensure_uv_available() {
    echo "--- 1. 检查仓库内置 uv 环境 ---"

    local deps_dir="$DEST_DIR/$DEPS_DIR_RELATIVE"
    if [ ! -d "$deps_dir" ]; then
        echo "错误: 当前仓库版本未找到内置依赖目录: $deps_dir"
        echo "请确认当前平台受支持，或手动安装 uv 后重试。"
        exit 1
    fi

    export PATH="$deps_dir:$PATH"
    echo "已将内置依赖目录加入 PATH: $deps_dir"

    if ! command -v uv &> /dev/null; then
        echo "错误: 未在仓库内置依赖目录中找到 uv。"
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
    latest_tag="$(get_latest_tag "$GITEE_URL")"
    if [ -n "$latest_tag" ]; then
        SOURCE_URL="$GITEE_URL"
        SOURCE_REF="$latest_tag"
        return
    fi

    latest_tag="$(get_latest_tag "$GITHUB_URL")"
    if [ -n "$latest_tag" ]; then
        SOURCE_URL="$GITHUB_URL"
        SOURCE_REF="$latest_tag"
        return
    fi

    SOURCE_URL="$GITHUB_URL"
    SOURCE_REF="$DEFAULT_BRANCH"
}

checkout_source_ref() {
    local source_ref="$1"

    if git fetch --depth 1 origin "refs/tags/$source_ref:refs/tags/$source_ref" 2>/dev/null; then
        git checkout -f "$source_ref"
        return
    fi

    git fetch --depth 1 origin "$source_ref"
    git checkout -f FETCH_HEAD
}

prepare_source_tree() {
    echo -e "\n--- 1. 下载 Jarvis 源码 ---"
    resolve_source_reference
    echo "目标版本: $SOURCE_REF"
    echo "下载源: $SOURCE_URL"

    if [ -d "$DEST_DIR" ] && [ ! -d "$DEST_DIR/.git" ]; then
        echo "警告: '$DEST_DIR' 存在但不是 git 仓库"
        echo "请手动备份或删除该目录后重新安装。"
        exit 1
    fi

    if [ -d "$DEST_DIR/.git" ]; then
        echo "检测到已存在 Jarvis 源码仓库，正在切换到目标版本..."
        cd "$DEST_DIR"
        if [ -n "$(git status --porcelain)" ]; then
            echo "错误: '$DEST_DIR' 存在未提交的更改，请先处理后再执行安装。"
            exit 1
        fi
        git remote set-url origin "$SOURCE_URL"
        checkout_source_ref "$SOURCE_REF"
        return
    fi

    echo "正在浅克隆源码到 $DEST_DIR..."
    if git clone --depth 1 --branch "$SOURCE_REF" "$SOURCE_URL" "$DEST_DIR"; then
        return
    fi

    if [ "$SOURCE_URL" != "$GITHUB_URL" ]; then
        SOURCE_URL="$GITHUB_URL"
        echo "Gitee 下载失败，尝试从 GitHub 获取同版本源码..."
        git clone --depth 1 --branch "$SOURCE_REF" "$SOURCE_URL" "$DEST_DIR"
        return
    fi

    echo "源码下载失败，请检查网络连接后重试。"
    exit 1
}

install_tools() {
    echo -e "\n--- 3. 从源码安装 Jarvis ---"
    cd "$DEST_DIR"
    uv tool install -e . --python 3.12
    uv tool install playwright
    uv tool install ddgr
    
    echo -e "\n--- 更新 shell 环境配置 ---"
    uv tool update-shell || echo "提示: 如果需要手动配置，请运行: uv tool update-shell"
}

prepare_source_tree
ensure_uv_available
install_tools

echo -e "\n--- 4. 安装完成! ---"
echo "Jarvis 已全局安装成功！您现在可以直接使用 jarvis 命令。"
echo "已安装附加工具: playwright, ddgr"
echo "源码目录: $DEST_DIR"
