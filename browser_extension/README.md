# Jarvis Browser Bridge

让 Jarvis Agent 操作用户**真实浏览器**中的网页（复用登录态与 Cookie）。

与 `jarvis-browser`（`jb`，服务端 Playwright 启动独立浏览器）不同，本扩展运行在用户浏览器内，
通过 WebSocket 主动连出到 Jarvis 网关，因此无需公网 IP、无需开放端口。

## 安装（开发者模式）

1. 打开 Chrome/Edge，访问 `chrome://extensions`
2. 右上角开启「开发者模式」
3. 点击「加载已解压的扩展程序」，选择本目录（`browser_extension/`）
4. 在浏览器中登录 Jarvis 网页（扩展会自动复用其登录态，**无需手动填写 Token**）
5. 点击工具栏中的扩展图标，在「添加网关地址」中填写：
   - **网关地址**：如 `https://jvs-ai.cn` 或 `http://127.0.0.1:8000`
6. 点击「添加并连接」，列表中该网关状态显示「已连接」即成功
7. 如需连接多个网关，重复第 5~6 步即可（每个网关独立连接、独立会话）

## 登录态复用机制

扩展不要求用户单独登录，也不要求手填 Token，而是**自动复用浏览器中已登录的 Jarvis 网页登录态**：

```text
Jarvis 网页（已登录）
  │  window.__jarvisAuthBridge.getToken()  ← 前端暴露的只读接口
  │  window.postMessage('jarvis_token_changed')  ← Token 变化广播
  ▼
content_script.js（隔离世界）
  │  注入主世界脚本读取 Token，转发给 background
  ▼
service_worker.js
  │  Token 变化 → 重连；Token 为空（未登录/已登出）→ 断开
  ▼
网关 WebSocket（携带 jarvis-token.<token> 子协议）
```

要点：

- **身份天然一致**：扩展使用的 Token 就是网页登录用户的 Token，不存在"扩展登录账号与网页账号不一致"的问题
- **Token 变化自动跟随**：用户在网页切换账号或登出，扩展自动重连或断开
- **冷启动自动获取**：扩展启动时主动向已打开的 Jarvis 页面索取 Token
- 前端需暴露 `window.__jarvisAuthBridge.getToken()`（见 `App.vue` 中「浏览器扩展登录态桥接」段落）

## 多网关支持

同一浏览器可**同时连接多个 Jarvis 网关**（例如本机 `http://127.0.0.1:8000` 与线上 `https://jvs-ai.cn`）：

- 每个网关维护独立的 WebSocket 连接、独立的 `session_id`、独立的登录态 Token
- popup 中列出所有已添加网关，可对单个网关执行「连接 / 断开 / 移除」
- 网关列表持久化在 `chrome.storage.local.gateways`；Token 仅存内存，不落盘
- 冷启动（扩展启动 / 浏览器启动）时自动为所有已配置网关重连

**取舍：所有网关共享同一批浏览器标签页。** 扩展的 `chrome.tabs` 是浏览器全局的，
无法按网关隔离标签页；如需隔离，只能由用户手动使用不同浏览器窗口/配置文件，不现实。
因此多个 Agent 同时操作时可能互相影响同一批标签页，请避免并发操作同一页面。

## 目录结构

