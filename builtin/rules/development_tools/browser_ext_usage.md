---
name: browser_ext_usage
description: 当需要操作用户本地真实浏览器中的网页时触发。每当用户提及"browser_ext"、"浏览器扩展工具"、"操作用户浏览器"、"复用登录态"、"打开网页点击"、"真实标签页"时触发。不触发：仅用 jb/Playwright 在服务端启动浏览器（用 jarvis_browser_cli）；仅读取网页内容（用 read_webpage）；仅查看可用工具列表（用 jarvis_tool_usage）。
---

# browser_ext 工具使用指南

## 规则简介

`browser_ext` 驱动的是**用户自己浏览器**里已登录的真实标签页（通过用户安装的 Jarvis Browser Bridge 扩展），
可复用登录态与 Cookie，适合操作需要登录的内网站点。
它与 `jb`（服务端 Playwright 启动独立浏览器）互补：能用 `browser_ext` 就不要用 `jb`。

**核心约束**：每次调用只能执行一个 action；操作的是用户真实浏览器，写操作可能产生不可逆后果。

## 你必须遵守的原则

### 1. 先建会话，再定标签页

**要求的明确：**

- **必须**：任何操作前先调 `list_sessions` 拿 `session_id`（除 `list_sessions` 外所有 action 都必填 `session_id`）。
- **必须**：需要指定页面时先调 `list_tabs` 拿 `tab_id`；不传 `tab_id` 时多数操作作用于**当前活动标签页**。
- **禁止**：凭空猜测 `session_id` 或 `tab_id`。

**示例：**

```text
browser_ext(action="list_sessions")
browser_ext(action="list_tabs", session_id="<sid>")
```

### 2. 读值优先用 evaluate，不要依赖 execute_script 的返回值

**要求的明确：**

- **必须**：需要拿到 JS 求值结果时用 `evaluate`（走 CDP `Runtime.evaluate`，`returnByValue`），
  它不受页面 CSP 限制，相当于 F12 Console 直接敲表达式。
- **必须**：`execute_script` 仅用于「执行副作用」，其返回值**不透传**，不要用它读值。
- **禁止**：用 `execute_script` 的返回值做判断。

### 3. 动手前先盘点扩展里已装的脚本

**要求的明确：**

- **必须**：接到浏览器操作任务后，**第一步**先枚举扩展里已安装的脚本，看看有没有现成能力可直接复用。
  这是获得「比裸 DOM 操作强得多」的能力的捷径：脚本跑在页面**主世界**，能访问页面自身的 JS 对象
  （如站点自带的编辑器实例），可绕过 CSP、iframe 隔离与坐标点击的脆弱性。
- **必须**：用 `script_list` 拿脚本清单（含 `script_id`/`name`/`description`/`match`/`enabled`），
  再用 `script_get`（传 `script_id`）读源码，从中提取该脚本导出的 **action 名、desc 与 params**。
- **必须**：脚本的 `match` 与目标页面 URL 匹配、且 `enabled` 为 true 时才可用；命中则优先 `script_run`，
  不要重复用 `click`/`type`/`evaluate` 手搓同样的逻辑。
- **禁止**：在未盘点脚本的情况下直接手搓底层 DOM 操作；禁止凭脚本名猜测 action，必须以 `script_get` 源码为准。

**示例：**

```text
browser_ext(action="script_list", session_id="<sid>")
browser_ext(action="script_get", session_id="<sid>", script_id="s-xxxxxxxx")
browser_ext(action="script_run", session_id="<sid>", script_id="s-xxxxxxxx", script_action="getEditor", script_args={}, tab_id=123)
```

> 备选：若工具不可用，也可直接走网关 HTTP：`POST {master_url}/api/browser-ext/command`，
> body `{ session_id, action:"script.list"|"script.get"|"script.run", params, timeout }`，
> header `Authorization: Bearer $JARVIS_AUTH_TOKEN`（`script.run` 的 `params` 内为 `{id, action, args, tab_id}`）。
> ⚠️ `{master_url}` 必须是 **Agent 所在节点能访问到的 master 地址**，**不要**硬编码 `127.0.0.1:8000`——
> Agent 跑在子节点时，`127.0.0.1` 是子节点本地、并非 master，会连不上。
> 可用 `gateway_manager(action="get_master_url")` 查当前节点实际使用的 master 地址。
> 优先用上面的 `browser_ext` 工具 action，它内部已使用正确的 master 地址。

