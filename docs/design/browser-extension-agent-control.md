# 浏览器插件方案：让 Agent 操作用户真实浏览器

> 状态：设计草案
> 目标：让 Agent 能够操作用户**本地真实浏览器**中**任意网页**（复用登录态、Cookie、已打开标签页）
> 关联模块：`jarvis_web_gateway`、`jarvis_browser`、`jarvis_tools`

---

## 1. 背景与问题

### 1.1 现状

Jarvis 现有的浏览器能力由 `jarvis-browser`（CLI 名 `jb`）提供，实现位于 `src/jarvis/jarvis_browser/cli.py`。

关键事实（已核实）：

- `cli.py:1788` 使用 `_playwright_context.chromium.launch(headless=headless)` 启动一个**全新的独立 Chromium 实例**。
- `cli.py:1798` 仅调用 `browser.new_context()`，**没有** `user_data_dir`、**没有** `launch_persistent_context`、**没有** `storage_state`。
- `cli.py:837-848` daemon 通过 `os.fork()` + `os.setsid()` 双重 fork 脱离终端，运行在**服务端后台**。
- 全代码库**无任何** CDP / `connect_over_cdp` / 扩展通信机制。

### 1.2 根本局限

`jb` 操作的是"**服务器上凭空开的一个浏览器**"：

- 与用户桌面上的浏览器**毫无关系**；
- 不共享用户的登录态、Cookie、书签、已打开标签页；
- 所谓 "UI 模式" 也只是在**跑 Agent 的那台机器**上开窗口，用户可能隔着网络，看不到也摸不到。

因此 `jb` **无法满足**"操作用户自己的网页"这一需求。

### 1.3 目标

| 项       | 要求                                                   |
| -------- | ------------------------------------------------------ |
| 操作对象 | 用户本地真实浏览器中**当前打开的任意标签页**           |
| 登录态   | 直接复用用户已有 Cookie / Session，无需重新登录        |
| 覆盖范围 | 任意 `http(s)` 网页                                    |
| 触发方式 | Agent 通过工具下发指令，用户在浏览器中看到实时操作效果 |
| 安全     | 用户显式安装并授权；指令可审计；敏感操作可控           |

### 1.4 非目标

- 不替代 `jb`：`jb` 仍适用于"无登录态、服务端批量抓取/测试"场景。
- 不追求操作 `chrome://*`、扩展商店等浏览器受保护页面。
- 不做静默安装或绕过用户授权。

---

## 2. 方案总览

### 2.1 核心思路

把**执行体**从"服务端 Playwright"换成"**用户浏览器内部的扩展**"：

