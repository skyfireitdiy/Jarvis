# Node 模式详细设计拆分规划

## 1. 目标

本文档用于将 `node_mode_spec.md` 进一步拆分为可指导编码的详细设计结构，明确：

1. node 模式的功能点边界
2. 每个功能点的设计落点
3. 推荐的详细设计文档组织方式
4. 每个功能点对应的代码模块范围

本文档本身不包含业务代码实现，仅用于指导下一步详细设计文档编写。

## 2. 设计拆分原则

### 2.1 拆分原则

- 每个功能点必须能映射到明确的代码模块
- 每个功能点必须有清晰的输入、输出、状态变化与异常处理
- 每个功能点必须说明兼容性要求
- 每个功能点必须可独立验证
- 每个功能点的设计粒度应达到“开发者可据此直接开始编码”的程度

### 2.2 文档组织原则

推荐采用：

- **一个总览文档**：说明整体设计、模块关系、公共数据结构、统一错误码与测试策略
- **多个功能点子文档**：每个功能点一个独立设计文档，聚焦单一主题

原因：

- 当前 node 模式涉及 CLI、认证、状态、代理、客户端兼容等多个高耦合但职责不同的模块
- 单一文档会过大，不利于编码时定位
- 子文档更适合后续逐项实现与验收

## 3. 功能点清单

### F1. CLI 参数与配置解析

**功能目标**：
为 `jarvis-web-gateway` 与 `jarvis-service` 增加 node 模式参数和配置透传能力。

**核心问题**：

- `--node-mode` 只允许 `master` / `child`
- `child` 模式必须校验依赖参数
- `jarvis-service` 需要将 node 配置透传给 `jwg`

**主要代码落点**：

- `src/jarvis/jarvis_web_gateway/cli.py`
- `src/jarvis/jarvis_service/cli.py`

**输出结果**：

- 运行时 node 配置对象
- 启动参数校验结果

---

### F2. 运行模式归一化与启动流程

**功能目标**：
统一 `master` 模式下的单节点/多节点语义，明确启动时组件初始化策略。

**核心问题**：

- `master` 是默认模式
- 无子节点时仍保持当前单节点行为
- `child` 模式下需额外启动主节点连接流程

**主要代码落点**：

- `src/jarvis/jarvis_web_gateway/app.py`

**输出结果**：

- 运行时模式状态
- 各模式组件初始化清单

---

### F3. 子节点到主节点的连接与鉴权

**功能目标**：
建立子节点到主节点的长期 WebSocket，并完成 node 级认证。

**核心问题**：

- 新增节点专用 WS 通道
- 子节点首帧必须认证
- 主节点必须校验 `node_id + node_secret`
- 节点冲突、超时、非法接入的处理策略

**主要代码落点**：

- `src/jarvis/jarvis_web_gateway/app.py`
- 建议新增节点连接管理模块（位于 `src/jarvis/jarvis_web_gateway/`）

**输出结果**：

- 节点连接会话
- 鉴权结果

---

### F4. token 同步机制

**功能目标**：
子节点接入成功后，从主节点获取 token 并更新本地 `JARVIS_AUTH_TOKEN`。

**核心问题**：

- token 更新时机
- 更新失败时节点可用性
- 子节点后续创建 Agent 必须继承新 token

**主要代码落点**：

- `src/jarvis/jarvis_web_gateway/app.py`
- `src/jarvis/jarvis_web_gateway/token_manager.py`
- `src/jarvis/jarvis_web_gateway/agent_manager.py`

**输出结果**：

- 同步后的 token 状态
- token 更新失败错误

---

### F5. 节点注册表与心跳管理

**功能目标**：
主节点维护在线子节点状态，并支持心跳、断连、重连。

**核心问题**：

- `NodeInfo` 模型
- 节点在线/离线/降级状态
- 心跳超时规则
- 重连后的状态恢复

**主要代码落点**：

- `src/jarvis/jarvis_web_gateway/app.py`
- 建议新增节点注册表/心跳管理模块

