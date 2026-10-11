# -*- coding: utf-8 -*-
"""Node 内部消息协议。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import msgpack

PROTOCOL_VERSION = 1

# 二进制帧头魔数：用于自描述消息编码，接收端据此判断是 msgpack 还是 JSON。
MAGIC = b"\x93JAR"

NODE_AUTH = "node_auth"
NODE_AUTH_RESULT = "node_auth_result"
NODE_HEARTBEAT = "node_heartbeat"
AGENT_CREATE_REQUEST = "agent_create_request"
AGENT_CREATE_RESPONSE = "agent_create_response"
AGENT_HTTP_REQUEST = "agent_http_request"
AGENT_HTTP_RESPONSE = "agent_http_response"
NODE_HTTP_PROXY_REQUEST = "node_http_proxy_request"
NODE_HTTP_PROXY_RESPONSE = "node_http_proxy_response"
AGENT_LIST_REQUEST = "agent_list_request"
AGENT_LIST_RESPONSE = "agent_list_response"
AGENT_STOP_REQUEST = "agent_stop_request"
AGENT_STOP_RESPONSE = "agent_stop_response"
AGENT_DELETE_REQUEST = "agent_delete_request"
AGENT_DELETE_RESPONSE = "agent_delete_response"
AGENT_REGENERATE_REQUEST = "agent_regenerate_request"
AGENT_REGENERATE_RESPONSE = "agent_regenerate_response"
AGENT_WS_REQUEST = "agent_ws_request"
AGENT_WS_RESPONSE = "agent_ws_response"
AGENT_WS_OPEN_REQUEST = "agent_ws_open_request"
AGENT_WS_OPEN_RESPONSE = "agent_ws_open_response"
AGENT_WS_SEND_REQUEST = "agent_ws_send_request"
AGENT_WS_SEND_RESPONSE = "agent_ws_send_response"
AGENT_WS_RECV_REQUEST = "agent_ws_recv_request"
AGENT_WS_RECV_RESPONSE = "agent_ws_recv_response"
AGENT_WS_CLOSE_REQUEST = "agent_ws_close_request"
AGENT_WS_CLOSE_RESPONSE = "agent_ws_close_response"
DIRECTORY_LIST_REQUEST = "directory_list_request"
DIRECTORY_LIST_RESPONSE = "directory_list_response"
NODE_TERMINAL_REQUEST = "node_terminal_request"
NODE_TERMINAL_RESPONSE = "node_terminal_response"
NODE_TERMINAL_OUTPUT = "node_terminal_output"
SERVICE_RESTART_REQUEST = "service_restart_request"
SERVICE_RESTART_RESPONSE = "service_restart_response"
CONFIG_SYNC_REQUEST = "config_sync_request"
CONFIG_SYNC_RESPONSE = "config_sync_response"
CONFIG_GET_REQUEST = "config_get_request"
CONFIG_GET_RESPONSE = "config_get_response"
CONFIG_SET_REQUEST = "config_set_request"
CONFIG_SET_RESPONSE = "config_set_response"
CODE_UPDATE_TO_MAIN_REQUEST = "code_update_to_main_request"
CODE_UPDATE_TO_MAIN_RESPONSE = "code_update_to_main_response"
PLUGIN_MANAGE_REQUEST = "plugin_manage_request"
PLUGIN_MANAGE_RESPONSE = "plugin_manage_response"
ERROR = "error"


def build_node_message(
    message_type: str,
    payload: Dict[str, Any],
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "type": message_type,
        "request_id": request_id,
        "payload": payload,
        "meta": {
            "protocol_version": PROTOCOL_VERSION,
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        },
    }


def build_error_message(
    code: str, message: str, request_id: Optional[str] = None
) -> Dict[str, Any]:
    return build_node_message(
        ERROR,
        {
            "code": code,
            "message": message,
            "details": {},
        },
        request_id=request_id,
    )


def encode_node_message(message: Dict[str, Any]) -> bytes:
    """将节点消息编码为二进制帧（msgpack + 魔数前缀）。"""
    return MAGIC + msgpack.packb(message)


def decode_node_message(data: Any) -> Dict[str, Any]:
    """解码节点消息，兼容二进制（msgpack）与旧版 JSON 文本。

    接收端可能收到 bytes（二进制帧）或 str（旧版 JSON 文本帧）。
    带魔数前缀的按 msgpack 解码，否则按 JSON 解码。
    """
    if isinstance(data, str):
        return json.loads(data)
    if data.startswith(MAGIC):
        return msgpack.unpackb(data[len(MAGIC) :])
    return json.loads(data)