```text
browser_extension/
├── manifest.json                  # Manifest V3 配置
├── background/
│   ├── service_worker.js          # 入口：连接管理 + 指令分发 + 登录态接收 + 脚本管理转发
│   ├── ws_client.js               # WebSocket 连接、心跳、重连
│   ├── command_router.js          # action → executor 映射
│   ├── script_manager.js          # 脚本仓库（类油猴）：安装 / 列表 / 启停 / 卸载
│   └── executors/
│       ├── tab_executor.js        # 标签页 / 导航
│       ├── dom_executor.js        # DOM 读写（executeScript 注入）
│       ├── script_executor.js     # 自定义脚本执行（主世界注入）
│       ├── clipboard_executor.js  # 读网关静态文件 / 写前端剪贴板
│       ├── capture_executor.js    # 截图
│       ├── bookmarks_executor.js  # 书签（读 / 搜索 / 增删）
│       ├── history_executor.js    # 历史记录（查询 / 删除）
│       ├── downloads_executor.js  # 下载记录（列表 / 搜索 / 控制）
│       ├── sessions_executor.js   # 最近关闭的会话（查询 / 恢复）
│       ├── top_sites_executor.js  # 常访问站点
│       ├── reading_list_executor.js  # 阅读列表
│       ├── context_menus_executor.js # 扩展右键菜单
│       ├── alarms_executor.js     # 定时器
│       ├── notifications_executor.js # 系统通知
│       ├── search_executor.js     # 默认搜索引擎检索
│       ├── idle_executor.js       # 空闲状态检测
│       ├── favicon_executor.js    # 站点图标 URL
│       ├── web_navigation_executor.js # 页面框架信息
│       ├── tab_groups_executor.js # 标签组
│       ├── cookies_executor.js    # Cookie（高敏感）
│       ├── web_request_executor.js # 网络请求规则（高敏感，declarativeNetRequest）
│       ├── management_executor.js # 扩展与应用管理（高敏感）
│       ├── native_messaging_executor.js # 本机应用通信（高敏感）
│       ├── proxy_executor.js      # 代理设置（高敏感）
│       ├── privacy_executor.js    # 隐私设置（高敏感）
│       ├── browsing_data_executor.js # 浏览数据清除（高敏感，不可逆）
│       └── content_settings_executor.js # 站点内容设置（高敏感）
├── content/
│   └── content_script.js          # 页面内脚本：登录态桥接 + 页面元信息
└── popup/
    ├── popup.html                 # 连接配置 / 状态 / 高危确认 / 脚本管理 UI
    └── popup.js
```

## 脚本管理（类油猴）

扩展内置一个**脚本仓库**：用户可安装自定义页面脚本，Agent 通过 `script.*` 指令查询并调用。
适合把「某个站点的专用操作」封装成可复用能力（例如某在线文档站点的编辑器读写）。

### 脚本格式

脚本是一段 JS，在**页面主世界**被求值，应导出如下对象：

```js
globalThis.__JARVIS_SCRIPT__ = {
  name: "mysite", // 脚本名（唯一，重名视为更新）
  version: "1.0.0",
  description: "某站点文档操作",
  match: ["example.com"], // 适用域名（仅作提示，不做强制拦截）
  actions: {
    // entry 可以是 { desc, params, run } 或直接是一个函数
    getText: { desc: "读取全文", run: () => ({ text: window.ze.getText() }) },
    insertText: {
      desc: "在指定偏移插入文本（写操作）",
      params: { offset: "number", text: "string" },
      run: ({ offset, text }) => {
        window.ze.executeCommandAndMoveCursor({
          command: "addText",
          range: { startOffset: offset, endOffset: offset },
          data: text,
        });
        return { ok: true };
      },
    },
  },
};
```

也兼容 `module.exports = {...}` 写法。安装时会做**轻量静态校验**（导出关键字检查 + 括号配平检查），
不执行脚本，因此校验是「弱保证」——**请只安装你自己信任的脚本**。

> 校验**不使用** `new Function` / `eval`：MV3 扩展页面的 CSP 为 `script-src 'self'`（不允许 `unsafe-eval`），
> 动态求值会被浏览器直接拒绝。真正的语法错误会在 `script.run` 于页面主世界求值时暴露。

### 安装与使用

1. 打开扩展 popup → 「脚本管理（类油猴）」
2. 三种安装方式任选其一：
   - 把脚本源码粘贴到「脚本源码」框 → 填脚本名称 → 点「安装脚本」
   - 点「或从本地文件导入」选择 `.js` 文件
   - 在「或从 URL 安装」填入脚本 URL → 点「从 URL 安装」（源码由后台下载，不显示在界面）
3. 列表中可对每个脚本「启用 / 停用」「查看源码」「导出」「卸载」

Agent 侧通过 `script.list` 查询已装脚本，再用 `script.run` 调用其某个 action。

### 从 URL 安装

「从 URL 安装」由 **background 侧 `fetch`** 下载脚本源码，popup 不接触源码内容。
适合把脚本托管在任意 HTTP 静态目录（如网关的 `/uploads/`）后按 URL 分发，避免在对话里传输大段源码。

URL 校验由 `background/url_guard.js` 完成（防 SSRF）：

