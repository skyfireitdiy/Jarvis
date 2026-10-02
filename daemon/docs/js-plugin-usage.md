# Jarvis JS 插件系统使用说明

Jarvis daemon 内置一个 JS 运行时（基于 [goja](https://github.com/dop251/goja)，纯 Go、零 cgo），
你可以编写 JS 脚本调用 daemon 的能力（capability）做本机自动化，例如读取系统信息、操作文件、
执行命令、管理进程等。

## 1. 快速开始

```bash
# 运行示例脚本
jarvis-daemon run-script examples/system-info.js

# 运行脚本并传参（注入 jarvis.args）
jarvis-daemon run-script examples/list-dir.js --arg path=/tmp
```

脚本内通过全局对象 `jarvis` 调用能力，`print()` / `console.log()` 输出到 stdout，
`console.error()` 输出到 stderr，脚本顶层返回值会打印到 stdout。

## 2. jarvis API

脚本内可用的全局对象：

| API                               | 说明                                                              |
| --------------------------------- | ----------------------------------------------------------------- |
| `jarvis.cap(name, params)`        | 通用调用入口，按能力名调用，返回 `{success, data, error}`         |
| `jarvis.caps.<域>.<动作>(params)` | 嵌套命名空间调用，成功返回 `data`，失败抛 JS 异常（可 try/catch） |
| `jarvis.listCaps()`               | 列出当前平台所有可用能力（名称/描述/参数/平台）                   |
| `jarvis.sleep(ms)`                | 同步延迟（毫秒），替代 `setTimeout`（goja 无宏任务事件循环）      |
| `jarvis.args`                     | 脚本参数对象（由 `--arg key=value` 注入）                         |

### 2.1 jarvis.cap 通用调用

```js
const res = jarvis.cap("linux.system.info", {});
if (res.success) {
  print("主机名:", res.data.hostname);
} else {
  console.error("失败:", res.error);
}
```

`jarvis.cap` 总是返回 `{success, data, error}`，不会抛异常，适合需要显式判断成败的场景。

### 2.2 jarvis.caps 嵌套命名空间

```js
// 等价于 jarvis.cap("linux.fs.list", {path: "/tmp"})，但失败抛异常
try {
  const files = jarvis.caps.linux.fs.list({ path: "/tmp" });
  print("共", files.count, "个条目");
} catch (e) {
  console.error("调用失败:", e.message);
}
```

能力名按 `.` 拆成嵌套对象：`linux.fs.read` → `jarvis.caps.linux.fs.read`。

### 2.3 查看能力清单

```js
const caps = jarvis.listCaps();
caps.forEach((c) => print(c.name, "-", c.description));
```

### 2.4 脚本参数

```bash
jarvis-daemon run-script my-script.js --arg name=world --arg count=3
```

```js
print("hello", jarvis.args.name); // hello world
```

## 3. 示例脚本

`examples/` 目录：

- `system-info.js` — 读取系统信息（展示 `jarvis.cap` 与 `jarvis.caps` 两种调用方式）
- `list-dir.js` — 列出目录内容（展示 `jarvis.args` 参数注入与遍历返回数组）

## 4. 能力清单

可用能力随平台而异（Linux / Windows），可用 `jarvis.listCaps()` 或
`jarvis-daemon run-script` 执行下面的脚本查看：

```js
jarvis.listCaps().forEach((c) => print(c.name));
```

常见能力域（以 Linux 为例）：

- `linux.system.info` — 系统信息
- `linux.fs.read` / `linux.fs.write` / `linux.fs.list` — 文件读写与目录列举
- `linux.script.exec` — 执行 shell 命令
- `linux.process.list` / `linux.process.kill` — 进程管理
- `linux.clipboard` / `linux.input` / `linux.window` — 剪贴板 / 输入 / 窗口
- `linux.screenshot` / `ocr.recognize` — 截图与 OCR
- `browser.ext.*` — 浏览器扩展管理
- `fs.transfer.push` / `fs.transfer.pull` — 跨机文件直传

## 5. 错误处理

- **语法错误**：脚本无法编译，`run-script` 输出 SyntaxError 并退出码非 0。
- **运行错误**：脚本抛出异常，输出错误信息 + JS 堆栈（文件/行号），退出码非 0。
- **能力调用失败**：`jarvis.cap` 返回 `{success:false, error}`；`jarvis.caps` 抛异常可 try/catch。

## 6. 安全注意事项

> ⚠️ **脚本权限等同守护进程权限**。

JS 脚本以 daemon 进程的权限运行，能调用**全部**已注册能力（等同 shell 脚本权限）。
本插件系统定位为"本机自动化工具"，首版**不做沙箱隔离**。请勿运行来源不明的脚本，
脚本中不要硬编码敏感凭据。

`jarvis.args` 仅来自 CLI `--arg` 或脚本管理能力的 `args`，能力参数来自脚本自身，
无网络输入，无 XSS 注入面。

## 7. 限制

- goja 核心无 `setTimeout` / `setInterval` 宏任务事件循环，延迟请用 `jarvis.sleep(ms)`。
- 脚本内 `require` / `import` 不可用（无模块加载器），单文件脚本。
- 不支持 ES 模块（`import`/`export`），使用普通 JS 语法。
