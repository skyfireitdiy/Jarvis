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

### 4. 善用等待，避免竞态

**要求的明确：**

- **必须**：页面跳转或异步渲染后，用 `wait_for` 等待目标元素出现，再执行后续操作。
- **必须**：长耗时操作（如网络采集）显式调大 `timeout`。
- **禁止**：在元素尚未出现时直接点击并假定成功。

## 你必须执行的操作

### 操作一：标准操作流程

**执行步骤：**

1. `list_sessions` → 取 `session_id`（返回空列表说明扩展未连接，需提示用户）。
2. `script_list` → **先盘点扩展里已装的脚本**，看有无匹配当前站点/任务的现成能力（见「操作二」）。
3. `list_tabs` → 取 `tab_id`，确认目标页面已打开；未打开则用 `navigate` 或 `new_tab`。
4. 有匹配脚本则 `script_get` 读源码确认 action 与参数，再 `script_run` 调用；否则执行目标操作（`get_text`/`click`/`type`/`screenshot` 等）。
5. 用只读操作（`get_text`/`get_page_info`/`evaluate`，或脚本内的只读 action）验证结果。

**注意事项：**

- `navigate` 不传 `tab_id` 会**新建页面**，默认在新窗口打开（`new_window` 默认 `true`，可保证前台渲染）；
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
- 安装/卸载/启停脚本（`script.install`/`uninstall`/`set_enabled`/`export`）**未**作为工具 action 暴露，
  需要时走网关 HTTP：`POST {master_url}/api/browser-ext/command`，`action` 传 `script.install` 等，`params` 传对应字段。
  同样地，`{master_url}` 要用 Agent 所在节点能访问到的 master 地址，不要硬编码 `127.0.0.1:8000`，
  可用 `gateway_manager(action="get_master_url")` 查询。

#### 其他

| action           | 必填参数            | 说明                                                                              |
| ---------------- | ------------------- | --------------------------------------------------------------------------------- |
| `screenshot`     | `session_id`        | 截图；可选 `full_page`。返回落盘的 PNG 路径与尺寸                                 |
| `execute_script` | `session_id`,`code` | 在页面执行 JS（高危）；可选 `world`（ISOLATED/MAIN，默认 MAIN）。**返回值不透传** |

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
- [ ] 异步/跳转场景已用 `wait_for` 等待
- [ ] 长耗时操作已调大 `timeout`
- [ ] 结果已用只读操作验证

## 相关资源

- 工具源码：`{{ jarvis_src_dir }}/jarvis_tools/browser_ext.py`
- 扩展说明：`{{ git_root_dir }}/browser_extension/README.md`
- 扩展脚本编写：`{{ rule_file_dir }}/browser_ext_script.md`
- 服务端浏览器自动化：`{{ rule_file_dir }}/jarvis_browser_cli.md`
- 查看工具列表：`{{ rule_file_dir }}/jarvis_tool_usage.md`
