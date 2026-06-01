# 10 节点消息协议详细设计

## 1. 功能目标

统一定义 master 与 child 之间通过长连接传输的内部消息协议，约束消息结构、分类、关联 ID、错误语义与版本演进方式，避免各功能点各自发明协议导致实现分裂。

## 2. 影响模块

- `src/jarvis/jarvis_web_gateway/app.py`
- 建议新增：
  - `src/jarvis/jarvis_web_gateway/node_protocol.py`
  - `src/jarvis/jarvis_web_gateway/node_message_dispatcher.py`

## 3. 总体协议结构

所有节点消息统一采用如下基础格式：

```json
{
  "type": "message_type",
  "request_id": "optional-request-id",
  "payload": {},
  "meta": {
    "protocol_version": 1,
    "timestamp": "2026-04-02T00:00:00Z"
  }
}
```

## 4. 字段定义

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `type` | 是 | 消息类型 |
| `request_id` | 否 | 请求-响应型消息的关联 ID |
| `payload` | 是 | 业务载荷 |
| `meta.protocol_version` | 是 | 协议版本，初版固定为 `1` |
| `meta.timestamp` | 否 | 发送时间，便于排障 |

## 5. 消息分类

### 5.1 连接与认证类

- `node_auth`
- `node_auth_result`
- `node_heartbeat`
- `node_heartbeat_ack`（可选）

### 5.2 Agent 生命周期类

- `agent_create_request`
- `agent_create_response`
- `agent_sync`
- `agent_remove`

### 5.3 HTTP 转发类

- `agent_http_request`
- `agent_http_response`

### 5.4 WebSocket 转发类

- `agent_ws_open`
- `agent_ws_open_result`
- `agent_ws_data`
- `agent_ws_close`

### 5.5 通用错误类

- `error`

## 6. request_id 规则

- 只有请求-响应型消息必须带 `request_id`
- fire-and-forget 类型消息可不带 `request_id`
- 同一连接内 `request_id` 必须唯一
- 响应消息必须原样回传请求中的 `request_id`

适用示例：

| 请求类型 | 是否需要 `request_id` |
| --- | --- |
| `node_auth` | 建议需要 |
| `agent_create_request` | 必须 |
| `agent_http_request` | 必须 |
| `agent_ws_data` | 不需要 |

## 7. 错误语义

### 7.1 通用错误消息格式

```json
{
  "type": "error",
  "request_id": "req-123",
  "payload": {
    "code": "NODE_OFFLINE",
    "message": "target node is offline",
    "details": {}
  },
  "meta": {
    "protocol_version": 1
  }
}
```

### 7.2 规范化错误码建议

- `NODE_AUTH_FAILED`
- `NODE_CONFLICT`
- `NODE_NOT_FOUND`
- `NODE_OFFLINE`
- `AGENT_NOT_FOUND`
- `AGENT_CREATE_FAILED`
- `HTTP_PROXY_TIMEOUT`
- `WS_TUNNEL_OPEN_FAILED`
- `INVALID_NODE_MESSAGE`

## 8. 分发机制设计

建议按 `type` 建立消息处理器映射：

```python
handlers = {
    "node_auth": handle_node_auth,
    "node_heartbeat": handle_node_heartbeat,
    "agent_create_request": handle_agent_create_request,
    ...
}
```

处理要求：

- 未知 `type` 返回 `INVALID_NODE_MESSAGE`
- 缺失必要字段返回 `INVALID_NODE_MESSAGE`
- 处理器应尽量无副作用地做参数校验后再执行业务逻辑

## 9. 版本演进策略

- 初版 `protocol_version=1`
- master/child 初期必须要求版本一致
- 后续若需升级版本，优先向后兼容新增字段，不破坏已有字段语义

## 10. 兼容性要求

- 节点内部协议不得暴露给普通客户端
- 各功能点文档中的消息样例必须遵循本协议基类
- 单节点模式下即使不使用该协议，实现中也应保留统一消息定义

## 11. 代码落点建议

### 11.1 `node_protocol.py`

建议职责：

- 定义消息类型常量
- 定义消息构造器/解析器
- 做基础字段校验

### 11.2 `node_message_dispatcher.py`

建议职责：

- 分发收到的节点消息
- 管理 request-response pending 表
- 统一异常转 `error` 消息

## 12. 测试建议

- 合法消息可正确解析
- 缺字段消息被拒绝
- 未知消息类型返回规范错误
- request_id 能正确关联请求与响应

## 13. 验收标准

1. 开发者可直接据此定义统一节点协议模型
2. 开发者可直接据此实现消息分发器与 pending request 管理
3. 开发者可直接据此为后续 HTTP/WS/Agent 创建功能共用协议层
