---
name: daemon_windows_hot_replace
description: 当需要在 Windows 真机上替换正在运行的 jarvis-daemon 可执行文件（热替换/临时版本部署/换新编译产物）时触发。每当用户提及"替换 daemon"、"换 daemon exe"、"更新 daemon 二进制"、"热替换服务"、"临时版本部署"、"self-update-apply"、"helper 替换"时触发。不触发：Linux/macOS 上的 daemon 替换（可直接 rename）；仅编译 daemon 不涉及替换；仅重启 daemon 服务；用 daemon 的 windows.* 能力操作桌面程序（用 jarvis_daemon_windows 规则）。
---

# Windows 上热替换 jarvis-daemon 可执行文件

## 规则简介

在 **Windows 真机**上把正在运行的 `jarvis-daemon.exe` 换成新版本（新编译产物、临时版本、回滚版本），而**不中断服务**。核心难点：**Windows 不允许覆盖或重命名正在运行的 exe**（文件被独占锁），因此必须借一个「父进程退出后再动手」的 helper 子进程完成替换。

本规则覆盖两条路径：

- **A. 自动更新 helper 机制**（daemon 内置）：daemon 自更新时自动走此路径。
- **B. 手动临时替换**（经网关 daemon 能力）：用户不在机器旁、需要立刻换上某个本地编译产物时用。

**Linux/macOS 不适用**：Linux 允许对运行中的二进制直接 `rename` 原子替换，无需 helper。

## 你必须遵守的原则

### 1. 先弄清「谁在跑、exe 在哪、怎么启动的」

**必须**：

- 先确认目标 exe 的**真实路径**（通常是固定安装路径 `%USERPROFILE%\.jarvis\bin\jarvis-daemon.exe`，见 `daemon/internal/service/install_dir.go`）。
- 确认 daemon **由谁拉起**：`jarvis-daemon install` 装的计划任务（schtasks）还是服务。这决定重启方式。
- 确认当前运行的版本与 PID（daemon 的 `build_info` 会上报 version/commit/pid）。

**禁止**：凭记忆假设路径或启动方式。

### 2. helper 必须从「新文件」启动

**这是最容易踩的坑**：旧 exe 正在运行、被锁，**无法执行**。所以 helper 自身必须从新版本文件的副本启动：

```text
<target>.helper.exe   ← helper 从这份「新文件」副本运行
```

daemon 内置实现（`daemon/internal/selfupdate/apply_windows.go` 的 `SpawnApplyHelper`）正是这么做的：先把新文件复制为 `<target>.helper.exe`，再执行它。

### 3. 不在替换流程里调 `restartService()`

**关键教训（真机踩过）**：不要用 `service.New().Restart()` 来「停掉自己再重启」。

原因：daemon 若由 `schtasks /Run` 启动，**不写 PID 文件**（只有 `service start` 才写）。`Restart()` 的 `Stop()` 读 PID 文件 → 读到失效 PID → 误判「服务未运行」→ 不杀本进程 → `Start()` 又拉起新进程 → 新进程抢 17800 端口失败 → **旧进程一直占着 exe，helper 等 60s 超时替换失败**。

正确做法：**父进程直接 `os.Exit(0)` 退出**（`exitForHelperReplacement()`），把「替换 + 重启」全部交给 helper（helper 侧的 `--restart` → `restartServiceForHelper()`）。

### 4. 写操作前说明意图，事后清理

**必须**：

- 替换前告知用户将替换哪个文件、目标版本、是否重启。
- 替换后清理残留：`.new`、`.helper.exe`、临时脚本、日志。
- 如实区分「已验证」与「未验证」。

## 你必须执行的操作

### 路径 A：自动更新 helper 机制（daemon 内置）

daemon 收到网关下发的 `daemon_update` 后自动执行，日志序列（真机已验证）：

```text
downloading → verifying → applying → 启动 helper(pid) → done → restarting
→ 「jarvis-daemon vX.Y.Z 启动」→ connected → build_info: version=vX.Y.Z → hello_ack
```

内部流程：

1. 下载新 exe（`net/http`，UA=`jarvis-daemon/<ver>`，超时 5min）+ sha256 流式校验。
2. 解包（tar.gz / zip）到同目录临时文件，`Chmod 0755`。
3. 尝试直接 `os.Rename` 替换；**成功即结束**（Linux 或 Windows 未被占用时）。
4. 失败（Windows 目标被占用）→ 保留新文件为 `<target>.new` → `SpawnApplyHelper`：
   - 复制新文件为 `<target>.helper.exe`；
   - 以 `DETACHED_PROCESS | CREATE_NO_WINDOW` 分离启动 helper；
   - 父进程 `exitForHelperReplacement()` 退出。
5. helper 轮询等目标释放（最多 60s）→ `selfupdate.Apply(src, dst)` → 可选 `--restart` 重启服务。

