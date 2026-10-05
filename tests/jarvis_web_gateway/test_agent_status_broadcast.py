"""测试 _on_agent_status_change 的 WebSocket 广播逻辑。

该函数由 AgentManager 在 Agent 生命周期状态变化时调用，通过全局 _router
广播 status_update 消息给所有连接的前端。本测试用假 router 验证广播消息格式。
"""

from typing import Any, Dict, List

import pytest

from jarvis.jarvis_web_gateway import app as app_module


class FakeRouter:
    """记录 publish 调用的假路由器。"""

    def __init__(self) -> None:
        self.published: List[Dict[str, Any]] = []

    def publish(self, message: Dict[str, Any], session_id: Any = None) -> None:
        self.published.append({"message": message, "session_id": session_id})


@pytest.fixture(autouse=True)
def _patch_router(monkeypatch: pytest.MonkeyPatch) -> FakeRouter:
    """把 app 模块的全局 _router 替换为假路由器。"""
    fake = FakeRouter()
    monkeypatch.setattr(app_module, "_router", fake)
    return fake


def _call(agent_id: str, status: str, data: Any = None) -> None:
    app_module._on_agent_status_change(agent_id, status, data)


def test_stopped_broadcasts_stopped_execution_status(_patch_router: FakeRouter) -> None:
    """Agent 正常停止时，广播 execution_status=stopped 且携带 agent_id。"""
    _call("agent-1", "stopped", {"agent_id": "agent-1", "status": "stopped"})
    assert len(_patch_router.published) == 1
    msg = _patch_router.published[0]["message"]
    assert msg["type"] == "status_update"
    payload = msg["payload"]
    assert payload["agent_id"] == "agent-1"
    assert payload["status"] == "stopped"
    assert payload["execution_status"] == "stopped"
    # 广播模式：session_id 为 None
    assert _patch_router.published[0]["session_id"] is None


def test_error_broadcasts_stopped_execution_status(_patch_router: FakeRouter) -> None:
    """Agent 异常退出时，同样映射为 stopped 供前端标记已退出。"""
    _call("agent-2", "error", {"return_code": 1})
    payload = _patch_router.published[0]["message"]["payload"]
    assert payload["agent_id"] == "agent-2"
    assert payload["status"] == "error"
    assert payload["execution_status"] == "stopped"


def test_deleted_broadcasts_status_without_execution_status(
    _patch_router: FakeRouter,
) -> None:
    """Agent 被删除时，广播原始 status=deleted，不设置 execution_status。"""
    _call("agent-3", "deleted", None)
    payload = _patch_router.published[0]["message"]["payload"]
    assert payload["agent_id"] == "agent-3"
    assert payload["status"] == "deleted"
    assert "execution_status" not in payload


def test_running_broadcasts_running_execution_status(
    _patch_router: FakeRouter,
) -> None:
    """Agent 运行时，广播 execution_status=running。"""
    _call("agent-4", "running", {"status": "running"})
    payload = _patch_router.published[0]["message"]["payload"]
    assert payload["execution_status"] == "running"


def test_no_router_no_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """_router 为 None 时静默返回，不抛异常。"""
    monkeypatch.setattr(app_module, "_router", None)
    # 不应抛异常
    app_module._on_agent_status_change("agent-5", "stopped", None)
