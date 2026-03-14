#!/bin/bash
set -e

# 获取脚本所在目录作为项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

echo "🚀 启动 Jarvis 网关和前端..."
echo "📁 项目根目录: $PROJECT_ROOT"

# 检查 Python 环境
if ! command -v python &> /dev/null; then
    echo "❌ 错误: 未找到 Python 环境"
    exit 1
fi

# 检查 npm 环境
if ! command -v npm &> /dev/null; then
    echo "❌ 错误: 未找到 npm 环境"
    exit 1
fi

# 检查是否设置了网关密码环境变量
GATEWAY_PASSWORD=""
if [ -n "$JARVIS_GATEWAY_PASSWORD" ]; then
    echo "🔐 检测到网关密码环境变量"
    GATEWAY_PASSWORD="--gateway-password $JARVIS_GATEWAY_PASSWORD"
fi

# 启动网关（后台运行）
echo "📡 启动网关服务..."
cd "$PROJECT_ROOT"
python -m uvicorn jarvis.jarvis_web_gateway.app:create_app --host 0.0.0.0 --port 8000 $GATEWAY_PASSWORD &
GATEWAY_PID=$!

echo "✅ 网关已启动 (PID: $GATEWAY_PID)"

# 等待网关启动
echo "⏳ 等待网关服务就绪..."
sleep 5

# 启动前端（开发模式）
echo "🎨 启动前端服务..."
cd "$PROJECT_ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo "✅ 前端已启动 (PID: $FRONTEND_PID)"
echo ""
echo "========================================="
echo "✨ Jarvis 服务已全部启动！"
echo "========================================="
echo "📡 网关地址: http://localhost:8000"
echo "🎨 前端地址: http://localhost:5173"
echo "========================================="
echo ""
echo "💡 提示: 按 Ctrl+C 停止所有服务"
echo ""

# 捕获退出信号，清理后台进程
trap "echo ''; echo '🛑 正在停止服务...'; kill $GATEWAY_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM

# 等待所有后台进程
wait $GATEWAY_PID $FRONTEND_PID