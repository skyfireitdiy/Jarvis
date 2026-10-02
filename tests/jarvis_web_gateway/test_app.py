# -*- coding: utf-8 -*-
"""jarvis_web_gateway app API tests."""

import json
import os

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

from datetime import datetime
from datetime import timedelta
from unittest.mock import Mock
from fastapi.testclient import TestClient

from jarvis.jarvis_gateway.events import GatewayOutputEvent
from jarvis.jarvis_gateway.output_bridge import SessionOutputRouter
from jarvis.jarvis_utils.output import OutputType
from jarvis.jarvis_web_gateway.app import MAX_FILE_SIZE_BYTES
from jarvis.jarvis_web_gateway.app import _fuzzy_match_score
from jarvis.jarvis_web_gateway.app import WebGateway
from jarvis.jarvis_web_gateway.app import create_app
from jarvis.jarvis_web_gateway.timer_manager import TimerManager


# 测试用的认证 Token
TEST_AUTH_TOKEN = "test-token-for-unit-tests"
os.environ["JARVIS_AUTH_TOKEN"] = TEST_AUTH_TOKEN


def create_test_client() -> TestClient:
    app = create_app()
    return TestClient(app)


def _cleanup_timer_persistence() -> None:
    persistence_file = TimerManager.PERSISTENCE_FILE
    if persistence_file.exists():
        persistence_file.unlink()


def get_auth_headers():
    """获取认证 Header"""
    return {"Authorization": f"Bearer {TEST_AUTH_TOKEN}"}


def test_session_output_router_drops_messages_without_subscribers():
    """无订阅者时，router 不应缓存或延迟回放消息"""
    router = SessionOutputRouter()

    session_a_message = {"type": "output", "payload": {"text": "from-a"}}
    session_b_message = {"type": "output", "payload": {"text": "from-b"}}

    sender_a = Mock()
    sender_b = Mock()

    router.publish(session_a_message, session_id="session-a")
    router.publish(session_b_message, session_id="session-b")

    router.register("conn-a", sender_a, session_id="session-a")
    router.register("conn-b", sender_b, session_id="session-b")

    sender_a.assert_not_called()
    sender_b.assert_not_called()


def test_session_output_router_routes_only_to_registered_session():
    """已注册订阅者时，消息只发送给对应 session 的 sender"""
    router = SessionOutputRouter()

    session_a_message = {"type": "output", "payload": {"text": "from-a"}}
    session_b_message = {"type": "output", "payload": {"text": "from-b"}}

    sender_a = Mock()
    sender_b = Mock()
    router.register("conn-a", sender_a, session_id="session-a")
    router.register("conn-b", sender_b, session_id="session-b")

    router.publish(session_a_message, session_id="session-a")
    router.publish(session_b_message, session_id="session-b")

    sender_a.assert_called_once_with(session_a_message)
    sender_b.assert_called_once_with(session_b_message)


def test_web_gateway_emit_output_promotes_agent_id_to_payload():
    """主连接 output 消息应在 payload 顶层携带 agent_id，便于前端准确归属"""
    router = SessionOutputRouter()
    input_registry = Mock()
    terminal_input_registry = Mock()
    auth_store = {"default": {"token": "test-token"}}
    gateway = WebGateway(router, input_registry, auth_store, terminal_input_registry)
    gateway._check_auth = Mock(return_value=(True, None))

    sender = Mock()
    router.register("conn-1", sender, session_id="default")

    event = GatewayOutputEvent(
        output_type=OutputType.INFO,
        text="hello",
        timestamp="12:00:00",
        context={"agent_id": "agent-123", "agent_name": "Agent 123"},
    )

    gateway.emit_output(event)

    sender.assert_called_once()
    message = sender.call_args[0][0]
    assert message["type"] == "output"
    assert message["payload"]["agent_id"] == "agent-123"
    assert message["payload"]["context"]["agent_id"] == "agent-123"


def test_create_app_attaches_timer_manager_to_app_state():
    _cleanup_timer_persistence()
    app = create_app()
    timer_manager = app.state.timer_manager

    try:
        assert isinstance(timer_manager, TimerManager)
        assert timer_manager.is_shutdown() is False
    finally:
        timer_manager.shutdown()
        _cleanup_timer_persistence()


def test_create_timer_with_capability_call_action(tmp_path):
    """capability_call 动作应能被 _build_timer_action 正确构建并调度。"""
    _cleanup_timer_persistence()
    client = create_test_client()
    headers = get_auth_headers()

    # 创建 capability_call 定时任务（delay 足够长避免测试期间触发）
    resp = client.post(
        "/api/timers",
        headers=headers,
        json={
            "schedule": {"delay_seconds": 3600},
            "action": {
                "type": "capability_call",
                "params": {
                    "session_id": "session-1",
                    "capability": "fs.read",
                    "params": {"path": "/tmp"},
                    "timeout": 15,
                    "user_id": "user-1",
                    "is_admin": True,
                },
            },
        },
    )
    body = resp.json()
    assert body["success"] is True, body
    timer_info = body["data"]
    action_meta = timer_info["metadata"]["action"]
    assert action_meta["type"] == "capability_call"
    assert action_meta["params"]["capability"] == "fs.read"
    assert action_meta["params"]["session_id"] == "session-1"
    assert action_meta["params"]["timeout"] == 15.0
    assert action_meta["params"]["is_admin"] is True
    assert action_meta["params"]["params"] == {"path": "/tmp"}

    # 清理
    timer_id = timer_info["task_id"]
    resp_del = client.delete(f"/api/timers/{timer_id}", headers=headers)
    assert resp_del.json()["success"] is True
    _cleanup_timer_persistence()


