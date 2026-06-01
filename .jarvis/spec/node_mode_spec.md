# Node 模式功能规范

## 1. 功能概述

### 1.1 功能目标

为 Jarvis 增加 Node 模式，使 `jarvis-web-gateway` 与 `jarvis-service` 支持以下两类运行形态：

- `master`：主节点模式，也是默认模式；当未启用子节点接入能力时，其行为等价于当前单节点模式
- `child`：子节点模式，接入主节点并承载本地 Agent

说明：系统中不存在独立的 `standalone` 模式，也不存在 `standalone` 兼容输入。单节点部署直接使用 `master` 模式实现，因此单节点与主节点共用同一套主流程，只是在是否存在子节点接入这一点上表现不同。

该功能的目标是让客户端始终只连接主节点，但可以在指定节点创建 Agent，并无感知地通过主节点访问部署在子节点上的 Agent HTTP/WS 接口。

### 1.2 使用场景

1. 作为运维人员，我希望启动一个主节点 gateway，统一接入多个子节点。
2. 作为子节点部署者，我希望当前 gateway 以 child 模式接入主节点，并自动完成 token 对齐。
3. 作为客户端用户，我希望创建 Agent 时可以指定目标节点，而无需修改后续访问方式。
4. 作为客户端用户，我希望访问子节点上的 Agent 时仍然通过主节点地址完成 HTTP/WS 通信。
5. 作为兼容性要求，未启用 node 模式时，系统应保持当前单节点行为不变。

### 1.3 范围内功能

- 为 `jarvis-web-gateway` 增加 node 模式 CLI 参数
- 为 `jarvis-service` 增加 node 模式透传参数
- 定义主节点与子节点的接入、认证、心跳与断连行为
- 将单节点模式收敛到 `master` 实现语义，避免双套主流程
- 定义子节点从主节点获取 token 并同步本地 `JARVIS_AUTH_TOKEN` 的行为
- 扩展 Agent 创建接口以支持 `node_id`
- 扩展 Agent 元数据以记录所属节点
- 扩展主节点代理逻辑，使其能够对远端 Agent 执行 HTTP/WS 透明转发
- 扩展节点状态与 Agent 路由状态模型

### 1.4 范围外功能

- 不要求本阶段实现多主节点高可用
- 不要求本阶段实现跨主节点的负载均衡调度
- 不要求客户端直接连接子节点
- 不要求更换现有 Bearer token 认证模型
- 不要求引入数据库或外部注册中心

## 2. 接口定义

### 2.1 CLI 接口

#### 2.1.1 jarvis-web-gateway

命令：`jwg serve`

新增参数：

- `--node-mode <master|child>`
  - 默认值：`master`
  - 说明：指定当前 gateway 的运行模式
- `--node-id <string>`
  - child 模式必填
  - standalone/master 模式可选
  - 说明：节点唯一标识
- `--master-url <string>`
  - child 模式必填
  - 说明：主节点 gateway 地址
- `--node-secret <string>`
  - child 模式必填
  - 说明：子节点接入主节点时使用的共享凭据

约束：

- 当 `--node-mode=child` 时，必须同时提供 `--node-id`、`--master-url`、`--node-secret`
- 当 `--node-mode=master` 时，不应强制要求 `--master-url`
- `--node-mode` 只允许取值 `master` 或 `child`

#### 2.1.2 jarvis-service

命令：`jarvis-service`

新增能力：

- 支持通过环境变量或服务配置将 node 参数透传给 `jwg`
- 至少支持以下配置：
  - `JARVIS_NODE_MODE`
  - `JARVIS_NODE_ID`
  - `JARVIS_MASTER_URL`
  - `JARVIS_NODE_SECRET`

约束：

- service 不直接实现节点协议，只负责把 node 参数传递给 gateway
- 未配置 node 参数时，保持现有启动流程不变

### 2.2 HTTP API 接口

#### 2.2.1 POST /api/agents

功能：创建 Agent，并支持指定目标节点。

请求体新增字段：

