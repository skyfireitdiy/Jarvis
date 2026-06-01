# 04 token 同步详细设计

## 1. 功能目标

在 child 节点通过主节点鉴权成功后，将主节点返回的 token 同步到子节点本地运行环境，确保：

- 子节点本地 `JARVIS_AUTH_TOKEN` 与主节点一致
- 子节点后续创建的 Agent 继承统一 token
- 主节点代理到子节点上的 Agent 时不产生 token 不一致问题

本功能点只负责 token 对齐，不负责 child 与 master 的连接建立。

## 2. 影响模块

- `src/jarvis/jarvis_web_gateway/app.py`
- `src/jarvis/jarvis_web_gateway/token_manager.py`
- `src/jarvis/jarvis_web_gateway/agent_manager.py`
- 建议新增：`src/jarvis/jarvis_web_gateway/node_token_sync.py`

## 3. 输入/输出

### 3.1 输入

来自主节点的认证成功响应：

```json
{
  "type": "node_auth_result",
  "payload": {
    "success": true,
    "token": "<master-token>",
    "node_id": "child-01",
    "heartbeat_interval": 10
  }
}
```

### 3.2 输出

- 子节点环境变量中的 `JARVIS_AUTH_TOKEN` 被更新
- 子节点运行时状态标记为 `token_synced`
- 后续本地 Agent 创建请求使用同步后的 token

## 4. 数据结构

建议新增 token 同步状态对象：

```python
class NodeTokenSyncState:
    last_synced_at: str | None
    sync_status: str
    source_node_id: str | None
    error_message: str | None
```

状态建议：

- `pending`
- `success`
- `failed`

## 5. 详细流程

### 5.1 child token 同步流程

```text
child 收到 node_auth_result(success=true)
  ├── 读取 payload.token
  ├── 校验 token 非空
  ├── 更新 os.environ['JARVIS_AUTH_TOKEN']
  ├── 更新 token_sync_state = success
  ├── 标记 child 可进入 ready 候选状态
  └── 后续 AgentManager 创建 Agent 时读取新 token
```

### 5.2 启动期与运行期行为区分

#### 启动期

- child 第一次连上主节点后必须先完成 token 同步
- token 同步成功前，不允许把 child 视作 fully ready

#### 运行期

- 初版不要求支持主节点动态轮换 token 并热更新所有已运行 Agent
- 若后续主节点 token 改变，可作为后续增强能力设计

## 6. 状态变化

```text
pending
 ├──> success
 └──> failed
```

附加运行时门槛：

- 只有 `token_sync_state=success` 且 `node_auth=success` 时，child 才能进入 `ready`

## 7. 异常处理

| 场景 | 处理方式 |
| --- | --- |
| `payload.token` 缺失 | 标记 `TOKEN_SYNC_FAILED`，不进入 ready |
| 环境变量写入失败 | 标记 `TOKEN_SYNC_FAILED`，记录错误 |
| token 同步成功但后续 Agent 仍使用旧 token | 视为严重实现错误，需通过测试发现 |

## 8. 兼容性要求

- master 模式保持现有 token 生成逻辑不变
- child 模式只能接受主节点下发的 token，不自行生成独立 token
- 不得修改当前客户端 Bearer token 使用方式

## 9. 代码落点建议

### 9.1 `app.py`

建议改动：

- child 节点收到 `node_auth_result` 后调用统一 token 同步函数
- 在 child ready 判定中纳入 token 同步结果

### 9.2 `agent_manager.py`

建议改动：

- 保持 `create_agent()` 从环境变量或调用参数读取 token
- 确保 token 同步完成后，新的 Agent 一定继承新 token

### 9.3 `node_token_sync.py`

建议职责：

- 执行 token 更新
- 维护同步状态
- 提供同步结果查询

## 10. 测试建议

### 10.1 单元测试

- 成功接收主节点 token 后更新环境变量
- token 缺失时报错
- token 同步失败时 child 不进入 ready

### 10.2 集成测试

- child 连接 master 成功后，本地 `JARVIS_AUTH_TOKEN` 与 master 一致
- child 上新建 Agent 时，该 Agent 能通过主节点 token 完成后续鉴权通信

## 11. 验收标准

1. 开发者可直接知道 token 同步发生在 child 的哪个时序点
2. 开发者可直接知道 token 同步成功/失败如何影响 child ready 状态
3. 开发者可据此实现 token 同步逻辑与测试
