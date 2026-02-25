# Windows 程序操作工具功能规范

## 功能概述

提供一个基于 pywinauto 的 Windows 桌面程序自动化 CLI 工具，支持启动应用、连接到已有窗口、执行点击、输入、截图、获取控件树等操作。与 jarvis_browser 类似，通过 execute_script 调用，适用于需要多步交互的 Windows 原生应用场景。

**使用场景**：

- 自动化 Windows 原生应用（记事本、资源管理器、设置等）
- 需要多步骤交互的桌面程序操作
- 批量执行重复性 UI 操作
- AI Agent 通过工具链操控 Windows 应用

**平台限制**：仅支持 Windows 操作系统。

## 接口定义

### CLI 入口

```bash
# 通过 Python 模块调用
python -m jarvis.jarvis_windows.cli <command> [options]

# 通过入口点（安装后）
jw <command> [options]
jarvis-windows <command> [options]
```

### 命令列表

| 命令 | 描述 |
|------|------|
| `start` | 启动应用程序 |
| `connect` | 连接到已运行的窗口 |
| `list` | 列出当前管理的应用会话 |
| `list-windows` | 列举可见窗口（title、pid、handle），便于 connect |
| `close` | 关闭/断开应用会话 |
| `click` | 点击控件（通过标题、auto_id、索引等） |
| `double-click` | 双击控件 |
| `right-click` | 右键点击控件 |
| `hover` | 将鼠标移动到控件中心或指定坐标 |
| `drag` | 拖拽鼠标（从起点拖到终点） |
| `type` | 向控件输入文本 |
| `type-keys` | 发送键盘按键序列 |
| `screenshot` | 截取窗口截图 |
| `get-tree` | 获取窗口控件树结构 |
| `menu` | 执行菜单操作 |

### config 子命令（系统配置）

| 命令 | 描述 |
|------|------|
| `config theme` | 切换深色/浅色主题（dark \| light \| toggle） |
| `config power-plan` | 列出或切换电源计划（list \| set） |
| `config proxy` | 获取或设置系统代理（get \| enable \| disable \| set） |
| `config screen-timeout` | 获取或设置屏幕关闭超时（get \| set） |
| `config remote-desktop` | 启用/禁用远程桌面（enable \| disable \| get，需管理员） |
| `config startup` | 列出或启用/禁用当前用户启动项（list \| enable \| disable） |

### 通用参数

- `--app-id`：应用会话 ID（默认 `"default"`），用于区分多个连接
- `--backend`：pywinauto 后端，`uia`（默认）或 `win32`。连接失败时自动尝试另一后端

## 输入输出说明

### 返回值格式

所有命令以 JSON 格式输出到 stdout：

```python
{
    "success": bool,      # 操作是否成功
    "stdout": str,        # 成功消息或操作结果
    "stderr": str         # 错误消息或空字符串
}
```

失败时 `success` 为 `false`，`stderr` 包含错误描述，CLI 以非零退出码退出。

### 命令参数详述

#### start

启动应用程序。

- `--path`（必需）：可执行文件路径，如 `notepad.exe`、`C:\Program Files\app\app.exe`
- `--args`（可选）：启动参数，如 `"C:\file.txt"`
- `--timeout`（可选）：启动超时秒数，默认 30

#### connect

连接到已运行的窗口。

- `--process`：进程名或路径，如 `notepad.exe`
- `--title`：窗口标题（支持部分匹配）
- `--pid`：进程 ID

至少需要 `process`、`title`、`pid` 之一。

#### list

列出当前通过工具管理（start/connect）的应用会话。

返回：app_id、进程名、窗口标题、状态。

#### list-windows

列举当前可见的顶层窗口。

- `--backend`：uia（默认）或 win32
- `--title`：按窗口标题过滤（子串匹配）
- `--limit`：最多列出数量，默认 50

返回：每项含 `title`、`pid`、`handle`，可用于 connect 的 `--title` 或 `--pid`。

#### close

关闭会话并结束进程。

- `--kill` / `--no-kill`：是否结束进程，默认 kill（结束进程）。使用 `--no-kill` 仅断开会话、不结束进程

#### click

点击控件。

- `--control`：控件标识，可为标题文本、AutomationId、或 `title_regex=模式`
- `--menu`：菜单路径，如 `文件(&F)->打开(&O)`（用于菜单点击）
- `--index`：同类型控件中的索引（从 0 开始）

#### double-click

