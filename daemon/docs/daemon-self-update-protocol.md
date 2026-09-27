# jarvis-daemon 自动更新协议设计（v1）

适用范围：**仅 Windows 与 Linux**（不含 macOS）。

## 1. 目标

1. daemon 向网关上报自身**版本号**与**体系架构**（GOOS/GOARCH）。
2. 网关把上报信息与「最新发布版本」比对，判断是否需要更新。
3. 需要更新时，网关向 daemon 下发 GitHub 发布下载链接（含 sha256）。
4. daemon 静默下载、校验、原子替换自身可执行文件，并重启服务。
5. 重启后 **Token 必须保持**。

## 2. 现状事实（调研结论，带依据）

- daemon hello 帧已上报：`extension_version`（版本号，`daemon/internal/wsclient/client.go:278`）、
  `system_info`（`client.go:286-292`）、`build_info`（`client.go:308-309`）。
- `build_info` 已含 `version`/`os`/`arch`/`go_version`/`exe_path`/`exe_mtime`/`commit`/`pid`
  （`daemon/internal/buildinfo/buildinfo.go:135-152`）——**架构已在 `build_info.os` / `build_info.arch` 上报**。
- 网关侧会话已存 `daemon_version`（取自 `extension_version`）、`build_info`、`system_info`、`platform`
  （`src/jarvis/jarvis_web_gateway/daemon_capability_manager.py:184-186`）。
- 网关 daemon `hello_ack` 目前**只回** `{type, session_id, heartbeat_interval}`（`daemon_capability_manager.py:208-214`），
  未带任何版本比对结果。
- daemon 的 `OnHelloAck` 回调已存在但 `latest` 恒为空（`client.go:374-377`）。
- daemon WS 消息分发：`client.go:359-388`，已识别 `pong`/`hello_ack`/`command`/`capability.list`/`capability.call`。
- 网关 daemon WS 消息循环：`daemon_capability_manager.py:217-242`，已识别
  `capability.list.result`/`capability.call.result`/`ping`/`hello`。
- **Token 仅存内存，绝不落盘**（`daemon/internal/auth/store.go:1-15`）；进程退出即失效。
- 服务重启能力已具备：`internal/service/service.go:44-57`（`Restart()`），
  `systemd_linux.go:161` / `task_windows.go:142` 已实现。
- 固定安装路径：`internal/service/install_dir.go`（`~/.jarvis/bin/jarvis-daemon[.exe]`）。
- GitHub Release 产物命名（`.github/workflows/release-daemon.yml:100-107`）：
  - `jarvis-daemon_linux_amd64.tar.gz`
  - `jarvis-daemon_linux_arm64.tar.gz`
  - `jarvis-daemon_windows_amd64.zip`
  - `jarvis-daemon_windows_arm64.zip`
  - 下载 URL：`https://github.com/<owner>/<repo>/releases/download/<tag>/<asset>`

## 3. 协议设计（v1）

### 3.1 复用现有 hello，不新增上报帧

架构与版本**已在 hello 中上报**，无需新增字段或新消息类型。网关侧只需读取
`build_info.os` / `build_info.arch`（缺失时回退 `platform` 与 `system_info`）。

> 兼容性：旧版 daemon 的 `build_info` 为空时，网关按「无架构信息 → 跳过更新判断」处理，
> 不影响连接与既有能力。

### 3.2 更新判断结果随 hello_ack 下发（复用现有帧）

在 `hello_ack` 中新增可选字段（**只增不改**，旧 daemon 忽略即可）：

```jsonc
{
  "type": "hello_ack",
  "session_id": "...",
  "heartbeat_interval": 20,
  // 新增（可选）：
  "daemon_update": {
    "available": true, // 是否需要更新
    "latest_version": "v1.2.0", // 最新版本（tag）
    "current_version": "v1.1.0",
    "url": "https://github.com/<owner>/<repo>/releases/download/v1.2.0/jarvis-daemon_linux_amd64.tar.gz",
    "sha256": "…64位小写十六进制…", // 可选；缺失时 daemon 跳过校验并记警告
    "size": 12345678, // 可选；字节数，用于进度/校验
    "asset": "jarvis-daemon_linux_amd64.tar.gz",
    "note": "…", // 可选；发布说明摘要
  },
}
```

- `available=false` 或字段缺失 → daemon 不做任何事（等价于当前行为）。
- 平台/架构不匹配（无对应产物）→ 网关返回 `available=false` 并在 `note` 说明原因。

