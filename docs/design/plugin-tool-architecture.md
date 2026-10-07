# 插件体系工具架构方案

## 背景与问题

Jarvis 插件体系里，插件的"工具"职责不清，存在两类工具被混为一谈的问题：

- **插件自己使用的**：插件实现功能所需的代码（如 gh 插件的 GitHub API 封装、token 管理）。
- **Agent 使用的**：暴露给 Agent 的工具（`class XxxTool`，有 `name`/`description`/`parameters`/`execute`），让 AI 助手能代表用户操作。

此前 gateway 前端代理插件功能时，把插件功能当成"Agent 工具"来处理——加载 ToolRegistry / PluginToolManager 去执行 `class XxxTool`，导致**插件内部功能与 Agent 工具耦合**，甚至可能把插件内部功能暴露给 Agent。

## 核心原则：工具分两类，真正隔离

插件的工具必须分为两类，且**物理隔离**：

### 1. 插件私有功能（插件自己使用的）

- 插件实现功能所需的代码，放在**插件私有目录**（如 `plugin/`、`api/`、`internal/`）。
- **不声明在 `tool_load_dirs`**，因此不会被 ToolRegistry 加载，**Agent 看不到、调不到**。
- gateway 前端代理通过插件功能通道调用这些私有功能。

### 2. Agent 工具（Agent 使用的）

- 暴露给 Agent 的工具（`class XxxTool`），放在 `tools/` 目录，通过 `tool_load_dirs` 声明。
- 工具类是插件私有功能的**薄封装**：只做参数解析、调用私有功能、格式化返回。

## 运行环境区分（gateway / agent）

两类工具**运行在不同的进程环境**，进一步强化隔离：

| 类别 | 运行环境 | 加载机制 | 调用方 |
|------|----------|----------|--------|
| 插件私有功能（`plugin/`） | **gateway**（master 进程） | 由 gateway 按需 importlib 动态加载 | 前端代理（`POST /api/plugins/{node_id}/function-call`） |
| Agent 工具（`tools/`） | **agent 进程** | 由 ToolRegistry 加载（`register_tool_by_file`） | Agent（AI 助手） |

- 插件私有功能运行在 **gateway**，供前端代理调用，**不暴露给 Agent**。
- Agent 工具运行在 **agent 进程**，供 Agent 调用，是私有功能的薄封装。
- 因此：前端代理调用插件功能**不经过 ToolRegistry / Agent 工具机制**，与 Agent 侧完全隔离。

## 隔离机制

- **私有功能目录不进入 `tool_load_dirs`** → 不被 ToolRegistry 加载 → Agent 不可见。
- **gateway 前端代理**通过插件功能端点，动态加载插件私有功能并调用，**不经过 ToolRegistry / Agent 工具机制**。
- 私有功能与 Agent 工具**不共用同一份实现**：工具类只薄封装私有功能，私有功能本身不暴露给 Agent。

## gh 插件重构示例

gh 插件的功能逻辑（列 PR、列 Issue、查看、合并、评论、关闭、认证）目前分布在 `tools/` 的工具类 `execute` 里，同时被 Agent 当作工具使用。重构后：

```text
builtin/plugins/gh/
├── config.yaml          # tool_load_dirs 只声明 tools/（Agent 工具）
├── plugin/              # 插件私有功能（不暴露给 Agent，gateway 前端代理调用）
│   ├── api.py           # 纯函数：list_issues / list_prs / get_issue / get_pr
│   │                    #        merge_pr / comment / close_issue / auth
│   └── gh_common.py     # 底层 GitHub API 封装、token 管理
├── tools/               # Agent 工具（薄封装，调用 plugin/api.py）
│   ├── gh_list_issues.py
│   ├── gh_list_prs.py
│   └── ...
└── frontend/            # 前端组件（通过 gateway 调用 plugin/api.py）
```

- `plugin/api.py` 提供纯函数，**不通过 `tool_load_dirs` 暴露**，Agent 不可见。
- `tools/` 的工具类薄封装，调用 `plugin/api.py`，供 Agent 使用。
- gateway 前端代理调用 `plugin/api.py` 的纯函数，不经过 ToolRegistry。

## 实施要点

1. 新建插件私有功能目录（如 `plugin/`），承载插件功能实现。
2. `tools/` 工具类改为薄封装，调用私有功能。
3. gateway 提供插件功能代理端点，动态加载插件私有功能并调用。
4. 更新插件开发规则文档，明确两类工具的隔离规范。

## 相关代码位置

- 插件私有功能：`builtin/plugins/<name>/plugin/`（新增约定）
- Agent 工具：`builtin/plugins/<name>/tools/`
- 工具加载：`src/jarvis/jarvis_tools/registry.py`（`register_tool_by_file`）
- 插件注册追踪：`src/jarvis/jarvis_tools/plugin_registry.py`（PluginRegistry）
- gateway 插件功能代理：`src/jarvis/jarvis_web_gateway/app.py`
