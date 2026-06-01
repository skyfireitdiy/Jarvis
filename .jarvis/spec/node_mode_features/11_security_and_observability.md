# 11 安全与可观测性详细设计

## 1. 功能目标

为 node 模式补充必要的安全边界、日志、指标与排障信息，确保该能力在多节点环境下可运维、可审计、可定位问题。

## 2. 影响模块

- `src/jarvis/jarvis_web_gateway/app.py`
- `src/jarvis/jarvis_web_gateway/token_manager.py`
- 建议新增：
  - `src/jarvis/jarvis_web_gateway/node_security.py`
  - `src/jarvis/jarvis_web_gateway/node_observability.py`

## 3. 安全设计

### 3.1 节点鉴权边界

- child 接入 master 必须使用独立的 `node_secret`
- 不允许仅凭客户端 Bearer token 建立节点级信任
- `node_secret` 不得出现在明文日志中

### 3.2 权限边界

- child 仅能执行主节点下发的受控操作：
  - 创建本地 Agent
  - 代理本地指定 Agent 的 HTTP 请求
  - 代理本地指定 Agent 的 WS 会话
- child 不得依据任意外部输入访问非 Agent 目标地址

### 3.3 输入校验

- 所有节点消息按协议做字段校验
- `agent_id`、`node_id`、`request_id` 必须校验非空与格式合法性
- 转发 headers 时过滤敏感或不需要的 hop-by-hop 头

### 3.4 数据最小暴露

- 日志中 token 只允许输出掩码形式
- node_auth 日志不可打印完整 secret
- 错误响应给客户端时避免泄漏子节点内部路径与栈信息

## 4. 可观测性设计

### 4.1 日志事件建议

| 事件 | 日志级别 | 关键字段 |
| --- | --- | --- |
| 子节点连接建立 | INFO | `node_id`, `connection_id` |
| node_auth 成功/失败 | INFO/WARN | `node_id`, `error_code` |
| token 同步成功/失败 | INFO/ERROR | `node_id` |
| Agent 远端创建 | INFO | `agent_id`, `node_id`, `request_id` |
| HTTP 转发超时 | WARN | `agent_id`, `node_id`, `request_id` |
| WS 隧道建立/关闭 | INFO | `agent_id`, `node_id`, `tunnel_id` |

### 4.2 指标建议

- 当前在线节点数
- 节点鉴权失败次数
- 远端 Agent 创建成功/失败次数
- HTTP 转发请求数、超时数、平均耗时
- WS 隧道建立数、当前活跃隧道数

### 4.3 Trace/关联字段

建议统一透传：

- `request_id`
- `tunnel_id`
- `node_id`
- `agent_id`

这些字段应贯穿主节点、子节点与日志上下文。

## 5. 详细流程要求

### 5.1 鉴权审计流程

```text
child 连接 master
  ├── 记录连接来源
  ├── 记录 node_id
  ├── 若鉴权成功：记录成功事件
  └── 若鉴权失败：记录失败原因（不打印 secret）
```

### 5.2 转发审计流程

```text
远端 Agent HTTP/WS 请求
  ├── 记录 request_id/tunnel_id
  ├── 记录目标 node_id/agent_id
  ├── 记录开始时间
  ├── 结束时记录耗时与结果
  └── 异常时记录错误码
```

## 6. 异常处理与告警

| 场景 | 告警建议 |
| --- | --- |
| 短时间内连续 node_auth 失败 | 安全告警 |
| 节点频繁上下线 | 可用性告警 |
| HTTP 代理超时率升高 | 性能告警 |
| WS 隧道泄漏/活跃数异常 | 资源告警 |

## 7. 兼容性要求

- 日志增强不得破坏现有接口返回结构
- 如项目暂未接入指标系统，至少保证结构化日志信息完整
- 单节点模式下仍可复用统一日志字段体系

## 8. 代码落点建议

### 8.1 `node_security.py`

建议职责：

- 敏感信息掩码处理
- 节点消息输入校验工具
- 安全相关公共函数

### 8.2 `node_observability.py`

建议职责：

- 结构化日志工具
- 简单指标计数封装
- request_id/tunnel_id 上下文辅助

## 9. 测试建议

- 日志中不泄漏完整 token/secret
- 非法节点消息被记录并拒绝
- 关键操作日志包含 `node_id` / `agent_id` / `request_id`
- 超时、失败、断连场景存在可定位日志

## 10. 验收标准

1. 开发者可直接据此为 node 模式增加安全校验与日志规范
2. 开发者可直接据此补充必要监控指标或占位实现
3. 开发者可直接据此保证排障链路可追踪
