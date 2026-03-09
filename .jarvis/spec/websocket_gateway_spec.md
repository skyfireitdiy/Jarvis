# WebSocket Gateway Spec

## 1. 功能概述

### 1.1 目标

为 Jarvis 增加一个基于 WebSocket 的交互网关，使外部客户端可以通过长连接与应用程序进行双向交互，包括：

- 接收系统输出事件
- 提交用户输入
- 观察工具执行结果
- 在支持的平台上与脚本执行过程进行实时交互

### 1.2 背景

当前 Jarvis 的输入输出机制具有以下现状：

- `src/jarvis/jarvis_utils/output.py`
  - 已具备 `OutputEvent`、`OutputSink`、`emit_output()`、`PrettyOutput.add_sink()` 等输出扩展能力
- `src/jarvis/jarvis_utils/input.py`
  - 主要围绕本地终端与 `prompt_toolkit` 组织，缺少统一输入抽象
- `src/jarvis/jarvis_tools/execute_script.py`
  - 当前不同平台存在不同执行路径
  - Windows 已有交互式 PTY 雏形
  - Unix 交互模式当前不利于程序化 stdin/stdout 实时桥接

### 1.3 目标价值

- 保持现有 CLI 使用方式不变
- 为 Web UI / 桌面端 / 远程控制端提供统一后端能力
- 为后续多前端演进提供标准协议基础
- 为工具流式执行与会话化交互建立统一模型

## 2. 设计范围

### 2.1 范围内

本 Spec 覆盖以下内容：

1. WebSocket 网关连接与会话模型
2. 输出事件向 WebSocket 客户端推送
3. WebSocket 输入提交到 Jarvis 输入流程
4. `execute_script` 的标准输入输出重定向设计
5. 基于虚拟 TTY 的交互执行能力设计
6. CLI 与 WebSocket 双模式兼容策略
7. 消息协议、异常处理、能力分级
8. 安全、测试与验收标准

### 2.2 范围外

本 Spec 不包含以下内容：

1. Web 前端页面实现
2. 浏览器端终端 UI 具体实现
3. 完整认证中心/用户系统
4. 所有 CLI 快捷键在 WebSocket 首版的等价迁移
5. 所有工具全面流式化改造
6. `prompt_toolkit`/fzf/剪贴板的远端完整重建

## 3. 当前系统现状

### 3.1 输出现状

当前输出系统已具备事件化扩展能力：

- `OutputEvent`：统一输出事件结构
- `OutputSink`：输出消费抽象
- `ConsoleOutputSink`：默认控制台输出实现
- `emit_output()`：广播到所有 sink
- `PrettyOutput.add_sink()`：支持注册新 sink

**结论**：输出侧适合以“新增 WebSocket sink”的方式增量扩展。

### 3.2 输入现状

当前输入系统特点：

- 主要入口为 `get_single_line_input()`、`get_multiline_input()`
- 强依赖本地终端、`prompt_toolkit`、快捷键、fzf、剪贴板
- 非交互模式直接返回自动响应
- 尚不存在统一的输入提供者抽象

**结论**：输入侧不能直接硬接 WebSocket，需要引入输入抽象层。

### 3.3 脚本执行现状

`execute_script.py` 当前平台行为不一致：

- Windows 非交互：`subprocess.PIPE`，可捕获输出，不可交互
- Windows 交互：`winpty.PtyProcess`，可读取输出并转发 stdin
- Unix 非交互：通过 `script` 录制输出文件后解析
- Unix 交互：`os.system()` 继承当前终端，难以程序化桥接

**结论**：`execute_script` 需要抽象为双执行后端，并引入虚拟 TTY 执行模式。

## 4. 功能需求

### 4.1 输出网关需求

1. 系统输出事件应可发送给 WebSocket 客户端
2. 输出事件推送不得破坏现有 CLI 输出
3. 输出事件应保留结构化字段：
   - 文本
   - 类型
   - 时间戳信息
   - 上下文信息
4. 单个 WebSocket sink 失败不得影响控制台输出

### 4.2 输入网关需求

1. WebSocket 客户端应能提交普通用户输入
2. 输入应按会话隔离
3. 默认 CLI 输入路径必须保持不变
4. 非交互模式下仍沿用当前自动响应逻辑
5. 当 WebSocket 输入不可用时，应有明确错误或降级行为

