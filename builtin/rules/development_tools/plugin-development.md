---
name: plugin-development
description: 当需要开发、编写或维护 Jarvis 插件时触发。每当用户提及"插件开发"、"编写插件"、"开发插件"、"内置插件"、"新建插件"、"jarvis插件"、"gh插件"时触发。不触发：仅安装/卸载已有插件（用 CLI 命令即可）；开发 Skill（用 skill-development 规则）；开发 Agent（不涉及插件）。
---

# Jarvis 插件开发规则

此规则定义了 Jarvis 插件的标准化开发流程与规范，确保插件符合加载约定、可被正确注册与卸载、具备可维护性。

## 插件系统概述

Jarvis 插件是**按目录组织的可扩展单元**，通过 `config.yaml` 声明各扩展点（工具/规则/Agent/编排/前端），运行时由 Jarvis 自动加载并注册。插件资源遵循**可逆效应**（Cordis 理念）：加载时显式登记到 `PluginRegistry`，卸载时按登记精确撤销，实现 register/unregister 完全对称。

**两类插件：**

- **内置插件**：位于源码 `builtin/plugins/<name>/`，config.yaml 声明 `builtin: true`，不复制、不可卸载/升级。
- **外部插件**：位于 `<data_dir>/plugins/<name>/`（默认 `~/.jarvis/plugins/`），可安装/升级/卸载。

## 插件目录结构

```text
<plugin_name>/
├── config.yaml          # 必填：插件配置（name/version + 扩展点声明）
├── README.md            # 推荐：开发者文档
├── plugin/              # 可选：插件私有功能（运行在 gateway，不暴露给 Agent）
├── rules/               # 可选：规则（Markdown，带 YAML front matter）
├── tools/               # 可选：Agent 工具（Python 模块，class XxxTool）
├── agents/              # 可选：Agent 定义（YAML）
├── orchestration/       # 可选：编排流水线（YAML）
└── frontend/            # 可选：前端扩展（纯浏览器 ES module，用 window.Vue）
```

> **工具分两类，物理隔离**：`plugin/` 是插件私有功能（运行在 gateway，供前端代理调用，**不暴露给 Agent**）；`tools/` 是 Agent 工具（运行在 agent 进程，供 Agent 调用）。详见下文「工具（tools/）」与「插件私有功能（plugin/）」。

## config.yaml 字段规范

```yaml
---
name: my-plugin # 必填：插件唯一标识（目录名、工具/规则命名依据）
description: 插件描述。 # 必填：功能说明
version: 0.1.0 # 版本号（安装时做版本比较）
license: MIT # 开源协议
builtin: true # 内置插件标记（外部插件不写）
# --- 扩展点（路径用 {% raw %}{{plugin_dir}}{% endraw %} 占位，运行时由 jinja2 自动渲染为插件绝对路径）---
rules_load_dirs:
  - "{% raw %}{{plugin_dir}}{% endraw %}/rules"
tool_load_dirs:
  - "{% raw %}{{plugin_dir}}{% endraw %}/tools"
# agent_definition_dirs:
#   - "{% raw %}{{plugin_dir}}{% endraw %}/agents"
# --- 编排流水线声明（配合 OrganizeAgents + --task-file 消费）---
orchestration:
  - name: "my-pipeline"
    description: "流水线描述"
    file: "{% raw %}{{plugin_dir}}{% endraw %}/orchestration/my_pipeline.yaml"
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
# --- 自定义能力清单（可选，前端展示用）---
# capabilities:
#   - name: "事件钩子 xxx"
#     description: "说明该能力"
---
```

**字段要点：**

