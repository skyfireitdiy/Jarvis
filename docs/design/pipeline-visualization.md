# 流水线 DAG 可视化 + 运行时进度标记 设计方案

> 状态：方案待管理员确认后实现
> 日期：2026-10-08
> 回退点：`513f7167115c6bdb85137fb7c42a15f0d0a15899`
> 关联：`docs/design/ai-dark-factory-orchestration-engine.md`（DAG 编排引擎）、`src/jarvis/jarvis_tools/pipeline_runner.py`

## 0. 管理员决策（本方案输入）

| 编号 | 决策 | 含义 |
| --- | --- | --- |
| D1 | **方案乙** | 前端自绘 SVG（不走 mermaid/d3-graphviz），可控性/美观度最高 |
| D2 | **用绚的** | 视觉要炫：发光节点、流动连线、渐变、动效 |
| D3 | **全链路实时** | 后端执行状态实时推送前端，非一次性快照 |
| 附加 | 多流程区分 | 前端可能同时编排多个流程，必须能区分 |
| 附加 | 活动栏入口 | 在左侧活动栏新增「编排查看」入口 |

---

## 1. 现状摸底（已验证事实）

### 1.1 后端：pipeline_runner 执行状态

`src/jarvis/jarvis_tools/pipeline_runner.py`（1147 行）：

- `execute()`（:101）：解析编排 YAML → `_build_dag` → `_create_stage_agents`（主线程串行创建 jvs 常驻 Agent，:424）→ `_schedule`（线程池并行调度，:659）。
- `_schedule`（:659）持有唯一的**权威状态机** `state: Dict[stage, "pending"|"running"|"completed"|"failed"|"skipped"]`，以及 `results`、`gate_blocked_stage`、`gate_approval_path`。
- 状态迁移点：
  - `_create_stage_agents` 成功后 `agent_map[stage] = agent_id`（:452）——**stage ↔ agent_id 映射在此产生**。
  - `_schedule` 中 `state[stage] = "running"`（:757，派发前）。
  - `_handle_stage_result`（:845）：`completed` / `failed` / `pending`（retry 回退）。
  - `skipped`：依赖失败（:695）或 when 不满足（:734）。
  - 门禁停住（:795）。
- 当前进度**只输出到 `stdout_lines`**（文本），无结构化事件、无对外推送。

### 1.2 后端：WebSocket 实时推送通道（已存在，可复用）

- `SessionOutputRouter`（`src/jarvis/jarvis_gateway/output_bridge.py:38`）：`publish(message, session_id=None)`，`session_id=None` 表示**广播到所有活跃连接**（:114）。线程安全（`RLock`）。
- 全局 router 单例：`jarvis_web_gateway/app.py:297 _router`，在 :2158 赋值。
- **已有同类先例**：`_on_agent_status_change`（app.py:518）直接 `_router.publish({"type": "status_update", ...}, session_id=None)` 广播 Agent 状态；`WebGateway.publish_editor_command`（:849）同样广播 `editor_*` 消息。
- 前端 `handleMessage`（`App.vue:15043`）按 `message.type` 分派，已有 `status_update`（:15463）、`editor_open_file`（:15525）、`eval_js_request`（:15528）等分支——**新增一种 type 即可，无需改协议框架**。
- 前端主连接：`connect()`（App.vue:11092）建立主 WebSocket，`handleMessage(message)`（:11187）处理所有广播消息。

### 1.3 前端：活动栏与侧边栏

- 活动栏：`WorkspacePanel.vue:21`（`.workspace-activity-bar`），每个入口是一个 `.workspace-activity-button`，点击 `$emit('setSidebarView', view)`（如 :27）。
- 侧边栏内容：`App.vue:76` 起，按 `workspaceSidebarView` 分支渲染（agents/files/search/manage/timers/plugins/...）。
- 侧边栏标题：`App.vue:79` 三元表达式映射。
- **已有「浮层大图」先例**：`TopologyOverlay.vue`（1027 行，自绘 SVG 网络拓扑）+ `topology.js`（纯 JS 数据模型 + 布局，335 行，有 `topology.test.mjs`）。**这是 D2「自绘 SVG」的最佳参照模板**（发光滤镜、渐变、连线动效、响应式缩放、Esc 关闭、hover 提示）。
- 前端技术栈：Vue 3 + Vite；测试 vitest + `node --test`（`topology.test.mjs`）。

