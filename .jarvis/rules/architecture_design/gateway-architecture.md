# Jarvis 网关架构设计规则

本文档描述 Jarvis 系统的网关架构，用于指导后续相关功能的扩展开发。

## 1. 整体架构概述

Jarvis 采用分层网关架构，主要包含以下层次：

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端层                                  │
│  ┌─────────────┐              ┌─────────────────┐              │
│  │   前端      │              │  VSCode 插件    │              │
│  │ (Vue.js)    │              │   (TypeScript)  │              │
│  └──────┬──────┘              └────────┬────────┘              │
└─────────┼──────────────────────────────┼───────────────────────┘
          │                              │
          │ WebSocket                    │ WebSocket
          ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Web 网关层                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              jarvis_web_gateway (FastAPI)               │   │
│  │  - Agent 管理 (agent_manager.py)                        │   │
│  │  - 节点管理 (node_manager.py)                           │   │
│  │  - 代理管理 (agent_proxy_manager.py)                    │   │
│  │  - 终端会话 (terminal_session_manager.py)              │   │
│  └──────────────────────────┬──────────────────────────────┘   │
└─────────────────────────────┼───────────────────────────────────┘
                              │
                              │ WebSocket / HTTP
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agent 网关层                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              jarvis_gateway (BaseGateway)               │   │
│  │  - 输入桥接 (input_bridge.py)                           │   │
│  │  - 输出桥接 (output_bridge.py)                          │   │
│  │  - 事件处理 (events.py)                                 │   │
│  └──────────────────────────┬──────────────────────────────┘   │
└─────────────────────────────┼───────────────────────────────────┘
                              │
                              │ 进程调用
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agent 代理层                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              jarvis_agent (Agent 实现)                  │   │
│  │  - 会话管理 (session_manager.py)                        │   │
│  │  - 规则管理 (rules_manager.py)                          │   │
│  │  - 任务管理 (task_manager.py)                           │   │
│  │  - 工具执行 (tool_executor.py)                          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 核心组件职责

### 2.1 Web 网关 (jarvis_web_gateway)

**代码位置**: `src/jarvis/jarvis_web_gateway/`

**职责**: 作为对外的统一入口，提供 WebSocket 和 HTTP 接口，管理 Agent 生命周期和节点连接。

**核心模块**:

| 模块 | 文件 | 职责 |
|------|------|------|
| Agent 管理器 | `agent_manager.py` | 创建、停止、监控 Agent 子进程，分配端口 |
| 节点管理器 | `node_manager.py` | 管理主从节点连接，处理节点间通信协议 |
| 代理管理器 | `agent_proxy_manager.py` | 反向代理前端请求到 Agent 端口 |
| 终端会话 | `terminal_session_manager.py` | 管理交互式终端会话 |
| 主应用 | `app.py` | FastAPI 应用入口，WebSocket 处理 |

### 2.2 Agent 网关 (jarvis_gateway)

**代码位置**: `src/jarvis/jarvis_gateway/`

**职责**: 定义 Agent 交互的抽象接口，实现输入/输出/确认的桥接。

**核心模块**:

| 模块 | 文件 | 职责 |
|------|------|------|
| 网关接口 | `gateway.py` | 定义 IGateway 接口和 BaseGateway 实现 |
| 输入桥接 | `input_bridge.py` | 管理输入会话注册和请求处理 |
| 输出桥接 | `output_bridge.py` | 路由输出到不同客户端 |
| 事件定义 | `events.py` | 定义 GatewayInputRequest、GatewayOutputEvent 等 |

### 2.3 Agent 代理 (jarvis_agent)

**代码位置**: `src/jarvis/jarvis_agent/`

**职责**: 核心 Agent 实现，处理用户请求、执行任务、管理会话。

**核心模块**:

