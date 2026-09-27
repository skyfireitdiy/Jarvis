# 无 GUI 主机的登录方式：`login` 子命令与 Web 登录服务

本文描述在没有图形界面的主机（典型如无桌面的 Linux 服务器）上，如何让
`jarvis-daemon` 拿到网关凭据并建立连接。

背景：正常情况下凭据由**浏览器扩展**推送给本机守护进程（页面加载时通过
`POST /api/auth` 把 JWT 交给 `127.0.0.1:17800`）。无 GUI 主机上没有浏览器，
这条链路走不通，因此提供两条替代路径：

| 方式                    | 适用场景                         | 入口                                 |
| ----------------------- | -------------------------------- | ------------------------------------ |
| `login` 子命令          | 能 SSH 登录该主机、可交互输入    | `jarvis-daemon login`                |
| Web 登录服务（`webui`） | 只能从**另一台机器**的浏览器访问 | `http://<主机IP>:17801/`（默认端口） |

两条路径最终都落到**同一套凭据写入 + 连接发起**逻辑，与浏览器扩展推送完全等价。

---

## 1. `jarvis-daemon login` 子命令

### 1.1 用法

```bash
jarvis-daemon login [-gateway <网关地址>] [-u <用户名>] [-listen <本地监听地址>] [-config <配置文件>]
```

- `-gateway`：网关地址，覆盖配置文件中的 `gateway:`。留空且配置也未填时报错。
- `-u`：登录用户名。留空时交互式提示输入。
- `-listen`：本地 API 监听地址，覆盖配置文件中的 `listen:`；都为空时回退
  `127.0.0.1:17800`。凭据会推送到这个地址。
- `-config`：配置文件路径，默认 `~/.jarvis/daemon/config.yaml`。

**密码始终通过交互式隐藏输入获取，不提供 `-p` 之类的命令行参数**——避免密码
进入 shell 历史、进程命令行（`ps` 可见）与日志。

### 1.2 交互流程

```text
$ jarvis-daemon login -gateway http://gateway.example.com:8000
用户名: admin
密码:            # 输入时不回显
[daemon] 正在登录网关 http://gateway.example.com:8000 ...
[daemon] 登录成功: 管理员（token e2e1...efgh）
[daemon] 已向本地后台服务（127.0.0.1:17800）推送凭据，守护进程将连接网关
```

- token 只打印**脱敏**形式（首尾各 4 字符，中间省略），完整凭据不落日志。
- 登录成功后向 `POST http://<listen>/api/auth` 推送 `{gateway, token, name}`，
  `name` 传空字符串，表示保留守护进程在该网关下已有的终端名称。

### 1.3 错误信息

| 情况             | 输出                                                                    |
| ---------------- | ----------------------------------------------------------------------- |
| 用户名或密码错误 | `登录被拒绝: Invalid username or password`（网关原文）                  |
| 网关不可达       | `登录请求失败（...）: connection refused`                               |
| 未配置网关       | `未指定网关地址，请用 -gateway 指定，或先在配置文件 ... 中配置 gateway` |
| 本地服务未运行   | 推送失败并给出提示（登录本身已完成）                                    |

### 1.4 实现位置

- `daemon/internal/login/login.go`：`Login()` / `PushAuth()` / `NormalizeGateway()` / `MaskToken()`。
- `daemon/internal/login/password_{linux,windows,other}.go`：隐藏输入的平台实现
  （Linux 用 `ioctl` 关 `ECHO`，Windows 用 `SetConsoleMode` 关 `ENABLE_ECHO_INPUT`）。
- `daemon/cmd/jarvis-daemon/main.go` 的 `cmdLogin()`。

---

## 2. Web 登录服务（`webui`）

### 2.1 用途

当操作者**无法 SSH** 到目标主机（或不想用命令行）时，可以从另一台机器的浏览器
访问目标主机上的 Web 登录页，在页面上填写「网关地址 + 用户名 + 密码」，由守护
进程代为登录网关并直接建立连接。

