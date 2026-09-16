---
name: browser_ext_script
description: 当需要为 Jarvis 浏览器扩展编写、安装或调试页面脚本（类油猴脚本）时触发。每当用户提及"浏览器扩展脚本"、"browser_ext 脚本"、"script.run"、"脚本管理"、"页面主世界脚本"、"油猴脚本"时触发。不触发：仅使用 browser_ext 内置 action（用 jarvis_tool_usage）；仅用 jb/Playwright 做浏览器自动化（用 jarvis_browser_cli）；仅编写普通 Node/Python 脚本（用 script-generation）。
---

# Jarvis 浏览器扩展脚本编写规范

## 规则简介

本规则约束「Jarvis Browser Bridge 扩展」中**页面脚本**（类油猴脚本）的编写、安装与调试。
这类脚本通过扩展在目标标签页的 **MAIN 世界**执行，可访问页面自身的 JS 对象（如 `window.ze`），
从而完成 `browser_ext` 内置 action 覆盖不到的操作。适用于把某个站点的复杂交互封装成可复用 action。

相关源码位置（以 `{{ git_root_dir }}` 为仓库根）：

- 脚本仓库：`{{ git_root_dir }}/browser_extension/background/script_manager.js`
- 脚本执行器：`{{ git_root_dir }}/browser_extension/background/executors/script_executor.js`
- 路由表：`{{ git_root_dir }}/browser_extension/background/command_router.js`
- 示例脚本：`{{ git_root_dir }}/browser_extension/README.md`（含脚本格式与完整示例）

## 你必须遵守的原则

### 1. 脚本必须是自包含的纯 JS 源码

**要求的明确：**

- **必须**：脚本源码在页面 MAIN 世界用 `new Function("module", "exports", src)` 求值，
  因此**不能**使用 `import` / `export` 语句，也不能依赖扩展侧的任何变量。
- **必须**：通过下列两种方式之一导出脚本对象：
  - `globalThis.__JARVIS_SCRIPT__ = { ... }`
  - `module.exports = { ... }`（`module` 由执行器作为形参传入）
- **必须**：导出对象含 `name` 与 `actions`；`actions` 是「action 名 → `{ run(args) }` 或函数」的映射。
- **禁止**：在源码里写 `import`/`export`、`require`、或引用扩展 background 的模块。

**示例：**

```js
globalThis.__JARVIS_SCRIPT__ = {
  name: "mysite",
  version: "1.0.0",
  description: "某站点操作",
  match: ["example.com"], // 仅作提示，扩展不强制拦截
  actions: {
    getTitle: { desc: "读取标题", run: () => document.title },
    clickByText: {
      desc: "按文本点击",
      params: { text: "string" },
      run: ({ text }) => {
        const el = [...document.querySelectorAll("button")].find(
          (b) => b.textContent.trim() === text,
        );
        if (!el) throw new Error("not found: " + text);
        el.click();
        return { ok: true };
      },
    },
  },
};
```

### 2. 返回值必须可 JSON 序列化

**要求的明确：**

- **必须**：action 的返回值经 `safeSerialize` 处理（`JSON.parse(JSON.stringify(v))`），
  因此 DOM 节点、函数、循环引用、`undefined` 都会丢失或报错。
- **必须**：只返回基本类型或纯数据对象（字符串、数字、布尔、数组、普通对象）。
- **禁止**：直接 `return document.querySelector(...)` 这类 DOM 对象或 window 对象。

### 3. 写操作必须显式、可控、可回滚

**要求的明确：**

- **必须**：涉及修改页面/服务端数据的 action（提交、删除、发送）要单独命名，且**不得**在脚本加载时自动执行。
- **必须**：优先提供对应的「查询」action（如 `getState`）与「撤销」能力（如页面自带 undo），便于验证与回滚。
- **禁止**：脚本一加载就发起写操作；禁止用「全选 + 删除」这类粗粒度操作清空内容。

### 4. 校验是弱校验，语法错误在运行时才暴露

**要求的明确：**

- **必须**：知道 `validateSource` 只做字符串层面的检查（是否含导出标记、是否含 `actions`、括号是否配平），
  它**不做**真正的语法解析——因为 MV3 扩展页 CSP 为 `script-src 'self'`，禁用 `unsafe-eval`。
- **必须**：安装后务必用一次「只读 action」实跑，确认脚本能正常求值与执行。
- **禁止**：仅凭「安装成功」就认定脚本可用。

## 你必须执行的操作

### 操作一：编写脚本

**执行步骤：**

1. 先确认目标页面的关键 JS 对象挂在哪个 window（顶层还是 iframe 内），
   用只读探测 action 验证可达性，再写后续逻辑。
2. 按上述「脚本对象」结构编写，`actions` 中每个条目给 `desc` 与 `params` 便于调用方理解。
3. 提供至少一个**只读** action（如 `getState`），作为连通性与就绪度的探针。
4. 用 `node --check <file>` 做基本语法检查（扩展环境无 eslint 时这是最低保障）。

