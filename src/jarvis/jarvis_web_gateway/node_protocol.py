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
AGENT_WS_REQUEST = "agent_ws_request"
AGENT_WS_RESPONSE = "agent_ws_response"
DIRECTORY_LIST_REQUEST = "directory_list_request"
DIRECTORY_LIST_RESPONSE = "directory_list_response"
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



def build_error_message(code: str, message: str, request_id: Optional[str] = None) -> Dict[str, Any]:
    return build_node_message(
        ERROR,
        {
            "code": code,
            "message": message,
            "details": {},
        },
        request_id=request_id,
    )
