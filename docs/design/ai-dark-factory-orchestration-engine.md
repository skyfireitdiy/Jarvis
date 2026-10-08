# AI 黑灯工厂：内置编排执行引擎（方案 B）设计

> 状态：**待评审（先方案后实现）**
> 目标：让黑灯工厂的 4 个 agent（planner → generator → validator → orchestrator）**自动按顺序协作**跑起来，同时保留门禁人工审批关口（不完全无人值守）。
> 依据：对 Jarvis 多 Agent 编排机制的完整调研（见文末「调研事实」）。

---

## 0. 背景与问题

当前黑灯工厂用 `@OrganizeAgents` 加载 `dark_factory_pipeline.yaml`，只**批量创建 4 个带 `task`（角色描述）的 agent**。调研确认（详见文末）：

- `@OrganizeAgents`（`builtin_input_handler.py:546-757`）创建 agent 后**直接返回，无任何自动执行**。
- 带 `--task` 的 agent（无论是否 `no_interaction_mode`）启动后**执行一次 task 然后退出**（jvs `jarvis.py:1647-1653,1713`；jca `code_agent.py:1726-1760`），web_gateway 在 finally 关闭。
- 编排文件**只支持单 agent 创建字段，无依赖/顺序/产物传递字段**（`builtin_input_handler.py:711-729`）。
- 系统**无现成的"等待/join 多 agent 顺序执行"机制**（`dispatch` 是 tmux 并行派发，`tmux_wrapper.py:72`）。

**结论**：黑灯工厂当前是"创建了流水线角色，但没有流水线调度引擎"。要让 4 个 agent 自动协作，需要**内置编排执行引擎**（方案 B）。

**设计取向**：编排执行引擎（`pipeline_runner`）是**通用基础设施**，与黑灯工厂的具体业务（NLSpec/四层架构/holdout/门禁）无关。它放核心工具目录，任何插件/用户都能用它定义自己的多 Agent 流水线；黑灯工厂只是它的一个使用者（通过编排文件的 `flow` 字段声明自己的阶段与产物契约）。

**编排文件动态生成**：编排文件（含 `agents` 与 `flow`）是**每次任务动态生成的结构化 plan**，由编排 agent 根据 spec、代码库现状与用户讨论共同产出，用户确认后再执行。插件自带的 `dark_factory_pipeline.yaml` 仅作为参考模板，不直接用于每次任务。黑灯工厂在**已有代码库**中工作——generator 阶段直接修改现有代码，不生成到独立目录。

---

## 1. 设计目标与原则

### 1.1 目标

1. 一次触发，自动跑完 `规划 → 生成 → 验证 → 门禁` 四层流水线。
2. 每层之间**自动传递中间产物**（实现计划 → 代码库改动 → pass/fail 报告）。
3. 每层**自动等待完成**后再触发下一层。
4. 在门禁处**停住等人工审批**，不自动合并（不完全无人值守）。

### 1.2 原则

- **只协调不执行**（sw-controller 模式）：调度器不写码、不测试，只负责按序调度与产物传递。
- **复用现有机制**：优先复用 `jca -n --task-file` + `status_file`（现成的非交互执行 + 状态回传），不重复造轮子。
- **最小侵入**：不改动核心 agent 启动逻辑，新增能力以**核心通用工具**形式提供。
- **保持人工审批关口**：门禁处停住，符合管理员"不完全无人值守"决策。

---

## 2. 总体架构

```text
┌─────────────────────────────────────────────────────────────┐
│  触发入口（三种）                                            │
│  ① 用户输入 <dark-factory/issue> / <dark-factory/pr>         │
│  ② 用户输入 <dark-factory/run>（新增，直接跑流水线）          │
│  ③ 主 agent 调用 pipeline_runner 工具                         │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  编排执行引擎 pipeline_runner（核心通用工具，自动注册）       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ 读取编排定义（flow 顺序）                                │ │
│  │ 对每个阶段：                                            │ │
│  │   1. 组装 task-file（含本阶段 task + 上阶段产物路径）     │ │
│  │   2. 用 jca -n --task-file 启动阶段 agent（同步）        │ │
│  │   3. poll status_file 等待 completed/failed             │ │
│  │   4. 校验产物落盘，写入下一阶段 task-file                │ │
│  │ 门禁阶段：输出审批报告后停住，等待人工审批               │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
    planner ──计划──▶ generator ──代码──▶ validator ──报告──▶ orchestrator ──审批报告──▶ 人工审批
```

