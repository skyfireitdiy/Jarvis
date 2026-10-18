# Jarvis 插件开发指南

> 本文档面向**插件作者与开源贡献者**，介绍如何开发、打包、发布与分发 Jarvis 插件包。
> 若你只是想安装/使用已有插件，见 [使用指南](jarvis_book/4.使用指南.md) 的插件章节。
>
> 相关设计文档：[插件体系工具架构](design/plugin-tool-architecture.md)、[前端插件扩展设计](design/frontend-plugin-extension-design.md)。

## 一、插件是什么

Jarvis 采用**内核 + 插件包**架构：`config.yaml` 支持的任意配置（工具 / 规则 / Agent 定义 / 编排 / 前端扩展 / 回调）都可打包为插件，安装后自动发现并注入，**无需改内核、无需重新部署**。

插件是**按目录组织的可扩展单元**，运行时由 Jarvis 自动加载并注册。插件资源遵循**可逆效应**：加载时显式登记到 `PluginRegistry`，卸载时按登记精确撤销，register / unregister 完全对称。

**两类插件：**

| 类型 | 位置 | 特征 |
| --- | --- | --- |
| 内置插件 | 源码 `builtin/plugins/<name>/` | `config.yaml` 声明 `builtin: true`；不复制、不可卸载/升级 |
| 外部插件 | `<data_dir>/plugins/<name>/`（默认 `~/.jarvis/plugins/`） | 可安装 / 升级 / 卸载 |

## 二、快速开始

### 1. 生成脚手架

```bash
jarvis --new-plugin my-plugin --plugin-output-dir .
```

生成符合加载约定的完整骨架：

```text
my-plugin/
├── config.yaml          # 必填：插件配置（name/version + 扩展点声明）
├── README.md            # 推荐：开发者文档
├── plugin/              # 可选：插件私有功能（运行在 gateway，不暴露给 Agent）
├── rules/               # 可选：规则（Markdown，带 YAML front matter）
├── tools/               # 可选：Agent 工具（Python 模块，class XxxTool）
├── agents/              # 可选：Agent 定义（YAML）
├── orchestration/       # 可选：编排流水线（YAML）
└── frontend/            # 可选：前端扩展（纯浏览器 ES module，用 window.Vue）
```

### 2. 按需实现扩展点

编辑 `config.yaml` 声明扩展点，在对应目录实现规则 / 工具 / Agent / 编排 / 前端。

### 3. 本地验证

```bash
# 工具模块语法检查
python -m py_compile my-plugin/tools/my_plugin_tool.py

# 安装到本地验证（目录安装）
jarvis --install-plugin ./my-plugin

# 查看已安装插件
jarvis --list-plugins
```

## 三、config.yaml 字段规范

