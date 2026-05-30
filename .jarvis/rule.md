# 项目综述

## 项目概述

**项目名称**: Jarvis AI Assistant  
**版本**: 3.1.2  
**定位**: 本地运行、开箱即用、可深度定制的 AI 开发助手平台  
**目标用户**: 个人开发者、工程团队、专项场景用户

### 核心能力

- 分析项目结构，生成执行计划
- 修改代码后自动验证（Git、构建、静态检查、影响分析）
- 安全扫描与报告聚合
- C→Rust 迁移流水线
- 方法论沉淀、记忆分层、规则按需加载
- 支持 CLI、Web、VSCode 三种访问方式

## 技术栈

### 编程语言

- **Python**: 3.12 (严格要求)

### 核心框架

- **FastAPI**: 0.115.12 (Web 服务框架)
- **Uvicorn**: 0.33.0 (ASGI 服务器)
- **OpenAI SDK**: 1.78.1 (AI 模型调用)
- **Anthropic SDK**: >=0.40.0 (Claude 模型支持)

### 关键依赖

- **代码解析**: tree-sitter 系列 (支持 JS/TS/Rust/Go/Java/C/C++/Python/HTML/CSS/SQL/YAML/Markdown 等)
- **终端UI**: prompt_toolkit, pygments, rich, pyte
- **Web抓取**: playwright, beautifulsoup4, lxml, markdownify
- **文本处理**: tiktoken, jieba, fuzzywuzzy, python-Levenshtein
- **代码检查**: ruff, bandit, python-lsp-server
- **测试**: pytest, pytest-xdist, pytest-asyncio

## 目录结构

```text
Jarvis/
├── src/jarvis/                    # 核心源码
│   ├── jarvis_agent/             # 主Agent模块（122KB核心文件）
│   │   ├── jarvis.py             # Jarvis主类
│   │   ├── run_loop.py           # 运行循环
│   │   ├── session_manager.py    # 会话管理
│   │   ├── rules_manager.py      # 规则管理
│   │   ├── task_list.py          # 任务列表
│   │   ├── tool_executor.py      # 工具执行器
│   │   ├── builtin_input_handler.py  # 内置输入处理
│   │   ├── prompts.py            # 提示词模板
│   │   └── language_support_info.py  # 语言支持信息
│   ├── jarvis_code_agent/        # 代码Agent模块
│   │   ├── code_agent.py         # 代码Agent核心（76KB）
│   │   ├── code_reviewer.py       # 代码审查
│   │   ├── code_analyzer/        # 代码分析器
│   │   ├── diff_visualizer.py    # 差异可视化
│   │   └── worktree_manager.py   # Git worktree管理
│   ├── jarvis_tools/             # 工具集（54KB注册器）
│   │   ├── registry.py            # 工具注册中心
│   │   ├── edit_file.py           # 文件编辑
│   │   ├── execute_script.py      # 脚本执行
│   │   ├── read_code.py           # 代码读取
│   │   ├── task_list_manager.py   # 任务列表管理（106KB）
│   │   └── memory.py              # 记忆管理
│   ├── jarvis_tui/               # 终端UI模块
│   ├── jarvis_service/           # Web服务模块
│   ├── jarvis_vscode_extension/  # VSCode插件
│   ├── jarvis_browser/           # 浏览器自动化
│   ├── jarvis_c2rust/            # C→Rust迁移
│   ├── jarvis_mcp/                # MCP协议集成
│   ├── jarvis_config/             # 配置管理
│   └── jarvis_memory_organizer/   # 记忆组织器
├── tests/                        # 测试目录
│   ├── jarvis_agent/
│   ├── jarvis_code_agent/
│   ├── jarvis_tools/
│   └── performance/
├── builtin/rules/                # 内置规则
│   ├── development_workflow/      # 开发工作流
│   ├── code_quality/             # 代码质量
│   ├── security/                 # 安全
│   └── architecture_design/      # 架构设计
├── .jarvis/                      # Jarvis配置目录
│   ├── rule/                     # 项目规则文件
│   ├── memory/                   # 记忆存储
│   ├── sessions/                 # 会话存储
│   └── symbol_cache/             # 符号缓存
├── docs/                         # 文档
├── frontend/                     # 前端代码
├── pyproject.toml                # 项目配置
├── setup.py                      # 安装脚本
├── Dockerfile                    # Docker镜像
└── docker-compose.yml            # Docker编排
```