---

## 3. 编排定义格式扩展（编排文件新增 `flow`）

在 `dark_factory_pipeline.yaml` 的 `agents` 之外，新增顶层 `flow` 字段描述**阶段顺序与产物契约**：

```yaml
agents:
  - name: "df_planner"
    type: "agent"
    working_dir: "."
    task: "..."   # 角色描述（保持不变）
  # ... df_generator / df_validator / df_orchestrator

flow:
  - stage: "planner"
    agent: "df_planner"
    output: ".df/plan.md"          # 本阶段产物（实现计划）
  - stage: "generator"
    agent: "df_generator"
    input: ".df/plan.md"           # 依赖上一阶段产物
    # 无独立 output：generator 直接在 working_dir（已有代码库）中修改代码
  - stage: "validator"
    agent: "df_validator"
    input: ".df/plan.md"           # 依赖规划产物；验证对象为修改后的工作目录
    output: ".df/report.json"      # pass/fail 报告
  - stage: "orchestrator"
    agent: "df_orchestrator"
    input: ".df/report.json"
    output: ".df/approval.md"      # 审批报告（交人工）
    gate: true                     # 门禁：停住等人工审批
```

**兼容性**：`flow` 为**可选**字段。无 `flow` 时，`@OrganizeAgents` 行为不变（只创建 agent）。有 `flow` 时，编排引擎按 flow 驱动。

---

## 4. 核心组件：pipeline_runner 工具

### 4.1 位置与形态

- **文件**：`src/jarvis/jarvis_tools/pipeline_runner.py`（**核心通用工具**，非插件专用）
- **类**：`PipelineRunnerTool`（`name = "pipeline_runner"`，等于文件名 stem）
- **注册**：核心工具目录被 `ToolRegistry._load_builtin_tools` 自动扫描注册（`registry.py:600-620`），无需任何配置。
- **通用性**：不依赖任何插件业务。它只做"读编排文件 flow → 按序驱动 agent → 传递产物 → 等待完成"，具体阶段/产物/门禁由**使用方的编排文件**声明。
- **职责**：读取编排文件 + 按 flow 顺序用 `jca -n --task-file` 驱动各阶段 agent，poll status_file 等待，传递产物，门禁停住。

### 4.2 参数（parameters）

```json
{
  "type": "object",
  "properties": {
    "orchestration_file": {"type": "string", "description": "编排 YAML 路径"},
    "spec_file": {"type": "string", "description": "NLSpec 文件路径（流水线输入）"},
    "working_dir": {"type": "string", "description": "工作目录（默认当前目录）"},
    "approve": {"type": "boolean", "description": "门禁阶段是否已获人工审批（默认 false，需人工确认）"}
  },
  "required": ["orchestration_file", "spec_file"]
}
```

### 4.3 执行流程

```text
execute(args):
  1. 校验参数：orchestration_file、spec_file 存在；编排文件可解析且含 agents + flow。
  2. 初始化工作目录：创建 .df/ 目录。
  3. 遍历 flow 的每个 stage：
     a. 组装 task-file JSON：
        {
          "task_desc": <agent.task 角色描述> + "\n\n本阶段输入产物:\n" + <input 路径内容摘要>,
          "background": "黑灯工厂流水线，阶段=<stage>，输入=<input>，输出=<output>",
          "additional_info": "请将本阶段产物写入 <output>，完成后退出。",
          "status_file": "<working_dir>/.df/<stage>.status"
        }
     b. 用 subprocess 运行：jca -n --task-file <taskfile>（cwd=working_dir）。
     c. poll <stage>.status 直到出现 "completed"/"failed"（超时则报错）。
     d. 校验 <output> 产物已落盘；失败则中止流水线并报告。
  4. 门禁阶段（gate: true）：
     a. 输出审批报告路径 .df/approval.md。
     b. 若 approve=false：停住，返回"审批报告已生成，请人工审批后以 approve=true 重跑门禁确认"。
     c. 若 approve=true：标记流水线完成，返回汇总。
  5. 返回 {"success", "stdout", "stderr"}，stdout 含各阶段状态与产物路径。
```

### 4.4 关键实现要点

