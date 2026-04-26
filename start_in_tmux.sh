#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
SCRIPT_PATH="$PROJECT_ROOT/$(basename "${BASH_SOURCE[0]}")"
TMUX_SESSION_NAME="jarvis"

run_jarvis_services() {
    echo "🚀 启动 Jarvis 网关和前端..."
    echo "📁 项目根目录: $PROJECT_ROOT"

    if ! command -v python &> /dev/null; then
        echo "❌ 错误: 未找到 Python 环境"
        exit 1
    fi

    if ! command -v npm &> /dev/null; then
        echo "❌ 错误: 未找到 npm 环境"
        exit 1
    fi

    gateway_password_args=()
    if [ -n "$JARVIS_GATEWAY_PASSWORD" ]; then
        echo "🔐 检测到网关密码环境变量"
        gateway_password_args=(--gateway-password "$JARVIS_GATEWAY_PASSWORD")
    fi

    GATEWAY_HOST="${JARVIS_GATEWAY_HOST:-127.0.0.1}"
    GATEWAY_PORT="${JARVIS_GATEWAY_PORT:-8000}"
    FRONTEND_HOST="${JARVIS_FRONTEND_HOST:-127.0.0.1}"
    FRONTEND_PORT="${JARVIS_FRONTEND_PORT:-5173}"

    echo "📡 启动网关服务..."
    cd "$PROJECT_ROOT"
    jwg --host "$GATEWAY_HOST" --port "$GATEWAY_PORT" "${gateway_password_args[@]}" &
    GATEWAY_PID=$!
    echo "✅ 网关已启动 (PID: $GATEWAY_PID)"

    echo "⏳ 等待网关服务就绪..."
    sleep 5

    echo "🎨 启动前端发布服务..."
    cd "$PROJECT_ROOT/src/jarvis/jarvis_service/frontend"

    echo "📦 安装前端依赖..."
    npm install
    echo "✅ 前端依赖安装完成"

    echo "🏗️ 构建前端发布产物..."
    npm run build
    echo "✅ 前端发布版本构建完成"

    npm run preview -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
    FRONTEND_PID=$!
    echo "✅ 前端发布服务已启动 (PID: $FRONTEND_PID)"

    echo ""
    echo "========================================="
    echo "✨ Jarvis 服务已全部启动！"
    echo "========================================="
    echo "📡 网关地址: http://$GATEWAY_HOST:$GATEWAY_PORT"
    echo "🎨 前端地址: http://$FRONTEND_HOST:$FRONTEND_PORT"
    echo "========================================="
    echo ""
    echo "💡 提示: 按 Ctrl+C 停止所有服务"
    echo ""

    trap 'echo ""; echo "🛑 正在停止服务..."; kill "$GATEWAY_PID" "$FRONTEND_PID" 2>/dev/null; exit 0' SIGINT SIGTERM
    wait "$GATEWAY_PID" "$FRONTEND_PID"
}

start_in_tmux_session() {
    if ! command -v tmux &> /dev/null; then
        echo "❌ 错误: 未找到 tmux，请先安装 tmux 后再运行此脚本"
        exit 1
    fi

    if tmux has-session -t "$TMUX_SESSION_NAME" 2>/dev/null; then
        echo "🔁 tmux 会话已存在，正在连接: $TMUX_SESSION_NAME"
        tmux attach -t "$TMUX_SESSION_NAME"
        return
    fi

    echo "🪟 当前不在 tmux 中，正在创建 tmux 会话: $TMUX_SESSION_NAME"
    tmux new-session -d -s "$TMUX_SESSION_NAME" "bash '$SCRIPT_PATH'"
    echo "✅ 已在 tmux 会话中启动 Jarvis"
    tmux attach -t "$TMUX_SESSION_NAME"
}

if [ -z "$TMUX" ]; then
    start_in_tmux_session
    exit 0
fi

run_jarvis_services
