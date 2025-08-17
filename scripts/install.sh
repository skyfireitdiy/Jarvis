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
            curl -LsSf https://astral.sh/uv/install.sh | sh
        fi
    else
        echo "未找到 pip3，使用 curl 安装 uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
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

# Define repo URL and destination directory
REPO_URL="https://github.com/skyfireitdiy/Jarvis"
DEST_DIR="$HOME/Jarvis"
VENV_DIR="$DEST_DIR/.venv"

echo -e "\n--- 2. 克隆或更新 Jarvis 仓库 ---"
if [ -d "$DEST_DIR" ]; then
    echo "目录 $DEST_DIR 已存在，正在检查更新..."
    cd "$DEST_DIR"
    if [ -n "$(git status --porcelain)" ]; then
        read -r -p "检测到 '$DEST_DIR' 存在未提交的更改，是否放弃这些更改并更新？ [y/N]: " choice
        case "$choice" in
          y|Y )
            echo "正在放弃更改..."
            git checkout .
            echo "正在拉取最新代码..."
            git pull
            ;;
          * )
            echo "跳过更新以保留未提交的更改。"
            ;;
        esac
    else
        echo "正在拉取最新代码..."
        git pull
    fi
else
    echo "正在克隆仓库到 $DEST_DIR..."
    git clone "$REPO_URL" "$DEST_DIR"
fi

echo -e "\n--- 3. 设置虚拟环境并安装 Jarvis ---"
cd "$DEST_DIR"

if [ ! -d "$VENV_DIR" ]; then
    echo "正在 $VENV_DIR 创建虚拟环境..."
    uv venv
else
    echo "虚拟环境 $VENV_DIR 已存在."
fi

echo "正在使用 uv 安装项目和依赖..."

read -r -p "是否安装 RAG 功能? (这将安装 PyTorch 等较重的依赖) [y/N]: " choice
case "$choice" in
  y|Y )
    echo "正在安装核心功能及 RAG 依赖..."
    uv pip install '.[rag]'
    ;;
  * )
    echo "正在安装核心功能..."
    uv pip install .
    ;;
esac


echo -e "\n--- 4. 安装完成! ---"
echo "请根据您使用的 Shell，运行以下命令激活虚拟环境:"
echo "  - Bash / Zsh:"
echo "    source $VENV_DIR/bin/activate"
echo "  - Fish:"
echo "    source $VENV_DIR/bin/activate.fish"
echo ""
echo "激活后，您就可以使用 'jarvis' 命令。"

# 检测用户shell类型并询问是否自动配置
echo -e "\n--- 5. Shell 环境配置 (可选) ---"
current_shell=$(basename "$SHELL")
case "$current_shell" in
    bash|zsh|fish)
        echo "检测到您正在使用 $current_shell，可以自动添加环境配置到您的 rc 文件。"
        read -r -p "是否自动添加 'source $VENV_DIR/bin/activate' 到您的 ~/.${current_shell}rc 文件? [y/N]: " choice
        case "$choice" in
            y|Y )
                if [ "$current_shell" = "fish" ]; then
                    echo "source $VENV_DIR/bin/activate.fish" >> "$HOME/.config/fish/config.fish"
                else
                    echo "source $VENV_DIR/bin/activate" >> "$HOME/.${current_shell}rc"
                fi
                echo "已成功添加到 ~/.${current_shell}rc 文件。下次启动 shell 时将自动激活 Jarvis。"
                ;;
            * )
                echo "跳过自动配置。"
                ;;
        esac
        ;;
    *)
        echo "检测到您正在使用 $current_shell，暂不支持自动配置。"
        ;;
esac