## 核心模块

### jarvis_agent (主Agent模块)

- **职责**: 核心Agent逻辑、会话管理、规则加载、任务调度
- **关键文件**:
  - `jarvis.py`: Jarvis主类，入口点
  - `run_loop.py`: 主运行循环，处理用户输入
  - `session_manager.py`: 会话生命周期管理
  - `rules_manager.py`: 规则加载与匹配
  - `builtin_input_handler.py`: 内置输入处理逻辑
- **依赖**: jarvis_tools, jarvis_code_agent

### jarvis_code_agent (代码Agent模块)

- **职责**: 代码修改、审查、构建验证、Lint检查
- **关键文件**:
  - `code_agent.py`: 代码Agent核心实现
  - `code_reviewer.py`: 自动代码审查
  - `code_agent_build.py`: 构建验证
  - `code_agent_lint.py`: Lint检查集成
  - `code_agent_diff.py`: Diff生成与处理
- **依赖**: tree-sitter系列, ruff, bandit

### jarvis_tools (工具集)

- **职责**: 提供Agent可调用的所有工具
- **关键文件**:
  - `registry.py`: 工具注册中心（管理所有工具）
  - `edit_file.py`: 文件编辑工具
  - `execute_script.py`: 脚本执行工具
  - `read_code.py`: 代码读取与符号分析
  - `task_list_manager.py`: 复杂任务拆分与执行
  - `memory.py`: 长期/短期记忆管理
  - `load_rule.py`: 规则加载工具
  - `symbol_dependency.py`: 符号依赖分析

### jarvis_service (Web服务)

- **职责**: 提供HTTP API访问方式，支持分布式部署
- **入口**: `jarvis-service start`
- **依赖**: FastAPI, Uvicorn, WebSockets

### jarvis_vscode_extension (VSCode插件)

- **职责**: IDE集成，Agent侧边栏、聊天面板、终端
- **关键文件**: `jarvis_vscode_extension/` 目录

## 代理与节点架构

### 整体通信架构

```text
┌──────────────┐                    ┌─────────────────────────────────────┐
│  Web 前端    │ ──── WebSocket ──▶ │           Master 节点                 │
│  (浏览器)    │ ◀─── WebSocket ──  │      (jarvis_web_gateway)            │
│              │                    │  ┌─────────────────────────────┐    │
│              │ ──── HTTP ──────▶  │  │ /ws          主连接         │    │
│              │                    │  │ /api/agent/{id}/ws  Agent WS │    │
│              │                    │  │ /api/agents   管理接口      │    │
│              │                    │  └─────────────────────────────┘    │
└──────────────┘                    │                 │                   │
                                    │    WebSocket    │    HTTP/WS       │
                                    │   (节点间协议)   │  (本地代理)      │
                                    │                 ▼                   │
                                    │  ┌─────────────────────────────┐    │
                                    │  │      Child 节点 (可选)       │    │
                                    │  │   (jarvis_web_gateway)      │    │
                                    │  └───────────┬─────────────────┘    │
                                    └──────────────┼─────────────────────┘
                                                   │ HTTP/WS (本地代理)
                                                   ▼
                                    ┌─────────────────────────────────────┐
                                    │           Agent 进程                 │
                                    │    (独立子进程，监听随机端口)         │
                                    │  ┌─────────────────────────────┐    │
                                    │  │ /ws          消息收发        │    │
                                    │  │ /status      状态查询        │    │
                                    │  │ /message     消息注入        │    │
                                    │  │ /sessions    会话管理        │    │
                                    │  └─────────────────────────────┘    │
                                    └─────────────────────────────────────┘
```

### 组件间通信关系详解

#### 1. Web前端 ↔ Master节点