### 4.3 脚本执行网关需求

1. `execute_script` 应支持保留现有结果模式
2. 在 WebSocket 场景下应支持流式输出推送
3. 在支持的平台上应支持脚本 stdin 透传
4. 应区分“结果模式”和“终端流模式”
5. 应明确平台能力差异与降级规则

### 4.4 会话管理需求

1. 每个 WebSocket 连接应绑定唯一会话
2. 输出事件必须可以路由到对应会话
3. 输入必须可以定位到对应会话或执行会话
4. 脚本执行过程必须支持 `execution_id` 级别隔离

## 5. 非功能需求

### 5.1 兼容性

- 未启用 WebSocket 时，系统行为应与当前一致
- 现有 CLI 用户无需修改使用方式
- 现有 `PrettyOutput` 调用代码无需修改
- 现有 `execute_script` 调用接口语义尽量保持兼容

### 5.2 性能

- 普通输出事件推送延迟目标 < 200ms
- 应支持多个 WebSocket 会话并发
- 应支持长文本与持续输出流的稳定推送

### 5.3 稳定性

- 单连接异常不得影响其他连接
- 单 sink 故障不得中断主输出流程
- 会话断开后应释放相关资源
- 脚本执行超时应及时终止并反馈

### 5.4 安全性

- WebSocket 连接应具备最小必要的鉴权能力
- 远端输入应受会话和权限约束
- 脚本交互能力应可被限制或关闭
- 应记录关键操作日志

### 5.5 可扩展性

- 输出后端可继续扩展
- 输入提供者可扩展为 CLI / WebSocket / API 等
- 脚本执行后端可扩展为更多平台实现

## 6. 核心设计约束

### 6.1 必须遵守的兼容约束

1. `output.py` 必须基于新增 `OutputSink` 扩展，不得破坏现有 Console sink
2. `input.py` 必须通过新增输入抽象实现扩展，不得直接破坏 `prompt_toolkit` 主路径
3. `execute_script.py` 必须保留当前兼容结果模式
4. WebSocket 能力必须可关闭
5. 功能关闭时系统行为应回退到当前状态

### 6.2 平台约束

- Windows：优先支持虚拟 TTY 交互流
- Unix/Linux：首版允许结果模式优先，交互流能力可条件支持
- macOS：视 Unix 路径实现兼容

### 6.3 协议约束

- WebSocket 消息格式统一采用 JSON
- 所有消息必须包含 `message_type`
- 需要会话级标识 `session_id`
- 脚本流式消息需包含 `execution_id`

## 7. 架构与模块边界

### 7.1 输出模块

新增：

- `WebSocketOutputSink`

职责：

- 订阅 `OutputEvent`
- 转换为 WebSocket 消息
- 推送到对应会话

### 7.2 输入模块

新增抽象：

- `InputProvider`
- `CliInputProvider`
- `WebSocketInputProvider`

职责：

- 统一输入读取接口
- CLI 模式走现有终端流程
- WebSocket 模式走远端消息队列

### 7.3 网关模块

新增：

- `ConnectionManager`
- `SessionRegistry`
- `MessageProtocolHandler`

职责：

- 管理连接
- 路由消息
- 管理会话状态
- 处理断连与清理

### 7.4 脚本执行模块

新增抽象：

- `ScriptExecutionBackend`
- `CapturedExecutionBackend`
- `VirtualTTYExecutionBackend`

职责：

- 统一执行模型
- 区分结果模式与终端流模式
- 提供交互式 stdin/stdout 桥接能力

## 8. 接口定义

### 8.1 WebSocket 连接接口

#### 连接路径

```text
/ws/gateway
```

#### 连接参数

| 参数名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| client_id | string | 否 | 客户端标识 |
| session_token | string | 否 | 鉴权令牌 |
| mode | string | 否 | `observe` / `interactive` |

#### 服务端返回

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| session_id | string | 服务端会话 ID |
| capabilities | object | 能力描述 |
| status | string | 连接状态 |

### 8.2 客户端 -> 服务端消息

#### 普通用户输入

```json
{
  "message_type": "user_input",
  "session_id": "sess_001",
  "payload": "请继续执行"
}
```

