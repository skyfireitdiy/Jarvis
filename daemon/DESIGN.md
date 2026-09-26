# Jarvis 本地守护进程（jarvis-daemon）设计方案

> 状态：方案定稿，待实现
> 范围：本轮只打通「认证 → 连接网关 → 保持在线 → 收指令回占位结果」这条链路

## 1. 背景与目标

用 **Go** 编写一个本地守护进程，运行在用户机器上，与浏览器扩展**完全独立**（不依赖扩展、不依赖浏览器）。

本轮目标只有一个：**把链路和通信打通**。

具体而言：

1. 网页（已登录）把登录信息（JWT + 网关地址）推送给本地守护进程；
2. 守护进程使用**独立端点** `/api/daemon/ws`（子协议 `jarvis-daemon`）连接网关，握手/心跳形态与浏览器扩展一致；
3. 保持在线：`hello` / `hello_ack` / 心跳 / 断线重连；
4. 能接收网关下发的指令，并返回**占位结果**（`not_implemented`）。

明确**不在本轮范围**：

- 具体业务功能（指令的真实执行）；
- 守护进程自更新；
- 浏览器扩展更新；
- 服务端更新。

## 2. 总体架构

```text
┌──────────────┐  ①POST /api/auth {gateway,token}  ┌────────────────────┐
│ 网页 App.vue  │ ─────────────────────────────────▶│  本地守护进程       │
│ (jvs-ai.cn)   │ ◀────────── /api/status ──────────│  127.0.0.1:17800   │
└──────────────┘                                    │  (Go, 常驻)         │
                                                    └─────────┬──────────┘
                                                              │ ②WS 子协议
                                                              │ ["jarvis-daemon",
                                                              │  "jarvis-token.<jwt>"]
                                                              ▼
                                                    ┌────────────────────┐
                                                    │ 网关 /api/daemon/ws │
                                                    │  hello/hello_ack    │
                                                    │  ping/pong          │
                                                    │  capability.list    │
                                                    │  capability.call    │
                                                    └────────────────────┘
```

**关键设计**：守护进程使用与浏览器扩展一致的握手/心跳形态，但走**独立端点**，
网关侧由独立的 `daemon_capability_manager` 管理会话，与扩展会话互不干扰。

因此：

- **网关侧**：新增端点 `/api/daemon/ws`（`app.py`）与会话管理 `daemon_capability_manager.handle_daemon_websocket`，并提供 `/api/daemon/sessions`、`/api/daemon/capability/list`、`/api/daemon/capability/call` 三个 HTTP API 供 Agent 工具层调用；
- **网页侧极小改动**：只新增一个「认证本地进程」入口 + 一次 `fetch`，不动现有逻辑。

## 3. 认证链路

### 3.1 网页 → 守护进程

网页新增入口（如设置面板中的「认证本地进程」按钮），点击后发起：

```http
POST http://127.0.0.1:17800/api/auth
Content-Type: application/json

{
  "gateway": "https://jvs-ai.cn",
  "token": "<JWT>"
}
```

- `gateway`：网页侧取自 `window.__jarvisAuthBridge.getGateway()`（`App.vue:16661` 附近），与扩展同源逻辑；
- `token`：网页侧取自 `auth.value.token`，与扩展 `getToken()` 同源。

守护进程校验入参后返回：

```json
{ "success": true, "status": "connecting", "daemon_version": "0.1.0" }
```

### 3.2 守护进程 → 网关

守护进程与浏览器扩展使用同一套握手/心跳形态（参考 `browser_extension/background/ws_client.js:65-69`），但走独立端点：

