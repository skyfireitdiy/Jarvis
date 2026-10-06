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
