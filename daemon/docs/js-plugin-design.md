# jarvis-daemon JS 插件系统设计文档

> 状态：设计稿（待评审）
> 作者：Jarvis
> 日期：2026-10-02

## 1. 背景与目标

jarvis-daemon（GO 后台服务）目前通过 **capability 能力注册表**（`internal/capability`）对外暴露系统能力，
由网关通过 WS 协议下发指令执行。能力清单涵盖文件系统（fs.read/write/list）、进程、剪贴板、输入、
窗口、服务、系统信息、截图、OCR、浏览器扩展等。

**目标**：在 jarvis-daemon 内实现一个 **JS 运行时插件系统**，把 GO 内置的 capability 能力暴露成 JS 对象，
让用户通过编写 JS 脚本做自动化（类似 shell 脚本，但能力更丰富、语义更友好）。

**脚本管理**：参考浏览器扩展（browser.ext）的管理模式，提供脚本的安装、更新、列出、查询、删除、运行
等管理能力，使脚本成为守护进程可管理的"一等公民"（见 §6）。

**非目标**：

- 不改变现有 capability 能力注册逻辑与 WS 网关调用链路。
- 不做浏览器端沙箱/多租户隔离（脚本以守护进程权限运行，等同 shell 权限，见 §8 安全模型）。

## 2. 技术选型：goja

Go 标准库不提供 JS 解释器，必须引入第三方 JS 引擎。候选对比：

| 引擎                    | 语言     | cgo    | 许可 | 说明                                                 |
| ----------------------- | -------- | ------ | ---- | ---------------------------------------------------- |
| **goja**（dop251/goja） | 纯 Go    | 无     | MIT  | 最活跃的纯 Go ES5.1+ 引擎，支持 async/await、Promise |
| otto                    | 纯 Go    | 无     | MIT  | 较老，维护不活跃，性能一般                           |
| v8go                    | C++ 绑定 | **有** | BSD  | 依赖 V8，性能好但引入 cgo 与庞大二进制               |

**选型结论：goja**。

- 纯 Go 实现、**零 cgo**，与 daemon 现有"纯 syscall + 零 cgo"设计理念一致，交叉编译友好。
- MIT 许可，依赖均为纯 Go 库（regexp2、sourcemap、x/text 等）。
- 支持 ES5.1 及部分 ES6+（async/await、Promise、箭头函数），足以支撑自动化脚本。

**依赖影响**：go.mod 新增 `github.com/dop251/goja` 及其纯 Go 传递依赖，无 cgo、无二进制体积爆炸。

## 3. 整体架构