### 4. 写操作前先确认目标

**要求的明确：**

- **必须**：点击/输入前先用 `query`、`get_text` 或 `evaluate` 确认目标元素存在且内容符合预期。
- **必须**：涉及提交、删除、发送等不可逆操作时，先向用户说明将要做什么。
- **禁止**：用「全选 + 删除」这类粗粒度操作清空内容；禁止盲目批量点击。

### 5. 高敏感 action 必须显式获得用户授权

**要求的明确：**

- **必须**：下列高敏感 action 在调用前**逐次**向用户说明「要做什么、影响范围、是否可逆」，得到明确同意后才执行：
  `cookie_get`/`cookie_get_all`/`cookie_set`/`cookie_remove`、`netrule_register`/`netrule_unregister`、
  `extmgr_set_enabled`/`extmgr_uninstall`、`native_send`、`proxy_set_settings`/`proxy_clear_settings`、
  `privacy_set`、`browsingdata_remove`、`contentsettings_set`/`contentsettings_clear`。
- **必须**：明确告知用户**不可逆**操作（`cookie_remove`、`netrule_unregister`、`extmgr_uninstall`、
  `browsingdata_remove`、`contentsettings_clear`、`history_remove`/`history_remove_range`、
  `bookmark_remove`/`bookmark_remove_tree`、`download_erase`、`script_uninstall`），
  并在执行前确认用户已备份或不介意丢失。
- **必须**：只读类高敏感 action（`cookie_get`、`extmgr_list`、`proxy_get_settings`、`privacy_get`、
  `browsingdata_settings`）可先执行以了解现状，但结果可能含**登录凭证、扩展清单、浏览痕迹**等隐私数据，
  不要写入日志、提交到仓库或转发给第三方。
- **禁止**：未经用户明确同意就调用任何写类高敏感 action；禁止把高敏感 action 放进循环批量执行。

### 6. 善用等待，避免竞态

**要求的明确：**

- **必须**：页面跳转或异步渲染后，用 `wait_for` 等待目标元素出现，再执行后续操作。
- **必须**：长耗时操作（如网络采集）显式调大 `timeout`。
- **禁止**：在元素尚未出现时直接点击并假定成功。

### 7. 剪贴板写入要求页面真实聚焦

**要求的明确：**

- **必须**：`clipboard_write`/`clipboard_write_from_url` 要求目标页**真正获得焦点**，否则报 `CLIPBOARD_WRITE_FAILED`。
  必要时先 `activate_tab` 激活标签页，并用 `click` 派发一次真实点击建立焦点。
- **必须**：`clipboard_write_from_url` 的 `clipboard_url` 优先传**完整绝对 URL**；
  相对路径仅支持 `/uploads/` 前缀（会用已连接网关补全，子节点场景易补错）。

## 你必须执行的操作

### 操作一：标准操作流程

**执行步骤：**

1. `list_sessions` → 取 `session_id`（返回空列表说明扩展未连接，需提示用户）。
2. `script_list` → **先盘点扩展里已装的脚本**，看有无匹配当前站点/任务的现成能力（见「操作二」）。
3. `list_tabs` → 取 `tab_id`，确认目标页面已打开；未打开则用 `navigate` 或 `new_tab`。
4. 有匹配脚本则 `script_get` 读源码确认 action 与参数，再 `script_run` 调用；否则执行目标操作（`get_text`/`click`/`type`/`screenshot` 等）。
5. 用只读操作（`get_text`/`get_page_info`/`evaluate`，或脚本内的只读 action）验证结果。

**注意事项：**

- `navigate` 不传 `tab_id` 会**新建页面**。默认（`new_window` 为 `true`）会**优先在「不含 Jarvis 前端页面」的窗口中新建标签页**，
  以免把自动化打开的页面混进用户查看 Jarvis 的窗口；仅当所有窗口都含 Jarvis 前端页面时才新开窗口。
  想在当前窗口新开标签页则传 `new_window=false`。
- 页面渲染在 iframe 内时，`selector` 作用于顶层文档；需用 `evaluate` 进入 iframe 的 `contentDocument` 操作。
- 扩展改动后需在 `edge://extensions/` 重载扩展才生效。