- 只允许 `http` / `https`；拒绝 `file:`、`data:`、`ftp:` 等
- 拒绝回环与内网地址：`127.0.0.1`、`localhost`、`10.x`、`172.16-31.x`、`192.168.x`、`169.254.x`、`::1`、`fe80::` 等
- 因此**本机/内网网关不能用 URL 安装**，请改用下面的「网关目录中转」

脚本名可由 URL 末段推导（`.../my-script.js` → `my-script`），推导不出时须显式填写脚本名称。
下载内容只作为**源码字符串**存储，扩展绝不在 background 求值。

### 网关目录中转

Agent 可把扩展里的脚本保存到网关数据目录（`{data_dir}/browser_scripts/`），
再从该目录读回安装，全程**不回传脚本原文**：

- `script_save`：扩展 → 网关目录，只回传路径与字节数
- `script_load_from_file`：网关目录 → 扩展，只回传安装元数据

脚本名只允许 `[A-Za-z0-9_.-]`，禁止 `/`、`\`、`..` 与以 `.` 开头，防止目录穿越。

### 导出与分享

列表中的「导出」按钮会把脚本导出为 `<name>.js` 文件（浏览器下载），文件顶部带一段元信息注释：

```js
// ===== Jarvis 脚本导出 =====
// name: mysite
// version: 1.0.1
// description: 某在线文档编辑器读写操作
// match: example.com
// 安装方式：扩展 popup →「脚本管理」→ 粘贴本文件内容或从本地文件导入。
// ===========================

