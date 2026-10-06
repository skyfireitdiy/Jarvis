# -*- coding: utf-8 -*-
"""集成终端 ACL 单元测试。

覆盖 TerminalSessionManager 的 ACL 逻辑：
1. owner 可设置 ACL（set_access_acl），非 owner 被拒
2. set_access_acl 自动过滤 owner 自身与 admin 用户
3. read 用户可 attach 但不能交互（attach 返回 "read"）
4. interact 用户可 attach 且可交互（attach 返回 "interact"）
5. 非 ACL 用户 attach 被拒（返回 None）
6. admin / system 用户放行（视为 owner）
7. list_sessions_for_user 返回 owner 会话 + 被分享会话（带 access 级别）

不依赖真实 PTY：直接构造 TerminalSession 对象注入 manager._sessions。
"""

import os

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import pytest
from unittest.mock import patch

from jarvis.jarvis_web_gateway.terminal_session_manager import (
    TerminalSession,
    TerminalSessionManager,
)


def _make_session(terminal_id, owner_id, acl=None, session_id=None):
    """构造一个无真实 PTY 的会话对象（仅用于 ACL 逻辑测试）。"""
    return TerminalSession(
        terminal_id=terminal_id,
        interpreter="bash",
        working_dir=".",
        session_id=session_id or f"session_{owner_id}",
        owner_id=owner_id,
        access_acl=acl or {},
    )


@pytest.fixture
def manager():
    m = TerminalSessionManager()
    m._sessions["term-1"] = _make_session("term-1", "owner1")
    return m


def test_owner_can_set_acl(manager):
    ok = manager.set_access_acl(
        "term-1", "owner1", {"read": ["u1"], "interact": ["u2"]}
    )
    assert ok is True
    info = manager.get_session_info("term-1")
    assert info["access_acl"] == {"read": ["u1"], "interact": ["u2"]}


def test_non_owner_cannot_set_acl(manager):
    ok = manager.set_access_acl("term-1", "intruder", {"read": ["u1"]})
    assert ok is False
    info = manager.get_session_info("term-1")
    assert info["access_acl"] == {}


def test_set_acl_filters_owner_and_admin(manager):
    # admin user_id 为 "admin-u"（由 _get_admin_user_id 返回）
    with patch.object(manager, "_get_admin_user_id", return_value="admin-u"):
        ok = manager.set_access_acl(
            "term-1",
            "owner1",
            {"read": ["owner1", "admin-u", "u1", "u1"], "interact": ["u2"]},
        )
    assert ok is True
    info = manager.get_session_info("term-1")
    # owner 自身与 admin 被过滤，重复项去重
    assert info["access_acl"] == {"read": ["u1"], "interact": ["u2"]}


def test_read_user_can_attach_but_not_interact(manager):
    manager.set_access_acl("term-1", "owner1", {"read": ["reader"], "interact": []})
    # attach 返回 "read"
    assert manager.attach_session("term-1", "session_reader") == "read"
    # 交互校验（check_access need_interact=True）返回 "read"，非 interact 级别
    assert manager.check_access("term-1", "reader", need_interact=True) == "read"


def test_interact_user_can_attach_and_interact(manager):
    manager.set_access_acl("term-1", "owner1", {"read": [], "interact": ["writer"]})
    assert manager.attach_session("term-1", "session_writer") == "interact"
    assert manager.check_access("term-1", "writer", need_interact=True) == "interact"


def test_non_acl_user_rejected(manager):
    manager.set_access_acl(
        "term-1", "owner1", {"read": ["reader"], "interact": ["writer"]}
    )
    assert manager.attach_session("term-1", "session_stranger") is None
    assert manager.check_access("term-1", "stranger", need_interact=False) is None


def test_admin_and_system_are_owner(manager):
    manager.set_access_acl("term-1", "owner1", {"read": [], "interact": []})
    # system 用户放行
    assert manager.attach_session("term-1", "system") == "owner"
    # admin 用户放行（_is_admin_user 返回 True）
    with patch.object(manager, "_is_admin_user", return_value=True):
        assert manager.attach_session("term-1", "session_admin") == "owner"


def test_owner_attach_returns_owner(manager):
    assert manager.attach_session("term-1", "session_owner1") == "owner"


def test_attach_nonexistent_returns_none(manager):
    assert manager.attach_session("term-999", "session_owner1") is None


