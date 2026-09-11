#!/usr/bin/env python3
"""子节点 HTTP 代理透传 user_info 的回归测试。

背景：master 转发创建 agent 请求（POST /agents）到子节点时，必须把
user_info 一并透传，否则子节点创建出的 agent owner_id 为 None，
导致前端"无损重生/权限管理"按钮不显示。

本测试直接调用 NodeConnectionManager._handle_node_http_proxy_request，
断言 dispatcher 收到了 payload 中的 user_info。
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.jarvis_web_gateway.node_config import NodeRuntimeConfig
from jarvis.jarvis_web_gateway.node_manager import NodeConnectionManager
from jarvis.jarvis_web_gateway.node_runtime import NodeRuntime


class _RecordingDispatcher:
    """记录被调用参数的 dispatcher 替身。"""

    def __init__(self):
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": True, "status_code": 200, "body": "{}"}


def _build_manager(dispatcher):
    runtime = NodeRuntime(NodeRuntimeConfig(node_mode="child", node_id="worker-x"))
    # agent_manager / agent_proxy_manager 在本测试路径中不会被访问，
    # 传 None 即可；cast 仅用于满足类型检查。
    return NodeConnectionManager(
        node_runtime=runtime,
        agent_manager=cast(Any, None),
        agent_proxy_manager=cast(Any, None),
        node_http_dispatcher=dispatcher,
    )


def test_proxy_request_forwards_user_info():
    """非流式代理请求应把 payload.user_info 透传给 dispatcher。"""
    dispatcher = _RecordingDispatcher()
    manager = _build_manager(dispatcher)

    user_info = {"user_id": "u-123", "username": "alice"}
    message = {
        "request_id": "req-1",
        "payload": {
            "method": "POST",
            "path": "/agents",
            "query": "",
            "headers": {"content-type": "application/json"},
            "body": '{"name": "demo"}',
            "user_info": user_info,
        },
    }

    asyncio.run(manager._handle_node_http_proxy_request(None, message))

    assert len(dispatcher.calls) == 1
    call = dispatcher.calls[0]
    assert call["user_info"] == user_info
    assert call["method"] == "POST"
    assert call["path"] == "/agents"


def test_proxy_request_without_user_info_passes_none():
    """payload 未携带 user_info 时应传 None（不报错）。"""
    dispatcher = _RecordingDispatcher()
    manager = _build_manager(dispatcher)

    message = {
        "request_id": "req-2",
        "payload": {"method": "GET", "path": "/agents"},
    }

    asyncio.run(manager._handle_node_http_proxy_request(None, message))

    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0]["user_info"] is None


def test_proxy_request_without_dispatcher_returns_error():
    """未配置 dispatcher 时应返回失败响应而非抛异常。"""
    manager = _build_manager(None)
    message = {
        "request_id": "req-3",
        "payload": {"method": "GET", "path": "/agents"},
    }

    result = asyncio.run(manager._handle_node_http_proxy_request(None, message))

    assert result is not None
    assert result["payload"]["success"] is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
