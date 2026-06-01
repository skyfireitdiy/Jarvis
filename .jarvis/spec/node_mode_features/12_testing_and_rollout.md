# 12 测试与发布验证详细设计

## 1. 功能目标

为 node 模式落地提供完整的测试分层、集成验证与灰度发布建议，确保实现完成后可按设计验证，而不是停留在“代码写完但不可证明正确”。

## 2. 验证范围

覆盖以下能力：

- CLI 参数与配置解析
- child 接入 master 的 node_auth
- token 同步
- 节点注册与心跳
- Agent 按节点创建
- 远端 Agent HTTP 转发
- 远端 Agent WS 转发
- master 单节点兼容性

## 3. 测试分层

### 3.1 单元测试

目标：验证纯逻辑组件。

建议覆盖：

- `NodeRuntimeConfig` 校验
- 节点消息协议解析与分发
- `node_registry` 状态切换
- `agent_route_registry` 增删查改
- token 同步状态机

### 3.2 组件测试

目标：验证单个 gateway 进程内多个组件协同。

建议覆盖：

- master `/ws/node` 接入与鉴权
- child 启动后连接与重连
- Agent 创建请求路由分流
- HTTP 请求 pending-response 关联
- WS tunnel 生命周期管理

### 3.3 集成测试

目标：验证双节点端到端行为。

建议环境：

- 1 个 master gateway
- 1 个 child gateway
- 可选 1 个真实或模拟 Agent 进程
- 1 个测试客户端

### 3.4 回归测试

目标：保证单节点能力未被破坏。

建议覆盖：

- 原有登录流程
- 原有本地 Agent 创建
- 原有 `/api/agent/{agent_id}/ws`
- 原有 `/api/agent/{agent_id}/{path}`

## 4. 核心测试场景

### 4.1 场景一：单节点兼容

步骤：

1. 以 `master` 默认模式启动 gateway
2. 客户端登录
3. 创建本地 Agent
4. 访问 Agent HTTP/WS

预期：

- 与当前版本行为一致

### 4.2 场景二：child 成功接入

步骤：

1. 启动 master
2. 启动 child，配置合法 `node_id/master_url/node_secret`
3. 等待 child 完成 auth + token sync

预期：

- master 注册 child online
- child ready
- token 对齐成功

### 4.3 场景三：在子节点创建 Agent

步骤：

1. 客户端向 master 发起 `POST /api/agents`，指定 `node_id=child-01`
2. master 转发创建请求
3. child 本地启动 Agent

预期：

- 返回的 `agent_info.node_id=child-01`
- master 路由表存在该 agent

### 4.4 场景四：远端 HTTP 代理

步骤：

1. 获取 child 上创建的 `agent_id`
2. 通过 master 访问 `/api/agent/{agent_id}/{path}`

预期：

- 返回 200 或符合 Agent 实际行为
- 客户端无感知 child 存在

### 4.5 场景五：远端 WS 代理

步骤：

1. 客户端连接 master 的 `/api/agent/{agent_id}/ws`
2. 通过 child 建立到目标 Agent 的 WS 隧道
3. 双向收发消息

预期：

- 消息收发正常
- 隧道关闭时资源正确回收

### 4.6 场景六：故障恢复

步骤：

1. child 已在线并存在远端 Agent
2. 人为断开 child 与 master 的长连接
3. 等待重连

预期：

- master 将节点标记 offline 再恢复 online
- 远端能力在断连期间失败可预期
- 重连后新请求恢复可用

## 5. 发布策略建议

### 5.1 实现顺序

建议按以下顺序落地：

1. CLI 与运行时模式
2. node_auth + token sync
3. node_registry + heartbeat
4. Agent 创建路由
5. HTTP 转发
6. WS 转发
7. 安全与观测补强

### 5.2 灰度策略

- 先在本地/测试环境验证 master-child 双节点
- 再验证真实客户端创建远端 Agent
- 最后再扩大到更多节点

### 5.3 回滚策略

- 因 `master` 是默认模式且兼容单节点，出现问题时可关闭 child 部署并继续使用主节点本地模式
- 必要时可回退到用户提供的初始安全提交点

## 6. 验证脚本建议

建议补充自动化脚本：

- 启动 master/child 的本地调试脚本
- 基于 curl/websocket client 的 smoke test
- Agent 创建与代理访问脚本

## 7. 交付定义

当以下条件同时满足时，node 模式实现可视为通过：

- 所有核心单元测试通过
- 至少 1 套 master-child 集成测试通过
- 单节点回归通过
- 文档、日志、错误码与实现一致

## 8. 验收标准

1. 开发者可直接据此制定实现后的测试计划
2. 开发者可直接据此设计集成验证与灰度发布步骤
3. 开发者可直接据此定义“什么时候算真正完成”
