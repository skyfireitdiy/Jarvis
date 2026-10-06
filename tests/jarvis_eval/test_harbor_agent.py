# -*- coding: utf-8 -*-
"""Jarvis 的 Harbor 适配层单元测试（不依赖 Docker）。

Harbor 为惰性依赖：当本机未安装 ``harbor`` 时，本测试模块整体跳过
（``pytest.importorskip``）。测试用 mock environment 捕获命令调用，
验证 install / run 的命令构造与 API key 透传逻辑。
"""

import base64
import asyncio
from pathlib import Path

import pytest

harbor = pytest.importorskip("harbor", reason="需要 harbor 包（惰性依赖）")

from harbor.agents.installed.base import BaseInstalledAgent  # noqa: E402  # type: ignore

from jarvis.jarvis_eval.harbor_agent import (  # noqa: E402
    JarvisInstalledAgent,
    _INSTRUCTION_PATH,
    _PASSTHROUGH_ENV_VARS,
)


class _FakeResult:
    def __init__(self, code=0, out="", err=""):
        self.return_code = code
        self.stdout = out
        self.stderr = err


class _FakeEnvironment:
    """捕获 exec 调用的 mock environment。"""

    def __init__(self, jca_installed=False):
        self.commands = []
        self.jca_installed = jca_installed

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        self.commands.append({"cmd": command, "env": env, "user": user})
        if "command -v jca" in command:
            return _FakeResult(0 if self.jca_installed else 1)
        return _FakeResult(0, "ok")


def _make_agent(**kwargs):
    return JarvisInstalledAgent(
        logs_dir=Path("/tmp/harbor-test-logs"),
        model_name="gpt-4o",
        extra_env={"OPENAI_API_KEY": "sk-test-123"},
        **kwargs,
    )


def _run(coro):
    return asyncio.run(coro)


# ----------------------------------------------------------------------
# 类加载与基础属性
# ----------------------------------------------------------------------
def test_agent_subclasses_base_installed_agent():
    assert issubclass(JarvisInstalledAgent, BaseInstalledAgent)


def test_agent_name():
    assert JarvisInstalledAgent.name() == "jarvis"


def test_agent_can_instantiate():
    agent = _make_agent()
    assert agent.version() is None
    assert agent.get_version_command() == "jca --version 2>/dev/null || true"


def test_passthrough_env_collects_api_keys():
    agent = _make_agent()
    env = agent._build_passthrough_env()
    assert env["OPENAI_API_KEY"] == "sk-test-123"
    # 未配置的变量不应出现
    assert "ANTHROPIC_API_KEY" not in env


def test_passthrough_env_skips_empty():
    agent = JarvisInstalledAgent(
        logs_dir=Path("/tmp/harbor-test-logs"),
        model_name="gpt-4o",
        extra_env={"OPENAI_API_KEY": ""},
    )
    env = agent._build_passthrough_env()
    assert "OPENAI_API_KEY" not in env


def test_passthrough_env_vars_declared():
    # 关键凭据变量必须在透传清单里
    assert "OPENAI_API_KEY" in _PASSTHROUGH_ENV_VARS
    assert "ANTHROPIC_API_KEY" in _PASSTHROUGH_ENV_VARS


# ----------------------------------------------------------------------
# install
# ----------------------------------------------------------------------
def test_install_skips_when_jca_present():
    agent = _make_agent()
    env = _FakeEnvironment(jca_installed=True)
    _run(agent.install(env))
    # 只应有一次 jca 检查，不应有 pip install
    assert len(env.commands) == 1
    assert "command -v jca" in env.commands[0]["cmd"]
    assert "pip install" not in env.commands[0]["cmd"]


def test_install_runs_pip_when_missing():
    agent = _make_agent()
    env = _FakeEnvironment(jca_installed=False)
    _run(agent.install(env))
    assert len(env.commands) == 2
    # 第二次是 pip install
    pip_cmd = env.commands[1]["cmd"]
    assert "pip install" in pip_cmd
    assert "jarvis-ai-assistant" in pip_cmd


# ----------------------------------------------------------------------
# run
# ----------------------------------------------------------------------
def test_run_writes_instruction_and_invokes_jca():
    agent = _make_agent()
    env = _FakeEnvironment()
    instruction = "请解决任务：计算 1+1，结果写入 /tmp/answer.txt。"
    _run(agent.run(instruction, env, None))

    assert len(env.commands) == 2

    # 第一条：base64 写入 instruction
    write_cmd = env.commands[0]["cmd"]
    assert "base64 -d" in write_cmd
    assert _INSTRUCTION_PATH.as_posix() in write_cmd
    # 验证写入的内容能解码回原文
    encoded = write_cmd.split("printf '%s' ")[1].split(" |")[0].strip("'")
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded == instruction

    # 第二条：jca 调用
    run_cmd = env.commands[1]["cmd"]
    assert "jca -n" in run_cmd
    assert "--task-file" in run_cmd
    assert _INSTRUCTION_PATH.as_posix() in run_cmd
    # API key 透传
    assert env.commands[1]["env"]["OPENAI_API_KEY"] == "sk-test-123"


def test_run_invokes_as_agent_user():
    agent = _make_agent()
    env = _FakeEnvironment()
    _run(agent.run("do the thing", env, None))
    # exec_as_agent 的 user 为 None（默认 agent 用户）
    for cmd in env.commands:
        assert cmd["user"] is None


def test_base64_roundtrip():
    instruction = "中文任务：把 hello world 写入文件。"
    encoded = base64.b64encode(instruction.encode("utf-8")).decode("ascii")
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded == instruction