**注意事项：**

- 页面若渲染在 iframe 中，需遍历 `document.querySelectorAll("iframe")` 取 `contentWindow`
  再查找目标对象；跨域 iframe 访问会抛错，必须 `try/catch` 兜底。
- 同一页面连续执行脚本时，执行器会先 `delete globalThis.__JARVIS_SCRIPT__`，
  因此**不要**依赖上一次执行残留的全局状态。

### 操作二：安装脚本

**执行步骤：**

1. 通过扩展 popup →「脚本管理」粘贴源码安装，或用「从本地文件导入」。
2. 也可由 Agent 走网关调用 `script.install`，参数 `{ name, source, description, match, version }`；
   同名脚本会被覆盖，且保留原 `id`。
3. 安装后用 `script_list` 确认 `script_id`、`enabled`、`source_size`。

**注意事项：**

- 调用 `script_run` 用的参数是 **`script_id`（脚本 id，形如 `s-xxx`）**，不是脚本名；
  另有 `script_action`（脚本内要执行的 action 名）、`script_args`（传给它的参数对象）、可选 `tab_id`。
- 这三个 action 已作为 `browser_ext` 工具的 action 暴露：`script_list` / `script_get` / `script_run`。
  安装/卸载/启停/导出脚本同样已暴露为工具 action：`script_install` / `script_uninstall` /
  `script_set_enabled` / `script_export`（参数名见 `browser_ext_usage.md` 的「脚本管理」表）。
  需要更底层控制时也可走网关 HTTP：`POST {master_url}/api/browser-ext/command`，
  body `{ session_id, action:"script.install", params:{...}, timeout }`。
  ⚠️ `{master_url}` 必须是 **Agent 所在节点能访问到的 master 地址**，不要硬编码 `127.0.0.1:8000`
  （Agent 在子节点时 `127.0.0.1` 指向子节点本地，连不上 master）。
  可用 `gateway_manager(action="get_master_url")` 查询当前节点实际使用的 master 地址。
- 网关调用：`POST {master_url}/api/browser-ext/command`，
  body `{ session_id, action, params, timeout }`，header `Authorization: Bearer $JARVIS_AUTH_TOKEN`。
- 扩展改动后需在 `edge://extensions/` 重载扩展才生效。

### 操作三：调试与验证

**执行步骤：**

1. 先跑只读 action 确认 `{ ok: true, result: ... }`。
2. 若需读取复杂返回值，用 `debugger.send_command` + `Runtime.evaluate`
   （`returnByValue: true, awaitPromise: true`），因为 `script.execute` 的返回值不透传。
3. 写操作后，用独立的只读手段（如服务端接口的 `revision`/时间戳）验证是否真正生效。
4. 出错时读 `err.code`（`cmdError(code, message)` 抛的 `Error`，code 挂在 `err.code` 上，不在 message 里）。

**注意事项：**

- 页面 CSP 可能限制 ISOLATED 世界的 eval，故脚本一律在 MAIN 世界执行。
- 页面若通过 WebSocket 实时提交（如协同编辑），写操作可能在调用返回时**已经落库**，
  验证时必须查服务端版本号而非只看本地 DOM。
- 坐标/偏移类操作要建立两套坐标系（如「读取文本的字符偏移」与「删除接口的偏移」）的映射，
  直接混用会删错位置；每次点击后校验焦点元素位置再继续。

### 操作四：嵌入 iframe 的 canvas 富文本编辑器

**背景（已实测）：** 部分在线文档站点把编辑器渲染在 `iframe` 内，正文由 `canvas` 绘制，
编辑器实例挂在 iframe 的 `contentWindow` 上。这类站点常走 WebSocket 协同编辑（Etherpad 风格 OT），
**编辑即实时落库、没有保存按钮**，因此验证写操作必须查服务端 `revision`，不能只看本地 DOM。

**执行步骤：**

1. 取编辑器对象：遍历 `document.querySelectorAll("iframe")`，在 `contentWindow` 上找编辑器实例，
   全程 `try/catch` 兜底（跨域 iframe 会抛错）。
2. 注入脚本时用 **iframe 自己的 `Function` 构造器**：`new w.Function("module","exports",src)`。
   若用外层 `new Function` 再 `fn.call(w, ...)`，`globalThis` 仍指向外层 window，
   `w.__JARVIS_SCRIPT__` 会取不到。注入前先 `delete w.__JARVIS_SCRIPT__`。
3. 富文本写入统一走编辑器**命令层**（形如 `editor.executeCommandAndMoveCursor({ command, range:{startOffset,endOffset}, data })`）。
   **禁止**直接调底层 OT 适配器（如 `editor.otAdaptor.applyBatchOperations(...)`），会破坏内部状态（报 `Too many closing tags`）。
