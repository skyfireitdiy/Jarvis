# 第一阶段：构建阶段
FROM python:3.8-slim as builder

# 配置国内镜像源
RUN rm -f /etc/apt/sources.list && \
    echo "deb http://mirrors.aliyun.com/debian/ bookworm main non-free contrib" > /etc/apt/sources.list && \
    echo "deb http://mirrors.aliyun.com/debian-security/ bookworm-security main" >> /etc/apt/sources.list && \
    pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

WORKDIR /workdir
COPY . .

# 安装项目依赖
RUN pip install --user -U pip && \
    pip install --user --default-timeout=100 --retries 5 -e .

# 第二阶段：运行阶段
FROM python:3.8-slim

# 配置国内镜像源
RUN rm -f /etc/apt/sources.list && \
    echo "deb http://mirrors.aliyun.com/debian/ bookworm main non-free contrib" > /etc/apt/sources.list && \
    echo "deb http://mirrors.aliyun.com/debian-security/ bookworm-security main" >> /etc/apt/sources.list && \
    pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

WORKDIR /workdir

# 从构建阶段复制已安装的Python包
COPY --from=builder /root/.local /root/.local
COPY --from=builder /app/src /app/src
COPY --from=builder /app/setup.py /app/

# 确保脚本在PATH中
ENV PATH=/root/.local/bin:$PATH

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 安装项目
RUN pip install --no-deps -e .
