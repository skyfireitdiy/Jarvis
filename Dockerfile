# 使用 Rust 作为基础镜像
FROM rust:latest AS base

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

# 安装系统依赖（包括 Python 3.12）
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 基础工具
    git \
    curl \
    wget \
    ca-certificates \
    # Python 3.12 和虚拟环境支持
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pip \
    # Python 基础依赖（用于编译 Python 扩展）
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
    && ln -sf /usr/bin/python3.12 /usr/local/bin/python3.12 \
    && ln -sf /usr/bin/python3.12 /usr/local/bin/python3 \
    && ln -sf /usr/bin/python3.12 /usr/local/bin/python \
    && python3.12 --version


# 设置 Rust 环境变量（必须在 rustup 操作之前设置）
ENV PATH="/root/.cargo/bin:$PATH" \
    CARGO_HOME="/root/.cargo" \
    RUSTUP_HOME="/root/.rustup"

# 安装 Rust 组件（Rust 镜像已包含 Rust，只需添加组件）
# 设置默认工具链，确保 cargo 可以正常工作
RUN rustup default stable \
    && rustup component add rust-analyzer \
    && rustup component add rustfmt \
    && rustup component add clippy \
    && echo "✅ Rust 组件安装完成" \
    && rustc --version && cargo --version

# 安装 ripgrep (rg)
# 确保默认工具链已设置，然后安装
RUN rustup default stable \
    && cargo install ripgrep --locked \
    && rg --version \
    && rm -rf /root/.cargo/registry/cache \
    && rm -rf /root/.cargo/git \
    && rm -rf /tmp/*

# 安装 fd
# 确保默认工具链已设置，然后安装
RUN rustup default stable \
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

# 创建虚拟环境并安装 Jarvis（使用 -e 参数以可编辑模式安装，便于自动更新生效）
# 同时安装 clang 依赖（用于 C/C++ 代码分析）
RUN python3.12 -m venv /app/.venv \
    && . /app/.venv/bin/activate \
    && pip install --upgrade pip setuptools wheel \
    && pip install -e ".[clang19]" \
    && echo "Jarvis installed" \
    && find /app/.venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && find /app/.venv -type f -name "*.pyc" -delete 2>/dev/null || true \
    && find /app/.venv -type f -name "*.pyo" -delete 2>/dev/null || true \
    && rm -rf /tmp/* /var/tmp/* \
    && rm -rf /root/.cache/pip 2>/dev/null || true \
    && chmod +x /app/.venv/bin/* 2>/dev/null || true \
    && /app/.venv/bin/python3 --version

# 安装 Python 静态检查、格式化和 LSP 工具
RUN . /app/.venv/bin/activate \
    && pip install \
    ruff \
    mypy \
    python-lsp-server \
    && echo "✅ Python 工具安装完成" \
    && find /app/.venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && find /app/.venv -type f -name "*.pyc" -delete 2>/dev/null || true \
    && find /app/.venv -type f -name "*.pyo" -delete 2>/dev/null || true \
    && rm -rf /tmp/* /var/tmp/* \
    && rm -rf /root/.cache/pip 2>/dev/null || true

# 设置 PATH 环境变量，确保所有工具可用
# 同时支持 root 用户和非 root 用户
ENV PATH="/app/.venv/bin:/root/.cargo/bin:/usr/local/bin:$PATH"

# 创建非 root 用户（用于 docker-compose，避免文件权限问题）
# 用户 ID 和组 ID 可以通过环境变量传入，默认为 1000
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG USER_NAME=jarvis

# 在 chown 之前清理所有临时文件和缓存，释放磁盘空间
RUN rm -rf /tmp/* /var/tmp/* \
    && rm -rf /root/.cache/* \
    && rm -rf /root/.cargo/registry/cache \
    && rm -rf /root/.cargo/git \
    && find /app/.venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && find /app/.venv -type f -name "*.pyc" -delete 2>/dev/null || true \
    && find /app/.venv -type f -name "*.pyo" -delete 2>/dev/null || true \
    && find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && find /app -type f -name "*.pyc" -delete 2>/dev/null || true \
    && find /app -type f -name "*.pyo" -delete 2>/dev/null || true

RUN groupadd -g ${GROUP_ID} ${USER_NAME} || true \
    && useradd -u ${USER_ID} -g ${GROUP_ID} -m -s /usr/bin/fish ${USER_NAME} || true \
    && mkdir -p /home/${USER_NAME}/.config/fish \
    && mkdir -p /home/${USER_NAME}/.jarvis \
    && mkdir -p /home/${USER_NAME}/.cargo \
    && chown -R ${USER_ID}:${GROUP_ID} /home/${USER_NAME} \
    && chown -R ${USER_ID}:${GROUP_ID} /app \
    && find /app/.venv/bin -type f -exec chmod +x {} \; 2>/dev/null || true


# 设置 fish 为默认 shell（后续 RUN 命令将使用 fish）
SHELL ["/usr/bin/fish", "-c"]

# 创建 fish 配置目录并配置自动激活虚拟环境
# 为 root 用户配置（默认情况）
RUN mkdir -p /root/.config/fish; \
    and echo "# 自动激活 Jarvis 虚拟环境" >> /root/.config/fish/config.fish; \
    and echo "if test -f /app/.venv/bin/activate.fish" >> /root/.config/fish/config.fish; \
    and echo "    source /app/.venv/bin/activate.fish" >> /root/.config/fish/config.fish; \
    and echo "end" >> /root/.config/fish/config.fish; \
    and echo "# 确保虚拟环境在 PATH 最前面" >> /root/.config/fish/config.fish; \
    and echo "set -gx PATH /app/.venv/bin \$PATH" >> /root/.config/fish/config.fish; \
    and echo "set -gx VIRTUAL_ENV /app/.venv" >> /root/.config/fish/config.fish; \
    and echo "✅ Fish shell 和虚拟环境自动激活配置完成"

# 为非 root 用户配置（docker-compose 使用）
# 临时切换到 bash shell 执行（因为 fish 的 if 语法不同，且需要避免变量解析问题）
SHELL ["/bin/bash", "-c"]
RUN if [ -d /home/${USER_NAME} ]; then \
    echo '# 自动激活 Jarvis 虚拟环境' >> /home/${USER_NAME}/.config/fish/config.fish && \
    echo 'if test -f /app/.venv/bin/activate.fish' >> /home/${USER_NAME}/.config/fish/config.fish && \
    echo '    source /app/.venv/bin/activate.fish' >> /home/${USER_NAME}/.config/fish/config.fish && \
    echo 'end' >> /home/${USER_NAME}/.config/fish/config.fish && \
    echo '# 确保虚拟环境在 PATH 最前面' >> /home/${USER_NAME}/.config/fish/config.fish && \
    echo 'set -gx PATH /app/.venv/bin $PATH' >> /home/${USER_NAME}/.config/fish/config.fish && \
    echo 'set -gx VIRTUAL_ENV /app/.venv' >> /home/${USER_NAME}/.config/fish/config.fish && \
    chown -R ${USER_ID}:${GROUP_ID} /home/${USER_NAME}/.config && \
    chmod +x /app/.venv/bin/* 2>/dev/null || true; \
    fi
SHELL ["/usr/bin/fish", "-c"]

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

