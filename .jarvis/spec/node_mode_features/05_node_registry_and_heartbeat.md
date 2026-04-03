# 05 节点注册表与心跳详细设计

## 1. 功能目标

在主节点维护在线子节点注册表，并通过心跳机制跟踪节点可用性，支撑：

- Agent 路由决策
- 创建 Agent 时的节点可用性校验
- HTTP/WS 远端转发前的节点状态判断
- 节点断连与重连恢复

## 2. 影响模块

- `src/jarvis/jarvis_web_gateway/app.py`
- 建议新增：
  - `src/jarvis/jarvis_web_gateway/node_registry.py`
  - `src/jarvis/jarvis_web_gateway/node_heartbeat.py`

## 3. 输入/输出

### 3.1 输入

- `node_auth` 成功后的节点注册事件
- 周期性 `node_heartbeat` 消息
- WebSocket 断开事件
- child 重连事件

### 3.2 输出

- `node_registry` 中的节点记录
- 节点状态变化事件
- 对路由层可查询的节点状态结果

## 4. 数据结构

```python
class NodeInfo:
    node_id: str
    status: str
    connected_at: str | None
    last_heartbeat_at: str | None
    capabilities: dict
    connection_id: str | None
    metadata: dict
```

### 4.1 注册表结构建议

```python
node_registry: dict[str, NodeInfo]
```

## 5. 详细流程

### 5.1 注册流程

```text
node_auth success
  ├── 生成/确认 connection_id
  ├── 写入 node_registry[node_id]
  ├── 设置 status=online
  ├── 设置 connected_at/last_heartbeat_at
  └── 可供 Agent 路由和创建流程查询
```

### 5.2 心跳流程

```text
child 定时发送 node_heartbeat
  ├── master 收到心跳
  ├── 更新 node_registry[node_id].last_heartbeat_at
  ├── 若原状态不是 online，则恢复为 online
  └── 若 connection_id 不匹配，则忽略或告警
```

### 5.3 超时与离线流程

```text
master 定时扫描 node_registry
  ├── 若 now - last_heartbeat_at > timeout
  ├── 标记 status=offline
  ├── 触发相关 Agent 路由降级/不可用
  └── 记录日志
```

### 5.4 重连流程

```text
同一 node_id 重新连接
  ├── 重新鉴权
  ├── 替换旧 connection_id
  ├── 更新 connected_at
  ├── 设置 status=online
  └── 触发 Agent 路由恢复逻辑
```

## 6. 状态变化

- `online`
- `offline`
- `degraded`
- `auth_failed`

状态切换规则：

- 注册成功 -> `online`
- 心跳超时 -> `offline`
- 局部错误但连接未断 -> `degraded`
- 鉴权失败 -> `auth_failed`

## 7. 异常处理

| 场景 | 处理方式 |
| --- | --- |
| 未注册节点发送心跳 | 忽略并记录告警 |
| 已离线节点心跳恢复 | 若连接有效则恢复 `online` |
| 相同 node_id 新旧连接并存 | 采用最新认证成功的连接，旧连接作废 |

## 8. 兼容性要求

- 无子节点时，master 的 `node_registry` 为空，但系统仍能工作
- 节点状态管理不得影响本地 Agent 使用
- 节点离线时，只应影响远端能力，不应影响主节点本地能力

## 9. 代码落点建议

### 9.1 `node_registry.py`

建议职责：

- 注册/更新/删除节点
- 查询节点状态
- 提供路由查询接口

### 9.2 `node_heartbeat.py`

建议职责：

- 心跳消息处理
- 超时扫描
- 节点状态切换

### 9.3 `app.py`

建议改动：

- 在 `/ws/node` 生命周期中注册/移除节点
- 在 startup 中启动心跳扫描任务
- 在 shutdown 中清理节点状态

## 10. 测试建议

- 节点注册成功后状态为 online
- 心跳超时后状态变为 offline
- 重连后状态恢复为 online
- 无效心跳不会污染注册表

## 11. 验收标准

1. 开发者可直接实现 `node_registry` 数据结构与状态切换逻辑
2. 开发者可直接实现心跳扫描与节点状态更新
3. 开发者可据此为路由层提供节点可用性查询能力
