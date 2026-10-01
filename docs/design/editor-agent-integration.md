# 编辑器与 Agent 集成架构设计

> 目标：让 Monaco 编辑器成为 Agent 与用户协作的可视化工作台，而非孤立编辑器。
> 本文档基于已核实的代码现状，给出每个集成点的消息格式、前后端改动位置与优先级。
> 对应任务：task-326（架构设计）、task-327~333（功能实施）。

---

## 1. 现状盘点（已核实）

### 1.1 前端编辑器（Vue 3 + Monaco）

- 主文件：`src/jarvis/jarvis_service/frontend/src/App.vue`（24421 行），编辑器逻辑集中在 App.vue + `components/WorkspacePanel.vue`。
- **已有能力**：多语言高亮、多标签、多 pane 分割、代码折叠、括号配对、minimap、智能提示、LSP(hover/completion/diagnostics)、保存、只读切换、Git diff、全局搜索、文件树、命令面板(Ctrl+P)、文件心跳自动刷新（轮询 mtime 检测 Agent 外部修改）。
- **关键函数**（App.vue）：
  - `openWorkspaceFile(path, agentId)`（:4934）—— 打开文件到编辑器（核心入口，所有「打开文件」都应走它）。
  - `resolveAgentRelativePath(relativePath, agentId)`（:4481）—— 相对路径按 Agent working_dir 解析为绝对路径。
  - `openFileSearchResult`（:4765）/ `openGlobalSearchResult`（:4769）—— 打开搜索结果并 `revealLineInCenter` + `setSelection` 定位。
  - `checkActiveWorkspaceFileHeartbeat`（:4878）—— 轮询 mtime 检测外部修改。
- **LSP 客户端**：`src/lsp/manager.js`（569 行）自建轻量 JSON-RPC over WebSocket，按 (serverId, root) 复用连接，已注册 hover/completion/diagnostics 三个 provider，按语言隔离，失败静默降级，**绝不 dispose model**。
- **命令面板动作单一数据源**：`src/actions/registry.js`（1109 行），纯模块，通过 `ctx` 回调触发 App.vue 函数。

### 1.2 后端消息通道（app.py，10531 行）

- 消息格式统一：`{"type": "...", "payload": {...}, "seq": N}`。
- 发布机制：`self._router.publish(message, session_id, connection_id)`。
- **`output` 消息**（app.py:547）：`payload` 含 `text/output_type/timestamp/lang/traceback/section/context`，`context` 含 `agent_id`，**无文件路径字段**。
- **`eval_js_request` 通道已存在**（app.py:744）：`payload={call_id, code, timeout}`，前端 `handleEvalJsRequest`（App.vue:14857）执行任意 JS 并回传 `eval_js_result`。这是**双向**通道，Agent 已能借此让前端执行 JS——但它是「通用逃逸口」，不适合作为结构化文件指令的规范通道。

### 1.3 后端符号级能力（code_analyzer）

- `src/jarvis/jarvis_code_agent/code_analyzer/context_manager.py`：
  - `find_definition(symbol_name, file_path)`（:187）→ Symbol
  - `find_references(symbol_name, file_path)`（:106）→ List[Reference]
  - `impact_analyzer`、`dependency_analyzer`、`symbol_table_db` 等。
- 这些是 **Agent（Python 侧）** 的能力，与前端 LSP（JS 侧）是两套独立体系。

---

## 2. 集成架构总览

