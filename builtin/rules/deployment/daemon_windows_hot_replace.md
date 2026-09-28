---
name: daemon_windows_hot_replace
description: 当需要在 Windows 真机上替换正在运行的 jarvis-daemon 可执行文件（热替换/临时版本部署/换新编译产物）时触发。每当用户提及"替换 daemon"、"换 daemon exe"、"更新 daemon 二进制"、"热替换服务"、"临时版本部署"、"self-update-apply"、"helper 替换"时触发。不触发：Linux/macOS 上的 daemon 替换（可直接 rename）；仅编译 daemon 不涉及替换；仅重启 daemon 服务；用 daemon 的 windows.* 能力操作桌面程序（用 jarvis_daemon_windows 规则）。
---

# Windows 上热替换 jarvis-daemon 可执行文件

## 规则简介

在 **Windows 真机**上把正在运行的 `jarvis-daemon.exe` 换成新版本（新编译产物、临时版本、回滚版本），而**不中断服务**。核心难点：**Windows 不允许覆盖或重命名正在运行的 exe**（文件被独占锁），因此必须借一个「父进程退出后再动手」的 helper 子进程完成替换。

本规则只走**一条路径**：**目标机 daemon 执行 `fs.transfer.pull`，从网关节点（Agent 所在节点）拉取编译产物**。

| 路径                             | 新 exe 来源              | 触发/执行方式                                         | 适用场景                                                     |
| -------------------------------- | ------------------------ | ----------------------------------------------------- | ------------------------------------------------------------ |
| **目标机 daemon 从网关节点拉取** | **网关节点上的编译产物** | 目标机 daemon 执行 `fs.transfer.pull`，从网关节点拉取 | Agent 在本节点（网关节点）编译出 exe，目标机是另一台远程机器 |

**为什么只用这条路径**：

- 产物本来就在网关节点上，**天然可达**，不需要额外起 HTTP 服务、不需要暴露 URL。
- `pull` 由 daemon 内部循环分块，**字节不经过你的上下文**，只返回摘要（路径/大小/sha256），可据此校验。
- 全程只用 daemon 能力，不依赖子节点/WSL/SSH。
- 不依赖 GitHub Release（正式发版自更新）或旁路通道（WSL/SSH 直写文件系统）——那些在「本节点编译、目标机远程」场景下都不可用。

**关键概念澄清（易混）**：

- **`fs.transfer.pull` 是「指定远端节点 → 发起方本机」**，**`fs.transfer.push` 是「发起方本机 → 指定远端节点」**。两者都是**站在执行该命令的 daemon 的视角**，且都要求**执行者本机 daemon 已认证网关**。
- **更新 daemon 本身时，`pull`/`push` 不是「更新手段」，而是「文件投递手段」**：真正替换 exe 的永远是「拉起 helper + 自杀」那套（见下方步骤）。
- 本场景产物在**网关节点**、要送进**目标机**，所以由**目标机**发起 `pull`（`node_id` 指向网关节点）。

**Linux/macOS 不适用**：Linux 允许对运行中的二进制直接 `rename` 原子替换，无需 helper。

## 你必须遵守的原则

### 1. 明确「新 exe 来自网关节点」

**必须**先确认：**编译产物已放在网关节点（源节点）的 `~/.jarvis/transfers/` 之下**，且目标机 daemon 已连上网关。

**禁止**：

- **禁止用 `windows.fs.write` 手工 base64 分块灌 exe**——已有 `fs.transfer.pull` 专门做跨机直传，手工分块既笨重又污染上下文。
- **禁止把 `fs.transfer.pull` 当成「更新 daemon 的手段」**——它只是文件投递；替换必须走 helper。
- **禁止在「本机与目标机不共享文件系统」时套用「WSL 里 cp 文件 + schtasks」**——WSL 只有与目标机**同机**时才可用。

### 2. 再弄清「谁在跑、exe 在哪、怎么启动的」