| 项       | 取值                                                                                                                                              |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| URL      | `{ws_gateway}/api/daemon/ws`                                                                                                                      |
| 子协议   | `["jarvis-daemon", "jarvis-token." + urlencode(token)]`                                                                                           |
| 首帧     | `{"type":"hello","client_id":...,"extension_version":...,"browser_info":...,"tabs":[]}`                                                           |
| 应答     | `{"type":"hello_ack","session_id":...,"heartbeat_interval":...}`                                                                                  |
| 心跳     | 按 `heartbeat_interval`（默认 20s）发 `{"type":"ping"}`，收 `pong`                                                                                |
| 能力     | 收 `{"type":"capability.list"}` → 回 `capability.list.result`；收 `{"type":"capability.call","id","name","params"}` → 回 `capability.call.result` |
| 鉴权失败 | 关闭码 `4401` / `4403` → 标记 Token 失效，**不重连**，等网页重新推送                                                                              |
| 其他断开 | 指数退避重连：1s → 30s                                                                                                                            |

守护进程会话的字段约定：

- `client_id`：`daemon-<hostname>-<uuid>`
- `extension_version`：守护进程自身版本
- `browser_info`：标识为守护进程（如 `{"name":"jarvis-daemon","os":...}`）
- `tabs`：空数组
- `user_id`：**不由守护进程上报**，而是网关从 WS 子协议中的 `jarvis-token.<token>` 解析得到并绑定到会话上，用于多用户隔离（见 8.7）

### 3.3 状态查询

```http
GET http://127.0.0.1:17800/api/status
```

```json
{
  "connected": true,
  "session_id": "...",
  "gateway": "https://jvs-ai.cn",
  "token_valid": true,
  "daemon_version": "0.1.0"
}
```

网页可轮询该接口，展示「已连接 / 未连接 / Token 失效」。

## 4. 本地接口

| 方法 | 路径          | 说明                                        |
| ---- | ------------- | ------------------------------------------- |
| POST | `/api/auth`   | 接收 `{gateway, token}`，存入内存并触发连接 |
| GET  | `/api/status` | 返回连接状态、`session_id`、Token 有效性    |
| POST | `/api/logout` | 清空内存中的 Token，断开 WebSocket          |

### 安全设计

- **仅绑定 `127.0.0.1`**，绝不监听 `0.0.0.0`；
- **不做额外鉴权**（已确认）：因为只对本机回环开放，外部无法访问；
- Token **仅存内存**，不落盘，进程退出即失效。

## 5. 目录结构

```text
daemon/                          # 与 browser_extension/ 同级
├── DESIGN.md                    # 本文档
├── go.mod                       # module jarvis-daemon
├── cmd/
│   └── jarvis-daemon/
│       └── main.go              # 入口：加载配置、启动本地 API、启动 WS 客户端
└── internal/
    ├── config/
    │   └── config.go            # 端口、网关默认值、配置文件读取
    ├── localapi/
    │   └── server.go            # /api/auth /api/status /api/logout
    ├── auth/
    │   └── store.go             # 内存 token / gateway 存储
    ├── wsclient/
    │   ├── client.go            # WS 子协议 + hello + 心跳 + 重连 + 能力消息处理
    │   └── client_capability_test.go # 能力列表 / 能力调用 的 WS 单元测试
    ├── capability/
    │   ├── capability.go        # Platform / Capability / Result / Registry
    │   ├── platform.go          # Current / Matches（平台判定）
    │   ├── registry_linux.go    # //go:build linux：Linux 能力装配（本轮空）
    │   ├── registry_windows.go  # //go:build windows：Windows 能力装配（本轮空）
    │   ├── registry_other.go    # //go:build !linux && !windows：兜底（本轮空）
    │   └── capability_test.go   # 注册 / 查询 / 平台过滤 / 执行 单元测试
    └── handler/
        └── dispatch.go          # command 分发（action 即能力名；未接入注册表时占位返回 not_implemented）
```

## 6. 配置

默认配置文件：`~/.jarvis/daemon/config.yaml`

```yaml
listen: "127.0.0.1:17800" # 本地 API 监听地址
gateway: "" # 默认网关（可被 /api/auth 覆盖）
heartbeat_interval: 20 # 秒，可被 hello_ack 覆盖
reconnect_min: 1 # 秒
reconnect_max: 30 # 秒
```

命令行参数可覆盖配置文件（如 `--listen`、`--gateway`）。

## 7. 服务安装与管理

守护进程支持注册为系统服务，实现开机自启与统一的生命周期管理。参考实现为 `src/jarvis/jarvis_service/cli.py`（`SystemdBackend` / `WindowsTaskBackend`）。