- **同步等待**：poll status_file（间隔 2s，超时默认 30min，可配）。复用 `status_file` 机制（`jarvis.py:1758-1801`）。
- **产物传递**：上阶段 `<output>` 路径写入下阶段 task-file 的 `input`，agent 通过 `additional_info` 读取。
- **失败处理**：任一阶段 failed 即中止，保留已落盘产物便于排查。
- **门禁停住**：orchestrator 阶段完成后，引擎不继续，等待人工审批（approve 参数）。
- **jca 可用性**：调用前校验 `shutil.which("jca")`，不可用则报错。

---

## 5. 触发入口（三种）

### 5.1 新增 replace_map 指令 `<dark-factory/run>`

在 `config.yaml` 的 `replace_map` 新增：

```yaml
dark-factory/run:
  append: false
  template: |
    请用内置编排引擎 pipeline_runner 运行黑灯工厂流水线。
    - 先确认 NLSpec 已就绪（spec_file），否则用 spec_validator 补全。
    - 与用户讨论，动态生成编排文件（agents + flow，参考
      orchestration/dark_factory_pipeline.yaml 模板），落盘 .df/pipeline.yaml，
      用户确认无误。
    - 调用 pipeline_runner 执行（approve=false，门禁停住）。
    - 运行后把审批报告交人工审批。
```

用户输入 `<dark-factory/run>` 即触发主 agent：与用户讨论生成编排文件 → 用户确认 → 调用 pipeline_runner。

### 5.2 保留 `<dark-factory/issue>` / `<dark-factory/pr>`

这两个入口面向 GitHub Issue/PR 驱动，模板中同样改为"动态生成编排文件 + 用户确认 + 用 pipeline_runner 跑流水线"，其余不变。

### 5.3 手动调用

主 agent 或 orchestrator agent 可直接调用 `pipeline_runner` 工具。

---

## 6. 与现有机制的关系

| 现有机制 | 方案 B 的使用 |
|---------|--------------|
| `@OrganizeAgents` | **保留**：无 `flow` 时仍只创建 agent；有 `flow` 时建议改用 pipeline_runner 驱动 |
| `jca -n --task-file` | **复用**：作为阶段 agent 的执行入口（`jarvis.py:1095-1119`） |
| `status_file` | **复用**：作为阶段完成状态回传（`jarvis.py:1758-1801`） |
| `send_to_agent` | **不使用**（异步，无法同步等待；且带 task agent 已退出） |
| `no_interaction_mode` | **不使用**（阶段 agent 由 jca -n 驱动，天然非交互） |
| 3 个工具（spec_validator/holdout_generator/gate_calculator） | **保留**：各阶段 agent 内部仍可调用 |

---

## 7. 不完全无人值守的落地

- **全自动段**：planner → generator → validator 由引擎自动驱动，可无人值守。
- **人工审批关口**：orchestrator 产出审批报告后，引擎**停住**，返回审批报告路径，等待人工 `approve=true` 确认后才标记完成。
- **不自动合并**：引擎不做 git merge/PR merge，交付/合并由人工在审批通过后触发。

---

## 8. 实施步骤

1. **扩展编排文件**：`dark_factory_pipeline.yaml` 新增 `flow` 字段（阶段顺序 + 产物契约）。
2. **新增核心通用工具** `src/jarvis/jarvis_tools/pipeline_runner.py`：实现 `PipelineRunnerTool`（校验/组装 task-file/启动 jca/poll status/产物校验/门禁停住）。放核心目录由 `ToolRegistry._load_builtin_tools` 自动注册（`registry.py:600-620`），无需配置。
3. **更新 config.yaml**：`replace_map` 新增 `dark-factory/run`（模板：与用户讨论动态生成编排文件 → 用户确认 → 调用 pipeline_runner）。
4. **更新规则**：`orchestration.md` 补充"用 pipeline_runner 驱动流水线"的说明。
5. **更新设计文档**：记录方案 B 的编排引擎设计。
6. **补充测试**：`tests/jarvis_tools/test_pipeline_runner.py` 增加 pipeline_runner 的单元测试（mock jca 子进程 + status_file）。

---

## 9. 验证方式

- **单元测试**：pipeline_runner 在 mock 场景下按 flow 顺序调用 jca、poll status、传递产物、门禁停住。
- **编排文件**：yamllint 通过；`flow` 字段可解析。
- **端到端**（可选，需真实环境）：`<dark-factory/run>` 触发后，观察 4 个阶段按序执行、产物落盘、门禁停住。