def test_create_timer_with_capability_call_rejects_invalid_params():
    """capability_call 动作缺少必填字段或字段类型错误时应返回 INVALID_ARGUMENT。"""
    _cleanup_timer_persistence()
    client = create_test_client()
    headers = get_auth_headers()

    # 缺 session_id
    resp = client.post(
        "/api/timers",
        headers=headers,
        json={
            "schedule": {"delay_seconds": 3600},
            "action": {
                "type": "capability_call",
                "params": {"capability": "fs.read"},
            },
        },
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_ARGUMENT"
    assert "session_id" in body["error"]["message"]

    # 缺 capability
    resp = client.post(
        "/api/timers",
        headers=headers,
        json={
            "schedule": {"delay_seconds": 3600},
            "action": {
                "type": "capability_call",
                "params": {"session_id": "session-1"},
            },
        },
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_ARGUMENT"
    assert "capability" in body["error"]["message"]

    # params 非对象
    resp = client.post(
        "/api/timers",
        headers=headers,
        json={
            "schedule": {"delay_seconds": 3600},
            "action": {
                "type": "capability_call",
                "params": {
                    "session_id": "session-1",
                    "capability": "fs.read",
                    "params": "not-an-object",
                },
            },
        },
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_ARGUMENT"

    # timeout 非数字
    resp = client.post(
        "/api/timers",
        headers=headers,
        json={
            "schedule": {"delay_seconds": 3600},
            "action": {
                "type": "capability_call",
                "params": {
                    "session_id": "session-1",
                    "capability": "fs.read",
                    "timeout": "not-a-number",
                },
            },
        },
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_ARGUMENT"

    # 未知 action.type
    resp = client.post(
        "/api/timers",
        headers=headers,
        json={
            "schedule": {"delay_seconds": 3600},
            "action": {"type": "bogus_type", "params": {}},
        },
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_ARGUMENT"

    _cleanup_timer_persistence()


def test_set_node_config_rejects_schema_invalid_config():
    """保存配置前应使用 config_schema.json 校验，非法配置不得写入。"""
    client = create_test_client()
    headers = get_auth_headers()

    # 非法配置：mcp 应为 array，给成 string
    resp = client.post(
        "/api/nodes/nonexistent-node/config",
        headers=headers,
        json={
            "config_sections": ["mcp"],
            "config_data": {"mcp": "not-an-array"},
        },
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "CONFIG_SCHEMA_VALIDATION_FAILED"
    assert any(e["path"] == "mcp" for e in body["error"]["details"])

    # 合法配置应通过校验（此处因节点不存在而返回 NODE_NOT_FOUND，而非校验失败）
    resp2 = client.post(
        "/api/nodes/nonexistent-node/config",
        headers=headers,
        json={
            "config_sections": ["llm_group"],
            "config_data": {"llm_group": "qwen3"},
        },
    )
    body2 = resp2.json()
    assert body2["success"] is False
    assert body2["error"]["code"] == "NODE_NOT_FOUND"


def test_fuzzy_match_score_prefers_contiguous():
    """连续匹配得分应优于跳跃匹配。"""
    assert _fuzzy_match_score("mod", "mod.rs") is not None
    contiguous = _fuzzy_match_score("mod", "mod.rs")
    scattered = _fuzzy_match_score("mod", "m_x_o_y_d.rs")
    assert contiguous is not None and scattered is not None
    assert contiguous < scattered


def test_fuzzy_match_score_rejects_non_subsequence():
    """非子序列应返回 None。"""
    assert _fuzzy_match_score("xyz", "sche/mod.rs") is None


def test_file_search_matches_directory_path():
    """f> 搜索应支持「目录 + 文件名」的模糊匹配（如 scmodrs → sche/mod.rs）。"""
    query = "scmodrs"

    def match_score(relative_path: str) -> int | None:
        name = relative_path.rsplit("/", 1)[-1]
        name_score = _fuzzy_match_score(query, name)
        path_score = _fuzzy_match_score(query, relative_path)
        candidates = [s for s in (name_score, path_score) if s is not None]
        return min(candidates) if candidates else None

    # 目录路径命中：仅凭文件名 mod.rs 无法匹配 scmodrs，但完整路径可以
    assert _fuzzy_match_score(query, "mod.rs") is None
    assert match_score("sche/mod.rs") is not None
    # 文件名命中不应因引入路径匹配而劣化：取 min 保证不劣于单独的文件名匹配
    assert match_score("mod.rs") == _fuzzy_match_score(query, "mod.rs") or (
        match_score("mod.rs") is None
    )
