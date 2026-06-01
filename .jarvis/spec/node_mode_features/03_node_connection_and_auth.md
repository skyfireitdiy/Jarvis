# 03 子节点连接与鉴权详细设计

## 1. 功能目标

设计主节点与子节点之间的专用连接与鉴权流程，确保：

- 子节点通过长期 WebSocket 接入主节点
- 首帧必须完成 node_auth
- 主节点只接受合法子节点接入
- 节点冲突、超时与非法访问可被正确处理

## 2. 影响模块

- `src/jarvis/jarvis_web_gateway/app.py`
- 建议新增：
  - `src/jarvis/jarvis_web_gateway/node_connection_manager.py`
  - `src/jarvis/jarvis_web_gateway/node_client.py`

## 3. 输入/输出

### 3.1 输入

#### child -> master 首帧

```json
{
  "type": "node_auth",
  "payload": {
    "node_id": "child-01",
    "secret": "***",
    "capabilities": {
      "agent_creation": true,
      "agent_proxy": true
    }
  }
}
```

### 3.2 输出

#### master -> child 认证成功

```json
{
  "type": "node_auth_result",
  "payload": {
    "success": true,
    "node_id": "child-01",
    "token": "<masked>",
    "heartbeat_interval": 10
  }
}
```

#### master -> child 认证失败

```json
{
  "type": "error",
  "payload": {
    "code": "NODE_AUTH_FAILED",
    "message": "invalid node credentials"
  }
}
```

## 4. 接口定义

### 4.1 主节点接口

建议新增：

- `@app.websocket("/ws/node")`

用途：

- 仅接受子节点连接
- 不用于客户端普通会话

### 4.2 child 侧内部接口

建议新增内部方法：

- `connect_to_master()`
- `send_node_auth()`
- `handle_node_auth_result()`

## 5. 详细流程

### 5.1 主节点接入流程

```text
child 发起 /ws/node 连接
  ├── master accept
  ├── 等待首帧 node_auth
  ├── 校验消息类型
  ├── 校验 node_id / node_secret
  ├── 检查 node_id 冲突
  ├── 注册连接会话
  ├── 返回 node_auth_result(success)
  └── 进入心跳/请求处理阶段
```

### 5.2 child 连接流程

```text
child startup
  ├── 连接 master_url/ws/node
  ├── 建立 websocket
  ├── 发送 node_auth
  ├── 等待 node_auth_result
  ├── 若成功：进入 token 同步与 ready 阶段
  └── 若失败：进入 auth_failed/degraded
```

## 6. 状态变化

### 6.1 child 侧

- `init`
- `connecting`
- `authenticating`
- `authenticated`
- `auth_failed`

### 6.2 master 侧节点会话状态

- `accepted`
- `authenticated`
- `rejected`
- `closed`

## 7. 异常处理

| 场景 | 主节点处理 | 子节点处理 |
| --- | --- | --- |
| 首帧不是 `node_auth` | 返回错误并关闭连接 | 记录失败并重试 |
| `node_secret` 错误 | 返回 `NODE_AUTH_FAILED` | 进入 `auth_failed` |
| 相同 `node_id` 重复接入 | 返回 `NODE_CONFLICT` 或按策略替换 | 记录冲突错误 |
| 超时未发送认证消息 | 主节点关闭连接 | 子节点下次重试 |

## 8. 兼容性要求

- 新增 `/ws/node` 不得影响现有 `/ws`
- 客户端不得使用 `/ws/node`
- 节点接入鉴权不得复用客户端 Bearer token 作为唯一凭据

## 9. 代码落点建议

### 9.1 `app.py`

建议改动：

- 新增 `/ws/node` 路由
- 将节点连接逻辑从现有 `WebSocketConnectionManager` 分离，避免污染客户端 session 模型

### 9.2 `node_connection_manager.py`

建议职责：

- 管理 node websocket 会话
- 处理 node_auth 首帧
- 管理连接关闭和注册回调

### 9.3 `node_client.py`

建议职责：

- child 连接主节点
- 发送 node_auth
- 维护连接生命周期

## 10. 测试建议

- 有效 node_id/node_secret 时鉴权成功
- 非法 secret 被拒绝
- 未发送首帧认证时主节点关闭连接
- 相同 node_id 冲突接入时行为符合设计

## 11. 验收标准

1. 开发者可据此实现 `/ws/node` 路由与 node_auth 流程
2. 开发者可据此实现 child 主动连接主节点
3. 开发者可据此处理冲突、超时与非法首帧场景