| 方向        | 协议      | 端点                                      | 用途                                |
| ----------- | --------- | ----------------------------------------- | ----------------------------------- |
| 前端→Master | WebSocket | `/ws`                                     | 主连接，发送用户输入、接收Agent输出 |
| 前端→Master | WebSocket | `/api/agent/{agent_id}/ws`                | Agent专用连接，独立于主连接         |
| 前端→Master | WebSocket | `/api/node/{node_id}/agent/{agent_id}/ws` | 指定节点的Agent连接                 |
| 前端→Master | HTTP      | `/api/auth/login`                         | 登录获取Token                       |
| 前端→Master | HTTP      | `/api/agents`                             | 创建/列出/停止/删除Agent            |
| 前端→Master | HTTP      | `/api/agent/{agent_id}/*`                 | 代理到Agent的HTTP请求               |

#### 2. Master节点 ↔ Child节点

| 方向         | 协议      | 端点                            | 用途                 |
| ------------ | --------- | ------------------------------- | -------------------- |
| Child→Master | WebSocket | `/ws/node`                      | 子节点注册、心跳保活 |
| Master→Child | 节点协议  | `AGENT_CREATE_REQUEST`          | 跨节点创建Agent      |
| Master→Child | 节点协议  | `AGENT_HTTP_REQUEST`            | 跨节点HTTP代理       |
| Master→Child | 节点协议  | `AGENT_WS_OPEN/SEND/RECV/CLOSE` | 跨节点WebSocket代理  |
| Child→Master | 节点协议  | `NODE_HEARTBEAT`                | 心跳保活             |

#### 3. Master/Child节点 ↔ Agent进程

| 方向       | 协议      | 地址                             | 用途               |
| ---------- | --------- | -------------------------------- | ------------------ |
| 节点→Agent | HTTP      | `http://127.0.0.1:{port}/{path}` | 反向代理HTTP请求   |
| 节点→Agent | WebSocket | `ws://127.0.0.1:{port}/ws`       | 双向消息转发       |
| Agent→节点 | WebSocket | 回复消息                         | 输出事件、执行状态 |

#### 4. Agent进程内部端点

Agent进程启动时在随机端口上启动微型Web服务（uvicorn），提供以下端点：

| 端点        | 方法      | 用途                                     |
| ----------- | --------- | ---------------------------------------- |
| `/ws`       | WebSocket | WebSocketConnectionManager处理，消息收发 |
| `/status`   | GET       | 返回Agent执行状态                        |
| `/diff`     | GET       | 返回代码差异                             |
| `/rules`    | GET       | 返回已加载规则                           |
| `/tools`    | GET       | 返回可用工具列表                         |
| `/sessions` | GET/POST  | 会话管理                                 |
| `/message`  | POST      | 接收其他Agent发来的消息，注入到输入流    |

### 节点模式

Jarvis 支持分布式部署，采用 **Master/Child** 节点模式：

- **Master 节点**：对外统一入口，管理所有子节点连接，路由 Agent 请求
- **Child 节点**：运行 Agent 实例，通过 WebSocket 长连接注册到 Master

**核心组件**：

| 组件         | 文件                                  | 职责                                                                              |
| ------------ | ------------------------------------- | --------------------------------------------------------------------------------- |
| 节点配置     | `jarvis_web_gateway/node_config.py`   | NodeRuntimeConfig，定义 node_mode(master/child)、node_id、master_url、node_secret |
| 节点运行时   | `jarvis_web_gateway/node_runtime.py`  | NodeRuntime，管理 NodeRegistry、AgentRouteRegistry、TokenSyncState                |
| 节点连接管理 | `jarvis_web_gateway/node_manager.py`  | NodeConnectionManager(Master端)，管理子节点 WebSocket 连接，处理节点间请求转发    |
| 子节点客户端 | `jarvis_web_gateway/node_manager.py`  | ChildNodeClient(Child端)，连接 Master、心跳保活、接收并处理 Master 下发的请求     |
| 节点协议     | `jarvis_web_gateway/node_protocol.py` | 定义节点间所有消息类型和消息构建工具                                              |

**节点生命周期**：

1. Child 启动 → 通过 `node_secret` 认证连接 Master `/ws/node`
2. Master 返回 `JARVIS_AUTH_TOKEN` → Child 同步到环境变量
3. Child 心跳保活（`NODE_HEARTBEAT`），断线自动重连
4. Master 通过 `NodeConnectionManager.send_request_to_node()` 向 Child 发送请求

### Agent 路由

**AgentRouteRegistry** 维护 agent_id → node_id 的映射关系：