**必须**：

- 先确认目标 exe 的**真实路径**（通常是固定安装路径 `%USERPROFILE%\.jarvis\bin\jarvis-daemon.exe`，见 `daemon/internal/service/install_dir.go`）。
- 确认 daemon **由谁拉起**：`jarvis-daemon install` 装的计划任务（schtasks）还是服务。这决定重启方式。
- 确认当前运行的版本与 PID（daemon 的 `build_info` 会上报 version/commit/pid）。

**禁止**：凭记忆假设路径或启动方式。

### 3. helper 必须从「新文件」启动

**这是最容易踩的坑**：旧 exe 正在运行、被锁，**无法执行**。所以 helper 自身必须从新版本文件的副本启动：

```text
<target>.helper.exe   ← helper 从这份「新文件」副本运行
```

daemon 内置实现（`daemon/internal/selfupdate/apply_windows.go` 的 `SpawnApplyHelper`）正是这么做的：先把新文件复制为 `<target>.helper.exe`，再执行它。

### 4. 不在替换流程里调 `restartService()`

**关键教训（真机踩过）**：不要用 `service.New().Restart()` 来「停掉自己再重启」。

原因：daemon 若由 `schtasks /Run` 启动，**不写 PID 文件**（只有 `service start` 才写）。`Restart()` 的 `Stop()` 读 PID 文件 → 读到失效 PID → 误判「服务未运行」→ 不杀本进程 → `Start()` 又拉起新进程 → 新进程抢 17800 端口失败 → **旧进程一直占着 exe，helper 等 60s 超时替换失败**。

正确做法：**父进程直接 `os.Exit(0)` 退出**（`exitForHelperReplacement()`），把「替换 + 重启」全部交给 helper（helper 侧的 `--restart` → `restartServiceForHelper()`）。

### 5. 写操作前说明意图，事后清理

**必须**：

- 替换前告知用户将替换哪个文件、目标版本、是否重启。
- 替换后清理残留：`.new`、`.helper.exe`、临时脚本、日志。
- 如实区分「已验证」与「未验证」。

## 你必须执行的操作

### 路径：目标机 daemon 从网关节点拉取

**适用**：**编译产物在网关节点上**（典型：Agent 在本节点编译出 exe），目标机是**另一台远程机器**，本节点够不到目标机的文件系统。此时让**目标机 daemon 执行 `fs.transfer.pull`**，从网关节点把产物拉过去。

**前提**：

1. 目标机 daemon **已连上网关**（有有效 token）——`pull` 用 daemon 的网关凭据发起。
2. 产物需先放到**网关节点（源节点）的 `~/.jarvis/transfers/` 之下**——`remote_path` 会被网关收敛到该目录（绝对路径去根保留结构，`app.py` 的 `_resolve_transfer_path`）。
3. `node_id` 填**源节点**（也就是网关节点/master）的 node_id。

**步骤：**

