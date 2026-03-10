# -*- coding: utf-8 -*-
"""Gateway 接口与基础实现。"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Optional

from .events import GatewayExecutionEvent
from .events import GatewayInputRequest
from .events import GatewayInputResult
from .events import GatewayOutputEvent


class IGateway(ABC):
    """统一交互网关接口。"""

    @abstractmethod
    def emit_output(self, event: GatewayOutputEvent) -> None:
        """发送输出事件。"""

    @abstractmethod
    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        """请求用户输入。"""

    @abstractmethod
    def publish_execution_event(
        self,
        event: GatewayExecutionEvent,
        session_id: Optional[str] = None,
    ) -> None:
        """发布执行流事件。"""


class BaseGateway(IGateway):
    """基础网关实现，便于扩展自定义交互方式。"""

    def emit_output(self, event: GatewayOutputEvent) -> None:
        del event
        raise NotImplementedError

    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        del request
        raise NotImplementedError

    def publish_execution_event(
        self,
        event: GatewayExecutionEvent,
        session_id: Optional[str] = None,
    ) -> None:
        del event, session_id
        raise NotImplementedError
