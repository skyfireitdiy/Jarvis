# 为编辑器扩展 LSP 语言支持

本文说明如何通过配置为 Jarvis 的编辑器新增一种语言的 LSP（Language Server Protocol）支持。

**核心机制：改配置即扩展。** 新增一种语言只需在 `~/.jarvis/config.yaml` 的
`lsp.languages` 段增加一项，**无需修改任何代码**。

## 整体架构

Jarvis 有两处使用 LSP，它们**共用同一份配置**：

```text
~/.jarvis/config.yaml  →  lsp.languages  ← 唯一配置来源
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
  jarvis-lsp（CLI / 守护进程）      Web 网关（Monaco 编辑器）
  hover / 定义 / 引用 / 诊断         hover / 补全 / 诊断
              │                             │
              │                    WS /api/lsp/{语言}?root=<workspace>
              │                             │（网关桥接，语言无感知，纯转发）
              │                             ▼
              └────────────► 语言服务器子进程（stdio）
```

- **配置读取层**：`src/jarvis/jarvis_lsp/config.py` 的 `LSPConfigReader`，
  两处共用，避免配置漂移。
- **Web 网关转换**：`src/jarvis/jarvis_web_gateway/lsp_registry.py` 把配置转换为
  网关内部 spec 结构。
- **WS 桥接**：`src/jarvis/jarvis_web_gateway/lsp_bridge.py` + `app.py` 的
  `GET /api/lsp/servers` 与 `WS /api/lsp/{语言}`，对语言完全无感知，只做
  WebSocket ↔ 子进程 stdio 的 JSON-RPC 转发。
- **前端客户端**：`src/jarvis/jarvis_service/frontend/src/lsp/registry.js`（拉清单、建索引）
  与 `manager.js`（连接、文档同步、注册 hover/completion provider、诊断）。

## 配置位置

配置位于 `~/.jarvis/config.yaml` 的 `lsp.languages` 段：

```yaml
lsp:
  languages:
    python:
      command: pylsp
      args: []
      file_extensions: [".py", ".pyi"]
      monaco_language: python
      root_markers: ["pyproject.toml", "setup.py", ".git"]
      install_hint: "pip install python-lsp-server"
```

**内置默认**：代码内置了 13 种语言的默认配置（python / go / typescript /
javascript / rust / c / cpp / lua / bash / ruby / php / html / css），
开箱即用。用户配置会**整体覆盖**同名语言的默认项，未配置的语言沿用默认。

## 字段说明

| 字段                     | 类型         | 必填 | 默认值   | 说明                                                            |
| ------------------------ | ------------ | ---- | -------- | --------------------------------------------------------------- |
| `command`                | string       | ✅   | —        | 启动命令（可执行文件名或绝对路径）。参数放 `args`，不要写在一起 |
| `args`                   | list[string] |      | `[]`     | 启动参数，如 `["--stdio"]`                                      |
| `file_extensions`        | list[string] |      | `[]`     | 文件扩展名，如 `[".py", ".pyi"]`，用于按扩展名匹配语言          |
| `monaco_language`        | string       |      | 取语言名 | 对应 Monaco 语言 id，如 `python`、`typescript`                  |
| `root_markers`           | list[string] |      | `[]`     | 用于确定 workspace 根的标记文件，如 `["Cargo.toml", ".git"]`    |
| `initialization_options` | object       |      | `{}`     | 传给 LSP `initialize` 的初始化选项                              |
| `install_hint`           | string       |      | `""`     | 服务器未安装时展示给用户的提示文案                              |

语言名（`languages` 下的 key）即服务器 id，也是 WS 路径 `/api/lsp/{语言}` 中的取值，
**大小写不敏感**。

**容错**：`command` 缺失、字段类型错误的语言项会被跳过并记录 `logging.warning`，
**不会影响其他语言**。

## 完整示例：新增 Rust 支持（rust-analyzer）

### 步骤 1：安装语言服务器

```bash
rustup component add rust-analyzer
rust-analyzer --version    # 确认可执行
```

### 步骤 2：修改配置

编辑 `~/.jarvis/config.yaml`，在 `lsp.languages` 下增加：

```yaml
lsp:
  languages:
    rust:
      command: rust-analyzer
      args: []
      file_extensions: [".rs"]
      monaco_language: rust
      root_markers: ["Cargo.toml", "Cargo.lock", ".git"]
      install_hint: "rustup component add rust-analyzer"
```

### 步骤 3：确认被识别

```bash
cd /home/skyfire/code/Jarvis
.venv/bin/python -c "
from jarvis.jarvis_web_gateway.lsp_registry import load_lsp_server_specs
for sid, s in sorted(load_lsp_server_specs().items()):
    print(f'{sid:12} monaco={s[\"monacoLanguage\"]:12} command={s[\"command\"]}')
"
```

