# Web Gateway 使用指南

## 概述

Web Gateway 是 Jarvis 的独立 Web 界面，通过 WebSocket 对接 Gateway 事件流，提供友好的 Web 交互界面。

## 功能特性

- ✅ **输出展示**：支持 Markdown 和普通文本渲染
- ✅ **输入交互**：支持单行/多行输入切换
- ✅ **终端交互**：使用 xterm.js 进行交互式命令执行
- ✅ **多终端管理**：每个 `execute_script` 调用创建独立终端
- ✅ **认证支持**：基于配置的固定 token/密码认证
- ✅ **WS 通信**：实时双向通信，低延迟

## 架构说明

```text
┌─────────────┐     WebSocket     ┌──────────────────┐
│   Vue 前端   │ ◄──────────────► │  FastAPI 后端    │
│ (frontend/)  │                   │(jarvis_web_gateway)│
└─────────────┘                   └────────┬─────────┘
                                            │
                                    Gateway 事件流
                                            │
                                    ┌───────▼───────┐
                                    │ Gateway 模块  │
                                    │ (jarvis_gateway)│
                                    └───────────────┘
```

## 快速开始

### 1. 启动后端（CLI 集成模式）

启动 Jarvis 时添加 `--web-gateway` 参数：

```bash
# 使用默认配置（host=0.0.0.0, port=8000）
jvs --web-gateway

# 自定义 host 和 port
jvs --web-gateway --web-gateway-host 127.0.0.1 --web-gateway-port 5005

# 启动 Code Agent Web Gateway
jvs-ca --web-gateway --web-gateway-host 127.0.0.1 --web-gateway-port 5006
```

启动后会输出 WebSocket 地址：

```text
WebGateway started: ws://0.0.0.0:8000/ws
```

### 2. 启动前端

```bash
# 进入前端目录
cd frontend

# 安装依赖（首次运行）
npm install

# 启动开发服务器
npm run dev
```

访问前端地址（通常是 `http://localhost:5173`）

### 3. 连接 WebSocket

在前端界面中：

1. 填写认证信息（可选）
   - Token：配置文件中设置的 `gateway_auth.token`
   - Password：配置文件中设置的 `gateway_auth.password`
2. 填写后端地址和端口
   - 后端地址：如 `127.0.0.1`
   - 后端端口：如 `8000`
3. Session ID：留空自动生成
4. 点击「连接 WebSocket」按钮

连接成功后会显示「已连接」状态，且后端日志中会输出 session 信息。

## 认证配置

在配置文件中添加 `gateway_auth` 配置：

```json
{
  "gateway_auth": {
    "enable": true,
    "token": "your-secret-token",
    "password": "your-secret-password",
    "allow_unset": true
  }
}
```

配置说明：

- `enable`：是否启用认证（默认 `false`）
- `token`：固定 token 认证凭据（与 password 二选一或都设置）
- `password`：固定密码认证凭据（与 token 二选一或都设置）
- `allow_unset`：未配置时是否允许访问（默认 `true`，保持 CLI 兼容）

## WebSocket 消息协议

### 1. 认证消息（首条消息）

```json
{
  "type": "auth",
  "payload": {
    "token": "optional-token",
    "password": "optional-password"
  }
}
```

### 2. 输出事件（后端 → 前端）

```json
{
  "type": "output",
  "payload": {
    "text": "Hello World",
    "output_type": "INFO",
    "lang": "markdown",
    "timestamp": "2024-01-01 12:00:00",
    "section": "系统"
  }
}
```

### 3. 输入请求（后端 → 前端）

```json
{
  "type": "input_request",
  "payload": {
    "tip": "请输入您的选择",
    "preset": "",
    "metadata": {
      "mode": "single",
      "session_id": "uuid"
    }
  }
}
```

### 4. 输入结果（前端 → 后端）

```json
{
  "type": "input_result",
  "payload": {
    "text": "用户输入内容",
    "metadata": {
      "session_id": "uuid"
    }
  }
}
```

### 5. 执行事件（后端 → 前端）

```json
{
  "type": "execution",
  "payload": {
    "execution_id": "exec-123",
    "message_type": "tool_stream",
    "event_type": "stdout",
    "data": "command output"
  }
}
```

### 6. 错误事件（后端 → 前端）

```json
{
  "type": "error",
  "payload": {
    "code": "AUTH_FAILED",
    "message": "认证失败"
  }
}
```

## 多终端管理

前端支持多终端管理，每个 `execute_script` 调用会创建独立的终端实例：

- **动态创建**：页面加载时不创建终端，收到 `execution` 事件时动态创建
- **执行状态**：终端显示 `execution_id` 和完成状态
- **交互控制**：执行期间允许键盘输入，完成后禁用交互（只读）
- **垂直布局**：多个终端垂直排列，互不影响

## 故障排查

### 问题 1：无法连接 WebSocket

**原因**：后端未启动或端口配置错误

**解决方案**：

- 检查后端是否启动：`jvs --web-gateway`
- 检查端口是否正确：默认 `8000`，可用 `--web-gateway-port` 自定义
- 检查防火墙设置

### 问题 2：认证失败

**原因**：认证信息不正确或配置问题

**解决方案**：

- 检查配置文件 `gateway_auth` 配置
- 确认 `allow_unset` 设置（未配置时允许）
- 检查前端输入的 token/password 是否正确

### 问题 3：终端无输出

**原因**：执行事件未正确转发

**解决方案**：

- 检查浏览器控制台是否有错误
- 检查后端日志是否有 `execution` 事件输出
- 确认 `execute_script` 调用是否正常执行

### 问题 4：前端无法启动

**原因**：依赖未安装或端口冲突

**解决方案**：

- 运行 `npm install` 安装依赖
- 检查 5173 端口是否被占用，或修改 `vite.config.js` 中的端口配置

## 开发与调试

### 后端调试

```bash
# 设置日志级别为 DEBUG
export LOG_LEVEL=DEBUG

# 启动 Web Gateway
jvs --web-gateway --web-gateway-port 8000
```

### 前端调试

```bash
# 进入前端目录
cd frontend

# 启动开发服务器（支持热重载）
npm run dev
```

浏览器控制台会输出详细的 WebSocket 消息日志，便于调试。

## 验收标准

- ✅ 后端可启动并输出 WebSocket 地址
- ✅ 前端可连接 WebSocket（认证成功/失败符合配置）
- ✅ 输出可见（Markdown 正常渲染）
- ✅ 输入可回传（单行/多行切换正常）
- ✅ 终端交互（xterm.js 显示执行输出）
- ✅ 多终端管理（独立终端、动态创建、状态跟踪）
- ✅ CLI 默认行为不受影响（未启用 `--web-gateway` 时）

## 技术栈

- **后端**：FastAPI + WebSocket
- **前端**：Vue 3 + Vite + xterm.js + marked
- **认证**：基于配置的固定 token/密码
- **通信**：WebSocket（实时双向）

## 相关文档

- [Gateway 模块规范](./gateway_spec.md)
- [Web Gateway 应用规范](./web_gateway_app_spec.md)
