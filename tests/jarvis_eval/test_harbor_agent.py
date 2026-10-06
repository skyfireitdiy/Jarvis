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

    def __init__(self, jca_installed=False, sys_missing=False):
        self.commands = []
        self.uploads = []
        self.jca_installed = jca_installed
        self.sys_missing = sys_missing

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        self.commands.append({"cmd": command, "env": env, "user": user})
        if "command -v jca" in command:
            return _FakeResult(0 if self.jca_installed else 1)
        if self.sys_missing and "command -v python3" in command:
            return _FakeResult(1)
        return _FakeResult(0, "ok")

    async def upload_dir(self, source_dir, target_dir):
        self.uploads.append((str(source_dir), target_dir))


def _make_agent(**kwargs):
    extra_env = dict(kwargs.pop("extra_env", None) or {})
    extra_env.setdefault("OPENAI_API_KEY", "sk-test-123")
    return JarvisInstalledAgent(
        logs_dir=Path("/tmp/harbor-test-logs"),
        model_name="gpt-4o",
        extra_env=extra_env,
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


def test_passthrough_env_skips_proxy_vars():
    # 代理变量指向宿主机 127.0.0.1:7890，容器内无对应代理服务，
    # 透传会导致 jca 调用 LLM API 时 Connection error，必须排除。
    agent = _make_agent(
        extra_env={
            "HTTP_PROXY": "http://127.0.0.1:7890",
            "HTTPS_PROXY": "http://127.0.0.1:7890",
            "http_proxy": "http://127.0.0.1:7890",
            "https_proxy": "http://127.0.0.1:7890",
        }
    )
    env = agent._build_passthrough_env()
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        assert name not in env
    # 凭据仍应透传
    assert env["OPENAI_API_KEY"] == "sk-test-123"


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
    # 命令序列：jca 检查、系统依赖检查、git 配置、pip install、mkdir
    pip_cmds = [c for c in env.commands if "pip install" in c["cmd"]]
    assert len(pip_cmds) == 1
    pip_cmd = pip_cmds[0]["cmd"]
    assert "jarvis-ai-assistant" in pip_cmd
    # 绕过容器内无效代理 + 处理 PEP 668
    assert "env -u HTTP_PROXY" in pip_cmd
    assert "--break-system-packages" in pip_cmd
    # 使用国内镜像源加速下载（容器内直连 PyPI 不稳）
    assert "pypi.tuna.tsinghua.edu.cn" in pip_cmd
    assert "--quiet" not in pip_cmd
    # 从本机源码上传 builtin/prompts 补齐资源
    assert len(env.uploads) == 1
    assert env.uploads[0][1] == "/root/.jarvis/prompts"


def test_install_skips_system_deps_when_present():
    # python3/pip/git 已存在时，不应触发 apt 安装
    agent = _make_agent()
    env = _FakeEnvironment(jca_installed=False)
    _run(agent.install(env))
    apt_cmds = [c for c in env.commands if "apt-get" in c["cmd"]]
    assert apt_cmds == []


def test_install_apt_uses_mirror_and_retry_when_sys_missing():
    # python3/pip/git 缺失时，apt 应替换为国内镜像源并整体重试多轮
    agent = _make_agent()
    env = _FakeEnvironment(jca_installed=False, sys_missing=True)
    _run(agent.install(env))
    # 镜像替换命令（sed 替换官方源为阿里云）
    mirror_cmds = [c for c in env.commands if "mirrors.aliyun.com/ubuntu" in c["cmd"]]
    assert len(mirror_cmds) == 1
    assert "archive.ubuntu.com" in mirror_cmds[0]["cmd"]
    # apt 安装命令：绕过代理 + 整体重试循环
    apt_cmds = [c for c in env.commands if "apt-get" in c["cmd"]]
    assert len(apt_cmds) == 1
    apt_cmd = apt_cmds[0]["cmd"]
    assert "env -u HTTP_PROXY" in apt_cmd
    assert "for i in 1 2 3" in apt_cmd
    assert "done_apt=1; break" in apt_cmd


def test_install_uses_offline_wheelhouse_when_configured(tmp_path):
    # 设置 JARVIS_WHEELHOUSE_DIR 时，走离线 wheelhouse 安装：
    # 上传 wheelhouse 到容器 + --no-index --find-links 完全离线安装
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    (wheelhouse / "jarvis_ai_assistant-6.0.10-py3-none-any.whl").write_text("x")
    agent = _make_agent(extra_env={"JARVIS_WHEELHOUSE_DIR": str(wheelhouse)})
    env = _FakeEnvironment(jca_installed=False)
    _run(agent.install(env))

    # 应上传 wheelhouse 到容器 /tmp/jarvis-wheelhouse
    wh_uploads = [u for u in env.uploads if "wheelhouse" in u[1]]
    assert len(wh_uploads) == 1
    assert wh_uploads[0][1] == "/tmp/jarvis-wheelhouse"

    # pip 命令应为离线安装：--no-index --find-links
    pip_cmds = [c for c in env.commands if "pip install" in c["cmd"]]
    assert len(pip_cmds) == 1
    pip_cmd = pip_cmds[0]["cmd"]
    assert "--no-index" in pip_cmd
    assert "--find-links=/tmp/jarvis-wheelhouse" in pip_cmd
    assert "jarvis-ai-assistant" in pip_cmd
    # 离线安装不应出现任何在线镜像源
    assert "pypi.tuna.tsinghua.edu.cn" not in pip_cmd
    assert "pypi.org" not in pip_cmd


def test_wheelhouse_dir_none_when_unset():
    # 未设置 JARVIS_WHEELHOUSE_DIR 时返回 None（回退在线安装）
    agent = _make_agent()
    assert agent._wheelhouse_dir() is None


def test_wheelhouse_dir_none_when_missing_dir(tmp_path):
    # 设置但目录不存在时返回 None
    agent = _make_agent(
        extra_env={"JARVIS_WHEELHOUSE_DIR": str(tmp_path / "nope")}
    )
    assert agent._wheelhouse_dir() is None

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
    # 启动 jca 前必须清除容器内指向自身 loopback 的代理变量（强制直连）
    assert "env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy" in run_cmd
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