### 1.4 前端：Agent 状态来源

- `agentList`（App.vue:9280）+ `agentStatuses`（Map: agent_id → {execution_status}）。
- `getStatusClass(agent)`（:11936）：`agent.status==='stopped'` → stopped；否则取 `agentStatuses` 的 execution_status；默认 running。
- `status_update` 消息（:15463）实时更新 `agentStatuses`。

**结论**：D3「全链路实时」无需新建通道——复用 `SessionOutputRouter.publish`（后端）+ `handleMessage` 新分支（前端）。

---

## 2. 总体设计（方案乙）

```text
pipeline_runner（执行中）                web_gateway                   前端
  │ 状态机 state/results/gate              │                          │
  │──emit_pipeline_event()──► 全局事件总线 │                          │
  │        (线程安全, 纯数据)              │                          │
  │                          ◄── drain ───│ (后台轮询线程)            │
  │                                       │──_router.publish(广播)──► │
  │                                       │   type=pipeline_event     │
  │                                       │                          │ handleMessage
  │                                       │                          │  新分支
  │                                       │                          ▼
  │                                       │                  pipelineStore（多流程 Map）
  │                                       │                          │
  │                                       │                  OrchestrationView.vue
  │                                       │                  （活动栏入口 + 自绘 SVG DAG）
```

**三层解耦**：

1. **产出层**（pipeline_runner）：在状态机迁移点调用 `emit_pipeline_event(...)`，把结构化事件写入**全局事件总线**。pipeline_runner 不感知 WebSocket / 前端。
2. **桥接层**（web_gateway）：一个后台线程从事件总线 `drain()` 事件，经 `_router.publish(..., session_id=None)` 广播。无前端连接时事件仅短暂驻留内存（有上限），不阻塞执行。
3. **消费层**（前端）：`handleMessage` 新增 `pipeline_event` 分支，写入 `pipelineStore`（按 `pipeline_id` 分组，支持多流程），`OrchestrationView.vue` 渲染。

---

## 3. 后端设计

### 3.1 新增：流水线事件总线（`src/jarvis/jarvis_tools/pipeline_events.py`）

独立小模块，避免 pipeline_runner 与 web_gateway 相互 import：

```python
# 线程安全的事件队列（有界，防止无消费者时内存膨胀）
class PipelineEventBus:
    def emit(self, event: dict) -> None      # 生产者：pipeline_runner 调用
    def drain(self) -> list[dict]            # 消费者：web_gateway 后台线程调用
    def has_events(self) -> bool

def get_event_bus() -> PipelineEventBus      # 全局单例
```

- 用 `collections.deque(maxlen=N)` + `threading.Lock`；`maxlen` 溢出丢弃最旧事件（进度事件可容忍丢帧，最终态以 `pipeline_done` 为准）。
- 纯内存、无 IO、无外部依赖。

### 3.2 改动：pipeline_runner 在状态迁移点发事件

新增私有方法 `_emit(...)`（内部调用 `get_event_bus().emit`），在以下位置埋点：

| 事件 | 触发点 | 关键字段 |
| --- | --- | --- |
| `pipeline_start` | `execute()` 在 `_build_dag` 成功后（:165 附近） | `pipeline_id`、`orchestration_file`、`working_dir`、`nodes`（stage/agent/depends_on/output/gate/when）、`max_workers`、`approve` |
| `pipeline_agents` | `_create_stage_agents` 完成后（:185 附近） | `pipeline_id`、`agent_map`（stage→agent_id） |
| `stage_update` | `_schedule` 中 `state[stage]` 每次迁移时 | `pipeline_id`、`stage`、`status`、`agent_id`、`output`、`error?`、`retry?`、`detail?` |
| `pipeline_done` | `_schedule` 返回前（:810 起各出口） | `pipeline_id`、`success`、`final_status`（completed/failed/gate_blocked）、`gate_stage?`、`approval_path?` |

