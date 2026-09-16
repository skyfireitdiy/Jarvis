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
- 示例脚本：`{{ git_root_dir }}/browser_extension/README.md` 与 `~/tmp/icenter.js`

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
  安装/卸载/启停/导出脚本（`script.install`/`uninstall`/`set_enabled`/`export`）**未**暴露为工具 action，
  需要时走网关 HTTP：`POST {master_url}/api/browser-ext/command`，
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
