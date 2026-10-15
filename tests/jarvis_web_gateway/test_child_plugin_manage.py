# -*- coding: utf-8 -*-
"""子节点处理 master 转发的插件管理请求（PLUGIN_MANAGE_REQUEST）的单元测试。

覆盖 Bug：AutoWorker 插件切到子节点后任务列表一直"加载中"。
根因：master 侧 NodeConnectionManager 收到 PLUGIN_MANAGE_REQUEST 会转发到子节点，
但 ChildNodeClient.recv_loop 缺少 PLUGIN_MANAGE_REQUEST 分支，子节点收到后走
unhandled 分支不响应，master 侧 send_request_to_node 60s 超时。

修复：在 ChildNodeClient.recv_loop 增加 PLUGIN_MANAGE_REQUEST 分支，
调用 NodeConnectionManager._handle_plugin_manage_request 并回发响应。
"""

import os

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import inspect

from unittest.mock import MagicMock

from jarvis.jarvis_web_gateway.node_manager import (
    ChildNodeClient,
    NodeConnectionManager,
)
from jarvis.jarvis_web_gateway.node_protocol import PLUGIN_MANAGE_REQUEST


def _make_manager():
    """构造一个 NodeConnectionManager（master 侧处理逻辑）。"""
    return NodeConnectionManager(
        node_runtime=MagicMock(),
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_http_dispatcher=None,
        router=MagicMock(),
        terminal_session_manager=MagicMock(),
    )


def _make_child_client():
    """构造一个 ChildNodeClient（子节点侧）。"""
    ncm = _make_manager()
    return ChildNodeClient(
        node_runtime=MagicMock(),
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_connection_manager=ncm,
    )


def test_child_recv_loop_handles_plugin_manage_request():
    """ChildNodeClient.recv_loop 必须包含 PLUGIN_MANAGE_REQUEST 分支。

    这是本次 Bug 的直接回归点：缺少该分支时，子节点收到 master 转发的插件
    管理/私有功能调用请求会走 unhandled 分支不响应，导致 master 60s 超时。
    """
    source = inspect.getsource(ChildNodeClient)
    assert PLUGIN_MANAGE_REQUEST in source
    # 确保分支在 recv_loop 内（而非仅 import/常量定义处）
    assert "if message_type == PLUGIN_MANAGE_REQUEST:" in source
    # 确保分支调用 _handle_plugin_manage_request 并回发响应
    assert "_handle_plugin_manage_request" in source


def test_child_handles_plugin_manage_call_function():
    """子节点 _handle_plugin_manage_request 应能处理 call_function 动作。

    模拟 master 转发 autoworker 插件的 list_tasks 私有功能调用：
    子节点应加载插件 api.py、校验白名单、执行函数并返回结构化响应。
    """
    m = _make_manager()

    # mock 插件 api 层：返回一个带 PUBLIC_FUNCTIONS 白名单的 api
    api = MagicMock()
    api.PUBLIC_FUNCTIONS = ["list_tasks"]
    api.list_tasks.return_value = {"success": True, "data": [{"id": "t1"}]}
    m._load_plugin_api = MagicMock(return_value=api)

    message = {
        "type": PLUGIN_MANAGE_REQUEST,
        "request_id": "req-plugin-1",
        "payload": {
            "action": "call_function",
            "name": "autoworker",
            "function": "list_tasks",
            "arguments": {"workdir": "/tmp/aw_test"},
        },
    }
    resp = m._handle_plugin_manage_request(message)

    assert resp["type"] == "plugin_manage_response"
    assert resp["request_id"] == "req-plugin-1"
    payload = resp["payload"]
    assert payload["success"] is True
    assert payload["action"] == "call_function"
    assert payload["result"] == {"success": True, "data": [{"id": "t1"}]}
    api.list_tasks.assert_called_once_with(workdir="/tmp/aw_test")


def test_child_plugin_manage_function_not_in_whitelist():
    """子节点应拒绝调用不在 PUBLIC_FUNCTIONS 白名单内的功能。"""
    m = _make_manager()

    api = MagicMock()
    api.PUBLIC_FUNCTIONS = ["list_tasks"]
    m._load_plugin_api = MagicMock(return_value=api)

    message = {
        "type": PLUGIN_MANAGE_REQUEST,
        "request_id": "req-plugin-2",
        "payload": {
            "action": "call_function",
            "name": "autoworker",
            "function": "rm_rf",
            "arguments": {},
        },
    }
    resp = m._handle_plugin_manage_request(message)

    payload = resp["payload"]
    assert payload["success"] is False
    assert payload["error"]["code"] == "FUNCTION_NOT_ALLOWED"
    api.rm_rf.assert_not_called()


def test_child_plugin_manage_missing_api():
    """子节点找不到插件 api.py 时应返回 FUNCTION_API_NOT_FOUND。"""
    m = _make_manager()
    m._load_plugin_api = MagicMock(return_value=None)

    message = {
        "type": PLUGIN_MANAGE_REQUEST,
        "request_id": "req-plugin-3",
        "payload": {
            "action": "call_function",
            "name": "no-such-plugin",
            "function": "list_tasks",
            "arguments": {},
        },
    }
    resp = m._handle_plugin_manage_request(message)

    payload = resp["payload"]
    assert payload["success"] is False
    assert payload["error"]["code"] == "FUNCTION_API_NOT_FOUND"


def test_child_plugin_manage_list_functions():
    """子节点 list_functions 应返回白名单内可调用的函数列表。"""
    m = _make_manager()

    api = MagicMock()
    api.PUBLIC_FUNCTIONS = ["list_tasks", "get_status", "secret_fn"]
    m._load_plugin_api = MagicMock(return_value=api)

    message = {
        "type": PLUGIN_MANAGE_REQUEST,
        "request_id": "req-plugin-4",
        "payload": {"action": "list_functions", "name": "autoworker"},
    }
    resp = m._handle_plugin_manage_request(message)

    payload = resp["payload"]
    assert payload["success"] is True
    assert payload["functions"] == ["list_tasks", "get_status", "secret_fn"]
