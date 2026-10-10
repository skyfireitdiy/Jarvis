# -*- coding: utf-8 -*-
"""Agent 运行时配置更新（update_agent_runtime_config）单元测试。

覆盖 Issue #115 的网关侧实现：
1. 更新模型组（llm_group）并持久化
2. 更新代理节点（proxy_node）并持久化
3. 清空代理节点（proxy_node=""）后前端展示为未使用代理
4. 不存在的 Agent 抛 KeyError
5. 只更新单个字段时另一字段保持不变
"""
import json

import pytest

from jarvis.jarvis_web_gateway.agent_manager import AgentInfo, AgentManager


def _make_manager(tmp_path, monkeypatch) -> AgentManager:
    """构造一个数据目录隔离的 AgentManager，并注入一个 AgentInfo。"""
    data_dir = tmp_path / "jarvis_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("JARVIS_DATA_DIR", str(data_dir))
    monkeypatch.setattr(
        AgentManager,
        "PERSISTENCE_FILE",
        data_dir / "gateway" / ".jarvis_agents.json",
    )
    manager = AgentManager()
    agent = AgentInfo(
        agent_id="agent-test-1",
        agent_type="agent",
        pid=0,
        port=10000,
        working_dir=str(tmp_path),
        process=None,
        name="test-agent",
        llm_group="default",
        proxy_node=None,
    )
    manager._agents[agent.agent_id] = agent
    return manager


def test_update_llm_group(tmp_path, monkeypatch):
    """更新模型组后内存与持久化文件均应生效。"""
    manager = _make_manager(tmp_path, monkeypatch)
    result = manager.update_agent_runtime_config(
        "agent-test-1", llm_group="new_group"
    )
    assert result["llm_group"] == "new_group"
    assert manager._agents["agent-test-1"].llm_group == "new_group"
    # 持久化文件已写入
    saved = json.loads(AgentManager.PERSISTENCE_FILE.read_text(encoding="utf-8"))
    assert saved[0]["llm_group"] == "new_group"


def test_update_proxy_node(tmp_path, monkeypatch):
    """更新代理节点后内存与持久化文件均应生效。"""
    manager = _make_manager(tmp_path, monkeypatch)
    result = manager.update_agent_runtime_config(
        "agent-test-1", proxy_node="node-2"
    )
    assert result["proxy_node"] == "node-2"
    assert manager._agents["agent-test-1"].proxy_node == "node-2"
    saved = json.loads(AgentManager.PERSISTENCE_FILE.read_text(encoding="utf-8"))
    assert saved[0]["proxy_node"] == "node-2"


def test_clear_proxy_node(tmp_path, monkeypatch):
    """清空代理节点（proxy_node=""）后前端 v-if 视为未使用代理。"""
    manager = _make_manager(tmp_path, monkeypatch)
    manager._agents["agent-test-1"].proxy_node = "node-1"
    result = manager.update_agent_runtime_config("agent-test-1", proxy_node="")
    assert result["proxy_node"] == ""
    assert manager._agents["agent-test-1"].proxy_node == ""
    saved = json.loads(AgentManager.PERSISTENCE_FILE.read_text(encoding="utf-8"))
    assert saved[0]["proxy_node"] == ""
    # 前端 AgentSidebar.vue 使用 v-if="agent.proxy_node"，空字符串不显示
    assert not saved[0]["proxy_node"]


def test_update_only_one_field_preserves_other(tmp_path, monkeypatch):
    """只更新 llm_group 时 proxy_node 保持不变。"""
    manager = _make_manager(tmp_path, monkeypatch)
    manager._agents["agent-test-1"].proxy_node = "node-1"
    result = manager.update_agent_runtime_config(
        "agent-test-1", llm_group="new_group"
    )
    assert result["llm_group"] == "new_group"
    assert result["proxy_node"] == "node-1"


def test_update_nonexistent_agent_raises_keyerror(tmp_path, monkeypatch):
    """更新不存在的 Agent 应抛 KeyError。"""
    manager = _make_manager(tmp_path, monkeypatch)
    with pytest.raises(KeyError):
        manager.update_agent_runtime_config("agent-not-exist", llm_group="x")
