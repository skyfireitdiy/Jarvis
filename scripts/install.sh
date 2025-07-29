#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- 1. 检查 uv 环境 ---"
if ! command -v uv &> /dev/null; then
    echo "错误: 'uv' 未安装."
    echo "请先运行以下命令安装:"
    echo "curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "发现 uv: $(uv --version)"

# Define repo URL and destination directory
REPO_URL="https://github.com/skyfireitdiy/Jarvis"
DEST_DIR="$HOME/Jarvis"
VENV_DIR="$DEST_DIR/.venv"

echo -e "\n--- 2. 克隆或更新 Jarvis 仓库 ---"
if [ -d "$DEST_DIR" ]; then
    echo "目录 $DEST_DIR 已存在，正在拉取最新代码..."
    cd "$DEST_DIR"
    git pull
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
uv pip install .

echo -e "\n--- 4. 初始化 Jarvis ---"
CONFIG_FILE="$HOME/.jarvis/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
    echo "配置文件 $CONFIG_FILE 已存在，跳过初始化。"
else
    echo "正在运行 'jarvis' 来生成配置文件..."
    "$VENV_DIR/bin/jarvis"
fi

echo -e "\n--- 5. 安装与初始化完成! ---"
echo "请根据您使用的 Shell，运行以下命令激活虚拟环境:"
echo "  - Bash / Zsh:"
echo "    source $VENV_DIR/bin/activate"
echo "  - Fish:"
echo "    source $VENV_DIR/bin/activate.fish"
echo ""
echo "激活后，您就可以使用 'jarvis' 命令。"