```text
┌───────────────────────────── 前端 (Vue 3 + Monaco) ─────────────────────────────┐
│                                                                                 │
│  App.vue handleMessage() ── 消息分发中心                                        │
│    ├─ type='editor_open_file'   → openWorkspaceFile + revealLineInCenter       │
│    ├─ type='editor_diff'        → 打开 Git diff 视图（Agent 修改可视化）         │
│    └─ type='eval_js_request'    → 已有，通用 JS 执行                             │
│                                                                                 │
│  actions/registry.js ── 动作单一数据源                                          │
│    ├─ 编辑器功能动作（格式化/跳转行/大纲/问题面板…）                              │
│    └─ Agent 联动动作（"让 Agent 分析选中代码"…）                                 │
│                                                                                 │
│  lsp/manager.js ── 轻量 LSP 客户端（复用连接）                                   │
│    ├─ 已有：hover / completion / diagnostics                                    │
│    └─ 新增：definition / references / implementation / documentSymbols /        │
│              documentFormatting / rename                                        │
│                                                                                 │
│  Monaco editor ── 右键菜单 + 快捷键 + 选中内容                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
                              │  WebSocket (JSON-RPC 风格消息)
                              ▼
┌───────────────────────────── 后端 (app.py) ─────────────────────────────────────┐
│  WebGateway.emit_output / request_input / publish_execution_event               │
│  ── 新增：publish_editor_command(agent_id, command)                              │
│  Agent 侧：code_analyzer（符号级）+ 文件操作工具                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**核心原则**：

1. **Agent 集成优先于孤立编辑器功能**——每个编辑器功能都要问「Agent 能否受益/触发/联动」。
2. **复用现有通道**：LSP 复用 `lsp/manager.js`；Agent 指令复用 `app.py publish` + 前端 `handleMessage`；动作复用 `actions/registry.js`。
3. **不引入新第三方依赖**。

---

## 3. 集成点 1：Agent → 编辑器指令通道（最高优先级）

### 3.1 需求

Agent 在对话中引用文件/定位代码时，前端编辑器应自动打开对应文件并跳转到指定行/列。这是「Agent 与用户协作」的核心体验。

### 3.2 消息格式（新增 `editor_open_file` 类型）

```jsonc
// 后端 → 前端（通过 _router.publish，session_id=None 广播到所有 session）
{
  "type": "editor_open_file",
  "payload": {
    "agent_id": "agent-xxx", // 目标 Agent（决定 working_dir 与 node_id）
    "path": "src/foo/bar.py", // 相对 Agent working_dir 的路径（或绝对路径）
    "line": 42, // 可选，1-based，跳转行
    "column": 5, // 可选，1-based，跳转列
    "select_start": 40, // 可选，选中范围起点（行内字符偏移）
    "select_end": 50, // 可选，选中范围终点
    "reveal": true, // 可选，是否居中显示（默认 true）
  },
  "seq": 123,
}
```

### 3.3 后端改动点（app.py）

在 `WebGateway` 新增方法：

```python
def publish_editor_command(self, agent_id: str, command: str, payload: dict) -> None:
    """向所有前端广播编辑器指令（如打开文件/跳转行）。"""
    message = {
        "type": f"editor_{command}",
        "payload": {"agent_id": agent_id, **payload},
    }
    self._router.publish(message, session_id=None)
