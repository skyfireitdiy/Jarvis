---
name: jarvis_daemon_windows
description: 当需要通过 jarvis-daemon 的 windows.* 能力操作用户 Windows 真机上的桌面程序时触发。每当用户提及"操作Windows程序"、"控制桌面应用"、"windows.window"、"windows.input"、"daemon 能力"、"真机自动化"、"点击窗口"、"给应用输入文字"时触发。不触发：用 jw/jarvis-windows CLI(pywinauto) 操作（用 jarvis_windows_cli）；Linux/macOS 桌面操作；仅执行命令行脚本不涉及 GUI；Web 页面自动化（用 jarvis_browser_cli 或 browser_ext_usage）。
---

# jarvis-daemon Windows 能力操作指南

## 规则简介

`jarvis-daemon` 是运行在用户真机上的常驻守护进程，通过 `daemon` 工具暴露 `windows.*` 能力，可在**用户自己的 Windows 机器**上启动/操作桌面程序、模拟鼠标键盘、读写文件剪贴板、执行 PowerShell 脚本。

它与 `jw`（jarvis-windows，基于 pywinauto 的 Python CLI）是**两条独立路径**：

- `daemon`：Go 实现的守护进程，能力经 `daemon` 工具调用，**不依赖 pywinauto**，可操作真机（含用户已登录的桌面会话）。
- `jw`：Python CLI，需在 Windows 上直接跑命令。

**能用 `daemon` 就不要用 `jw`**（daemon 面向真机、无需额外安装、能力更全）。

## 你必须遵守的原则

### 1. 先发现，再调用

**必须**：

- 任何操作前先调 `daemon(action="list_sessions")` 拿 `session_id`（除 `list_sessions` 外所有调用都必填）。
- 调 `daemon(action="list_capabilities", session_id=...)` 确认目标机器上**实际注册了哪些能力及其参数**——不同平台/版本能力清单不同。
- **禁止**凭猜测直接调用未确认的能力名或参数。

**示例：**

```text
daemon(action="list_sessions")
daemon(action="list_capabilities", session_id="<sid>")
daemon(action="call", session_id="<sid>", name="windows.window.list", params={})
```

### 2. 操作的是用户真机，写操作要谨慎

**必须**：

- 明确告知用户将要执行的写操作（点击、输入、启动/关闭程序、改剪贴板、写文件）。
- 高风险操作（关闭窗口、结束进程、写系统文件、改服务）执行前先说明意图。

**禁止**：

- 未经确认就结束用户进程或关闭用户窗口。
- 在用户机器上留下临时文件——**任务结束必须清理**（见「你必须执行的操作」第 6 节）。

### 3. 用事实验证，不臆测 UI 状态

**必须**：

- 每次操作后用可观测手段验证结果（窗口标题、窗口列表、剪贴板内容、进程状态、OCR 文本）。
- 无法验证时如实说明「未验证」，**禁止**声称已完成。

**禁止**：

- 假设「点了应该就生效」而不复核。
- 把「工具返回成功」等同于「业务目标达成」。

### 4. 平台专有约定

**必须**：

- 能力名带平台前缀（`windows.*`），调用前确认平台匹配。
- 涉及图形环境的能力（GUI 类）在无桌面会话时会失败，需先确认有可用桌面。

## 你必须执行的操作

### 1. 建立会话与能力清单

```text
# 1) 拿 session_id（含 system_info：hostname/os/user/exe_path/commit）
daemon(action="list_sessions")

# 2) 看这台机器有哪些能力、各自参数
daemon(action="list_capabilities", session_id="<sid>")
```

从 `list_sessions` 的 `system_info` 确认：主机名、OS 版本、当前用户、是否管理员（`isAdmin` 需另查）。

### 2. 按任务选能力