```yaml
---
name: my-plugin            # 必填：插件唯一标识（目录名、工具/规则命名依据）
description: 插件描述。     # 必填：功能说明
version: 0.1.0             # 版本号（安装时做版本比较）
license: MIT               # 开源协议
builtin: true              # 内置插件标记（外部插件不写）
# api_version: "1.0"        # 可选：插件依赖的接口协议版本（默认 "1.0"，向后兼容；见「接口版本」章节）
# --- 扩展点（路径用 {{plugin_dir}} 占位，运行时由 jinja2 自动渲染为插件绝对路径）---
rules_load_dirs:
  - "{{plugin_dir}}/rules"
tool_load_dirs:
  - "{{plugin_dir}}/tools"
# agent_definition_dirs:
#   - "{{plugin_dir}}/agents"
# --- MCP 扩展点（可选，声明插件自带的 MCP 服务，合并进全局 mcp 配置）---
# mcp:
#   - type: "stdio"
#     name: "my-mcp"
#     command: "npx"
#     args:
#       - "-y"
#       - "@modelcontextprotocol/server-filesystem"
#       - "/path/to/dir"
# --- LSP 语言服务扩展点（可选，声明插件自带的 LSP 服务器，按语言合并进全局 lsp.languages）---
# lsp:
#   languages:
#     python:
#       command: "pyright-langserver"
#       args: ["--stdio"]
#       file_extensions: [".py"]
#       root_markers: ["pyproject.toml", "setup.py"]
# --- 事件回调扩展点（可选，声明插件自带的事件回调目录，见「四.8 事件回调」）---
# event_callbacks:
#   - "{{plugin_dir}}/callbacks"          # 字符串：目录内 .py 按文件名自动匹配事件，默认 event_bus
#   - dir: "{{plugin_dir}}/callbacks"     # 字典：显式声明事件与注册目标
#     events: ["task_started", "task_completed"]
#     target: "event_bus"                 # event_bus（默认）/ hook / modifier
# --- 模型供应商扩展点（可选，声明插件自带的平台实现目录，见「四.10 模型供应商（platforms/）」）---
# platforms:
#   - "{{plugin_dir}}/platforms"
# --- 编排流水线声明 ---
orchestration:
  - name: "my-pipeline"
    description: "流水线描述"
    file: "{{plugin_dir}}/orchestration/my_pipeline.yaml"
# --- 前端扩展声明（可选）---
# frontend:
#   admin_tabs:
#     - id: my-admin
#       title: "我的管理"
#       entry: admin_tab.js
#   sidebar_views:
#     - id: my-view
#       title: "我的视图"
#       entry: sidebar_view.js
#   tool_panels:
#     - id: my-tool
#       title: "我的工具"
#       entry: tool.js
# --- 依赖声明（可选，三类：plugins/python/commands）---
# dependencies:
#   plugins:
#     - name: other-plugin
#       version: ">=1.0.0"
#   python:
#     requests: ">=2.0"
#   commands:
#     - git
# --- 生命周期钩子（可选，安装/升级/卸载前后执行 shell 命令）---
# hooks:
#   pre-install:
#     - "python scripts/prepare.py"
#   post-install:
#     - "echo 'installed'"
#   pre-update:
#     - "git stash"
#   post-update:
#     - "python scripts/migrate.py"
#   pre-uninstall:
#     - "python scripts/cleanup.py"
#   post-uninstall:
#     - "echo 'uninstalled'"
---
```

**要点：**

- `{{plugin_dir}}` 是 jinja2 模板变量，运行时渲染为插件目录绝对路径（见 `render_plugin_config_template`），**勿**写死绝对路径。
- 扩展点字段（`rules_load_dirs`/`tool_load_dirs`/`agent_definition_dirs`/`orchestration`/`roles_dirs`/`mcp`/`lsp`/`event_callbacks`/`platforms` 等）会被合并进全局配置供 getter 消费；其中 `mcp` 声明的 MCP server 列表会被合并进全局 `mcp` 配置，插件安装后自动注册为 MCP 工具，无需用户在全局 `~/.jarvis/config.yaml` 重复配置；`lsp` 声明的语言服务会按语言名深度合并进全局 `lsp.languages`，插件安装后自动生效，无需重启；`platforms` 声明的平台实现目录会在插件安装后自动注册到 `PlatformRegistry`（见「四.9 模型供应商」）。
- 除扩展点字段外的其余字段（`name`/`description`/`version`/`builtin`/`license`/`dependencies`/`capabilities`/`frontend`/自定义业务字段）会被隔离到全局配置的 `plugin_configs.<plugin_name>`，**不污染全局配置顶层、多个插件同名私有字段互不覆盖**。插件可通过 `get_plugin_config(plugin_name)` 读取自己的私有配置。
- **`hooks` 生命周期钩子**：可选，声明插件在安装/升级/卸载前后要执行的 shell 命令（见上方示例）。支持 6 个时机：`pre-install` / `post-install` / `pre-update` / `post-update` / `pre-uninstall` / `post-uninstall`，每个时机是命令字符串列表，命令以**插件目录为工作目录**、经 shell 执行（超时 300s）。**`pre-*` 钩子失败会中止对应操作**（安装/升级/卸载不执行，避免半成品状态）；**`post-*` 钩子失败仅警告**，不影响主体操作结果。注意 `post-uninstall` 执行时插件目录已删除，命令工作目录为插件根目录（即 `plugins/`）。
- **安装后免重启生效**：插件安装 / 升级 / 卸载完成后，网关会自动重新扫描 `plugins` 目录并把各插件的扩展点合并进全局配置（`reload_plugin_configs`），因此**无需重启网关进程**，`get_tool_load_dirs` / `get_rules_load_dirs` 等 getter 立即返回最新配置。若因环境异常导致重载失败，仅打印警告，可稍后重启生效。

### 接口版本与向后兼容

插件接口（config.yaml 扩展点、plugin/api.py 私有功能、前端扩展、工具协议）随 Jarvis 演进。为保持**向后兼容**（新 Jarvis 能加载旧插件），引入统一的接口版本声明机制：

