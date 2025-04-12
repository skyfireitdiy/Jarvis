#!/bin/bash

set -e

# 获取当前版本号
VERSION=$(python setup.py --version)

# 构建Docker镜像
docker-compose build

# 标记版本
docker tag jarvis:latest jarvis:$VERSION

# 推送镜像(可选)
# docker push jarvis:$VERSION
# docker push jarvis:latest

echo "Successfully built jarvis:$VERSION and updated jarvis:latest"
