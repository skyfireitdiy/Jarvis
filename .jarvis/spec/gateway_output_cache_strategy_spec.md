# 网关输出缓存策略规范

## 功能概述

调整 Jarvis Web Gateway 与 Agent WebSocket 代理的输出缓存职责，避免主 `/ws` 通道在前端离线时继续缓存普通输出消息，同时保留 Agent 代理链路在客户端断连后的消息补发能力。

本规范对应方案 A：

1. Web Gateway 主 `/ws` 通道不再缓存普通输出消息。
2. `input_request` 与 `confirm` 的重连恢复机制保持不变。
3. Agent WebSocket 代理 `/api/agent/{agent_id}/ws` 负责缓存 agent->client 转发失败的消息，并在后续重连成功后按顺序补发。

## 使用场景

- 前端连接主 `/ws` 通道查看全局执行输出时，如果连接未建立或已断开，普通输出消息不需要补发。
- 前端通过 `/api/agent/{agent_id}/ws` 连接具体 Agent 时，如果客户端短暂断开，应尽量补发断线期间已从 Agent 收到、但未成功送达客户端的消息。
- 等待用户输入或确认的交互场景，仍需在主 `/ws` 重连后恢复待处理请求。

## 范围说明

### 范围内

- `SessionOutputRouter` 的普通输出缓存行为
- `WebSocketConnectionManager` 对主 `/ws` 的恢复语义
- `AgentProxyManager` 的 agent 消息缓存与补发逻辑

### 范围外

- 不引入 Redis、数据库或文件持久化缓存
- 不修改认证协议
- 不改变前端消息格式
- 不改变 input/confirm 的保存与恢复机制

## 接口定义

### 1. SessionOutputRouter.publish

文件：`src/jarvis/jarvis_gateway/output_bridge.py`

现有接口：

```python
def publish(self, message: Dict[str, Any], session_id: Optional[str] = None) -> None
```

规范要求：

- 保持函数签名不变。
- 当没有订阅者时，不再把消息写入 `_message_cache`。
- 当存在订阅者时，继续向现有订阅者发送消息。
- 允许保留无订阅者日志输出，但不得缓存普通消息。

### 2. WebSocketConnectionManager.handle

文件：`src/jarvis/jarvis_web_gateway/app.py`

现有接口：

```python
async def handle(self, websocket: WebSocket) -> None
```

规范要求：

- 保持现有连接替换、认证、注册 sender、ready 响应逻辑不变。
- 保持 `pending_request` 与 `pending_confirm` 的恢复逻辑不变。
- 不新增主 `/ws` 普通输出缓存补发逻辑。

### 3. AgentProxyManager.proxy_websocket

文件：`src/jarvis/jarvis_web_gateway/agent_proxy_manager.py`

现有接口：

```python
async def proxy_websocket(self, client_ws: WebSocket, agent_id: str) -> None
```

规范要求：

- 保持客户端连接、连接 Agent、转发双向消息、关闭资源的总体流程不变。
- 在新代理连接建立成功、且 Agent 认证完成后，必须尝试将该 `agent_id` 的缓存消息补发给客户端。
- 仅补发此前“已从 Agent 收到但未成功发送给客户端”的消息。

### 4. AgentProxyManager._cache_agent_message

文件：`src/jarvis/jarvis_web_gateway/agent_proxy_manager.py`

现有接口：

```python
async def _cache_agent_message(self, agent_id: str, message: str) -> None
```

规范要求：

- 继续使用内存缓存，按 `agent_id` 分桶。
- 继续使用 FIFO 策略。
- 默认上限保持 200 条。
- 超过上限时移除最旧消息。

### 5. AgentProxyManager._flush_cached_messages

文件：`src/jarvis/jarvis_web_gateway/agent_proxy_manager.py`

现有接口：

```python
async def _flush_cached_messages(self, client_ws: WebSocket, agent_id: str) -> None
```

规范要求：

- 必须按缓存顺序补发。
- 补发前先读取当前 `agent_id` 的缓存快照。
- 仅在成功发送后才视为该条消息已完成补发。
- 若补发中途失败，失败消息及尚未发送的后续消息不得丢失。
- 补发后缓存中不应保留已成功发送的消息。

## 输入输出说明

### SessionOutputRouter.publish

输入：

- `message`: 已结构化的 WebSocket 输出消息，可能是 `output`、`execution`、`input_request`、`confirm` 等
- `session_id`: 可选的会话 ID