### 7.1 子命令

```text
jarvis-daemon [run] [选项]     前台运行守护进程（默认行为，向后兼容）
jarvis-daemon install [选项]   安装为系统服务并设为开机自启（不启动）
jarvis-daemon uninstall        停止并卸载系统服务
jarvis-daemon start            启动服务
jarvis-daemon stop             停止服务
jarvis-daemon restart          重启服务
jarvis-daemon status           查看服务状态
```

`install` 与 `run` 共用 `-listen` / `-gateway` / `-config` 选项；`install` 会把这些值固化进服务定义。

### 7.2 平台实现

| 项       | Linux                                                  | Windows                                       |
| -------- | ------------------------------------------------------ | --------------------------------------------- |
| 服务定义 | `~/.config/systemd/user/jarvis-daemon.service`         | 计划任务 `Jarvis-Daemon`                      |
| 安装     | 写 unit + `systemctl --user daemon-reload` + `enable`  | `schtasks /Create /SC ONLOGON /RL HIGHEST /F` |
| 启动     | `systemctl --user start`                               | 分离进程启动 + PID 文件                       |
| 停止     | `systemctl --user stop`                                | `taskkill /PID <pid> /F`                      |
| 自启     | `systemctl --user enable`                              | 计划任务本身（登录时触发）                    |
| 状态     | `is-active` / `is-enabled` / `show --property=MainPID` | PID 存活（`tasklist`）+ `schtasks /Query`     |

Linux unit 关键内容：

