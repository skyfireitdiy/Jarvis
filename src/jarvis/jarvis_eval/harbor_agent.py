# -*- coding: utf-8 -*-
"""Jarvis 的 Harbor（Terminal-Bench 2.0）适配层。

将 Jarvis 封装为 Harbor 的 ``BaseInstalledAgent``，使其可作为
Terminal-Bench 2.0 的评测 Agent 运行。核心思路：

1. ``install()``：在评测容器内 ``pip install jarvis-ai-assistant`` 安装 jca CLI。
2. ``run()``：把任务 instruction 写入容器文件，然后调用
   ``jca -n --task-file <path>`` 在容器内执行任务（jca 的 execute_script
   天然运行在容器环境，无需命令重定向）。
3. API key / base URL 通过 Harbor 的 ``--ae``（extra env）传入，本适配层
   在 ``run()`` 里读取并透传给 jca 进程。

Harbor 为惰性依赖：本模块仅在 Harbor 环境中被加载（Harbor 通过
``harbor run -a jarvis_eval.harbor_agent:JarvisInstalledAgent`` 定位类），
因此 Jarvis 主项目 import ``jarvis_eval`` 包不会触发 harbor 依赖。
"""

from __future__ import annotations

import base64
import shlex
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, override

# harbor 为惰性依赖：本模块仅在 Harbor 环境中被加载（Harbor 通过
# ``harbor run -a jarvis_eval.harbor_agent:JarvisInstalledAgent`` 定位类），
# 因此 Jarvis 主项目 import ``jarvis_eval`` 包不会触发 harbor 依赖。
# 以下 import 行尾的 type-ignore 注释用于抑制静态检查的 unresolved-import 误报。
from harbor.agents.capabilities import AgentCapabilities  # type: ignore
from harbor.agents.installed.base import (  # type: ignore
    BaseInstalledAgent,
    with_prompt_template,
)
from harbor.agents.model_connection import ModelConnectionSpec  # type: ignore

# 常见 LLM API key / base URL 环境变量，透传给容器内的 jca 进程。
# jca 的 platform 实现（openai/claude/deepseek 等）从这些标准变量名读取凭据。
_PASSTHROUGH_ENV_VARS: tuple[str, ...] = (
    # OpenAI / 兼容平台
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "OPENAI_BASE_URL",
    # Anthropic
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    # DeepSeek
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    # 通用代理
    "API_BASE_URL",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
)

# 容器内透传的代理变量指向宿主机 127.0.0.1:7890，容器内无对应代理服务，
# 透传给 jca 会导致其调用 LLM API 时 Connection error，故透传时排除。
_PROXY_ENV_VARS: frozenset[str] = frozenset(
    {"HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"}
)

# 容器内任务 instruction 的落盘路径
_INSTRUCTION_PATH = PurePosixPath("/tmp/jarvis-instruction.txt")

# 容器内离线 wheelhouse 的落盘路径
_WHEELHOUSE_REMOTE_DIR = PurePosixPath("/tmp/jarvis-wheelhouse")