输出：

- 无返回值

错误处理：

- 若 sender 抛异常，保持当前逐个 sender 容错行为
- 不因无订阅者而抛异常

### AgentProxyManager._cache_agent_message

输入：

- `agent_id`: Agent 标识符，非空字符串
- `message`: 需要缓存的原始 WebSocket 文本消息

输出：

- 无返回值

错误处理：

- 使用异步锁保护并发访问
- 若单条消息加入缓存后超过上限，移除最旧消息

### AgentProxyManager._flush_cached_messages

输入：

- `client_ws`: 当前前端客户端 WebSocket 连接
- `agent_id`: Agent 标识符

输出：

- 无返回值

错误处理：

- 若没有缓存消息，直接返回
- 若发送某条缓存消息失败：
  - 当前失败消息必须重新进入缓存
  - 当前失败消息之后尚未发送的消息也必须重新进入缓存
  - 重新抛出异常，让上层关闭本次代理连接

## 功能行为

### 正常情况

1. 主 `/ws` 连接在线时，`SessionOutputRouter.publish` 将消息直接发给订阅者。
2. 主 `/ws` 无订阅者时，普通输出消息直接丢弃，不做缓存。
3. Agent 代理链路中，`agent->client` 消息发送成功时，不写入缓存。
4. Agent 代理链路中，`agent->client` 消息发送失败时，该消息写入 `agent_id` 对应缓存。
5. 后续新的 `/api/agent/{agent_id}/ws` 连接建立后，在开始双向转发前补发缓存消息。

### 边界情况

1. 主 `/ws` 在断连后重连：
   - 仍恢复 `input_request`
   - 仍恢复 `confirm`
   - 不恢复普通 `output` / `execution`
2. Agent 缓存为空时，补发函数直接返回。
3. Agent 缓存达到 200 条后继续写入：
   - 删除最旧消息
   - 保留最新 200 条
4. Agent 补发过程中若第 N 条发送失败：
   - 第 1 到 N-1 条视为已成功补发
   - 第 N 条及后续未发送消息继续保留

### 异常情况

1. 主 `/ws` sender 抛异常时：
   - 不引入新的缓存回退逻辑
   - 保持现有容错打印行为
2. Agent 与客户端间发送失败时：
   - 在 `agent->client` 方向缓存失败消息
3. Agent 补发失败时：
   - 不丢失尚未成功补发的消息
   - 允许本次连接失败退出，等待下次重连继续补发

## 验收标准

1. `SessionOutputRouter.publish` 在无订阅者时不再调用任何缓存写入逻辑。
2. 主 `/ws` 重连后，`pending_request` 与 `pending_confirm` 仍能恢复。
3. 主 `/ws` 重连后，普通 `output` / `execution` 不会因为 router 缓存被补发。
4. `AgentProxyManager` 仍会在 `agent->client` 发送失败时缓存消息。
5. `AgentProxyManager` 在新连接建立后会尝试按 FIFO 顺序补发缓存消息。
6. Agent 缓存补发失败时，失败消息及其后续未发送消息不会丢失。
7. 缓存上限仍为每个 `agent_id` 200 条，超限时淘汰最旧消息。
8. 代码实现不修改前端消息结构，不引入新的外部依赖。

## 验证方法

### 代码级验证

1. 检查 `src/jarvis/jarvis_gateway/output_bridge.py`，确认 `publish()` 在 `not callbacks` 分支不再调用 `_cache_message()`。
2. 检查 `src/jarvis/jarvis_web_gateway/app.py`，确认主 `/ws` 的 `pending_request` / `pending_confirm` 恢复逻辑保持存在。
3. 检查 `src/jarvis/jarvis_web_gateway/agent_proxy_manager.py`：
   - `_cache_agent_message()` 仍按 FIFO 和 200 条上限缓存
   - `proxy_websocket()` 仍在建立连接后调用 `_flush_cached_messages()`
   - `_flush_cached_messages()` 能在中途失败时重新保留未成功补发消息

### 行为级验证

1. 在无主 `/ws` 订阅者时发布普通消息，不应出现 router 缓存累积。
2. 断开再重连主 `/ws`，仍可收到待输入/待确认请求恢复。
3. 模拟 Agent 代理向客户端发送失败后，重新连接同一 `agent_id`，应能收到缓存补发。
4. 模拟补发过程中再次失败，失败消息和剩余消息在下一次重连后仍可继续补发。