```ini
[Unit]
Description=Jarvis Daemon
After=network.target

[Service]
Type=simple
Environment=PATH=<可执行文件目录>:<当前 PATH>
Environment=<透传的代理环境变量，有值才写>
ExecStart=<可执行文件绝对路径> run --listen 127.0.0.1:17800
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

Windows PID 文件位于 `~/.jarvis/pids/jarvis-daemon.pid`。

### 7.3 代码结构

```text
internal/service/
├── service.go            # Service 接口、Options、Status、New、ResolveExecPath、BuildRunArgs
├── systemd_linux.go      # //go:build linux：BuildUnit + systemd 用户服务实现
├── task_windows.go       # //go:build windows：计划任务实现
├── new_linux.go          # //go:build linux：平台分发
├── new_windows.go        # //go:build windows：平台分发
├── new_other.go          # //go:build !linux && !windows：兜底
├── procattr_windows.go   # //go:build windows：分离进程启动属性
├── procattr_other.go     # //go:build !windows：空实现
└── service_test.go       # 纯函数与平台分发单元测试
```

平台分发通过 `newPlatformService()` 由各平台文件提供，`New()` 在返回 nil 时兜底为 `unsupportedService`（避免在无构建标签的文件里引用平台专有类型）。

## 8. 能力注册表（Capability Registry）

### 8.1 设计目标与参考对象

守护进程需要一套统一的方式描述「本机可以做什么」，让网关（进而让模型）能够**先查询能力、再按名调用**，而不必在网关侧硬编码平台差异。

参考对象是 Python 侧 `src/jarvis/jarvis_tools/registry.py` 的 `Tool` / `ToolRegistry` 模型：每个工具由 `name` / `description` / `parameters` / `func` 四要素构成，注册表负责注册、查询、列出与执行。Go 侧做等价映射，但改用 Go 惯用法：`Handler` 返回 `(any, error)`，结果用 `Result{Success, Data, Error}` 表达。

### 8.2 Capability 结构

| 字段          | 类型                                       | 说明                                              |
| ------------- | ------------------------------------------ | ------------------------------------------------- |
| `name`        | `string`                                   | 能力唯一名称，建议「域.动作」形式（如 `fs.read`） |
| `description` | `string`                                   | 能力说明，供模型理解用途                          |
| `parameters`  | `map[string]any`                           | 参数 JSON schema 描述，可为空                     |
| `platform`    | `Platform`                                 | 适用平台；为空时视为 `any`                        |
| `handler`     | `func(params map[string]any) (any, error)` | 能力实现；不参与 JSON 序列化（`json:"-"`）        |

`Result` 为一次调用的结果：`success`（bool）、`data`（any）、`error`（string）。

### 8.3 Registry 接口

| 方法                             | 说明                                                                                                                                                   |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `NewRegistry()`                  | 创建注册表，并调用 `registerPlatformCapabilities` 装配当前平台能力                                                                                     |
| `Register(cap Capability) error` | 注册能力；名称为空或重复注册均返回错误（不静默覆盖）                                                                                                   |
| `Get(name string)`               | 按名查询，返回 `(*Capability, bool)`                                                                                                                   |
| `List()`                         | 返回全部能力副本，按名称升序                                                                                                                           |
| `ListForPlatform(p Platform)`    | 返回适用于指定平台的能力（含 `any`），按名称升序                                                                                                       |
| `Execute(name, params) Result`   | 按名执行；未注册返回 `unknown capability: <name>`；`handler` 为 nil 返回 `capability not implemented: <name>`；`handler` panic 会被 recover 并转为错误 |

注册表并发安全（`sync.RWMutex`），且**不含任何全局状态**——`NewRegistry()` 每次返回独立实例，因此多个守护进程连接同一网关时互不干扰。

### 8.4 平台划分与分发方式

平台取值：`windows` / `linux` / `darwin` / `any`，其中 `any` 表示跨平台通用能力（`Matches` 对任意平台返回 true）。

平台专有能力通过**构建标签**装配：

```text
internal/capability/
├── capability.go          # 无标签：类型与注册表
├── platform.go            # 无标签：Current / Matches
├── registry_linux.go      # //go:build linux
├── registry_windows.go    # //go:build windows
└── registry_other.go      # //go:build !linux && !windows
```

各平台文件提供 `registerPlatformCapabilities(reg *Registry)`，由 `NewRegistry()` 调用。之所以不把 `runtime.GOOS` 的 `switch` 写在无标签文件里，是因为那样会引用平台专有类型，交叉编译（如 `GOOS=windows go build`）时对应类型被排除而直接编译失败。该做法与 `internal/service` 的 `newPlatformService()` 一致。

### 8.5 WS 协议扩展

在既有 WS 连接上新增两类消息（网关 → 守护进程）：

#### 查询能力列表

```json
{ "type": "capability.list" }
```

```json
{
  "type": "capability.list.result",
  "capabilities": [
    {
      "name": "fs.read",
      "description": "读取文件内容",
      "parameters": {
        "type": "object",
        "properties": { "path": { "type": "string" } }
      },
      "platform": "any"
    }
  ]
}
```

#### 调用能力

```json
{
  "type": "capability.call",
  "id": "call-1",
  "name": "fs.read",
  "params": { "path": "/tmp/a.txt" }
}
```

```json
{
  "type": "capability.call.result",
  "id": "call-1",
  "success": true,
  "data": { "content": "..." },
  "error": ""
}
```

失败时 `success` 为 `false`、`error` 给出原因（如 `unknown capability: fs.read`、`capability registry is nil`、`capability name is empty`）。

### 8.6 与扩展 command/result 信封的关系

指令的信封结构保持不变（`{id, type:"command", action, params, timeout_ms}` → `{id, type:"result", success, data, error}`），只是 **`action` 现在就是能力名**：接入注册表后由 `handler.DispatchWith(reg, cmd)` 执行，未接入（`Registry` 为 nil）时回退到旧的占位实现（返回 `not_implemented`），保证向后兼容。

### 8.7 本轮范围

本轮实现框架 **并注册 Linux 平台能力**：

- Linux 平台已注册 21 个能力（`registerPlatformCapabilities` 在 `registry_linux.go` 中按 `//go:build linux` 装配），见下表；Windows / Darwin 暂未注册（为空实现）；
- 网关侧（Python）已实现：新增独立端点 `/api/daemon/ws` 与会话管理 `daemon_capability_manager`，并提供 `/api/daemon/sessions`、`/api/daemon/capability/list`、`/api/daemon/capability/call` 三个 HTTP API；跨节点调用经 `node_protocol` 的 `daemon_capability_*` 消息由 `NodeConnectionManager` 转发；
- 多守护进程连接同一网关时，网关侧以 `hello` 中的 `client_id` 区分会话（`session_id` 由网关分配），能力调用结果按 `id` 回投到对应会话。

