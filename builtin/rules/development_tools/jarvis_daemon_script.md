---
name: jarvis_daemon_script
description: 当需要为 jarvis-daemon（后台服务）编写、运行或调试 JS 脚本（后台服务脚本/daemon 脚本/JS 插件）时触发。每当用户提及"后台服务脚本"、"daemon 脚本"、"run-script"、"jarvis.cap"、"jarvis.caps"、"daemon JS 插件"、"本机自动化脚本"时触发。不触发：为浏览器扩展编写页面脚本（用 browser_ext_script）；仅用 daemon 的 windows.* 能力操作桌面 GUI（用 jarvis_daemon_windows）；仅编写普通 Node/Python/Shell 脚本（用 script-generation）。
---

# jarvis-daemon 后台服务脚本编写规范

## 规则简介

本规则约束「jarvis-daemon」后台服务上**JS 脚本**（后台服务脚本）之编写、运行与调试。
jarvis-daemon 内置一个基于 [goja](https://github.com/dop251/goja) 之 JS 运行时（纯 Go、零 cgo），
脚本内通过全局对象 `jarvis` 调用 daemon 之能力（capability）做本机自动化——读取系统信息、操作文件、
执行命令、管理进程等。脚本以 daemon 进程权限运行，等同 shell 脚本权限。
相关源码位置（以 `{{ jarvis_src_dir }}` 为 Jarvis 源码根）：

- 运行时封装：`{{ jarvis_src_dir }}/daemon/internal/jsruntime/runtime.go`
- 能力桥接：`{{ jarvis_src_dir }}/daemon/internal/jsruntime/bridge.go`
- 子命令入口：`{{ jarvis_src_dir }}/daemon/cmd/jarvis-daemon/main.go`（`run-script`）
- 示例脚本：`{{ jarvis_src_dir }}/daemon/examples/system-info.js`、`list-dir.js`
- 使用说明：`{{ jarvis_src_dir }}/daemon/docs/js-plugin-usage.md`

## 你必须遵守的原则

### 1. 脚本是单文件纯 JS，无模块加载器

**要求的明确：**

- **必须**：脚本为单个 `.js` 文件，普通 JS 语法；goja 无模块加载器，
  **不能**使用 `require` / `import` / `export`，也不支持 ES 模块。
- **必须**：通过全局对象 `jarvis` 访问 daemon 能力（见下）。
- **禁止**：在脚本里写 `import`/`export`/`require`，或依赖任何外部模块。
  **示例：**

```js
// 读取系统信息（jarvis.cap 通用入口）
const res = jarvis.cap("linux.system.info", {});
if (res.success) {
  print("主机名:", res.data.hostname);
  print("操作系统:", res.data.os_name, res.data.os_version, res.data.arch);
} else {
  console.error("获取系统信息失败:", res.error);
}
```

### 2. 用 jarvis.cap 显式判断成败，用 jarvis.caps 抛异常

**要求的明确：**

- **必须**：`jarvis.cap(name, params)` 总是返回 `{success, data, error}`，**不抛异常**，
  适合需要显式判断成败之场景。
- **必须**：`jarvis.caps.<域>.<动作>(params)` 成功返回 `data`，**失败抛 JS 异常**（可 try/catch），
  适合希望失败即中断之场景。
- **必须**：能力名按 `.` 拆成嵌套对象——`linux.fs.read` → `jarvis.caps.linux.fs.read`。
- **禁止**：混用两者之成败语义（`jarvis.caps` 失败不会返回 `{success:false}`，而是抛异常）。
  **示例：**

```js
// 方式一：jarvis.cap 返回对象，显式判断
const res = jarvis.cap("linux.fs.list", { path: "/tmp" });
if (!res.success) {
  console.error("列出目录失败:", res.error);
  throw new Error("目录列表失败: /tmp");
}
for (const entry of res.data.entries) {
  print(entry.is_dir ? "[D] " + entry.name : "    " + entry.name);
}
// 方式二：jarvis.caps 嵌套调用，失败抛异常
try {
  const info = jarvis.caps.linux.system.info({});
  print("CPU 核心数:", info.cpu_count);
} catch (e) {
  console.error("嵌套调用失败:", e.message);
}
```

### 3. 延迟用 jarvis.sleep，禁用 setTimeout/setInterval

**要求的明确：**

- **必须**：goja 无宏任务事件循环，**没有** `setTimeout` / `setInterval`；
  延迟一律用 `jarvis.sleep(ms)`（Go 侧同步阻塞延迟）。
- **必须**：脚本顶层若返回 Promise 会被等待（支持 async 脚本），
  但 Promise 若在同步完成前不 resolve（依赖宏任务）会报「未完成之 Promise」。
- **禁止**：在脚本里写 `setTimeout`/`setInterval` 做延迟或调度。
  **示例：**

```js
// 等待 2 秒再继续（替代 setTimeout）
jarvis.sleep(2000);
```

### 4. 脚本以 daemon 权限运行，写操作要谨慎

**要求的明确：**

- **必须**：脚本以 daemon 进程权限运行，能调用**全部**已注册能力（等同 shell 权限），
  首版**不做沙箱隔离**——勿运行来源不明之脚本。
- **必须**：脚本中**不要硬编码敏感凭据**；`jarvis.args` 仅来自 CLI `--arg`，无网络输入，无 XSS 注入面。
- **必须**：写操作（改文件、杀进程、执行命令）先说明意图，任务结束清理临时文件。
- **禁止**：未经确认就执行破坏性操作（删文件、结束进程、改系统配置）。

### 5. 能力随平台而异，先 listCaps 再调用

**要求的明确：**

- **必须**：可用能力随平台而异（Linux 见 `linux.*`，Windows 见 `windows.*`，通用见 `any.*`），
  调用前可用 `jarvis.listCaps()` 确认当前平台实际可用之能力。
- **必须**：能力名带平台前缀（如 `linux.fs.list`、`windows.script.exec`），调用前确认平台匹配。
- **禁止**：凭猜测调用未确认之能力名或参数。
  **示例：**

```js
// 列出当前平台所有可用能力
jarvis.listCaps().forEach((c) => print(c.name, "-", c.description));
```

## 你必须执行的操作

### 操作一：编写脚本

**执行步骤：**

1. 先用 `jarvis.listCaps()` 或 `jarvis-daemon run-script` 跑一个探针脚本，
   确认目标能力名与参数（不同平台/版本能力清单不同）。
2. 按上述 API 编写脚本：优先用 `jarvis.cap` 做需要显式判断成败之调用，
   用 `jarvis.caps` 做失败即中断之调用。
3. 脚本顶层返回值（非 `undefined`）会被 `run-script` 打印到 stdout，可作结果出口。
4. 用 `node --check <file>` 做基本语法检查（goja 无独立 lint，这是最低保障）。
   **注意事项：**

- `print(...)` / `console.log()` 输出到 stdout；`console.warn` / `console.error` 输出到 stderr。
- 对象/数组经 JSON 序列化输出（与浏览器 console 行为近似）。
- 能力参数为 JS 对象（自动转 `map[string]any`）；传 `undefined`/`null` 时按空参数处理。

### 操作二：运行脚本

**执行步骤：**

1. 用 `jarvis-daemon run-script <file.js>` 运行脚本文件。
2. 需要参数化时用 `--arg key=value`（可重复），脚本内读 `jarvis.args.key`。
3. 脚本顶层返回值非 `undefined` 时打印到 stdout；错误输出到 stderr 并带 JS 堆栈（文件/行号）。
   **示例：**

```bash
# 运行示例脚本
jarvis-daemon run-script examples/system-info.js
# 运行脚本并传参（注入 jarvis.args）
jarvis-daemon run-script examples/list-dir.js --arg path=/tmp
```

**注意事项：**

- 退出码：成功 0；脚本语法错误/运行错误/能力调用失败 非 0。
- 脚本内 `jarvis.args` 由 `--arg key=value` 注入，缺省时为空对象，可安全访问。

### 操作三：调试与验证

**执行步骤：**

1. 语法错误：`run-script` 输出 SyntaxError 并退出码非 0，按文件/行号定位。
2. 运行错误：脚本抛出异常，输出错误信息 + JS 堆栈（文件/行号），退出码非 0。
3. 能力调用失败：`jarvis.cap` 返回 `{success:false, error}`；`jarvis.caps` 抛异常可 try/catch。
4. 写操作后用可观测手段验证结果（读回文件、查进程状态、看命令输出），**禁止**臆断「点了应该就生效」。
   **注意事项：**

- `jarvis.caps` 叶节点调用失败抛的异常信息含能力名与错误，`e.message` 可读。
- 脚本内 `jarvis.args` 仅来自 `--arg`，能力参数来自脚本自身，无网络输入，无 XSS 注入面。

## 检查清单

完成任务后，你必须确认：

- [ ] 脚本为单文件纯 JS，无 `require`/`import`/`export`/ES 模块
- [ ] 延迟用 `jarvis.sleep(ms)`，未用 `setTimeout`/`setInterval`
- [ ] 能力调用前已用 `jarvis.listCaps()` 确认能力名与参数
- [ ] `jarvis.cap` 与 `jarvis.caps` 之成败语义使用正确
- [ ] 已用 `node --check` 检查语法
- [ ] 已用 `run-script` 实跑确认脚本可执行
- [ ] 写操作已用独立手段验证生效，临时文件已清理
- [ ] 脚本未硬编码敏感凭据，未运行来源不明脚本

## 相关资源

- daemon 使用说明：`{{ jarvis_src_dir }}/daemon/docs/js-plugin-usage.md`
- daemon 设计文档：`{{ jarvis_src_dir }}/daemon/docs/js-plugin-design.md`
- 示例脚本：`{{ jarvis_src_dir }}/daemon/examples/system-info.js`、`list-dir.js`
- Windows 桌面 GUI 操作：`{{ rule_file_dir }}/jarvis_daemon_windows.md`
- 浏览器扩展页面脚本：`{{ rule_file_dir }}/browser_ext_script.md`
- 脚本生成通用规范：`{{ rule_file_dir }}/script-generation.md`