```text
┌──────────────────────────── 服务端（Jarvis 网关）────────────────────────────┐
│  Agent (code agent / chat agent)                                            │
│     │ 调用工具 browser_ext_*                                                 │
│     ▼                                                                        │
│  BrowserExtensionManager  ── 会话注册 / 指令路由 / 结果回传                  │
│     │                                                                        │
│  WebSocket 端点  /api/browser-ext/ws                                         │
└─────┼────────────────────────────────────────────────────────────────────────┘
      │  WebSocket (wss/ws)
      │  用户浏览器主动连出（NAT 友好，无需公网暴露用户端口）
      ▼
┌──────────────────────────── 用户本地浏览器 ──────────────────────────────────┐
│  Chrome/Edge 扩展 (Manifest V3)                                              │
│   ├─ background service worker  ← 消息桥 + 指令执行器                        │
│   ├─ content script（按需注入）  ← DOM 读取 / 事件派发                        │
│   └─ popup / options            ← 连接配置、授权、会话状态                     │
│                                                                              │
│  chrome.tabs / chrome.scripting / chrome.debugger  →  用户真实标签页          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 为什么可行

1. **扩展运行在用户浏览器进程内**，天然拥有当前登录态、Cookie 与全部标签页。
2. `chrome.tabs` + `chrome.scripting.executeScript` 可对任意 `http(s)` 页面读写 DOM、派发事件。
3. 网关已有成熟的 WebSocket 基础设施（`app.py:2896` `/ws`、`app.py:2904` `/ws/node`），新增一条插件专用端点即可复用同一套鉴权与连接管理范式。
4. 浏览器**主动连出**到网关，用户侧无需开放端口、无需公网 IP。

### 2.3 与 `jb` 的对比

| 维度            | `jb`（Playwright）         | 浏览器插件（本方案）                |
| --------------- | -------------------------- | ----------------------------------- |
| 浏览器实例      | 服务端新建，干净           | 用户真实浏览器                      |
| 登录态 / Cookie | 无                         | 直接复用                            |
| 标签页          | 新建空白页                 | 用户当前标签页                      |
| 用户可见性      | 服务端窗口，用户通常看不到 | 用户眼前实时可见                    |
| 覆盖范围        | 任意网页                   | 任意 `http(s)` 网页（受保护页除外） |
| 安装成本        | 已可用                     | 需开发 + 用户手动安装               |
| 多用户          | 共享服务端环境             | 天然按用户隔离                      |

---

## 3. 组件设计

### 3.1 浏览器扩展（客户端）

#### 3.1.1 目录结构

```text
browser_extension/
├── manifest.json
├── background/
│   ├── service_worker.js      # 入口：连接管理 + 指令分发
│   ├── ws_client.js           # WebSocket 连接、心跳、重连
│   ├── command_router.js      # 指令 → 执行器映射
│   └── executors/
│       ├── tab_executor.js    # tabs 相关（list/activate/close/navigate）
│       ├── dom_executor.js    # DOM 相关（query/click/type/getText）
│       ├── script_executor.js # 任意 JS 执行
│       └── capture_executor.js# 截图 / 抓取
├── content/
│   └── content_script.js      # 页面内 DOM 操作（按需注入）
├── popup/
│   ├── popup.html             # 连接配置、状态显示、授权开关
│   └── popup.js
└── icons/
```

#### 3.1.2 manifest.json 要点

```json
{
  "manifest_version": 3,
  "name": "Jarvis Browser Bridge",
  "version": "0.1.0",
  "permissions": ["tabs", "scripting", "activeTab", "storage", "debugger"],
  "host_permissions": ["<all_urls>"],
  "background": {
    "service_worker": "background/service_worker.js",
    "type": "module"
  },
  "action": { "default_popup": "popup/popup.html" },
  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": ["content/content_script.js"],
      "run_at": "document_idle",
      "all_frames": false
    }
  ]
}
```

说明：

- `host_permissions: <all_urls>` 是覆盖任意网页的前提，安装时用户会看到明确授权提示。
- `debugger` 权限为**可选增强**：启用后可用 `chrome.debugger`（CDP）做更底层的操作（如真实鼠标轨迹、网络拦截、跨域 iframe）。默认不启用，作为后续阶段能力。
- `content_scripts` 也可改为**按需注入**（`chrome.scripting.executeScript`），减少对用户浏览的干扰；两种方式在实现时二选一或并存。

#### 3.1.3 连接管理（ws_client.js）

- 用户在 popup 中填写网关地址（如 `wss://jvs-ai.cn`）与 token。
- 连接 URL：`{gateway}/api/browser-ext/ws`。
- 鉴权复用现有子协议范式（见 `app.py:7649` `_extract_auth_from_headers`）：
  `new WebSocket(url, ['jarvis-ext', 'jarvis-token.<urlencoded-token>'])`。
- 心跳：每 20s 发送 `{"type":"ping"}`，服务端回 `{"type":"pong"}`；连续 2 次无响应则重连。
- 重连：指数退避（1s → 2s → 4s … 上限 30s）。
- 断线期间指令不缓存（避免过期指令误操作），由 Agent 侧感知失败。

#### 3.1.4 指令执行（command_router.js）

统一消息信封：

```json
{
  "id": "req-<uuid>",
  "type": "command",
  "action": "dom.click",
  "params": { "selector": "#submit", "tab_id": 123 },
  "timeout_ms": 15000
}
```

响应信封：

```json
{
  "id": "req-<uuid>",
  "type": "result",
  "success": true,
  "data": { "ok": true },
  "error": null
}
```

### 3.2 网关侧（服务端）

#### 3.2.1 新增模块 `browser_extension_manager.py`

职责：

- 维护插件连接注册表：`session_id → {websocket, user_id, client_id, tabs_meta, connected_at}`
- 指令路由：`send_command(session_id, action, params) → result`（带超时）
- 结果回传：通过 `asyncio.Future` 按 `id` 匹配响应
- 会话生命周期：连接/断开事件、心跳超时清理

核心接口（伪代码）：

```python
class BrowserExtensionManager:
    async def handle_extension_websocket(self, websocket: WebSocket) -> None: ...
    async def send_command(self, session_id: str, action: str,
                           params: dict, timeout: float = 15.0) -> dict: ...
    def list_sessions(self, user_id: str | None = None) -> list[dict]: ...
    async def disconnect(self, session_id: str) -> None: ...
```

#### 3.2.2 新增 WebSocket 端点

在 `app.py` 中，参照 `app.py:2904` `/ws/node` 的写法新增：

```python
@app.websocket("/api/browser-ext/ws")
async def browser_ext_websocket_endpoint(websocket: WebSocket) -> None:
    await browser_extension_manager.handle_extension_websocket(websocket)
```

