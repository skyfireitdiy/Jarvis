# Gateway 交互网关模块规范

## 功能概述

Gateway 模块用于统一 Jarvis 的输入/输出/执行流交互，向上提供稳定接口，向下支持 CLI/TUI/Web/GUI 等多种交互方式扩展。开发者只需实现 Gateway 接口即可与 Jarvis 交互。

## 接口定义

### 核心接口

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Iterable

class IGateway(ABC):
    @abstractmethod
    def emit_output(self, event: "GatewayOutputEvent") -> None:
        """发送输出事件"""

    @abstractmethod
    def request_input(self, request: "GatewayInputRequest") -> "GatewayInputResult":
        """请求用户输入"""

    @abstractmethod
    def publish_execution_event(
        self,
        event: "GatewayExecutionEvent",
        session_id: Optional[str] = None,
    ) -> None:
        """发布执行流事件"""
```

### 事件模型

```python
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass(frozen=True)
class GatewayOutputEvent:
    text: str
    output_type: str
    timestamp: bool = True
    lang: Optional[str] = None
    traceback: bool = False
    section: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

@dataclass(frozen=True)
class GatewayInputRequest:
    tip: str
    preset: Optional[str] = None
    preset_cursor: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass(frozen=True)
class GatewayInputResult:
    text: str
    metadata: Optional[Dict[str, Any]] = None

@dataclass(frozen=True)
class GatewayExecutionEvent:
    event_type: str
    payload: Dict[str, Any]
    timestamp: Optional[str] = None
```

## 输入输出说明

### 输入

- `GatewayInputRequest.tip`：提示文本，必填
- `GatewayInputRequest.preset`：预填内容，可选
- `GatewayInputRequest.preset_cursor`：预填光标位置，可选
- `GatewayInputRequest.metadata`：扩展信息，可选

### 输出

- `GatewayInputResult.text`：用户输入结果，必填
- `GatewayInputResult.metadata`：输入来源、会话信息等，可选

### 输出事件

- `GatewayOutputEvent.text`：输出文本
- `GatewayOutputEvent.output_type`：输出类型，如 SYSTEM/ERROR/INFO
- `GatewayOutputEvent.context`：扩展信息，如 TUI/Web 额外状态

### 执行事件

- `GatewayExecutionEvent.event_type`：事件类型，如 stdout/stderr/status
- `GatewayExecutionEvent.payload`：执行事件数据

## 功能行为

### 正常行为

1. 调用 `emit_output` 时，事件被传递给具体交互实现（CLI/TUI/Web/GUI）。
2. 调用 `request_input` 时，返回用户输入结果，保持阻塞或异步由实现决定。
3. 调用 `publish_execution_event` 时，执行流事件被发布给具体交互实现。

### 边界条件

- 空输入：返回空字符串，但不抛异常。
- `output_type` 未识别：由实现层决定降级策略（默认 INFO）。
- 执行事件缺少可选字段：不影响发布。

### 异常处理

- 输入超时：抛出 `InputProviderTimeoutError`（或网关实现自定义异常）。
- 输入断开：抛出 `InputProviderDisconnectedError`。
- 输出/发布失败：记录日志并降级处理，不影响主流程。

## 扩展指南与示例

### 扩展步骤

1. 实现 `IGateway` 接口（或继承 `BaseGateway`）。
2. 在运行时通过 `set_current_gateway()` 注入新实现。
3. 保持输出事件、输入请求、执行流事件的语义不变。

### TUI 扩展示例（概念示意）

```python
from jarvis.jarvis_gateway import IGateway, GatewayOutputEvent, GatewayInputRequest, GatewayInputResult
from jarvis.jarvis_gateway import GatewayExecutionEvent, set_current_gateway

class TUIGateway(IGateway):
    def __init__(self, tui_app):
        self.tui_app = tui_app

    def emit_output(self, event: GatewayOutputEvent) -> None:
        self.tui_app.append_output(event.text, event.output_type)

    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        text = self.tui_app.prompt(request.tip, preset=request.preset)
        return GatewayInputResult(text=text, metadata={"source": "tui"})

    def publish_execution_event(self, event: GatewayExecutionEvent, session_id=None) -> None:
        self.tui_app.update_execution(event.event_type, event.payload, session_id=session_id)

set_current_gateway(TUIGateway(tui_app))
```

### Web 扩展示例（概念示意）

```python
class WebGateway(IGateway):
    def __init__(self, websocket_server):
        self.websocket_server = websocket_server

    def emit_output(self, event: GatewayOutputEvent) -> None:
        self.websocket_server.broadcast({"type": "output", "payload": event.__dict__})

    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        text = self.websocket_server.wait_for_input(request.tip)
        return GatewayInputResult(text=text, metadata={"source": "web"})

    def publish_execution_event(self, event: GatewayExecutionEvent, session_id=None) -> None:
        self.websocket_server.broadcast({"type": "execution", "payload": event.__dict__})
```

### GUI 扩展示例（概念示意）

```python
class GUIGateway(IGateway):
    def __init__(self, ui):
        self.ui = ui

    def emit_output(self, event: GatewayOutputEvent) -> None:
        self.ui.render_output(event.text, style=event.output_type)

    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        text = self.ui.get_user_input(request.tip, preset=request.preset)
        return GatewayInputResult(text=text, metadata={"source": "gui"})

    def publish_execution_event(self, event: GatewayExecutionEvent, session_id=None) -> None:
        self.ui.render_execution_event(event.event_type, event.payload)
```

## 验收标准

1. ✅ Spec 文件位于 `.jarvis/spec/gateway_spec.md` 且命名正确。
2. ✅ Spec 包含功能概述、接口定义、输入输出说明、功能行为、验收标准。
3. ✅ 接口定义涵盖输出、输入、执行流发布三类交互。
4. ✅ 描述边界条件与异常处理策略。