- **`api_version` 字段**（可选）：在 config.yaml 顶层声明插件依赖的接口协议版本，**默认 `"1.0"`**。未声明的旧插件按 `"1.0"` 处理，无需改动即可在新 Jarvis 上运行。
- **与插件自身 `version` 区分**：`version` 是插件版本（安装时做版本比较），`api_version` 是接口协议版本（决定插件与 Jarvis 接口的兼容性）。
- **兼容策略**：以主版本号（major）判断。插件声明的 major 不大于当前 Jarvis 支持的接口版本即兼容；声明更高 major 时 Jarvis **降级警告**（不拒绝加载），提示插件可能依赖未来接口能力。
- **废弃流程**：废弃某扩展点字段时，Jarvis 在加载插件时打印 deprecation 警告，通知开发者迁移；字段本身仍保留（旧插件仍可加载），仅提示尽快迁移。
- **覆盖范围**：config.yaml 扩展点（`tool_load_dirs`/`rules_load_dirs`/`orchestration`/`mcp`/`lsp`/`frontend` 等）、plugin/api.py 私有功能（`PUBLIC_FUNCTIONS` 白名单）、工具协议（`protocol_version`，见「工具（tools/）」）。`lsp` 扩展点由接口版本 `1.1` 引入（旧插件未声明 `api_version` 时按 `"1.0"` 处理，仍可正常加载，只是不识别 `lsp` 字段）。`event_callbacks` 扩展点同样由接口版本 `1.1` 引入。`platforms` 扩展点由接口版本 `1.1` 引入。

## 四、扩展点开发规范

### 1. 工具（tools/）

工具文件是 Python 模块。**类名 `name` 必须等于文件名 stem**（否则注册表不加载）。

```python
class MyPluginTool:
    name = "my_plugin_tool"          # 必须等于文件名 stem
    description = "工具描述"
    parameters = {
        "type": "object",
        "properties": {"input": {"type": "string", "description": "输入"}},
        "required": ["input"],
    }

    @staticmethod
    def check() -> bool:
        """工具是否可用（无外部依赖时始终返回 True）。"""
        return True

    def execute(self, args: dict) -> dict:
        """返回 {"success": bool, "stdout": str, "stderr": str}。"""
        try:
            return {"success": True, "stdout": "...", "stderr": ""}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": f"执行异常: {e}"}
```

- 工具运行在 **agent 进程**，由 ToolRegistry 加载，供 Agent 调用。
- 可选 `protocol_version`（默认 `"1.0"`）、`interactive`（True 时要求串行执行）。

### 2. 插件私有功能（plugin/，可选）

插件自己使用的功能实现（API 封装、token 管理、业务纯函数）放在 `plugin/` 目录。

- `plugin/` **不声明在 `tool_load_dirs`**，因此不会被 ToolRegistry 加载，**Agent 看不到、调不到**。
- 运行在 **gateway**（master 进程），供前端代理通过 `POST /api/plugins/{node_id}/function-call` 调用。
- `api.py` 每个功能是纯函数，返回 `{"success": bool, "data"/"message"/"error": ...}`；模块末尾定义 `PUBLIC_FUNCTIONS: list[str]` 白名单，gateway **只允许**调用白名单内函数。
- Agent 工具（`tools/`）应是私有功能的**薄封装**：只做参数解析、调用私有功能、格式化返回。

### 3. 规则（rules/）

Markdown 文件，开头带 YAML front matter：

```yaml
---
name: my_plugin_rule
description: 何时触发该规则（清晰列出触发关键词/场景）。
---
```

规则会被 Agent 自动发现并加载，用于约束相关场景下的行为。

### 4. Agent 定义（agents/，可选）

YAML 格式，需在 `config.yaml` 启用 `agent_definition_dirs`：

```yaml
name: my_agent
description: Agent 角色描述。
system_prompt: |
  你是 my-plugin 插件的专用 Agent。
```

### 5. 编排（orchestration/，可选）

YAML 编排流水线，配合 `OrganizeAgents` 与 `jca -n --task-file` 消费。参考 `builtin/agent_orchestration/` 下的示例格式。

### 6. 前端扩展（frontend/，可选）

前端 JS 是**纯浏览器 ES module**：用 `window.Vue` 渲染，导出 default 组件，**不要 `import 'vue'`**。在 `config.yaml` 的 `frontend` 字段声明 `admin_tabs`/`sidebar_views`/`tool_panels`，每项含 `id`/`title`/`entry`（entry 为 JS 文件名，相对插件 frontend 目录）。