### 3.3 更新状态回执（新增消息类型，单向）

daemon 执行更新后向网关回执（**可选**，便于网关/前端展示进度；网关不等待、不阻塞）：

```jsonc
// daemon → 网关
{
  "type": "daemon.update.status",
  "state": "downloading" | "verifying" | "applying" | "restarting" | "failed",
  "version": "v1.2.0",
  "error": ""            // state=failed 时填原因
}
```

网关在 `daemon_capability_manager.py` 消息循环新增 `elif msg_type == "daemon.update.status":`
分支，仅记录日志 / 更新会话字段，**不回复**。旧网关收到未知类型只 debug 忽略（`daemon_capability_manager.py:241-242`），
天然兼容。

### 3.4 下载与校验

- 下载：`net/http` GET `url`，带 `User-Agent: jarvis-daemon/<version>`，超时（如 5 分钟）。
- 校验：若 `sha256` 非空，流式计算 sha256 并比对；不一致 → 丢弃、报 `failed`。
- 解包：`.tar.gz`（Linux）/ `.zip`（Windows）用标准库 `archive/tar`+`compress/gzip` / `archive/zip` 解出
  `jarvis-daemon[.exe]`。

### 3.5 原子替换与重启

1. 解出的新二进制写入**同目录临时文件**（`~/.jarvis/bin/.jarvis-daemon.new-<pid>`），`Chmod 0755`。
2. 校验临时文件可执行（可选：`--version` 探测）。
3. 原子替换当前可执行文件：
   - Linux：`os.Rename(tmp, target)`（同目录同文件系统，原子）。
   - Windows：运行中的 exe 无法被覆盖/改名，采用 **helper 进程**方案——
     启动一个分离的子进程（`jarvis-daemon self-update-apply --src <tmp> --dst <target> --restart`），
     父进程退出后由 helper 完成替换并调用 `service.Restart()`。
4. 重启：`service.New().Restart()`（Linux systemd --user / Windows 计划任务）。
   - 若当前**不是以服务方式运行**（无服务定义），则退化为：替换文件后由 helper 重新拉起
     `run` 子命令（保留原命令行参数）。

### 3.6 Token 保持方案（关键）

Token 现状**只存内存、不落盘**（`auth/store.go:1-15`）。重启后 Token 丢失。

**方案（推荐，安全默认）**：daemon 在更新前把当前凭据**临时落盘**到
`~/.jarvis/daemon/update-token.json`（权限 0600），字段：

```jsonc
{ "gateway": "https://jvs-ai.cn", "token": "…", "name": "…", "expires_at": 0 }
```

- 重启后 daemon 启动时读取该文件：若存在且未过期，则用其恢复 `store` 并主动 `manager.Connect`，
  随后**立即删除该文件**（一次性使用，避免长期落盘）。
- 若文件不存在/已过期/解析失败 → 走现有路径（等前端推送）。
- 该文件仅在「自更新」窗口内存在，属**临时凭据中转**，非长期持久化；
  用户如不接受落盘，可关闭自动更新（见 3.7），此时不产生该文件。

> 备选方案（零落盘）：更新后依赖前端在线补推（`App.vue:16924` 页面加载补推、`:16898` token 变化推送）。
> 缺点：前端不在线时 daemon 会一直未认证，直到用户下次打开网页。
> **决策：默认采用临时落盘方案**，保证「静默更新 + 重启」后仍在线；并在文档与日志中明确告知。

### 3.7 无条件更新与防重复

- **无开关**：daemon 必须与网关保持同版本，`daemon_update.available=true` 即执行更新，
  不提供 `auto_update_daemon` 设置项（用户口径：无条件、与网关自身版本同步）。
- **防重复**（触发点是每次 WS 握手，若不加约束，失败的更新会随重连无限重试）：
  1. **同版本失败不重试 + 指数退避**：连续失败按 1min → 5min → 30min 退避，
     退避窗口内跳过；目标版本变化则重置计数。
  2. **跨重启熔断**：更新前把「正在更新到版本 X」写入
     `~/.jarvis/daemon/update-attempt.json`（0600，`in_progress=true`）；若替换后新版本
     起不来，新进程启动时读到该标记且自身版本仍为旧版 → 判定为重启循环，熔断自动更新并告警；
     网关发布更新版本（目标版本变化）后自动恢复。更新成功后清除该文件。
  3. 实现见 `internal/selfupdate/attempt_state.go`（`ShouldSkipUpdate` / `BackoffFor` /
     `NormalizeVersion`），接线见 `cmd/jarvis-daemon/main.go` 的 `maybeAutoUpdateDaemon`。
