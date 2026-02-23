# Jarvis Windows CLI (jw) 使用指南

## 概述

`jw` (或 `jarvis-windows`) 是一个基于 pywinauto 的 Windows 桌面程序自动化命令行工具，支持启动应用、连接到已有窗口、执行点击、输入、截图、获取控件树等操作。**仅支持 Windows 平台**。

通过 `~/.jarvis/jw_sessions.json` 持久化连接信息，后续命令可复用已保存的会话。

## 快速开始

```bash
# 1. 启动记事本
jw start --path notepad.exe

# 2. 连接到已运行的记事本（若未使用 start）
jw connect --title "无标题 - 记事本"

# 3. 输入文本
jw type --text "Hello World"

# 4. 截图
jw screenshot

# 5. 关闭会话
jw close
```

## 通用参数

多数命令支持以下可选参数：

- `--app-id TEXT`: 应用会话 ID（默认：`default`）
- `--process TEXT`: 进程名或路径（覆盖会话）
- `--title TEXT`: 窗口标题（覆盖会话，支持正则）
- `--pid INT`: 进程 ID（覆盖会话）
- `--backend TEXT`: pywinauto 后端，`uia`（默认）或 `win32`

## 命令列表

### 1. 应用管理

#### start - 启动应用

启动应用程序并注册会话。

**参数：**

- `-p, --path TEXT`: 可执行文件路径（必需）
- `-a, --args TEXT`: 启动参数
- `--app-id TEXT`: 会话 ID（默认：`default`）
- `--backend TEXT`: 后端（默认：`uia`）
- `-t, --timeout INT`: 启动超时秒数（默认：30）

**示例：**

```bash
jw start --path notepad.exe
jw start --path "C:\Program Files\app\app.exe" --args "C:\file.txt"
```

#### connect - 连接到已运行窗口

连接到已运行的窗口并保存会话。

**参数：**

- `--process TEXT`: 进程名或路径，如 `notepad.exe`
- `-t, --title TEXT`: 窗口标题（支持正则匹配）
- `--pid INT`: 进程 ID
- `--app-id TEXT`: 会话 ID（默认：`default`）

至少需要 `--process`、`--title` 或 `--pid` 之一。

**示例：**

```bash
jw connect --process notepad.exe
jw connect --title "无标题 - 记事本"
jw connect --pid 12345
```

#### list - 列出会话

列出所有已注册的应用会话。

**参数：**

- `--app-id TEXT`: 按会话 ID 过滤

**示例：**

```bash
jw list
```

#### close - 关闭/断开会话

断开应用会话，可选强制结束进程。

**参数：**

- `--app-id TEXT`: 会话 ID（默认：`default`）
- `-k, --kill`: 是否强制结束进程（默认：false）

**示例：**

```bash
jw close
jw close --kill   # 强制结束进程
```

### 2. 鼠标与点击

#### click - 点击

点击控件或执行菜单选择。

**参数：**

- `-c, --control TEXT`: 控件标题、AutomationId 或 `title_regex=模式`
- `-m, --menu TEXT`: 菜单路径，如 `文件(&F)->打开(&O)`
- `-i, --index INT`: 同类型控件中的索引（从 0 开始）

**示例：**

```bash
jw click --control "确定"
jw click --control "Edit"
jw click --menu "文件(&F)->另存为(&A)"
```

#### double-click - 双击

双击控件。

**参数：**

- `-c, --control TEXT`: 控件标识（必需）
- `-i, --index INT`: 控件索引

**示例：**

```bash
jw double-click --control "文件名"
```

#### right-click - 右键点击

右键点击控件或窗口。

**参数：**

- `-c, --control TEXT`: 控件标识（可选，不指定则对窗口右键）

**示例：**

```bash
jw right-click
jw right-click --control "编辑区域"
```

#### hover - 移动鼠标

将鼠标移动到控件中心或指定屏幕坐标。

**参数：**

- `-c, --control TEXT`: 移至控件中心
- `--x INT`: 屏幕 X 坐标（与 --control 二选一）
- `--y INT`: 屏幕 Y 坐标（与 --control 二选一）

**示例：**

```bash
jw hover --control "确定"
jw hover --x 100 --y 200
```

#### drag - 拖拽

拖拽鼠标从起点到终点。

**参数：**

- `--from-control TEXT`: 起始控件
- `--from-x INT`, `--from-y INT`: 起始屏幕坐标
- `--to-control TEXT`: 目标控件
- `--to-x INT`, `--to-y INT`: 目标屏幕坐标
- `-b, --button TEXT`: 鼠标按键（默认：`left`，可选 `right`、`middle`）

**示例：**

```bash
jw drag --from-control "项目1" --to-control "目标区"
jw drag --to-x 200 --to-y 200
```

### 3. 键盘输入

#### type - 输入文本

向控件输入文本（清空后输入）。

**参数：**

- `-t, --text TEXT`: 要输入的文本（必需）
- `-c, --control TEXT`: 目标控件（可选，不指定则为当前焦点）