globalThis.__JARVIS_SCRIPT__ = { ... };
```

把该文件发给他人，对方用「从本地文件导入」或粘贴源码即可安装，无需任何格式转换。
Agent 侧也可用 `script.export` 取回同样的文本内容（返回 `{ filename, name, version, content }`）。

### 执行机制与安全说明

`script.run` 会把脚本源码通过 `chrome.scripting.executeScript({ world: "MAIN" })` 注入到目标标签页的
**主世界**执行，因此脚本能访问页面自身的 JS 对象（如站点自带的编辑器实例 `window.editor`）。
这等同于在页面里执行任意 JS —— 安全边界完全依赖「只安装可信脚本」。

- 脚本默认**启用**；停用后 `script.run` 会返回 `SCRIPT_DISABLED`
- 脚本在页面主世界求值，可读写该页面的 DOM 与 JS 对象，也可能发起网络请求
- 脚本可来自手动粘贴/本地导入，也可由 `script.install_from_url` 从 URL 下载；
  远程下载仅限 http(s) 且拒绝内网地址，**请只安装你自己信任的脚本**

## 支持的指令（action）

| 类别     | action                                                                                                                                                                           |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 标签页   | `tab.list` `tab.activate` `tab.close` `tab.create`                                                                                                                               |
| 导航     | `page.navigate` `page.reload` `page.back` `page.forward` `page.get_info`                                                                                                         |
| DOM      | `dom.query` `dom.get_text` `dom.get_html` `dom.click` `dom.type` `dom.hover` `dom.select` `dom.wait_for` `dom.press_key` `dom.scroll` `dom.upload_file` `dom.get_computed_style` |
| 调试     | `debugger.evaluate` `debugger.send_command` `console.get_logs` `network.get_requests`（走 CDP，不受页面 CSP 限制）                                                               |
| 脚本     | `script.execute`（执行任意 JS 代码，高危）                                                                                                                                       |
| 脚本库   | `script.list` `script.get` `script.install` `script.install_from_url` `script.uninstall` `script.export` `script.set_enabled` `script.run`（类油猴脚本管理）                     |
| 剪贴板   | `clipboard.write_from_url`（读 URL 内容写入剪贴板）`clipboard.write`（直接写文本/base64）                                                                                        |
| 书签     | `bookmark.list` `bookmark.search` `bookmark.create` `bookmark.remove` `bookmark.remove_tree`                                                                                     |
| 历史     | `history.search` `history.recent` `history.remove` `history.remove_range`                                                                                                        |
| 下载     | `download.list` `download.search` `download.start` `download.pause` `download.resume` `download.cancel` `download.erase` `download.open`                                         |
| 会话     | `session.recent` `session.restore`（最近关闭的标签页/窗口）                                                                                                                      |
| 常用站点 | `topsite.list`                                                                                                                                                                   |
| 阅读列表 | `readinglist.list` `readinglist.add` `readinglist.remove` `readinglist.update`                                                                                                   |
| 右键菜单 | `contextmenu.create` `contextmenu.remove` `contextmenu.remove_all` `contextmenu.list`                                                                                            |
| 定时器   | `alarm.create` `alarm.list` `alarm.clear` `alarm.clear_all`                                                                                                                      |
| 通知     | `notification.create` `notification.clear` `notification.clear_all` `notification.list`                                                                                          |
| 搜索     | `search.query`（用浏览器默认搜索引擎检索）                                                                                                                                       |
| 空闲状态 | `idle.query_state` `idle.set_interval` `idle.get_interval`                                                                                                                       |
| 站点图标 | `favicon.get_url`                                                                                                                                                                |
| 页面框架 | `webnav.get_all_frames` `webnav.get_frame`                                                                                                                                       |
| 标签组   | `tabgroup.list` `tabgroup.get` `tabgroup.query` `tabgroup.update`                                                                                                                |
| 捕获     | `capture.screenshot`（支持 `full_page` 整页截图）                                                                                                                                |

### 高敏感指令（调用前必须向用户确认）

| 类别     | action                                                                                                           |
| -------- | ---------------------------------------------------------------------------------------------------------------- |
| Cookie   | `cookie.get` `cookie.get_all` `cookie.set` `cookie.remove`（涉及登录凭证）                                       |
| 网络规则 | `netrule.list` `netrule.register` `netrule.unregister`（可阻断/重定向请求，基于 `declarativeNetRequest`）        |
| 扩展管理 | `extmgr.list` `extmgr.get` `extmgr.launch_app` `extmgr.set_enabled` `extmgr.uninstall`（`uninstall` **不可逆**） |
| 本机通信 | `native.send`（需已注册 native messaging host）                                                                  |
| 代理     | `proxy.get_settings` `proxy.set_settings` `proxy.clear_settings`（影响全部网络流量）                             |
| 隐私设置 | `privacy.get` `privacy.set`                                                                                      |
| 浏览数据 | `browsingdata.settings` `browsingdata.remove`（`remove` **不可逆**，可清空历史/Cookie/缓存/密码等）              |
| 内容设置 | `contentsettings.get` `contentsettings.set` `contentsettings.clear`（站点级 Cookie/JS/弹窗/摄像头等权限）        |

## 剪贴板（读网关静态文件 → 写前端剪贴板）

把网关静态目录（`/uploads/`）中的文件内容读出来，写入**前端页面的系统剪贴板**，
供页面内的编辑器粘贴使用（例如把图片贴进富文本编辑器）。

读写分两处执行，这是浏览器的硬约束：

- **读文件**：在 background（service worker）里 `fetch`，可跨域；
- **写剪贴板**：`navigator.clipboard` 在 service worker 中不可用，必须注入**页面上下文**执行，
  且要求文档真正获得焦点，否则报 `NotAllowedError: Document is not focused`。

### `clipboard.write_from_url`

| 参数     | 必填 | 说明                                                                               |
| -------- | ---- | ---------------------------------------------------------------------------------- |
| `url`    | 是   | 文件地址。绝对 URL（推荐）或 `/uploads/xxx.png` 相对路径（用配置的第一个网关补全） |
| `as`     | 否   | `blob`（默认，二进制，适合图片）或 `text`（按文本写入）                            |
| `mime`   | 否   | `as=blob` 时覆盖 MIME（默认取响应 `content-type`）                                 |
| `tab_id` | 否   | 目标标签页，默认当前活动标签页                                                     |

返回 `{ ok, url, mime, size, mode }`。

> **节点拓扑**：Agent 可能运行在 master 或任意子节点上，读哪个地址由**调用方**决定。
> 请直接传完整绝对 URL（如 `https://<node-gateway>/uploads/xxx.png`），扩展不做地址猜测。

### `clipboard.write`

直接写入给定内容，不经网关：`text`（文本）或 `base64` + `mime`（二进制）。

### 使用前置：文档必须获得焦点

`tab.activate` 只能激活标签页，**不足以**让剪贴板可写（`document.hasFocus()` 为 true 仍可能报错）。
调用前需先派发一次真实鼠标点击（如 CDP `Input.dispatchMouseEvent` 的 `mousePressed` + `mouseReleased`）。

