# 前端插件扩展设计方案（方案1 + 方案2）

> 状态：管理员已确认方向（按节点管理 + 扩展点自设计尽量覆盖全 + 安全性暂不考虑）
> 日期：2026-10-07
> 回退点：`7a7506376e7d464cf62ea9e7230947783fdedf59`

## 背景

管理员批准"方案1 和方案2 都要做"，并明确：

1. **插件管理是按节点管理的**（每个节点有自己的插件集合，管理需按节点维度）
2. **扩展点由我设计，尽量覆盖全、功能尽量完善，安全性暂不考虑**

前置已完成：插件可逆效应（PluginRegistry，卸载时撤销工具/规则）。

## 现状摸底（已验证事实）

**后端插件管理函数**（`src/jarvis/jarvis_agent/utils.py`）：

- `install_plugin(source_path, force, source_url, _installing_deps)`（:556）
- `list_plugins()`（:868，只打印控制台，不返回结构化数据）
- `uninstall_plugin(plugin_name)`（:923，卸载前调 PluginRegistry.revoke_plugin）
- `upgrade_plugin(plugin_name)`（:979）
- 插件目录：`<data_dir>/plugins/<name>/`（每个节点自己的 data_dir）

**后端 web_gateway（app.py）**：

- 无插件相关 HTTP API
- 管理端点模式：`verify_token` + `_check_permission` + `{"success": True/False, "data": ...}`
- **节点代理**：`node_http_proxy`（:4554）处理 `/api/node/{node_id}/{path}`，目前支持 `agent/` 和 `http_proxy/` 前缀
- **节点执行**：`node_exec`（:4398）在指定节点执行命令（本地直接 / 远程 `send_request_to_node`）
- **节点协议**：`node_protocol.py` 定义消息类型；`node_manager.py`（:194-318）分发处理，子节点本地处理各 request

**前端（src/jarvis/jarvis_service/frontend/）**：

- 单页应用，无 vue-router，vite build 静态产物，`npm run preview` serve
- `AdminPanel.vue`（4 tab：users/groups/system/config，`activeTab` + `switchTab`，:399）
- 侧边栏 view：agents/files/search/manage/timers/git/目录树（`workspaceSidebarView` ref）
- `buildNodeHttpUrl`（App.vue:2428）生成 `/api/node/{node_id}/{path}` 访问任意节点
- `fetchWithAuth`（App.vue:2327）带 Bearer token 调后端
- 测试：vitest + node test；构建：vite build
- 前端未暴露全局 Vue；node_modules 有 `vue.global.js`

**关键机制**：`PrettyOutput` 有 **Sink 机制**（`add_sink`/`remove_sink`，output.py:873/879，`emit_output` 广播到所有 sink）。API 层可注册自定义 sink 捕获 install_plugin 等函数的输出，无需改动这些函数。

## 方案1：插件管理界面（按节点）

### 后端：节点协议新增插件管理消息

**node_protocol.py** 新增：

```python
PLUGIN_MANAGE_REQUEST = "plugin_manage_request"
PLUGIN_MANAGE_RESPONSE = "plugin_manage_response"
```

**node_manager.py** 分发逻辑新增分支，子节点本地处理插件管理操作：

- `_handle_plugin_manage_request(message)`：根据 `action`（list/install/uninstall/upgrade）调用 `jarvis_agent/utils.py` 对应函数，返回结构化 JSON
- list → `list_plugins_info()`（新增，返回结构化数据）
- install → `install_plugin(source, force)`，用 Sink 捕获输出
- uninstall → `uninstall_plugin(name)`
- upgrade → `upgrade_plugin(name)`

### 后端：master 插件管理 API（app.py）

**`node_http_proxy` 扩展 `plugins/` 前缀**：把 `/api/node/{node_id}/plugins/...` 转发到目标节点执行。

