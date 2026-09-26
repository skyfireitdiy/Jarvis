# 守护进程系统信息上报：链路与排查手册

本文描述 **jarvis-daemon 注册时上报系统信息** 这条链路的每一环，以及端到端验证
不通过时的定位方法。

## 1. 链路总览

```text
[daemon] capability.CollectSystemInfo()
   │  daemon/internal/capability/{linux_system_linux,system_windows,system_darwin}.go
   ▼
[daemon] hello 帧 {"type":"hello", ..., "system_info": {...}}
   │  daemon/internal/wsclient/client.go  connectAndServe()
   ▼  WS /api/daemon/ws（子协议 jarvis-daemon + jarvis-token.<token>）
[网关] handle_daemon_websocket() 解析 hello
   │  src/jarvis/jarvis_web_gateway/daemon_capability_manager.py
   ▼
[网关] 会话落库 self._sessions[session_id]["system_info"]
   │
   ▼
[网关] GET /api/daemon/sessions → {"success":true,"sessions":[{...,"system_info":{...}}]}
   │  src/jarvis/jarvis_web_gateway/app.py
   ▼
[Agent] daemon.list_sessions → stdout 中 JSON 含 system_info
      src/jarvis/jarvis_tools/daemon.py
```

## 2. 每一环的检查点

### 环节 A：daemon 采集系统信息

- 代码：`capability.CollectSystemInfo()`
- 各平台实现文件：
  - Linux：`daemon/internal/capability/linux_system_linux.go`（12 字段）
  - Windows：`daemon/internal/capability/system_windows.go`（6 字段）
  - macOS：`daemon/internal/capability/system_darwin.go`（6 字段）
- **验证方式**：daemon 启动日志中应出现

  ```text
  [wsclient] hello 将上报 system_info: hostname=xxx fields=N
  ```

- **失败现象**：
  - 无此行 → 采集函数返回了 error，日志中会有
    `[wsclient] 采集系统信息失败，hello 将不含 system_info: ...`
  - `fields=0` → 平台实现返回空 map（检查构建标签是否匹配当前 GOOS）

### 环节 B：hello 帧发送

- 代码：`daemon/internal/wsclient/client.go` 的 `connectAndServe()`
- hello 帧字段：`type` / `client_id` / `extension_version` / `tabs` / `system_info`
- **注意**：daemon 的 hello **不含** `browser_info`（浏览器信息由扩展自行上报）。
- **验证方式**：daemon 日志

  ```text
  [wsclient] 已连接 http://.../api/daemon/ws（子协议 [jarvis-daemon jarvis-token.xxx]）
  ```

### 环节 C：网关接收并落库

- 代码：`daemon_capability_manager.py` 的 `handle_daemon_websocket()`
- **验证方式**：网关日志应出现

  ```text
  [DAEMON] session connected: session_id=... client_id=... node_id=... user_id=...
  [DAEMON] hello system_info: received=True hostname='xxx' platform='yyy' fields=N
  ```

- **失败现象与含义**：

  | 现象                      | 含义                                                                                  |
  | ------------------------- | ------------------------------------------------------------------------------------- |
  | 无 `session connected` 行 | WS 未连上：token 无效、子协议不匹配、端点不对                                         |
  | `received=False fields=0` | 网关收到了 hello 但里面没有 `system_info` → 问题在环节 A/B（daemon 版本旧或采集失败） |
  | `hostname=''`             | `system_info` 里没有 `hostname` 键 → 检查平台实现的字段名                             |
  | `platform=''`             | `system_info` 里既无 `os_name` 也无 `platform`，且旧版 `browser_info` 也没有          |

### 环节 D：HTTP 接口返回

- 代码：`app.py` 的 `/api/daemon/sessions`
- **验证方式**：

  ```bash
  curl -s http://127.0.0.1:<网关端口>/api/daemon/sessions \
    -H "Authorization: Bearer <token>" | python -m json.tool
  ```

- **失败现象**：`session connected` 日志有、但这里 `system_info` 为 `{}`
  → 问题在返回层（`list_sessions()` 未带该字段，或会话已被心跳超时清理）

### 环节 E：Agent 工具透传

- 代码：`src/jarvis/jarvis_tools/daemon.py` 的 `list_sessions` 分支
- 该分支把网关返回的 `sessions` 列表交给 `_format_result()`，
  后者用 `json.dumps` **原样序列化，不裁字段**。
- **失败现象**：环节 D 的 curl 能看到 `system_info`，但 Agent 侧看不到
  → 检查是否用了旧版 `daemon.py`（旧版无此描述但逻辑本就透传），
  或 Agent 连的是另一个网关（`master_url` 不一致）。

## 3. 快速定位口诀

按顺序看三处日志/输出，即可把问题锁定到具体环节：

1. **daemon 日志**有没有 `hello 将上报 system_info: ... fields=N`？
   - 没有 → 问题在环节 A/B（daemon 侧）。
2. **网关日志**有没有 `hello system_info: received=True ... fields=N`？
   - 没有 → 问题在环节 C 的传输/解析（token、子协议、字段名）。
3. **curl `/api/daemon/sessions`** 有没有 `system_info`？
   - 没有 → 问题在环节 D（返回层）。
   - 有但 Agent 看不到 → 问题在环节 E（连错网关或旧代码）。

## 4. 已知限制

- `client_id` 含 PID（`daemon-<hostname>-<pid>`），daemon 每次重启都会变，
  因此 `node_id`（缺省回退为 `client_id`）不稳定。若需要稳定节点身份，
  需参照扩展的 `getClientId()` 做法把 client_id 持久化（本轮未做）。
- Windows / macOS 的系统信息字段少于 Linux（仅 hostname/os_name/arch/
  cpu_count/user/home），因未引入平台专有库。
- 本轮未做真实端到端联调（用户明确要求跳过），仅由单元测试覆盖
  网关解析、落库、返回与 Agent 透传四段。