def test_list_sessions_for_user_includes_owner_and_shared(manager):
    # owner1 拥有 term-1；再建一个分享给 reader 的会话
    manager._sessions["term-2"] = _make_session(
        "term-2", "owner2", acl={"read": ["reader"], "interact": []}
    )
    # 未分享给 reader 的会话
    manager._sessions["term-3"] = _make_session("term-3", "owner3")

    # 给 term-1 设置 ACL 让 reader 可见
    manager.set_access_acl("term-1", "owner1", {"read": ["reader"], "interact": []})

    sessions = manager.list_sessions_for_user("session_reader")
    ids = {s["terminal_id"]: s for s in sessions}
    # reader 可见 term-1（read）与 term-2（read），不可见 term-3
    assert set(ids.keys()) == {"term-1", "term-2"}
    assert ids["term-1"]["access"] == "read"
    assert ids["term-2"]["access"] == "read"
    # owner 视角：可见自己拥有的 term-1
    owner_sessions = manager.list_sessions_for_user("session_owner1")
    owner_ids = {s["terminal_id"]: s["access"] for s in owner_sessions}
    assert owner_ids["term-1"] == "owner"


def test_get_access_session_ids_includes_owner_and_acl_users(manager):
    """_get_access_session_ids 应返回 owner + 被分享（read/interact）用户的 session_id。"""
    manager.set_access_acl(
        "term-1", "owner1", {"read": ["reader"], "interact": ["writer"]}
    )
    session = manager.get_session("term-1")
    ids = session._get_access_session_ids()
    assert "session_owner1" in ids
    assert "session_reader" in ids
    assert "session_writer" in ids
    # 去重：owner 不应重复
    assert len(ids) == len(set(ids))


def test_get_access_session_ids_no_acl_only_owner(manager):
    """无 ACL 时只返回 owner 的 session_id。"""
    session = manager.get_session("term-1")
    assert session._get_access_session_ids() == ["session_owner1"]


def test_publish_output_sends_to_all_access_users(manager):
    """_publish_output 应把实时输出推送给 owner 与所有被分享用户（修复跨设备/分享看不到内容）。"""
    published = []

    class FakeRouter:
        def publish(self, message, session_id=None, connection_id=None):
            published.append((session_id, message.get("type")))

    manager.set_access_acl(
        "term-1", "owner1", {"read": ["reader"], "interact": ["writer"]}
    )
    session = manager.get_session("term-1")
    session.stream_publisher = FakeRouter()
    session._publish_output(b"hello realtime")

    target_sids = {sid for sid, _ in published}
    assert "session_owner1" in target_sids
    assert "session_reader" in target_sids
    assert "session_writer" in target_sids
    # 每个 session_id 都收到 execution 消息
    assert all(mtype == "execution" for _, mtype in published)


def test_attach_records_admin_user_for_realtime_output(manager):
    """admin 用户（不同账号）attach 后应被记录，使其能收到实时输出。

    根因：admin 用户经 _access_level 被放行（视为 owner），能看到终端、能输入，
    但 _get_access_session_ids 之前只返回 owner + ACL，不含 admin，导致
    实时输出不推送给 admin 用户（第二台设备看不到输出）。
    """
    session = manager.get_session("term-1")
    # admin 用户 attach（_is_admin_user 返回 True 视为 owner）
    with patch.object(manager, "_is_admin_user", return_value=True):
        assert manager.attach_session("term-1", "session_admin2") == "owner"
    ids = session._get_access_session_ids()
    assert "session_admin2" in ids


def test_attach_records_acl_user_for_realtime_output(manager):
    """attach 过的 ACL 用户应被记录，实时输出能送达（含共享用户）。"""
    manager.set_access_acl("term-1", "owner1", {"read": ["reader"], "interact": []})
    assert manager.attach_session("term-1", "session_reader") == "read"
    session = manager.get_session("term-1")
    ids = session._get_access_session_ids()
    assert "session_reader" in ids


def test_attach_rejected_user_not_recorded(manager):
    """无权限用户 attach 被拒，不应被记录（不泄露实时输出）。"""
    manager.set_access_acl("term-1", "owner1", {"read": [], "interact": []})
    assert manager.attach_session("term-1", "session_stranger") is None
    session = manager.get_session("term-1")
    assert "session_stranger" not in session._get_access_session_ids()


def test_publish_output_sends_to_admin_after_attach(manager):
    """admin 用户 attach 后，_publish_output 应把实时输出推送给它。"""
    published = []

    class FakeRouter:
        def publish(self, message, session_id=None, connection_id=None):
            published.append(session_id)

    session = manager.get_session("term-1")
    with patch.object(manager, "_is_admin_user", return_value=True):
        assert manager.attach_session("term-1", "session_admin2") == "owner"
    session.stream_publisher = FakeRouter()
    session._publish_output(b"hello admin")
    assert "session_admin2" in published