| 目标                              | 能力                                   | 关键参数                                          |
| --------------------------------- | -------------------------------------- | ------------------------------------------------- |
| 列出窗口（拿 window_id/pid/标题） | `windows.window.list`                  | `filter`（**匹配标题，不匹配进程名**）            |
| 聚焦窗口                          | `windows.window.focus`                 | `window_id`（**HWND 十六进制串**）或 `title`      |
| 关闭窗口                          | `windows.window.close`                 | `window_id`                                       |
| 点击                              | `windows.input.click`                  | `x`/`y`（**屏幕绝对坐标**）、`button`、`count`    |
| 按键组合                          | `windows.input.keys`                   | `keys`（如 `ctrl+f`、`Return`、`ctrl+alt+Right`） |
| 输入文本                          | `windows.input.type`                   | `text`、`delay_ms`                                |
| 剪贴板读写                        | `windows.clipboard.get` / `.set`       | `text`                                            |
| 跑 PowerShell/cmd                 | `windows.script.exec`                  | `script`、`interpreter`、`timeout_ms`             |
| 列进程                            | `windows.process.list`                 | `filter`（匹配进程名或 PID）                      |
| 结束进程                          | `windows.process.kill`                 | `pid`、`force`                                    |
| 列已安装应用                      | `windows.app.list`                     | `filter`（名称或发布者）                          |
| 文件读写列                        | `windows.fs.read` / `.write` / `.list` | `path` 等                                         |
| 大文件分块传输                    | `windows.fs.transfer.*`                | `path`、`offset`、`length`、`data`、`sha256`      |
| 服务管理                          | `windows.service.*`                    | `unit`（需管理员权限才能启停）                    |
| 截图                              | `windows.screenshot`                   | `path`（**只截主屏，返回体不含图像**）            |
| 系统信息                          | `windows.system.info`                  | 无                                                |

### 3. 文件传输（大文件 / 双向）

`windows.fs.read` / `.write` 面向「看内容」，单次上限 8 MiB，不适合搬文件。
搬文件（尤其是二进制、大文件、需要校验完整性）请用 `windows.fs.transfer.*` 四个能力。
Linux 侧完全对称，把前缀换成 `linux.` 即可（参数与返回字段逐字一致）。

| 能力                         | 用途                  | 关键参数                                       | 主要返回字段                                                  |
| ---------------------------- | --------------------- | ---------------------------------------------- | ------------------------------------------------------------- |
| `windows.fs.transfer.stat`   | 传输前查元信息 / 比对 | `path`                                         | `exists`、`size`、`mtime`、`sha256`、`is_dir`                 |
| `windows.fs.transfer.read`   | 分块读（下载）        | `path`、`offset`、`length`                     | `data`（base64）、`bytes_read`、`eof`、`chunk_sha256`、`size` |
| `windows.fs.transfer.write`  | 分块写（上传 / 续传） | `path`、`offset`、`data`（base64）、`truncate` | `written_bytes`、`size`、`truncated`                          |
| `windows.fs.transfer.verify` | 落盘后校验完整性      | `path`、`sha256`                               | `match`、`size`、`actual_sha256`                              |

**约束（必须记住）：**

- 单文件上限 **512 MiB**；`stat` / `read` / `write` / `verify` 都会校验，超限直接报错。
- 单块上限 **8 MiB**，默认块 **1 MiB**（`length` 不传即 1 MiB）。
- `offset` 不能为负。`offset` 超出文件尾**不报错**，返回 `bytes_read=0` + `eof=true`。
- `length<=0` 表示「读到文件尾」；`length` 超过剩余部分时自动取剩余并置 `eof=true`。
- `write` 的 `data` 是 **base64**；首块传 `truncate=true` 清空已有内容，后续块传 `truncate=false`。
- 断点续传：从 `stat` 拿到已传大小，把 `offset` 设到那里继续写即可（`truncate=false`）。

**推荐流程（下载：真机 → 本地）：**