```

- Agent 侧在「引用文件」的 tool 回调里调用（例如 `open_file` 工具成功后、或对话流式输出中检测到文件路径时）。
- **最小改动**：后端只加一个 publish 辅助函数 + 在合适回调里触发；不引入新依赖。

### 3.4 前端改动点（App.vue handleMessage）

在 `handleMessage`（:14376）新增分支（放在 `eval_js_request` 之前）：

```js
} else if (type === 'editor_open_file') {
  handleEditorOpenFile(payload)
}
```

新增处理函数：

```js
async function handleEditorOpenFile(payload) {
  const agentId = payload?.agent_id || currentAgentId.value;
  const path = resolveAgentRelativePath(payload?.path, agentId);
  if (!path) return;
  await openWorkspaceFile(path, agentId); // 复用现有入口
  await nextTick();
  const modelData = editorModels.get(path);
  const view = getActiveWorkspaceView();
  if (!view || !modelData) return;
  const line = Number(payload?.line || 1);
  const col = Number(payload?.column || 1);
  view.revealLineInCenter(line); // 居中定位
  if (payload?.select_start != null && payload?.select_end != null) {
    view.setSelection(
      new monaco.Selection(
        line,
        payload.select_start + 1,
        line,
        payload.select_end + 1,
      ),
    );
  }
  view.setPosition({ lineNumber: line, column: col });
  view.focus();
}
```

### 3.5 与现有 `eval_js_request` 的关系

- `eval_js_request` 是通用逃逸口（任意 JS），保留用于无法结构化的场景。
- `editor_open_file` 是**结构化、类型安全**的编辑器指令，走专用分支，便于前端精确控制、审计与降级。
- **建议**：后续 Agent 侧新增 `open_file` 工具时，统一发 `editor_open_file`，不再用 eval_js 拼 JS。

---

## 4. 集成点 2：编辑器选中内容 → 发给 Agent

### 4.1 需求

用户在编辑器选中一段代码，通过右键菜单/命令面板把选中内容发给当前 Agent，让 Agent 分析/解释/修改。

### 4.2 前端改动点

1. **actions/registry.js** 新增动作（`ctx` 回调触发 App.vue 函数）：

   ```js
   {
     id: "editor-send-selection-to-agent",
     label: "让 Agent 分析选中代码",
     en: "Send Selection to Agent",
     group: "当前 Agent",
     icon: "🤖",
     keywords: ["分析", "选中", "selection", "agent"],
     enabled: (ctx) => !!ctx?.currentAgentId && !!ctx?.getEditorSelection,
     run: (ctx) => ctx.sendSelectionToAgent && ctx.sendSelectionToAgent(),
   }
   ```

2. **App.vue** 新增 `sendSelectionToAgent()`：
   - 从当前活跃编辑器 view 取 `getSelection()` + `getModel().getValueInRange(range)` 得到选中文本与文件路径。
   - 通过现有「发送消息给 Agent」通道（`sendMessageToAgent` / 输入框注入）把文本发给当前 Agent。
   - 消息格式：`分析以下选中代码（文件: <path> 行 <start>-<end>）：\n<选中文本>`。
3. **Monaco 右键菜单**：注册 `monaco.editor.addAction` 或 context menu，菜单项「让 Agent 分析选中代码」调用 `sendSelectionToAgent`。

### 4.3 消息通道

复用现有「用户 → Agent」输入通道（`input_result` / `send_to_agent`），**无需新增后端消息类型**。

---

## 5. 集成点 3：Agent 修改 → 编辑器实时联动

### 5.1 现状

已有 `checkActiveWorkspaceFileHeartbeat`（:4878）轮询 mtime 检测外部修改并自动刷新。但**无 diff 可视化**、无「Agent 正在修改」的实时反馈。

### 5.2 增强方案

1. **保留心跳轮询**作为兜底（不破坏现有功能）。
2. **新增 `editor_diff` 消息**：Agent 完成文件修改后，后端发一条指令，前端自动打开 Git diff 视图展示改动：

   ```jsonc
   {
     "type": "editor_diff",
     "payload": {
       "agent_id": "agent-xxx",
       "path": "src/foo/bar.py", // 可选，只展示该文件 diff；缺省展示整个工作区 diff
       "action": "show", // show / refresh
     },
   }
   ```

   前端 `handleMessage` 新增分支 → 调用现有 `openWorkspaceDiff` / `refreshGitView`。

3. **心跳刷新时自动标记**：当检测到外部修改且用户未编辑（`!tab.isDirty`），刷新后若内容变化，自动提示「Agent 已修改此文件」并提供「查看变更」入口（复用现有 `current-view-diff` 动作）。

### 5.3 数据流

```text
Agent 修改文件 → (文件系统) → 前端心跳轮询检测 mtime 变化
                          → 自动刷新 model 内容
                          → 标记 externalModified / 提示查看变更
