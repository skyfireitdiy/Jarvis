# -*- coding: utf-8 -*-
"""Agent --master-url 选择逻辑单元测试。

覆盖子节点 Agent 上报目标修复：
1. master 节点（不传 local_gateway_url）→ 使用 jglobals.master_url（本机网关）
2. 子节点（传 local_gateway_url）→ 使用本机网关地址，即使 jglobals.master_url 指向 master
3. 子节点且 jglobals.master_url 指向 master → 仍使用本机网关地址（核心修复点）
4. 两者均为空 → 不添加 --master-url 参数
"""
from unittest.mock import patch

from jarvis.jarvis_utils import globals as jglobals
from jarvis.jarvis_web_gateway.agent_manager import AgentManager


def _build(local_gateway_url):
    """构造 AgentManager 并构建命令，返回 --master-url 的值（无则返回 None）。"""
    with patch.object(
        AgentManager,
        "_get_agent_entry_points",
        return_value={"agent": "jarvis-agent"},
    ), patch("jarvis.jarvis_web_gateway.agent_manager.shutil.which", return_value="jarvis-agent"):
        manager = AgentManager(local_gateway_url=local_gateway_url)
        cmd = manager._build_command(
            agent_type="agent",
            port=10000,
            llm_group="default",
            tool_group="default",
            config_file=None,
            task=None,
            additional_args=None,
            agent_id="test-1",
        )
    if "--master-url" in cmd:
        return cmd[cmd.index("--master-url") + 1]
    return None


def test_master_node_uses_global_master_url():
    """master 节点不传 local_gateway_url，应使用 jglobals.master_url（本机网关）。"""
    jglobals.master_url = "http://127.0.0.1:8000"
    try:
        assert _build(None) == "http://127.0.0.1:8000"
    finally:
        jglobals.master_url = None


def test_child_node_uses_local_gateway_url():
    """子节点传 local_gateway_url，应优先使用本机网关地址。"""
    jglobals.master_url = "https://jvs-ai.cn:4443"
    try:
        assert _build("http://127.0.0.1:9000") == "http://127.0.0.1:9000"
    finally:
        jglobals.master_url = None


def test_child_node_ignores_master_pointing_url():
    """核心修复点：子节点 jglobals.master_url 指向 master 时，agent 仍上报本机网关。"""
    jglobals.master_url = "https://jvs-ai.cn:4443"
    try:
        assert _build("http://127.0.0.1:9000") == "http://127.0.0.1:9000"
        assert _build("http://127.0.0.1:9000") != jglobals.master_url
    finally:
        jglobals.master_url = None


def test_no_master_url_when_both_empty():
    """local_gateway_url 与 jglobals.master_url 均为空时，不添加 --master-url。"""
    jglobals.master_url = None
    try:
        assert _build(None) is None
    finally:
        jglobals.master_url = None