粘贴到页面编辑器时，需用 CDP 发 `Ctrl+V`，且**必须用 `rawKeyDown` 类型**（`keyDown` 无效）：

```js
{ type: "rawKeyDown", modifiers: 2, key: "v", code: "KeyV",
  windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86, text: "", unmodifiedText: "" }
```

## 消息协议

### 网关 → 插件（指令）

```json
{
  "id": "req-<uuid>",
  "type": "command",
  "action": "dom.click",
  "params": { "selector": "#submit", "tab_id": 123 },
  "timeout_ms": 15000
}
```

### 插件 → 网关（结果）

```json
{
  "id": "req-<uuid>",
  "type": "result",
  "success": true,
  "data": { "ok": true },
  "error": null
}
```

**握手**：连接后插件发送 `hello`（含扩展版本、浏览器信息、标签页快照），网关回 `hello_ack`
（含 `session_id` 与 `latest_extension_version`）。

**心跳**：插件每 20s 发送 `{"type":"ping"}`，网关回 `{"type":"pong"}`。

## 版本更新提示

扩展**不会自动更新**（未上架商店，且 MV3 不允许改写自身已安装文件），但有两处主动提示：

1. **插件侧**：握手时网关随 `hello_ack` 下发 `latest_extension_version`。插件比对本地版本，
   落后则弹一次系统通知（同一新版本只提示一次，记录在 `chrome.storage.local` 的
   `notified_extension_version`）。**无需打开 Jarvis 网页即可收到提示。**
2. **网页侧**：进入大厅时检测一次，之后每 5 分钟复查，有新版本时「安装浏览器插件」按钮
   显示红点，弹层内展示版本对比。

收到提示后，需**手动**重新下载插件包并重新加载扩展 —— 浏览器未提供任何 API 允许扩展
替换自身文件或自动重载，这一步无法自动化。

## 已知限制

1. **受保护页面不可操作**：`chrome://*`、扩展商店、其他扩展页面等
2. **跨域 iframe 受限**：同源策略下无法直接进入跨域 iframe（`all_frames: false`）
3. **MV3 service worker 可能休眠**：靠 WebSocket 连接延长生命周期，但非绝对保证
4. **高危动作二次确认尚未接入**：popup 中已有 UI 占位，后续版本接入真实拦截
5. **文件上传依赖 `debugger` 权限**：`dom.upload_file` 通过 `chrome.debugger` 的
   `DOM.setFileInputFiles` 设置真实本地文件路径，这是扩展沙箱内唯一可行的方式。
   附加调试器时浏览器会显示「正在调试此浏览器」提示条；若标签页已被 DevTools
   占用，附加会失败。
6. **整页截图依赖滚动拼接**：`capture.screenshot` 的 `full_page` 通过逐屏滚动截图
   后在 `OffscreenCanvas` 拼接实现，超长页面（超过 50 屏）会被截断；截图期间页面
   会短暂滚动，结束后恢复原位置。
7. **`script.execute` 受页面 CSP 限制**：部分站点禁止 `eval`/`new Function`，
   此时执行会失败。
8. **书签与历史为新增权限**：`bookmark.*` / `history.*` 需要 `bookmarks`、`history`
   权限，安装或更新扩展后浏览器会再次提示授权。`bookmark.remove` /
   `bookmark.remove_tree` / `history.remove` / `history.remove_range` 为**不可逆**
   删除操作；`history.remove_range` 不传时间参数时会清空全部历史记录，调用前请确认。