双击控件。

- `--control`（必需）：控件标识
- `--index`（可选）：同类型控件中的索引

#### right-click

右键点击控件。

- `--control`（可选）：控件标识，不指定则对窗口本身右键点击
- `--index`（可选）：同类型控件中的索引

#### hover

将鼠标移动到目标位置。

- `--control`（可选）：移至控件中心
- `--x`、`--y`（可选）：屏幕坐标，与 `--control` 二选一

#### drag

拖拽鼠标。

- `--from-control`（可选）：起始控件，不指定则从窗口中心或 `--from-x --from-y` 开始
- `--from-x`、`--from-y`（可选）：起始屏幕坐标
- `--to-control`（可选）：目标控件
- `--to-x`、`--to-y`（可选）：目标屏幕坐标，与 `--to-control` 二选一
- `--button`（可选）：鼠标按键，默认 `left`，可选 `right`、`middle`

#### type

向目标控件输入文本（清空后输入）。

- `--control`（可选）：目标控件，不指定则为当前焦点
- `--text`（必需）：要输入的文本

#### type-keys

发送键盘按键序列（支持 `pywinauto` 的 `type_keys` 语法）。

- `--keys`（必需）：按键序列，如 `^a`（Ctrl+A）、`{ENTER}`

#### screenshot

截取窗口截图。

- `--path`（可选）：保存路径，默认临时目录下带时间戳的文件

#### get-tree

获取窗口或控件的 UI 树结构（用于生成选择器）。

- `--depth`（可选）：遍历深度，默认 3
- `--control`（可选）：从指定控件开始，不指定则为根窗口

#### config theme

切换系统/应用深色或浅色主题。

- 参数：`dark` \| `light` \| `toggle`

#### config power-plan

列出或切换电源计划。

- 参数：`list` \| `set`
- `--id`：电源方案 GUID（set 时必需，可通过 list 获取）

#### config proxy

获取或设置系统代理。

- 参数：`get` \| `enable` \| `disable` \| `set`
- `--server`：代理地址，如 `127.0.0.1:7890`
- `--bypass`：绕过列表，如 `localhost;127.*`

#### config screen-timeout

获取或设置屏幕关闭超时（当前电源计划）。

- 参数：`get` \| `set`
- `--minutes`：熄屏分钟数，0 表示从不

#### config remote-desktop

启用/禁用远程桌面（需管理员权限）。

- 参数：`enable` \| `disable` \| `get`

#### config startup

列出或启用/禁用当前用户「启动」文件夹中的启动项。

- 参数：`list` \| `enable` \| `disable`
- `--name`：启动项文件名，如 `MyApp.lnk`（enable/disable 时必需）

## 功能行为

### 1. start

- 使用 `Application(backend).start(path, args)` 启动进程
- 将应用句柄存入会话字典，键为 `app_id`
- 若 `app_id` 已存在，先关闭旧会话再创建
- 等待主窗口就绪（可选 `timeout`）

### 2. connect

- 使用 `Application(backend).connect(process=...|title=...|process=pid)` 连接
- 存入会话字典
- 若未找到匹配窗口，返回错误

### 3. list

- 返回所有 `app_id` 对应的进程名、窗口标题

### 3a. list-windows

- 使用 `Desktop(backend).windows()` 遍历可见顶层窗口
- 返回每项 `title`、`pid`、`handle`
- 支持 `--title` 子串过滤、`--limit` 数量限制

### 4. close

- 从会话移除；若 `kill=true`，调用 `app.kill()`
- 未找到会话时视为已关闭，返回成功

### 5. click

- 根据 `control`、`menu`、`index` 解析目标
- 调用 `element.click()` 或 `menu_select()`
- 控件不存在或不可见时返回错误

### 5a. double-click

- 根据 `control`、`index` 定位控件
- 调用 `element.double_click()`

### 5b. right-click

- 根据 `control`、`index` 定位控件（可选）
- 调用 `element.right_click()`

### 5c. hover

- 若有 `--control`，计算控件中心屏幕坐标并 `move_mouse(coords, absolute=True)`
- 若有 `--x`、`--y`，直接移动至该屏幕坐标

### 5d. drag

- 确定起始坐标：`--from-control` 的控件中心，或 `--from-x --from-y`，否则使用窗口中心
- 确定目标坐标：`--to-control` 的控件中心，或 `--to-x --to-y`
- 调用 `drag_mouse(button, press_coords, release_coords)`

