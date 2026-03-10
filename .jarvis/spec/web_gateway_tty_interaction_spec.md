# Web Gateway TTY 交互规范

## 功能概述

为 Web Gateway 提供 xterm.js 与后端真实 TTY 的双向交互能力。用户在 Web 终端输入的内容应实时发送到后端 PTY，后端输出实时回传并渲染在终端内。该功能不影响现有 CLI 行为，默认不破坏现有输出/输入逻辑。

## 使用场景

- 用户在 Web 前端通过 xterm.js 直接与 `execute_script` 的交互式命令（如 htop、python REPL、bash）交互。
- 后端通过 PTY 捕获输出并推送到前端，前端将用户输入发送给后端。

## 接口定义

### WebSocket 消息协议（新增/扩展）

#### 1) terminal_input

- **方向**：前端 → 后端
- **用途**：前端发送终端输入事件到后端 PTY
- **格式**：

```json
{
  "type": "terminal_input",
  "payload": {
    "execution_id": "<string>",
    "data": "<string>"
  }
}
```

#### 2) execution（已有）

- **方向**：后端 → 前端
- **用途**：后端流式输出执行事件
- **扩展说明**：
  - `payload.event_type` 使用 `stdout` / `stderr` / `stdin` / `status`
  - `payload.message_type` 使用 `tool_stream_start` / `tool_stream` / `tool_stream_end` / `tool_input`

## 输入输出说明

### 前端输入

- `execution_id`: 必填，标识该终端所属执行实例
- `data`: 必填，终端输入数据（单字符或批量）

### 后端输出

- 通过既有 `execution` 事件推送输出
- 不改变输出结构，仅确保输入事件可驱动 PTY 输入

## 功能行为

### 正常流程

1. 前端收到 `execution` 事件，创建对应 xterm 终端。
2. 用户在 xterm 输入，触发 `onData`，发送 `terminal_input` 消息。
3. 后端收到 `terminal_input`，根据 `execution_id` 定位 PTY 并写入输入。
4. PTY 输出通过 `execution` 事件回传前端，前端写入终端。

### 边界条件

- 若 `execution_id` 未找到对应 PTY：后端返回 `error` 消息，不崩溃。
- 若终端已结束（`tool_stream_end`）：前端禁用输入，不再发送 `terminal_input`。
- 允许输入空字符串但不应发送。

### 异常处理

- WebSocket 断开：后端清理会话与执行上下文。
- PTY 写入失败：后端记录错误并返回 `error` 消息。

## 验收标准

1. **交互输入生效**：在 Web 终端输入内容后，后端 PTY 能收到并产生正确输出。
2. **输出可见**：交互式命令（如 `python -i` 或 `htop`）的输出能实时显示在 Web 终端。
3. **多终端隔离**：不同 `execution_id` 的终端输入输出互不影响。
4. **结束禁用**：收到 `tool_stream_end` 后终端进入只读状态，不再发送输入。
5. **兼容性**：未启用 Web Gateway 时，CLI 行为不变。

## 验证方法

- 启动 Web Gateway：

  ```bash
  jvs --web-gateway --web-gateway-host 0.0.0.0 --web-gateway-port 5005 --keep-jvs
  ```

- 前端执行交互命令：
  - `python -i`
  - `bash` / `sh`
  - `htop`（若可用）
- 验证输入输出闭环与终端隔离。