9. **扩展已申请较多权限（含高敏感权限）**：为支持完整的浏览器自动化能力，
   `manifest.json` 申请了 28 项权限，其中 8 项为高敏感权限：
   `cookies`、`webRequest`、`management`、`nativeMessaging`、`proxy`、
   `privacy`、`browsingData`、`contentSettings`。安装或更新扩展时浏览器会
   明确提示「读取和更改您在所访问网站上的所有数据」等警告，请确认后再授权。
   高敏感权限对应的能力如下：
   - `cookies`：读写/删除站点 Cookie（**含登录凭证**）
   - `webRequest`：注册网络请求规则，可阻断或重定向请求
   - `management`：列出/启用/禁用/卸载其他扩展（`uninstall` **不可逆**）
   - `nativeMessaging`：与已注册的本机应用通信
   - `proxy`：修改浏览器全局代理设置（**影响全部网络流量**）
   - `privacy`：修改隐私相关开关
   - `browsingData`：清除浏览数据（**不可逆**，含历史/Cookie/缓存/密码）
   - `contentSettings`：修改站点级内容权限（Cookie/JS/弹窗/摄像头等）

   > ⚠️ **风险提示**：这些权限使扩展具备等同于「完全控制浏览器」的能力。
   > 请仅在信任运行本扩展的网关与 Agent 的前提下使用；删除/清空类操作不可恢复。
   > 若不需要这些能力，可自行从 `manifest.json` 的 `permissions` 中移除对应项
   > （移除后相关 action 会返回 `NOT_SUPPORTED` 或 `unknown action`）。

## 排障

### 网关重启后扩展一直「断开—重连」

**现象**：重启 Jarvis 主网关后，popup 里该网关状态在「连接中 / 未连接」之间反复跳动，
控制台持续打印 `ws closed 4401 Unauthorized`。

**原因**：网关未设置 `JARVIS_JWT_SECRET` 时，JWT 签名密钥在每次启动时随机生成
（`src/jarvis/jarvis_web_gateway/jwt_utils.py`）。网关重启后密钥变化，浏览器页面
`localStorage` 里缓存的旧 Token 立即失效，扩展用旧 Token 重连必然被拒。

**扩展侧的处理**（v1.1+）：`ws_client.js` 收到 `4401`（Unauthorized）/ `4403`（Forbidden）
关闭码时**不再指数退避重连**，而是转交 `service_worker.js` 的 `handleAuthError()`：

1. 清空该网关的 Token 缓存，关闭旧连接；
2. 重新从 Jarvis 页面探测一次 Token（`requestTokenFromPages`）；
3. 探测到新 Token → 自动重连；探测不到 → 停止重连并提示重新登录。

连续失败超过 3 次（`AUTH_ERROR_MAX_RETRIES`）后不再自动重连，避免无限空转；
计数在握手成功、手动点「连接」或「断开」时清零。

**断开时也会刷新 Token**：点「断开」会清空该网关的 Token 缓存，并从页面重新探测一次
登录态写回缓存（探测不建链）。因此若你已在页面重新登录，断开再连接即可用上新 Token；
移除网关则不会探测。

**你需要做什么**：在浏览器中**重新登录一次**该网关的 Jarvis 页面（刷新后重新登录），
让页面拿到新 Token；然后回到 popup 点一次「连接」即可。

> 根治办法是给网关设置固定的 `JARVIS_JWT_SECRET` 环境变量，使密钥在重启后保持不变。
> 本扩展侧的自愈只是缓解，无法让已失效的 Token 起死回生。

## 安全说明

- 本方案**不做权限控制**（设计决策），安全边界由插件侧承担
- 连接需携带有效网关 Token；Token 由 Jarvis 网页登录态自动提供
- **Token 复用风险（已知取舍）**：前端通过 `window.__jarvisAuthBridge` 暴露 Token，
  同页面脚本理论上可读取。当前版本接受此风险以换取零配置体验，
  后续可升级为 `externally_connectable` + 固定扩展 ID 的强隔离方案
- Token 仅缓存在 service worker 内存中，不写入 `chrome.storage`
- 建议使用 `wss://` 加密连接
- **高敏感权限风险**：`cookies` / `webRequest` / `management` / `nativeMessaging` /
  `proxy` / `privacy` / `browsingData` / `contentSettings` 能力已超出「操作网页」范畴，
  可读取登录凭证、改写网络流量、卸载其他扩展、清除浏览数据。本方案**不做权限控制**
  （设计决策），因此这些能力对已连接的 Agent 完全开放。请确保：
  1. 只连接你信任的网关（Token 泄露等同于浏览器被完全接管）；
  2. 高敏感 action（尤其是 `browsingdata.remove`、`extmgr.uninstall`、`cookie.remove`、
     `proxy.set_settings`）在调用前由 Agent 向你明确说明并征得同意；
  3. 不需要时从 `manifest.json` 移除对应权限并重新加载扩展。