```text
┌────────────────────────────────────────────────────────────┐
│                     cmd/jarvis-daemon/main.go                │
│    run-script / script <list|status|install|remove|run>      │
│                        │                                     │
│                        ▼                                     │
│   ┌──────────────────────────────────────────────────────┐  │
│   │          internal/jsruntime  (新增包)                  │  │
│   │                                                       │  │
│   │  ┌─────────────────┐   ┌──────────────────────────┐  │  │
│   │  │  Runtime         │   │  CapabilityBridge        │  │  │
│   │  │  (goja 封装)     │   │  (能力 → JS 对象)         │  │  │
│   │  │  - RunScript()   │   │  - jarvis.cap()          │  │  │
│   │  │  - 错误处理       │   │  - jarvis.caps.<nested>  │  │  │
│   │  └─────────────────┘   │  - jarvis.listCaps()      │  │  │
│   │                        └──────────────────────────┘  │  │
│   └──────────────────────────────┬───────────────────────┘  │
│                                  │ 调用                     │
│   ┌──────────────────────────────▼───────────────────────┐  │
│   │      internal/capability.Registry (现有，不改动)       │  │
│   │      Execute(name, params) → Result{Success,Data,Err}│  │
│   └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

- **`internal/jsruntime`**（新增包）：封装 goja 运行时，提供脚本执行与能力桥接。
- **`internal/capability`**（现有包，**不改动**）：能力注册表，作为 JS 能力的后端执行者。
- **`cmd/jarvis-daemon/main.go`**：新增 `run-script` 与 `script` 子命令，装配 Registry → 注入 JS 运行时 → 执行/管理脚本。

## 4. 能力暴露 API 设计

脚本内通过全局 `jarvis` 对象访问能力。提供三种访问形式，满足不同场景。

### 4.1 `jarvis.cap(name, params)` —— 通用调用

按能力名直接调用，返回能力 `Result`（`{success, data, error}`）。

```js
const res = jarvis.cap("linux.system.info");
if (res.success) {
  print("主机名:", res.data.hostname);
} else {
  print("失败:", res.error);
}
```

### 4.2 `jarvis.caps.<域>.<动作>(params)` —— 嵌套命名空间

遍历 Registry 全部能力，把能力名按 `.` 拆成嵌套对象，叶节点为可调用函数。
能力名 `linux.fs.read` → `jarvis.caps.linux.fs.read({path})`。

```js
const files = jarvis.caps.linux.fs.list({ path: "/home" });
print(JSON.stringify(files.data, null, 2));
```

**实现要点**：

- 调用时若 `Result.Success === false`，**抛 JS 异常**（`throw new Error(res.error)`），让脚本可用 try/catch 处理失败；同时提供 `jarvis.cap` 返回对象形式供需要显式判断的场景。
- 参数：JS 对象自动转 `map[string]any`（goja 原生支持 object ↔ Go map 转换）。
- 未注册能力：`jarvis.cap` 返回 `{success:false, error:"unknown capability: ..."}`；嵌套访问不存在的域/动作时返回 `undefined`，调用时报 TypeError。

### 4.3 `jarvis.listCaps()` —— 能力清单

返回当前平台可用能力列表（名称 + 描述 + 参数 schema），便于脚本作者发现能力。

```js
jarvis.listCaps().forEach((c) => print(c.name, "-", c.description));
```

### 4.4 能力自动暴露机制

**Registry 里注册的所有能力都会自动暴露给 JS**，无需为每个能力手写绑定：

- `jarvis.caps` 嵌套对象通过遍历 `Registry.ListForPlatform(capability.Current())` 自动构建，按能力名 `.` 拆分生成嵌套结构。**新增一个能力，JS 里自动就能用**。
- 平台自动过滤：只暴露当前平台适用的能力（含 `PlatformAny`），Linux 上只见 `linux.*` + `any.*`。
- `jarvis.cap(name, params)` 是通用入口，按名字直接查 Registry 并 Execute。

## 5. 脚本运行（run-script）

### 5.1 CLI 子命令 `run-script`

```text
jarvis-daemon run-script <file.js> [--arg key=value ...]
```

- `<file.js>`：脚本文件路径（必填），可以是任意路径的 `.js` 文件。
- `--arg key=value`：可选，把键值对注入脚本全局对象 `jarvis.args`（如 `jarvis.args.path`），供脚本参数化。

**执行流程**：

1. 创建 `capability.NewRegistry()` 并装配当前平台能力（复用现有 `run` 流程的注册逻辑，见 §7 复用点）。
2. 读取脚本文件内容。
3. 创建 `jsruntime.Runtime`，注入 `jarvis` 能力对象。
4. 执行脚本；输出结果或错误。
5. 退出码：成功 0；脚本语法错误/运行错误/能力调用失败 非 0。

### 5.2 输出约定

- 脚本内 `print(...)` / `console.log(...)` 输出到 stdout。
- 脚本顶层返回的 Promise 会被等待（支持 async 脚本）。
- 错误输出到 stderr，并附带 goja 的堆栈信息（文件/行号）便于定位。

## 6. 脚本管理（script.\* 能力 + CLI）

参考浏览器扩展（browser.ext）的管理模式，把脚本作为守护进程可管理的对象。

### 6.1 存储布局

```text
~/.jarvis/scripts/
├── <name>.js              # 脚本本体（单文件）
└── <name>.json            # 可选元数据（manifest：name/version/description/enabled）
```

- 固定目录 `~/.jarvis/scripts/`，与 `~/.jarvis/browser_extension` 同级，遵循既有 `~/.jarvis` 约定。
- 每个脚本一个 `<name>.js` 文件；可选同名 `<name>.json` 存放元数据（版本、描述、启用状态）。
- 脚本名即文件名（不含扩展名），作为脚本的唯一标识。

### 6.2 管理能力（capability 暴露）

脚本管理本身作为 capability 暴露（跨平台，`PlatformAny`），既可供网关下发指令管理脚本，
也可被脚本内 `jarvis.cap("script.list")` 调用（脚本间协作）。

| 能力名           | 作用                                      | 关键参数                                                         |
| ---------------- | ----------------------------------------- | ---------------------------------------------------------------- |
| `script.list`    | 列出已安装脚本（名称/版本/描述/启用状态） | —                                                                |
| `script.status`  | 查询单个脚本状态                          | `name`                                                           |
| `script.install` | 安装/更新脚本（从本地文件路径或内容）     | `name`、`source`（文件路径或脚本内容）、`description`、`enabled` |
| `script.remove`  | 删除脚本                                  | `name`                                                           |
| `script.run`     | 运行已安装脚本（按名字）                  | `name`、`args`（传给 `jarvis.args`）                             |

**install 来源**：

- `source` 为本地文件路径时，读取文件内容安装；
- `source` 为脚本内容字符串时，直接写入；
- 更新时覆盖同名脚本，保留元数据或按参数更新。

**安全校验**（参考 browser.ext 的解压安全策略）：

- 脚本名只允许 `[A-Za-z0-9_-]`，拒绝路径穿越（`../`、绝对路径），防止写出 `~/.jarvis/scripts/` 之外。
- 脚本文件大小设上限（如 1 MiB），防止异常内容撑爆。

### 6.3 CLI 子命令 `script`

```text
jarvis-daemon script list
jarvis-daemon script status <name>
jarvis-daemon script install <name> <source.js> [--desc ...] [--disable]
jarvis-daemon script remove <name>
jarvis-daemon script run <name> [--arg key=value ...]
```

- `script list`：列出已安装脚本。
- `script install <name> <source.js>`：从本地 `.js` 文件安装/更新脚本。
- `script run <name>`：运行已安装脚本（等价于 `run-script ~/.jarvis/scripts/<name>.js`，但按名字解析）。

### 6.4 与浏览器扩展的对应关系

| 浏览器扩展（browser.ext）              | JS 脚本（script.\*）                |
| -------------------------------------- | ----------------------------------- |
| `~/.jarvis/browser_extension` 固定目录 | `~/.jarvis/scripts/` 固定目录       |
| `browser.ext.status`                   | `script.status` / `script.list`     |
| `browser.ext.sync`（从网关下载）       | `script.install`（从本地路径/内容） |
| manifest.json 版本                     | `<name>.json` 元数据版本            |
| 浏览器手动刷新生效                     | 脚本按需运行，无热加载概念          |

## 7. 代码复用点

`main.go` 的 `run` 流程（544 行附近）已包含能力装配逻辑：

```go
registry := capability.NewRegistry()
capability.SetBrowserExtCredentialProvider(...) // 注入网关 Token
capability.SetOcrGatewayLister(...)             // 注入已认证网关列表
```

`run-script` 与 `script run` 需要复用这些装配逻辑（尤其是注入 provider，使 browser.ext / ocr 能力可用）。
**方案**：抽取一个 `newRuntimeRegistry()` 辅助函数（或复用现有装配函数），供 `run`、`run-script`、`script run` 共用，
避免重复造轮子。具体抽取方式在实现时按最小改动原则确定。

## 8. 安全模型

- **权限边界**：JS 脚本以守护进程权限运行，能调用全部已注册能力（等同 shell 脚本权限）。
  这是设计预期——插件系统定位为"本机自动化工具"，不做沙箱隔离。
- **能力白名单（可选增强）**：后续可增加 `--allow` / `--deny` 参数或配置文件，限制脚本可调用的能力子集，
  降低误操作风险。首版不实现，文档中说明。
- **脚本名校验**：只允许 `[A-Za-z0-9_-]`，拒绝路径穿越，防止脚本写入越界。
- **注入面**：`jarvis.args` 仅来自 CLI `--arg` 或 `script.run` 的 `args`，能力参数来自脚本自身，无网络输入，无 XSS 面。
- **文档提示**：明确告知用户脚本权限等同守护进程，勿运行来源不明的脚本。

## 9. 目录结构（新增部分）

```text
daemon/
├── cmd/jarvis-daemon/
│   └── main.go                  # 新增 run-script 与 script 子命令
├── internal/
│   └── jsruntime/               # 新增包
│       ├── runtime.go           # goja 封装：创建运行时、RunScript、错误处理
│       ├── bridge.go            # 能力桥接：jarvis.cap / jarvis.caps / jarvis.listCaps
│       ├── runtime_test.go      # 单测
│       └── bridge_test.go       # 能力桥接单测（fake 能力）
├── internal/
│   └── scriptmgr/               # 新增包：脚本存储与管理（list/status/install/remove）
│       ├── manager.go           # 脚本目录解析、CRUD、安全校验
│       ├── manager_test.go      # 单测
├── examples/
│   ├── system-info.js           # 示例：读取系统信息
│   └── list-dir.js              # 示例：列出目录
└── docs/
    └── js-plugin-design.md      # 本文档
