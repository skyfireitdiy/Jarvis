# 09 WebSocket 代理转发详细设计

## 1. 功能目标

支持主节点将客户端对远端 Agent 的 WebSocket 会话透明转发到子节点，使客户端像连接本地 Agent 一样连接远端 Agent。

该功能点覆盖：

- Agent 专属 WS 连接建立
- 双向消息转发
- 会话关闭与异常回收

## 2. 影响模块

- `src/jarvis/jarvis_web_gateway/app.py`
- `src/jarvis/jarvis_web_gateway/agent_proxy_manager.py`
- 建议新增：`src/jarvis/jarvis_web_gateway/node_ws_proxy.py`

## 3. 输入/输出

### 3.1 输入

客户端访问现有 WS 代理接口：

- `/api/agent/{agent_id}/ws`

输入包括：

- WS connect
- text/binary/frame close

### 3.2 输出

- 与本地 Agent 一致的 WebSocket 行为
- 双向消息流转

## 4. 协议设计

### 4.1 会话控制消息

#### master -> child

```json
{
  "type": "agent_ws_open",
  "payload": {
    "tunnel_id": "ws-uuid",
    "agent_id": "agent-123",
    "path": "/ws",
    "headers": {
      "origin": "..."
    }
  }
}
```

#### child -> master

```json
{
  "type": "agent_ws_open_result",
  "payload": {
    "tunnel_id": "ws-uuid",
    "success": true,
    "error_code": null,
    "error_message": null
  }
}
```

### 4.2 数据消息

```json
{
  "type": "agent_ws_data",
  "payload": {
    "tunnel_id": "ws-uuid",
    "direction": "client_to_agent",
    "data_type": "text",
    "data": "..."
  }
}
```

### 4.3 关闭消息

```json
{
  "type": "agent_ws_close",
  "payload": {
    "tunnel_id": "ws-uuid",
    "code": 1000,
    "reason": "normal closure"
  }
}
```

## 5. 详细流程

### 5.1 本地 WS 流程

```text
客户端连接 /api/agent/{agent_id}/ws
  ├── 查询 agent_route_registry
  ├── 若 node_id=local
  ├── 调用现有本地 WS 代理
  └── 建立本地 Agent WS 会话
```

### 5.2 远端 WS 建立流程

```text
客户端连接 /api/agent/{agent_id}/ws
  ├── 主节点查询 agent_route_registry
  ├── 确认目标 child online
  ├── 为会话分配 tunnel_id
  ├── 向 child 发送 agent_ws_open
  ├── 等待 agent_ws_open_result
  ├── 若成功，accept 客户端 websocket
  └── 启动双向转发协程
```

### 5.3 双向转发流程

```text
客户端 -> 主节点 -> child -> 远端 Agent
远端 Agent -> child -> 主节点 -> 客户端
```

要求：

- 主节点维护 `tunnel_id -> client websocket` 映射
- child 维护 `tunnel_id -> local agent websocket` 映射
- 任一侧关闭都应通知另一侧释放资源

## 6. 状态管理

### 6.1 隧道状态

- `opening`
- `open`
- `closing`
- `closed`
- `error`

### 6.2 状态切换

- `agent_ws_open` 已发出 -> `opening`
- 收到成功结果 -> `open`
- 任意一侧发起关闭 -> `closing`
- 清理完成 -> `closed`

## 7. 异常处理

| 场景 | 处理方式 |
| --- | --- |
| agent 不存在 | 关闭客户端连接并返回错误 |
| 节点离线 | 建连失败 |
| child 无法连接本地 Agent WS | 返回 `agent_ws_open_result(success=false)` |
| 转发过程中任一侧断开 | 发送 `agent_ws_close` 并清理隧道 |

## 8. 性能与资源要求

- 每个远端 WS 会话都必须有独立 `tunnel_id`
- 隧道映射在关闭后必须清理，避免内存泄漏
- 单节点模式下不得引入明显额外开销

## 9. 兼容性要求

- 本地 Agent WS 路径保持不变
- 客户端无需理解 `tunnel_id`
- 本地模式下仍走现有逻辑

## 10. 代码落点建议

### 10.1 `app.py`

建议改动：

- 在 Agent WS 接入时先查询路由
- 本地继续沿用现有逻辑，远端走 node ws 隧道

### 10.2 `node_ws_proxy.py`

建议职责：

- 管理 WS 隧道生命周期
- 处理 open/data/close 协议消息
- 维护 tunnel 映射

## 11. 测试建议

- 本地 Agent WS 行为保持不变
- 远端 Agent WS 可建立连接并双向传输消息
- 断线后 tunnel 映射被清理
- child 无法连接远端 Agent 时客户端收到合理失败结果

## 12. 验收标准

1. 开发者可直接据此实现远端 Agent WS 隧道协议
2. 开发者可直接据此实现 open/data/close 生命周期管理
3. 开发者可直接据此完成双向转发与资源清理
