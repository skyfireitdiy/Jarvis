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
│   ├── service_worker.js          # 入口：连接管理 + 指令分发 + 登录态接收
│   ├── ws_client.js               # WebSocket 连接、心跳、重连
│   ├── command_router.js          # action → executor 映射
│   └── executors/
│       ├── tab_executor.js        # 标签页 / 导航
│       ├── dom_executor.js        # DOM 读写（executeScript 注入）
│       └── capture_executor.js    # 截图
├── content/
│   └── content_script.js          # 页面内脚本：登录态桥接 + 页面元信息
└── popup/
    ├── popup.html                 # 连接配置 / 状态 / 高危确认 UI
    └── popup.js
```

## 支持的指令（action）

| 类别   | action                                                                                                                                                  |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 标签页 | `tab.list` `tab.activate` `tab.close` `tab.create`                                                                                                      |
| 导航   | `page.navigate` `page.reload` `page.back` `page.forward`                                                                                                |
| DOM    | `dom.query` `dom.get_text` `dom.get_html` `dom.click` `dom.type` `dom.hover` `dom.select` `dom.wait_for` `dom.press_key` `dom.scroll` `dom.upload_file` |
| 脚本   | `script.execute`                                                                                                                                        |
| 捕获   | `capture.screenshot`（支持 `full_page` 整页截图）                                                                                                       |

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

**握手**：连接后插件发送 `hello`（含扩展版本、浏览器信息、标签页快照），网关回 `hello_ack`（含 `session_id`）。

**心跳**：插件每 20s 发送 `{"type":"ping"}`，网关回 `{"type":"pong"}`。

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

## 安全说明

- 本方案**不做权限控制**（设计决策），安全边界由插件侧承担
- 连接需携带有效网关 Token；Token 由 Jarvis 网页登录态自动提供
- **Token 复用风险（已知取舍）**：前端通过 `window.__jarvisAuthBridge` 暴露 Token，
  同页面脚本理论上可读取。当前版本接受此风险以换取零配置体验，
  后续可升级为 `externally_connectable` + 固定扩展 ID 的强隔离方案
- Token 仅缓存在 service worker 内存中，不写入 `chrome.storage`
- 建议使用 `wss://` 加密连接