- `node_id: string | null`
  - 可选
  - 为空时表示使用默认节点策略
  - 非空时表示在指定节点创建 Agent

请求示例：

```json
{
  "agent_type": "agent",
  "working_dir": "~/workspace",
  "name": "demo-agent",
  "llm_group": "default",
  "node_id": "child-01"
}
```

响应体新增字段：

- `data.node_id`
  - 表示 Agent 实际所属节点

响应示例：

```json
{
  "success": true,
  "data": {
    "agent_id": "agent-123",
    "agent_type": "agent",
    "status": "running",
    "node_id": "child-01"
  }
}
```

约束：

- 若 `node_id` 指向主节点本地，则沿用现有本地创建逻辑
- 若 `node_id` 指向在线子节点，则必须通过节点通道转发创建请求
- 若 `node_id` 不存在或目标节点离线，则返回明确错误

#### 2.2.2 GET /api/agents

功能：获取 Agent 列表。

返回数据要求：

- 每个 Agent 必须包含 `node_id`
- 对于远端 Agent，仍需返回统一结构，便于客户端展示

### 2.3 WebSocket 接口

#### 2.3.1 客户端主通道 `/ws`

要求：

- 保持现有客户端行为兼容
- 不要求客户端在 node 模式下改变 `/ws` 使用方式

#### 2.3.2 Agent 通道 `/api/agent/{agent_id}/ws`

要求：

- 对本地 Agent，保持现有代理行为
- 对远端 Agent，由主节点通过主子节点长连接中继该 WebSocket 流量
- 客户端不应感知目标 Agent 是否位于子节点

#### 2.3.3 节点通道（新增）

建议新增专用节点 WebSocket 通道，例如：`/ws/node`

子节点首条消息必须完成认证，消息格式：

```json
{
  "type": "node_auth",
  "payload": {
    "node_id": "child-01",
    "secret": "shared-secret",
    "capabilities": {
      "agent_creation": true,
      "agent_proxy": true
    }
  }
}
```

主节点成功响应示例：

```json
{
  "type": "node_auth_result",
  "payload": {
    "success": true,
    "node_id": "child-01",
    "token": "<master-token>",
    "heartbeat_interval": 10
  }
}
```

### 2.4 内部转发协议

主节点与子节点之间必须支持以下消息类型：

- `node_auth`
- `node_auth_result`
- `node_heartbeat`
- `create_agent_request`
- `create_agent_response`
- `http_proxy_request`
- `http_proxy_response`
- `ws_proxy_open`
- `ws_proxy_message`
- `ws_proxy_close`
- `agent_sync`
- `error`

约束：

- 每个转发请求必须包含唯一 `request_id` 或 `channel_id`
- 同一节点长连接上必须允许复用多个并发请求/通道

## 3. 输入输出说明

### 3.1 节点模式输入

| 输入项 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| node_mode | string | 否 | `master/child` |
| node_id | string | child 时是 | 当前节点 ID |
| master_url | string | child 时是 | 主节点地址 |
| node_secret | string | child 时是 | 子节点接入凭据 |

### 3.2 Agent 创建输入

| 输入项 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| agent_type | string | 是 | Agent 类型 |
| working_dir | string | 是 | 工作目录 |
| node_id | string | 否 | 目标节点 |

### 3.3 Agent 创建输出

| 输出项 | 类型 | 说明 |
| --- | --- | --- |
| agent_id | string | Agent 唯一标识 |
| node_id | string | Agent 所属节点 |
| status | string | Agent 当前状态 |

### 3.4 节点状态输出

| 输出项 | 类型 | 说明 |
| --- | --- | --- |
| node_id | string | 节点标识 |
| status | string | `online/offline/degraded` |
| last_heartbeat_at | string | 最近心跳时间 |

## 4. 数据结构要求

### 4.1 NodeInfo

必须至少包含：

- `node_id`
- `mode`
- `status`
- `connected_at`
- `last_heartbeat_at`
- `capabilities`

### 4.2 AgentInfo 扩展

