# -*- coding: utf-8 -*-
"""CLI Gateway 实现：复用现有输出/输入逻辑，保持向后兼容。"""

from __future__ import annotations

from typing import Callable
from typing import Optional

from jarvis.jarvis_gateway.events import GatewayChoiceRequest
from jarvis.jarvis_gateway.events import GatewayChoiceResult
from jarvis.jarvis_gateway.events import GatewayConfirmRequest
from jarvis.jarvis_gateway.events import GatewayConfirmResult
from jarvis.jarvis_gateway.events import GatewayExecutionEvent
from jarvis.jarvis_gateway.events import GatewayInputRequest
from jarvis.jarvis_gateway.events import GatewayInputResult
from jarvis.jarvis_gateway.events import GatewayOutputEvent
from jarvis.jarvis_gateway.gateway import BaseGateway
from jarvis.jarvis_utils.input import get_choice
from jarvis.jarvis_utils.input import get_current_input_provider
from jarvis.jarvis_utils.output import OutputEvent
from jarvis.jarvis_utils.output import OutputType
from jarvis.jarvis_utils.output import emit_output


class CLIGateway(BaseGateway):
    """CLI 默认网关实现，沿用现有输出/输入能力。"""

    def __init__(
        self,
        execution_event_handler: Optional[
            Callable[[GatewayExecutionEvent, Optional[str]], None]
        ] = None,
    ) -> None:
        self._execution_event_handler = execution_event_handler

    def emit_output(self, event: GatewayOutputEvent) -> None:
        auth_payload = None
        if event.context:
            auth_payload = event.context.get("auth")
        authorized, _ = self._check_auth(auth_payload)
        if not authorized:
            return
        context = dict(event.context) if event.context else {}
        context["_gateway_skip"] = True
        output_event = OutputEvent(
            text=event.text,
            output_type=_resolve_output_type(event.output_type),
            timestamp=event.timestamp,
            lang=event.lang,
            traceback=event.traceback,
            section=event.section,
            context=context,
        )
        emit_output(output_event)

    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        auth_payload = None
        if request.metadata:
            auth_payload = request.metadata.get("auth")
        authorized, reason = self._check_auth(auth_payload)
        if not authorized:
            return GatewayInputResult(text="", metadata={"error": reason})
        provider = get_current_input_provider()
        text = provider.get_multiline_input(
            request.tip,
            preset=request.preset,
            preset_cursor=request.preset_cursor,
        )
        return GatewayInputResult(text=text, metadata=request.metadata)

    def request_confirm(self, request: GatewayConfirmRequest) -> GatewayConfirmResult:
        auth_payload = None
        if request.metadata:
            auth_payload = request.metadata.get("auth")
        authorized, reason = self._check_auth(auth_payload)
        if not authorized:
            return GatewayConfirmResult(
                confirmed=request.default, metadata={"error": reason}
            )
        provider = get_current_input_provider()
        # 使用 get_multiline_input 接收用户输入
        suffix = "[Y/n]" if request.default else "[y/N]"
        result = provider.get_multiline_input(f"{request.message} {suffix}: ")
        # 返回确认结果
        confirmed = request.default if result == "" else result.lower() == "y"
        return GatewayConfirmResult(confirmed=confirmed, metadata=request.metadata)

    def request_choice(self, request: GatewayChoiceRequest) -> GatewayChoiceResult:
        auth_payload = None
        if request.metadata:
            auth_payload = request.metadata.get("auth")
        authorized, reason = self._check_auth(auth_payload)
        if not authorized:
            # 返回默认选择（第一个选项）
            default_index = request.default_index if request.default_index is not None else 0
            return GatewayChoiceResult(
                selected_index=default_index,
                selected_text=request.choices[default_index],
                metadata={"error": reason}
            )
        # 调用 get_choice 函数获取用户选择
        selected_text = get_choice(request.tip, request.choices)
        # 找到选择的索引
        try:
            selected_index = request.choices.index(selected_text)
        except ValueError:
            # 如果找不到，使用默认索引
            selected_index = request.default_index if request.default_index is not None else 0
            selected_text = request.choices[selected_index]
        return GatewayChoiceResult(
            selected_index=selected_index,
            selected_text=selected_text,
            metadata=request.metadata
        )

    def publish_execution_event(
        self,
        event: GatewayExecutionEvent,
        session_id: Optional[str] = None,
    ) -> None:
        auth_payload = None
        payload = event.payload if isinstance(event.payload, dict) else {}
        auth_payload = payload.get("auth")
        authorized, _ = self._check_auth(auth_payload)
        if not authorized:
            return
        if self._execution_event_handler is None:
            return
        self._execution_event_handler(event, session_id)


def _resolve_output_type(output_type: str) -> OutputType:
    try:
        return OutputType[output_type]
    except KeyError:
        pass
    try:
        return OutputType(output_type)
    except Exception:
        return OutputType.INFO
