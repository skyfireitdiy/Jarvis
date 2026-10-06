# 增强镜像：基于 crack-7z-hash 官方镜像，预装 python3.12 + pytest + jca，
# 使 Terminal-Bench verifier 完全离线运行（不依赖容器内下载 uv/astral.sh）。
# 构建方法见 docs/technical/eval_run_guide.md 第四节。
FROM alexgshaw/crack-7z-hash:20251031

# 预装系统 python3.12 + pip + git（构建期网络可靠，apt 源为 Ubuntu 官方）
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip git \
    && rm -rf /var/lib/apt/lists/*

# 预装 pytest==8.4.1 + pytest-json-ctrf==0.3.5（纯 Python 包，直接并入 site-packages）
COPY pytest-site/ /tmp/pytest-site/
RUN cp -r /tmp/pytest-site/* /usr/lib/python3/dist-packages/ \
    && rm -rf /tmp/pytest-site

# 预装 jca（jarvis-ai-assistant）及其依赖：用离线 cp312 wheelhouse 完全离线安装，
# 使 install() 检测到 jca 已存在而跳过（harbor_agent.py 中 command -v jca 检查）。
COPY wheelhouse/ /tmp/wheelhouse/
RUN python3 -m pip install --break-system-packages --no-index \
        --find-links=/tmp/wheelhouse jarvis-ai-assistant \
    && rm -rf /tmp/wheelhouse

# PyPI 发布版未打包 builtin 提示词资源，从本机源码补齐到 jca 数据目录
# （install() 的步骤 4 也会做同样的事，这里预装以跳过 install()）。
COPY prompts/ /root/.jarvis/prompts/

# 校验
RUN python3 --version && python3 -m pytest --version && command -v jca