#### 已注册的 Linux 能力

| 能力名                  | 说明                                           | 实现方式                                       |
| ----------------------- | ---------------------------------------------- | ---------------------------------------------- |
| `linux.script.exec`     | 执行 shell 脚本                                | `sh -c`（带超时）                              |
| `linux.process.list`    | 列出进程                                       | 直接读 `/proc`（不依赖 `ps`）                  |
| `linux.process.kill`    | 结束进程                                       | 发送信号                                       |
| `linux.system.info`     | 系统信息（发行版/内核/CPU/内存等）             | 读 `/proc`、`/etc/os-release`                  |
| `linux.fs.read`         | 读文件（支持 offset/limit，二进制自动 base64） | 标准库                                         |
| `linux.fs.write`        | 写文件                                         | 标准库                                         |
| `linux.fs.list`         | 列目录                                         | 标准库                                         |
| `linux.service.list`    | 列出用户级 systemd 服务                        | `systemctl --user`                             |
| `linux.service.status`  | 查询服务状态                                   | `systemctl --user`                             |
| `linux.service.start`   | 启动服务                                       | `systemctl --user`                             |
| `linux.service.stop`    | 停止服务                                       | `systemctl --user`                             |
| `linux.service.restart` | 重启服务                                       | `systemctl --user`                             |
| `linux.window.list`     | 列出窗口                                       | `wmctrl -lp`，回退 `xdotool search`            |
| `linux.window.focus`    | 激活窗口                                       | `wmctrl -i -a` / `xdotool windowactivate`      |
| `linux.window.close`    | 关闭窗口                                       | `wmctrl -i -c` / `xdotool windowclose`         |
| `linux.input.click`     | 鼠标移动并点击                                 | `xdotool mousemove` + `click`                  |
| `linux.input.type`      | 输入文本                                       | `xdotool type --delay -- <text>`               |
| `linux.input.keys`      | 发送按键/组合键                                | `xdotool key -- <keys>`                        |
| `linux.clipboard.get`   | 读剪贴板                                       | `xclip -selection clipboard -o` / `xsel -b -o` |
| `linux.clipboard.set`   | 写剪贴板                                       | `xclip` stdin / `xsel -b -i`                   |
| `linux.screenshot`      | 截屏                                           | `import` > `scrot` > `grim`                    |

设计约束与已知限制：

- **GUI 能力不直接链接 X11**：早期尝试用纯 Go `dlopen`（`cgo_import_dynamic` + `linkname`）调用 X11 失败（ABI0/ABIInternal 不匹配），cgo 方案又需要 `X11/extensions/XTest.h` 且破坏 `CGO_ENABLED=0` 交叉编译，故最终改为**调用外部命令**（`xdotool`/`wmctrl`/`xclip`/`xsel`/`import`/`scrot`/`grim`）。缺失工具时返回带安装提示的明确错误。
- GUI 能力执行前检查 `DISPLAY` / `WAYLAND_DISPLAY`，为空时返回「未检测到图形环境」；Wayland 下 `xdotool`/`wmctrl` 通常不可用（仅 `grim` 截图可用）。
- `linux.service.*` 仅支持 `--user` 级服务；unit 名做了白名单校验并**拒绝以 `-` 开头**，避免 `--now` 之类被 `systemctl` 当作命令行选项（参数注入）。
- `linux.fs.*` 未做路径白名单/沙箱，可读写守护进程有权限的任意路径；二进制判定为「含 NUL 或非法 UTF-8」，纯 ASCII 的二进制格式可能漏判。
- GUI 能力的成功路径**未在本机端到端验证**（本机无 `DISPLAY` 且 GUI 工具均缺失），仅验证了错误路径与解析逻辑。

#### 多用户隔离