```text
# 1) 先看文件是否存在、多大、校验和是多少
daemon(action="call", session_id="<sid>", name="windows.fs.transfer.stat",
       params={"path": "C:\\data\\big.bin"})

# 2) 按 1 MiB 循环分块读，直到 eof=true
daemon(action="call", session_id="<sid>", name="windows.fs.transfer.read",
       params={"path": "C:\\data\\big.bin", "offset": 0, "length": 1048576})
#    → 拿到 data(base64) 后本地拼接，offset += bytes_read，重复直到 eof

# 3) 本地拼完后，用第 1 步的 sha256 比对；或反过来对真机文件调 verify
daemon(action="call", session_id="<sid>", name="windows.fs.transfer.verify",
       params={"path": "C:\\data\\big.bin", "sha256": "<第1步拿到的 sha256>"})
```

**推荐流程（上传：本地 → 真机）：**

```text
# 1) 先 stat 目标路径，确认是否已存在部分内容（决定 offset 起点）
daemon(action="call", session_id="<sid>", name="windows.fs.transfer.stat",
       params={"path": "C:\\data\\upload.bin"})

# 2) 首块 truncate=true，后续块 truncate=false 并按 offset 定位
daemon(action="call", session_id="<sid>", name="windows.fs.transfer.write",
       params={"path": "C:\\data\\upload.bin", "offset": 0,
               "data": "<base64 首块>", "truncate": true})
daemon(action="call", session_id="<sid>", name="windows.fs.transfer.write",
       params={"path": "C:\\data\\upload.bin", "offset": 1048576,
               "data": "<base64 第二块>", "truncate": false})

# 3) 传完 verify 校验
daemon(action="call", session_id="<sid>", name="windows.fs.transfer.verify",
       params={"path": "C:\\data\\upload.bin", "sha256": "<本地算出的 sha256>"})
```

**注意：**

- 传输完的临时文件必须清理（见「你必须执行的操作」第 6 节）。
- 上层不做 `pull`/`push` 封装，分块循环由调用方控制——这样断点续传与进度上报都更灵活。
- 超过 512 MiB 的文件应改用独立通道（如 `windows.script.exec` 调 `curl`/`scp`），不要用本能力硬传。

### 4. 定位 UI 元素（核心方法论）

按以下顺序降级尝试，不要一上来就盲点坐标。

#### ① UIAutomation 枚举控件树（首选）

用 `windows.script.exec` 跑 PowerShell + `UIAutomationClient`：

```powershell
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$root=[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]0xXXXX)
$all=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
foreach($e in $all){ $c=$e.Current; $r=$c.BoundingRectangle
  Write-Output "$($c.ControlType.ProgrammaticName) name='$($c.Name)' aid='$($c.AutomationId)' rect=$([int]$r.X),$([int]$r.Y),$([int]$r.Width),$([int]$r.Height)" }
```

拿到控件的 `Name`/`AutomationId`/`BoundingRectangle` 后，用 `input.click` 点其中心。

#### ② CEF/Electron 应用：UIA 无效，改用 Windows OCR

若 UIA 只返回 3~5 个空 `Pane`（`CefBrowserWindow` / `Chrome_WidgetWin_0` / `Chrome_RenderWidgetHostHWND`），说明是 **CEF/Chromium 渲染**，UIA 拿不到内部控件。此时用**系统 OCR** 对窗口截图做文字识别，得到「文字 + 边界框坐标」：

```powershell
# 前提：系统已装中文 OCR 语言包，先查：
[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages

# 截图窗口区域 → WinRT OCR 识别 → 输出每行文字及坐标
# 关键点：WinRT 异步要 AsTask 桥接；BoundingRect 字段用 [double] 强转
```

拿到 OCR 行的 `x/y/x2/y2`（**窗口相对坐标**）后，加窗口原点即得屏幕坐标，再用 `input.click`。

#### ③ 坐标探测（兜底）