### 操作二：action 速查

**执行步骤：** 按需选用，每次仅一个 action。

#### 会话与标签页

| action                        | 必填参数              | 说明                                              |
| ----------------------------- | --------------------- | ------------------------------------------------- |
| `list_sessions`               | 无                    | 列出在线会话，返回 `session_id` 列表              |
| `list_tabs`                   | `session_id`          | 列出标签页，返回 `tab_id`/`url`/`title`           |
| `activate_tab`                | `session_id`,`tab_id` | 切换到指定标签页                                  |
| `close_tab`                   | `session_id`,`tab_id` | 关闭标签页                                        |
| `new_tab`                     | `session_id`          | 新建标签页；可选 `url`、`new_window`（默认 true） |
| `navigate`                    | `session_id`,`url`    | 导航；可选 `tab_id`、`new_window`                 |
| `reload` / `back` / `forward` | `session_id`          | 重新加载 / 后退 / 前进；可选 `tab_id`             |

#### DOM 操作

| action               | 必填参数                            | 说明                                                                       |
| -------------------- | ----------------------------------- | -------------------------------------------------------------------------- |
| `get_text`           | `session_id`,`selector`             | 读取元素文本                                                               |
| `get_html`           | `session_id`,`selector`             | 读取元素 innerHTML                                                         |
| `query`              | `session_id`,`selector`             | 查询元素信息；可选 `all=true` 返回全部匹配                                 |
| `click`              | `session_id`,`selector`             | 点击元素                                                                   |
| `type`               | `session_id`,`selector`,`text`      | 输入文本                                                                   |
| `hover`              | `session_id`,`selector`             | 悬停                                                                       |
| `select`             | `session_id`,`selector`,`value`     | 选择下拉框选项                                                             |
| `press_key`          | `session_id`,`key`                  | 按键（如 Enter/Escape/Tab/ArrowDown）；可选 `selector` 先聚焦              |
| `scroll`             | `session_id`                        | 滚动；`selector` 滚动到元素，或 `x`/`y` 像素偏移；可选 `behavior`          |
| `wait_for`           | `session_id`,`selector`             | 等待元素；可选 `state`（visible/hidden/attached，默认 visible）、`timeout` |
| `upload_file`        | `session_id`,`selector`,`file_path` | 上传本地文件（需 debugger 权限）                                           |
| `get_computed_style` | `session_id`,`selector`             | 计算样式；可选 `props`（kebab-case 属性名数组）                            |

#### 信息与调试（相当于 F12 各面板）

| action                 | 必填参数                  | 说明                                                                                 |
| ---------------------- | ------------------------- | ------------------------------------------------------------------------------------ |
| `get_page_info`        | `session_id`              | 页面基础信息（url/title/ready_state/viewport/scroll/document）                       |
| `get_console_logs`     | `session_id`              | console 日志；可选 `limit`（默认 100）、`clear`。首次调用装 hook，需页面产生新日志   |
| `evaluate`             | `session_id`,`expression` | CDP 求值任意表达式；可选 `await_promise`（默认 true）                                |
| `send_cdp_command`     | `session_id`,`method`     | 透传任意 CDP 命令；可选 `cdp_params`                                                 |
| `get_network_requests` | `session_id`              | 采集网络请求；可选 `duration_ms`（默认 3000）、`limit`、`filter`。**会阻塞采集时长** |

#### 已装脚本（类油猴，优先复用）

扩展支持安装「用户脚本」，每个脚本导出若干 `action`，在页面**主世界**执行，可访问页面自身 JS 对象。
**能力远强于裸 DOM 操作，动手前务必先盘点。**

| action        | 必填参数                                 | 说明                                                                                        |
| ------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------- |
| `script_list` | `session_id`                             | 列出已装脚本元数据：`script_id`/`name`/`description`/`match`/`enabled`/`version`            |
| `script_get`  | `session_id`,`script_id`                 | 读取单个脚本（**含源码**，据此得知有哪些 action、参数与行为）                               |
| `script_run`  | `session_id`,`script_id`,`script_action` | 在目标页主世界执行脚本的某个 action；可选 `script_args`（对象）、`tab_id`（默认当前活动页） |

**注意事项：**

