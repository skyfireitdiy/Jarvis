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
from pathlib import PurePosixPath
from typing import Any, override

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

# 容器内任务 instruction 的落盘路径
_INSTRUCTION_PATH = PurePosixPath("/tmp/jarvis-instruction.txt")


class JarvisInstalledAgent(BaseInstalledAgent):
    """Jarvis 的 Harbor 适配 Agent。"""

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
        """在评测容器内安装 jca CLI（jarvis-ai-assistant 包）。"""
        check = await environment.exec(
            command="command -v jca >/dev/null 2>&1",
            user="root",
        )
        if check.return_code == 0:
            self.logger.debug("jca 已安装，跳过安装")
            return
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                "python3 -m pip install --quiet --upgrade jarvis-ai-assistant"
            ),
        )

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

        command = (
            f"jca -n --task-file {shlex.quote(_INSTRUCTION_PATH.as_posix())} "
            f"2>&1 | tee {shlex.quote(log_path)}"
        )
        await self.exec_as_agent(environment, command=command, env=env)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    def _build_passthrough_env(self) -> dict[str, str]:
        """收集需要透传给 jca 进程的 API 凭据环境变量。"""
        env: dict[str, str] = {}
        for name in _PASSTHROUGH_ENV_VARS:
            value = self._get_env(name)
            if value:
                env[name] = value
        return env