| 模块 | 文件 | 职责 |
|------|------|------|
| 主入口 | `jarvis.py` | Agent 主逻辑，消息处理循环 |
| 会话管理 | `session_manager.py` | 管理对话会话和上下文 |
| 规则管理 | `rules_manager.py` | 加载和管理规则系统 |
| 任务管理 | `task_manager.py` | 任务拆分和执行 |
| 工具执行 | `tool_executor.py` | 执行工具调用 |

### 2.4 前端 (jarvis_service/frontend)

**代码位置**: `src/jarvis/jarvis_service/frontend/`

**技术栈**: Vue.js + TypeScript

**职责**: 提供 Web 界面，通过 WebSocket 与网关通信。

**关键功能**:
- WebSocket 连接管理（主连接 + 多 Agent 连接）
- 网关地址配置和持久化
- 消息收发和状态显示

### 2.5 VSCode 插件 (jarvis_vscode_extension)

**代码位置**: `src/jarvis/jarvis_vscode_extension/`

**技术栈**: TypeScript

**职责**: 提供 IDE 内的 Agent 交互界面。

**关键功能**:
- WebSocket 连接管理
- 面板状态管理
- 代码更新推送

## 3. 组件间关系

### 3.1 连接关系图

```
┌──────────────┐         WebSocket          ┌──────────────────┐
│   前端       │ ──────────────────────────▶│                  │
│ (Vue.js)     │◀────────────────────────────│                  │
└──────────────┘                             │                  │
                                              │  jarvis_web      │
┌──────────────┐         WebSocket          │  _gateway        │
│ VSCode 插件  │ ──────────────────────────▶│  (FastAPI)       │
│(TypeScript)  │◀────────────────────────────│                  │
└──────────────┘                             │  ┌────────────┐  │
                                              │  │  Agent     │  │
                                              │  │  Manager   │  │
                                              │  └────────────┘  │
                                              │  ┌────────────┐  │
                                              │  │  Node      │  │
                                              │  │  Manager   │  │
                                              │  └────────────┘  │
                                              │                  │
                                              └────────┬─────────┘
                                                       │
                                              HTTP/WS  │
                                                       ▼
                                              ┌──────────────────┐
                                              │                  │
                                              │  jarvis_gateway  │
                                              │  (BaseGateway)   │
                                              │                  │
                                              └────────┬─────────┘
                                                       │
                                              进程调用 │
                                                       ▼
                                              ┌──────────────────┐
                                              │                  │
                                              │  jarvis_agent    │
                                              │  (子进程)        │
                                              │                  │
                                              └──────────────────┘
```

### 3.2 数据流分析

**场景1: 用户通过前端发送消息**

```
前端 ─(WebSocket)─▶ Web网关 ─(HTTP/子进程)─▶ Agent网关 ─(进程调用)─▶ Agent代理
     │                                        │
     │◀─────────────── (输出事件) ────────────┘
```

**步骤**:
1. 前端建立 WebSocket 连接到 Web 网关
2. 前端发送消息到 Web 网关
3. Web 网关通过 HTTP 或子进程方式调用 Agent 网关
4. Agent 网关触发 Agent 代理处理请求
5. Agent 代理产生输出，通过网关返回
6. Web 网关通过 WebSocket 推送到前端

**场景2: 创建新 Agent**

```
前端 ─(API)─▶ AgentManager ─(spawn)─▶ Agent子进程 ─(连接)─▶ Agent网关
```

**步骤**:
1. 前端调用创建 Agent 的 API
2. AgentManager 分配端口和资源
3. 启动 Agent 子进程
4. Agent 子进程连接到 Agent 网关
5. 返回 Agent 信息给前端

**场景3: 节点间通信**

```
主节点 Web网关 ─(WebSocket)─▶ 子节点 Web网关
```

**步骤**:
1. 子节点通过 WebSocket 连接到主节点
2. 主节点通过 NodeConnectionManager 管理连接
3. 支持节点间的 Agent 代理请求转发

## 4. 接口设计

### 4.1 Web 网关 API