---

## 10. 风险与对策

| 风险 | 对策 |
|------|------|
| 阶段 agent 长时间不结束 | poll 超时（默认 30min，可配），超时报错并保留产物 |
| 产物契约不一致（某阶段未写 output） | 每阶段完成后校验 output 落盘，缺失即中止 |
| jca 不可用/未登录 | 启动前校验 `shutil.which("jca")`，报错提示 |
| 门禁误自动通过 | 默认 `approve=false`，必须人工确认才放行 |
| 与 `@OrganizeAgents` 行为冲突 | `flow` 可选，无 flow 时保持原行为，向后兼容 |

---

## 11. 调研事实（方案依据）

1. **@OrganizeAgents**：`builtin_input_handler.py:546-757`，创建 agent 后直接返回，无自动执行。
2. **agent 启动**：`agent_manager.py:251` Popen；`AGENT_ENTRY_POINTS={agent:jvs, code_agent:jca}`（115-118）；带 `--task` 即执行后退出（jvs `jarvis.py:1647-1653,1713`；jca `code_agent.py:1726-1760`）。
3. **消息传递**：`send_to_agent`（`gateway_manager.py:617`）走 `/api/agent/{id}/message`；`/message` 端点 `jarvis.py:1527-1558` 注入输入流，仅对无 task 待命 agent 有效。
4. **task-file/status_file**：`jarvis.py:1095-1119` 解析 task-file（task_desc/background/additional_info/status_file）；`jarvis.py:1758-1801` 执行后回写 status/.output/.error 文件。
5. **编排文件字段**：`builtin_input_handler.py:711-729`，无依赖/顺序/产物字段。
6. **顺序执行机制**：无现成 wait/join；`dispatch` 是 tmux 并行派发（`tmux_wrapper.py:72`）。
7. **agent 执行入口**：CLI task（jvs:1647/jca:1726）、`/message`（jarvis.py:1527）、交互循环（jvs:1689-1711）；主循环 `agent.run`（`jarvis_agent/__init__.py:1958`）。

---

## 附录 A：pipeline_runner 支持 DAG 编排（方案设计）

> 状态：**待评审（先方案后实现）**
> 目标：把 `pipeline_runner` 的 `flow` 从**线性列表**升级为 **DAG（有向无环图）**，支持并行、多输入汇聚、条件分支、失败策略与重试。
> 范围确认（管理员 2026-10-08）：**全做**（并行/多输入/条件/失败策略/重试），并行度默认 4。

## A.1 背景与问题

当前 `pipeline_runner.py`（`src/jarvis/jarvis_tools/pipeline_runner.py`）的 `flow` 是**线性数组**，`execute()` 用 `for idx, stage in enumerate(flow)` 顺序遍历：

- 每阶段**只能指定一个 agent**（`agent_name` 为单字符串，154-157 行校验须在 `agents_by_name` 内）。
- 输入**只能是上一个阶段的 output**（`stage_input = input_ref or previous_output`，163 行）——无多输入、无分支、无并行、无循环。
- 阶段失败**即整体中止**（201-207 行），无重试、无容错分支。

**结论**：flow 目前只支持**线性顺序**。要支撑"更复杂的编排流程"（黑灯工厂多验证器并行、按结果分支、多报告汇聚等），需把 flow 升级为 DAG。

## A.2 设计目标与原则

1. **DAG 调度**：支持并行、多输入汇聚、条件分支、失败策略、重试。
2. **只协调不执行**（不变）：调度器不写码、不测试，只负责调度与产物传递。
3. **阶段 Agent = 常驻 Agent 实体，统一用 `jvs`**：每个 flow 阶段对应一个**常驻 Agent 实体**（经 `_create_agent` 创建，`type: agent` → `jvs --web-gateway` 待命），通过 `send_to_agent` 发送任务并**同步等待**其完成。**统一使用 `jvs`**——`jvs`（`jarvis_agent/jarvis.py`）**无仓库文件锁**（锁只存在于 `jca` 的 `code_agent.py:1688-1696`），多个 jvs 常驻 Agent 可安全并行。不使用 `jca -n --task-file` 一次性子进程作为并行载体（受仓库文件锁限制，见 A.5.1）。
4. **入口统一 jvs**：阶段 Agent 一律 `type: agent` → `jvs`（`agent_manager.py:115-118`），避免 jca 的仓库锁。
5. **向后兼容**：老编排文件（线性 flow）零改动；`flow` 仍可选，无 flow 时 `@OrganizeAgents` 行为不变。
6. **安全**：`when` 条件用受限表达式解析器，绝不 `eval` 任意代码。