**输出结果**：

- `node_registry`
- 节点状态变化事件

---

### F6. AgentInfo 扩展与路由表设计

**功能目标**：
为 Agent 增加 `node_id` 归属，并让主节点维护统一的 Agent 路由表。

**核心问题**：

- `AgentInfo` 扩展 `node_id`
- 本地 Agent 与远端 Agent 的统一表示
- `agent_id -> node_id` 映射维护

**主要代码落点**：

- `src/jarvis/jarvis_web_gateway/agent_manager.py`
- `src/jarvis/jarvis_web_gateway/app.py`

**输出结果**：

- 扩展后的 Agent 元数据
- Agent 路由注册表

---

### F7. 创建 Agent 的节点路由

**功能目标**：
让 `/api/agents` 支持 `node_id`，并根据目标节点决定本地创建或远端创建。

**核心问题**：

- 请求参数扩展
- 默认节点策略
- 远端创建协议
- 失败回传与错误透传

**主要代码落点**：

- `src/jarvis/jarvis_web_gateway/app.py`
- `src/jarvis/jarvis_web_gateway/agent_manager.py`
- 建议新增节点请求转发模块

**输出结果**：

- 创建结果包含 `node_id`
- Agent 路由注册完成

---

### F8. 远端 HTTP 转发

**功能目标**：
主节点可通过节点通道访问子节点上的 Agent HTTP 接口。

**核心问题**：

- 复用现有 `/api/agent/{agent_id}/{path}` 路径
- 本地代理与远端代理分流
- 请求/响应封装结构
- 超时与错误转换

**主要代码落点**：

- `src/jarvis/jarvis_web_gateway/agent_proxy_manager.py`
- `src/jarvis/jarvis_web_gateway/app.py`
- 建议新增远端 HTTP 转发模块

**输出结果**：

- 统一 HTTP 代理结果
- 远端转发错误模型

---

### F9. 远端 WebSocket 转发

**功能目标**：
主节点可通过节点通道透明中继子节点 Agent 的 WebSocket 通信。

**核心问题**：

- `channel_id` 生命周期
- 客户端、主节点、子节点、本地 Agent 四方消息转发
- 连接关闭、异常关闭、缓存与清理

**主要代码落点**：

- `src/jarvis/jarvis_web_gateway/agent_proxy_manager.py`
- `src/jarvis/jarvis_web_gateway/app.py`
- 建议新增远端 WS 通道管理模块

**输出结果**：

- 可复用的 WS 中继协议
- 通道状态表

---

### F10. 客户端兼容与 API 扩展

**功能目标**：
在不破坏现有客户端默认行为的前提下，支持节点选择与节点信息展示。

**核心问题**：

- `/api/agents` 返回 `node_id`
- 客户端创建 Agent 时可选 `node_id`
- 未升级客户端仍可在主节点本地创建 Agent

**主要代码落点**：

- `src/jarvis/jarvis_vscode_extension/src/extension.ts`
- 可能的前端调用层

**输出结果**：

- API 兼容矩阵
- 客户端字段扩展方案

---

### F11. 错误码、状态机与日志

**功能目标**：
统一 node 模式中的错误码、节点状态、转发状态与日志要求。

**核心问题**：

- `NODE_AUTH_FAILED`、`NODE_OFFLINE`、`FORWARD_TIMEOUT` 等错误码
- 节点状态机
- 转发请求生命周期状态
- 日志中脱敏 token

**主要代码落点**：

- `src/jarvis/jarvis_web_gateway/app.py`
- 新增节点/转发管理模块

**输出结果**：

- 统一错误码表
- 状态转换表

---

### F12. 测试与验证设计

**功能目标**：
为每个功能点定义可执行的测试与验收方式。

**核心问题**：

- 单元测试覆盖哪些状态机与路由逻辑
- 集成测试如何模拟 master/child
- 静态检查与最小可验证路径

**主要代码落点**：

