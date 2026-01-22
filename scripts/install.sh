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

echo -e "\n--- 2. 选择安装方式 ---"
echo "请选择安装方式："
echo "  1) 直接安装（推荐） - 快速简单，无需下载源码，适合快速使用"
echo "  2) 克隆安装 - 下载源码到本地，便于查看和修改代码"
read -r -p "请输入选择 [1/2，默认1]: " choice
INSTALL_TYPE="direct"
case "$choice" in
  2 )
    INSTALL_TYPE="clone"
    echo "已选择：克隆安装（源码将下载到 $DEST_DIR）"
    ;;
  * )
    echo "已选择：直接安装（快速、无源码）"
    ;;
esac

echo -e "\n--- 3. 克隆或更新 Jarvis 仓库 ---"
if [ "$INSTALL_TYPE" = "clone" ]; then
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

echo -e "\n--- 4. 全局安装 Jarvis ---"

echo "正在使用 uv 全局安装项目和依赖..."

read -r -p "是否安装 RAG 功能? (这将安装 PyTorch 等较重的依赖) [y/N]: " rag_choice

case "$INSTALL_TYPE" in
  clone )
    cd "$DEST_DIR"
    case "$rag_choice" in
      y|Y )
        echo "正在从本地安装核心功能及 RAG 依赖..."
        uv tool install '.[rag]'
        ;;
      * )
        echo "正在从本地安装核心功能..."
        uv tool install .
        ;;
    esac
    ;;
  direct )
    # 临时禁用 set -e 以允许降级重试
    set +e
    case "$rag_choice" in
      y|Y )
        echo "正在从仓库安装核心功能及 RAG 依赖..."
        if uv tool install "git+${GITEE_URL}[rag]"; then
          echo "✓ 从 Gitee 安装成功"
        else
          echo "✗ Gitee 安装失败，尝试从 GitHub 安装..."
          if uv tool install "git+${GITHUB_URL}[rag]"; then
            echo "✓ 从 GitHub 安装成功"
          else
            echo "✗ GitHub 安装也失败，请检查网络连接"
            set -e
            exit 1
          fi
        fi
        ;;
      * )
        echo "正在从仓库安装核心功能..."
        if uv tool install "git+$GITEE_URL"; then
          echo "✓ 从 Gitee 安装成功"
        else
          echo "✗ Gitee 安装失败，尝试从 GitHub 安装..."
          if uv tool install "git+$GITHUB_URL"; then
            echo "✓ 从 GitHub 安装成功"
          else
            echo "✗ GitHub 安装也失败，请检查网络连接"
            set -e
            exit 1
          fi
        fi
        ;;
    esac
    set -e
    ;;
esac


echo -e "\n--- 5. 安装完成! ---"
case "$INSTALL_TYPE" in
  clone )
    echo "Jarvis 已全局安装成功！您现在可以直接使用 jarvis 命令。"
    echo "源码已下载到: $DEST_DIR"
    ;;
  direct )
    echo "Jarvis 已全局安装成功！您现在可以直接使用 jarvis 命令。"
    echo "提示: 使用直接安装方式，源码未下载到本地。"
    echo "如需查看或修改源码，请手动克隆仓库: git clone $GITHUB_URL"
    ;;
esac

echo -e "\n--- 6. 安装自动补全 (可选) ---"
echo "您可以为常用命令安装自动补全功能，以提高使用效率。"
read -r -p "是否安装命令行自动补全功能? [y/N]: " choice
case "$choice" in
    y|Y )
        echo "正在安装自动补全..."

        # 使用循环来安装所有工具的自动补全
        tools=("jvs" "jvsd" "ja" "jca" "jcad" "jcr" "jgc" "jgs" "jsec" "jc2r" "jrg" "jpm" "jma" "jcfg" "jqc" "jt" "jm" "jss" "jmo")
        for tool in "${tools[@]}"; do
            echo "正在为 $tool 安装自动补全..."
            if "$tool" --install-completion > /dev/null 2>&1; then
                echo "$tool 自动补全安装成功。"
            else
                echo "警告: $tool 自动补全安装失败。"
            fi
        done

        echo "所有工具的自动补全已尝试安装。"
        echo "请重新启动您的 shell 以使更改生效。"
        ;;
    * )
        echo "跳过安装自动补全。"
        ;;
esac