现有 AgentInfo 必须新增：

- `node_id`

要求：

- 对本地 Agent，`node_id` 为当前节点 ID 或主节点默认 ID
- 对远端 Agent，`node_id` 为实际子节点 ID

### 4.3 转发请求模型

必须至少包含：

- `request_id`
- `protocol`
- `agent_id`
- `path`
- `headers`
- `body`
- `query`

### 4.4 转发响应模型

必须至少包含：

- `request_id`
- `status_code`
- `headers`
- `body`
- `error`

## 5. 功能行为

### 5.1 master 模式行为

- `master` 是默认模式，也是单节点模式的统一实现
- 当没有任何子节点接入时，其行为必须与当前单节点系统一致
- 接受客户端登录与 API/WS 请求
- 接受子节点通过节点通道接入
- 维护节点注册表与 Agent 路由表
- 对本地 Agent 执行本地代理
- 对远端 Agent 执行节点中继代理
- 不要求必须存在子节点才能启动

### 5.2 child 模式行为

- 启动后主动连接主节点的节点通道
- 首帧发送节点认证消息
- 认证成功后，使用主节点返回的 token 更新本地 `JARVIS_AUTH_TOKEN`
- 仅通过主节点接收远端创建和代理请求
- 保留本地 AgentManager 与本地 AgentProxyManager 能力

### 5.4 token 同步行为

- 主节点仍为 token 唯一来源
- 子节点认证成功后必须使用主节点返回 token 覆盖本地 token
- 子节点后续创建的 Agent 必须继承该同步后的 token
- 如果子节点 token 同步失败，节点不得进入 ready/online 状态

### 5.5 Agent 创建行为

- 当请求未提供 `node_id` 时：
  - 默认使用当前主节点本地
- 当请求提供 `node_id` 且指向本地节点时：直接本地创建
- 当请求提供 `node_id` 且指向在线子节点时：通过节点通道创建
- 当请求提供 `node_id` 但节点不存在或离线时：返回错误，不得静默降级到其他节点

### 5.6 HTTP 代理行为

- 当目标 Agent 属于本地节点时：保持现有 `AgentProxyManager.proxy_http_request()` 行为
- 当目标 Agent 属于子节点时：
  1. 主节点封装 HTTP 请求
  2. 通过节点通道发送到目标子节点
  3. 子节点对本地 Agent 执行 HTTP 代理
  4. 子节点将响应回传主节点
  5. 主节点将结果返回客户端

### 5.7 WebSocket 代理行为

- 当目标 Agent 属于本地节点时：保持现有 `proxy_websocket()` 行为
- 当目标 Agent 属于子节点时：
  1. 主节点为该客户端连接创建 `channel_id`
  2. 子节点建立到本地 Agent 的 WS 连接
  3. 主子节点之间通过节点通道转发 WS 数据帧
  4. 客户端关闭时，主节点和子节点都必须完成通道清理

### 5.8 节点重连行为

- 子节点断连后可重连主节点
- 子节点重连成功后必须重新注册节点状态
- 子节点重连后应重新同步本地 Agent 清单或重建 Agent 路由

## 6. 边界条件

### 6.1 参数边界

- child 模式缺少 `node_id/master_url/node_secret` 时，启动必须失败
- `node_mode` 非法取值时，启动必须失败
- `node_id` 为空字符串时，视为非法输入

### 6.2 节点状态边界

- 若两个子节点使用相同 `node_id` 接入主节点，主节点必须返回冲突错误或按明确策略拒绝其一
- 若子节点连接建立但未在超时时间内完成 `node_auth`，主节点必须关闭连接
- 若子节点超过约定心跳周期未上报，主节点必须将其标记为离线

### 6.3 Agent 路由边界

- 若 `agent_id` 未找到路由，必须返回 `AGENT_NOT_FOUND`
- 若路由指向离线节点，必须返回节点不可用错误
- 不得因为远端节点不可用而自动改为访问本地同名 Agent

### 6.4 兼容性边界

