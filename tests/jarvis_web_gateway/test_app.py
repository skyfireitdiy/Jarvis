# -*- coding: utf-8 -*-
"""jarvis_web_gateway app API tests."""

import os
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


def create_test_client() -> TestClient:
    # 在测试环境中跳过交互式配置
    os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"
    # 设置认证 Token 环境变量
    os.environ["JARVIS_AUTH_TOKEN"] = TEST_AUTH_TOKEN
    app = create_app()
    return TestClient(app)


def get_auth_headers():
    """获取认证 Header"""
    return {"Authorization": f"Bearer {TEST_AUTH_TOKEN}"}


def test_post_file_content_success(tmp_path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("hello jarvis", encoding="utf-8")
    client = create_test_client()

    response = client.post(
        "/api/file-content",
        json={"path": str(test_file.resolve())},
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["path"] == str(test_file.resolve())
    assert payload["data"]["content"] == "hello jarvis"


def test_post_file_content_rejects_relative_path(tmp_path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("hello jarvis", encoding="utf-8")
    client = create_test_client()

    response = client.post(
        "/api/file-content", json={"path": test_file.name}, headers=get_auth_headers()
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_PATH"


def test_post_file_content_rejects_directory(tmp_path):
    client = create_test_client()

    response = client.post(
        "/api/file-content",
        json={"path": str(tmp_path.resolve())},
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "NOT_A_FILE"


def test_post_file_content_rejects_large_file(tmp_path):
    test_file = tmp_path / "large.txt"
    test_file.write_text("a" * (MAX_FILE_SIZE_BYTES + 1), encoding="utf-8")
    client = create_test_client()

    response = client.post(
        "/api/file-content",
        json={"path": str(test_file.resolve())},
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "FILE_TOO_LARGE"


def test_post_file_content_rejects_binary_file(tmp_path):
    test_file = tmp_path / "binary.bin"
    test_file.write_bytes(b"\x00\x01\x02jarvis")
    client = create_test_client()

    response = client.post(
        "/api/file-content",
        json={"path": str(test_file.resolve())},
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "BINARY_FILE_NOT_SUPPORTED"


def test_post_file_write_success(tmp_path):
    test_file = tmp_path / "write.txt"
    client = create_test_client()

    response = client.post(
        "/api/file-write",
        json={"path": str(test_file.resolve()), "content": "hello write"},
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["path"] == str(test_file.resolve())
    assert payload["data"]["bytes_written"] == len("hello write".encode("utf-8"))
    assert test_file.read_text(encoding="utf-8") == "hello write"


def test_post_file_write_rejects_relative_path(tmp_path):
    client = create_test_client()

    response = client.post(
        "/api/file-write",
        json={"path": "relative.txt", "content": "hello"},
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_PATH"


def test_post_file_write_rejects_missing_parent_directory(tmp_path):
    missing_file = tmp_path / "missing" / "write.txt"
    client = create_test_client()

    response = client.post(
        "/api/file-write",
        json={"path": str(missing_file.resolve(strict=False)), "content": "hello"},
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "PARENT_DIRECTORY_NOT_FOUND"


def test_post_file_write_rejects_non_string_content(tmp_path):
    test_file = tmp_path / "write.txt"
    client = create_test_client()

    response = client.post(
        "/api/file-write",
        json={"path": str(test_file.resolve()), "content": 123},
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_CONTENT"


def test_post_file_write_rejects_large_content(tmp_path):
    test_file = tmp_path / "large-write.txt"
    client = create_test_client()

    response = client.post(
        "/api/file-write",
        json={
            "path": str(test_file.resolve()),
            "content": "a" * (MAX_FILE_SIZE_BYTES + 1),
        },
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "FILE_TOO_LARGE"


def test_session_output_router_keeps_cache_isolated_per_session():
    """断线缓存应按 session 隔离，不能被其他 session 取走"""
    router = SessionOutputRouter()

    session_a_message = {"type": "output", "payload": {"text": "from-a"}}
    session_b_message = {"type": "output", "payload": {"text": "from-b"}}

    router.publish(session_a_message, session_id="session-a")
    router.publish(session_b_message, session_id="session-b")

    cached_messages_a = router.get_and_clear_cache("session-a")
    assert cached_messages_a == [session_a_message]

    cached_messages_b = router.get_and_clear_cache("session-b")
    assert cached_messages_b == [session_b_message]


def test_session_output_router_clears_only_requested_session_cache():
    """回放某个 session 缓存后，不应清空其他 session 的缓存"""
    router = SessionOutputRouter()

    session_a_message = {"type": "output", "payload": {"text": "from-a"}}
    session_b_message = {"type": "output", "payload": {"text": "from-b"}}

    router.publish(session_a_message, session_id="session-a")
    router.publish(session_b_message, session_id="session-b")

    assert router.get_and_clear_cache("session-a") == [session_a_message]
    assert router.get_and_clear_cache("session-a") == []
    assert router.get_and_clear_cache("session-b") == [session_b_message]


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
    app = create_app()
    timer_manager = app.state.timer_manager

    try:
        assert isinstance(timer_manager, TimerManager)
        assert timer_manager.is_shutdown() is False
    finally:
        timer_manager.shutdown()


def test_create_timer_with_create_agent_action(tmp_path):
    client = create_test_client()

    response = client.post(
        "/api/timers",
        json={
            "schedule": {"delay_seconds": 60},
            "action": {
                "type": "create_agent",
                "params": {
                    "agent_type": "agent",
                    "working_dir": str(tmp_path.resolve()),
                    "name": "scheduled-agent",
                },
            },
        },
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    timer_data = payload["data"]
    assert timer_data["metadata"]["action"]["type"] == "create_agent"
    assert timer_data["metadata"]["action"]["params"]["agent_type"] == "agent"
    assert timer_data["metadata"]["action"]["params"]["working_dir"] == str(
        tmp_path.resolve()
    )
    assert timer_data["metadata"]["schedule"]["type"] == "delay"
    assert timer_data["metadata"]["schedule"]["delay_seconds"] == 60.0


def test_list_get_and_delete_timer(tmp_path):
    client = create_test_client()

    create_response = client.post(
        "/api/timers",
        json={
            "schedule": {"delay_seconds": 60},
            "action": {
                "type": "create_agent",
                "params": {
                    "agent_type": "agent",
                    "working_dir": str(tmp_path.resolve()),
                },
            },
        },
        headers=get_auth_headers(),
    )
    timer_id = create_response.json()["data"]["task_id"]

    list_response = client.get("/api/timers", headers=get_auth_headers())
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["success"] is True
    assert any(timer["task_id"] == timer_id for timer in list_payload["data"])

    get_response = client.get(f"/api/timers/{timer_id}", headers=get_auth_headers())
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["success"] is True
    assert get_payload["data"]["task_id"] == timer_id

    delete_response = client.delete(
        f"/api/timers/{timer_id}", headers=get_auth_headers()
    )
    assert delete_response.status_code == 200
    delete_payload = delete_response.json()
    assert delete_payload["success"] is True

    get_missing_response = client.get(
        f"/api/timers/{timer_id}", headers=get_auth_headers()
    )
    assert get_missing_response.status_code == 200
    get_missing_payload = get_missing_response.json()
    assert get_missing_payload["success"] is False
    assert get_missing_payload["error"]["code"] == "NOT_FOUND"


def test_create_timer_rejects_invalid_schedule_shape(tmp_path):
    client = create_test_client()

    response = client.post(
        "/api/timers",
        json={
            "schedule": {"delay_seconds": 10, "interval_seconds": 5},
            "action": {
                "type": "create_agent",
                "params": {
                    "agent_type": "agent",
                    "working_dir": str(tmp_path.resolve()),
                },
            },
        },
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_create_timer_rejects_empty_shell_command(tmp_path):
    client = create_test_client()

    response = client.post(
        "/api/timers",
        json={
            "schedule": {"delay_seconds": 10},
            "action": {
                "type": "run_shell_command",
                "params": {
                    "command": "   ",
                    "working_dir": str(tmp_path.resolve()),
                    "interpreter": "bash",
                },
            },
        },
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_create_timer_with_shell_command_action(tmp_path):
    client = create_test_client()
    run_at = (datetime.now() + timedelta(minutes=5)).isoformat()

    response = client.post(
        "/api/timers",
        json={
            "schedule": {"run_at": run_at},
            "action": {
                "type": "run_shell_command",
                "params": {
                    "command": "echo hello",
                    "working_dir": str(tmp_path.resolve()),
                    "interpreter": "bash",
                },
            },
        },
        headers=get_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    timer_data = payload["data"]
    assert timer_data["metadata"]["action"]["type"] == "run_shell_command"
    assert timer_data["metadata"]["action"]["params"]["command"] == "echo hello"
    assert timer_data["metadata"]["action"]["params"]["working_dir"] == str(
        tmp_path.resolve()
    )
    assert timer_data["metadata"]["action"]["params"]["interpreter"] == "bash"
    assert timer_data["metadata"]["schedule"]["type"] == "run_at"
    assert timer_data["metadata"]["schedule"]["run_at"] == run_at
