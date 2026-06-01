# 08 HTTP 代理转发详细设计

## 1. 功能目标

当客户端访问某个 Agent 的 HTTP 接口时，主节点根据 `agent_id -> node_id` 路由关系，将请求：

- 直接转发到本地 Agent，或
- 通过主子节点长连接转发给子节点，再由子节点访问本地 Agent

实现客户端无感访问远端 Agent。

## 2. 影响模块

- `src/jarvis/jarvis_web_gateway/app.py`
- `src/jarvis/jarvis_web_gateway/agent_proxy_manager.py`
- 建议新增：`src/jarvis/jarvis_web_gateway/node_http_proxy.py`

## 3. 输入/输出

### 3.1 输入

客户端访问现有 Agent HTTP 代理接口：

- `/api/agent/{agent_id}/{path}`

输入内容包括：

- HTTP method
- path
- query string
- headers
- body

### 3.2 输出

返回统一 HTTP 响应：

- status code
- headers（过滤 hop-by-hop 后）
- body

## 4. 协议设计

### 4.1 主子节点内部消息建议

#### master -> child

```json
{
  "type": "agent_http_request",
  "payload": {
    "request_id": "req-uuid",
    "agent_id": "agent-123",
    "method": "POST",
    "path": "/v1/chat/completions",
    "query": "stream=true",
    "headers": {"content-type": "application/json"},
    "body_base64": "..."
  }
}
```

#### child -> master

```json
{
  "type": "agent_http_response",
  "payload": {
    "request_id": "req-uuid",
    "status_code": 200,
    "headers": {"content-type": "application/json"},
    "body_base64": "..."
  }
}
```

## 5. 详细流程

### 5.1 本地 Agent HTTP 代理

```text
客户端请求 /api/agent/{agent_id}/{path}
  ├── 查询 agent_route_registry
  ├── 若 node_id=local
  ├── 调用现有 AgentProxyManager 本地转发
  └── 返回结果
```

### 5.2 远端 Agent HTTP 代理

```text
客户端请求 /api/agent/{agent_id}/{path}
  ├── 查询 agent_route_registry
  ├── 若 node_id=child-01
  ├── 查询 child-01 状态是否 online
  ├── 构造 agent_http_request(request_id)
  ├── 通过主子 ws 发送请求
  ├── 等待 child 返回 agent_http_response
  ├── 转换为 FastAPI Response
  └── 返回给客户端
```

### 5.3 child 本地执行流程

```text
child 收到 agent_http_request
  ├── 解析 agent_id/path/method/body
  ├── 校验 agent_id 属于本节点
  ├── 调用本地 AgentProxyManager 访问 Agent HTTP 端口
  ├── 收集响应
  └── 返回 agent_http_response
```

## 6. 请求关联与超时

- 每个远端 HTTP 请求必须分配唯一 `request_id`
- 主节点维护待响应请求表 `pending_http_requests`
- 若在超时窗口内未收到响应，返回 `504` 或网关级超时错误

## 7. 异常处理

| 场景 | 处理方式 |
| --- | --- |
| `agent_id` 不存在 | 返回 `404 AGENT_NOT_FOUND` |
| 路由到离线节点 | 返回 `503 NODE_OFFLINE` |
| child 未返回响应超时 | 返回 `504 GATEWAY_TIMEOUT` |
| child 返回本地访问失败 | 透传规范化错误 |

## 8. 安全与过滤

- 仅转发必要 headers，过滤 hop-by-hop headers
- 不允许 child 自由伪造目标地址，child 只能访问本机 Agent 代理目标
- `agent_id` 必须由主节点侧路由决定，不接受 child 重写

## 9. 兼容性要求

- 本地 Agent HTTP 访问路径与现有完全一致
- 现有客户端无需感知远端转发协议
- 若全部 Agent 都在本地，HTTP 路径行为必须不变

## 10. 代码落点建议

### 10.1 `app.py`

建议改动：

- 在现有 Agent HTTP 代理入口前增加路由查询
- 分支到本地或远端代理实现

### 10.2 `node_http_proxy.py`

建议职责：

- 构造/发送远端 HTTP 请求消息
- 维护 pending request 表
- 等待并解析响应

### 10.3 child 请求处理器

建议职责：

- 接收 `agent_http_request`
- 调用本地代理
- 回包 `agent_http_response`

## 11. 测试建议

- 本地 Agent HTTP 请求行为保持不变
- 远端 Agent HTTP 请求可成功返回 200
- 远端节点离线时返回 503
- 超时与异常响应可正确映射

## 12. 验收标准

1. 开发者可直接据此实现主节点 HTTP 路由分流
2. 开发者可直接据此定义主子节点内部 HTTP 转发消息协议
3. 开发者可直接据此实现 request_id 关联、超时与异常映射
