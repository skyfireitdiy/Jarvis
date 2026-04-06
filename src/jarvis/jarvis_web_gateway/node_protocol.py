# -*- coding: utf-8 -*-
"""Node 内部消息协议。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

PROTOCOL_VERSION = 1

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
            "timestamp": datetime.utcnow().isoformat(),
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