**示例：**

```bash
jw type --text "Hello World"
jw type --control "Edit" --text "内容"
```

#### type-keys - 发送按键序列

发送键盘按键序列，支持 pywinauto 的 `type_keys` 语法。

**参数：**

- `-k, --keys TEXT`: 按键序列（必需），如 `^a`（Ctrl+A）、`{ENTER}`

**示例：**

```bash
jw type-keys --keys "^a"
jw type-keys --keys "{ENTER}"
```

### 4. 截图与控件树

#### screenshot - 截图

截取窗口截图。

**参数：**

- `-p, --path TEXT`: 保存路径（可选，默认保存到 `~/.jarvis/`）

**示例：**

```bash
jw screenshot
jw screenshot --path C:\temp\capture.png
```

#### get-tree - 获取控件树

获取窗口控件树结构，用于生成选择器。

**参数：**

- `-d, --depth INT`: 遍历深度（默认：3）
- `-c, --control TEXT`: 从指定控件开始（可选）

**示例：**

```bash
jw get-tree
jw get-tree --depth 5 --control "Panel"
```

#### menu - 执行菜单

执行菜单选择。

**参数：**

- `-p, --path TEXT`: 菜单路径（必需），如 `文件(&F)->打开(&O)`

**示例：**

```bash
jw menu --path "编辑(&E)->粘贴(&P)"
```

## 完整使用示例

### 记事本自动化

```bash
# 1. 启动记事本
jw start --path notepad.exe

# 2. 输入文本
jw type --text "Hello from Jarvis"

# 3. 保存文件
jw menu --path "文件(&F)->另存为(&A)"
jw type --control "Edit" --text "C:\\Users\\test\\demo.txt"
jw click --control "保存"

# 4. 截图
jw screenshot --path C:\temp\notepad.png

# 5. 关闭
jw close --kill
```

### 连接已有窗口操作

```bash
# 1. 连接到已打开的记事本
jw connect --title "无标题 - 记事本"

# 2. 查看控件树
jw get-tree

# 3. 双击编辑区
jw double-click --control "Edit"

# 4. 全选并复制
jw type-keys --keys "^a"
jw type-keys --keys "^c"
```

## 最佳实践

### 1. 使用 get-tree 定位控件

在不清楚控件标识时，先用 `get-tree` 查看结构：

```bash
jw connect --title "应用标题"
jw get-tree
```

### 2. 会话持久化

`connect` 或 `start` 成功后，会话会保存到 `~/.jarvis/jw_sessions.json`，后续命令可直接使用 `--app-id` 而不必重复指定 `--process`/`--title`。

### 3. 控件标识方式

- **标题文本**：`--control "确定"`
- **AutomationId**：`--control "submitButton"`
- **正则匹配**：`--control "title_regex=.*记事本.*"`

### 4. 错误处理

所有命令返回 JSON 格式：

```json
{
  "success": true,
  "stdout": "操作结果",
  "stderr": ""
}
```

失败时 `success` 为 `false`，`stderr` 包含错误描述。

## 故障排除

### 非 Windows 平台

**错误：** `jarvis-windows (jw) requires Windows`

**说明：** 此工具仅支持 Windows，请在 Windows 上使用。

### pywinauto 未安装

**错误：** `pywinauto not installed. Run: pip install pywinauto`

**解决：**

```bash
pip install pywinauto
# 或安装完整依赖
pip install jarvis-ai-assistant[windows]
```

### 找不到窗口

**错误：** `Connect failed` 或 `Control not found`

**解决：**

```bash
# 1. 确认应用已启动
# 2. 使用 get-tree 检查控件结构
jw connect --title "部分标题"
jw get-tree

# 3. 尝试不同后端
jw connect --title "标题" --backend win32
```

## 命令速查表

| 命令        | 描述           | 关键参数                                  |
| ----------- | -------------- | ----------------------------------------- |
| start       | 启动应用       | --path (必需), --args                      |
| connect     | 连接窗口       | --process / --title / --pid 至少其一       |
| list        | 列出会话       | --app-id                                  |
| close       | 关闭会话       | --app-id, --kill                          |
| click       | 点击           | --control, --menu                         |
| double-click| 双击           | --control (必需)                           |
| right-click | 右键点击       | --control                                 |
| hover       | 移动鼠标       | --control 或 --x --y                      |
| drag        | 拖拽           | --from-control, --to-control 或坐标       |
| type        | 输入文本       | --text (必需), --control                   |
| type-keys   | 发送按键       | --keys (必需)                              |
| screenshot  | 截图           | --path                                    |
| get-tree    | 获取控件树     | --depth, --control                         |
| menu        | 执行菜单       | --path (必需)                              |

## 相关文档

- [pywinauto 文档](https://pywinauto.readthedocs.io/)
- [Windows App 工具规范]({{ git_root_dir }}/.jarvis/spec/windows_app_tool_spec.md)