## A.3 核心概念：从"列表"到"图"

**现状**：`flow` 是 `[{stage, agent, input, output, gate}]` 数组，隐式顺序 = 数组下标。

**升级后**：`flow` 仍是数组（保持人类可读、向后兼容），但每个 stage 显式声明 `depends_on`（依赖的上游 stage 列表），引擎据此构建 DAG 并做**拓扑排序 + 并行调度**。

```yaml
flow:
  - stage: "plan"
    agent: "df_planner"
    output: ".df/plan.md"

  # 两个验证器并行，都依赖 plan
  - stage: "verify_unit"
    agent: "df_validator_unit"
    input: ".df/plan.md"
    output: ".df/report_unit.json"
    depends_on: ["plan"]

  - stage: "verify_e2e"
    agent: "df_validator_e2e"
    input: ".df/plan.md"
    output: ".df/report_e2e.json"
    depends_on: ["plan"]

  # 汇聚：orchestrator 消费两个验证报告
  - stage: "orchestrate"
    agent: "df_orchestrator"
    input: [".df/report_unit.json", ".df/report_e2e.json"]
    output: ".df/approval.md"
    depends_on: ["verify_unit", "verify_e2e"]
    gate: true
```

**关键点**：

- `depends_on` 缺省时 = 上一个 stage（**保持线性写法完全兼容**，老编排文件无需改动）。
- `input` 升级为**可列表**（多输入汇聚）。
- 无依赖的 stage 自动进入并行调度。

## A.4 字段扩展

| 字段 | 现状 | DAG 版 | 说明 |
|------|------|--------|------|
| `stage` | 字符串 | 字符串 | 阶段唯一名（图节点 ID） |
| `agent` | 单字符串 | 单字符串 | 每阶段仍单 agent（保持"只协调"语义） |
| `depends_on` | ❌ 无 | `[stage名]` 可选 | 显式依赖；缺省=上一个 |
| `input` | 单字符串 | **字符串或列表** | 多输入汇聚 |
| `output` | 单字符串 | 单字符串 | 产物路径 |
| `gate` | bool | bool | 门禁 |
| `when` | ❌ 无 | 条件表达式（可选） | 条件分支 |
| `retry` | ❌ 无 | int（可选） | 失败重试次数 |
| `on_error` | ❌ 无 | `abort`/`continue`/`skip_dependents` | 失败策略 |

## A.5 调度引擎（核心改动）

`execute()` 从 `for` 线性循环改为 **DAG 调度循环**：

```text
execute(args):
  1. 校验参数（同现状）
  2. 解析 flow，构建图：
     - 节点 = stage；边 = depends_on 关系
     - 校验：stage 名唯一、agent 存在、depends_on 引用的 stage 存在
     - 拓扑排序；检测环（有环则报错不执行）
  3. 初始化产物目录 .df/、spec 摘要（同现状）
  4. 创建本流水线所需的常驻 Agent 实体（经 _create_agent，type 决定 jvs/jca）
  5. 调度循环（关键新增）：
     while 有未完成节点:
       - ready = 所有依赖已成功完成的节点
       - 并行向 ready 节点对应的常驻 Agent 发送任务（并发上限 max_workers 默认 4）
       - 每个节点 = 一个独立 Agent（send_to_agent 发送 → 同步等待完成 → 校验产物）
       - 收集各节点结果，更新完成集合
  6. 门禁：任一 gate 节点完成后，若 approve=false 停住（同现状）
  7. 失败策略：按 on_error 处理
  8. 返回汇总（stdout 含各阶段状态/产物/耗时）
```

### A.5.1 关键约束：jca 仓库文件锁（为何统一用 jvs）

**代码事实**（`code_agent.py:1688-1696`、`utils.py:421-470`、`jarvis_agent/jarvis.py`）：