- Agent 创建时注册路由（`register`），删除时移除（`remove`）
- Master 收到浏览器请求时，通过路由表确定 Agent 所在节点
- 浏览器重连不影响路由（路由与 Agent 生命周期绑定，非连接绑定）

### 本地 Agent 代理

**AgentProxyManager** 负责将前端请求反向代理到本地 Agent：

- **HTTP 代理**：`proxy_http_request()` → 转发到 `http://127.0.0.1:{port}/{path}`
- **WebSocket 代理**：`proxy_websocket()` → 连接 `ws://127.0.0.1:{port}/ws`
  - 通过 subprotocol `jarvis-token.{auth_token}` 传递认证
  - 连接后发送 auth JSON 消息 `{"type": "auth", "payload": {"token": ...}}`
  - 双向转发：client→agent 和 agent→client 并行任务
  - 消息缓存：客户端断开时缓存 Agent 消息（`_agent_message_cache`，上限200条），重连后刷新（`_flush_cached_messages`）

### 远程 Agent 代理

当 Agent 运行在 Child 节点时，Master 通过 **SEND/RECV 轮询模式** 代理 WebSocket：

```text
浏览器 → Master /api/agent/{agent_id}/ws
  → NodeConnectionManager.send_request_to_node(AGENT_WS_OPEN_REQUEST)
  → Child _handle_agent_ws_open_request() → 连接 Agent ws://127.0.0.1:{port}/ws
  → 存入 _agent_ws_sessions[session_id]
双向转发：AGENT_WS_SEND_REQUEST / AGENT_WS_RECV_REQUEST 轮询
```

**关键差异（本地 vs 远程）**：

- 本地代理：连接 Agent 后发送 auth JSON 消息
- 远程代理：仅通过 subprotocol 传递 token，不发送 auth JSON 消息
- Agent 端 `WebSocketConnectionManager.handle` 只从 headers 提取 auth，不处理 JSON auth 消息，因此差异不影响功能

**远程代理轮询机制**：

- `forward_client_to_remote`：浏览器消息 → `AGENT_WS_SEND_REQUEST` → Child → `agent_ws.send()`
- `forward_remote_to_client`：`AGENT_WS_RECV_REQUEST`(timeout=1.0s) → Child `agent_ws.recv()` → 浏览器
- 浏览器断开 → Master finally 块发 `AGENT_WS_CLOSE_REQUEST` → Child 关闭 agent_ws 并从 `_agent_ws_sessions` 移除

### WebSocket 连接管理

**WebSocketConnectionManager**（Agent 端，`app.py:487`）：

- `session_id = "default"` 固定，简化重连逻辑
- `_connection_lock_enabled = False`：允许新连接替换旧连接
- 新连接替换时：关闭旧 WebSocket → unregister 旧路由 → 清除旧 auth → 注册新连接
- `connection_id` 检查保护：finally 块中只有当前 connection_id 匹配才清理，避免新连接被旧连接的清理逻辑误删
- 断开时恢复：发送缓存输出（`_pending_outputs`）、恢复待处理输入/确认请求

### 节点间协议消息类型

| 类别           | 消息类型                                | 说明                          |
| -------------- | --------------------------------------- | ----------------------------- |
| 认证           | `NODE_AUTH` / `NODE_AUTH_RESULT`        | 子节点认证，Master 返回 token |
| 心跳           | `NODE_HEARTBEAT`                        | 子节点心跳保活                |
| Agent 管理     | `AGENT_CREATE_REQUEST/RESPONSE`         | 跨节点创建 Agent              |
|                | `AGENT_LIST_REQUEST/RESPONSE`           | 获取节点 Agent 列表           |
|                | `AGENT_STOP_REQUEST/RESPONSE`           | 跨节点停止 Agent              |
|                | `AGENT_DELETE_REQUEST/RESPONSE`         | 跨节点删除 Agent              |
| HTTP 代理      | `AGENT_HTTP_REQUEST/RESPONSE`           | 跨节点 HTTP 代理              |
|                | `NODE_HTTP_PROXY_REQUEST/RESPONSE`      | 节点级 HTTP 代理              |
| WebSocket 代理 | `AGENT_WS_OPEN_REQUEST/RESPONSE`        | 打开远程 WS 会话              |
|                | `AGENT_WS_SEND_REQUEST/RESPONSE`        | 发送 WS 消息                  |
|                | `AGENT_WS_RECV_REQUEST/RESPONSE`        | 接收 WS 消息                  |
|                | `AGENT_WS_CLOSE_REQUEST/RESPONSE`       | 关闭 WS 会话                  |
|                | `AGENT_WS_REQUEST/RESPONSE`             | 通用 WS 请求                  |
| 终端           | `NODE_TERMINAL_REQUEST/RESPONSE/OUTPUT` | 远程终端会话                  |
| 目录           | `DIRECTORY_LIST_REQUEST/RESPONSE`       | 跨节点目录列表                |
| 配置           | `CONFIG_SYNC/GET/SET_REQUEST/RESPONSE`  | 配置同步与管理                |
| 运维           | `SERVICE_RESTART_REQUEST/RESPONSE`      | 远程重启服务                  |
|                | `CODE_UPDATE_TO_MAIN_REQUEST/RESPONSE`  | 更新代码到 main 分支          |