4. 写前先 `editor.focus()` 建立真实 DOM 选区，再 `editor.setSelection(offset)`。
5. 写后用服务端接口读 `revision`/`contentBody` 校验落库。

**已验证的编辑器能力（实测有效，命令名以目标站点实际 API 为准）：**

| 能力       | 调用方式                                                                                                                                                                        |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 纯文本插入 | `addTextAndAttribs` + `data:{text}`                                                                                                                                             |
| 富文本     | `addTextAndAttribs` + `data:{text, attribs}`；`attribs` 支持 `size`（**不带 px**，`'24'`→`24px`，传 `'24px'` 会变 `24pxpx`）、`family`、`color`、`bold:'true'`、`href`+`target` |
| 超链接     | 同上，`attribs:{href, target}`                                                                                                                                                  |
| 表格插入   | 走编辑器的剪贴板插入器（`editor.clipboard.inserter.*`）传入普通 HTML `<table>`，会被解析为原生表格节点                                                                          |
| 读取       | `getText()` / `getHtml()` / `getTextLength()`（返回 `[len, 字号]`）/ `getMacroList()`（**返回 Promise**）                                                                       |

**未攻克 / 不稳定（不要臆断为可用）：**

- **段落级属性**（行距 `lineHeight`、对齐 `textAlign`）：走批量属性命令 + `attribs:{lineHeight,textAlign,'tag-start':'p'}`，
  仅当编辑器处于**真实交互态**（用户点击过文档、有真实 DOM 选区、range 长度为 0/1）时才生效；
  纯脚本 `setSelection` 后调用时 `revision` 会变但段落 style 常不更新。唯一稳定成功路径是**真实点击菜单项**。
- **宏插入**：直接插带宏标记的 HTML **不被识别**（`revision` 不变），
  需走编辑器的宏引擎注册流程（`macroEngine.getMacroCreateUtils(key)` 返回 `macroNode`/`attribute`/`params`/`genNodesByHtml`，
  核心是 `coreModelNodeToMacroNode`），尚未攻克。
- **代码块**：本质是宏，`<pre><code>` HTML 会被过滤，尚未攻克。

#### 关键坑：offset 体系不一致

- 写操作的 `offset` 是编辑器**内部 offset**（来源 `editor.otAdaptor.rep.text`）；
  它与 `getText()` 的语义索引**不一致**（`getText()` 含 `\n`，内部文本用空格填充）。
- **必须**用 `editor.otAdaptor.rep.text.indexOf(目标文本)` 求内部 offset，再 `setSelection`；
  直接拿 `getText()` 的下标去写会插错位置。
- offset 落在表格内部会报 `Error: pos=…, table cannot contain text`，插入点必须避开表格区间。

**其他实测坑：**

- 清空单元格：点进单元格 → `End` → `Backspace` × N（N 给足，超出无副作用）。
  **严禁 `Ctrl+A`**（那是全选整个文档，配合 Delete 会删光全文）；慎用 `Home`+`Shift+End`+`Delete`
  （只作用于当前视觉行，单元格内容换行时会有残留）。误删可用 `Ctrl+Z` 撤销。
- 单元格文字过长会换行占多行，光标输入框的 `style.top` 反映**光标所在视觉行**而非单元格顶部。
- 点击坐标有抖动，每次点击后必须校验光标输入框的 `style.left/top` 命中目标单元格再继续操作。
- 通过 CDP 发键盘事件必须给全 `key`/`code`/`windowsVirtualKeyCode`/`nativeVirtualKeyCode`，
  `Shift` 用 `modifiers=8`、`Ctrl` 用 `modifiers=2`，否则事件无效。
- 每列填完后列宽会变，后续列需重新扫描 x 坐标标定。
- canvas 正文抓文字需 hook `CanvasRenderingContext2D.prototype.fillText`，且必须**在渲染前**装好；
  已渲染完的页面需重装 hook 后触发重绘（CDP 滚轮事件可触发）。

## 检查清单

完成任务后，你必须确认：

- [ ] 脚本为自包含纯 JS，无 `import`/`export`/`require`
- [ ] 通过 `globalThis.__JARVIS_SCRIPT__` 或 `module.exports` 导出，且含 `name` 与 `actions`
- [ ] 所有 action 返回值可 JSON 序列化
- [ ] 至少有一个只读 action 作为探针
- [ ] 写操作独立命名、不自动执行、有回滚或验证手段
- [ ] 已用 `node --check` 检查语法
- [ ] 已用只读 action 实跑确认脚本可求值执行
- [ ] 写操作已用服务端版本/时间戳等独立手段验证生效

## 相关资源

- 工具使用：`{{ rule_file_dir }}/jarvis_tool_usage.md`
- 浏览器自动化（服务端 Playwright）：`{{ rule_file_dir }}/jarvis_browser_cli.md`
- 脚本生成通用规范：`{{ rule_file_dir }}/script-generation.md`
- 扩展说明：`{{ git_root_dir }}/browser_extension/README.md`