### 2.2 配置

| 配置项                                    | 默认值          | 说明                 |
| ----------------------------------------- | --------------- | -------------------- |
| `web_listen`（配置文件）                  | `0.0.0.0:17801` | Web 登录服务监听地址 |
| `-web-listen`（命令行，run/install 共用） | 同左            | 覆盖配置文件         |

**`-web-listen` 传空串表示关闭该服务**（与「未提供该参数」不同：未提供时沿用
配置文件里的值）。示例：

```bash
# 关闭 Web 登录服务
jarvis-daemon run -web-listen ""

# 只监听回环（仅本机浏览器可访问）
jarvis-daemon run -web-listen 127.0.0.1:17801
```

启动时若绑定到非回环地址，日志会打印安全提示：

```text
[daemon] Web 登录页: http://0.0.0.0:17801/（绑定非回环地址，仅限可信内网使用）
```

### 2.3 接口

| 方法 | 路径         | 说明                                                          |
| ---- | ------------ | ------------------------------------------------------------- |
| GET  | `/`          | 内嵌登录页（`Cache-Control: no-store`；非根路径一律 404）     |
| POST | `/api/login` | 请求体 `{gateway, username, password, name?}`，代为登录并连接 |

`POST /api/login` 成功返回：

```json
{
  "success": true,
  "message": "登录成功，守护进程已连接网关，本页面可以关闭了",
  "user": "管理员"
}
```

失败返回 400 与可读的中文错误（如 `请填写网关地址` / `请填写用户名` /
`请填写密码` / 网关返回的登录错误原文），**错误信息中不含密码**。

请求体上限 64 KiB（`http.MaxBytesReader`）。

### 2.4 实现位置

- `daemon/internal/webui/server.go`：`Server` / `New()` / `Handler()`。
- `daemon/internal/webui/index_html.go`：内嵌登录页。
- `daemon/cmd/jarvis-daemon/main.go`：`runDaemon()` 中按 `cfg.WebListen` 启动
  （与本地 API 服务相互独立，共用同一份 `auth.Store` 与 `wsclient.Manager`）。

---

## 3. ⚠️ 安全警告（务必阅读）

Web 登录服务是**方案 A**：只做登录、不做额外防护。已知风险：

1. **明文传输**：页面与接口走 HTTP，密码在局域网内明文传输。
2. **无鉴权**：任何能连到该端口的人都可以尝试登录（并可能爆破密码）。
3. **默认对外监听**：默认 `0.0.0.0:17801`，即监听所有网卡。

因此：

- **仅应在可信内网使用**，并配合防火墙限制来源网段；
- 不需要该功能时，用 `-web-listen ""` 或把 `web_listen` 置空关闭；
- 若只是本机使用，改为监听 `127.0.0.1:17801`。

> 本轮按用户要求**未加入任何鉴权**，请勿在不可信网络中启用。

---

## 4. 凭据存储与生命周期

- 凭据（JWT）**只存内存、绝不落盘**（`daemon/internal/auth/store.go`），
  进程退出即失效，重启后需重新登录（或由浏览器扩展补推）。
- 多网关并存：`Store` 以网关地址为键，登录新网关不会覆盖已有网关。
- 网关侧 JWT 默认**不设过期时间**（`JARVIS_JWT_EXPIRE_HOURS` 默认 `0`），
  以满足守护进程长期连接的需要。

---

## 5. 已知限制与未验证项

- **未验证**：真实网关的 **HTTPS** 场景（仅用 HTTP mock 端到端验证过）。
- **未验证**：Windows 上密码隐藏输入的实机行为（仅交叉编译通过）。
- `login` 子命令与 Web 登录服务都依赖**本地守护进程已在运行**（推送目标），
  若本地服务未启动，登录会成功但推送失败。
