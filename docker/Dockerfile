# 使用Python 3.8作为基础镜像
FROM python:3.8-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y git && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir jarvis-ai-assistant && \
    playwright install chromium 

WORKDIR /workspace