守护进程能力可在用户本机执行任意操作，因此网关侧必须做用户级隔离，避免任意有效 Token 跨用户调用他人机器：

- **会话绑定 `user_id`**：`/api/daemon/ws` 端点鉴权成功后，从 `auth_payload["user_info"]` 取 `user_id` 传入 `DaemonCapabilityManager.handle_daemon_websocket`，写入会话；浏览器扩展端点（`/api/browser-ext/ws`）同样处理。
- **去掉「无 Token 也放行」兜底**：daemon 与 browser-ext 的 WS 端点原先在未携带 token 时以「网关存在任一已登录会话」为由放行，现已改为直接鉴权失败（4401）。
- **HTTP API 归属校验**：`/api/daemon/capability/list`、`/api/daemon/capability/call`、`/api/browser-ext/command` 在调用前用 `check_session_access(session_id, user_id, is_admin)` 校验会话归属；`/api/daemon/sessions`、`/api/browser-ext/sessions` 按 `user_id` 过滤（`user_id` 为 `system` 或 `is_admin` 时可见全部）。
- **跨节点转发携带 `user_id`**：master 把 `daemon_capability_list_request` / `daemon_capability_call_request` 转发到 child 时，payload 中带上 `user_id` 与 `is_admin`，child 侧再次校验归属，避免绕过。
- **拒绝语义**：会话不存在返回 `daemon session not found: <id>`；跨用户返回 `forbidden: daemon session belongs to another user`。

## 9. 网页侧改动

仅一处：新增「认证本地进程」按钮，点击后：

```js
await fetch("http://127.0.0.1:17800/api/auth", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    gateway: window.__jarvisAuthBridge.getGateway(),
    token: window.__jarvisAuthBridge.getToken(),
  }),
});
```

不改动任何现有逻辑。

## 10. 验证方式

1. `go build ./...` 通过；
2. 启动守护进程，`curl -X POST http://127.0.0.1:17800/api/auth -d '{"gateway":"...","token":"<真实JWT>"}'`；
3. `GET /api/status` 返回 `connected: true` 且带 `session_id`；
4. 网关侧 `GET /api/daemon/sessions` 能看到该会话；
5. 网关侧 `POST /api/daemon/capability/list`（带 `session_id`）→ 返回能力列表（Linux 下为 21 个 `linux.*` 能力）；
6. 网关侧 `POST /api/daemon/capability/call`（带 `session_id`/`name`/`params`）→ 执行对应能力；能力名不存在时返回 `unknown capability: <name>`；
7. 断线后按退避重连；Token 失效（4401）时不空转重连；
8. 多用户隔离：用用户 A 的 Token 携带用户 B 的 `session_id` 调用 `capability/list` 或 `capability/call` → 返回 `forbidden: daemon session belongs to another user`；`GET /api/daemon/sessions` 只返回 A 自己的会话；未携带 Token 连接 `/api/daemon/ws` → 关闭码 4401。

## 11. 后续（不在本轮）

- 指令的真实执行（业务功能）；
- 守护进程自更新；
- 浏览器扩展更新（下载 zip → 覆盖扩展目录 → 通知 `chrome.runtime.reload()`）；
- 服务端更新。

## 12. 已确认的决策

| 项             | 决定                                                                     |
| -------------- | ------------------------------------------------------------------------ |
| 本地端口鉴权   | 不做鉴权（仅绑 127.0.0.1）                                               |
| 端口 / 配置    | 默认 `127.0.0.1:17800`，配置走 `~/.jarvis/daemon/config.yaml`            |
| 代码位置       | `daemon/`，与浏览器扩展同目录                                            |
| 本轮范围       | 只打通链路与通信                                                         |
| 扩展目录路径   | 后续再定（本轮不涉及扩展更新）                                           |
| 能力命名       | 「域.动作」形式（如 `fs.read`），`action` 即能力名                       |
| 能力平台分发   | 用构建标签（`registry_*.go`），不在无标签文件里写平台 switch             |
| 能力注册表范围 | 框架 + Linux 平台 21 个能力已实现；Windows / Darwin 未注册；网关侧已实现 |