应能看到 `rust` 一行。若没有，检查 YAML 缩进、`command` 是否为字符串。

### 步骤 4：生效

- **jarvis-lsp**：下次调用即生效（每次读取配置）。
- **Web 编辑器**：重启网关（配置在启动时加载），并刷新浏览器页面。

然后在 Web 界面打开一个 `.rs` 文件，悬停符号应出现类型/文档提示，输入时应出现补全建议。

## 降级行为

设计原则：**LSP 是增强，不是依赖**。任何环节失败都不会影响编辑器基本功能
（打开、编辑、保存、多标签、语法高亮）。

| 场景                          | 行为                                                                                              |
| ----------------------------- | ------------------------------------------------------------------------------------------------- |
| 语言服务器未安装 / 命令不存在 | 后端返回 `SERVER_START_FAILED`（含 `install_hint`）；前端 `console.warn` 一条降级提示，编辑器正常 |
| WS 连接失败 / 超时            | 前端 `console.warn`，静默降级为仅语法高亮                                                         |
| 配置项缺 `command` / 类型错误 | 后端跳过该项并记录 warning，其他语言不受影响                                                      |
| 清单拉取失败                  | 前端降级为空映射，所有语言退化为仅语法高亮                                                        |
| 非 master 节点的文件          | 当前仅支持 master 本地 LSP，非 master 文件跳过（已知限制）                                        |

## 调试方法

### 1. 确认配置是否被识别

```bash
cd /home/skyfire/code/Jarvis
.venv/bin/python -c "
from jarvis.jarvis_lsp.config import LSPConfigReader
r = LSPConfigReader()
for name, cfg in sorted(r.load_config().languages.items()):
    print(f'{name:12} command={cfg.command:30} args={cfg.args} ext={cfg.file_extensions}')
"
```

### 2. 查看桥接日志

语言服务器进程的启动、stderr、退出都会打到网关日志，关键词前缀为 `[lsp_bridge]`：

```bash
grep "\[lsp_bridge\]" <网关日志文件>
```

常见日志：

- 进程启动 / 复用：`logger.info`（含 `server_id`、`workspace_root`、pid）
- 子进程 stderr 输出：原样转发（语言服务器自身的报错会在这里出现）
- 空闲回收 / 退出：`logger.info`

### 3. 查看前端日志

浏览器开发者工具 Console 中，LSP 相关日志以 `[lsp]` 开头：

- `[lsp] 拉取语言服务器清单失败: HTTP 401` —— token 问题
- `[lsp] 语言服务器 "xxx" 不可用，已降级为仅语法高亮。安装提示: ...` —— 服务器未安装
- `[lsp] 拉取语言服务器清单异常，已降级为无 LSP` —— 网络/网关问题

### 4. 手动验证 WS 桥接

```bash
# 需要 websocat 或类似工具；token 放在子协议里
websocat -H="Sec-WebSocket-Protocol: jarvis-ws,jarvis-token.<urlencoded-token>" \
  "ws://127.0.0.1:8000/api/lsp/rust?root=/abs/path/to/project"
# 然后手输一行 JSON-RPC：
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"processId":null,"rootUri":null,"capabilities":{}}}
```

收到 `result.capabilities` 即表示桥接与语言服务器均正常。

## 已知限制

1. **仅支持 master 本地**：文件读写走 `/api/node/{nodeId}/...`，但 LSP 桥接注册在 master 本地。
   非 master 节点的文件会跳过 LSP（跨节点 WS 转发是独立传输层问题）。
2. **workspace root 取文件所在目录**：未向上查找 `root_markers`，因此在同一项目的不同子目录
   打开文件时可能各起一个语言服务器进程。
3. **未实现 `didSave`**：当前同步 didOpen / didChange / didClose，未发送 didSave。

## 相关源码

| 文件                                                     | 职责                                                            |
| -------------------------------------------------------- | --------------------------------------------------------------- |
| `src/jarvis/jarvis_lsp/config.py`                        | **配置读取层（唯一来源）**，内置默认语言，jarvis-lsp 与网关共用 |
| `src/jarvis/jarvis_web_gateway/lsp_registry.py`          | 把配置转换为网关 spec 结构                                      |
| `src/jarvis/jarvis_web_gateway/lsp_bridge.py`            | LSP 分帧编解码、进程池、workspace root 解析                     |
| `src/jarvis/jarvis_web_gateway/app.py`                   | `GET /api/lsp/servers`、`WS /api/lsp/{server_id}`               |
| `src/jarvis/jarvis_service/frontend/src/lsp/registry.js` | 前端拉清单、建语言/扩展名索引                                   |
| `src/jarvis/jarvis_service/frontend/src/lsp/manager.js`  | 自建轻量 LSP 客户端、文档同步、语言特性 provider                |