- `tests/` 下相关模块测试目录

**输出结果**：

- 测试矩阵
- 验收用例清单

## 4. 推荐文档结构

推荐在 `.jarvis/spec/` 下采用以下结构：

```text
.jarvis/spec/
├── node_mode_spec.md
├── node_mode_design_plan.md
├── node_mode_detailed_design.md
└── node_mode_features/
    ├── 01_cli_and_config.md
    ├── 02_runtime_mode_and_bootstrap.md
    ├── 03_node_connection_and_auth.md
    ├── 04_token_sync.md
    ├── 05_node_registry_and_heartbeat.md
    ├── 06_agent_metadata_and_routing.md
    ├── 07_agent_creation_routing.md
    ├── 08_remote_http_proxy.md
    ├── 09_remote_ws_proxy.md
    ├── 10_client_compatibility.md
    ├── 11_error_codes_and_state_machine.md
    └── 12_test_and_validation.md
```

## 5. 文档职责划分

### 5.1 总文档：`node_mode_detailed_design.md`

职责：

- 汇总整体架构
- 说明公共数据结构
- 说明模块依赖关系
- 汇总总流程图与实现顺序
- 为各子文档提供导航

### 5.2 子文档职责

| 文件名 | 功能点 | 主要目标 |
| --- | --- | --- |
| `01_cli_and_config.md` | F1 | 明确 CLI 参数、配置源、参数校验与代码入口 |
| `02_runtime_mode_and_bootstrap.md` | F2 | 明确 master/child 模式初始化流程与组件装配 |
| `03_node_connection_and_auth.md` | F3 | 明确节点 WS 接入、认证时序、冲突处理 |
| `04_token_sync.md` | F4 | 明确 token 下发、更新与失败处理 |
| `05_node_registry_and_heartbeat.md` | F5 | 明确节点状态模型、心跳、断连、重连 |
| `06_agent_metadata_and_routing.md` | F6 | 明确 AgentInfo 扩展与路由表维护 |
| `07_agent_creation_routing.md` | F7 | 明确创建 Agent 的本地/远端分流 |
| `08_remote_http_proxy.md` | F8 | 明确远端 HTTP 请求封装、回传与异常处理 |
| `09_remote_ws_proxy.md` | F9 | 明确远端 WS 通道生命周期与转发协议 |
| `10_client_compatibility.md` | F10 | 明确 API 兼容与客户端字段扩展 |
| `11_error_codes_and_state_machine.md` | F11 | 明确错误码、状态图、日志要求 |
| `12_test_and_validation.md` | F12 | 明确测试矩阵、验收步骤与未验证项定义 |

## 6. 后续编写要求

下一步详细设计文档编写必须满足以下要求：

1. 每个功能点文档必须包含：
   - 功能目标
   - 影响模块
   - 输入/输出
   - 数据结构
   - 详细流程
   - 状态变化
   - 异常处理
   - 兼容性要求
   - 编码落点建议
   - 测试建议

2. 每个功能点文档必须尽量标注到具体代码文件，例如：
   - `src/jarvis/jarvis_web_gateway/cli.py`
   - `src/jarvis/jarvis_web_gateway/app.py`
   - `src/jarvis/jarvis_web_gateway/agent_manager.py`
   - `src/jarvis/jarvis_web_gateway/agent_proxy_manager.py`
   - `src/jarvis/jarvis_service/cli.py`
   - `src/jarvis/jarvis_vscode_extension/src/extension.ts`

3. 设计必须达到以下程度：
   - 开发者可直接据此确定修改文件
   - 开发者可直接据此确定新增类、函数或状态模型
   - 开发者可直接据此编写对应测试

## 7. 结论

推荐继续采用“1 个总设计文档 + 12 个功能点子文档”的方式推进 node 模式详细设计。这样可以保证：

- 每个功能点边界清晰
- 每个设计文档足够细致，可指导编码
- 后续实现与验证可以按功能点逐项推进
