# -*- coding: utf-8 -*-
"""UserManager 初始无密码安全与首次登录强制改密测试。

覆盖：
1. 无 JARVIS_ADMIN_PASSWORD 时 admin 初始为无密码状态，must_change_password=True，
   日志不含任何密码明文
2. 无密码 admin 允许以空密码登录
3. 显式设置 JARVIS_ADMIN_PASSWORD 的 admin 有密码、不强制改密、需密码登录
4. change_password 对 must_change_password=True 用户跳过旧密码验证并清除标记
5. change_password 对普通用户仍需旧密码验证
6. 登录接口返回的 user 包含 must_change_password 标记
7. 改密接口对 must_change_password 用户不强制要求旧密码
8. 鉴权拦截：must_change 用户调用普通接口被 403 拒绝，改密接口放行，改密后恢复正常
"""

import logging
import os

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import pytest
from fastapi.testclient import TestClient

from jarvis.jarvis_web_gateway.user_manager import UserManager


# ---------------------------------------------------------------------------
# 单元测试：UserManager 直接测试
# ---------------------------------------------------------------------------


def test_admin_no_password_not_logged(tmp_path, monkeypatch):
    """无 JARVIS_ADMIN_PASSWORD 时 admin 无密码、must_change_password=True，日志无密码明文。"""
    monkeypatch.delenv("JARVIS_ADMIN_PASSWORD", raising=False)

    records = []

    class _CapturingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _CapturingHandler()
    logger = logging.getLogger("jarvis.jarvis_web_gateway.user_manager")
    logger.addHandler(handler)
    try:
        um = UserManager(str(tmp_path))
    finally:
        logger.removeHandler(handler)

    admin = um.get_user_by_username("admin")
    assert admin is not None
    assert admin.get("is_admin") is True
    assert admin.get("must_change_password") is True

    # 日志不含任何疑似密码明文（16 位十六进制随机串）
    joined = "\n".join(records)
    assert "admin starts with no password" in joined
    import re

    assert not re.search(r"\b[0-9a-f]{16}\b", joined), f"密码被打印到日志: {joined}"


def test_admin_empty_password_login(tmp_path, monkeypatch):
    """无密码 admin 允许空密码登录，拒绝非空密码。"""
    monkeypatch.delenv("JARVIS_ADMIN_PASSWORD", raising=False)
    um = UserManager(str(tmp_path))
    # 空密码登录成功
    assert um.authenticate("admin", "") is not None
    # 非空密码登录失败
    assert um.authenticate("admin", "anything") is None


def test_explicit_admin_password_no_must_change(tmp_path, monkeypatch):
    """显式设置 JARVIS_ADMIN_PASSWORD 时，admin 有密码、不强制改密、需密码登录。"""
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "ExplicitStrongPass1!")
    um = UserManager(str(tmp_path))
    admin = um.get_user_by_username("admin")
    assert admin is not None
    assert admin.get("must_change_password") is False
    # 需密码登录，空密码失败
    assert um.authenticate("admin", "") is None
    assert um.authenticate("admin", "ExplicitStrongPass1!") is not None


def test_change_password_skips_old_for_must_change(tmp_path, monkeypatch):
    """must_change_password=True 的用户改密时跳过旧密码验证，改密后清除标记。"""
    monkeypatch.delenv("JARVIS_ADMIN_PASSWORD", raising=False)
    um = UserManager(str(tmp_path))
    admin = um.get_user_by_username("admin")
    assert admin is not None
    assert admin.get("must_change_password") is True

    # 用错误的旧密码也应能改密成功（跳过验证）
    ok = um.change_password(admin["user_id"], "wrong-old-password", "NewStrongPass1!")
    assert ok is True

    # 改密后标记清除，且可用新密码登录、空密码不再可登录
    updated = um.get_user(admin["user_id"])
    assert updated is not None
    assert updated.get("must_change_password") is False
    assert um.authenticate("admin", "NewStrongPass1!") is not None
    assert um.authenticate("admin", "") is None