- `script_id` 形如 `s-xxxxxxxx`，**不是脚本名**；先 `script_list` 拿 `script_id` 再 `script_run`。
- `script_run` 里：`script_action` 是要执行的**脚本内 action 名**（取自 `script_get` 源码），
  `script_args` 是传给它的参数对象。二者不要与工具自身的 `action` 字段混淆。
- 脚本必须 `enabled` 为 true，且目标页 URL 命中其 `match`，否则 `script_run` 报错。
- 目标页需在扩展的 host 权限内，否则报 `PROTECTED_PAGE`（如 `edge://`、未授权域）。
- 脚本 action 的返回值经 JSON 序列化后透传（DOM/函数/循环引用会丢失）；
  写操作类 action 会真实改动页面/服务端数据，调用前先向用户说明。
- 没有匹配脚本时，才退回 `click`/`type`/`evaluate` 等底层操作。
- 安装/卸载/启停/导出脚本已暴露为工具 action，见下方「脚本管理」表；
  需要更底层控制时也可走网关 HTTP：`POST {master_url}/api/browser-ext/command`，`action` 传 `script.install` 等，`params` 传对应字段。
  同样地，`{master_url}` 要用 Agent 所在节点能访问到的 master 地址，不要硬编码 `127.0.0.1:8000`，
  可用 `gateway_manager(action="get_master_url")` 查询。

#### 脚本管理（安装/卸载/启停/导出/网关目录中转）

| action                    | 必填参数                                   | 说明                                                                                                                     |
| ------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| `script_install`          | `session_id`,`script_name`,`script_source` | 安装脚本；可选 `script_description`/`script_match`/`script_version`。同名覆盖并保留原 `id`                               |
| `script_install_from_url` | `session_id`,`script_url`                  | 从 URL 下载并安装脚本；可选 `script_name`/`script_description`/`script_match`/`script_version`。**源码不经对话传输**     |
| `script_uninstall`        | `session_id`,`script_id`                   | 卸载脚本（**不可逆**，源码一并丢失，卸载前建议先 `script_export` 或 `script_save` 备份）                                 |
| `script_set_enabled`      | `session_id`,`script_id`,`script_enabled`  | 启用/停用脚本                                                                                                            |
| `script_export`           | `session_id`,`script_id`                   | 导出脚本源码，用于备份或迁移（**会把源码原文返回给 Agent**，大脚本慎用）                                                 |
| `script_save`             | `session_id`,`script_id`                   | 把扩展里的脚本保存到网关数据目录 `{data_dir}/browser_scripts/`；可选 `script_name`（保存文件名）。**只回传路径与字节数** |
| `script_load_from_file`   | `session_id`,`script_name`                 | 从网关数据目录读取脚本并安装到扩展；可选 `script_description`/`script_match`/`script_version`。**只回传安装元数据**      |

**避免把脚本原文带进上下文（重要）**：
`script_export` 会把脚本源码原样返回给 Agent，大脚本会迅速吃满上下文。**备份/迁移脚本时优先用
`script_save` + `script_load_from_file` 这一对**：前者把源码落盘到网关目录，后者从目录读回并安装，
两者都只回传路径/元数据，源码始终不进入对话。

**从 URL 安装（`script_install_from_url`）**：

- 源码由扩展后台 `fetch` 下载，**不经过对话上下文**，适合把脚本托管在任意 HTTP 静态目录后按 URL 分发。
- 网关的 `/uploads/` 目录已挂载为静态服务（`{data_dir}/uploads` → `{master_url}/uploads/<file>`），
  把 `.js` 放到该目录即可用 URL 直接安装（**仅限公网可达的网关**，原因见下）。
- **安全限制（SSRF 防护）**：扩展侧会拒绝 `file:`/`data:` 等非 http(s) 协议，
  并拒绝回环与内网地址（`127.0.0.1`、`localhost`、`10.x`、`172.16-31.x`、`192.168.x`、`169.254.x`、`::1`、`fe80::` 等）。
  因此**本机/内网网关不能用 URL 安装**，此时请改用 `script_save`/`script_load_from_file`（走带 Token 的网关 API，不经过该限制）。
- 脚本名可由 URL 末段自动推导（`.../my-script.js` → `my-script`），推导不出时必须显式传 `script_name`。

#### 剪贴板