**`pipeline_id` 生成**：`f"{orchestration_file 的 stem}-{时间戳}-{短随机}"`，在一次 `execute()` 内唯一且稳定。多流程区分靠它。

**埋点原则**：只在既有状态迁移处**追加一行 emit**，不改动控制流、不改返回值、不改 stdout 文本。`state`/`results` 语义零变化 → 现有 48 个单测不受影响（emit 是纯副作用，测试不消费总线）。

### 3.3 改动：web_gateway 桥接线程

`src/jarvis/jarvis_web_gateway/app.py`：

- 新增 `_pipeline_event_pump()`：`while True: drain → for e in events: _router.publish({"type":"pipeline_event","payload":e}, session_id=None); sleep(0.2)`。
- 在 `create_app` 启动 lifespan 中 `asyncio.to_thread`（或 `threading.Thread(daemon=True)`）启动，关闭时置停止标志。
- 复用全局 `_router`（:2158）。**无前端连接时 `publish` 直接返回**（`output_bridge.py:105`），事件被丢弃——符合"实时"语义（不重放历史）。
- 若担心事件在无连接时积压：drain 后无论是否有订阅者都清空（当前实现即如此）。

**为什么用轮询而非直接回调**：pipeline_runner 运行在**独立线程/子进程**（send_to_agent 触发的 Agent 内），与 gateway 的 asyncio 事件循环不在同一上下文；轮询总线是最简单、无耦合的跨线程桥接。0.2s 延迟满足"实时"体感。

### 3.4 多流程并发的正确处理

- 每个 `pipeline_runner.execute()` 生成独立 `pipeline_id`，事件自带该 id。
- 前端 `pipelineStore` 以 `pipeline_id` 为 key 分别维护状态，互不覆盖。
- 同一 `orchestration_file` 并发跑两次 → 两个 `pipeline_id`，前端显示两条独立流程（可加"同一编排文件"分组标签）。

---

## 4. 前端设计

### 4.1 数据层：`src/stores/pipelineStore.js`（新建）

纯 JS（便于 `node --test` 单测，参照 `topology.js` 风格）：

```js
// 内部：Map<pipeline_id, PipelineState>
// PipelineState = {
//   id, orchestrationFile, specFile, workingDir, startedAt, finishedAt,
//   maxWorkers, approve, status,               // running|completed|failed|gate_blocked
//   nodes: [{ stage, agent, dependsOn[], output, gate, when, agentId, status, error }],
//   gateStage, approvalPath, lastSeq
// }

export function createPipelineStore()
  - applyEvent(store, event)      // 按 type 归并；未知 pipeline_id 自动新建
  - listPipelines(store)          // 返回数组（按 startedAt 倒序）
  - getPipeline(store, id)
  - pruneFinished(store, max=20)  // 保留最近 N 条已完成，防内存膨胀
```

- 事件归并规则：
  - `pipeline_start` → 建条目 + 初始化 nodes（status=pending）。
  - `pipeline_agents` → 回填各 node 的 `agentId`。
  - `stage_update` → 更新对应 node 的 status/error/retry。
  - `pipeline_done` → 置条目终态。
- **幂等**：重复事件按 `stage` 覆盖，不追加重复 node。

### 4.2 视图：`src/components/OrchestrationView.vue`（新建，自绘 SVG 的"炫"图）

参照 `TopologyOverlay.vue` 的 SVG 手法（`<defs>` 发光滤镜/渐变、`viewBox` 自适应、hover 高亮、Esc 关闭）。

**布局算法**：DAG 分层（拓扑层级 = 最长路径深度）。