鉴权流程复用 `_extract_auth_from_headers`（`app.py:7649`）+ `gateway._check_auth`（`gateway.py:63`），与 `app.py:2927-2937` 的 `/api/agent/{agent_id}/ws` 保持一致。

#### 3.2.3 新增 Agent 工具

新增工具模块 `src/jarvis/jarvis_tools/browser_ext.py`，并在 `registry.py` 注册。建议工具集：

| 工具名                      | 作用                         | 关键参数                                   |
| --------------------------- | ---------------------------- | ------------------------------------------ |
| `browser_ext_list_sessions` | 列出当前可用的用户浏览器会话 | 无                                         |
| `browser_ext_list_tabs`     | 列出目标会话的标签页         | `session_id`                               |
| `browser_ext_navigate`      | 导航到 URL                   | `session_id`, `tab_id`, `url`              |
| `browser_ext_get_text`      | 读取元素文本                 | `session_id`, `tab_id`, `selector`         |
| `browser_ext_click`         | 点击元素                     | `session_id`, `tab_id`, `selector`         |
| `browser_ext_type`          | 输入文本                     | `session_id`, `tab_id`, `selector`, `text` |
| `browser_ext_execute_js`    | 在页面执行任意 JS            | `session_id`, `tab_id`, `code`             |
| `browser_ext_screenshot`    | 截图                         | `session_id`, `tab_id`                     |
| `browser_ext_wait_for`      | 等待元素/条件出现            | `session_id`, `tab_id`, `selector`         |

工具内部通过全局 `browser_extension_manager` 实例下发指令。

#### 3.2.4 权限设计

**不引入权限校验。** 决策：浏览器控制能力不做权限控制。

- 不新增 `browser:*` 权限资源，不改动 `permission_manager.py` 与前端权限矩阵。
- 工具调用不经过 `check_permission`，与聊天功能"无人检查即开放"的现状一致。
- 安全边界由**插件侧**承担：插件需用户手动安装并授权 `<all_urls>`，且连接需携带有效网关 token（见 3.1.3、第 6 节）。

> 说明：若后续需要收紧，可按现有 `资源:动作` 模型补 `browser:control`，属增量改动，不影响本设计其余部分。

---

## 4. 消息协议

### 4.1 传输层

- 协议：WebSocket（文本帧，JSON）
- 端点：`/api/browser-ext/ws`
- 鉴权：子协议 `jarvis-ext` + `jarvis-token.<token>`
- 心跳：`ping` / `pong`

### 4.2 消息类型

| type            | 方向        | 说明                                                 |
| --------------- | ----------- | ---------------------------------------------------- |
| `hello`         | 插件 → 网关 | 连接后首帧，上报扩展版本、浏览器信息、当前标签页快照 |
| `hello_ack`     | 网关 → 插件 | 确认，返回 `session_id`                              |
| `command`       | 网关 → 插件 | 下发指令                                             |
| `result`        | 插件 → 网关 | 指令执行结果                                         |
| `event`         | 插件 → 网关 | 主动上报（标签页变化、页面导航等）                   |
| `ping` / `pong` | 双向        | 心跳                                                 |

### 4.3 指令动作清单（action）

#### 标签页类

- `tab.list` → `[{tab_id, url, title, active, window_id}]`
- `tab.activate` `{tab_id}`
- `tab.close` `{tab_id}`
- `tab.create` `{url, active}`

#### 导航类

- `page.navigate` `{tab_id, url, wait_until}`
- `page.reload` `{tab_id}`
- `page.back` / `page.forward` `{tab_id}`

**DOM 类**（经 content script 或 `chrome.scripting`）

- `dom.query` `{tab_id, selector, all}` → 元素信息
- `dom.get_text` `{tab_id, selector}`
- `dom.get_html` `{tab_id, selector}`
- `dom.click` `{tab_id, selector}`
- `dom.type` `{tab_id, selector, text, clear}`
- `dom.hover` `{tab_id, selector}`
- `dom.select` `{tab_id, selector, value}`
- `dom.wait_for` `{tab_id, selector, state, timeout_ms}`

#### 脚本类

- `script.execute` `{tab_id, code, world}` → 返回值（`world`: `MAIN` | `ISOLATED`）

#### 捕获类

- `capture.screenshot` `{tab_id, full_page}` → base64 PNG
- `capture.pdf` `{tab_id}`

#### 会话类

- `session.info` → 扩展与浏览器信息

### 4.4 错误码

| code                | 含义                       |
| ------------------- | -------------------------- |
| `NO_SESSION`        | 会话不存在或已断开         |
| `NO_TAB`            | 标签页不存在               |
| `ELEMENT_NOT_FOUND` | 选择器未匹配               |
| `TIMEOUT`           | 执行超时                   |
| `PROTECTED_PAGE`    | 目标为受保护页面，无法操作 |
| `EXEC_ERROR`        | 页面脚本执行异常           |