- **jca**（`code_agent.py`）启动时按**仓库根目录**加独占锁：`code_agent_{md5(repo_root)}.lock`（`code_agent.py:1692`）。锁是**非阻塞独占**：已有存活实例持锁时，新进程**直接 `sys.exit(0)` 退出**（`utils.py:432-436`）。**`--web-gateway` 常驻模式同样会走到该锁**（`code_agent.py:1591-1603` 后继续到 1690）。
- **jvs**（`jarvis_agent/jarvis.py`）**完全没有文件锁逻辑**（grep 无 `_acquire_single_instance_lock`），且支持 `--web-gateway` 常驻（`jarvis.py:950-957,1262`）与 `--task-file`（`jarvis.py:819-820`）。

**结论（管理员决策 2026-10-08）**：**并行编排统一使用 `jvs` 常驻 Agent**，从根上规避 jca 的仓库文件锁——同一仓库下多个 jvs 常驻 Agent 可安全并行，**无需 worktree 隔离**（worktree 方案不接受）。

### A.5.2 并行实现（常驻 jvs Agent + send_to_agent 同步等待）

每个 flow 阶段就是一个**常驻 `jvs` Agent 实体**。并行 = 同时向多个互不依赖的常驻 Agent 发送任务并各自等待完成，**而非线程池调度、也非一次性 jca 子进程**。

- **创建**：经 `_create_agent` 创建常驻 Agent，**统一 `type: agent` → `jvs --web-gateway`** 待命（`agent_manager.py:115-118`），无仓库锁，可并行。
- **发送**：`send_to_agent` 向各 Agent 发送本阶段任务。
- **同步等待**：**给 `send_to_agent` 增加 `wait` 参数**——目前是异步 fire-and-forget（`gateway_manager.py:617` 只发消息、立即返回；`/message` 端点 `jarvis.py:1527` 仅注入输入流）。`wait=true` 时等待 Agent 处理完并回传结果（见 A.5.3）。
- **并发上限**：`max_workers` 默认 4，限制同时执行的常驻 Agent 数，避免资源打爆。
- **产物隔离**：`status_file` 用 `stage名` 区分；产物目录 `.df/` 各 stage 独立文件；jvs 无仓库锁，同仓库并行无需 worktree。

### A.5.3 新增能力：send_to_agent 的 `wait` 参数

现状 `send_to_agent` 只投递消息、不等待结果。为支撑"同步等待阶段 Agent 完成"，**给 `send_to_agent` 增加 `wait` 参数（管理员决策 2026-10-08）**：

- **`wait=false`（默认，向后兼容）**：行为不变，异步 fire-and-forget。
- **`wait=true`**：发送后**轮询 Agent 的 `/status`**（`code_agent.py:1349` / `jarvis.py` 已有 `execution_status` 接口），直到 `execution_status` 回到空闲/完成态，再返回结果。
- **结果回传**：Agent 完成阶段任务后，把产物路径/结构化结果通过 `/message` 或专用回传接口返回，编排引擎据此校验产物并进入下一批。
- **超时**：轮询设超时（默认可配），超时报错并保留现场。

> 注：`/message` 目前只对**无 task 待命 agent** 有效（`jarvis.py:1527-1558` 注入输入流）；常驻 jvs Agent 即此类待命 agent，故 `wait` 机制与常驻 Agent 方案天然契合。

## A.6 条件分支（`when`）

`when` 用**简单表达式**引用上游阶段结果，满足才执行该节点，否则跳过（标记 skipped，其下游视为"依赖满足"）。

```yaml
- stage: "verify_e2e"
  agent: "df_validator_e2e"
  depends_on: ["verify_unit"]
  when: "verify_unit.status == 'completed' && verify_unit.pass_rate >= 0.9"
```

**表达式范围（保守）**：只支持读取上游 stage 的**结构化结果**（从 status_file 或产物 JSON 读取），如 `status`、`pass_rate`、`exit_code`。**不做任意代码求值**（安全考虑，避免注入）。用受限的表达式解析器（如 `asteval` 或手写白名单解析），不 `eval()`。

## A.7 失败策略（`on_error`）

每阶段可声明失败时的行为：

| 值 | 行为 |
|----|------|
| `abort`（默认） | 中止整条流水线（同现状） |
| `continue` | 标记失败，但继续执行不依赖它的节点 |
| `skip_dependents` | 标记失败，并跳过所有依赖它的下游节点 |

全局可设默认 `default_on_error`，阶段级可覆盖。

## A.8 重试（`retry`）

每阶段可声明 `retry: N`，失败时自动重跑该阶段最多 N 次；重试耗尽仍失败则按 `on_error` 处理。每次重试重新组装 task-file 并清空旧 status_file。

