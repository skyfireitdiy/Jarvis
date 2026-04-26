# -*- coding: utf-8 -*-
"""Jarvis WebSocket/网关相关基础模块。"""

from .cli_gateway import CLIGateway
from .events import GatewayExecutionEvent
from .events import GatewayInputRequest
from .events import GatewayInputResult
from .events import GatewayOutputEvent
from .gateway import BaseGateway
from .gateway import IGateway
from .input_bridge import InputSessionRegistry
from .input_bridge import RemoteInputSession
from .input_bridge import WebSocketInputProvider
from .manager import get_current_gateway
from .manager import set_current_gateway
from .output_bridge import OutputMessagePublisher
from .output_bridge import SessionOutputRouter
from .output_bridge import WebSocketOutputSink
from .output_bridge import serialize_output_event

__all__ = [
    "CLIGateway",
    "GatewayExecutionEvent",
    "GatewayInputRequest",
    "GatewayInputResult",
    "GatewayOutputEvent",
    "BaseGateway",
    "IGateway",
    "InputSessionRegistry",
    "RemoteInputSession",
    "WebSocketInputProvider",
    "get_current_gateway",
    "set_current_gateway",
    "OutputMessagePublisher",
    "SessionOutputRouter",
    "WebSocketOutputSink",
    "serialize_output_event",
]
