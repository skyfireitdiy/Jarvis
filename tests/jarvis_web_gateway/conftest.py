# -*- coding: utf-8 -*-
"""jarvis_web_gateway 测试的全局隔离。

为什么必须隔离（重要）：
1. ``create_app()`` 会读取 ``get_data_dir()``（默认 ``~/.jarvis``）并构造
   ``UserManager`` / ``PermissionManager`` / ``TimerManager`` / ``ChatManager``，
   这些对象会**写入** ``<data_dir>/auth/*.json``、``<data_dir>/gateway/.jarvis_timers.json``。
   线上网关进程用的是同一份真实数据目录，测试若直接跑就会改动线上用户/权限/定时器数据。
2. ``AgentManager.PERSISTENCE_FILE`` 是**模块级常量**（导入时即由 ``get_data_dir()`` 定死），
   指向 ``<data_dir>/gateway/.jarvis_agents.json``。``_load_agents()`` 会读取它，
   若其中记录的 pid 恰好存活，``delete_agent()`` 会 ``os.kill`` 真实进程。
   因此除了环境变量，还必须把该常量重定向到临时目录。
3. ``create_app()`` 会覆盖 ``os.environ["JARVIS_AUTH_TOKEN"]``，用 monkeypatch 保证测试后还原。

隔离手段：把 ``JARVIS_DATA_DIR`` 指向每个测试独立的 ``tmp_path``，
并把已导入模块里的模块级路径常量一并重定向。测试全程使用 ``TestClient``（ASGI 内存传输），
不监听任何端口，因此不会与已部署服务争抢端口。
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

# 必须在导入 jarvis 模块之前设置，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """把 Jarvis 数据目录整体重定向到临时目录，避免触碰真实 ~/.jarvis。"""
    data_dir = tmp_path / "jarvis_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("JARVIS_DATA_DIR", str(data_dir))

    # 模块级常量在导入时已定死，需显式重定向（仅对已导入的模块生效）
    from jarvis.jarvis_web_gateway import agent_manager, timer_manager

    monkeypatch.setattr(
        agent_manager.AgentManager,
        "PERSISTENCE_FILE",
        data_dir / "gateway" / ".jarvis_agents.json",
    )
    monkeypatch.setattr(
        timer_manager.TimerManager,
        "PERSISTENCE_FILE",
        data_dir / "gateway" / ".jarvis_timers.json",
    )

    yield data_dir


@pytest.fixture
def auth_token(monkeypatch):
    """为当前测试设置一个独立的网关 Token，并返回它。"""
    token = "test-token-isolated"
    monkeypatch.setenv("JARVIS_AUTH_TOKEN", token)
    return token