---

## 5. 关键流程

### 5.1 连接建立

```text
插件启动 → 读取配置(网关地址/token) → 连 /api/browser-ext/ws
        → 网关校验 token → 注册会话 → 回 hello_ack(session_id)
        → 插件上报 hello(标签页快照) → 进入就绪
```

### 5.2 Agent 操作网页

```text
Agent → browser_ext_click(session_id, tab_id, "#submit")
      → BrowserExtensionManager.send_command(...)
      → WS 下发 {action:"dom.click", params:{...}}
      → 插件 background 收到 → 定位 tab → 注入/调用 content script 执行
      → 回 {type:"result", success:true}
      → Manager 匹配 id → 返回结果给 Agent
```

### 5.3 断线处理

- 插件侧：指数退避重连；重连后重新 `hello`，网关按 `client_id` 复用或新建会话。
- 网关侧：心跳超时（60s）清理会话；对未完成指令以 `NO_SESSION` 失败返回。

---

## 6. 安全设计

| 风险                      | 对策                                                                  |
| ------------------------- | --------------------------------------------------------------------- |
| 未授权控制浏览器          | 插件需用户手动安装 + 显式授权 `<all_urls>`；连接需携带有效网关 token  |
| token 泄露                | 复用网关 token 体系；建议 wss 加密；token 仅存 `chrome.storage.local` |
| 恶意指令（如窃取 Cookie） | 指令白名单（仅上表 action）；连接与指令全程记日志                     |
| 误操作真实页面            | **高危动作二次确认**：确认交互放在插件 popup（见下方策略）            |
| 多用户越权                | 会话与 `user_id` 绑定；`list_sessions` 仅返回本人会话；管理员可查全部 |
| 审计缺失                  | 所有指令与结果落日志（含 `user_id`、`session_id`、`action`、时间戳）  |

**安全策略（已定）**：

- `script.execute` **默认开放**，无需用户逐次开启。
- **高危动作二次确认**：对可能造成不可逆后果的动作（如提交表单、删除、支付类点击），由**插件 popup** 弹出确认，用户放行后执行。
- 确认交互**放在插件侧**，不经过 Jarvis 前端——保证用户在自己浏览器中直接看到并决定。
- 多用户场景下，**同一用户允许多个浏览器会话同时在线**，各自独立 `session_id`。

---

## 7. 分阶段实施

### 阶段一：最小闭环（MVP）

- 扩展：连接、`tab.list`、`page.navigate`、`dom.get_text`、`dom.click`、`dom.type`、`capture.screenshot`
- 网关：`/api/browser-ext/ws` 端点 + `BrowserExtensionManager`（注册/路由/回传）
- 工具：`browser_ext_list_sessions` / `list_tabs` / `navigate` / `get_text` / `click` / `type` / `screenshot`
- 验证：Agent 能打开指定网页、读取内容、点击按钮、输入文本

### 阶段二：能力增强

- `script.execute`（任意 JS，默认开放）
- `dom.wait_for`、`dom.select`、`dom.hover`
- 标签页事件上报（`event`）
- 高危动作二次确认（插件 popup）
- 审计日志

### 阶段三：高级能力（可选）

- `chrome.debugger`（CDP）：真实鼠标轨迹、网络拦截、跨域 iframe
- 多浏览器 / 多窗口会话管理（同一用户多会话并行）
- 操作录制与回放

---

## 8. 风险与限制

1. **受保护页面不可操作**：`chrome://*`、扩展商店、其他扩展页面、部分 PDF 查看器。
2. **跨域 iframe 受限**：同源策略下 content script 无法直接进入跨域 iframe（需 `all_frames` + `match_about_blank` 或 CDP）。
3. **页面 CSP / 沙箱**：`chrome.scripting` 走扩展特权通常可绕过页面 CSP，但个别强沙箱页面仍可能失败。
4. **Manifest V3 service worker 生命周期**：SW 会被浏览器休眠，需用 `chrome.alarms` 或保持 WS 连接维持活跃（WS 连接本身可延长生命周期，但非绝对保证）。
5. **浏览器兼容**：Chrome/Edge 同源（Chromium）可行；Firefox 需适配 `browser.*` API 与 manifest 差异。
6. **用户授权不可绕过**：必须手动安装，无法静默部署。

---

## 9. 设计决策（已确认）

| #   | 问题                          | 决策                                      |
| --- | ----------------------------- | ----------------------------------------- |
| 1   | 权限粒度                      | **不做权限控制**，不引入 `browser:*` 资源 |
| 2   | `script.execute` 是否默认开放 | **默认开放**                              |
| 3   | 高危动作二次确认交互位置      | **插件 popup**                            |
| 4   | 单用户多浏览器会话            | **允许**，各自独立 `session_id`           |
| 5   | 扩展分发方式                  | **开发者模式加载**（不上架商店）          |

