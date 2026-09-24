# 为 Monaco 编辑器扩展 LSP 语言支持

本文说明如何为 Web 界面的 Monaco 编辑器新增一种语言的 LSP（Language Server Protocol）支持。

**核心机制：丢清单即扩展。** 新增一种语言只需在清单目录放入一个 JSON 文件，**无需修改任何核心代码**（后端桥接、前端客户端、App.vue 均不用动）。

## 整体架构

```text
浏览器 (Monaco 编辑器)
    │  自建轻量 LSP 客户端（原生 WebSocket + JSON-RPC）
    ▼
WS  /api/lsp/{server_id}?root=<workspace根目录>      ← 网关桥接，语言无感知，纯转发
    │  Content-Length 分帧
    ▼
语言服务器子进程 (stdio)                              ← 命令来自清单
```

- **清单（manifest）**：描述一种语言服务器如何启动、对应哪个 Monaco 语言、匹配哪些扩展名。
- **清单扫描器**：`src/jarvis/jarvis_web_gateway/lsp_registry.py`，扫描两个目录并合并。
- **WS 桥接**：`src/jarvis/jarvis_web_gateway/lsp_bridge.py` + `app.py` 的 `GET /api/lsp/servers` 与 `WS /api/lsp/{server_id}`。对语言完全无感知，只做 WebSocket ↔ 子进程 stdio 的 JSON-RPC 转发。
- **前端客户端**：`src/jarvis/jarvis_service/frontend/src/lsp/registry.js`（拉清单、建索引）与 `manager.js`（连接、文档同步、注册 hover/completion provider、诊断）。

## 清单目录与优先级

扫描两个目录，**按 `id` 去重，用户目录覆盖内置目录**：

| 目录 | 路径                                         | 用途                                             |
| ---- | -------------------------------------------- | ------------------------------------------------ |
| 内置 | `src/jarvis/jarvis_web_gateway/lsp_servers/` | 随代码分发，开箱即用（python / typescript / go） |
| 用户 | `{数据目录}/lsp_servers/`                    | 用户自行扩展，同名 `id` 覆盖内置                 |

数据目录由 `jarvis.jarvis_utils.config.get_data_dir()` 决定，通常是 `~/.jarvis/`。用户目录不存在时会被忽略，不会报错。

覆盖的典型用途：内置 `python.json` 用 `pylsp`，若你想换成 `pyright`，只需在用户目录放一个同 `id` 的 `python.json`，无需改动内置文件。

## 清单字段说明

| 字段                    | 类型         | 必填 | 说明                                                                                 |
| ----------------------- | ------------ | ---- | ------------------------------------------------------------------------------------ |
| `id`                    | string       | ✅   | 语言服务器唯一标识，如 `"python"`。同时用于 WS 路径 `/api/lsp/{id}`，须全局唯一      |
| `monacoLanguage`        | string       | ✅   | 对应 Monaco 语言 id，如 `"python"`、`"typescript"`。前端据此把编辑器语言与服务器关联 |
| `command`               | list[string] | ✅   | 启动命令，**必须是列表**（如 `["pylsp"]`），禁止写成字符串，以避免 shell 解析        |
| `extensions`            | list[string] |      | 文件扩展名，如 `[".py", ".pyi"]`。语言 id 不可靠时用作备用匹配                       |
| `args`                  | list[string] |      | 附加参数，如 `["--stdio"]`                                                           |
| `rootMarkers`           | list[string] |      | 用于确定 workspace 根的标记文件，如 `["pyproject.toml", ".git"]`                     |
| `initializationOptions` | object       |      | 传给 LSP `initialize` 的初始化选项                                                   |
| `installHint`           | string       |      | 服务器未安装时展示给用户的提示文案                                                   |

加载后每个清单会额外带一个 `_source` 字段（`"builtin"` 或 `"user"`），用于区分来源。

**容错**：非法 JSON、缺必填字段、字段类型错误的清单会被跳过并记录 `logging.warning`，**不会中断其他清单的加载**。

## 完整示例：新增 Rust 支持（rust-analyzer）

### 步骤 1：安装语言服务器

```bash
rustup component add rust-analyzer
# 或
rustup component add rust-src
```

确认可执行：

```bash
rust-analyzer --version
```

### 步骤 2：编写清单

在用户目录创建 `{数据目录}/lsp_servers/rust.json`（例如 `~/.jarvis/lsp_servers/rust.json`）：

