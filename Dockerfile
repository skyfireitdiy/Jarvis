# 使用 Python 3.12 作为基础镜像
FROM python:3.12 AS base

# 设置工作目录
WORKDIR /app

# 构建参数：支持代理配置（可选）
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY="localhost,127.0.0.1"

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 如果提供了代理，设置代理环境变量
RUN if [ -n "$HTTP_PROXY" ]; then \
        echo "使用代理: HTTP_PROXY=$HTTP_PROXY, HTTPS_PROXY=$HTTPS_PROXY"; \
    fi

# 安装系统依赖（Python 3.12 已包含在基础镜像中）
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 基础工具
    git \
    curl \
    wget \
    ca-certificates \
    # Python 基础依赖（用于编译 Python 扩展，基础镜像已包含大部分）
    build-essential \
    libssl-dev \
    libffi-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    libncurses5-dev \
    libncursesw5-dev \
    xz-utils \
    tk-dev \
    # libclang 依赖（用于 C/C++ 代码分析，支持 clang 16-21）
    # 安装 clang-19 和对应的 libclang（jarvis-c2rust 支持 16-21）
    llvm-19 \
    clang-19 \
    libclang-19-dev \
    # C/C++ 静态检查和格式化工具
    clang-tidy \
    clang-format \
    clangd \
    # Fish shell
    fish \
    # 其他工具依赖
    unzip \
    # timeout 命令
    coreutils \
    && rm -rf /var/lib/apt/lists/* \
    && python3 --version


# 安装 Rust 工具链
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && . "$HOME/.cargo/env" \
    && rustup default stable \
    && rustup component add rust-analyzer \
    && rustup component add rustfmt \
    && rustup component add clippy \
    && echo "✅ Rust 安装完成" \
    && rustc --version && cargo --version

# 设置 Rust 环境变量
ENV PATH="/root/.cargo/bin:$PATH" \
    CARGO_HOME="/root/.cargo" \
    RUSTUP_HOME="/root/.rustup"

# 安装 ripgrep (rg)
RUN . "$HOME/.cargo/env" \
    && cargo install ripgrep --locked \
    && rg --version \
    && rm -rf /root/.cargo/registry/cache \
    && rm -rf /root/.cargo/git \
    && rm -rf /tmp/*

# 安装 fd
RUN . "$HOME/.cargo/env" \
    && cargo install fd-find --locked \
    && fd --version \
    && rm -rf /root/.cargo/registry/cache \
    && rm -rf /root/.cargo/git \
    && rm -rf /tmp/*

# 安装 fzf
RUN git clone --depth 1 https://github.com/junegunn/fzf.git /tmp/fzf \
    && /tmp/fzf/install --bin \
    && mv /tmp/fzf/bin/fzf /usr/local/bin/fzf \
    && rm -rf /tmp/fzf \
    && fzf --version

# 复制项目文件
COPY . /app

# 升级 pip 并安装 Jarvis（使用 -e 参数以可编辑模式安装，便于自动更新生效）
# 同时安装 clang 依赖（用于 C/C++ 代码分析）
RUN pip install --upgrade pip setuptools wheel \
    && pip install -e ".[clang19]" \
    && echo "Jarvis installed" \
    && find /usr/local/lib/python3.12 -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib/python3.12 -type f -name "*.pyc" -delete 2>/dev/null || true \
    && find /usr/local/lib/python3.12 -type f -name "*.pyo" -delete 2>/dev/null || true \
    && rm -rf /tmp/* /var/tmp/* \
    && rm -rf /root/.cache/pip 2>/dev/null || true

# 安装 Python 静态检查、格式化和 LSP 工具
RUN pip install \
    ruff \
    mypy \
    python-lsp-server \
    && echo "✅ Python 工具安装完成" \
    && find /usr/local/lib/python3.12 -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib/python3.12 -type f -name "*.pyc" -delete 2>/dev/null || true \
    && find /usr/local/lib/python3.12 -type f -name "*.pyo" -delete 2>/dev/null || true \
    && rm -rf /tmp/* /var/tmp/* \
    && rm -rf /root/.cache/pip 2>/dev/null || true

# 设置 PATH 环境变量，确保所有工具可用
ENV PATH="/root/.cargo/bin:/usr/local/bin:$PATH"

# 清理所有临时文件和缓存，释放磁盘空间
RUN rm -rf /tmp/* /var/tmp/* \
    && rm -rf /root/.cache/* \
    && rm -rf /root/.cargo/registry/cache \
    && rm -rf /root/.cargo/git \
    && find /usr/local/lib/python3.12 -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib/python3.12 -type f -name "*.pyc" -delete 2>/dev/null || true \
    && find /usr/local/lib/python3.12 -type f -name "*.pyo" -delete 2>/dev/null || true \
    && find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && find /app -type f -name "*.pyc" -delete 2>/dev/null || true \
    && find /app -type f -name "*.pyo" -delete 2>/dev/null || true

# 设置 fish 为默认 shell（后续 RUN 命令将使用 fish）
SHELL ["/usr/bin/fish", "-c"]

# 创建 fish 配置目录
RUN mkdir -p /root/.config/fish; \
    and echo "✅ Fish shell 配置完成"

# 验证安装的工具
RUN echo "=== 验证工具安装 ==="; \
    and python --version; \
    and rustc --version; \
    and cargo --version; \
    and rust-analyzer --version; or echo "rust-analyzer installed"; \
    and cargo clippy --version; or echo "cargo clippy installed"; \
    and rustfmt --version; or echo "rustfmt installed"; \
    and rg --version; \
    and fd --version; \
    and fzf --version; \
    and git --version; \
    and clang-19 --version | head -1; \
    and clang-tidy --version | head -1; \
    and clang-format --version | head -1; \
    and clangd --version | head -1; \
    and ruff --version; \
    and mypy --version; \
    and pylsp --version; or echo "pylsp installed"; \
    and pip --version; \
    and fish --version; \
    and echo "=== 所有工具安装完成 ==="

# 设置默认命令为 fish
CMD ["/usr/bin/fish"]

