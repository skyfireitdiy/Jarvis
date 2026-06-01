# Node 模式功能点级详细设计总览

## 1. 文档目标

本文档基于以下输入形成：

- `node_mode_spec.md`
- `node_mode_design_plan.md`
- 已完成的反向工程分析与 node 模式总体设计

目标是将 node 模式设计细化到可直接指导编码的程度，明确：

1. 总体模块关系
2. 公共数据结构
3. 公共状态模型
4. 统一错误码与日志要求
5. 各功能点子文档的职责与边界
6. 推荐的实现顺序

本文档不直接替代各功能点设计文档，而是为各子文档提供统一约束。

## 2. 适用范围

本设计适用于以下模块：

- `src/jarvis/jarvis_web_gateway/cli.py`
- `src/jarvis/jarvis_web_gateway/app.py`
- `src/jarvis/jarvis_web_gateway/token_manager.py`
- `src/jarvis/jarvis_web_gateway/agent_manager.py`
- `src/jarvis/jarvis_web_gateway/agent_proxy_manager.py`
- `src/jarvis/jarvis_service/cli.py`
- `src/jarvis/jarvis_vscode_extension/src/extension.ts`

同时允许在 `src/jarvis/jarvis_web_gateway/` 下新增 node 模式相关管理模块，但必须优先复用现有组件能力。

## 3. 总体设计目标

### 3.1 模式定义

系统只允许两种 `node_mode`：

- `master`
- `child`

其中：

- `master` 是默认模式
- 单节点部署直接使用 `master` 模式，不再存在 `standalone` 模式
- `child` 模式必须依赖主节点接入

### 3.2 高层行为目标

- 客户端始终连接主节点
- 子节点通过长期 WebSocket 接入主节点
- 子节点从主节点获取统一 token，并更新本地 `JARVIS_AUTH_TOKEN`
- Agent 创建支持目标节点选择
- 主节点根据 Agent 路由决定执行本地代理还是远端转发
- 对客户端保持现有主路径兼容：
  - `/api/auth/login`
  - `/ws`
  - `/api/agent/{agent_id}/ws`
  - `/api/agent/{agent_id}/{path:path}`

## 4. 总体模块关系

```text
客户端
  │
  ▼
主节点 gateway (master)
  ├── CLI 参数与启动模式解析
  ├── 客户端登录与 token 校验
  ├── 节点接入与鉴权
  ├── 节点注册表 / 心跳管理
  ├── Agent 路由表
  ├── Agent 创建分流
  ├── 本地 Agent 代理
  └── 远端 HTTP/WS 转发
         │
         ▼
子节点 gateway (child)
  ├── 主节点连接客户端
  ├── token 同步器
  ├── 本地 AgentManager
  ├── 本地 AgentProxyManager
  └── 节点请求处理器
```

## 5. 公共数据结构

### 5.1 NodeRuntimeConfig

建议新增运行时配置对象，用于统一承载 CLI/环境变量解析结果。

字段建议：

- `node_mode: str`
- `node_id: str | None`
- `master_url: str | None`
- `node_secret: str | None`
- `is_master: bool`
- `is_child: bool`

使用位置：

- `jarvis_web_gateway/cli.py`
- `jarvis_web_gateway/app.py`
- `jarvis_service/cli.py`

### 5.2 NodeInfo

字段建议：

- `node_id`
- `status`
- `connected_at`
- `last_heartbeat_at`
- `capabilities`
- `connection_id`
- `version`
- `metadata`

状态说明：

- `online`
- `offline`
- `degraded`
- `auth_failed`

### 5.3 AgentRouteInfo

字段建议：

- `agent_id`
- `node_id`
- `status`
- `working_dir`
- `port`
- `updated_at`

说明：

- 本地 Agent 也必须注册到统一路由表
- 主节点只根据路由表决定代理方式，不直接假设 Agent 本地存在

### 5.4 ForwardRequest / ForwardResponse

#### ForwardRequest

字段建议：

- `request_id`
- `protocol` (`http` / `ws` / `control`)
- `agent_id`
- `path`
- `method`
- `headers`
- `query`
- `body`
- `channel_id`

#### ForwardResponse

字段建议：

- `request_id`
- `status_code`
- `headers`
- `body`
- `error`

## 6. 公共状态模型

### 6.1 节点状态机

```text
init
 └──> connecting
       ├──> online
       ├──> auth_failed
       ├──> offline
       └──> degraded
```

#### 状态说明

- `init`：刚启动，尚未建立连接
- `connecting`：正在连接主节点或正在等待鉴权
- `online`：连接已建立且已通过鉴权，心跳正常
- `auth_failed`：鉴权失败，不能进入业务可用状态
- `offline`：连接断开或心跳超时
- `degraded`：连接存在但部分能力异常，如 token 同步失败或转发异常率过高

### 6.2 WS 转发通道状态机

```text
created
 └──> opened
       ├──> streaming
       ├──> closing
       └──> closed
```

说明：

- `created`：主节点刚为远端 Agent WS 分配 `channel_id`
- `opened`：子节点已建立到本地 Agent 的 WS 连接
- `streaming`：正在双向转发
- `closing`：任一侧请求关闭，正在清理
- `closed`：通道已结束，资源已释放