前端通过 `GET /api/plugins/{node_id}/{name}/frontend/{path}` 动态加载插件 JS，用 Blob URL `import()` 加载为 Vue 组件。插件 JS 应**单文件自包含**（不引用相对路径资源），否则 Blob module 无法解析。

#### 6.1 三个扩展点

| 扩展点 | 渲染位置 | 说明 |
|--------|----------|------|
| `admin_tabs` | 管理面板 tab | 在管理面板（AdminPanel）新增一个 tab |
| `sidebar_views` | 工作区侧边栏 | 在活动栏新增入口，view 名为 `plugin:<id>` |
| `tool_panels` | 工作区侧边栏 | 在活动栏新增入口，view 名为 `plugin-tool:<id>`，与 `sidebar_views` 独立 |

#### 6.2 统一 props（宿主自动注入）

宿主在渲染插件组件时会自动注入以下 props（插件组件通过 `props` 声明接收，未声明则忽略）：

```js
export default {
  name: 'MyView',
  props: {
    workingDir: String,   // 当前工作目录
    agentInfo: Object,    // 当前活跃 Agent 信息 { agentId, agentName, workingDir } 或 null
    userInfo: Object,     // 当前登录用户信息 { user_id, username, display_name, is_admin } 或 null
    nodes: Array,         // 节点列表 [{ node_id, status, ... }]
    gatewayUrl: String,   // 网关地址
    fetchWithAuth: Function, // 带认证的 fetch(url, options)
    getHttpProtocol: Function, // () => 'http' | 'https'
    showToast: Function,  // (message, type) 显示 toast
  },
  render(h) {
    return h('div', {}, '插件内容');
  },
};
```

#### 6.3 window.__jarvis* 接口族

插件组件也可通过全局 `window.__jarvis*` 接口访问宿主能力（无需声明 props）：

| 接口 | 签名 | 说明 |
|------|------|------|
| `__jarvisFetch` | `(url, options) => Promise<Response>` | 带认证的 fetch，自动携带 token |
| `__jarvisSendToActiveAgent` | `(text, options) => {success, agentId}` | 向当前活跃 Agent 发送提示词 |
| `__jarvisGetActiveAgentInfo` | `() => {agentId, agentName, workingDir} \| null` | 获取当前活跃 Agent 信息 |
| `__jarvisCreateAgentForTask` | `(options) => Promise<{success, agentId}>` | 创建新 Agent 处理任务 |
| `__jarvisPickDirectory` | `() => Promise<string \| null>` | 打开目录选择弹窗 |
| `__jarvisGetUserInfo` | `() => userInfo \| null` | 获取当前登录用户信息 |
| `__jarvisGetNodes` | `() => Array` | 获取节点列表（数组副本） |
| `__jarvisShowToast` | `(message, type='success')` | 显示 toast 通知 |
| `__jarvisSwitchSidebarView` | `(view) => {success}` | 切换工作区侧边栏视图（内置或 `plugin:<id>`/`plugin-tool:<id>`） |
| `__jarvisOpenPanel` | `(kind) => {success}` | 打开面板/导航（admin/settings/workspace/git/plugins/topology/docs） |
| `__jarvisGetGatewayInfo` | `() => {host, port, protocol}` | 获取当前网关信息 |

#### 6.4 事件订阅

插件可通过 `window.__jarvisOn(event, handler)` 订阅宿主事件，返回取消订阅函数；`window.__jarvisOff(event, handler)` 取消订阅（handler 省略则清空该事件全部订阅）。

```js
const off = window.__jarvisOn('agent_changed', (payload) => {
  // payload: { agentId, agentName, workingDir } 或 null
  console.log('当前 Agent 变化', payload);
});
// 组件卸载时清理
// off();
```

| 事件 | payload | 触发时机 |
|------|---------|----------|
| `agent_changed` | `{agentId, agentName, workingDir} \| null` | 当前活跃 Agent 变化 |
| `token_changed` | `{token}` | token 变化（登出为 null） |
| `user_changed` | `{userInfo} \| null` | 当前用户信息变化 |
| `nodes_changed` | `{nodes}` | 节点列表变化 |

### 7. LSP 语言服务（lsp/，可选）