- `{% raw %}{{plugin_dir}}{% endraw %}` 是 jinja2 模板变量，运行时被渲染为插件目录绝对路径（见 `render_plugin_config_template`），**勿**写死绝对路径。
- `orchestration` 每项含 `name`/`description`/`file`，file 路径含 `plugins/<name>/` 时自动反推来源插件名。
- `capabilities` 顶层字段用于声明事件钩子、@内置命令等自定义能力，与自动推导的能力（rules/tools/agents/orchestration/frontend）合并展示。
- 插件 config 会被 `_load_plugin_configs` 读取、渲染并 `_deep_merge` 进全局配置，因此 `rules_load_dirs`/`tool_load_dirs` 等字段会被 `get_rules_load_dirs()`/`get_tool_load_dirs()` 等消费。
- **私有配置隔离**：插件 config.yaml 中**除扩展点字段**（`tool_load_dirs`/`rules_load_dirs`/`agent_definition_dirs`/`orchestration`/`roles_dirs`/`before_tool_call_cb_dirs`/`after_tool_call_cb_dirs`/`before_model_call_cb_dirs`/`summary_cb_dirs`/`builtin_input_handler_dirs`）外的其余字段（`name`/`description`/`version`/`builtin`/`license`/`dependencies`/`capabilities`/`frontend`/自定义业务字段）会被隔离到全局配置的 `plugin_configs.<plugin_name>` 单独配置项，**不污染全局配置顶层、多个插件同名私有字段互不覆盖**。插件可通过 `get_plugin_config(plugin_name)` / `get_all_plugin_configs()`（`jarvis.jarvis_utils.config`）读取自己的私有配置。

## 扩展点开发规范

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
            # 实现逻辑
            return {"success": True, "stdout": "...", "stderr": ""}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": f"执行异常: {e}"}
```

**要点：**

- 类需具备 `name`/`description`/`parameters`/`execute` 属性，且 `item.name == 文件名 stem` 才会被 `register_tool_by_file` 加载。
- 可选 `protocol_version`（默认 "1.0"）、`interactive`（True 时要求串行执行）。
- 工具路径含 `plugins/<name>/` 时，`_infer_source_plugin` 自动反推来源插件名并登记到 `PluginRegistry`，卸载时精确撤销。
- **运行环境**：Agent 工具运行在 **agent 进程**，由 ToolRegistry 加载，供 Agent 调用。工具类应尽量是私有功能的薄封装（见下节）。

### 2. 插件私有功能（plugin/，可选）

插件自己使用的功能实现（如 API 封装、token 管理、业务纯函数）放在 `plugin/` 目录（如 `plugin/api.py`）。

**关键约束：**

- `plugin/` **不声明在 `tool_load_dirs`**，因此不会被 ToolRegistry 加载，**Agent 看不到、调不到**。
- **运行环境**：插件私有功能运行在 **gateway**（master 进程），供前端代理调用。
- gateway 前端代理通过 `POST /api/plugins/{node_id}/function-call` 调用私有功能（请求体 `{plugin, function, arguments}`），**只允许**调用模块内 `PUBLIC_FUNCTIONS` 白名单里的函数。
- Agent 工具（tools/）是私有功能的**薄封装**：只做参数解析、调用私有功能、格式化返回 `{"success","stdout","stderr"}`。

**api.py 约定：**

- 每个功能是纯函数，返回 dict：`{"success": bool, "data": ... / "message": ... / "error": ...}`。
- 模块末尾定义 `PUBLIC_FUNCTIONS: list[str]` 白名单，gateway 只允许调用白名单内函数（防任意函数被调用）。
- 工具类通过 importlib 按文件路径加载 `plugin/api.py`（因 `plugin/` 不在 sys.path），用 `importlib.util.spec_from_file_location` 加载并缓存，供工具类薄封装调用。

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

YAML 格式，需在 config.yaml 启用 `agent_definition_dirs`：

```yaml
name: my_agent
description: Agent 角色描述。
system_prompt: |
  你是 my-plugin 插件的专用 Agent。
