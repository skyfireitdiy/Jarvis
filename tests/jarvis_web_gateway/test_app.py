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


def test_create_timer_with_create_agent_action(tmp_path):
    _cleanup_timer_persistence()