Agent 完成修改 → 后端 publish editor_diff → 前端自动打开 diff 视图
```

---

## 6. 集成点 4：LSP 能力与后端 code_analyzer 打通

### 6.1 定位

- **前端 LSP**（lsp/manager.js）负责**交互式**语言特性：跳转定义/引用/实现、符号树、格式化、重命名——依赖本地语言服务器，实时性好。
- **后端 code_analyzer** 负责**Agent 侧**符号级分析：`find_definition`/`find_references`/`impact_analyzer`/`dependency_analyzer`——供 Agent 在做修改决策时使用。

### 6.2 打通方式（不重复造轮子）

1. **前端编辑器功能**（task-327/330/328）优先复用 `lsp/manager.js` 的 JSON-RPC 通道，扩展 provider：`textDocument/definition`、`references`、`implementation`、`documentSymbol`、`formatting`、`rename`。
2. **Agent 侧**继续用后端 code_analyzer（Python），两者各自服务自己的消费方，**不做数据层合并**（避免引入跨语言同步复杂度）。
3. **可选联动**：若前端 LSP 不可用（语言服务器未安装），编辑器「跳转定义」可降级调用后端 `code_analyzer.find_definition`（通过现有 HTTP API），实现「LSP 优先、code_analyzer 兜底」。

### 6.3 新增 LSP provider 清单（lsp/manager.js）

| 功能        | LSP 方法                                  | 前端触发                | 对应 task |
| ----------- | ----------------------------------------- | ----------------------- | --------- |
| 跳转定义    | `textDocument/definition`                 | F12 / 右键 / Ctrl+Click | task-327  |
| 查找引用    | `textDocument/references`                 | Shift+F12 / 右键        | task-327  |
| 跳转实现    | `textDocument/implementation`             | Ctrl+F12 / 右键         | task-327  |
| 代码格式化  | `textDocument/formatting`                 | Shift+Alt+F / 保存时    | task-328  |
| 问题面板    | `textDocument/publishDiagnostics`（已有） | 侧边栏「问题」视图      | task-329  |
| 大纲/符号树 | `textDocument/documentSymbol`             | 侧边栏「大纲」视图      | task-330  |
| 面包屑      | `documentSymbol` 层级                     | 顶部面包屑              | task-330  |
| 重命名符号  | `textDocument/rename`                     | F2                      | task-331  |

> **约束**：所有 provider 复用现有 `getClientForModel` / `ensureClient` 连接复用机制；失败静默降级；**绝不 dispose model**。

---

## 7. 优先级排序与任务映射

| 优先级 | 功能                        | 类型           | 依赖                              | 对应 task         |
| ------ | --------------------------- | -------------- | --------------------------------- | ----------------- |
| **P0** | Agent→编辑器打开文件/跳转行 | Agent 集成     | 后端 publish + 前端 handleMessage | task-332          |
| **P0** | 编辑器选中内容→Agent        | Agent 集成     | actions/registry + App.vue        | task-333          |
| **P1** | Agent 修改→diff 联动        | Agent 集成     | 心跳 + editor_diff                | 并入 task-332/329 |
| **P1** | LSP 跳转定义/引用/实现      | 纯编辑器 + LSP | lsp/manager.js                    | task-327          |
| **P1** | 代码格式化                  | 纯编辑器 + LSP | lsp/manager.js                    | task-328          |
| **P2** | 问题面板                    | 纯编辑器 + LSP | 复用 diagnostics                  | task-329          |
| **P2** | 大纲/符号树 + 面包屑        | 纯编辑器 + LSP | lsp/manager.js                    | task-330          |
| **P2** | 跳转行/自动保存/状态栏      | 纯编辑器       | App.vue                           | task-331          |

**实施顺序建议**：先做 P0 两个 Agent 集成点（task-332/333，体现「编辑器与 Agent 协作」核心价值），再做 P1 LSP 增强（task-327/328），最后 P2 面板类（task-329/330/331）。

---

## 8. 改动文件清单（汇总）

| 文件                                                                      | 改动                                                                                                                     |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `src/jarvis/jarvis_web_gateway/app.py`                                    | 新增 `publish_editor_command`；在 Agent 引用文件/完成修改处触发                                                          |
| `src/jarvis/jarvis_service/frontend/src/App.vue`                          | `handleMessage` 新增 `editor_open_file`/`editor_diff` 分支；`handleEditorOpenFile`；`sendSelectionToAgent`；右键菜单注册 |
| `src/jarvis/jarvis_service/frontend/src/actions/registry.js`              | 新增编辑器功能动作 + Agent 联动动作                                                                                      |
| `src/jarvis/jarvis_service/frontend/src/lsp/manager.js`                   | 扩展 definition/references/implementation/documentSymbol/formatting/rename provider                                      |
| `src/jarvis/jarvis_service/frontend/src/lsp/registry.js`                  | 如需按能力注册 provider                                                                                                  |
| `src/jarvis/jarvis_service/frontend/src/components/WorkspacePanel.vue`    | 问题面板/大纲视图/状态栏渲染                                                                                             |
| `src/jarvis/jarvis_service/frontend/src/components/WorkspacePaneTree.vue` | 侧边栏视图（问题/大纲）                                                                                                  |

---

## 9. 验证标准

- 每个功能改动后 `npm run build` 通过。
- **Agent 集成链路**（P0）：
  - Agent 发 `editor_open_file` → 前端自动打开文件并跳转行（真机验证）。
  - 编辑器选中代码 → 右键「让 Agent 分析」→ 消息到达 Agent（真机验证）。
- **LSP 增强**（P1/P2）：F12 跳转、Shift+F12 引用、格式化、问题面板、大纲可交互（npm run build + 浏览器验证）。
- 不破坏：心跳刷新、分割视图、只读切换、多标签 undo 栈（不 dispose model）。

---

## 10. 风险与规避

| 风险                          | 规避                                                                                |
| ----------------------------- | ----------------------------------------------------------------------------------- |
| Agent 指令通道滥用（任意 JS） | 用结构化 `editor_open_file` 替代 eval_js 逃逸口；eval_js 保留但仅用于无法结构化场景 |
| LSP provider 重复注册         | 沿用 `registeredProviders` Set 去重（manager.js:29）                                |
| 破坏多标签 undo 栈            | 所有改动不 dispose model（沿用现有约束）                                            |
| 心跳与用户编辑冲突            | 仅 `!tab.isDirty` 时自动刷新（沿用 :4900 现有逻辑）                                 |
| 后端改动影响面大              | 只加 publish 辅助函数 + 回调触发点，不动现有消息链路                                |