| action                     | 必填参数                     | 说明                                                                        |
| -------------------------- | ---------------------------- | --------------------------------------------------------------------------- |
| `clipboard_write`          | `session_id`                 | 写入剪贴板；`clipboard_text` 或 `clipboard_base64` 二选一。要求页面真实聚焦 |
| `clipboard_write_from_url` | `session_id`,`clipboard_url` | 从 URL 取内容写入剪贴板；可选 `clipboard_mime`。要求页面真实聚焦            |

#### 书签与历史

| action                 | 必填参数                      | 说明                                                                                                |
| ---------------------- | ----------------------------- | --------------------------------------------------------------------------------------------------- |
| `bookmark_list`        | `session_id`                  | 列出书签树；可选 `bookmark_id` 指定子树                                                             |
| `bookmark_search`      | `session_id`,`bookmark_query` | 按标题/URL 关键词搜索书签                                                                           |
| `bookmark_create`      | `session_id`,`url`            | 新建书签；可选 `bookmark_title`、`bookmark_parent_id`、`bookmark_index`                             |
| `bookmark_remove`      | `session_id`,`bookmark_id`    | 删除单个书签（**不可逆**）                                                                          |
| `bookmark_remove_tree` | `session_id`,`bookmark_id`    | 删除书签及其整个子树（**不可逆**，会连带删除文件夹内所有书签）                                      |
| `history_search`       | `session_id`                  | 搜索历史；可选 `history_query`、`history_start_time`、`history_end_time`、`history_max_results`     |
| `history_recent`       | `session_id`                  | 最近历史；可选 `history_max_results`                                                                |
| `history_remove`       | `session_id`,`history_url`    | 删除某 URL 的历史记录（**不可逆**）                                                                 |
| `history_remove_range` | `session_id`                  | 按时间区间批量删除历史（**不可逆**）；可选 `history_start_time`、`history_end_time`，不传则清空全部 |

#### 下载、会话与站点

| action               | 必填参数                      | 说明                                                                    |
| -------------------- | ----------------------------- | ----------------------------------------------------------------------- |
| `download_list`      | `session_id`                  | 列出下载项；可选 `download_limit`                                       |
| `download_search`    | `session_id`,`download_query` | 按文件名/URL 搜索下载项                                                 |
| `download_start`     | `session_id`,`url`            | 发起下载；可选 `download_filename`、`download_save_as`                  |
| `download_erase`     | `session_id`,`download_id`    | 从下载列表抹除记录（**不可逆**，不删磁盘文件）                          |
| `download_pause`     | `session_id`,`download_id`    | 暂停下载                                                                |
| `download_resume`    | `session_id`,`download_id`    | 继续下载                                                                |
| `download_cancel`    | `session_id`,`download_id`    | 取消下载                                                                |
| `download_open`      | `session_id`,`download_id`    | 打开已下载的文件                                                        |
| `session_recent`     | `session_id`                  | 最近关闭的标签页/窗口；可选 `session_max_results`                       |
| `session_restore`    | `session_id`,`session_key`    | 恢复指定会话                                                            |
| `topsite_list`       | `session_id`                  | 最常访问站点列表                                                        |
| `readinglist_list`   | `session_id`                  | 阅读列表                                                                |
| `readinglist_add`    | `session_id`,`url`            | 加入阅读列表；可选 `readinglist_title`、`readinglist_has_been_read`     |
| `readinglist_remove` | `session_id`,`url`            | 移出阅读列表（**不可逆**）                                              |
| `readinglist_update` | `session_id`,`url`            | 更新阅读列表条目；可选 `readinglist_title`、`readinglist_has_been_read` |

#### 界面与事件

