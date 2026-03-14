#!/bin/bash
set -e

echo "🚀 启动 Jarvis 网关和前端..."

# 启动网关（后台运行）
echo "📡 启动网关服务..."
cd /app
python -m uvicorn jarvis.jarvis_web_gateway.app:create_app --host 0.0.0.0 --port 8000 &
GATEWAY_PID=$!

echo "✅ 网关已启动 (PID: $GATEWAY_PID)"

# 等待网关启动
echo "⏳ 等待网关服务就绪..."
sleep 5

# 启动前端（开发模式）
echo "🎨 启动前端服务..."
cd /app/frontend
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

# 等待所有后台进程
wait $GATEWAY_PID $FRONTEND_PID