插件可在 `config.yaml` 声明 `lsp.languages`，为指定语言注册 LSP 服务器。声明会按语言名**深度合并**进全局 `lsp.languages` 配置（与用户手动写在全局 `~/.jarvis/config.yaml` 的 `lsp.languages` 等效），插件安装后免重启生效、卸载后自动撤销，无需用户手动配置。

```yaml
lsp:
  languages:
    python:
      command: "pyright-langserver"
      args: ["--stdio"]
      file_extensions: [".py"]
      root_markers: ["pyproject.toml", "setup.py"]
```

字段说明（与全局 `lsp.languages` 一致，见 LSP 配置文档）：

| 字段 | 说明 |
|------|------|
| `command` | 启动 LSP 服务器的可执行命令（必填） |
| `args` | 传给命令的参数列表 |
| `file_extensions` | 触发该语言服务的文件扩展名列表 |
| `root_markers` | 判定项目根目录的标记文件列表 |
| `enable` | 是否启用（默认 true） |

> **⚠️ 安全提示**：`command` 会在本机启动外部语言服务器进程（与 `mcp` 的 `command` 同级别）。安装插件前请确认插件来源可信、`command` 指向的是预期程序。插件能力展示中会明确标注该提示。
>
> **合并语义**：多插件声明同一语言时按语言名深度合并（`file_extensions`/`args`/`root_markers` 等列表字段追加合并），不同语言互不覆盖；优先级为「项目配置 > 后加载插件 > 前加载插件 > 内置默认」。

### 8. 事件回调（event_callbacks/，可选）

插件可在 `config.yaml` 声明 `event_callbacks`，注册插件自带的事件回调，在 Agent 生命周期事件（任务开始/完成、工具调用前后、模型调用前后、总结前后等）被触发时执行。声明会合并进全局配置，插件安装后免重启生效、卸载后自动撤销。

```yaml
event_callbacks:
  # 形式一：字符串目录（自动探测事件，默认 event_bus）
  - "{{plugin_dir}}/callbacks"
  # 形式二：字典（显式声明事件与注册目标）
  - dir: "{{plugin_dir}}/callbacks"
    events: ["task_started", "task_completed"]
    target: "event_bus"
```

字段说明：

| 字段 | 说明 |
|------|------|
| `dir` | 回调目录绝对路径（必填，用 `{{plugin_dir}}` 占位） |
| `events` | 事件短名列表（可选，缺省时自动探测目录内 .py 文件按文件名匹配） |
| `target` | 注册目标（可选，默认 `event_bus`）：`event_bus` 通知型 / `hook` 拦截型 / `modifier` 修改型 |

**回调文件约定**：目录内每个 `.py` 文件（跳过 `__init__.py`）按文件名前缀匹配事件短名，如 `task_started_cb.py` → `task_started`。文件内按优先级提供回调（任一命中即注册）：

- 模块级可调用对象：`<event>_cb`
- 工厂方法返回单个或多个可调用对象：`get_<event>_cb()` / `register_<event>_cb()`

```python
# callbacks/task_started_cb.py
def task_started_cb(agent, **kwargs):
    """任务开始时被调用（event_bus 通知型）。"""
    print(f"任务开始: {kwargs.get('name', '')}")
```

**事件短名与 target 约束**：

| 事件短名 | 触发时机 | 允许 target |
|----------|----------|-------------|
| `before_tool_call` | 工具调用前 | `event_bus` / `hook` |
| `after_tool_call` | 工具调用后 | `event_bus` |
| `task_started` | 任务开始 | `event_bus` |
| `task_completed` | 任务完成 | `event_bus` |
| `before_summary` | 总结前 | `event_bus` / `modifier` |
| `after_summary` | 总结后 | `event_bus` |
| `before_addon_prompt` | 附加提示前 | `event_bus` |
| `after_addon_prompt` | 附加提示后 | `event_bus` |
| `before_history_clear` | 历史清理前 | `event_bus` |
| `after_history_clear` | 历史清理后 | `event_bus` |
| `before_model_call` | 模型调用前 | `event_bus` / `modifier` |
| `after_model_call` | 模型调用后 | `event_bus` |
| `interrupt_triggered` | 中断触发 | `event_bus` |
| `before_tool_filter` | 工具筛选前 | `event_bus` |
| `tool_filtered` | 工具筛选后 | `event_bus` |