| action                   | 必填参数                       | 说明                                                                                  |
| ------------------------ | ------------------------------ | ------------------------------------------------------------------------------------- |
| `contextmenu_create`     | `session_id`,`menu_id`,`text`  | 创建右键菜单项；可选 `contextmenu_contexts`、`contextmenu_url_patterns`               |
| `contextmenu_remove`     | `session_id`,`menu_id`         | 移除右键菜单项                                                                        |
| `contextmenu_remove_all` | `session_id`                   | 移除全部右键菜单项                                                                    |
| `contextmenu_list`       | `session_id`                   | 列出本扩展创建的右键菜单项                                                            |
| `alarm_create`           | `session_id`,`alarm_name`      | 创建定时器；可选 `alarm_delay_minutes`、`alarm_period_minutes`（周期任务用后者）      |
| `alarm_list`             | `session_id`                   | 列出定时器                                                                            |
| `alarm_clear`            | `session_id`,`alarm_name`      | 清除指定定时器                                                                        |
| `alarm_clear_all`        | `session_id`                   | 清除全部定时器                                                                        |
| `notification_create`    | `session_id`,`text`            | 发系统通知（`text` 即通知标题）；可选 `notification_message`、`notification_icon_url` |
| `notification_list`      | `session_id`                   | 列出通知                                                                              |
| `notification_clear`     | `session_id`,`notification_id` | 关闭指定通知                                                                          |
| `notification_clear_all` | `session_id`                   | 关闭全部通知                                                                          |
| `search_query`           | `session_id`,`search_query`    | 在默认搜索引擎检索；可选 `search_disposition`、`search_tab_id`                        |

#### 系统状态

| action                  | 必填参数                                  | 说明                                                                      |
| ----------------------- | ----------------------------------------- | ------------------------------------------------------------------------- |
| `idle_query_state`      | `session_id`                              | 查询空闲状态                                                              |
| `idle_set_interval`     | `session_id`,`detection_interval_seconds` | 设置空闲检测间隔（秒）                                                    |
| `idle_get_interval`     | `session_id`                              | 读取空闲检测间隔                                                          |
| `favicon_get_url`       | `session_id`,`page_url`                   | 取站点 favicon URL                                                        |
| `webnav_get_all_frames` | `session_id`,`tab_id`                     | 列出标签页内所有 frame                                                    |
| `webnav_get_frame`      | `session_id`,`tab_id`,`frame_id`          | 读取指定 frame 详情                                                       |
| `tabgroup_list`         | `session_id`                              | 列出标签组                                                                |
| `tabgroup_get`          | `session_id`,`group_id`                   | 读取标签组详情                                                            |
| `tabgroup_query`        | `session_id`                              | 按条件查询标签组；可选 `tabgroup_collapsed`、`tabgroup_title`             |
| `tabgroup_update`       | `session_id`,`group_id`                   | 更新标签组；可选 `tabgroup_title`、`tabgroup_color`、`tabgroup_collapsed` |

#### 其他

| action           | 必填参数            | 说明                                                                              |
| ---------------- | ------------------- | --------------------------------------------------------------------------------- |
| `screenshot`     | `session_id`        | 截图；可选 `full_page`。返回落盘的 PNG 路径与尺寸                                 |
| `execute_script` | `session_id`,`code` | 在页面执行 JS（高危）；可选 `world`（ISOLATED/MAIN，默认 MAIN）。**返回值不透传** |

#### 高敏感 action（调用前必须获得用户明确授权）

以下 action 涉及**凭证、系统设置、扩展管理或不可逆删除**，使用前必须逐次向用户说明并获得同意。