## 7. 公共错误码与处理约定

### 7.1 错误码表

| 错误码 | 使用场景 | 责任侧 |
| --- | --- | --- |
| `INVALID_NODE_MODE` | 启动参数非法 | CLI / 启动层 |
| `MISSING_NODE_CONFIG` | child 缺少必需参数 | CLI / 启动层 |
| `NODE_AUTH_FAILED` | 子节点鉴权失败 | 主节点 |
| `NODE_CONFLICT` | 相同 node_id 冲突接入 | 主节点 |
| `NODE_OFFLINE` | 目标节点不可用 | 主节点 |
| `TOKEN_SYNC_FAILED` | 子节点 token 更新失败 | 子节点 |
| `AGENT_NOT_FOUND` | 路由未找到 Agent | 主节点 |
| `FORWARD_TIMEOUT` | 节点转发超时 | 主节点 |
| `FORWARD_FAILED` | 子节点执行代理失败 | 主/子节点 |
| `UNSUPPORTED_NODE_OPERATION` | 当前模式不支持某操作 | 主/子节点 |

### 7.2 错误处理约定

- 主节点应优先把节点内部错误转换为统一错误码，再返回客户端
- 子节点不得将未分类异常原样暴露给客户端
- 转发错误必须带上 `request_id` 或 `channel_id` 以便追踪

## 8. 日志与审计要求

### 8.1 必记日志

- 子节点连接开始/成功/失败
- 节点鉴权失败
- token 同步成功/失败
- Agent 创建分流决策
- 远端 HTTP 转发请求与响应摘要
- 远端 WS 通道建立与关闭
- 节点离线、心跳超时、重连

### 8.2 日志限制

- 不得打印明文 token
- 请求体仅在调试级别下允许输出摘要，默认避免敏感内容泄露

## 9. 子文档清单与职责

### 9.1 子文档列表

- `node_mode_features/01_cli_and_config.md`
- `node_mode_features/02_runtime_mode_and_bootstrap.md`
- `node_mode_features/03_node_connection_and_auth.md`
- `node_mode_features/04_token_sync.md`
- `node_mode_features/05_node_registry_and_heartbeat.md`
- `node_mode_features/06_agent_metadata_and_routing.md`
- `node_mode_features/07_agent_creation_routing.md`
- `node_mode_features/08_remote_http_proxy.md`
- `node_mode_features/09_remote_ws_proxy.md`
- `node_mode_features/10_client_compatibility.md`
- `node_mode_features/11_error_codes_and_state_machine.md`
- `node_mode_features/12_test_and_validation.md`

### 9.2 子文档编写统一模板

每个功能点文档必须包含：

1. 功能目标
2. 影响模块
3. 输入/输出
4. 数据结构
5. 详细流程
6. 状态变化
7. 异常处理
8. 兼容性要求
9. 代码落点建议
10. 测试建议

## 10. 推荐实现顺序

建议实现顺序如下：

1. `01_cli_and_config.md`
2. `02_runtime_mode_and_bootstrap.md`
3. `03_node_connection_and_auth.md`
4. `04_token_sync.md`
5. `05_node_registry_and_heartbeat.md`
6. `06_agent_metadata_and_routing.md`
7. `07_agent_creation_routing.md`
8. `08_remote_http_proxy.md`
9. `09_remote_ws_proxy.md`
10. `10_client_compatibility.md`
11. `11_error_codes_and_state_machine.md`
12. `12_test_and_validation.md`

原因：

- 先打通模式与连接基础
- 再建立节点状态与 Agent 路由
- 最后实现流量代理与客户端适配

## 11. 编码约束映射

### 11.1 可以新增的内容

- `jarvis_web_gateway` 下的 node 管理辅助模块
- 节点注册、连接、转发管理类
- Agent 路由表管理结构
- 节点协议消息模型

### 11.2 必须复用的内容

- `AgentManager`
- `AgentProxyManager`
- `verify_token()` 现有 Bearer token 模型
- 现有客户端 `/api/agent/{agent_id}/...` 访问路径

### 11.3 不允许破坏的内容

- 默认登录流程
- `/ws` 主通道现有使用方式
- 当前不传 `node_id` 时的客户端行为

## 12. 验证要求

### 12.1 设计完成的判断标准

满足以下条件可认为功能点级详细设计完成：

1. 每个功能点都有单独文档
2. 每个文档都包含代码落点建议
3. 每个文档都给出明确输入输出与异常处理
4. 每个文档都包含至少一种可执行验证方法
5. 开发者可据此直接开始编码

### 12.2 后续实现前检查项

- `node_mode_spec.md` 是否与详细设计一致
- 是否不存在 `standalone` 模式残留设计
- 是否每个功能点都明确影响文件
- 是否给出了测试入口与验收标准

## 13. 结论

Node 模式的详细设计应采用“总览 + 功能点子文档”的分层组织方式推进。总览文档负责统一约束和跨模块关系，功能点子文档负责把每个编码任务拆到可直接执行的粒度。后续应继续补齐 12 个子文档，再进入实现阶段。
