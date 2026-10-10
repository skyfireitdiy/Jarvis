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
# --- 扩展点（路径用 {{plugin_dir}} 占位，运行时由 jinja2 自动渲染为插件绝对路径）---
rules_load_dirs:
  - "{{plugin_dir}}/rules"
tool_load_dirs:
  - "{{plugin_dir}}/tools"
# agent_definition_dirs:
#   - "{{plugin_dir}}/agents"
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
---
```

**要点：**

- `{{plugin_dir}}` 是 jinja2 模板变量，运行时渲染为插件目录绝对路径（见 `render_plugin_config_template`），**勿**写死绝对路径。
- 除扩展点字段外的其余字段（`name`/`description`/`version`/`builtin`/`license`/`dependencies`/`capabilities`/`frontend`/自定义业务字段）会被隔离到全局配置的 `plugin_configs.<plugin_name>`，**不污染全局配置顶层、多个插件同名私有字段互不覆盖**。插件可通过 `get_plugin_config(plugin_name)` 读取自己的私有配置。

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