**master 本地插件管理 API**（`/api/plugins/...`，`verify_token` + `admin:plugins` 权限）：
| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/plugins?node_id=xxx` | 列出指定节点插件 |
| POST | `/api/plugins/install?node_id=xxx` | 在指定节点安装 `{source, force}` |
| POST | `/api/plugins/{name}/uninstall?node_id=xxx` | 卸载指定节点插件 |
| POST | `/api/plugins/{name}/upgrade?node_id=xxx` | 升级指定节点插件 |

`node_id` 默认 `master`。master 本地直接调函数；远端通过 `send_request_to_node(node_id, PLUGIN_MANAGE_REQUEST, ...)` 转发。

**`jarvis_agent/utils.py` 新增 `list_plugins_info() -> list[dict]`**：返回结构化插件信息（name/description/version/dependencies/frontend），保留原 `list_plugins()` 不动。

### 前端：AdminPanel 新增"插件管理"tab + 节点选择器

- 新增第 5 个 tab「插件管理」（`activeTab === 'plugins'`）
- **节点选择器**：列出所有在线节点（含 master），选择后管理该节点插件
- 功能：列出/安装（source + force）/卸载（确认 + 触发撤销）/升级
- 用 `buildNodeHttpUrl` + `fetchWithAuth` 调后端（带 node_id）

## 方案2：插件扩展前端（覆盖全扩展点）

### 核心思路

前端是 vite 构建的静态产物，插件无法参与构建。插件前端扩展采用**运行时动态加载**：

- 插件 config.yaml 声明 `frontend` 扩展点
- 后端按节点 serve 插件前端资源
- 前端启动时拉取扩展清单，动态 `import()` 插件 JS，用 Vue 动态组件渲染

### 扩展点类型（尽量覆盖全）

插件 config.yaml 的 `frontend` 字段声明扩展点列表，每个扩展点有 `type`：

```yaml
name: my-plugin
version: 0.1.0
frontend:
  # 1. 管理面板新增 tab（AdminPanel）
  admin_tabs:
    - id: my-panel
      title: 我的面板
      entry: frontend/my-panel.js
  # 2. 工作区侧边栏新增 view
  sidebar_views:
    - id: my-view
      title: 我的视图
      entry: frontend/my-view.js
  # 3. 工具面板扩展
  tool_panels:
    - id: my-tool
      title: 我的工具
      entry: frontend/my-tool.js
```

### 插件前端 JS 格式

纯浏览器 ES module，**通过全局 `window.Vue` 使用 Vue**（不 import 'vue'，避免 npm 模块解析），导出 Vue 组件定义（用渲染函数，兼容运行时构建）：

```js
// frontend/my-panel.js
export default {
  name: "MyPanel",
  render(h) {
    return h("div", { class: "my-panel" }, "插件面板内容");
  },
};
```

### 后端改动

1. **`GET /api/plugins`** 返回每个插件的 `frontend` 扩展声明（含 node_id）
2. **`GET /api/plugins/{node_id}/{name}/frontend/{path}`**：从指定节点 serve 插件前端资源（ES module JS），设置 Content-Type `application/javascript`；远端节点通过 `PLUGIN_MANAGE_REQUEST` 的 `action=serve_frontend` 或节点 HTTP 代理返回文件内容

### 前端改动

1. **main.js 暴露全局 Vue**：`import * as Vue from 'vue'; window.Vue = Vue`
2. **新增扩展加载器**（`pluginExtensions.js`）：
   - 启动时调 `GET /api/plugins` 获取扩展清单
   - 对每个扩展，用 `import(url)` 动态加载插件 JS（url 指向后端 serve 端点）
   - 缓存加载的组件
3. **AdminPanel 渲染动态 tab**：从扩展清单构建动态 tab，用 `<component :is>` 渲染
4. **侧边栏动态 view**：从扩展清单构建侧边栏 view 入口，渲染插件组件

## 涉及文件清单

**后端**：

- `src/jarvis/jarvis_web_gateway/node_protocol.py`：新增 2 个消息类型
- `src/jarvis/jarvis_web_gateway/node_manager.py`：新增 `_handle_plugin_manage_request`
- `src/jarvis/jarvis_web_gateway/app.py`：新增插件管理 API + node_http_proxy 扩展 plugins/ 前缀
- `src/jarvis/jarvis_agent/utils.py`：新增 `list_plugins_info()`

**前端**：

- `src/jarvis/jarvis_service/frontend/src/main.js`：暴露 window.Vue
- `src/jarvis/jarvis_service/frontend/src/components/AdminPanel.vue`：新增插件管理 tab + 动态插件 tab
- `src/jarvis/jarvis_service/frontend/src/App.vue`：侧边栏动态 view
- 新增 `src/jarvis/jarvis_service/frontend/src/pluginExtensions.js`（扩展加载器）

**测试**：

- 后端：pytest 覆盖插件管理 API + list_plugins_info + 节点协议
- 前端：vitest 覆盖扩展加载器 + AdminPanel 插件 tab + 侧边栏动态 view

## 验证与回滚

- 前端：`npm run test:vitest` + `npm run test:node` + `vite build` 全绿
- 后端：`ruff check` + `ty` + 相关 pytest
- 真实安装/卸载用 `JARVIS_DATA_DIR` 隔离
- 回退点：`7a7506376e7d464cf62ea9e7230947783fdedf59`