### 路径 B：手动临时替换（经网关 daemon 能力）

适用：用户不在机器旁，需把某个**本地编译产物**立刻换上去。

**步骤：**

```text
# 1) 找到目标 daemon 会话
daemon(action="list_sessions")
daemon(action="list_capabilities", session_id="<sid>")

# 2) 把新 exe 传到真机（大文件用分块传输，见 jarvis_daemon_windows 规则）
#    上传到目标同目录，避免跨盘 rename 失败：
#    C:\Users\<user>\.jarvis\bin\jarvis-daemon-new.exe

# 3) 复制为 helper 并从它启动（helper 必须从新文件运行）
daemon(action="call", session_id="<sid>", name="windows.script.exec",
       params={"interpreter": "powershell", "script":
         "Copy-Item 'C:\\Users\\<user>\\.jarvis\\bin\\jarvis-daemon-new.exe' " +
         "'C:\\Users\\<user>\\.jarvis\\bin\\jarvis-daemon.exe.helper.exe' -Force; " +
         "Start-Process -FilePath 'C:\\Users\\<user>\\.jarvis\\bin\\jarvis-daemon.exe.helper.exe' " +
         "-ArgumentList 'self-update-apply','--src','C:\\Users\\<user>\\.jarvis\\bin\\jarvis-daemon.exe.helper.exe'," +
         "'--dst','C:\\Users\\<user>\\.jarvis\\bin\\jarvis-daemon.exe','--restart' -WindowStyle Hidden"})

# 4) 让旧 daemon 自杀（helper 会等它退出后替换）
daemon(action="call", session_id="<sid>", name="windows.process.kill",
       params={"pid": <旧 daemon pid>, "force": true})
```

**helper 子命令签名（精确）：**

```text
jarvis-daemon self-update-apply --src <新exe路径> --dst <目标路径> [--restart]
```

- `--src`：新版本可执行文件路径（helper 自身即从该副本启动）。
- `--dst`：最终要替换到的路径（如 `...\.jarvis\bin\jarvis-daemon.exe`）。
- `--restart`：替换成功后是否重启服务（走 `restartServiceForHelper()`）。
- `--src` 与 `--dst` 缺一即报错。

### 备选：直接停服务替换（可接受短暂中断时）

若可接受停机，最简手法（真机验证过）：

```text
schtasks /End /TN jarvis-daemon
taskkill /F /IM jarvis-daemon.exe
cp <新exe> C:\Users\<user>\.jarvis\bin\jarvis-daemon.exe
# 删除残留
del C:\Users\<user>\.jarvis\bin\jarvis-daemon.exe.new
del C:\Users\<user>\.jarvis\bin\jarvis-daemon.exe.helper.exe
schtasks /Run /TN jarvis-daemon
```

## 验证替换结果

**必须**逐项验证，不能只看「命令返回成功」：

1. **exe 哈希**：新 exe 的 sha256 与本地构建产物一致。

   ```powershell
   Get-FileHash 'C:\Users\<user>\.jarvis\bin\jarvis-daemon.exe' -Algorithm SHA256
   ```

2. **进程**：新 PID 在跑，且监听 17800。
3. **日志**：daemon 日志出现「jarvis-daemon vX.Y.Z 启动」「已注册 N 个平台能力」。
4. **网关**：`list_sessions` 里该会话的 `build_info.version` / `commit` 是新值；`connected`、`token_valid:true`。
5. **残留清理**：确认 `.new` / `.helper.exe` 已删除（daemon 启动时会自动 cleanup，可复核）。

**注意**：daemon 的 Token **仅存内存、绝不落盘**，重启即丢（`gateways:[]`）。重启后需前端页面补推 Token（页面加载/Token 变化时 `syncTokenToDaemon`），或从浏览器侧触发一次。若替换后 `token_valid:false`，属预期现象，不是替换失败。

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

### 未验证 / 风险项（如实标注）

- Windows 真机上「目标 exe 被占用 → rename 失败 → 删旧 → 重试」的**完整路径**仅在真机跑通过 helper 分支；直接 rename 失败后的删旧重试分支未单独真机验证。
- 手动路径 B 的 PowerShell 单行命令需按实际用户名/路径替换，未逐字真机验证（自动路径 A 已完整验证）。

## 自检清单

- [ ] 是否确认了目标 exe 的真实路径与启动方式（schtasks / service）？
- [ ] helper 是否从**新文件副本**（`.helper.exe`）启动，而非旧 exe？
- [ ] 是否**没有**在替换流程里调 `restartService()`（改由 helper 负责重启）？
- [ ] 新文件是否与目标**同目录/同盘**？
- [ ] 是否用 sha256 + 进程 + 日志 + 网关 `build_info` 验证了替换结果？
- [ ] 是否清理了 `.new` / `.helper.exe` / 临时脚本等残留？
- [ ] 是否如实区分了「已验证」与「未验证」？
