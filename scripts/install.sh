#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# 设置 Python 构建镜像以加速安装
export UV_PYTHON_INSTALL_MIRROR="https://python-standalone.org/mirror/astral-sh/python-build-standalone/"
echo "已设置 Python 安装镜像: $UV_PYTHON_INSTALL_MIRROR"

echo "--- 1. 检查或安装 uv 环境 ---"
if ! command -v uv &> /dev/null; then
    echo "'uv' 未安装，正在尝试自动安装..."
    # 优先尝试 pip3
    if command -v pip3 &> /dev/null; then
        echo "尝试使用 'pip3 install uv --user'..."
        if pip3 install uv --user; then
            # 将 pip 用户目录添加到 PATH
            export PATH="$HOME/.local/bin:$PATH"
            echo "uv 使用 pip3 安装成功。"
        else
            echo "pip3 安装失败，回退到 curl 安装..."
            curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
        fi
    else
        echo "未找到 pip3，使用 curl 安装 uv..."
        curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
    fi

    # 尝试 source cargo env 以使 uv 在当前会话中可用
    if [ -f "$HOME/.cargo/env" ]; then
        # shellcheck disable=SC1090
        source "$HOME/.cargo/env"
    fi

    # 再次检查 uv 是否成功安装
    if ! command -v uv &> /dev/null; then
        echo "错误: 'uv' 自动安装失败。"
        echo "请访问 https://github.com/astral-sh/uv#installation 手动安装后重试。"
        exit 1
    fi
else
    echo "uv 已安装."
fi
echo "发现 uv: $(uv --version)"

# Define repo URLs and destination directory
# 优先尝试 Gitee 镜像（国内访问更快），失败后回退到 GitHub
GITEE_URL="https://gitee.com/skyfireitdiy/Jarvis.git"
GITHUB_URL="https://github.com/skyfireitdiy/Jarvis.git"
DEST_DIR="$HOME/Jarvis"

echo -e "\n--- 2. 克隆或更新 Jarvis 仓库 ---"
if [ -d "$DEST_DIR" ]; then
    echo "目录 $DEST_DIR 已存在"
    
    # 检查是否是 git 仓库
    if [ -d "$DEST_DIR/.git" ]; then
        echo "检测到已存在 Jarvis 源码仓库"
        cd "$DEST_DIR"
        
        # 检查是否有未提交的更改
        if [ -n "$(git status --porcelain)" ]; then
            read -r -p "检测到 '$DEST_DIR' 存在未提交的更改，更新前是否要放弃这些更改? [y/N]: " choice
            case "$choice" in
              y|Y )
                echo "正在放弃更改..."
                git checkout .
                echo "正在拉取最新代码..."
                git pull
                ;;
              * )
                echo "保留未提交的更改，跳过更新。"
                ;;
            esac
        else
            echo "正在拉取最新代码..."
            git pull
        fi
    else
        echo "警告: '$DEST_DIR' 存在但不是 git 仓库"
        echo "请手动备份或删除该目录后重新安装，或直接在该目录下执行: uv tool install -e ."
        exit 1
    fi
  else
    echo "正在克隆仓库到 $DEST_DIR..."
    # 临时禁用 set -e 以允许降级重试
    set +e
    if git clone "$GITEE_URL" "$DEST_DIR"; then
        echo "✓ Gitee 镜像克隆成功"
    else
        echo "✗ Gitee 镜像克隆失败，尝试从 GitHub 克隆..."
        if git clone "$GITHUB_URL" "$DEST_DIR"; then
            echo "✓ GitHub 克隆成功"
        else
            echo "✗ GitHub 克隆也失败，请检查网络连接或手动下载"
            set -e
            exit 1
        fi
    fi
    set -e
fi

echo -e "\n--- 3. 从源码安装 Jarvis ---"
cd "$DEST_DIR"
echo "正在使用 uv 从源码安装项目..."
uv tool install -e .

echo -e "\n--- 4. 安装完成! ---"
echo "Jarvis 已全局安装成功！您现在可以直接使用 jarvis 命令。"
echo "源码目录: $DEST_DIR"
