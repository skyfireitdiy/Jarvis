# Jarvis 集成终端会话持久化方案（方案 A）

## 一、概述

### 1.1 背景与目标

Administrator 提出需求：**集成终端在前端页面断开后会话丢失，希望保持会话，下次相同账号登录还能继续**，同时要求**支持同用户多设备登录**。

目标：

- 前端页面断开（刷新 / 断网 / 关闭标签页）后，终端进程不被杀掉，会话保留。
- 相同账号重新登录（含换设备）后，能恢复之前的终端会话并继续交互。
- 同一用户多台设备同时在线时，都能实时看到同一终端，且互不干扰。

### 1.2 设计原则

- **最小改动**：只改与目标相关的代码，不重构无关部分。
- **进程与连接解耦**：终端进程生命周期与前端 WebSocket 连接解耦——断开不杀进程。
- **按账号隔离**：会话归属以用户（`session_id`）为准，只能由同账号恢复。
- **多设备广播**：同账号多设备并存时输出广播给所有在线设备；重连设备只回放缓冲，不重复。
- **向后兼容**：现有终端创建 / 关闭 / 输入 / 调整尺寸逻辑保持不变。

---

## 二、现状分析

### 2.1 核心文件

- 后端：`src/jarvis/jarvis_web_gateway/terminal_session_manager.py`（601 行）
- 后端：`src/jarvis/jarvis_web_gateway/app.py`（终端相关：WS 消息处理、HTTP 端点）
- 后端：`src/jarvis/jarvis_gateway/output_bridge.py`（`SessionOutputRouter` 发布/订阅）
- 前端：`src/jarvis/jarvis_service/frontend/src/App.vue`、`components/TerminalPanel.vue`

### 2.2 关键事实

1. **会话仅存内存**：`TerminalSessionManager._sessions` 是内存字典，无持久化。`cleanup()` 在 app 关闭（lifespan shutdown）时调用，杀掉所有会话。

2. **前端断开不杀进程**：`WebSocketConnectionManager.handle` 的 `finally` 块只做 `router.unregister`、`input_registry.unregister_provider`、聊天客户端清理，**不关闭终端会话**。终端进程在 WS 断开后继续运行。

3. **断开期间输出被丢弃**：终端输出经 `router.publish(message, session_id=...)` 发布。WS 断开后该 session 无订阅者，`output_bridge.py` 的 `publish` 因 `if not callbacks: return` 直接丢弃输出。

4. **会话与用户已绑定**：`session_id = f"session_{user_id}"`（app.py:967），创建终端时传入（app.py:1389），存于 `TerminalSession.session_id`。

5. **多设备并存天然支持**：`router._subscribers[session_id]` 是 `{connection_id: sender}` 字典，可挂多个连接；`publish(session_id=...)` 广播给该 session 下所有连接；WS 断开只移除该 `connection_id`，不影响其他设备。

6. **前端会话是纯内存**：`terminalSessions`（App.vue:7731）刷新即清空，不会去重新发现后端仍存活的会话。

### 2.3 问题根因

不是"断开即杀进程"（进程还活着），而是三个缺口：

- **输出无缓冲**：断开期间输出被丢弃，重连后无法回放。
- **无接管/重连机制**：前端无法把已存在的会话重新关联到新连接。
- **会话归属不透明**：`list_terminals()` 返回所有会话且不含 `session_id`，无法按账号过滤/隔离。

---

## 三、方案 A 设计

### 3.1 后端改动

#### 3.1.1 输出环形缓冲（`terminal_session_manager.py`）

- 给 `TerminalSession` 增加输出环形缓冲（`collections.deque(maxlen=N)`），默认保留约 1MB 输出（可配置）。
- `_publish_output` 时既通过 `stream_publisher` 发布，也写入缓冲。
- 提供 `get_output_buffer()` 方法返回缓冲内容（供接管时回放）。

#### 3.1.2 接管 / attach 能力（`terminal_session_manager.py`）

- 新增 `list_sessions_for_user(session_id)`：返回指定用户（`session_id` 匹配）的存活会话元数据（含 `terminal_id`、`interpreter`、`working_dir`、`node_id`、`created_at`、`is_closed`）。
- 新增 `attach_session(terminal_id, session_id)`：校验会话归属后返回该会话的缓冲内容，供前端回放。**回放按连接粒度**：每个新连接 attach 时返回缓冲，已在线设备不重复回放（由前端按连接控制，后端只负责提供缓冲快照）。

#### 3.1.3 归属过滤与字段暴露（`app.py`）

- `list_terminals`（HTTP GET `/api/terminals`）改为按当前用户 `session_id` 过滤，只返回该用户自己的会话，并暴露 `session_id`、`node_id`、`created_at` 字段。
- 新增接管接口（HTTP 或 WS 消息）：前端登录/重连后调用，获取存活会话列表 + 缓冲内容。
- 接管接口沿用 `terminal:create` 权限校验，并校验会话归属（只能接管自己的会话）。

### 3.2 前端改动（`App.vue`）

- WS 重连成功后，调用 `list_terminals`（或接管接口）拉回当前用户存活会话。
- 将存活会话逐个加入 `terminalSessions`，调用 `initIndependentTerminal` 初始化 xterm，并回放缓冲内容。
- 多设备各自独立回放，互不重复。
- 在终端面板展示"可恢复的会话"标签，用户可点击接管或关闭。

### 3.3 多设备语义

| 场景               | 行为                                       |
| ------------------ | ------------------------------------------ |
| 设备 A、B 同时在线 | 都实时收到终端输出（现有能力，保留）       |
| 设备 A 断开        | 只移除 A 的订阅，B 继续接收                |
| 设备 A 重连        | 只给 A 回放缓冲，B 不重复                  |
| 任一设备关闭终端   | 广播 `terminal_closed`，所有设备移除该标签 |

---

## 四、局限与后续增强

### 4.1 局限（方案 A）

- 终端进程仍运行在网关进程内（PTY），**网关重启 / 升级后会话仍会丢失**（`cleanup()` 在 lifespan 关闭时杀所有会话）。
- 缓冲有上限，超出上限的早期输出无法回放。

### 4.2 后续增强（方案 B）

- **进程解耦（tmux/screen 或独立守护）**：把终端进程从网关进程解耦，网关只做代理。网关重启后终端仍存活，可重新 attach。改动大、引入外部依赖、多节点 / Windows 支持复杂，风险高，另行评估。

---

## 五、验证方式

1. 后端语法 / 导入检查通过。
2. 运行 `tests/jarvis_web_gateway/` 下终端相关测试，确认无回归。
3. 端到端验证：
   - 创建终端 → 前端断开 → 后端进程仍在（`list_terminals` 能看到）。
   - 重新登录 → 自动恢复会话 → 回放断开期间输出 → 可继续输入。
   - 同账号两台设备同时在线 → 都实时收到输出；一台断开重连 → 只回放给该设备，不重复。
4. 权限校验：非 `terminal:create` 权限用户无法创建/接管；只能接管自己的会话。

---

## 六、变更记录

- 2026-10-06：方案 A 定稿并开始实现。初始安全回退 commit：`98ff93532d6c2901dddfb862d9e39c71e97fc863`。
