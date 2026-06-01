# 02 运行模式与启动流程详细设计

## 1. 功能目标

明确 `master` 与 `child` 模式下 gateway 的启动装配方式，决定：

- 哪些组件总是初始化
- 哪些组件只在 `master` 初始化
- 哪些组件只在 `child` 初始化
- 如何保证 `master` 单节点行为与当前系统兼容

## 2. 影响模块

- `src/jarvis/jarvis_web_gateway/app.py`
- 建议新增：`src/jarvis/jarvis_web_gateway/node_runtime.py`

## 3. 输入/输出

### 3.1 输入

- `NodeRuntimeConfig`
- 当前环境配置
- `gateway_password`

### 3.2 输出

- 已初始化的运行时组件集合
- 模式相关的 app state 对象

## 4. 模块装配设计

### 4.1 所有模式共用组件

以下组件在 `master` / `child` 下都应初始化：

- token 初始化基础能力
- `AgentManager`
- `AgentProxyManager`
- `SessionOutputRouter`
- `InputSessionRegistry`
- `TerminalInputRegistry`
- `TerminalSessionManager`
- 基础 FastAPI app

### 4.2 仅 master 模式初始化组件

- 节点接入 WebSocket 路由
- 节点注册表
- 节点心跳管理器
- Agent 全局路由表
- 远端请求转发协调器

### 4.3 仅 child 模式初始化组件

- 主节点连接客户端
- token 同步器
- 节点请求处理器
- 本地 Agent 清单同步器

## 5. 详细流程

### 5.1 master 启动流程

```text
接收 NodeRuntimeConfig(master)
  ├── 初始化环境与 token
  ├── 初始化本地 Agent 相关组件
  ├── 初始化节点注册/心跳/路由管理组件
  ├── 注册客户端 HTTP/WS 路由
  ├── 注册节点接入 WS 路由
  └── 启动 FastAPI
```

### 5.2 child 启动流程

```text
接收 NodeRuntimeConfig(child)
  ├── 初始化环境与基础本地组件
  ├── 初始化主节点连接客户端
  ├── 注册节点请求处理器
  ├── 启动 FastAPI
  └── 在 startup 中异步连接主节点并执行 node_auth
```

## 6. app.state 设计建议

建议在 `app.state` 中统一挂载以下对象：

- `node_config`
- `node_runtime`
- `node_registry`（master）
- `agent_route_registry`（master）
- `node_client`（child）

## 7. 状态变化

### 7.1 gateway 运行时状态

- `bootstrapping`
- `ready`
- `degraded`

说明：

- `master` 在基础组件完成后可进入 `ready`
- `child` 必须在主节点连接与 token 同步成功后进入 `ready`
- 若 child 启动后主节点连接失败，可进入 `degraded`，但不得伪装成 fully ready

## 8. 异常处理

| 场景 | 处理方式 |
| --- | --- |
| child 模式启动后无法连接主节点 | 进入 `degraded`，记录错误并尝试重连 |
| child 模式连接成功但 token 同步失败 | 不进入 ready，记录 `TOKEN_SYNC_FAILED` |
| master 模式节点管理组件初始化失败 | 启动失败 |

## 9. 兼容性要求

- `master` 无子节点时，客户端行为必须与当前系统一致
- 现有 `/api/auth/login`、`/ws`、本地 Agent 代理逻辑必须仍然可用
- 引入 node 运行时后，不能破坏现有 startup/shutdown 生命周期处理

## 10. 代码落点建议

### 10.1 `app.py`

建议改动：

- 扩展 `create_app()` / `run()` 接收 `node_config`
- 在 `create_app()` 内根据模式装配组件
- 在 `startup` / `shutdown` 中增加节点相关生命周期管理

### 10.2 建议新增 `node_runtime.py`

建议职责：

- 定义运行时装配器
- 封装 master/child 模式初始化逻辑
- 统一 app.state 注入

## 11. 测试建议

- master 模式无子节点时启动成功
- child 模式下会注册主节点连接任务
- shutdown 时节点相关资源被释放

## 12. 验收标准

1. 开发者可据此明确 app 初始化中哪些对象在不同模式下存在
2. 开发者可据此把 startup/shutdown 生命周期改造为模式感知
3. 开发者可据此实现 child 启动后的主节点连接流程