## A.9 兼容性（关键约束）

- **`flow` 仍可选**：无 flow 时 `@OrganizeAgents` 行为不变。
- **老编排文件零改动**：`depends_on` 缺省 = 上一个 stage，`input` 单字符串也接受（自动转单元素列表）。`dark_factory_pipeline.yaml` 现有线性 flow 无需改。
- **新增字段全部可选**：`when`/`retry`/`on_error`/`worktree` 缺省时行为 = 现状。
- **`send_to_agent` 向后兼容**：新增同步等待为**可选参数/新操作**，现有异步调用不受影响。
- **线性编排仍可用**：无并行需求时，`depends_on` 缺省 = 上一个 stage，等价于现状线性 flow。

## A.10 改动范围

| 文件 | 改动 |
|------|------|
| `src/jarvis/jarvis_tools/pipeline_runner.py` | 核心：图构建/拓扑排序/常驻 Agent 创建与调度/条件/失败策略/重试。约 +250~350 行 |
| `src/jarvis/jarvis_tools/gateway_manager.py` | `send_to_agent` 增加同步等待能力（`wait` 参数或新增 `send_to_agent_sync` 操作） |
| `src/jarvis/jarvis_agent/jarvis.py` / `code_agent.py` | 如需：`/message` 或 `/status` 补充"任务完成 + 结果回传"语义 |
| `builtin/plugins/ai-dark-factory/orchestration/dark_factory_pipeline.yaml` | 注释补充 DAG 用法（可选，模板加并行示例） |
| `docs/design/ai-dark-factory-orchestration-engine.md` | 本文档（本附录） |
| `tests/jarvis_tools/test_pipeline_runner.py` | 新增 DAG 测试：拓扑排序、并行、多输入、条件、失败策略、环检测、锁处理 |

**不改**：`@OrganizeAgents`、`status_file`、config.yaml（无需新增入口）。

## A.11 风险与对策

| 风险 | 对策 |
|------|------|
| 环导致死循环 | 拓扑排序前置检测，有环报错不执行 |
| **同仓库并行被文件锁卡死** | **统一用 jvs 规避**（jvs 无仓库锁，`jarvis.py` 无 `_acquire_single_instance_lock`），无需 worktree |
| **同步等待超时/挂起** | `wait=true` 轮询 `/status` 设超时（默认可配），超时报错并保留现场 |
| 并行阶段资源竞争（多个 Agent 同时跑） | 可配 `max_workers`（默认 4），避免打爆机器 |
| 并行阶段产物写同一路径 | 约定每阶段独立 output 文件；引擎校验 output 唯一 |
| `when` 表达式注入 | 受限表达式解析器，白名单，不 eval 任意代码 |
| 门禁语义在并行下模糊 | 门禁节点仍是单节点；其所有依赖完成后才执行，执行完停住等审批 |
| 常驻 Agent 创建失败/不可用 | 启动前校验并重试创建；失败按 `on_error` 处理 |
| 复杂度上升 | 保持"每阶段单 agent"约束，DAG 只解决调度，不引入多 agent 单阶段 |

## A.12 实施步骤（评审通过后）

1. **给 `send_to_agent` 增加 `wait` 参数**（`gateway_manager.py`）：`wait=true` 时轮询 `/status` 等待完成并回传结果；必要时在 `/message`/`/status` 补充"任务完成 + 结果回传"语义。`wait` 缺省为 `false`，向后兼容。
2. 重构 `execute()`：拆出 `_build_dag()`（解析+校验+拓扑排序）、`_create_stage_agents()`（创建常驻 jvs Agent）、`_run_stage()`（send_to_agent 发送 + wait 同步等待 + 校验产物）、`_schedule()`（并行调度循环）。
3. 实现 `when` 受限表达式解析、`on_error` 失败策略、`retry`。
4. **编排系统忽略 flow 阶段的 `type` 字段**（管理员决策 2026-10-08）：阶段 Agent 一律按 `type: agent` → `jvs` 创建，不读取/不依赖编排文件里的 `type`。
5. 更新模板 YAML 注释 + 设计文档。
6. 补单元测试（mock send_to_agent + /status，覆盖并行/汇聚/条件/失败/环/锁处理）。
7. 验证：老编排文件行为不变；新 DAG 编排正确并行与汇聚。