### 6. type

- 定位控件（或使用焦点）
- 清空内容后输入 `text`

### 7. type-keys

- 向当前焦点发送 `keys` 序列

### 8. screenshot

- 调用 `window.capture_as_image()` 保存到 `path`
- 返回保存路径

### 9. get-tree

- 递归获取控件树，包含：ControlType、Name、AutomationId、Rect
- 输出为结构化文本或 JSON，便于生成选择器

### 10. menu

- 执行 `window.menu_select(menu_path)`
- `menu_path` 格式：`父菜单->子菜单`，如 `文件(&F)->另存为(&A)`

### 11. config（系统配置）

- **theme**：修改注册表 `HKCU\...\Themes\Personalize` 的 `AppsUseLightTheme`、`SystemUsesLightTheme`（0=深色，1=浅色）
- **power-plan**：调用 `powercfg /list`、`powercfg /setactive`
- **proxy**：修改注册表 `HKCU\...\Internet Settings` 的 `ProxyEnable`、`ProxyServer`、`ProxyOverride`
- **screen-timeout**：调用 `powercfg /change monitor-timeout-ac/dc`
- **remote-desktop**：修改 `HKLM\...\Terminal Server` 的 `fDenyTSConnections`（需管理员）
- **startup**：对 `%APPDATA%\...\Startup` 下的快捷方式重命名（添加/移除 `.disabled` 后缀）

## 边界条件

- **平台**：非 Windows 时，所有命令返回 `"Platform not supported"`，退出码 1
- **会话**：操作前检查 `app_id` 是否存在，否则返回 `"App [id] not connected"`
- **超时**：start/connect 支持超时，默认 30 秒
- **编码**：路径、标题、文本统一使用 UTF-8

## 异常处理

- pywinauto 未安装：提示 `pip install pywinauto`
- 找不到窗口：`connect` 返回明确错误
- 控件不存在：`click`、`type` 返回错误信息
- 超时：返回 `"Operation timed out"`

## 验收标准

1. **功能完整性**：start、connect、list、list-windows、close、click、double-click、right-click、hover、drag、type、type-keys、screenshot、get-tree、menu、config（theme/power-plan/proxy/screen-timeout/startup）均可正常执行
2. **平台检查**：非 Windows 时给出清晰提示
3. **会话管理**：list 正确列出会话；close 可正确断开
4. **依赖**：pywinauto 作为可选依赖，仅在 Windows 下安装
5. **CLI 注册**：`jw`、`jarvis-windows` 入口可用
6. **返回值**：所有命令输出统一 JSON，失败时包含 stderr 和非零退出码

## 依赖要求

### 可选依赖（仅 Windows）

```text
pywinauto>=0.6.9
pywin32  # pywinauto 的间接依赖
```

在 `pyproject.toml` 中增加：

```toml
[project.optional-dependencies]
windows = ["pywinauto>=0.6.9"]
```

## 实现建议

### 参考实现

- 参考 `src/jarvis/jarvis_browser/cli.py` 的命令结构和 JSON 输出格式
- 参考 `playwright_browser_tool_spec.md` 的规范结构

### 架构说明

- **无守护进程**：Windows 下每个 CLI 调用为独立进程，通过 `~/.jarvis/jw_sessions.json`（或类似）持久化连接信息（process/title/pid），下次命令据此重连。简化实现可要求每次传 `--process`/`--title`。
- **会话存储**：进程内使用 `_app_sessions: Dict[str, Application]`，同一进程内多次命令可复用；CLI 每次调用为单进程，故每次需 connect。为简化，首版采用「每次命令独立 connect」：必须传 `--process`/`--title`/`--pid`，不维护跨调用会话。
- **或采用 daemon**：与 jarvis_browser 一致，增加 daemon 子命令，会话存在 daemon 进程内，CLI 通过 socket 转发。首版可先实现无 daemon 的「每次 connect」模式，后续扩展 daemon。

### 文件结构

```text
src/jarvis/jarvis_windows/
  __init__.py
  cli.py          # Typer CLI，所有命令
```

### 代码结构

```python
# cli.py 核心逻辑
def _ensure_windows() -> None:
    """非 Windows 时抛出或退出"""

def _get_app(process=None, title=None, pid=None, backend="uia") -> Application:
    """连接并返回 Application 实例"""

def _run_and_exit(action: Callable) -> None:
    """执行 action，打印 JSON，按 success 设置退出码"""
```