```

### 5. 编排（orchestration/，可选）

YAML 编排流水线，配合 `OrganizeAgents` 与 `jca -n --task-file` 消费。参考 `builtin/agent_orchestration/` 下的示例格式。

### 6. 前端扩展（frontend/，可选）

前端 JS 是**纯浏览器 ES module**：用 `window.Vue` 渲染，导出 default 组件，**不要 `import 'vue'`**。在 config.yaml 的 `frontend` 字段声明 `admin_tabs`/`sidebar_views`/`tool_panels`，每项含 `id`/`title`/`entry`（entry 为 JS 文件名，相对插件 frontend 目录）。

前端通过 `GET /api/plugins/{node_id}/{name}/frontend/{path}` 动态加载插件 JS（后端返回 JSON 包裹的 content），用 Blob URL `import()` 加载为 Vue 组件。插件 JS 应**单文件自包含**（不引用相对路径资源），否则 Blob module 无法解析。

## 开发流程

1. **生成脚手架**：`jarvis --new-plugin <name>`（可加 `--plugin-output-dir <dir>`），生成符合加载约定的完整骨架（config.yaml/README/rules/tools/agents/orchestration/frontend）。
2. **按需实现扩展点**：编辑 config.yaml 声明扩展点，在对应目录实现工具/规则/Agent/编排/前端。
3. **本地验证**：
   - 工具类名与文件名 stem 一致；`execute` 返回 `{"success","stdout","stderr"}`。
   - 规则带 YAML front matter（name/description）。
   - config.yaml 可被 yaml 解析，`{% raw %}{{plugin_dir}}{% endraw %}` 占位正确。
   - 用 `py_compile` 或实际导入验证工具模块语法正确。
4. **安装**：`jarvis --install-plugin <path>`（path 可为目录、tar/tar.gz/tgz/zip 或 http(s) URL）。带 URL 安装会记录来源，供 `--upgrade-plugin` 升级。
5. **查看**：`jarvis --list-plugins` 列出已安装插件。
6. **卸载**：`jarvis --uninstall-plugin <name>`（内置插件不可卸载，会拒绝）。

## 依赖规范

config.yaml 的 `dependencies` 字段支持三类（见 `_check_dependencies`）：

- **plugins**：其他 Jarvis 插件，含 `name`/`version`/可选 `url`/`tag`/`branch`。带 url 的插件依赖未安装时自动下载安装。
- **python**：Python 包，dict `{包名: 版本约束}` 或 list `[{"name":..., "version":...}]`。
- **commands**：系统命令，list `["git", "jq"]` 或 dict。

依赖不满足时安装会被拒绝；带 url 的插件依赖会尝试自动安装。

## 内置插件规范

- 位于 `builtin/plugins/<name>/`，config.yaml 声明 `builtin: true`。
- 内置插件**不可卸载、不可升级**（`uninstall_plugin` 会防御性拒绝）。
- 若某插件名同时存在于内置目录与数据目录，以内置为准（跳过数据目录副本）。

## 验证检查清单

- [ ] config.yaml 存在且含 `name`/`description`/`version`
- [ ] 扩展点路径用 `{% raw %}{{plugin_dir}}{% endraw %}` 占位，未写死绝对路径
- [ ] 工具类 `name` 等于文件名 stem，实现 `check()` 与 `execute()`
- [ ] 规则文件带 YAML front matter（name/description）
- [ ] 前端 JS 用 `window.Vue`，未 `import 'vue'`，单文件自包含
- [ ] 依赖声明格式正确（plugins/python/commands）
- [ ] `py_compile` 通过，config.yaml 可解析
- [ ] 安装成功：`jarvis --install-plugin <path>`
- [ ] 卸载可逆：`jarvis --uninstall-plugin <name>` 能撤销注册的资源

## 相关代码位置

- 插件注册追踪：`src/jarvis/jarvis_tools/plugin_registry.py`（PluginRegistry，可逆效应事实来源）
- 工具加载：`src/jarvis/jarvis_tools/registry.py`（`register_tool_by_file`/`_infer_source_plugin`）
- 插件脚手架/安装/卸载/列表：`src/jarvis/jarvis_agent/utils.py`（`scaffold_plugin`/`install_plugin`/`uninstall_plugin`/`list_plugins`/`list_plugins_info`）
- 插件 config 合并：`src/jarvis/jarvis_utils/utils.py`（`_load_plugin_configs`）
- 模板渲染：`src/jarvis/jarvis_utils/template_utils.py`（`render_plugin_config_template`）
- 扩展点目录读取：`src/jarvis/jarvis_utils/config.py`（`get_tool_load_dirs`/`get_rules_load_dirs`/`get_agent_definition_dirs`/`get_plugin_orchestrations`）
- 前端扩展加载：`src/jarvis/jarvis_service/frontend/src/pluginExtensions.js`
- CLI 命令：`src/jarvis/jarvis_agent/jarvis.py`