| action                  | 必填参数                                                   | 说明                                                                                                                                 |
| ----------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `cookie_get`            | `session_id`,`url`,`cookie_name`                           | 读取指定 cookie（含**登录凭证**，属隐私数据）                                                                                        |
| `cookie_get_all`        | `session_id`                                               | 读取全部 cookie；可选 `cookie_url`、`cookie_name`                                                                                    |
| `cookie_set`            | `session_id`,`url`,`cookie_name`                           | 写入/覆盖 cookie；可选 `cookie_value`、`cookie_domain`、`cookie_path`、`cookie_secure`、`cookie_http_only`、`cookie_expiration_date` |
| `cookie_remove`         | `session_id`,`url`,`cookie_name`                           | 删除 cookie（**不可逆**，会登出对应站点）                                                                                            |
| `netrule_list`          | `session_id`                                               | 列出已注册的网络规则                                                                                                                 |
| `netrule_register`      | `session_id`,`rule_id`,`url_filter`                        | 注册网络拦截/修改规则；可选 `netrule_types`、`netrule_blocking`、`netrule_extra_headers`、`netrule_redirect_url`                     |
| `netrule_unregister`    | `session_id`,`rule_id`                                     | 注销网络规则（**不可逆**）                                                                                                           |
| `extmgr_list`           | `session_id`                                               | 列出已安装扩展（含其他扩展信息，属隐私数据）                                                                                         |
| `extmgr_get`            | `session_id`,`extension_id`                                | 读取扩展详情                                                                                                                         |
| `extmgr_launch_app`     | `session_id`,`extension_id`                                | 启动扩展应用                                                                                                                         |
| `extmgr_set_enabled`    | `session_id`,`extension_id`,`enabled`                      | 启用/停用**其他扩展**（影响用户浏览器功能）                                                                                          |
| `extmgr_uninstall`      | `session_id`,`extension_id`                                | 卸载**其他扩展**（**不可逆**）                                                                                                       |
| `native_send`           | `session_id`,`native_host`                                 | 与本机原生程序通信；可选 `native_message`。**可执行本机任意能力，风险最高**                                                          |
| `proxy_get_settings`    | `session_id`                                               | 读取代理设置                                                                                                                         |
| `proxy_set_settings`    | `session_id`,`proxy_mode`                                  | 修改代理设置；可选 `proxy_pac_url`、`proxy_rules`、`proxy_bypass_list`                                                               |
| `proxy_clear_settings`  | `session_id`                                               | 清空代理设置（**不可逆**）                                                                                                           |
| `privacy_get`           | `session_id`,`privacy_area`,`privacy_name`                 | 读取隐私设置项                                                                                                                       |
| `privacy_set`           | `session_id`,`privacy_area`,`privacy_name`,`privacy_value` | 修改隐私设置项                                                                                                                       |
| `browsingdata_settings` | `session_id`                                               | 读取可清理的数据类型与容量                                                                                                           |
| `browsingdata_remove`   | `session_id`,`data_types`                                  | 清理浏览数据（**不可逆**，可能清掉用户全部历史/密码/缓存）                                                                           |
| `contentsettings_get`   | `session_id`,`content_type`                                | 读取内容设置                                                                                                                         |
| `contentsettings_set`   | `session_id`,`content_type`,`content_setting`              | 修改内容设置；可选 `content_pattern`                                                                                                 |
| `contentsettings_clear` | `session_id`,`content_type`                                | 清除内容设置（**不可逆**）                                                                                                           |

### 操作三：排障

**执行步骤：**

1. `list_sessions` 返回空 → 用户未安装扩展或扩展未连接，提示用户在浏览器中连接扩展。
2. 报错 `master_url is not set` → Agent 未带 `--master-url` 启动。
3. 报错 `Cannot connect to gateway` → 网关未运行。
4. 报错 `unknown action` → action 名拼写错误，对照上表。
5. 元素找不到 → 先用 `wait_for` 等待，或用 `evaluate` 检查 DOM 实际结构（可能在其他 iframe/Shadow DOM 内）。

**注意事项：**

- 返回格式统一为 `{success, stdout, stderr}`；`stdout` 是格式化后的文本（对象为 JSON 缩进文本）。
- `screenshot` 会把 base64 落盘为临时 PNG，`stdout` 只给路径与尺寸，可直接用 `add_images` 查看。
- `get_network_requests` 会阻塞 `duration_ms`，建议**先触发页面动作再调用**。

## 检查清单

完成任务后，你必须确认：

- [ ] 已通过 `list_sessions` 获取有效 `session_id`
- [ ] **已用 `script_list` 盘点扩展里已装的脚本**，匹配则优先复用（`script_run`）
- [ ] 需要指定页面时已通过 `list_tabs` 获取 `tab_id`
- [ ] 读值用的是 `evaluate`，而非 `execute_script` 返回值
- [ ] 写操作前已确认目标元素，并已向用户说明不可逆动作
- [ ] 调用高敏感 action 前已获得用户明确授权，并已告知影响范围与是否可逆
- [ ] 异步/跳转场景已用 `wait_for` 等待
- [ ] 长耗时操作已调大 `timeout`
- [ ] 结果已用只读操作验证

## 相关资源

- 工具源码：`{{ jarvis_src_dir }}/src/jarvis/jarvis_tools/browser_ext.py`
- 扩展说明：`{{ jarvis_src_dir }}/browser_extension/README.md`
- 扩展脚本编写：`{{ rule_file_dir }}/browser_ext_script.md`
- 服务端浏览器自动化：`{{ rule_file_dir }}/jarvis_browser_cli.md`
- 查看工具列表：`{{ rule_file_dir }}/jarvis_tool_usage.md`
