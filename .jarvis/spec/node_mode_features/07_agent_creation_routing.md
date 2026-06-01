# 07 Agent 创建路由详细设计

## 1. 功能目标

在客户端创建 Agent 时支持显式指定目标节点，由主节点决定是在本地创建还是转发到子节点创建，并向客户端返回统一结果。

本功能点解决“创建入口的节点选择与请求分发”问题，不负责后续 HTTP/WS 会话代理细节。

## 2. 影响模块

- `src/jarvis/jarvis_web_gateway/app.py`
- `src/jarvis/jarvis_web_gateway/agent_manager.py`
- 建议新增：`src/jarvis/jarvis_web_gateway/node_agent_creation_service.py`

## 3. 输入/输出

### 3.1 输入

客户端创建 Agent 请求建议扩展字段：

```json
{
  "agent_name": "demo-agent",
  "workspace": "/path/to/workspace",
  "node_id": "child-01"
}
```

说明：

- `node_id` 可选
- 未提供时默认在主节点本地创建
- 若提供 `node_id=master` 或本地节点标识，则在本地创建
- 若提供子节点 `node_id`，则转发到对应 child 创建

### 3.2 输出

统一创建响应，至少包含：

- `agent_id`
- `status`
- `node_id`
- 其他现有 Agent 元数据字段

## 4. 接口设计

### 4.1 外部接口

复用现有创建 Agent 接口：

- `POST /api/agents`

扩展请求体支持 `node_id`。

### 4.2 内部接口建议

- `create_local_agent(...)`
- `create_remote_agent(node_id, request)`
- `resolve_target_node(node_id)`

## 5. 详细流程

### 5.1 本地创建流程

```text
客户端 POST /api/agents(node_id 未传或为 master)
  ├── 主节点解析请求
  ├── resolve_target_node => local
  ├── 调用 AgentManager.create_agent()
  ├── 注册 agent_route_registry
  └── 返回统一结果
```

### 5.2 远端创建流程

```text
客户端 POST /api/agents(node_id=child-01)
  ├── 主节点解析请求
  ├── 查询 node_registry 确认 child-01 online
  ├── 通过主子 ws 发送 create_agent 请求
  ├── child 本地调用 AgentManager.create_agent()
  ├── child 返回 agent 元数据
  ├── 主节点注册 agent_route_registry
  └── 返回统一结果给客户端
```

## 6. 路由决策规则

| 条件 | 路由结果 |
| --- | --- |
| `node_id` 为空 | 本地 master |
| `node_id` 为 master 标识 | 本地 master |
| `node_id` 为在线子节点 | 转发到该 child |
| `node_id` 为离线/不存在节点 | 返回错误 |

## 7. 数据结构建议

建议增加内部请求模型：

```python
class AgentCreateTarget:
    node_id: str
    is_local: bool
```

建议增加远端创建响应模型：

```python
class RemoteAgentCreateResult:
    success: bool
    agent_info: dict | None
    error_code: str | None
    error_message: str | None
```

## 8. 异常处理

| 场景 | 处理方式 |
| --- | --- |
| 指定的 `node_id` 不存在 | 返回 `NODE_NOT_FOUND` |
| 指定节点离线 | 返回 `NODE_OFFLINE` |
| child 创建 Agent 失败 | 返回 child 侧错误并透传规范化错误码 |
| 主节点在 child 成功后注册路由失败 | 返回错误并记录严重日志 |

## 9. 兼容性要求

- 不传 `node_id` 时行为必须与当前系统一致
- 当前客户端若不升级，仍可按单节点方式创建 Agent
- 新字段 `node_id` 必须为向后兼容的可选字段

## 10. 代码落点建议

### 10.1 `app.py`

建议改动：

- 扩展 `POST /api/agents` 请求体解析
- 增加目标节点解析逻辑
- 根据结果调用本地创建或远端创建服务

### 10.2 `node_agent_creation_service.py`

建议职责：

- 统一封装创建路由决策
- 调用 child 远端创建协议
- 返回统一响应对象

## 11. 测试建议

- 未传 `node_id` 时本地创建成功
- 指定在线子节点时远端创建成功
- 指定离线节点时返回错误
- 远端创建成功后 `agent_route_registry` 正确写入

## 12. 验收标准

1. 开发者可直接据此改造 `/api/agents` 支持按节点创建
2. 开发者可直接据此实现主节点本地/远端创建分流
3. 开发者可直接据此定义错误码与测试场景