def test_change_password_requires_old_for_normal_user(tmp_path, monkeypatch):
    """普通用户（must_change_password=False）改密仍需验证旧密码。"""
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "ExplicitStrongPass1!")
    um = UserManager(str(tmp_path))
    um.create_user("alice", "AliceOldPass1!")

    alice = um.get_user_by_username("alice")
    assert alice is not None
    assert alice.get("must_change_password") is False

    # 错误旧密码应失败
    assert um.change_password(alice["user_id"], "wrong", "NewPass1!") is False
    # 正确旧密码应成功
    assert um.change_password(alice["user_id"], "AliceOldPass1!", "NewPass1!") is True
    assert um.authenticate("alice", "NewPass1!") is not None


# ---------------------------------------------------------------------------
# 集成测试：登录、改密与鉴权拦截接口
# ---------------------------------------------------------------------------


@pytest.fixture
def client_factory():
    """返回一个工厂：先通过 UserManager 创建用户，再创建 TestClient。

    必须在 create_app() 之前创建用户，否则 app 闭包内的 UserManager 内存
    状态不会加载到新用户（不同 UserManager 实例各自维护内存 _users）。
    """

    def _make(setup=None):
        from jarvis.jarvis_web_gateway.user_manager import UserManager
        from jarvis.jarvis_utils.config import get_data_dir

        um = UserManager(get_data_dir())
        if setup:
            setup(um)
        from jarvis.jarvis_web_gateway.app import create_app

        return TestClient(create_app()), um

    return _make


def _login(client, username, password=""):
    """登录并返回 headers。"""
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True, body
    token = body["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_returns_must_change_password(client_factory):
    """登录接口返回的 user 应包含 must_change_password 标记。"""

    def setup(um):
        um.create_user("bob", "", is_admin=False, must_change_password=True)

    client, _ = client_factory(setup)

    resp = client.post("/api/auth/login", json={"username": "bob", "password": ""})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["user"]["must_change_password"] is True


def test_must_change_user_blocked_until_password_set(client_factory):
    """鉴权拦截：must_change 用户调用普通接口被 403，改密接口放行，改密后恢复正常。"""

    def setup(um):
        um.create_user("carol", "", must_change_password=True)

    client, um = client_factory(setup)
    carol = um.get_user_by_username("carol")
    assert carol is not None

    # 无密码登录
    headers = _login(client, "carol", "")

    # 调用普通接口（获取用户列表）应被 403 拦截
    resp = client.get("/api/users", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "FORCE_PASSWORD_CHANGE"

    # 改密接口应放行（不传旧密码）
    resp = client.post(
        f"/api/users/{carol['user_id']}/change-password",
        json={"new_password": "CarolNewPass1!"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 改密后 must_change_password 标记已清除（重新加载验证文件中的状态）
    from jarvis.jarvis_web_gateway.user_manager import UserManager
    from jarvis.jarvis_utils.config import get_data_dir

    fresh = UserManager(get_data_dir())
    updated = fresh.get_user(carol["user_id"])
    assert updated is not None
    assert updated.get("must_change_password") is False

    # 改密后普通接口不再被强制改密拦截（进入正常权限校验，carol 非 admin 返回权限不足）
    resp = client.get("/api/users", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "PERMISSION_DENIED"


def test_change_password_api_skips_old_when_must_change(client_factory):
    """改密接口对 must_change_password 用户不强制要求旧密码。"""

    def setup(um):
        um.create_user("erin", "", must_change_password=True)

    client, um = client_factory(setup)
    erin = um.get_user_by_username("erin")
    assert erin is not None

    headers = _login(client, "erin", "")
    resp = client.post(
        f"/api/users/{erin['user_id']}/change-password",
        json={"new_password": "ErinNewPass1!"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_change_password_api_requires_old_for_normal(client_factory):
    """改密接口对普通用户仍要求提供旧密码。"""

    def setup(um):
        um.create_user("dave", "DaveOldPass1!")

    client, um = client_factory(setup)
    dave = um.get_user_by_username("dave")
    assert dave is not None

    headers = _login(client, "dave", "DaveOldPass1!")

    # 不传旧密码应失败
    resp = client.post(
        f"/api/users/{dave['user_id']}/change-password",
        json={"new_password": "DaveNewPass1!"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert resp.json()["error"]["code"] == "INVALID_INPUT"