```text
# 1) 找到目标 daemon 会话与 PID
daemon(action="list_sessions")          # 记下目标机 session_id 与 build_info.pid
daemon(action="list_capabilities", session_id="<目标sid>")

# 2) 把编译产物放到网关节点（源节点）的 ~/.jarvis/transfers/ 之下
#    （本节点就是网关节点时，直接 cp 即可；否则用节点直传等方式先送过去）

# 3) 目标机 daemon 执行 pull：从网关节点拉取产物到目标机
daemon(action="call", session_id="<目标sid>", name="fs.transfer.pull",
       params={"gateway": "https://<网关>", "node_id": "<源节点ID，通常为 master>",
               "remote_path": "jarvis-daemon-new.exe",   # 源节点 transfers/ 下的相对路径
               "local_path": "C:\\Users\\<user>\\.jarvis\\bin\\jarvis-daemon-new.exe",
               "mode": "file",
               "chunk_size": 524288})   # 见下方「chunk_size 必填」说明
# 返回摘要的 sha256 应与源节点产物 sha256 一致，据此校验

# 4) 复制为 .helper.exe → 启动 helper（helper 必须从新文件运行）
daemon(action="call", session_id="<目标sid>", name="windows.script.exec",
       params={"interpreter": "powershell", "script":
         "$bin='C:\\Users\\<user>\\.jarvis\\bin'; $new=Join-Path $bin 'jarvis-daemon-new.exe';\n" +
         "$helper=Join-Path $bin 'jarvis-daemon.exe.helper.exe';\n" +
         "Copy-Item $new $helper -Force;\n" +
         "Start-Process -FilePath $helper -ArgumentList 'self-update-apply','--src',$helper,'--dst',(Join-Path $bin 'jarvis-daemon.exe'),'--restart' -WindowStyle Hidden"})

# 5) 让旧 daemon 自杀（helper 会等它退出后替换 + 重启）
daemon(action="call", session_id="<目标sid>", name="windows.process.kill",
       params={"pid": <旧 daemon pid>, "force": true})
```

**方向辨析（务必分清）**：

- `fs.transfer.pull` = **「指定远端节点 → 发起方本机」**；`fs.transfer.push` = **「发起方本机 → 指定远端节点」**。
- 本场景产物在**网关节点**、要送进**目标机**，所以由**目标机**发起 `pull`（`node_id` 指向网关节点）。
- 若产物在**执行方本机**、要送到别的节点，才用 `push`。

**chunk_size 必填（否则大概率 HTTP 413）**：

- 传输按 base64 分块（体积膨胀 4/3）。网关 nginx 默认 `client_max_body_size 1M`，而 daemon 默认 `chunk_size` 为 1MiB → 实际请求体约 1.33MB → 被 nginx 拒绝，报 **HTTP 413**。
- 因此**必须显式传 `chunk_size: 524288`（512KiB）**，两端 push/pull 都要传。daemon 侧允许 1MiB~8MiB（`NormalizeTransferChunkSize`），但受 nginx 限制，512KiB 是安全值。
- 大文件传输耗时较长，`daemon(action="call")` 默认 30s 会超时（实际传输可能仍在继续），请把 `timeout` 放大到 120s 以上。

**helper 子命令签名（精确）：**

```text
jarvis-daemon self-update-apply --src <新exe路径> --dst <目标路径> [--restart]
```

- `--src`：新版本可执行文件路径（helper 自身即从该副本启动）。
- `--dst`：最终要替换到的路径（如 `...\.jarvis\bin\jarvis-daemon.exe`）。
- `--restart`：替换成功后是否重启服务（走 `restartServiceForHelper()`）。
- `--src` 与 `--dst` 缺一即报错。

### 杀进程的可靠手法（WSL 侧权限不足时）

从 WSL 调 `/mnt/c/Windows/System32/taskkill.exe` 杀 daemon 常返回「拒绝访问」（WSL 进程无 Windows 管理员权限）。**可靠做法：用 daemon 自身的 `windows.process.kill` 能力自杀**（daemon 以自身权限运行，能杀掉自己）：

```text
daemon(action="call", session_id="<sid>", name="windows.process.kill",
       params={"pid": <daemon_pid>, "force": true})
```

调用后**会话立即断开**（`daemon session disconnected`），这是**预期现象**，不是失败。随后用 WSL 侧完成 exe 替换 + `schtasks /Run`（这两步不需要 Windows 管理员权限，WSL 直接操作 `/mnt/c/...` 即可）。

**顺序很关键**：`windows.process.kill` 是「最后一条 daemon 命令」——杀完就没有 daemon 通道了，之后所有操作只能走 WSL 侧文件系统 + `schtasks.exe`。

## 验证替换结果

**必须**逐项验证，不能只看「命令返回成功」：