- 抽成纯函数 `layoutDag(nodes) -> {width, height, positions: {stage: {x,y}}, edges: [{from,to}]}`，放 `src/components/dagLayout.js`，配 `dagLayout.test.mjs`（可 `node --test`）。
- 分层：`level(node) = 0 if 无依赖 else 1 + max(level(deps))`；同层内按声明顺序纵向排列；层间横向展开。
- 连线：贝塞尔曲线（`<path d="M... C...">`）。

**节点视觉（D2 炫）**：

- 圆角矩形卡片，含 stage 名 + agent 名 + 状态徽标。
- 状态配色（复用 TopologyOverlay 色板风格）：
  - `pending` 灰（`#8a9bb0`）
  - `running` 青蓝 + **呼吸发光**（`<animate>` 或 CSS `@keyframes`，`feGaussianBlur` 滤镜脉动）
  - `completed` 绿（`#34d99b`）+ 对勾
  - `failed` 红（`#ff5d6c`）+ 叉
  - `skipped` 半透明灰 + 虚线边框
  - `gate` 门禁节点：金色描边（`#f0b429`）+ 盾牌图标，停住时闪烁
- 连线视觉：
  - 已完成的边：绿色实线 + **流动光点**（`stroke-dasharray` + `animate` 偏移）。
  - 进行中的边：青色流动。
  - 未开始：灰色静态。
- 顶部统计卡片（复用 TopologyOverlay 的 `.topo-stats` 风格）：各状态节点计数、耗时、并行度。
- 多流程：顶部 tab 条（编排文件名 + 短 id），点击切换。**默认 tab 展示最新一条。**（管理员已确认：Tab 切换）
- 顶部统计卡片（复用 TopologyOverlay 的 `.topo-stats` 风格）：各状态节点计数、耗时、并行度。

**交互**：

- hover 节点 → 提示（agent_id、output 路径、error）。
- 点击节点 → **跳转到该 Agent 的聊天面板**（管理员已确认：跳转）。复用现有 `onWorkspaceSidebarAgentClick` 类逻辑；无 agent_id（未创建/已跳过）时仅显示详情。
- 终态流程可折叠/关闭（`pruneFinished`）。

### 4.3 入口：活动栏新增「编排查看」（两种形态都要）

管理员已确认：**侧边栏内嵌 + 浮层大图** 两者都要，共用同一渲染组件。

- **共用组件**：`OrchestrationView.vue` 只负责「渲染给定 pipelineStore 的 DAG + tab + 统计」，通过 props 接收 `pipelines`/`activeId`，通过 emit 回传交互事件（切换 tab、点击节点）。两种容器复用同一组件。
- **形态 A：侧边栏内嵌**（活动栏入口）
  - `WorkspacePanel.vue`：活动栏加一个 `.workspace-activity-button`（图标：流程/DAG 图形，自绘 SVG），`@click="$emit('setSidebarView', 'orchestration')"`，title「编排查看」。
  - `App.vue`：侧边栏标题映射（:79）加 `orchestration` → 「编排查看」；侧边栏内容分支（:76 起）加 `v-else-if="workspaceSidebarView === 'orchestration'"`，渲染 `OrchestrationView`（紧凑模式）。
- **形态 B：浮层大图**
  - 新建 `OrchestrationOverlay.vue`（参照 `TopologyOverlay.vue` 的浮层结构：遮罩 + 面板 + Esc 关闭 + `visible` prop/`update:visible`/`close` emit），内部复用 `OrchestrationView`（大图模式）。
  - 入口：侧边栏内嵌视图顶部加「⤢ 大图」按钮（`$emit` 到 `App.vue` 打开浮层）；浮层内亦可反向「在侧边栏打开」。
  - `App.vue` 新增 `showOrchestrationOverlay` ref + `openOrchestrationOverlay()`/`closeOrchestrationOverlay()`（参照 `showTopologyOverlay`，:11030/:9604）。
- `App.vue` 公共改动：
  - `handleMessage`（:15043）加 `else if (type === 'pipeline_event')` 分支 → `pipelineStore.applyEvent`。
  - 引入 `pipelineStore`、`OrchestrationView`、`OrchestrationOverlay`。