### 分发说明（开发者模式）

- 扩展以源码形式随仓库提供（`browser_extension/` 目录），用户通过 `chrome://extensions` → 开启"开发者模式" → "加载已解压的扩展程序"安装。
- 无需商店审核，便于快速迭代。
- 代价：用户需手动操作；Chrome 启动时可能提示"停用开发者模式扩展"，属预期行为。

---

## 10. 附：涉及改动点清单

| 位置                                                         | 改动                                                                    |
| ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| `src/jarvis/jarvis_web_gateway/browser_extension_manager.py` | **新增**：连接管理、指令路由、结果回传                                  |
| `src/jarvis/jarvis_web_gateway/app.py`                       | **新增** `/api/browser-ext/ws` 端点；初始化 `browser_extension_manager` |
| `src/jarvis/jarvis_tools/browser_ext.py`                     | **新增**：Agent 工具集                                                  |
| `src/jarvis/jarvis_tools/registry.py`                        | **无需修改**：`register_tool_by_file` 自动扫描 `jarvis_tools/*.py`      |
| `browser_extension/`（新目录）                               | **新增**：Chrome 扩展工程（开发者模式加载）                             |

> 权限相关文件（`permission_manager.py`、`AdminPanel.vue`）**不改动**——本方案不做权限控制。

---

## 11. 阶段一实现说明（MVP）

> 本章节记录阶段一 MVP 的**实际落地情况**，与上文设计如有差异以此为准。

### 11.1 交付物清单

#### 网关侧（Python）

| 文件                                                         | 说明                                                                 |
| ------------------------------------------------------------ | -------------------------------------------------------------------- |
| `src/jarvis/jarvis_web_gateway/browser_extension_manager.py` | 新增：`BrowserExtensionManager` 单例，连接管理 / 指令路由 / 结果回传 |
| `src/jarvis/jarvis_web_gateway/app.py`                       | 新增：WS 端点 `/api/browser-ext/ws`；HTTP API `/api/browser-ext/*`   |
| `src/jarvis/jarvis_tools/browser_ext.py`                     | 新增：Agent 工具 `browser_ext`（单工具 + action 参数范式）           |

#### 扩展侧（Chrome MV3）

| 文件                                                         | 说明                                      |
| ------------------------------------------------------------ | ----------------------------------------- |
| `browser_extension/manifest.json`                            | MV3 配置，`background.type: module`       |
| `browser_extension/background/ws_client.js`                  | WebSocket 连接、心跳（20s）、指数退避重连 |
| `browser_extension/background/command_router.js`             | `action` → executor 映射表                |
| `browser_extension/background/service_worker.js`             | 入口：连接编排、hello 握手、状态广播      |
| `browser_extension/background/executors/tab_executor.js`     | 标签页 / 导航                             |
| `browser_extension/background/executors/dom_executor.js`     | DOM 读写                                  |
| `browser_extension/background/executors/capture_executor.js` | 截图                                      |
| `browser_extension/content/content_script.js`                | 页面内补充脚本                            |
| `browser_extension/popup/popup.html` / `popup.js`            | 连接配置 / 状态 / 高危确认 UI 占位        |
| `browser_extension/README.md`                                | 安装与使用说明                            |

### 11.2 网关接口

#### WebSocket

- 路径：`/api/browser-ext/ws`
- 鉴权：复用 `_extract_auth_from_headers`，从 `sec-websocket-protocol` 中提取 `jarvis-token.<token>`，再经 `gateway._check_auth` 校验
- 鉴权失败：`accept(subprotocol="jarvis-ext")` 后发送错误帧并 `close(4401)`

**HTTP API**（均需 `Depends(verify_token)`）

| 方法   | 路径                        | 说明                         |
| ------ | --------------------------- | ---------------------------- |
| `GET`  | `/api/browser-ext/sessions` | 列出当前在线会话             |
| `POST` | `/api/browser-ext/command`  | 向指定会话下发指令并等待结果 |

### 11.3 Agent 工具 `browser_ext`

- 类名 `BrowserExtTool`，`name = "browser_ext"`（与文件名一致，满足 `register_tool_by_file` 要求）
- `check()`：`jglobals.agent_id is not None` 时可用
- 工具运行在 Agent 子进程中，**通过 HTTP 访问网关**，不直接接触网关内存对象
- 支持的 action 与扩展 action 的映射：