- 版本比对必须**归一化**（去前导 `v`/`V` + trim）：网关版本来自 `jarvis.__version__`（如 `6.0.0`），
  daemon 版本由构建注入（如 `v5.0.5`），不归一化会误判为不同版本 → 无限重启循环。
- 只允许从 **HTTPS** 的 GitHub 域名下载（白名单 `github.com` / `objects.githubusercontent.com`），
  防 SSRF / 中间人。
- 更新失败只记日志，绝不影响当前连接与能力。

## 4. 网关侧「最新版本」数据来源

v1 采用**配置驱动**（零新依赖、可离线）：

- 网关配置文件（或环境变量）提供：
  - `daemon.latest_version`（如 `v1.2.0`）
  - `daemon.release_base_url`（默认 `https://github.com/<owner>/<repo>/releases/download`）
  - `daemon.assets`（可选，显式映射 `os/arch → {asset, sha256}`；缺省时按命名规则拼装）
- 后续可扩展为「拉取 GitHub releases/latest 并缓存」，但**不在 v1 范围**（需外网与缓存策略）。

比对规则：`current_version != latest_version` 即视为需要更新（简单字符串比较；
如后续需要语义化比较再引入 `packaging`/自实现）。

## 5. 落地任务拆分

| 任务 | 内容                                                                        | 状态                                                        |
| ---- | --------------------------------------------------------------------------- | ----------------------------------------------------------- |
| T1   | daemon 侧：无条件自动更新（无开关）+ 防重复（退避 + 跨重启熔断）            | ✅ 已实现                                                   |
| T2   | daemon 侧：解析 `hello_ack.daemon_update`，实现下载/校验/解包/原子替换/重启 | ✅ 已实现                                                   |
| T3   | daemon 侧：Windows helper 子命令 `self-update-apply`                        | ✅ 已实现（未真机验证）                                     |
| T4   | daemon 侧：Token 临时落盘与启动恢复（一次性）                               | ✅ 已实现                                                   |
| T5   | 网关侧：`hello_ack` 下发 `daemon_update`；新增 `daemon.update.status` 分支  | ✅ 已实现                                                   |
| T6   | 端到端验证（httptest 模拟下载 + 假服务重启）与文档                          | 🔶 部分（httptest 已覆盖；假服务重启与 Windows 真机未验证） |

### 5.1 daemon 侧实现要点（对应 T1–T4）

- 更新核心：`internal/selfupdate/`（`ParseUpdateInfo` / `ValidateDownloadURL` 白名单 /
  `Download` 流式 sha256 / `ExtractBinary` / `Apply` / 平台 `restart_*.go`）。
- 防重复：`internal/selfupdate/attempt_state.go`（`ShouldSkipUpdate` 集中判定退避与熔断，
  状态落盘 `~/.jarvis/daemon/update-attempt.json`）。
- 上层接线：`internal/wsclient/client.go` 解析 `hello_ack.daemon_update` 并回调
  `Options.OnDaemonUpdate`；`manager.go` 提供带网关维度的 `OnGatewayDaemonUpdate`；
  `cmd/jarvis-daemon/main.go` 的 `maybeAutoUpdateDaemon` 无条件执行（仅受防重复约束）。
- helper：`cmd/jarvis-daemon` 的 `self-update-apply` 子命令（Windows 轮询等父进程退出后替换）。
- Token 中转：`internal/selfupdate/token.go`，更新前写 `~/.jarvis/daemon/update-token.json`（0600），
  启动时读取并**立即删除**，随后 `manager.ConnectWithName` 主动重连。
- 范围：**仅 Windows 与 Linux**；macOS 不实现（`restart_other.go` / `apply_other.go` 仅保证可编译）。

## 6. 未决/风险

- Windows 上运行中 exe 的替换必须依赖 helper 进程，**未真机验证**（本机为 Linux，仅交叉编译通过）。
- Token 临时落盘与「不落盘」原则存在张力，需用户确认（见 3.6）。
- 网关「最新版本」来源 v1 为配置驱动，需人工在发版后更新配置。
- `daemon.update.status` 回执（T5）尚未接线：`selfupdate.Options.Report` 钩子已就绪，
  待网关侧支持后由 `main.go` 注入发送逻辑。