- **`hook`（拦截型）**：仅支持 `before_tool_call`，回调返回 `False` 可拦截工具执行；同时订阅 EventBus 作为通知。
- **`modifier`（修改型）**：仅支持 `before_model_call` / `before_summary`，回调返回修改后的值。
- **`event_bus`（通知型）**：全部 14 个事件均支持，回调在事件触发时被调用，返回值不参与逻辑。
- target 与事件不匹配时（如 `hook` + `task_started`）会**显式告警并跳过**，不会静默降级。

> **与旧字段的关系**：`before_tool_call_cb_dirs` / `after_tool_call_cb_dirs` / `before_model_call_cb_dirs` / `summary_cb_dirs` 四个旧字段仍受支持（向后兼容），`event_callbacks` 是新增的统一入口，两者可共存。

#### 示例：工具调用白名单门禁（拦截型 hook）

下面是一个完整的示例插件，用 `hook` 目标实现**工具调用白名单门禁**：只允许 Agent 调用白名单内的工具，其余一律拦截。插件目录结构：

```text
tool-whitelist/
├── config.yaml
└── callbacks/
    └── before_tool_call_cb.py
```

`config.yaml`（声明回调目录，`target: hook` 表示拦截型）：

```yaml
name: tool-whitelist
description: 工具调用白名单门禁（event_callbacks hook 示例）
version: 0.1.0
license: MIT
event_callbacks:
  - dir: "{{plugin_dir}}/callbacks"
    events: ["before_tool_call"]
    target: "hook"
```

`callbacks/before_tool_call_cb.py`（hook 回调，返回 `False` 拦截工具执行）：

```python
# 工具调用白名单：仅允许这些工具被 Agent 调用
ALLOWED_TOOLS = {"execute_command", "read_file", "write_file"}


def before_tool_call_cb(agent, **kwargs):
    """工具调用前被调用；返回 False 拦截工具执行。"""
    tool_name = kwargs.get("tool_name", "")
    if tool_name not in ALLOWED_TOOLS:
        print(f"🚫 工具 {tool_name} 不在白名单，已拦截")
        return False
    return True
```

安装该插件后，Agent 调用白名单外的工具会被 `hook` 拦截（返回 `工具 xxx 被 hook 拦截`），实现强制权限门禁。回调文件支持 `# requirements:` 头声明额外依赖（如 `# requirements: requests`），加载时会自动安装。

### 9. 模型供应商（platforms/，可选）

插件可在 `config.yaml` 声明 `platforms`，注册插件自带的**模型供应商（Platform）实现**，安装后自动加载到 `PlatformRegistry`，与内置 `openai`/`claude`/`jev` 平台并列可用：

```yaml
platforms:
  - "{{plugin_dir}}/platforms"
```

`platforms` 声明的是**目录列表**（路径用 `{{plugin_dir}}` 占位），目录内为 `BasePlatform` 子类（每个 `.py` 文件一个平台实现），复用现有 `load_platform_from_dir` + `check_platform_implementation` 校验机制（需实现 `chat`/`name`/`delete_chat`/`set_system_prompt`/`set_model_name`/`get_model_list` 等必需方法）。

**典型场景**：新 LLM API、本地模型、代理网关、私有部署模型。第三方模型供应商可做成插件分发，安装即得新模型供应商。

**与全局平台目录的关系**：`platforms` 扩展点声明的目录会**追加**到 `PlatformRegistry` 扫描路径（用户全局 `~/.jarvis/models/` 目录与内置平台目录仍然生效），插件平台与内置/用户平台重名时插件平台**覆盖**（打印告警）。

**卸载撤销**：插件卸载时，其注册的平台会从 `PlatformRegistry` 精确移除（可逆效应，见 `PluginRegistry`）。

## 五、版本管理

### 语义化版本