前两者都不可行时，用「点击 → 输入 → Ctrl+A/Ctrl+C → 读剪贴板」验证是否点中了输入框；用窗口标题/进程状态变化判断操作是否生效。**每次只变一个变量**，避免多点连击。

### 5. 验证操作结果

常用判据：

- **窗口标题变化**：很多播放器/编辑器把「当前文档/歌曲」写进标题，是最廉价的判据。
- **`windows.window.list`**：确认窗口出现/消失/标题变化（注意 `filter` 匹配的是**标题**）。
- **剪贴板**：`input.type` 输入后 `ctrl+a`/`ctrl+c` + `clipboard.get` 读回，验证输入是否真的进了目标控件。
- **进程**：`windows.process.list` 确认启动/退出。
- **OCR**：重新截图 OCR，看界面文字是否如预期。

### 6. 清理临时产物

**必须**：任务结束删除本次在用户机器上产生的所有临时文件（截图、脚本、临时数据）。

```powershell
Remove-Item 'D:\jarvis-*.png','D:\jarvis-*.ps1' -Force -ErrorAction SilentlyContinue
```

## 实践指导

### 常见坑（均为真机实测）

1. **窗口标题 ≠ 应用名**：播放器/浏览器标题是「当前内容」，如网易云音乐标题是正在播放的歌名，不含「网易云音乐」。用 `window.list` 全量列出后按 `pid` 或标题特征找，**不要**用应用名去 `filter`。
2. **`window_id` 是 HWND，不是 PID**：传 PID 会报「窗口不存在」。HWND 用十六进制串（如 `0x003A0BB0`）。
3. **`input.type` 对 CEF 有效**：它走 `keybd_event` + Unicode 扫描码，能正确输入中文到 Chromium 应用。**但必须先点中真正的输入框**——否则文字进了别处。
4. **快捷键可能被应用拦截**：CEF 应用常吞掉 `Ctrl+F` 等系统级快捷键，**优先用「点击输入框」而非快捷键**。
5. **不要用「截图 + 试图读图」定位 UI**：`windows.screenshot` 返回体不含图像内容，`fs.read` 读回 base64 也无法直接理解。**截图只作为 OCR 的输入**，不要指望直接看图。
6. **UIA 对 CEF 无效**：见「定位 UI」②。
7. **`Get-Process` 的 `MainWindowTitle` 只给一个主窗口**：应用有多个窗口时可能拿到错的（如拿到 "SystemHint" 而非播放窗口）。用 `windows.window.list` 更可靠。
8. **PowerShell 里 `$pid` 是只读变量**：写脚本时不要用 `$pid` 作变量名。
9. **WinRT 调用需 AsTask 桥接**：PowerShell 调 `Windows.Media.Ocr` 等 WinRT API 时，异步操作必须用 `AsTask` 泛型方法 + `.Wait()` 取结果。
10. **`service.start/stop/restart` 需管理员**：非管理员会话下会失败，属环境限制，**不要标为「能力已验证通过」**。
11. **`windows.app.list` 只覆盖注册表桌面应用**（不含 UWP）；`screenshot` 只截主屏；`fs.*` 无路径沙箱。

### 找应用安装路径

`windows.app.list` 拿不到路径时，读注册表 Uninstall 项：

```powershell
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
                 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
                 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' |
  Where-Object DisplayName -like '*关键词*' |
  Select-Object DisplayName,DisplayIcon,InstallLocation,UninstallString
```

## 自检清单

- [ ] 是否先 `list_sessions` 拿了 `session_id`，并 `list_capabilities` 确认了能力？
- [ ] 是否用 UIA → OCR → 坐标探测的顺序定位 UI，而非盲目点击？
- [ ] 每次操作后是否用可观测手段（标题/窗口列表/剪贴板/进程/OCR）验证了结果？
- [ ] 写操作前是否向用户说明了意图？
- [ ] 是否清理了本次在用户机器上产生的临时文件？
- [ ] 报告中是否如实区分了「已验证」与「未验证」的项？