| 工具 action      | 扩展 action          | 必填参数                                 |
| ---------------- | -------------------- | ---------------------------------------- |
| `list_sessions`  | （HTTP 直查）        | 无                                       |
| `list_tabs`      | `tab.list`           | `session_id`                             |
| `navigate`       | `page.navigate`      | `session_id`, `url`                      |
| `get_text`       | `dom.get_text`       | `session_id`, `selector`                 |
| `click`          | `dom.click`          | `session_id`, `selector`                 |
| `type`           | `dom.type`           | `session_id`, `selector`, `text`         |
| `screenshot`     | `capture.screenshot` | `session_id`                             |
| `activate_tab`   | `tab.activate`       | `session_id`, `tab_id`                   |
| `close_tab`      | `tab.close`          | `session_id`, `tab_id`                   |
| `new_tab`        | `tab.create`         | `session_id`                             |
| `reload`         | `page.reload`        | `session_id`                             |
| `back`           | `page.back`          | `session_id`                             |
| `forward`        | `page.forward`       | `session_id`                             |
| `query`          | `dom.query`          | `session_id`, `selector`                 |
| `get_html`       | `dom.get_html`       | `session_id`, `selector`                 |
| `hover`          | `dom.hover`          | `session_id`, `selector`                 |
| `select`         | `dom.select`         | `session_id`, `selector`, `value`        |
| `wait_for`       | `dom.wait_for`       | `session_id`, `selector`                 |
| `press_key`      | `dom.press_key`      | `session_id`, `key`                      |
| `scroll`         | `dom.scroll`         | `session_id`（selector 或 x/y 至少一个） |
| `execute_script` | `script.execute`     | `session_id`, `code`                     |
| `upload_file`    | `dom.upload_file`    | `session_id`, `selector`, `file_path`    |

- 返回统一信封：`{"success": bool, "stdout": str, "stderr": str}`
- `screenshot` 的 base64 由工具侧落盘为临时 PNG（`/tmp/jarvis_browser_ext_<ts>.png`），
  `stdout` 只返回 `{path, width, height, full_page, bytes}`，避免超长 base64 撑爆上下文

### 11.4 安装与使用步骤

1. **启动网关**（需带 `--master-url` 供 Agent 工具访问）
2. **安装扩展**：`chrome://extensions` → 开启「开发者模式」→「加载已解压的扩展程序」→ 选择仓库中的 `browser_extension/` 目录
3. **登录 Jarvis 网页**：扩展会自动复用网页登录态（无需手动填写 Token，详见 11.8）
4. **配置连接**：点击扩展图标，填写网关地址（如 `https://jvs-ai.cn`），点击「连接」
5. **验证连通**：状态显示「已连接」后，在 Agent 会话中调用 `browser_ext` 的 `list_sessions`，应返回该会话的 `session_id`
6. **执行操作**：`list_tabs` 拿到 `tab_id` 后，即可执行 `navigate` / `get_text` / `click` / `type` / `screenshot`

### 11.5 阶段一验证结论

已完成的静态与 mock 验证：

- Python：`ast.parse` 全部通过，`ruff check` 全通过
- JavaScript：8 个 `.js` 文件全部通过 `node --check`（ESM 模式）
- `manifest.json`：`python -m json.tool` 校验合法
- 工具注册：`BrowserExtTool` 具备 `name`/`description`/`parameters`/`execute`，且 `name` 与文件名一致
- 端点存在：`/api/browser-ext/ws`、`/api/browser-ext/sessions`、`/api/browser-ext/command` 均已定义
- Mock 端到端：7 个 action 全部返回成功，4 条错误路径（未知 action、缺 `session_id`、缺 `url`、空 action）均正确报错
- 文档：`markdownlint` 通过

**尚未验证（受「禁止重启网关」约束，需用户自行操作）**：

- 网关与扩展的真实 WS 握手
- 真实浏览器中的指令往返与结果回传

### 11.6 阶段一已知简化

1. popup 中的高危动作二次确认仅为 UI 占位，background 尚未发起真实确认请求（设计上属阶段二）
2. `browser_extension/icons/` 目录未创建，`manifest.json` 中 `icons` 为空对象，不影响开发者模式加载
3. `content_scripts` 的 `all_frames: false`，暂不支持 iframe 内元素操作

### 11.7 阶段二待办

- 暴露 `script.execute` 工具
- `dom.wait_for` / `dom.hover` / `dom.select` 工具化
- 真实高危动作拦截（popup 二次确认接入 background）
- 操作审计日志

### 11.8 登录态复用（方案 B2）

#### 11.8.1 问题

阶段一最初要求用户在 popup 中手填网关 Token（`JARVIS_AUTH_TOKEN`）。但该 Token 用户无法自行获取：

- 网关 Token 存于网关进程的环境变量，用户不可见
- JWT Token 存于前端 `localStorage['jarvis_auth_token']`，且**仅当用户开启「免登录」开关时才写入**（否则只存在于 Vue 内存）