`config.yaml` 的 `version` 字段使用[语义化版本](https://semver.org/lang/zh-CN/)（如 `1.2.3`），版本比较由 `packaging.version.Version` 完成（见 `_compare_versions`）。

### 覆盖规则

安装到已存在的插件目录时，按版本比较决定是否覆盖：

| 场景 | 行为 |
| --- | --- |
| 新版本 > 已装版本 | 覆盖安装 |
| 新版本 == 已装版本 | 覆盖安装 |
| 新版本 < 已装版本 | **拒绝安装** |
| 任一方无版本号 | 允许覆盖（兼容旧格式插件） |
| `--install-plugin-force` | 忽略版本比较，强制覆盖 |

### 依赖版本约束

`dependencies` 中可声明版本约束（见 `_check_version_constraint`）：

```text
"1.2.0"           精确版本
">=1.2.0"         大于等于
">1.2.0"          大于
"<=1.2.0"         小于等于
"<1.2.0"          小于
"==1.2.0"         精确等于
"*"               任意版本
">=1.0.0,<2.0.0"  区间（逗号分隔，需全部满足）
```

## 六、依赖声明

`config.yaml` 的 `dependencies` 字段支持三类（见 `_check_dependencies`）：

- **plugins**：其他 Jarvis 插件，含 `name`/`version`/可选 `url`/`tag`/`branch`。带 `url` 的插件依赖未安装时**自动下载安装**。
- **python**：Python 包，dict `{包名: 版本约束}` 或 list `[{"name":..., "version":...}]`。
- **commands**：系统命令，list `["git", "jq"]` 或 dict。

依赖不满足时安装会被拒绝；带 `url` 的插件依赖会尝试自动安装（含循环依赖检测）。

## 七、发布流程

### 1. 打包

将插件目录打包为压缩包（支持 `.tar` / `.tar.gz` / `.tgz` / `.zip`）。**压缩包内可直接是插件目录，或包含单个插件目录**（安装时自动识别含 `config.yaml` 的目录）：

```bash
# 推荐：打包插件目录本身，解压后即为 my-plugin/
tar -czf my-plugin-0.1.0.tar.gz -C . my-plugin
```

> 打包前请确认目录内不含 `__pycache__`、`.git` 等无关文件。

### 2. 托管与分发

将压缩包托管到可公开访问的 URL，常见方式：

- **GitHub Release 附件**：`https://github.com/<owner>/<repo>/releases/download/<tag>/my-plugin-0.1.0.tar.gz`
- **GitHub 仓库 archive**：`https://github.com/<owner>/<repo>/archive/refs/tags/<tag>.tar.gz`（tag 触发）
- 任意可下载的 http(s) 直链

### 3. 分发机制（安装时记录来源）

用户通过 URL 安装时，Jarvis 会把来源 URL 写入插件目录的 `.source` 文件，供后续升级使用（见 `install_plugin` / `upgrade_plugin`）：

```bash
jarvis --install-plugin https://github.com/<owner>/<repo>/releases/download/v0.1.0/my-plugin-0.1.0.tar.gz
```

之后用户可一键升级到该来源的最新版：

```bash
jarvis --upgrade-plugin my-plugin
```

> **提示**：若希望升级生效，发布新版本时应更新同一来源 URL 指向的内容（或让 URL 始终指向 latest）。

## 七·五、插件市场

Jarvis 内置「插件市场」浏览功能：客户端从配置的市场仓库拉取结构化插件清单，在插件管理面板的「市场」页签中展示，用户可一键安装社区插件。

### 1. 市场仓库结构

市场仓库含 `plugins/` 目录，**每个插件一个 YAML 文件**（文件名为 `<id>.yaml`），`_` 开头的文件会被客户端当作模板/占位文件跳过（如 `_example.yaml`）：

```text
plugin-market/
├── README.md
└── plugins/
    ├── _example.yaml      # 模板（被跳过）
    ├── my-plugin.yaml     # 真实插件清单
    └── ...
```

### 2. 清单字段规范

```yaml
# plugins/my-plugin.yaml
id: my-plugin          # 唯一标识（必填）
name: 我的插件          # 展示名（可选，缺省用 id）
description: 插件功能说明
repo: https://github.com/<owner>/my-plugin   # 插件源码仓库（git 来源）
branch: main            # 发布分支（可选，默认 main）
author: 作者名
license: MIT
logo: ""                # 图标（可选，URL 或内联 SVG）
categories:             # 分类标签（可选）
  - 工具
  - 效率
```

> **设计原则**：市场清单**不记录版本号**。客户端从插件仓库的 git HEAD 获取最新版本（与升级检测机制自洽），避免清单与仓库版本不同步。

### 3. 提交插件到市场

1. 在官方市场仓库（`skyfireitdiy/plugin-market`）`plugins/` 目录下新增 `<id>.yaml`；
2. 通过 PR 提交，经审核合并后即对全体用户可见；
3. 客户端每次打开「市场」页签会拉取市场仓库最新清单（有本地缓存，离线可用）。

### 4. 配置多市场源

`config.yaml` 的 `plugin_market_repos` 支持配置多个市场仓库（默认仅官方市场）：

```yaml
plugin_market_repos:
  - https://github.com/skyfireitdiy/plugin-market
```

## 八、安装与卸载（用户视角）

| 命令 | 说明 |
| --- | --- |
| `jarvis --install-plugin <路径或URL>` | 安装插件：目录、`.tar`/`.tar.gz`/`.tgz`/`.zip` 或 http(s) URL |
| `jarvis --install-plugin-force <路径或URL>` | 强制覆盖已安装插件（忽略版本比较） |
| `jarvis --upgrade-plugin <名称>` | 升级：重新下载该插件记录来源 URL 的最新版（仅 URL 安装的插件） |
| `jarvis --uninstall-plugin <名称>` | 卸载插件（内置插件不可卸载，会拒绝） |
| `jarvis --list-plugins` | 列出所有已安装插件 |

- 插件名从 `config.yaml` 的 `name` 字段获取，若无则使用目录名/文件名。
- 卸载遵循可逆效应：撤销该插件注册的工具/规则等资源。

## 九、贡献流程（开源协作）

欢迎将你的插件贡献到社区。遵循标准的 Fork & Pull Request 工作流（详见 [参与贡献](jarvis_book/7.参与贡献.md) 与仓库根 `CONTRIBUTING.md`）：

1. **Fork** 本仓库并创建特性分支（如 `feat/plugin-<name>`），**不要直接向 `main` 提交**：

   ```bash
   gh repo fork skyfireitdiy/Jarvis --clone   # fork 并 clone；fork 成为 origin，原仓库变为 upstream
   cd Jarvis
   git checkout -b feat/plugin-<name>
   ```

2. 在分支上新增/修改插件（建议放在 `builtin/plugins/<name>/` 或独立插件仓库）。
3. 本地验证通过后提交，提交信息遵循规范（`feat:` / `fix:` / `docs:` 等）。
4. 推送分支并创建 Pull Request，描述需包含：背景、改动清单、验证方式：

   ```bash
   git push -u origin feat/plugin-<name>
   gh pr create --repo skyfireitdiy/Jarvis --base main \
     --head <你的用户名>:feat/plugin-<name> \
     --title "feat(plugin): 新增 <name> 插件" --body-file <描述文件>
   ```

5. 若解决某个 Issue，在 PR 描述中用 `Closes #<编号>` 关联。
6. 等待维护者审查与合并。

> **保持 fork 同步**：上游有新提交时，可用 `gh repo sync <你的用户名>/Jarvis` 将 fork 与上游同步。

## 十、验证检查清单

- [ ] `config.yaml` 存在且含 `name`/`description`/`version`
- [ ] 扩展点路径用 `{{plugin_dir}}` 占位，未写死绝对路径
- [ ] 工具类 `name` 等于文件名 stem，实现 `check()` 与 `execute()`
- [ ] 规则文件带 YAML front matter（`name`/`description`）
- [ ] 前端 JS 用 `window.Vue`，未 `import 'vue'`，单文件自包含
- [ ] `plugin/api.py` 定义 `PUBLIC_FUNCTIONS` 白名单（若使用私有功能）
- [ ] 依赖声明格式正确（plugins/python/commands）
- [ ] `py_compile` 通过，`config.yaml` 可被 yaml 解析
- [ ] 安装成功：`jarvis --install-plugin <路径>`
- [ ] 卸载可逆：`jarvis --uninstall-plugin <名称>` 能撤销注册的资源

## 相关代码位置

- 插件注册追踪：`src/jarvis/jarvis_tools/plugin_registry.py`（PluginRegistry，可逆效应事实来源）
- 工具加载：`src/jarvis/jarvis_tools/registry.py`（`register_tool_by_file` / `_infer_source_plugin`）
- 插件脚手架/安装/卸载/列表/升级：`src/jarvis/jarvis_agent/utils.py`（`scaffold_plugin` / `install_plugin` / `uninstall_plugin` / `list_plugins` / `upgrade_plugin`）
- 插件 config 合并：`src/jarvis/jarvis_utils/utils.py`（`_load_plugin_configs`）
- 模板渲染：`src/jarvis/jarvis_utils/template_utils.py`（`render_plugin_config_template`）
- 扩展点目录读取：`src/jarvis/jarvis_utils/config.py`
- 前端扩展加载：`src/jarvis/jarvis_service/frontend/src/pluginExtensions.js`
- CLI 命令：`src/jarvis/jarvis_agent/jarvis.py`