### 4.4 美观与响应式

- SVG `viewBox` + `preserveAspectRatio`，适配侧边栏宽度。
- 深色主题下发光效果最佳（与现有 TopologyOverlay 一致）。
- 动效用 CSS `@keyframes`（呼吸/流动），避免 JS 定时器开销。

---

## 5. 改动清单（预估）

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `src/jarvis/jarvis_tools/pipeline_events.py` | 新建 | 事件总线（~60 行） |
| `src/jarvis/jarvis_tools/pipeline_runner.py` | 改 | 加 `_emit` + 5 类埋点（~40 行，纯追加） |
| `src/jarvis/jarvis_web_gateway/app.py` | 改 | 桥接线程 + lifespan 启停（~40 行） |
| `src/jarvis/jarvis_service/frontend/src/stores/pipelineStore.js` | 新建 | 多流程状态归并（~120 行） |
| `src/jarvis/jarvis_service/frontend/src/components/dagLayout.js` | 新建 | DAG 分层布局纯函数（~100 行） |
| `src/jarvis/jarvis_service/frontend/src/components/OrchestrationView.vue` | 新建 | 自绘 SVG 视图（~400 行，侧边栏/浮层共用） |
| `src/jarvis/jarvis_service/frontend/src/components/OrchestrationOverlay.vue` | 新建 | 浮层大图容器（~120 行，参照 TopologyOverlay） |
| `src/jarvis/jarvis_service/frontend/src/components/WorkspacePanel.vue` | 改 | 活动栏入口按钮（~12 行） |
| `src/jarvis/jarvis_service/frontend/src/App.vue` | 改 | 标题映射 + 侧边栏分支 + 浮层挂载 + `handleMessage` 分支 + import（~50 行） |
| 测试 | 新建 | `test_pipeline_events.py`、`test_pipeline_runner.py` 补埋点断言、`pipelineStore.test.mjs`、`dagLayout.test.mjs` |

---

## 6. 兼容性与约束

- **向后兼容**：pipeline_runner 的返回值、stdout、状态机语义零变化；emit 纯副作用。现有 48 个 pipeline_runner 单测 + 77 个相关测试不受影响。
- **无前端连接**：事件被丢弃，不积压、不阻塞执行。
- **多流程**：靠 `pipeline_id` 隔离。
- **最小改动**：不改 WebSocket 协议框架（仅加一种 message type）；不改 Agent 状态机；不改 flow YAML 格式。
- **不引入 eval**：前端不 eval 后端数据；事件为纯 JSON 数据。
- **安全**：事件只含 stage/agent_id/路径/状态，不含密钥；广播走既有鉴权连接。

---

## 7. 验证计划

1. **后端单测**：
   - `test_pipeline_events.py`：emit/drain/溢出丢弃/线程安全。
   - `test_pipeline_runner.py`：mock 总线，断言 start/agents/stage_update/done 事件序列与 stage 状态一致。
2. **前端单测**（`node --test`）：
   - `pipelineStore.test.mjs`：多流程隔离、事件归并幂等、终态、prune。
   - `dagLayout.test.mjs`：分层正确、无依赖单点、多依赖、环（防御）。
3. **构建**：`npm run build` 通过；`ruff check` / `ty check` 通过。
4. **端到端（可选，管理员已表示可跳过真实环境验证）**：`pipeline_runner dry_run` 不产生事件；真实跑时前端可见节点由 pending→running→completed 的实时变化。

---

## 8. 管理员已确认决策（2026-10-08）

1. **入口形态**：侧边栏内嵌 + 浮层大图 **两者都要**（共用 `OrchestrationView`）。
2. **多流程展示**：顶部 **Tab 切换**。
3. **节点点击行为**：**跳转**到对应 Agent 聊天面板（无 agent_id 时仅显示详情）。
4. **事件保留**：前端保留最近 **20 条**已完成流程。

> 方案已定稿，可进入实现。