#### 脚本输入

```json
{
  "message_type": "script_input",
  "session_id": "sess_001",
  "execution_id": "exec_001",
  "payload": "y\n"
}
```

#### 心跳

```json
{
  "message_type": "ping",
  "session_id": "sess_001",
  "timestamp": "2026-03-09T12:00:00Z"
}
```

### 8.3 服务端 -> 客户端消息

#### 输出事件

```json
{
  "message_type": "output_event",
  "session_id": "sess_001",
  "payload": {
    "output_type": "INFO",
    "text": "任务开始",
    "timestamp": true,
    "section": null,
    "context": {}
  }
}
```

#### 脚本输出事件

```json
{
  "message_type": "script_output",
  "session_id": "sess_001",
  "execution_id": "exec_001",
  "payload": {
    "stream_type": "terminal_output",
    "chunk": "Hello\\n",
    "sequence": 1,
    "completed": false
  }
}
```

#### 错误事件

```json
{
  "message_type": "error",
  "session_id": "sess_001",
  "payload": {
    "code": "EXEC_TIMEOUT",
    "message": "脚本执行超时"
  }
}
```

#### 执行结束事件

```json
{
  "message_type": "script_exit",
  "session_id": "sess_001",
  "execution_id": "exec_001",
  "payload": {
    "success": true,
    "exit_code": 0
  }
}
```

## 9. 数据模型

### 9.1 GatewaySession

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| session_id | string | 会话唯一标识 |
| client_id | string | 客户端标识 |
| mode | string | `observe` / `interactive` |
| status | string | `connected` / `closed` |
| capabilities | object | 当前会话能力声明 |

### 9.2 InputRequest

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| request_id | string | 输入请求 ID |
| session_id | string | 会话 ID |
| prompt_text | string | 提示文本 |
| input_type | string | `single_line` / `multiline` / `script_stdin` |
| timeout_seconds | int | 超时时间 |

### 9.3 ToolStreamEvent

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| execution_id | string | 脚本执行 ID |
| session_id | string | 会话 ID |
| stream_type | string | `terminal_output` / `result` / `error` |
| chunk | string | 输出片段 |
| sequence | int | 顺序号 |
| completed | bool | 是否结束 |

## 10. 能力分级

### 10.1 能力级别定义

#### Level 1：结果模式
- 适用于现有兼容执行
- 保留 `stdout/stderr` 结果语义
- 不要求实时交互

#### Level 2：流式输出模式
- 输出按片段实时推送
- 可用于 WebSocket 实时展示
- 仍可能不支持 stdin 透传

#### Level 3：终端流交互模式
- 基于虚拟 TTY
- 支持实时输出
- 支持交互式 stdin 透传
- 输出按终端流语义处理

### 10.2 平台能力矩阵

| 能力项 | CLI | WebSocket | Windows | Unix/Linux |
| --- | --- | --- | --- | --- |
| 普通输出事件 | 支持 | 支持 | 支持 | 支持 |
| 普通输入 | 支持 | 支持 | 支持 | 支持 |
| 结果模式脚本执行 | 支持 | 支持 | 支持 | 支持 |
| 流式输出 | 支持 | 条件支持 | 优先支持 | 条件支持 |
| 脚本 stdin 透传 | 支持 | 条件支持 | 优先支持 | 首版可降级 |
| 完整终端语义 | 支持 | 非首版目标 | 条件支持 | 条件支持 |

## 11. 异常处理

### 11.1 异常类型

| 异常代码 | 描述 |
| --- | --- |
| WS_CONN_CLOSED | WebSocket 连接已关闭 |
| WS_PUBLISH_FAILED | WebSocket 推送失败 |
| INPUT_TIMEOUT | 输入超时 |
| INPUT_DISCONNECTED | 输入连接断开 |
| EXEC_TIMEOUT | 脚本执行超时 |
| EXEC_LAUNCH_FAILED | 执行启动失败 |
| EXEC_CAPABILITY_UNSUPPORTED | 平台能力不支持 |
| SESSION_NOT_FOUND | 会话不存在 |

### 11.2 处理原则

1. 不让单会话异常影响全局
2. 不让单 sink 异常影响 CLI 输出
3. 对不支持能力返回明确错误码
4. 脚本执行异常必须有统一回传
5. 连接断开时必须清理会话资源