- 现有客户端在不传 `node_id` 时必须仍可使用
- 现有 `/api/auth/login`、`/ws`、`/api/agent/{agent_id}/ws`、`/api/agent/{agent_id}/{path}` 路径必须继续可用
- 单节点模式下不得引入额外强制配置
- 单节点模式必须通过 `master` 的同一实现支撑，而不是单独分叉实现
- 客户端与部署文档中不得再暴露 `standalone` 取值

## 7. 异常处理

### 7.1 错误码要求

必须覆盖至少以下错误：

- `INVALID_NODE_MODE`
- `MISSING_NODE_CONFIG`
- `NODE_AUTH_FAILED`
- `NODE_CONFLICT`
- `NODE_OFFLINE`
- `TOKEN_SYNC_FAILED`
- `AGENT_NOT_FOUND`
- `FORWARD_TIMEOUT`
- `FORWARD_FAILED`
- `UNSUPPORTED_NODE_OPERATION`

### 7.2 异常场景处理

- 子节点鉴权失败：拒绝接入并记录日志
- token 同步失败：子节点不进入可用状态
- 远端 Agent 创建失败：主节点必须将错误透传给客户端
- HTTP 转发超时：主节点返回超时错误
- WS 转发异常断开：主节点与子节点都要清理通道状态

## 8. 安全要求

- 子节点接入必须依赖独立 node 凭据，不得仅依赖客户端 Bearer token
- 不得在普通日志中输出明文 token
- 主节点必须是 Agent 路由的唯一决策者
- 子节点不得伪造属于其他节点的 Agent 路由

## 9. 验收标准

### 9.1 Spec 完整性验收

1. Spec 文件存在于 `.jarvis/spec/node_mode_spec.md`
2. Spec 包含功能概述、接口定义、输入输出、功能行为、边界条件、异常处理、验收标准
3. Spec 明确区分范围内与范围外功能

### 9.2 功能验收标准

1. 当 `jwg` 以 `--node-mode=child` 启动且缺少必要参数时，启动失败并提示缺失项
2. 当用户未配置 `node_mode` 时，系统按 `master` 模式运行，且单节点功能保持兼容
3. 当用户传入非法的 `node_mode` 取值时，启动必须失败
4. 当子节点使用有效 `node_id + node_secret + master_url` 接入主节点时，主节点接受连接并返回 token
5. 当子节点接入成功后，其本地 token 与主节点 token 一致
6. 当客户端通过主节点创建 `node_id=child-01` 的 Agent 时，该 Agent 在子节点创建成功，且返回结果包含 `node_id=child-01`
7. 当客户端访问位于子节点的 Agent HTTP 接口时，响应通过主节点成功返回
8. 当客户端连接位于子节点的 Agent WebSocket 时，可以正常收发消息，且客户端无需修改连接方式
9. 当目标子节点离线时，创建 Agent 或访问远端 Agent 必须返回明确错误

### 9.3 验证方法

- 通过单元测试验证节点状态机、路由决策和错误分支
- 通过集成测试验证主子节点接入、token 同步、远端 Agent 创建与 HTTP/WS 转发
- 通过静态检查确认接口字段、错误码和兼容路径未破坏

## 10. 实现约束

- 必须优先复用现有 `AgentManager`、`AgentProxyManager`、HTTP 鉴权和 Bearer token 模型
- 不得破坏当前单节点默认行为
- `master` 与单节点模式必须共用同一套实现主流程
- 不得要求客户端直接连接子节点
- 不得引入 Spec 未定义的新外部接口语义

## 11. 参考代码位置

- `src/jarvis/jarvis_web_gateway/cli.py`
- `src/jarvis/jarvis_web_gateway/app.py`
- `src/jarvis/jarvis_web_gateway/token_manager.py`
- `src/jarvis/jarvis_web_gateway/agent_manager.py`
- `src/jarvis/jarvis_web_gateway/agent_proxy_manager.py`
- `src/jarvis/jarvis_service/cli.py`
- `src/jarvis/jarvis_vscode_extension/src/extension.ts`
