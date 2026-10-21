# wait_for_message 工具功能规范

## 功能概述

新增一个显式调用的工具 `wait_for_message`，用于"等消息"（等多行输入）。该工具的核心特点是：**等待时忽略 auto_complete 自动补全**——即使当前 Agent 处于非交互模式且 `auto_complete=True`，调用该工具时也不会自动补 `!!!COMPLETE!!!`，而是真正阻塞等待多行输入（或等待其他 Agent 通过消息通道发来的输入）。

**使用场景**：

- 多 Agent 编排（Orchestration）全自动运行时，某个 Agent 在流程中间需要等待其他 Agent 的消息
- 作为开发者，我需要让 Agent 在收到其他 Agent 的消息前保持阻塞等待，不被 auto_complete 提前结束

**功能边界**：

- 范围：仅新增显式工具，不改变 `get_multiline_input` 的默认行为
- 等待方式：复用既有多行输入链路（Gateway 模式走 `gateway.request_input` 等待前端/其他 Agent 注入）
- **启用条件**：工具**仅 Gateway 模式启用**（`check()` 判断 `get_current_gateway() is not None`）；CLI 模式无远端消息来源，工具不注册
- 忽略对象：仅忽略 auto_complete 的自动补全分支，不改变非交互模式的其它行为

## 接口定义

### 1. `get_multiline_input` 新增参数

```python
def get_multiline_input(
    tip: str,
    print_on_empty: bool = True,
    ignore_auto_complete: bool = False,
    timeout: Optional[float] = None,
) -> str:
```

**参数说明**：

- `tip`：提示文本，将显示在底部工具栏中
- `print_on_empty`：当输入为空字符串时，是否打印"输入已取消"提示，默认 `True`
- `ignore_auto_complete`：是否忽略 auto_complete 自动补全，默认 `False`。为 `True` 时跳过非交互模式的自动补全分支，直接进入真实等待
- `timeout`：等待超时秒数（可选），默认 `None` 表示无限等待。仅 Gateway 模式生效；CLI 模式（prompt_toolkit 阻塞）不支持超时，保持无限等待

**返回值**：用户输入的多行文本字符串；取消/超时时返回空字符串。

### 2. 工具 `wait_for_message`

```python
class WaitForMessageTool:
    name = "wait_for_message"
    description = "等待消息（等多行输入），忽略 auto_complete 自动补全。用于多 Agent 编排中阻塞等待其他 Agent 的消息。"

    @staticmethod
    def check() -> bool:
        """仅当存在 Gateway 时启用（CLI 模式无远端消息来源，不注册）。"""
        return get_current_gateway() is not None

    parameters = {
        "type": "object",
        "properties": {
            "tip": {"type": "string", "description": "等待提示文本（可选）"},
            "timeout": {"type": "number", "description": "等待超时秒数（可选），默认无限等待；仅 Gateway 模式生效"},
        },
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
```

**参数说明**：

- `tip`：可选，等待时显示的提示文本，默认 `"等待消息（输入完成后按提交键确认）"`
- `timeout`：可选，等待超时秒数，默认 `None`（无限等待）。超时后返回空字符串（`success: true, stdout: ""`）

**返回格式**：

```json
{
  "success": true,
  "stdout": "<用户输入的多行文本>",
  "stderr": ""
}
```

## 输入输出说明

### 输入

- `ignore_auto_complete=False`（默认）：行为与现状完全一致。非交互 + `auto_complete=True` 时仍返回含 `!!!COMPLETE!!!` 的文本。
- `ignore_auto_complete=True`：跳过 `input.py:1820-1821` 的非交互自动补全分支，直接进入真实等待。此时：
  - Gateway 模式：`gateway.request_input` 等待前端或其他 Agent 通过 `/message` 接口注入消息
- **仅 Gateway 模式**：`wait_for_message` 工具通过 `check()` 判断 gateway 是否存在，无 gateway（CLI 模式）时不注册该工具

### 输出

- 成功：`{"success": true, "stdout": "<输入文本>", "stderr": ""}`
- 取消/空输入：`{"success": true, "stdout": "", "stderr": ""}`
- 异常：`{"success": false, "stdout": "", "stderr": "<错误信息>"}`

## 功能行为

### 正常情况

- 交互模式下调用 `wait_for_message`，阻塞等待用户输入，返回输入内容
- 非交互 + `auto_complete=True` 时调用 `wait_for_message`，**不补 `!!!COMPLETE!!!`**，阻塞等待消息，收到消息后返回

### 边界情况

- 空输入（用户直接确认）：返回空字符串，工具返回 `success: true, stdout: ""`
- `get_multiline_input` 默认参数（`ignore_auto_complete=False`）行为完全不变，不破坏现有功能

### 异常情况

- 输入提供者超时/断开：`get_multiline_input` 内部已处理，返回空字符串
- 其它异常：工具捕获后返回 `success: false` 与错误信息

## 验收标准

1. `get_multiline_input` 新增 `ignore_auto_complete` 参数，默认 `False`，默认行为与现状完全一致
2. `ignore_auto_complete=True` 时，非交互 + `auto_complete=True` 场景下不再返回含 `!!!COMPLETE!!!` 的文本，而是进入真实等待
3. 新增 `wait_for_message` 工具，`name = "wait_for_message"`，位于 `src/jarvis/jarvis_tools/wait_for_message.py`，可被 registry 自动扫描加载
4. 工具 `execute` 调用 `get_multiline_input(..., ignore_auto_complete=True)`，返回输入内容
5. 新增单元测试覆盖：默认行为不受影响、`ignore_auto_complete=True` 绕过补全、工具返回输入内容
6. `get_multiline_input` 新增 `timeout` 参数（默认 `None`），Gateway 模式下透传并超时返回空字符串；CLI 模式不生效保持阻塞
7. 工具 `wait_for_message` 支持 `timeout` 参数，超时返回 `success: true, stdout: ""`
8. 工具**仅 Gateway 模式启用**：`check()` 返回 `get_current_gateway() is not None`；无 gateway（CLI 模式）时 registry 跳过注册，工具不出现在清单
9. 工具已加入 CodeAgent 工具清单（`code_agent.py` 的 `base_tools`）
10. 相关既有测试无回归
