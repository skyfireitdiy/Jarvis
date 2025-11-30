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

# 安装系统依赖（不包括 Python 3.12，将使用 uv 安装）
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 基础工具
    git \
    curl \
    wget \
    ca-certificates \
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
    && rm -rf /var/lib/apt/lists/*

# 安装 uv（Python 包管理器），然后使用 uv 安装 Python 3.12
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && (mv "$HOME/.local/bin/uv" /usr/local/bin/uv 2>/dev/null || mv "$HOME/.cargo/bin/uv" /usr/local/bin/uv 2>/dev/null || cp "$HOME/.local/bin/uv" /usr/local/bin/uv 2>/dev/null || true) \
    && /usr/local/bin/uv --version \
    && echo "📦 使用 uv 安装 Python 3.12..." \
    && /usr/local/bin/uv python install 3.12 \
    && ln -sf $(/usr/local/bin/uv python find 3.12) /usr/local/bin/python3.12 \
    && ln -sf /usr/local/bin/python3.12 /usr/local/bin/python3 \
    && ln -sf /usr/local/bin/python3.12 /usr/local/bin/python \
    && python --version

# 安装 Rust 组件（Rust 镜像已包含 Rust，只需添加组件）
# 设置默认工具链，确保 cargo 可以正常工作
RUN rustup default stable \
    && rustup component add rust-analyzer \
    && rustup component add rustfmt \
    && rustup component add clippy \
    && echo "✅ Rust 组件安装完成" \
    && rustc --version && cargo --version

# 配置 crates.io 使用中科大镜像源
RUN mkdir -p /root/.cargo \
    && echo '[source.crates-io]' > /root/.cargo/config.toml \
    && echo 'replace-with = "ustc"' >> /root/.cargo/config.toml \
    && echo '' >> /root/.cargo/config.toml \
    && echo '[source.ustc]' >> /root/.cargo/config.toml \
    && echo 'registry = "https://mirrors.ustc.edu.cn/crates.io-index"' >> /root/.cargo/config.toml

# 设置 Rust 环境变量（Rust 镜像已设置，这里确保路径正确）
ENV PATH="/root/.cargo/bin:$PATH" \
    CARGO_HOME="/root/.cargo" \
    RUSTUP_HOME="/root/.rustup"

# 安装 ripgrep (rg)
RUN cargo install ripgrep --locked \
    && rg --version

# 安装 fd
RUN cargo install fd-find --locked \
    && fd --version

# 安装 fzf
RUN git clone --depth 1 https://github.com/junegunn/fzf.git /tmp/fzf \
    && /tmp/fzf/install --bin \
    && mv /tmp/fzf/bin/fzf /usr/local/bin/fzf \
    && rm -rf /tmp/fzf \
    && fzf --version

# 复制项目文件
COPY . /app

# 创建虚拟环境并安装 Jarvis（使用 -e 参数以可编辑模式安装，便于自动更新生效）
# 同时安装 RAG 功能和 clang 依赖（用于 C/C++ 代码分析）
RUN uv venv /app/.venv --python 3.12 \
    && . /app/.venv/bin/activate \
    && uv pip install --system -e ".[rag,clang19]" \
    && jarvis --version || echo "Jarvis installed"

# 安装 Python 静态检查、格式化和 LSP 工具
RUN . /app/.venv/bin/activate \
    && uv pip install --system \
    ruff \
    mypy \
    python-lsp-server \
    && echo "✅ Python 工具安装完成"

# 设置 PATH 环境变量，确保所有工具可用
# 同时支持 root 用户和非 root 用户
ENV PATH="/app/.venv/bin:/root/.cargo/bin:/usr/local/bin:$PATH"

# 创建非 root 用户（用于 docker-compose，避免文件权限问题）
# 用户 ID 和组 ID 可以通过环境变量传入，默认为 1000
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG USER_NAME=jarvis

RUN groupadd -g ${GROUP_ID} ${USER_NAME} || true \
    && useradd -u ${USER_ID} -g ${GROUP_ID} -m -s /usr/bin/fish ${USER_NAME} || true \
    && mkdir -p /home/${USER_NAME}/.config/fish \
    && mkdir -p /home/${USER_NAME}/.jarvis \
    && mkdir -p /home/${USER_NAME}/.cargo \
    && chown -R ${USER_ID}:${GROUP_ID} /home/${USER_NAME} \
    && chown -R ${USER_ID}:${GROUP_ID} /app

# 为非 root 用户配置 crates.io 镜像源
RUN if [ -d /home/${USER_NAME} ]; then \
        mkdir -p /home/${USER_NAME}/.cargo && \
        echo '[source.crates-io]' > /home/${USER_NAME}/.cargo/config.toml && \
        echo 'replace-with = "ustc"' >> /home/${USER_NAME}/.cargo/config.toml && \
        echo '' >> /home/${USER_NAME}/.cargo/config.toml && \
        echo '[source.ustc]' >> /home/${USER_NAME}/.cargo/config.toml && \
        echo 'registry = "https://mirrors.ustc.edu.cn/crates.io-index"' >> /home/${USER_NAME}/.cargo/config.toml && \
        chown -R ${USER_ID}:${GROUP_ID} /home/${USER_NAME}/.cargo; \
    fi

# 设置 fish 为默认 shell（后续 RUN 命令将使用 fish）
SHELL ["/usr/bin/fish", "-c"]

# 创建 fish 配置目录并集成 smartshell，同时配置自动激活虚拟环境
# 为 root 用户配置（默认情况）
RUN mkdir -p /root/.config/fish; \
    and /app/.venv/bin/jss install --shell fish; \
    or echo "JSS install completed"; \
    and echo "# 自动激活 Jarvis 虚拟环境" >> /root/.config/fish/config.fish; \
    and echo "source /app/.venv/bin/activate.fish" >> /root/.config/fish/config.fish; \
    and echo "✅ Fish shell、smartshell 集成和虚拟环境自动激活配置完成"

# 为非 root 用户配置（docker-compose 使用）
# 使用 bash 执行（因为 fish 的 if 语法不同）
RUN /bin/bash -c "if [ -d /home/${USER_NAME} ]; then \
    . /app/.venv/bin/activate && \
    /app/.venv/bin/jss install --shell fish || echo 'JSS install completed' && \
    echo '# 自动激活 Jarvis 虚拟环境' >> /home/${USER_NAME}/.config/fish/config.fish && \
    echo 'source /app/.venv/bin/activate.fish' >> /home/${USER_NAME}/.config/fish/config.fish && \
    chown -R ${USER_ID}:${GROUP_ID} /home/${USER_NAME}/.config; \
    fi"

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
    and uv --version; \
    and fish --version; \
    and echo "=== 所有工具安装完成 ==="

# 设置默认命令为 fish
CMD ["/usr/bin/fish"]