```json
{
  "id": "rust",
  "monacoLanguage": "rust",
  "extensions": [".rs"],
  "command": ["rust-analyzer"],
  "args": [],
  "rootMarkers": ["Cargo.toml", "Cargo.lock", ".git"],
  "initializationOptions": {},
  "installHint": "rustup component add rust-analyzer"
}
```

目录不存在时先创建：

```bash
mkdir -p ~/.jarvis/lsp_servers
```

### 步骤 3：确认服务器被识别

重启网关（清单每次调用都会重新扫描，无需改代码；但前端有缓存，需刷新页面），然后：

```bash
curl -s -H "Authorization: Bearer <你的token>" \
  http://127.0.0.1:8000/api/lsp/servers | python -m json.tool
```

应能在返回的 `servers` 列表中看到：

```json
{
  "id": "rust",
  "monacoLanguage": "rust",
  "extensions": [".rs"],
  "installHint": "rustup component add rust-analyzer",
  "source": "user"
}
```

### 步骤 4：验证

在 Web 界面打开一个 `.rs` 文件，将鼠标悬停在符号上应出现类型/文档提示，输入时应出现补全建议。若语言服务器未安装，编辑器仍可正常使用（仅无 LSP 增强），控制台会打印一条降级提示。

## 降级行为

设计原则：**LSP 是增强，不是依赖**。任何环节失败都不会影响编辑器基本功能（打开、编辑、保存、多标签、语法高亮）。

| 场景                          | 行为                                                                                             |
| ----------------------------- | ------------------------------------------------------------------------------------------------ |
| 语言服务器未安装 / 命令不存在 | 后端返回 `SERVER_START_FAILED`（含 `installHint`）；前端 `console.warn` 一条降级提示，编辑器正常 |
| WS 连接失败 / 超时            | 前端 `console.warn`，静默降级为仅语法高亮                                                        |
| 清单 JSON 非法或缺字段        | 后端跳过该清单并记录 warning，其他语言不受影响                                                   |
| 清单拉取失败                  | 前端降级为空映射，所有语言退化为仅语法高亮                                                       |
| 非 master 节点的文件          | 当前仅支持 master 本地 LSP，非 master 文件跳过（已知限制）                                       |

## 调试方法

### 1. 确认清单是否被识别

```bash
# 直接调用扫描器（无需起网关）
cd /home/skyfire/code/Jarvis
.venv/bin/python -c "
from jarvis.jarvis_web_gateway.lsp_registry import load_lsp_server_specs
for sid, spec in sorted(load_lsp_server_specs().items()):
    print(f\"{sid:12} source={spec['_source']:8} command={spec['command']}\")
"
```

若你的清单没出现，检查：JSON 是否合法、`id`/`monacoLanguage`/`command` 是否齐全、`command` 是否为列表。

### 2. 查看桥接日志

语言服务器进程的启动、stderr、退出都会打到网关日志，关键词前缀为 `[lsp_bridge]`：

```bash
# 网关前台运行时直接观察；后台运行时查日志文件
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

1. **仅支持 master 本地**：文件读写走 `/api/node/{nodeId}/...`，但 LSP 桥接注册在 master 本地。非 master 节点的文件会跳过 LSP（跨节点 WS 转发是独立传输层问题）。
2. **workspace root 取文件所在目录**：未向上查找 `rootMarkers`，因此在同一项目的不同子目录打开文件时可能各起一个语言服务器进程。
3. **未实现 `didSave`**：当前同步 didOpen / didChange / didClose，未发送 didSave。

## 相关源码

| 文件                                                     | 职责                                              |
| -------------------------------------------------------- | ------------------------------------------------- |
| `src/jarvis/jarvis_web_gateway/lsp_registry.py`          | 清单扫描、校验、双目录合并                        |
| `src/jarvis/jarvis_web_gateway/lsp_bridge.py`            | LSP 分帧编解码、进程池、workspace root 解析       |
| `src/jarvis/jarvis_web_gateway/app.py`                   | `GET /api/lsp/servers`、`WS /api/lsp/{server_id}` |
| `src/jarvis/jarvis_service/frontend/src/lsp/registry.js` | 前端拉清单、建语言/扩展名索引                     |
| `src/jarvis/jarvis_service/frontend/src/lsp/manager.js`  | 自建轻量 LSP 客户端、文档同步、语言特性 provider  |