1. **exe 哈希**：新 exe 的 sha256 与本地构建产物一致。

   ```powershell
   Get-FileHash 'C:\Users\<user>\.jarvis\bin\jarvis-daemon.exe' -Algorithm SHA256
   ```

2. **进程**：新 PID 在跑，且监听 17800。
3. **日志**：daemon 日志出现「jarvis-daemon vX.Y.Z 启动」「已注册 N 个平台能力」。
   - **能力数变化是「新能力是否生效」的可靠指标**：对比替换前后 `已注册 N 个平台能力` 的 N。新增能力时 N 应增加（如加 OCR 后 26 → 27），数字不变说明新 exe 没真正生效。
4. **网关**：`list_sessions` 里该会话的 `build_info.version` / `commit` 是新值；`connected`、`token_valid:true`。能力清单里能看到新能力名（如 `ocr.recognize`）。
5. **残留清理**：确认 `.new` / `.helper.exe` 已删除（daemon 启动时会自动 cleanup，可复核）。

**注意**：daemon 的 Token **仅存内存、绝不落盘**，重启即丢（`gateways:[]`）。重启后需补推 Token 才会重连网关，否则日志停在「启动」、无 `connected`/`hello_ack`。补推方式见下方「重启后补推 Token（不必依赖浏览器）」。若替换后 `token_valid:false`，属预期现象，不是替换失败。

### 重启后补推 Token（不必依赖浏览器）

**关键结论**：补推 Token **不需要浏览器**，可直接从命令行 POST daemon 本机接口。前端页面做的也是同一件事（`App.vue` 的 `syncTokenToDaemon` → `POST http://127.0.0.1:17800/api/auth`）。

**接口契约**（`daemon/internal/localapi/server.go` 的 `handleAuth`）：

```text
POST http://127.0.0.1:17800/api/auth
Content-Type: application/json
{ "gateway": "https://jvs-ai.cn:4443", "token": "<有效token>", "name": "<终端名>" }
```

- 无鉴权、无来源限制（`withCORS` 允许任意源），只需 `gateway` + `token` 非空。
- 成功返回 `{"success":true,"status":"connecting",...}`，daemon 随即连接网关。

**在 Windows 侧执行**（WSL 访问不到 Windows 的 127.0.0.1，必须用 Windows 的 PowerShell）：

```powershell
$body = @{ gateway = "https://jvs-ai.cn:4443"; token = "<token>"; name = "SF-PC" } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Method POST -Uri http://127.0.0.1:17800/api/auth -ContentType "application/json" -Body $body
```

**token 从哪来**（关键是找到网关认可的有效凭据）：

1. **优先：master 网关的 `JARVIS_AUTH_TOKEN` 环境变量**。`token_manager.validate_gateway_token` 在 JWT 校验失败后会回退比对 `JARVIS_AUTH_TOKEN`，因此该 UUID 可直接作为有效 Bearer Token。
2. 若 `jvs-ai.cn` 是**本机网关经 nginx 反代**（查 `/etc/nginx/sites-enabled/`：`4443 → 127.0.0.1:8000`），则本机 master 网关认可的 token 即可用于 daemon。
3. 验证 token 有效性：`curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/daemon/sessions`，返回 `{"success":true,...}` 即有效。
4. 兜底：用 `/api/auth/login`（用户名+密码）换取 JWT；或让用户在浏览器侧触发一次补推。

**为什么不要指望浏览器 `reload`**：浏览器扩展的 `reload`/`navigate`/`evaluate` 依赖 CDP debugger attach，**会话被占用时全部超时**（`list_tabs` 仍可用，因为它走扩展 API 不依赖 attach）。此时补推走上述命令行路径更可靠。

## 实践指导

### 常见坑（均为真机实测）

