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

from .events import GatewayConfirmRequest
from .events import GatewayConfirmResult
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
    def request_confirm(self, request: GatewayConfirmRequest) -> GatewayConfirmResult:
        """请求用户确认。"""

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
        """检查认证信息。

        Args:
            auth: 认证信息字典，应包含 token 字段

        Returns:
            (是否认证成功, 错误信息) 元组
        """
        # 导入 token 管理模块
        try:
            from jarvis.jarvis_web_gateway.token_manager import validate_gateway_token
        except ImportError:
            # 如果不可用（如 CLI Gateway），则回退到旧的密码认证
            return self._check_auth_fallback(auth)

        # 检查 Token
        if not auth:
            return False, "token missing"

        token = auth.get("token")
        if not token:
            return False, "token missing"

        if validate_gateway_token(token):
            return True, None

        return False, "invalid token"

    def _check_auth_fallback(
        self, auth: Optional[Dict[str, Any]]
    ) -> Tuple[bool, Optional[str]]:
        """回退的密码认证方法（用于 CLI Gateway）。

        只要在配置中设置了 password，就启用认证。

        Args:
            auth: 认证信息字典，应包含 password 字段

        Returns:
            (是否认证成功, 错误信息) 元组
        """
        from jarvis.jarvis_utils.config import get_gateway_auth_config

        config = get_gateway_auth_config()

        # 获取配置的密码（可以从配置文件或命令行参数传入）
        expected_password = config.get("password") if config else None

        # 情况1：配置中有密码 -> 启用认证
        if expected_password:
            if not auth:
                return False, "gateway auth missing"

            password = auth.get("password")
            if password == expected_password:
                return True, None

            return False, "gateway auth failed"

        # 情况2：配置中没有密码 -> 不启用认证
        # - 用户没传密码 -> 允许访问
        # - 用户传了密码 -> 拒绝（因为配置中没有可校验的密码）
        if not auth or not auth.get("password"):
            return True, None  # 没传密码，允许访问

        return False, "gateway auth not configured"

    def emit_output(self, event: GatewayOutputEvent) -> None:
        del event
        raise NotImplementedError

    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        del request
        raise NotImplementedError

    def request_confirm(self, request: GatewayConfirmRequest) -> GatewayConfirmResult:
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
