# -*- coding: utf-8 -*-
"""pipeline 跨进程事件桥接测试。

覆盖：
1. /api/pipeline-events 接收事件并写入网关进程事件总线（事件泵可读到）；
2. 无 file:read 权限的非 admin 用户被拒（403 / PERMISSION_DENIED）；
3. admin 用户可正常上报；
4. 非法 body（非 list）返回错误；
5. pipeline_runner._emit 在本地泵激活时不上报远程（避免重复）；
6. emit_remote 在网关不可达时静默失败（不影响执行语义）。
"""
import os

os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import pytest
from fastapi.testclient import TestClient

from jarvis.jarvis_tools.pipeline_events import (
    emit_remote,
    get_event_bus,
    is_local_pump_active,
    set_local_pump_active,
)


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
    return {"Authorization": f"Bearer {body['data']['token']}"}


def _make_admin_client(perm_client_factory, monkeypatch):
    """创建 admin 登录的 TestClient。"""
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "AdminStrongPass1!")
    client, _, _ = perm_client_factory()
    return client, _login(client, "admin", "AdminStrongPass1!")


def _sample_event():
    return {
        "pipeline_id": "test-pipeline-123456",
        "type": "pipeline_start",
        "orchestration_file": "/tmp/simple_demo.yaml",
        "working_dir": "/tmp",
        "nodes": [
            {
                "stage": "planner",
                "agent": "planner",
                "depends_on": [],
                "input": [],
                "output": "plan.md",
            },
            {
                "stage": "worker_a",
                "agent": "worker_a",
                "depends_on": ["planner"],
                "input": [],
                "output": "a.md",
            },
            {
                "stage": "worker_b",
                "agent": "worker_b",
                "depends_on": ["planner"],
                "input": [],
                "output": "b.md",
            },
            {
                "stage": "aggregator",
                "agent": "aggregator",
                "depends_on": ["worker_a", "worker_b"],
                "input": [],
                "output": "final.md",
            },
        ],
    }


class TestPipelineEventsIngest:
    def test_admin_can_ingest_events(self, perm_client_factory, monkeypatch):
        """admin 用户上报事件成功，且事件写入网关进程事件总线。"""
        client, headers = _make_admin_client(perm_client_factory, monkeypatch)
        # 清空总线，确保测试前无残留
        get_event_bus().drain()
        resp = client.post(
            "/api/pipeline-events",
            headers=headers,
            json={"events": [_sample_event()]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["ingested"] == 1
        # 事件应写入网关进程事件总线（事件泵可读到）
        events = get_event_bus().drain()
        assert len(events) == 1
        assert events[0]["pipeline_id"] == "test-pipeline-123456"
        assert events[0]["type"] == "pipeline_start"

    def test_invalid_body_rejected(self, perm_client_factory, monkeypatch):
        """events 非 list 时返回错误。"""
        client, headers = _make_admin_client(perm_client_factory, monkeypatch)
        resp = client.post(
            "/api/pipeline-events",
            headers=headers,
            json={"events": "not-a-list"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is False

    def test_no_permission_user_rejected(self, perm_client_factory, monkeypatch):
        """无 file:read 权限的非 admin 用户被拒。"""
        from tests.jarvis_web_gateway.test_permission_checks import _create_user

        monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "AdminStrongPass1!")

        def setup(um, pm):
            _create_user(um, "noperm", "NoPermPass1!")

        client, _, _ = perm_client_factory(setup)
        headers = _login(client, "noperm", "NoPermPass1!")
        resp = client.post(
            "/api/pipeline-events",
            headers=headers,
            json={"events": [_sample_event()]},
        )
        assert resp.status_code == 403, resp.text


class TestEmitRemote:
    def test_no_master_url_returns_false(self, monkeypatch):
        """无 master_url 时 emit_remote 安全返回 False。"""
        import jarvis.jarvis_utils.globals as jglobals

        monkeypatch.setattr(jglobals, "master_url", None)
        assert emit_remote(_sample_event()) is False

    def test_unreachable_gateway_returns_false(self, monkeypatch):
        """网关不可达时 emit_remote 静默返回 False（不抛异常）。"""
        import jarvis.jarvis_utils.globals as jglobals

        monkeypatch.setattr(jglobals, "master_url", "http://127.0.0.1:1")
        assert emit_remote(_sample_event()) is False

    def test_local_pump_active_flag(self):
        """本地泵激活标志可读写。"""
        set_local_pump_active(True)
        assert is_local_pump_active() is True
        set_local_pump_active(False)
        assert is_local_pump_active() is False


class TestPipelineRunnerEmit:
    def test_emit_local_when_pump_active(self):
        """本地泵激活时 _emit 只写本地总线（不上报远程）。"""
        from jarvis.jarvis_tools.pipeline_runner import PipelineRunnerTool

        set_local_pump_active(True)
        bus = get_event_bus()
        bus.drain()
        tool = PipelineRunnerTool()
        tool._emit("test-pipeline-123456", "pipeline_start", orchestration_file="/tmp/x.yaml")
        events = bus.drain()
        assert len(events) == 1
        assert events[0]["type"] == "pipeline_start"
        set_local_pump_active(False)

    def test_emit_writes_local_when_pump_inactive(self):
        """本地泵未激活时 _emit 仍写本地总线（远程上报失败静默）。"""
        from jarvis.jarvis_tools.pipeline_runner import PipelineRunnerTool

        set_local_pump_active(False)
        bus = get_event_bus()
        bus.drain()
        tool = PipelineRunnerTool()
        tool._emit("test-pipeline-123456", "stage_update", stage="planner", status="running")
        events = bus.drain()
        assert len(events) == 1
        assert events[0]["type"] == "stage_update"
