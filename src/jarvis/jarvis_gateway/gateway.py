# -*- coding: utf-8 -*-
"""Gateway 接口与基础实现。"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Tuple

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

    @abstractmethod
    def get_execution_input_callback(
        self,
        execution_id: str,
    ) -> Optional[Callable[[Optional[float]], Optional[str]]]:
        """获取执行输入回调（用于交互式终端）。"""

    @abstractmethod
    def get_execution_resize_callback(
        self,
        execution_id: str,
    ) -> Optional[Callable[[], Optional[Tuple[int, int]]]]:
        """获取执行终端尺寸变更回调。"""


class BaseGateway(IGateway):
    """基础网关实现，便于扩展自定义交互方式。"""

    def _check_auth(self, auth: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        from jarvis.jarvis_utils.config import get_gateway_auth_config

        config = get_gateway_auth_config()
        if not config:
            return True, None
        if not bool(config.get("enable", False)):
            return True, None
        allow_unset = bool(config.get("allow_unset", True))
        expected_token = config.get("token")
        expected_password = config.get("password")
        if not expected_token and not expected_password:
            if allow_unset:
                return True, None
            return False, "gateway auth required"
        if not auth:
            return False, "gateway auth missing"
        token = auth.get("token")
        password = auth.get("password")
        token_match = bool(expected_token) and token == expected_token
        password_match = bool(expected_password) and password == expected_password
        if token_match or password_match:
            return True, None
        return False, "gateway auth failed"

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

    def get_execution_input_callback(
        self,
        execution_id: str,
    ) -> Optional[Callable[[Optional[float]], Optional[str]]]:
        del execution_id
        return None

    def get_execution_resize_callback(
        self,
        execution_id: str,
    ) -> Optional[Callable[[], Optional[Tuple[int, int]]]]:
        del execution_id
        return None