## 12. 兼容性策略

### 12.1 output.py 兼容策略

- 基于 `OutputSink` 新增 WebSocket sink
- 保留 `ConsoleOutputSink`
- 不改动 `PrettyOutput` 现有调用方式
- 输出事件模型优先复用 `OutputEvent`

### 12.2 input.py 兼容策略

- 新增输入抽象，不破坏 CLI 默认路径
- CLI 继续使用 `prompt_toolkit`
- 非交互模式保持现状
- WebSocket 模式只新增远端输入来源，不要求首版覆盖全部本地快捷键行为

### 12.3 execute_script.py 兼容策略

- 保留当前标准捕获结果模式
- 新增虚拟 TTY 流式执行模式
- 上层调用尽量保持兼容
- WebSocket 场景优先启用流式/TTY 模式
- 不支持时降级为结果模式或返回能力不支持

## 13. 安全要求

1. WebSocket 连接应支持会话鉴权
2. 应区分观察权限与交互权限
3. 脚本输入透传应受会话授权控制
4. 应记录关键安全事件：
   - 连接建立
   - 连接断开
   - 输入提交
   - 执行启动
   - 执行失败
5. 建议部署使用 WSS

## 14. 验收标准

### 14.1 输出网关验收

- **AC-OUT-001**：启用 WebSocket 网关后，CLI 输出仍正常显示
- **AC-OUT-002**：同一输出事件可被 WebSocket 客户端接收
- **AC-OUT-003**：单个 WebSocket sink 失败不影响控制台输出
- **AC-OUT-004**：输出事件包含必要结构化字段

### 14.2 输入网关验收

- **AC-IN-001**：未启用 WebSocket 时，CLI 输入行为与当前一致
- **AC-IN-002**：启用 WebSocket 会话后，远端输入可被系统消费
- **AC-IN-003**：非交互模式行为保持不变
- **AC-IN-004**：远端输入断开或超时有明确错误反馈

### 14.3 脚本执行验收

- **AC-EXE-001**：结果模式下，`execute_script` 保持现有结果语义
- **AC-EXE-002**：流式模式下，脚本输出可实时推送
- **AC-EXE-003**：在支持的平台上，脚本输入可透传
- **AC-EXE-004**：不支持交互流时可降级或明确报错
- **AC-EXE-005**：脚本超时、异常退出时，客户端收到一致错误语义

### 14.4 兼容性验收

- **AC-COMP-001**：现有 CLI 用户无需改变使用方式
- **AC-COMP-002**：现有 `PrettyOutput` 调用代码无需修改
- **AC-COMP-003**：现有 `input.py` 本地交互路径保持可用
- **AC-COMP-004**：关闭 WebSocket 功能时，行为与现状一致

### 14.5 稳定性与安全验收

- **AC-NFR-001**：不同会话之间输入输出不串流
- **AC-NFR-002**：连接断开后相关资源被释放
- **AC-NFR-003**：消息发送失败不导致主流程崩溃
- **AC-NFR-004**：支持最小必要的会话鉴权
- **AC-NFR-005**：关键交互行为可审计

## 15. 风险与限制

1. Unix 交互式 PTY 能力首版可能不完整
2. PTY 模式下 stdout/stderr 可能无法严格区分
3. 全屏类 TUI 程序不保证首版完美支持
4. 浏览器端若不具备终端渲染能力，展示效果会受限
5. 输入抽象改造需谨慎，避免影响现有 CLI

## 16. 后续实现约束

1. 实现前必须基于本 Spec 进行评审
2. 实现必须优先保证兼容性
3. 优先顺序建议为：
   - 输出 sink
   - 输入抽象
   - WebSocket 会话管理
   - `execute_script` 双后端
4. 每个阶段完成后都要回到本 Spec 验收标准进行验证

## 17. 建议的实现阶段

### 阶段 1
- 输出 WebSocket sink
- WebSocket 基础连接与会话管理

### 阶段 2
- 输入抽象层
- WebSocket 输入消费

### 阶段 3
- `execute_script` 双后端抽象
- 虚拟 TTY 模式接入

### 阶段 4
- 兼容性回归
- 平台差异验证
- 性能与稳定性测试