class JarvisInstalledAgent(BaseInstalledAgent):
    """Jarvis 的 Harbor 适配 Agent。"""

    # 评测镜像通常不含 Python/git，install() 需 apt 补齐并 pip 安装，
    # 首次安装耗时较长，放宽 setup 超时（默认 360s 不够）。
    DEFAULT_SETUP_TIMEOUT_SEC: ClassVar[float] = 1800.0

    capabilities = AgentCapabilities()
    MODEL_CONNECTION = ModelConnectionSpec(
        default_provider=None,
        api_key_envs=_PASSTHROUGH_ENV_VARS,
        passthrough=True,
    )

    @staticmethod
    @override
    def name() -> str:
        return "jarvis"

    @override
    def get_version_command(self) -> str | None:
        return "jca --version 2>/dev/null || true"

    @override
    def parse_version(self, stdout: str) -> str:
        return (stdout or "").strip() or "unknown"

    @override
    async def install(self, environment: Any) -> None:
        """在评测容器内安装 jca CLI（jarvis-ai-assistant 包）。

        评测镜像（如 gpt2-codegolf）通常不含 Python/git，且 PyPI 发布版
        jarvis-ai-assistant 未打包 builtin 提示词资源。因此依次：
        1. 用 apt 补齐 python3/pip/git；
        2. 配置 git user.name/email（jca 启动要求）；
        3. pip 安装 jarvis-ai-assistant（PEP 668 需 --break-system-packages）；
        4. 从本机源码上传 builtin/prompts 到容器数据目录补齐缺失资源。
        """
        check = await environment.exec(
            command="command -v jca >/dev/null 2>&1",
            user="root",
        )
        if check.return_code == 0:
            self.logger.debug("jca 已安装，跳过安装")
            return

        # 容器内透传的 HTTP_PROXY=127.0.0.1 指向容器自身，需绕过直连。
        no_proxy = "env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy"

        # 1. 补齐系统依赖：python3/pip/git
        sys_check = await environment.exec(
            command=(
                "command -v python3 >/dev/null 2>&1 && "
                "python3 -m pip --version >/dev/null 2>&1 && "
                "command -v git >/dev/null 2>&1"
            ),
            user="root",
        )
        if sys_check.return_code != 0:
            # 容器默认 apt 源为 Ubuntu 官方源（archive.ubuntu.com），容器内
            # 直连国外源极慢，先替换为国内镜像（阿里云）再安装。
            apt_mirror_cmd = (
                "set -euo pipefail; "
                "if command -v sed >/dev/null 2>&1; then "
                "sed -i "
                "'s|http://archive.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g; "
                "s|http://security.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' "
                "/etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list "
                "2>/dev/null || true; "
                "fi"
            )
            await self.exec_as_root(environment, command=apt_mirror_cmd)
            # 容器内直连外部源偶发超时，apt 整体重试多轮（成功即 break）。
            apt_cmd = (
                "set -euo pipefail; "
                "done_apt=0; "
                "for i in 1 2 3; do "
                f"if {no_proxy} apt-get update -qq && "
                f"{no_proxy} DEBIAN_FRONTEND=noninteractive "
                "apt-get install -y -qq python3 python3-pip git; "
                "then done_apt=1; break; fi; "
                'echo "[install] apt 第 $i 轮失败，5s 后重试..."; sleep 5; '
                "done; "
                'if [ "$done_apt" -ne 1 ]; then '
                'echo "[install] apt 安装多次重试后仍失败" >&2; exit 1; fi'
            )
            await self.exec_as_root(
                environment,
                command=apt_cmd,
                timeout_sec=900,
            )

        # 2. 配置 git 身份（jca 启动时要求）
        await self.exec_as_root(
            environment,
            command=(
                "git config --global user.name 'Jarvis' && "
                "git config --global user.email 'jarvis@local'"
            ),
        )

        # 3. 安装 jarvis-ai-assistant（Ubuntu 24.04 的 pip 受 PEP 668 限制）
        # 优先使用本机预构建的离线 wheelhouse（彻底绕开容器内下载大包不稳）；
        # 未提供 wheelhouse 时回退到在线多镜像源安装。
        wheelhouse_dir = self._wheelhouse_dir()
        if wheelhouse_dir is not None:
            await self._install_from_wheelhouse(
                environment, wheelhouse_dir, no_proxy
            )
        else:
            await self._install_online(environment, no_proxy)

        # 4. 补齐 PyPI 包缺失的 builtin 提示词资源（从本机源码上传）
        prompts_dir = self._local_prompts_dir()
        if prompts_dir is not None:
            await self.exec_as_root(
                environment,
                command="mkdir -p /root/.jarvis/prompts",
            )
            await environment.upload_dir(prompts_dir, "/root/.jarvis/prompts")
            self.logger.debug("已上传 builtin/prompts 到容器数据目录")

    @override
    @with_prompt_template
    async def run(self, instruction: str, environment: Any, context: Any) -> None:
        """在评测容器内运行 Jarvis 解决任务。

        instruction 通过 Harbor 的 ``@with_prompt_template`` 渲染后传入。
        将 instruction 写入容器文件，然后调用 ``jca -n --task-file <path>``。
        """
        # 用 base64 写入 instruction，避免 shell 转义问题
        encoded = base64.b64encode(instruction.encode("utf-8")).decode("ascii")
        await self.exec_as_agent(
            environment,
            command=(
                f"printf '%s' {shlex.quote(encoded)} | base64 -d > "
                f"{_INSTRUCTION_PATH.as_posix()}"
            ),
        )

        env = self._build_passthrough_env()
        run_id = uuid.uuid4().hex
        log_path = (self.environment_logs_dir / f"jca-{run_id}.log").as_posix()

        # 容器内可能被 Harbor 注入指向容器自身 loopback 的代理变量
        # （HTTP_PROXY=127.0.0.1:7890），容器内无对应代理服务，会导致 jca
        # 调用 LLM API 时 Connection error。启动 jca 前显式清除代理，强制直连。
        command = (
            "env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy "
            f"jca -n --task-file {shlex.quote(_INSTRUCTION_PATH.as_posix())} "
            f"2>&1 | tee {shlex.quote(log_path)}"
        )
        await self.exec_as_agent(environment, command=command, env=env)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    def _wheelhouse_dir(self) -> Path | None:
        """定位本机预构建的离线 wheelhouse 目录（供容器离线安装）。

        通过环境变量 ``JARVIS_WHEELHOUSE_DIR`` 指定本机 wheelhouse 路径；
        未设置或目录不存在时返回 None，install() 回退到在线安装。
        """
        raw = self._get_env("JARVIS_WHEELHOUSE_DIR")
        if not raw:
            return None
        wheelhouse = Path(raw).expanduser()
        return wheelhouse if wheelhouse.is_dir() else None

    async def _install_from_wheelhouse(
        self,
        environment: Any,
        wheelhouse_dir: Path,
        no_proxy: str,
    ) -> None:
        """用本机预构建的离线 wheelhouse 在容器内安装 jarvis-ai-assistant。

        将 wheelhouse 上传到容器后，用 ``--no-index --find-links`` 完全
        离线安装，彻底绕开容器内直连 PyPI 下载大包（playwright 等）不稳
        的问题。wheelhouse 需在本机用与容器相同的 Python 版本（3.12）
        预构建，确保 wheel 平台/ABI 兼容。
        """
        remote_dir = _WHEELHOUSE_REMOTE_DIR.as_posix()
        self.logger.info("使用离线 wheelhouse 安装：%s", wheelhouse_dir)
        await self.exec_as_root(
            environment,
            command=f"mkdir -p {remote_dir}",
        )
        await environment.upload_dir(wheelhouse_dir, remote_dir)
        install_cmd = (
            "set -euo pipefail; "
            "installed=0; "
            "for i in 1 2 3; do "
            f"if {no_proxy} python3 -m pip install --break-system-packages "
            "--no-cache-dir --upgrade "
            f"--no-index --find-links={remote_dir} jarvis-ai-assistant; "
            "then installed=1; break; fi; "
            'echo "[install] 离线安装第 $i 轮失败，5s 后重试..."; sleep 5; '
            "done; "
            'if [ "$installed" -ne 1 ]; then '
            'echo "[install] 离线 wheelhouse 安装多次重试后仍失败" >&2; '
            "exit 1; fi"
        )
        await self.exec_as_agent(
            environment,
            command=install_cmd,
            timeout_sec=900,
        )

    async def _install_online(self, environment: Any, no_proxy: str) -> None:
        """在线多镜像源安装 jarvis-ai-assistant（离线 wheelhouse 不可用时的回退）。

        容器内直连 PyPI 网络不稳，大包下载可能中途 ReadTimeout 或下载损坏
        （wheel 为空文件、hash 不匹配）；国内镜像源（清华 tuna）虽快但偶发
        403/限流。故采用多镜像源 fallback（清华 → 阿里云 → 直连 PyPI），
        并整体重试多轮，用 --no-cache-dir 避免缓存损坏文件导致重试仍失败。
        """
        pip_indexes = (
            "https://pypi.tuna.tsinghua.edu.cn/simple",
            "https://mirrors.aliyun.com/pypi/simple/",
            "https://pypi.org/simple",
        )
        pip_install_cmd = (
            "set -euo pipefail; "
            "installed=0; "
            "for i in 1 2 3; do "
            'for idx in "{0}" "{1}" "{2}"; do '
            f"if {no_proxy} python3 -m pip install --break-system-packages "
            "--no-cache-dir --upgrade --timeout 120 --retries 10 "
            '-i "$idx" jarvis-ai-assistant; then installed=1; break 2; fi; '
            'echo "[install] 源 $idx 失败，切换下一源"; '
            "done; "
            'echo "[install] 第 $i 轮全部源失败，5s 后重试..."; sleep 5; '
            "done; "
            'if [ "$installed" -ne 1 ]; then '
            'echo "[install] pip install 多次重试后仍失败" >&2; exit 1; fi'
        ).format(*pip_indexes)
        await self.exec_as_agent(
            environment,
            command=pip_install_cmd,
            timeout_sec=1500,
        )

    def _local_prompts_dir(self) -> Path | None:
        """定位本机源码的 builtin/prompts 目录。

        PyPI 发布版 jarvis-ai-assistant 未打包 builtin 提示词资源，需从
        本机源码上传补齐。本机以源码方式运行（``src/jarvis/jarvis_eval/``），
        由此向上推导项目根目录；若找不到（如已安装为包）则返回 None。
        """
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        prompts_dir = project_root / "builtin" / "prompts"
        return prompts_dir if prompts_dir.is_dir() else None

    def _build_passthrough_env(self) -> dict[str, str]:
        """收集需要透传给 jca 进程的 API 凭据环境变量。

        代理变量（HTTP_PROXY/HTTPS_PROXY 等）指向宿主机 127.0.0.1:7890，
        容器内无对应代理服务，透传会导致 jca 调用 LLM API 时 Connection
        error，故排除。
        """
        env: dict[str, str] = {}
        for name in _PASSTHROUGH_ENV_VARS:
            if name in _PROXY_ENV_VARS:
                continue
            value = self._get_env(name)
            if value:
                env[name] = value
        return env
