# Web Gateway 应用规范（SDD）

## 1. 目标与范围

### 目标

- 新增独立 Web 前端应用（Vue）与 FastAPI 后端服务，通过 **WebSocket** 对接 Gateway 事件流。
- 支持认证（固定 token/密码，来自前端输入，可通过 HTTP Header 或 WS 初始消息传递）。
- 支持单行/多行输入触发与返回。
- 输出正常渲染至前端（Markdown 渲染）。
- 交互式命令执行时使用 **xterm.js** 进行终端交互显示。

### 非目标

- 不复用现有 `jarvis_config/web_app.py`。
- 不改变现有 CLI 行为。
- 不要求提供完整生产部署脚本。

## 2. 系统边界与组件

### 后端（FastAPI 独立服务）

- 模块目录：`src/jarvis/jarvis_web_gateway/**`
- 负责：
  - WebSocket 接入
  - 会话管理（session_id/connection_id）
  - Gateway 输出/执行事件转发
  - 输入请求与输入结果回传
  - 认证校验（`get_gateway_auth_config()`）

### 前端（Vue 应用）

- 目录：`frontend/`
- 负责：
  - WebSocket 连接与消息处理
  - 输出区 Markdown 渲染
  - 输入区（单行/多行）
  - xterm.js 终端区展示执行事件
  - 认证输入与连接握手

## 3. 接口与协议

### 3.1 WebSocket 地址

- `ws://<host>:<port>/ws`

### 3.2 认证

- 前端提供 `token` 或 `password`。
- 可通过：
  - HTTP Header（Upgrade 时传递）
  - 首条 WS 消息（推荐）
- 后端读取 `gateway_auth` 配置：
  - `enable`: 是否启用认证
  - `token`/`password`: 固定凭据
  - `allow_unset`: 未配置时允许访问

#### 认证消息（首条 WS 消息）

```json
{
  "type": "auth",
  "payload": {
    "token": "optional-token",
    "password": "optional-password"
  }
}
```

#### 认证失败响应

```json
{
  "type": "error",
  "payload": {
    "code": "AUTH_FAILED",
    "message": "gateway auth failed"
  }
}
```

### 3.3 消息类型

#### 输出事件（后端 → 前端）

```json
{
  "type": "output",
  "payload": {
    "text": "...",
    "output_type": "INFO|ERROR|SYSTEM|...",
    "timestamp": true,
    "lang": "markdown|text|...",
    "traceback": false,
    "section": "optional",
    "context": {"session_id": "..."}
  }
}
```

#### 输入请求（后端 → 前端）

```json
{
  "type": "input_request",
  "payload": {
    "tip": "Please input...",
    "preset": "optional",
    "preset_cursor": 0,
    "metadata": {
      "mode": "single|multi",
      "session_id": "..."
    }
  }
}
```

#### 输入结果（前端 → 后端）

```json
{
  "type": "input_result",
  "payload": {
    "text": "user input",
    "metadata": {
      "session_id": "..."
    }
  }
}
```

#### 执行事件（后端 → 前端）

```json
{
  "type": "execution",
  "payload": {
    "event_type": "stdout|stderr|status",
    "data": "...",
    "session_id": "..."
  }
}
```

#### 错误事件（后端 → 前端）

```json
{
  "type": "error",
  "payload": {
    "code": "...",
    "message": "..."
  }
}
```

## 4. 行为规范

### 4.1 输出

- 所有 `GatewayOutputEvent` 转换为 `output` 消息发送到前端。
- 前端按 `lang` 进行 Markdown 或纯文本渲染。

### 4.2 输入

- 后端在收到 `GatewayInputRequest` 时发送 `input_request`。
- 前端根据 `metadata.mode` 渲染单行或多行输入框。
- 提交时发送 `input_result`。

### 4.3 执行事件（xterm.js）

- 当 `GatewayExecutionEvent` 事件出现时，前端将 `stdout/stderr` 追加到 xterm.js。
- `status` 事件用于更新终端状态（可显示执行结束）。

### 4.4 认证

- 若 `gateway_auth.enable=true` 且未通过认证：
  - 连接立即返回 `AUTH_FAILED`。
- 若未配置且 `allow_unset=true`：
  - 默认允许连接。

## 5. 数据结构与约束

- `session_id`: 可选，由后端生成或由前端提供。
- `connection_id`: 后端内部用于管理 WS 连接。
- 输入/输出事件必须带可选 `session_id` 以便多会话隔离。

## 6. UI 交互规范（Vue）

- 输出区：滚动展示输出，Markdown 渲染。
- 输入区：
  - 单行模式：Enter 提交
  - 多行模式：支持换行 + 提交按钮
- 终端区：xterm.js 实例，显示交互式执行流。
- 认证区：连接前输入 token/password。

## 7. 异常与边界

- WS 断开：后端回收 session；前端提示断线并允许重连。
- 输入超时：后端返回 `error` 消息。
- 认证失败：返回 `AUTH_FAILED`，前端提示重新输入。

## 8. 验收标准

1. ✅ `.jarvis/spec/web_gateway_app_spec.md` 创建且内容包含：WS 协议、认证流程、消息结构、UI 交互与验收标准。
2. ✅ 后端可通过 WebSocket 接收/发送 output/input/execution 事件（实现阶段验证）。
3. ✅ 前端支持 Markdown 输出、单/多行输入、xterm.js 展示（实现阶段验证）。
4. ✅ 认证启用时拒绝无凭据连接；未配置时默认允许。