def test_get_all_admin_session_ids_returns_admin_sessions(manager):
    """get_all_admin_session_ids 应返回所有 admin 用户的 session_id（用于终端事件广播）。"""
    fake_users = [
        {"user_id": "admin-a", "is_admin": True},
        {"user_id": "admin-b", "is_admin": True},
        {"user_id": "normal-u", "is_admin": False},
    ]

    class FakeUserManager:
        def list_users(self, limit=50):
            return fake_users

    with patch(
        "jarvis.jarvis_web_gateway.user_manager.UserManager",
        return_value=FakeUserManager(),
    ):
        sids = manager.get_all_admin_session_ids()
    assert "session_admin-a" in sids
    assert "session_admin-b" in sids
    # 非 admin 用户不应包含
    assert "session_normal-u" not in sids


def test_get_access_session_ids_falls_back_to_session_id_for_child_node(manager):
    """子节点终端 owner_id 为空时应回退到 session_id，避免输出无人接收。

    根因：Bug 1 修复后 _publish_output 改为遍历 _get_access_session_ids，
    但子节点创建终端时未传 owner_id（owner_id 为空），导致 _get_access_session_ids
    返回空列表，输出全部丢失（表现为"只有标签和空的 xterm"）。
    """
    # 模拟子节点终端：owner_id 为空，但 session_id 有值（session_{user_id}）
    session = TerminalSession(
        terminal_id="child-term",
        interpreter="bash",
        working_dir=".",
        session_id="session_owner1",
        owner_id="",
        access_acl={},
    )
    assert session._get_access_session_ids() == ["session_owner1"]


def test_publish_output_falls_back_to_session_id_for_child_node(manager):
    """子节点终端（owner_id 为空）的 _publish_output 应回退到 session_id 推送输出。"""
    published = []

    class FakeRouter:
        def publish(self, message, session_id=None, connection_id=None):
            published.append(session_id)

    session = TerminalSession(
        terminal_id="child-term",
        interpreter="bash",
        working_dir=".",
        session_id="session_owner1",
        owner_id="",
        access_acl={},
    )
    session.stream_publisher = FakeRouter()
    session._publish_output(b"hello child node")
    assert "session_owner1" in published


def test_register_remote_session_appears_in_list_for_user():
    """master 登记子节点终端影子会话后，list_sessions_for_user 应返回并带 node_id。"""
    m = TerminalSessionManager()
    m.register_remote_session(
        terminal_id="child-term",
        node_id="node-2",
        owner_id="owner1",
        session_id="session_owner1",
    )
    sessions = m.list_sessions_for_user("session_owner1")
    assert any(s["terminal_id"] == "child-term" for s in sessions)
    child = next(s for s in sessions if s["terminal_id"] == "child-term")
    assert child["node_id"] == "node-2"
    assert child["owner_id"] == "owner1"
    assert child["access"] == "owner"


def test_register_remote_session_visible_to_admin():
    """admin 用户应能看到 master 登记的子节点终端影子会话（_access_level 放行）。"""
    m = TerminalSessionManager()
    m.register_remote_session(
        terminal_id="child-term",
        node_id="node-2",
        owner_id="owner1",
        session_id="session_owner1",
    )
    with patch.object(TerminalSessionManager, "_is_admin_user", return_value=True):
        sessions = m.list_sessions_for_user("session_admin2")
    assert any(s["terminal_id"] == "child-term" for s in sessions)


def test_unregister_remote_session_removes():
    """unregister_session 应移除 master 登记的子节点终端影子会话。"""
    m = TerminalSessionManager()
    m.register_remote_session(
        terminal_id="child-term",
        node_id="node-2",
        owner_id="owner1",
        session_id="session_owner1",
    )
    m.unregister_session("child-term")
    sessions = m.list_sessions_for_user("session_owner1")
    assert not any(s["terminal_id"] == "child-term" for s in sessions)


def test_register_remote_session_attach_returns_owner():
    """影子会话（子节点终端）attach 应返回 owner（供前端恢复时记录）。"""
    m = TerminalSessionManager()
    m.register_remote_session(
        terminal_id="child-term",
        node_id="node-2",
        owner_id="owner1",
        session_id="session_owner1",
    )
    assert m.attach_session("child-term", "session_owner1") == "owner"
