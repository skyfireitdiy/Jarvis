# -*- coding: utf-8 -*-
"""子节点终端输出广播到 admin 用户的单元测试。

覆盖 NodeConnectionManager._publish_terminal_output_to_admins：
1. 子节点终端的输出应广播给所有 admin 用户（ACL 决策统一在 master）
2. 排除发起者 session_id，避免重复推送
3. 无 terminal_session_manager 时安全返回
"""

import os

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

from unittest.mock import MagicMock

from jarvis.jarvis_web_gateway.node_manager import NodeConnectionManager


def _make_manager(admin_sids, router=None):
    """构造一个带 mock terminal_session_manager 的 NodeConnectionManager。"""
    tsm = MagicMock()
    tsm.get_all_admin_session_ids.return_value = admin_sids
    return NodeConnectionManager(
        node_runtime=MagicMock(),
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_http_dispatcher=None,
        router=router or MagicMock(),
        terminal_session_manager=tsm,
    )


def test_publish_terminal_output_broadcasts_to_all_admins():
    """子节点终端输出应广播给所有 admin 用户。"""
    published = []

    class FakeRouter:
        def publish(self, message, session_id=None, connection_id=None):
            published.append(session_id)

    m = _make_manager(["session_admin-a", "session_admin-b"], router=FakeRouter())
    m._publish_terminal_output_to_admins({"type": "execution"}, "session_owner1")

    assert "session_admin-a" in published
    assert "session_admin-b" in published


def test_publish_terminal_output_excludes_initiator():
    """广播时应排除发起者 session_id，避免重复推送。"""
    published = []

    class FakeRouter:
        def publish(self, message, session_id=None, connection_id=None):
            published.append(session_id)

    # 发起者本身也是 admin
    m = _make_manager(["session_admin-a", "session_admin-b"], router=FakeRouter())
    m._publish_terminal_output_to_admins({"type": "execution"}, "session_admin-a")

    assert "session_admin-a" not in published
    assert "session_admin-b" in published


def test_publish_terminal_output_no_manager_is_safe():
    """无 terminal_session_manager 时应安全返回，不抛异常。"""
    m = NodeConnectionManager(
        node_runtime=MagicMock(),
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_http_dispatcher=None,
        router=MagicMock(),
        terminal_session_manager=None,
    )
    # 不应抛异常
    m._publish_terminal_output_to_admins({"type": "execution"}, "session_owner1")