### 认证机制

1. **Gateway Token**：服务启动时生成 `JARVIS_AUTH_TOKEN`，存入环境变量，子进程（Agent）共享
2. **HTTP 认证**：支持 `Authorization: Bearer <token>` 和 `X-Jarvis-Token: <token>` 两种方式
3. **WebSocket 认证**：通过 subprotocol `jarvis-token.{auth_token}` 传递，Agent 端从 `sec-websocket-protocol` header 提取
4. **节点认证**：Child 通过 `node_secret` 认证连接 Master，认证成功后 Master 下发 `JARVIS_AUTH_TOKEN`
5. **登录接口**：`POST /api/auth/login`，验证密码后返回 Token

## 构建与运行

### 安装

```bash
pip install -e .                    # 开发模式安装
pip install -e ".[browser]"        # 带浏览器支持
```

### 运行

```bash
# CLI模式
jarvis                              # 或 jvs
jarvis-code-agent                   # 或 jca

# Web服务模式
jarvis-service start

# Docker模式
docker-compose up -d

# 或使用启动脚本
./start.sh
```

### 环境要求

- Python: 3.12 (严格要求)
- 系统: Linux (主要), Windows (部分支持)
- 可选: Playwright浏览器、Clang编译器

## 测试

### 测试框架

- **pytest**: 主测试框架
- **pytest-xdist**: 并行测试
- **pytest-asyncio**: 异步测试支持

### 运行测试

```bash
pytest tests/                        # 运行所有测试
pytest tests/jarvis_agent/          # 运行特定模块测试
pytest -n auto                     # 并行运行
pytest --cov=src/jarvis            # 带覆盖率
```

### 测试目录结构

```text
tests/
├── jarvis_agent/                   # Agent测试
├── jarvis_code_agent/              # 代码Agent测试
├── jarvis_tools/                   # 工具测试
├── jarvis_c2rust/                  # C→Rust迁移测试
├── jarvis_memory_organizer/         # 记忆组织器测试
├── performance/                    # 性能测试
├── regression/                     # 回归测试
└── security/                      # 安全测试
```

## 关键配置

### 配置文件

- `pyproject.toml`: 项目元数据、依赖管理
- `.jarvis/build_validation_config.yaml`: 构建验证配置
- `.jarvis/rules/`: 项目规则目录
- `.jarvis/methodologies/`: 方法论目录

### 环境变量

- `OPENAI_API_KEY`: OpenAI API密钥
- `ANTHROPIC_API_KEY`: Anthropic API密钥
- `JARVIS_MODEL`: 使用的AI模型（默认gpt-4）
- `TERM`: 终端类型

### AI模型配置

支持多种模型:

- OpenAI: gpt-4, gpt-4-turbo, gpt-3.5-turbo
- Anthropic: claude-3-opus, claude-3-sonnet, claude-3-haiku

## 架构特点

### 模块化设计

- Agent、CodeAgent、Tools三层分离
- 支持工具热插拔
- 内置规则与自定义规则共存

### 可扩展性

- MCP (Model Context Protocol) 协议支持
- 自定义工具可通过 meta_agent 工具生成
- 支持新平台适配

### 本地优先

- 所有数据本地存储
- 支持离线工作
- 无vendor lock-in
