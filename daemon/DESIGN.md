# Jarvis 本地守护进程（jarvis-daemon）设计方案

> 状态：方案定稿，待实现
> 范围：本轮只打通「认证 → 连接网关 → 保持在线 → 收指令回占位结果」这条链路

## 1. 背景与目标

用 **Go** 编写一个本地守护进程，运行在用户机器上，与浏览器扩展**完全独立**（不依赖扩展、不依赖浏览器）。

本轮目标只有一个：**把链路和通信打通**。

具体而言：

1. 网页（已登录）把登录信息（JWT + 网关地址）推送给本地守护进程；
2. 守护进程使用与浏览器扩展**相同的 WebSocket 子协议**连接网关；
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
                                                              │ ["jarvis-ext",
                                                              │  "jarvis-token.<jwt>"]
                                                              ▼
                                                    ┌────────────────────┐
                                                    │ 网关 /api/browser-  │
                                                    │ ext/ws              │
                                                    │  hello/hello_ack    │
                                                    │  ping/pong          │
                                                    │  command/result     │
                                                    └────────────────────┘
```

**关键设计**：守护进程复用浏览器扩展的协议，在网关眼里它就是一个"扩展会话"。

因此：

- **网关侧零改动**：直接复用现有端点 `app.py:3248`（`/api/browser-ext/ws`）与会话管理 `browser_extension_manager.handle_extension_websocket`；
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

完全照搬浏览器扩展的做法（`browser_extension/background/ws_client.js:65-69`）：

| 项       | 取值                                                                                            |
| -------- | ----------------------------------------------------------------------------------------------- |
| URL      | `{ws_gateway}/api/browser-ext/ws`                                                               |
| 子协议   | `["jarvis-ext", "jarvis-token." + urlencode(token)]`                                            |
| 首帧     | `{"type":"hello","client_id":...,"extension_version":...,"browser_info":...,"tabs":[]}`         |
| 应答     | `{"type":"hello_ack","session_id":...,"heartbeat_interval":...,"latest_extension_version":...}` |
| 心跳     | 按 `heartbeat_interval`（默认 20s）发 `{"type":"ping"}`，收 `pong`                              |
| 指令     | 收 `{"id","type":"command","action","params","timeout_ms"}` → 回 `{"id","type":"result",...}`   |
| 鉴权失败 | 关闭码 `4401` / `4403` → 标记 Token 失效，**不重连**，等网页重新推送                            |
| 其他断开 | 指数退避重连：1s → 30s                                                                          |

守护进程作为"扩展会话"的字段约定：

- `client_id`：`daemon-<hostname>-<uuid>`
- `extension_version`：守护进程自身版本
- `browser_info`：标识为守护进程（如 `{"name":"jarvis-daemon","os":...}`）
- `tabs`：空数组

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
    │   └── client.go            # WS 子协议 + hello + 心跳 + 重连
    └── handler/
        └── dispatch.go          # command 分发（本轮占位返回 not_implemented）
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

## 8. 网页侧改动

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

## 9. 验证方式

1. `go build ./...` 通过；
2. 启动守护进程，`curl -X POST http://127.0.0.1:17800/api/auth -d '{"gateway":"...","token":"<真实JWT>"}'`；
3. `GET /api/status` 返回 `connected: true` 且带 `session_id`；
4. 网关侧 `GET /api/browser-ext/sessions` 能看到该会话；
5. 网关下发测试 command → 守护进程返回占位 `result`；
6. 断线后按退避重连；Token 失效（4401）时不空转重连。

## 10. 后续（不在本轮）

- 指令的真实执行（业务功能）；
- 守护进程自更新；
- 浏览器扩展更新（下载 zip → 覆盖扩展目录 → 通知 `chrome.runtime.reload()`）；
- 服务端更新。

## 11. 已确认的决策

| 项           | 决定                                                          |
| ------------ | ------------------------------------------------------------- |
| 本地端口鉴权 | 不做鉴权（仅绑 127.0.0.1）                                    |
| 端口 / 配置  | 默认 `127.0.0.1:17800`，配置走 `~/.jarvis/daemon/config.yaml` |
| 代码位置     | `daemon/`，与浏览器扩展同目录                                 |
| 本轮范围     | 只打通链路与通信                                              |
| 扩展目录路径 | 后续再定（本轮不涉及扩展更新）                                |