因此「手填 Token」对普通用户不可行。

#### 11.8.2 方案选型

| 方案                         | 说明                                                 | 结论                                                      |
| ---------------------------- | ---------------------------------------------------- | --------------------------------------------------------- |
| A. 扩展内独立登录            | popup 填账号密码，扩展自行调 `/api/auth/login`       | 否决：用户需登录两次，且扩展与网页登录态可能不一致        |
| B1. `externally_connectable` | 网页通过 `chrome.runtime.sendMessage` 直接投递给扩展 | 需固定扩展 ID（manifest 写 `key`），改动较大              |
| **B2. content script 桥接**  | content script 注入主世界脚本，读取网页暴露的 Token  | **采用**：用户零操作，无需固定扩展 ID，无需改前端登录逻辑 |

#### 11.8.3 实现

**前端（`App.vue`）**：暴露只读接口 + Token 变化广播

```js
window.__jarvisAuthBridge = {
  getToken: () => auth.value.token || null,
};
watch(
  () => auth.value.token,
  (newToken) => {
    window.postMessage(
      { type: "jarvis_token_changed", token: newToken || null },
      "*",
    );
  },
);
```

用 `watch` 统一覆盖所有 Token 变化点（登录成功、免登录恢复、401 失效、登出），无需逐个修改。

**content script（`content_script.js`）**：主世界注入桥接

content script 运行在隔离世界，无法访问页面 JS 变量，故注入一段主世界脚本：

- 主世界脚本调用 `window.__jarvisAuthBridge.getToken()` 读取 Token
- 通过 `window.postMessage` 与隔离世界通信（双向均校验 `event.source === window`）
- 隔离世界将 Token 转发给 background（`chrome.runtime.sendMessage`）
- 支持两种触发：页面主动广播 `jarvis_token_changed`；background 主动索取 `jarvis_request_token`

**background（`service_worker.js`）**：Token 驱动连接

- 收到 `jarvis_ext_token` / `jarvis_ext_token_changed` → 调 `handleAuthToken`
- Token 变化 → 重连；Token 为空 → 断开
- 冷启动时若尚无 Token，主动向所有标签页发 `jarvis_request_token` 索取
- `jarvis_get_status` 新增 `has_token` 字段供 popup 显示登录态

**popup**：移除 Token 输入框，改为显示登录态（已获取 / 未获取）

#### 11.8.4 关键收益

- **身份天然一致**：扩展使用的 Token 即网页登录用户的 Token，不存在「扩展登录账号与网页账号不一致」的问题
- **零配置**：用户只需登录 Jarvis 网页，扩展自动跟随
- **自动跟随变化**：切换账号 / 登出 / Token 过期，扩展自动重连或断开

#### 11.8.5 已知取舍

前端通过 `window.__jarvisAuthBridge` 暴露 Token，**同页面脚本理论上可读取**。当前版本接受此风险以换取零配置体验。若后续需强隔离，可升级为 B1（`externally_connectable` + 固定扩展 ID），届时仅指定扩展可获取 Token。

### 11.9 多网关并行连接（方案 B）

#### 11.9.1 问题

阶段一扩展只支持单个网关（`chrome.storage.local` 中扁平存 `gateway` / `token` / `session_id`）。但实际场景中用户常需同时接入多个 Jarvis 网关（如本机开发网关 + 线上网关），单网关模型下切换网关需反复改配置并重连。

#### 11.9.2 方案选型

| 方案                 | 说明                                     | 结论                                       |
| -------------------- | ---------------------------------------- | ------------------------------------------ |
| A. 扩展内独立登录    | 扩展自己维护账号密码登录，与网页登录解耦 | 否决：用户需登录两次，与 B2 零配置目标冲突 |
| B. 多网关并行连接    | 同一扩展同时维护多个网关连接，各自独立   | **采纳**                                   |
| C. 单网关 + 快速切换 | 保留单连接，popup 提供切换               | 否决：无法并行，Agent 侧需反复切换         |

选 B。核心判断：**网关侧无需任何改动**——每个网关是独立进程，各自维护 `browser_extension_manager._sessions`，扩展连 A 就注册到 A，连 B 就注册到 B，天然隔离。

#### 11.9.3 实现

**service_worker.js**：单例状态改为按网关索引的四个 `Map`：

```js
const clients = new Map(); // gateway -> WsClient
const tokens = new Map(); // gateway -> token
const sessions = new Map(); // gateway -> session_id
const states = new Map(); // gateway -> 'disconnected' | 'connecting' | 'connected'
```