**HTTP 接口**:

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 创建 Agent | POST | `/api/agent/create` | 创建新的 Agent 实例 |
| 列出 Agent | GET | `/api/agents` | 获取所有 Agent 列表 |
| 停止 Agent | POST | `/api/agent/{agent_id}/stop` | 停止指定 Agent |
| 删除 Agent | DELETE | `/api/agent/{agent_id}` | 删除指定 Agent |
| 节点代理 | POST | `/api/node/{node_id}/agent/{agent_id}/http` | HTTP 代理请求 |

**WebSocket 接口**:

| 接口 | 路径 | 说明 |
|------|------|------|
| 主连接 | `/ws` | 主 WebSocket 连接，用于通用消息 |
| Agent 连接 | `/ws/agent/{agent_id}` | 专用 Agent 连接 |
| 节点连接 | `/ws/node` | 节点间通信连接 |

### 4.2 Agent 网关接口

**IGateway 接口** (`gateway.py`):

```python
class IGateway(ABC):
    def emit_output(self, event: GatewayOutputEvent) -> None:
        """发送输出事件"""

    def request_input(self, request: GatewayInputRequest) -> GatewayInputResult:
        """请求用户输入"""

    def request_confirm(self, request: GatewayConfirmRequest) -> GatewayConfirmResult:
        """请求用户确认"""

    def publish_execution_event(self, event: GatewayExecutionEvent, session_id: Optional[str] = None) -> None:
        """发布执行流事件"""
```

### 4.3 节点间协议

**节点协议** (`node_protocol.py`):

| 消息类型 | 说明 |
|----------|------|
| AGENT_CREATE_REQUEST | 跨节点创建 Agent |
| AGENT_HTTP_REQUEST | 跨节点 HTTP 代理 |
| AGENT_LIST_REQUEST | 获取节点上的 Agent 列表 |
| AGENT_STOP_REQUEST | 跨节点停止 Agent |
| NODE_HEARTBEAT | 节点心跳 |
| CONFIG_SYNC_REQUEST | 配置同步 |

## 5. 扩展开发指导

### 5.1 添加新的客户端类型

1. 实现 WebSocket 连接到 `jarvis_web_gateway`
2. 使用相同的消息协议（参考 `events.py`）
3. 处理 GatewayOutputEvent、GatewayExecutionEvent 等事件

### 5.2 添加新的 Agent 类型

1. 在 `AgentManager.AGENT_ENTRY_POINTS` 注册入口点
2. 实现标准的输入/输出接口（遵循 IGateway）
3. 在前端添加对应的 UI 支持

### 5.3 添加新的节点类型

1. 实现 WebSocket 客户端连接到主节点
2. 实现节点协议消息处理
3. 在 node_manager.py 注册节点类型

### 5.4 添加新的网关功能

1. 在 `jarvis_web_gateway/app.py` 添加新的 API 端点
2. 在 `jarvis_gateway/events.py` 定义新的事件类型
3. 在前端和 VSCode 插件中添加对应的处理逻辑

## 6. 代码位置索引

| 组件 | 目录 | 关键文件 |
|------|------|----------|
| Web 网关 | `src/jarvis/jarvis_web_gateway/` | app.py, agent_manager.py, node_manager.py |
| Agent 网关 | `src/jarvis/jarvis_gateway/` | gateway.py, input_bridge.py, output_bridge.py |
| Agent 代理 | `src/jarvis/jarvis_agent/` | jarvis.py, session_manager.py, rules_manager.py |
| 前端 | `src/jarvis/jarvis_service/frontend/src/` | App.vue |
| VSCode 插件 | `src/jarvis/jarvis_vscode_extension/src/` | extension.ts |

## 7. 相关文档

- [反向工程规则](../architecture_design/reverse_engineering.md)
- [整洁架构](../architecture_design/clean_architecture.md)
- [SOLID 设计原则](../architecture_design/solid.md)