1. **`restartService()` 在 schtasks 启动的 daemon 上会误判**：PID 文件缺失 → 不杀旧进程 → 新旧抢端口 → 替换超时。见「原则 3」。
2. **helper 不能从旧 exe 启动**：旧 exe 被锁，无法执行。必须从新文件副本（`.helper.exe`）启动。
3. **目标被占用时 rename 失败是预期的**，不是错误——这正是要 helper 的原因。
4. **等 60s 是正常的**：helper 轮询等目标释放，最长 60s；GitHub 下载慢时整体耗时可达 1 分钟以上，观察日志需耐心。
5. **残留文件**：helper 替换后**不自清理** `.new` / `.helper.exe`；失败时 `<target>.new` 会保留（供下次替换）。替换成功后需清理，或依赖 daemon 启动时的 cleanup。
6. **`update-attempt.json`**：成功后仍可能留 `in_progress:true`，对「当前版本 == 目标版本」无害（`ShouldSkipUpdate` 自洽）。
7. **跨盘 rename 会失败**：新文件与目标必须**同目录/同盘**，否则先复制到目标同目录再替换。
8. **Token 丢失是预期**：daemon Token 仅存内存，重启即丢，需前端补推。
9. **非管理员会话**：`windows.process.kill` / 服务操作可能因权限失败；daemon 若以管理员运行，kill 它通常也需管理员权限。
10. **WSL 调 `taskkill` 常「拒绝访问」**：WSL 进程无 Windows 管理员权限，`taskkill /F /IM jarvis-daemon.exe` 会失败（但 `tasklist` 能列进程）。改用 daemon 能力 `windows.process.kill` 自杀（见「杀进程的可靠手法」）。
11. **WSL 访问不到 Windows 的 `127.0.0.1`**：WSL2 与 Windows 网络命名空间隔离，在 WSL 里 `curl http://127.0.0.1:17800` 不通。探测 Windows 侧本机服务（daemon 本地 API）必须用 Windows 的 PowerShell/curl，或直接读 Windows 侧日志文件。

### 未验证 / 风险项（如实标注）

- Windows 真机上「目标 exe 被占用 → rename 失败 → 删旧 → 重试」的**完整路径**仅在真机跑通过 helper 分支；直接 rename 失败后的删旧重试分支未单独真机验证。
- **本规则路径（`fs.transfer.pull` 从网关节点拉取 exe）的完整链路未真机验证**：能力实现与单元测试见 `daemon/internal/capability/transfer_remote.go` 与 `transfer_remote_test.go`；`pull` 的 `remote_path` 收敛规则见网关 `app.py` 的 `_resolve_transfer_path`。首次使用请先确认源节点 node_id 与产物落点。
- helper 替换 + 重启的链路已在真机完整验证（daemon 自更新场景，日志序列：downloading → verifying → applying → 启动 helper → done → restarting → 启动/connected）。

## 自检清单

- [ ] 是否已把编译产物放到**网关节点（源节点）的 `~/.jarvis/transfers/` 之下**？
- [ ] `fs.transfer.pull` 的 `node_id` 是否填的是**源节点**（网关节点/master）？
- [ ] 是否用 `pull` 返回摘要的 sha256 与源产物核对过？
- [ ] 目标机 daemon 是否已连上网关（有 token）？
- [ ] 是否确认了目标 exe 的真实路径与启动方式（schtasks / service）？
- [ ] helper 是否从**新文件副本**（`.helper.exe`）启动，而非旧 exe？
- [ ] 是否**没有**在替换流程里调 `restartService()`（改由 helper 负责重启）？
- [ ] 新文件是否与目标**同目录/同盘**？
- [ ] 是否用 sha256 + 进程 + 日志 + 网关 `build_info` 验证了替换结果？
- [ ] 若本次新增了能力，是否核对了「已注册 N 个平台能力」的 N 有变化？
- [ ] 重启后是否补推了 Token（命令行 POST `/api/auth` 即可，不必依赖浏览器）？会话是否 `connected`？
- [ ] 是否清理了 `.new` / `.helper.exe` / 临时脚本等残留？
- [ ] 是否如实区分了「已验证」与「未验证」？
