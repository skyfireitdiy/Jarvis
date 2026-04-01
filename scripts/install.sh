#!/bin/bash

set -e

export UV_PYTHON_INSTALL_MIRROR="https://python-standalone.org/mirror/astral-sh/python-build-standalone/"
echo "已设置 Python 安装镜像: $UV_PYTHON_INSTALL_MIRROR"

GITEE_URL="https://gitee.com/skyfireitdiy/Jarvis.git"
GITHUB_URL="https://github.com/skyfireitdiy/Jarvis.git"
DEST_DIR="$HOME/Jarvis"
DEFAULT_BRANCH="main"

ensure_uv_installed() {
    echo "--- 1. 检查或安装 uv 环境 ---"
    if command -v uv &> /dev/null; then
        echo "uv 已安装."
        echo "发现 uv: $(uv --version)"
        return
    fi

    echo "'uv' 未安装，正在尝试自动安装..."
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh

    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if [ -f "$HOME/.cargo/env" ]; then
        # shellcheck disable=SC1090
        source "$HOME/.cargo/env"
    fi

    if ! command -v uv &> /dev/null; then
        echo "错误: 'uv' 自动安装失败。"
        echo "请访问 https://github.com/astral-sh/uv#installation 手动安装后重试。"
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
    echo -e "\n--- 2. 下载 Jarvis 源码 ---"
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
    uv tool install -e .
    uv tool install playwright
    uv tool install ddgr
}

ensure_uv_installed
prepare_source_tree
install_tools

echo -e "\n--- 4. 安装完成! ---"
echo "Jarvis 已全局安装成功！您现在可以直接使用 jarvis 命令。"
echo "已安装附加工具: playwright, ddgr"
echo "源码目录: $DEST_DIR"