```

## 10. 实施计划

| 步骤 | 内容                                                          | 验证                            |
| ---- | ------------------------------------------------------------- | ------------------------------- |
| 1    | 引入 goja 依赖，实现 `internal/jsruntime` 运行时封装          | 单测执行 JS 表达式/函数/Promise |
| 2    | 实现能力桥接（jarvis.cap / jarvis.caps / jarvis.listCaps）    | 单测用 fake 能力验证调用与错误  |
| 3    | 实现 `scriptmgr` 脚本存储与管理（list/status/install/remove） | 单测覆盖 CRUD 与安全校验        |
| 4    | 实现 `run-script` 与 `script` 子命令 + 装配复用               | 实际执行示例脚本、管理脚本      |
| 5    | 编写示例脚本与使用文档                                        | 示例脚本端到端跑通              |
| 6    | 整体验证（build + test + 示例）                               | 全绿、无回归                    |

## 11. 验证方案

- **单元测试**：
  - `internal/jsruntime`：JS 基础执行、async/await、能力调用成功/失败、未注册能力、参数传递（string/number/bool/嵌套对象）。
  - `internal/scriptmgr`：脚本 CRUD、脚本名校验（路径穿越拒绝）、大小上限、元数据读写。
- **端到端**：`go run ./cmd/jarvis-daemon script install demo examples/system-info.js` → `script list` → `script run demo` 实际调用能力并输出结果。
- **回归**：`go build ./...` + `go test ./...` 全绿，现有 `run`/`status` 等子命令不受影响。
- **依赖检查**：`go mod tidy` 后 go.mod 仅新增 goja 及其纯 Go 传递依赖，无 cgo。
