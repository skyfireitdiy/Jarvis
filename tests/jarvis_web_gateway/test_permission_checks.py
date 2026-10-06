# -*- coding: utf-8 -*-
"""权限/ACL 落地缺口修复测试。

覆盖：
1. 无 agent:create 权限的非 admin 用户创建 Agent 被拒（PERMISSION_DENIED）
2. 无 timer:* 权限的非 admin 用户创建定时器被拒（PERMISSION_DENIED）
3. 拥有 sys-operator 组（含 agent:create / timer:*）的用户可正常创建
4. admin 用户不受权限校验影响（check_permission 对 admin 自动放行）
5. 网关 system token（JARVIS_AUTH_TOKEN）不受权限校验影响

依赖 conftest.py 的 isolated_data_dir / auth_token fixture 隔离数据目录。
"""

import os

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def perm_client_factory():
    """返回工厂：先创建用户并分配权限组，再创建 TestClient。

    必须在 create_app() 之前创建用户/权限，否则 app 闭包内的
    UserManager / PermissionManager 内存状态不会加载新数据。
    """
    from jarvis.jarvis_web_gateway.user_manager import UserManager
    from jarvis.jarvis_web_gateway.permission_manager import PermissionManager
    from jarvis.jarvis_utils.config import get_data_dir
    from jarvis.jarvis_web_gateway.app import create_app

    def _make(setup=None):
        data_dir = get_data_dir()
        um = UserManager(data_dir)
        pm = PermissionManager(data_dir)
        pm.set_user_manager(um)
        if setup:
            setup(um, pm)
        return TestClient(create_app()), um, pm

    return _make


def _login(client, username, password):
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True, body
    token = body["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _create_user(um, username, password):
    um.create_user(username, password)
    return um.get_user_by_username(username)


def _timer_payload():
    return {
        "schedule": {"delay_seconds": 3600},
        "action": {
            "type": "run_shell_command",
            "params": {
                "command": "echo hi",
                "working_dir": "/tmp",
                "interpreter": "bash",
            },
        },
    }


def _agent_payload():
    return {"agent_type": "code", "working_dir": "/tmp"}


# ---------------------------------------------------------------------------
# 无权限用户被拒
# ---------------------------------------------------------------------------
def test_no_permission_user_cannot_create_agent(perm_client_factory, monkeypatch):
    """无 agent:create 权限的非 admin 用户创建 Agent 应被拒。"""
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "AdminStrongPass1!")

    def setup(um, pm):
        _create_user(um, "noperm", "NoPermPass1!")

    client, _, _ = perm_client_factory(setup)
    headers = _login(client, "noperm", "NoPermPass1!")
    resp = client.post("/api/agents", headers=headers, json=_agent_payload())
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "PERMISSION_DENIED"
    assert "agent:create" in body["error"]["message"]


def test_no_permission_user_cannot_create_timer(perm_client_factory, monkeypatch):
    """无 timer:* 权限的非 admin 用户创建定时器应被拒。"""
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "AdminStrongPass1!")

    def setup(um, pm):
        _create_user(um, "noperm", "NoPermPass1!")

    client, _, _ = perm_client_factory(setup)
    headers = _login(client, "noperm", "NoPermPass1!")
    resp = client.post("/api/timers", headers=headers, json=_timer_payload())
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "PERMISSION_DENIED"
    assert "timer:create" in body["error"]["message"]


# ---------------------------------------------------------------------------
# 有权限用户（sys-operator）授权路径
# ---------------------------------------------------------------------------
def test_operator_can_create_timer(perm_client_factory, monkeypatch):
    """sys-operator 组（含 timer:*）用户可正常创建定时器。"""
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "AdminStrongPass1!")

    def setup(um, pm):
        op = _create_user(um, "operator", "OpPass1!")
        pm.set_user_groups(op["user_id"], ["sys-operator"])

    client, _, _ = perm_client_factory(setup)
    headers = _login(client, "operator", "OpPass1!")
    resp = client.post("/api/timers", headers=headers, json=_timer_payload())
    body = resp.json()
    assert body["success"] is True, body
    timer_id = body["data"]["task_id"]
    # 清理
    resp_del = client.delete(f"/api/timers/{timer_id}", headers=headers)
    assert resp_del.json()["success"] is True


def test_operator_can_create_agent(perm_client_factory, monkeypatch):
    """sys-operator 组（含 agent:create）用户可正常创建 Agent。"""
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "AdminStrongPass1!")

    def setup(um, pm):
        op = _create_user(um, "operator", "OpPass1!")
        pm.set_user_groups(op["user_id"], ["sys-operator"])

    client, _, _ = perm_client_factory(setup)
    headers = _login(client, "operator", "OpPass1!")
    fake_agent = {
        "agent_id": "test-agent-op",
        "status": "running",
        "node_id": "local",
        "working_dir": "/tmp",
    }
    with patch.object(
        client.app.state.agent_manager, "create_agent", return_value=fake_agent
    ) as mock_create:
        resp = client.post("/api/agents", headers=headers, json=_agent_payload())
    body = resp.json()
    assert body["success"] is True, body
    assert mock_create.called


# ---------------------------------------------------------------------------
# admin 用户不受影响
# ---------------------------------------------------------------------------
def test_admin_can_create_timer(perm_client_factory, monkeypatch):
    """admin 用户（is_admin）创建定时器不受权限校验影响。"""
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "AdminStrongPass1!")

    client, _, _ = perm_client_factory()
    headers = _login(client, "admin", "AdminStrongPass1!")
    resp = client.post("/api/timers", headers=headers, json=_timer_payload())
    body = resp.json()
    assert body["success"] is True, body
    timer_id = body["data"]["task_id"]
    resp_del = client.delete(f"/api/timers/{timer_id}", headers=headers)
    assert resp_del.json()["success"] is True


def test_admin_can_create_agent(perm_client_factory, monkeypatch):
    """admin 用户（is_admin）创建 Agent 不受权限校验影响。"""
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "AdminStrongPass1!")

    client, _, _ = perm_client_factory()
    headers = _login(client, "admin", "AdminStrongPass1!")
    fake_agent = {
        "agent_id": "test-agent-admin",
        "status": "running",
        "node_id": "local",
        "working_dir": "/tmp",
    }
    with patch.object(
        client.app.state.agent_manager, "create_agent", return_value=fake_agent
    ) as mock_create:
        resp = client.post("/api/agents", headers=headers, json=_agent_payload())
    body = resp.json()
    assert body["success"] is True, body
    assert mock_create.called


# ---------------------------------------------------------------------------
# 网关 system token 不受影响
# ---------------------------------------------------------------------------
def test_gateway_system_token_can_create_timer(
    perm_client_factory, monkeypatch, auth_token
):
    """网关 system token（JARVIS_AUTH_TOKEN）创建定时器不受权限校验影响。"""
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "AdminStrongPass1!")

    client, _, _ = perm_client_factory()
    headers = {"Authorization": f"Bearer {auth_token}"}
    resp = client.post("/api/timers", headers=headers, json=_timer_payload())
    body = resp.json()
    assert body["success"] is True, body
    timer_id = body["data"]["task_id"]
    resp_del = client.delete(f"/api/timers/{timer_id}", headers=headers)
    assert resp_del.json()["success"] is True