- `normalizeGateway()`：统一网关地址（无协议补 `http://`，去尾部斜杠），作为 Map 的 key
- `connect(gateway)`：为每个网关创建独立 `WsClient` 实例，`onMessage` 闭包绑定该网关
- `handleMessage(gateway, msg)`：指令结果只回传给 `clients.get(gateway)`，不会串网关
- `requestTokenFromPages(gateway)`：只接受 `resp.gateway` 与目标网关匹配的响应
- `handleAuthToken(gateway, token)`：按网关独立重连 / 断开
- `listStatus()`：汇总所有网关状态，`jarvis_get_status` 返回 `{ gateways: [...] }`
- 新增消息类型 `jarvis_remove_gateway`；`jarvis_connect` / `jarvis_disconnect` 支持 `gateway` 参数（disconnect 不传则断开全部）
- `connectAll()`：冷启动遍历 `chrome.storage.local.gateways` 逐个连接

**content_script.js**：主世界回传与隔离世界转发均携带 `gateway: location.origin`，使 Token 能归属到正确的网关。

**popup**：改为网关列表 UI——顶部输入框用于新增网关，列表区展示每个网关的地址 / 连接状态 / 登录态 / `session_id`，每项提供「连接 / 断开 / 移除」按钮。

**storage 结构变更**：`gateway` / `token` / `session_id` 扁平 key → `gateways: string[]`（仅存地址列表；Token 改存内存 `Map`，不再落 storage，安全性反而提升）。

**CommandRouter 复用**：executor 无状态、操作全局 `chrome.tabs`，与网关无关，因此多网关共享同一个 router 实例。

#### 11.9.4 关键取舍

**所有网关共享同一批浏览器标签页。** `chrome.tabs` 是浏览器全局的，扩展架构上无法按网关隔离标签页；如需隔离只能让用户手动使用不同浏览器窗口 / 配置文件，不现实。因此多个 Agent 并发操作时可能互相影响同一页面，使用时应避免并发操作同一标签页。

#### 11.9.5 兼容性

单网关场景行为不变：只添加一个网关时，表现与阶段一完全一致（连接、状态显示、登录态复用均相同），仅 UI 从「状态区」变为「单条列表项」。

### 11.10 能力补齐（第二轮）

在阶段一 17 个 action 基础上，补齐 5 项能力缺口，扩展 action 增至 21 个，与工具映射一一对应。

#### 11.10.1 新增 action

| 扩展 action                         | 工具 action                 | 说明                                                                                                  |
| ----------------------------------- | --------------------------- | ----------------------------------------------------------------------------------------------------- |
| `dom.press_key`                     | `press_key`                 | 派发 `keydown`/`keypress`/`keyup`，含 `keyCode`/`which` 兼容表；`Enter` 时尝试 `form.requestSubmit()` |
| `dom.scroll`                        | `scroll`                    | 指定 `selector` 则 `scrollIntoView`，否则 `window.scrollBy(x, y)`；返回滚动位置与页面尺寸             |
| `script.execute`                    | `execute_script`            | `new Function` 先按表达式求值，失败退化为语句执行；结果经 `safeSerialize`                             |
| `dom.upload_file`                   | `upload_file`               | 通过 `chrome.debugger` 的 `DOM.setFileInputFiles` 设置真实本地文件路径                                |
| `capture.screenshot`（`full_page`） | `screenshot`（`full_page`） | 逐屏滚动截图 + `OffscreenCanvas` 拼接，实现真整页截图                                                 |

#### 11.10.2 截图落盘改造

原实现把 base64 直接塞进 `stdout`，Agent 实际无法使用。现改为：

- 扩展返回 `{image, width, height, full_page}`（整页）或 base64 字符串（视口）
- 工具侧 `_screenshot_to_file()` 解码 base64 并写入 `/tmp/jarvis_browser_ext_<ts>.png`
- `stdout` 只返回 `{path, width, height, full_page, bytes}`

#### 11.10.3 文件上传的技术约束

扩展运行在沙箱中，**无法直接读取本地文件内容**。唯一能真实上传本地文件的方式是
`chrome.debugger` + `DOM.setFileInputFiles`（传入文件路径，由浏览器进程读取）。
因此 `manifest.json` 新增 `debugger` 权限。代价：附加调试器时浏览器显示「正在调试此浏览器」提示条；
若标签页已被 DevTools 占用，附加会失败。

#### 11.10.4 验证结论

- 扩展 action 注册集合（21）与工具 `_send_command` 映射集合（21）**零差异**
- 全部 `.js` 通过 `node --check`；`manifest.json` JSON 合法
- Python `ast.parse` + `ruff check` 通过
- Mock 实测：4 个新 action 的正常路径与错误路径（缺必填参数）全部符合预期；截图落盘路径与尺寸正确
- 回归：原有 15 个 action 映射行为不变
