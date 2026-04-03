# 06 Agent 元数据与路由详细设计

## 1. 功能目标

扩展现有 Agent 元数据，使主节点可以统一描述本地与远端 Agent，并建立 `agent_id -> node_id` 路由关系，支撑：

- 创建 Agent 结果统一返回
- `/api/agents` 统一展示
- HTTP/WS 代理的路由决策

## 2. 影响模块

- `src/jarvis/jarvis_web_gateway/agent_manager.py`
- `src/jarvis/jarvis_web_gateway/app.py`
- 建议新增：`src/jarvis/jarvis_web_gateway/agent_route_registry.py`

## 3. 输入/输出

### 3.1 输入

- 本地 Agent 创建成功事件
- 子节点返回的远端 Agent 创建成功事件
- Agent 删除/停止事件
- 子节点重连后的 Agent 同步事件

### 3.2 输出

- 扩展后的 AgentInfo / AgentRouteInfo
- 主节点统一 Agent 列表
- 供代理层查询的路由决策结果

## 4. 数据结构

### 4.1 AgentInfo 扩展

现有 `AgentInfo` 建议新增：

- `node_id: str`

### 4.2 AgentRouteInfo

```python
class AgentRouteInfo:
    agent_id: str
    node_id: str
    status: str
    working_dir: str | None
    port: int | None
    updated_at: str | None
```

### 4.3 注册表结构

```python
agent_route_registry: dict[str, AgentRouteInfo]
```

## 5. 详细流程

### 5.1 本地 Agent 注册流程

```text
master 本地 create_agent success
  ├── 从 AgentInfo 读取 agent_id/port/status
  ├── 构造 AgentRouteInfo(node_id=local master)
  ├── 写入 agent_route_registry
  └── 返回带 node_id 的统一响应
```

### 5.2 远端 Agent 注册流程

```text
master 转发 create_agent 到 child
  ├── child 本地创建 Agent
  ├── child 返回 Agent 元数据
  ├── master 构造 AgentRouteInfo(node_id=child)
  ├── 写入 agent_route_registry
  └── 返回统一响应给客户端
```

### 5.3 列表查询流程

```text
GET /api/agents
  ├── 读取本地 Agent 列表
  ├── 读取远端 Agent 路由记录
  ├── 统一格式化
  └── 返回包含 node_id 的列表
```

### 5.4 删除与停止流程

- 当 Agent 停止或删除时，必须同步更新 `agent_route_registry`
- 若 child 节点离线，远端 Agent 可保留记录但状态必须标记为不可用或未知

## 6. 状态变化

Agent 路由状态建议：

- `running`
- `stopped`
- `error`
- `unknown`

说明：

- `unknown` 用于节点离线后暂时无法确认远端 Agent 真实状态的情况

## 7. 异常处理

| 场景 | 处理方式 |
| --- | --- |
| `agent_id` 未注册到路由表 | 返回 `AGENT_NOT_FOUND` |
| child 创建成功但 master 注册路由失败 | 返回错误并记录严重日志 |
| 节点离线后路由仍指向该节点 | 查询时返回 `NODE_OFFLINE` 或 `unknown` |

## 8. 兼容性要求

- 现有本地 Agent 模型字段必须尽量保持不变，仅增加 `node_id`
- 客户端若不消费 `node_id` 字段，现有主流程仍应可用
- 本地模式下所有 Agent 的 `node_id` 必须稳定可预测

## 9. 代码落点建议

### 9.1 `agent_manager.py`

建议改动：

- `AgentInfo` 增加 `node_id`
- `to_dict()` 输出 `node_id`
- 本地创建 Agent 时填充本地 node_id

### 9.2 `agent_route_registry.py`

建议职责：

- 维护 agent_id 到 node_id 的映射
- 提供路由查询、注册、删除、批量同步接口

### 9.3 `app.py`

建议改动：

- `/api/agents` 改为读取统一路由视图
- 远端创建成功后注册路由

## 10. 测试建议

- 本地创建 Agent 后返回 `node_id=master`
- 远端创建 Agent 后主节点路由表写入 child node_id
- `/api/agents` 返回结果中统一包含 `node_id`
- 节点离线后远端 Agent 状态合理变化

## 11. 验收标准

1. 开发者可直接据此扩展 `AgentInfo` 和新增路由表
2. 开发者可直接据此实现本地/远端 Agent 的统一表示
3. 开发者可直接据此支持后续 HTTP/WS 路由决策
