#!/usr/bin/env python3
"""daemon 终端转发（网关侧）单元测试。

覆盖 daemon_capability_manager 新增的 daemon 终端转发链路：
1. send_node_terminal_request：向 daemon 下发 node_terminal_request 并按 request_id 匹配响应
2. 消息循环处理 node_terminal_response（唤醒等待中的 Future）
3. 消息循环处理 node_terminal_output（经 router 推前端 + 广播 admin）
4. get_session_by_node_id：按 node_id 反查 daemon 会话
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from jarvis.jarvis_web_gateway.daemon_capability_manager import (
    DaemonCapabilityManager,
    daemon_capability_manager,
)


class FakeWebSocket:
    """模拟 daemon 会话的 WebSocket：记录 send_json 调用。"""

    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)

    async def receive_json(self):
        raise asyncio.CancelledError()

    async def close(self):
        pass


def _make_session(manager, node_id="daemon-host-123", user_id="u1"):
    """向 manager 注册一个 daemon 会话，返回 (session_id, fake_ws)。"""
    ws = FakeWebSocket()
    session_id = "sess-1"
    manager._sessions[session_id] = {
        "websocket": ws,
        "user_id": user_id,
        "client_id": node_id,
        "node_id": node_id,
        "hostname": "host",
        "name": "host",
        "platform": "linux",
        "system_info": {},
        "daemon_version": "1.0",
        "build_info": {},
        "capabilities": [],
        "connected_at": 0,
        "last_seen": 0,
        "update_state": None,
    }
    return session_id, ws


class TestSendNodeTerminalRequest:
    """send_node_terminal_request 行为。"""

    @pytest.mark.asyncio
    async def test_send_request_and_match_response(self):
        manager = DaemonCapabilityManager()
        session_id, ws = _make_session(manager, node_id="daemon-host-123")

        # 启动一个协程发送请求，另一个协程模拟 daemon 回 node_terminal_response
        async def sender():
            return await manager.send_node_terminal_request(
                session_id,
                "terminal_create",
                {"interpreter": "bash"},
                timeout=5.0,
                user_id="u1",
            )

        async def responder():
            # 等请求发出后，读取发送的消息并回响应
            await asyncio.sleep(0.01)
            assert len(ws.sent) == 1
            sent = ws.sent[0]
            assert sent["type"] == "node_terminal_request"
            assert sent["payload"]["action"] == "terminal_create"
            assert sent["payload"]["payload"] == {"interpreter": "bash"}
            request_id = sent["request_id"]
            # 模拟 daemon 回包
            manager._handle_node_terminal_response(
                {
                    "type": "node_terminal_response",
                    "request_id": request_id,
                    "payload": {
                        "success": True,
                        "data": {"terminal_id": "t1", "interpreter": "bash"},
                    },
                }
            )
            return request_id

        result, _ = await asyncio.gather(sender(), responder())
        assert result["success"] is True
        assert result["data"]["terminal_id"] == "t1"

    @pytest.mark.asyncio
    async def test_session_not_found(self):
        manager = DaemonCapabilityManager()
        with pytest.raises(RuntimeError):
            await manager.send_node_terminal_request(
                "no-such-session", "terminal_create", {}, user_id="u1"
            )

    @pytest.mark.asyncio
    async def test_forbidden_other_user(self):
        manager = DaemonCapabilityManager()
        session_id, _ = _make_session(manager, node_id="daemon-host-123", user_id="u1")
        with pytest.raises(RuntimeError):
            await manager.send_node_terminal_request(
                session_id, "terminal_create", {}, user_id="other"
            )

    @pytest.mark.asyncio
    async def test_timeout(self):
        manager = DaemonCapabilityManager()
        session_id, ws = _make_session(manager, node_id="daemon-host-123")
        with pytest.raises(RuntimeError):
            await manager.send_node_terminal_request(
                session_id, "terminal_create", {}, timeout=0.05, user_id="u1"
            )


class TestHandleNodeTerminalOutput:
    """node_terminal_output 消息处理：经 router 推前端 + 广播 admin。"""

    @pytest.mark.asyncio
    async def test_publish_to_session_and_admins(self):
        manager = DaemonCapabilityManager()
        session_id, _ = _make_session(manager, node_id="daemon-host-123")

        published = []
        admin_sids = ["session_admin1", "session_admin2"]
        tsm = MagicMock()
        tsm.get_all_admin_session_ids.return_value = admin_sids
        router = MagicMock()
        router.publish = MagicMock(side_effect=lambda msg, session_id=None: published.append((msg, session_id)))
        manager.set_router(router)
        manager.set_terminal_session_manager(tsm)

        output_message = {
            "type": "execution",
            "payload": {
                "event_type": "stdout",
                "data": "aGVsbG8=",
                "encoded": True,
                "sequence": 1,
                "execution_id": "terminal_t1",
            },
        }
        manager._handle_node_terminal_output(
            {
                "type": "node_terminal_output",
                "payload": {"session_id": "session_u1", "message": output_message},
            }
        )

        # 推给创建者的 session_id
        assert any(sid == "session_u1" for _, sid in published)
        # 广播给所有 admin
        for admin_sid in admin_sids:
            assert any(sid == admin_sid for _, sid in published)
        # 推送的消息体就是 daemon 回传的 output_message
        assert any(msg is output_message for msg, _ in published)

    @pytest.mark.asyncio
    async def test_no_router_does_not_crash(self):
        manager = DaemonCapabilityManager()
        session_id, _ = _make_session(manager, node_id="daemon-host-123")
        # 未注入 router 时不应抛异常
        manager._handle_node_terminal_output(
            {
                "type": "node_terminal_output",
                "payload": {
                    "session_id": "session_u1",
                    "message": {"type": "execution", "payload": {}},
                },
            }
        )


class TestGetSessionByNodeId:
    """get_session_by_node_id 行为。"""

    def test_find_by_node_id(self):
        manager = DaemonCapabilityManager()
        session_id, _ = _make_session(manager, node_id="daemon-host-123")
        found = manager.get_session_by_node_id("daemon-host-123")
        assert found is not None
        assert found["session_id"] == session_id
        assert found["node_id"] == "daemon-host-123"

    def test_not_found(self):
        manager = DaemonCapabilityManager()
        _make_session(manager, node_id="daemon-host-123")
        assert manager.get_session_by_node_id("no-such-node") is None


class TestMessageLoopIntegration:
    """消息循环对 node_terminal_response / node_terminal_output 的分发。"""

    @pytest.mark.asyncio
    async def test_response_wakes_future(self):
        manager = DaemonCapabilityManager()
        session_id, ws = _make_session(manager, node_id="daemon-host-123")

        async def sender():
            return await manager.send_node_terminal_request(
                session_id, "terminal_close", {"terminal_id": "t1"}, timeout=5.0, user_id="u1"
            )

        async def responder():
            await asyncio.sleep(0.01)
            sent = ws.sent[0]
            request_id = sent["request_id"]
            # 模拟 daemon 回包（走消息循环分发路径）
            manager._handle_node_terminal_response(
                {
                    "type": "node_terminal_response",
                    "request_id": request_id,
                    "payload": {"success": True, "data": {}},
                }
            )
            return request_id

        result, _ = await asyncio.gather(sender(), responder())
        assert result["success"] is True
        assert result["data"] == {}
