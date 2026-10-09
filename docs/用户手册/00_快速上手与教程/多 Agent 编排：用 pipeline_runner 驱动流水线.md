# 多 Agent 编排：用 pipeline_runner 驱动流水线

## 使用场景

当任务可以拆成"规划 → 执行 → 验证 → 汇总"这类多阶段流程，且阶段之间有依赖关系时，用单个 Agent 串行做会又慢又乱。Jarvis 内置 **`pipeline_runner`** 编排引擎：你声明一份编排文件（含 `agents` 定义与可选 `flow` 顺序），它按 `flow` 构建 DAG，用常驻 `jvs` Agent 并行调度各阶段，同步等待完成、校验产物、把上阶段产物传给下阶段。

它遵循 **sw-controller 模式**：只协调不执行——引擎自己不写码、不测试，具体每个阶段做什么由编排文件里的 `task` 声明。

## 前置条件

- 已安装 Jarvis，且能运行 `jvs`（编排会创建常驻 `jvs` Agent）。
- 有一个工作目录（产物写入其下的 `.jarvis/artifacts/`）。
- 一份编排文件（`.yaml` / `.yml` / `.flow`）。

## 操作步骤

### 一、看一个最小示例

仓库自带 `builtin/agent_orchestration/simple_demo.yaml`，演示"扇出 → 并行 → 汇聚"：

```text
           ┌─> worker_a ─┐
planner ───┤             ├─> aggregator
           └─> worker_b ─┘
```

其 `flow` 部分：

```yaml
flow:
  - stage: "planner"
    agent: "demo_planner"
    output: ".df/demo_plan.md"
  - stage: "worker_a"
    agent: "demo_worker_a"
    depends_on: ["planner"]
    input: ".df/demo_plan.md"
    output: ".df/demo_a.md"
  - stage: "worker_b"
    agent: "demo_worker_b"
    depends_on: ["planner"]
    input: ".df/demo_plan.md"
    output: ".df/demo_b.md"
  - stage: "aggregator"
    agent: "demo_aggregator"
    depends_on: ["worker_a", "worker_b"]
    input:
      - ".df/demo_a.md"
      - ".df/demo_b.md"
    output: ".df/demo_final.md"
```

关键点：`worker_a` 与 `worker_b` 都只依赖 `planner`，因此**并行**执行；`aggregator` 等两者都完成后再跑。

### 二、先预览计划（不执行）

在真正跑之前，先用 `dry_run` 校验编排文件、看将要执行的 DAG（阶段 / 依赖 / 并行批次 / 产物 / 门禁 / 条件 / 重试 / 失败策略），**不创建 Agent、不派发任务**：

```text
pipeline_runner(
  orchestration_file="builtin/agent_orchestration/simple_demo.yaml",
  working_dir="/path/to/workdir",
  dry_run=true
)
```

在 Web 界面里，编排弹窗选中文件后点「预览」即可看到静态 DAG 图。

### 三、运行流水线

```text
pipeline_runner(
  orchestration_file="builtin/agent_orchestration/simple_demo.yaml",
  working_dir="/path/to/workdir",
  max_workers=4
)
```

`max_workers` 是并行度上限（默认 4），限制同时执行的阶段 Agent 数。

在 Web 界面里，选中编排文件后点「运行流水线」，可在「编排查看」中实时看到各阶段状态与 DAG。

### 四、编排文件的能力清单

`flow` 每一项是一个 stage，支持以下字段：

| 字段 | 说明 |
| --- | --- |
| `stage` | 阶段名（唯一，供 `depends_on` / `when` 引用） |
| `agent` | 引用 `agents` 中的 `name` |
| `input` | 上游产物路径；单个字符串自动转单元素列表，多输入写列表 |
| `output` | 本阶段产物路径；非空且全局唯一（重复报错） |
| `depends_on` | 依赖的 stage 列表；缺省 = 上一个 stage（线性） |
| `when` | 受限表达式，不满足则跳过该阶段 |
| `retry` | 失败重试次数（整数，默认 0） |
| `on_error` | 失败策略：`abort`（默认）/ `continue` / `skip_dependents` |
| `gate` | 门禁：`true` 时 `approve=false` 会停住等人工审批 |

顶层可选字段：

- `spec`：作为各阶段背景注入（可选）。
- `default_on_error`：阶段未声明 `on_error` 时的全局默认（非法值回退 `abort`）。

#### `when` 受限表达式

`when` 是**白名单求值**（不 eval 任意代码），支持：

- 引用上游 stage 的字段：`stage.field`（取自上游 `status_file` 与产物 JSON 内容）。
- 比较：`==` `!=` `>=` `<=` `>` `<`。
- 逻辑：`&&` `||` `!`。
- 字面量：数字 / 字符串 / 布尔。

示例：

```yaml
- stage: "notify"
  agent: "notifier"
  depends_on: ["validator"]
  when: "validator.pass_rate >= 0.9"
```

#### `loop` 运行时循环原语

需要"重跑直到达标"时（如修复 → 重验循环），用 `loop`：

```yaml
flow:
  - stage: "fix"
    agent: "fixer"
    output: ".df/report.json"
  - loop: "retry_until_pass"
    body: ["fix"]
    until: "contains(file(\".df/report.json\"), \"\\\"pass_rate\\\": 1.0\")"
    max_iterations: 3
```

- `body`：已声明 stage 组成的子图，整段重跑。
- `until` 白名单函数：`file("相对产物路径")`（读 work_dir 内产物正文）、`contains(text, substr)`。
- `max_iterations`：上限，达到即停。

### 五、`gate` 门禁与人工审批

`gate: true` 的阶段完成后会**停住**，默认 `approve=false`，必须人工确认才放行。这实现了"不完全无人值守"：全自动段可无人值守，关键关口保留人工审批。

在 Web 界面的「编排查看」中，门禁停住时会弹出审批浮层，提供**放行 / 拒绝 / 重试**三个操作，并可填写备注；审批记录会写入日志。

### 六、编排文件两种后缀

| 后缀 | 语义 |
| --- | --- |
| `.yaml` / `.yml` | **组织的编排**：声明一组 Agent，用于批量创建；可含 `flow` 走流水线 |
| `.flow` | **流程的编排**：用 Python DSL 声明 DAG 结构（脚本只声明结构、不产生副作用），适合"按数据动态生成阶段"等 YAML 表达不了的场景 |

`.flow` 脚本用 DSL 构造器声明，执行后产出与 YAML 同构的 DAG 数据，引擎行为完全一致。示例：

```python
from jarvis.jarvis_tools.orchestration_dsl import Pipeline, stage

p = Pipeline()
p.add(stage("planner", agent="demo_planner", output=".df/plan.md"))
p.add(stage("worker_a", agent="demo_worker_a",
            depends_on=["planner"], input=".df/plan.md", output=".df/a.md"))
p.agent("demo_planner", working_dir=".", task="你是规划器……")
```

> 详细设计见 `docs/design/orchestration-python-dsl.md`。

## 你会看到的提示与反馈

- **预览**：静态 DAG 图（各阶段与依赖关系），不创建 Agent。
- **运行中**：各阶段状态实时更新（pending / running / done / failed / skipped），可看到并行批次。
- **门禁停住**：审批浮层出现，需你选择放行 / 拒绝 / 重试。
- **产物**：各阶段产物写入 `working_dir` 下的 `.jarvis/artifacts/<pipeline_id>/`（示例里用 `.df/` 只是示例路径）。

## 注意事项

- 引擎**只协调不执行**：每个阶段具体做什么由该阶段 Agent 的 `task` 决定，引擎不写码。
- `output` 路径必须全局唯一，重复会报错。
- `depends_on` 缺省是"上一个 stage"（线性）；要并行必须显式声明依赖。
- 有环的 `flow` 会被拓扑排序直接拒绝报错。
- 阶段 Agent 是常驻 `jvs` Agent，创建后引擎会等其网关就绪再派发任务；就绪超时（约 60 秒）会报错。
- 编排文件示例均可运行，路径以仓库实际文件为准（`builtin/agent_orchestration/`、`builtin/plugins/ai-dark-factory/orchestration/`）。

## 下一步

- 想看一个真实的多阶段流水线（含门禁）？参考 `builtin/plugins/ai-dark-factory/orchestration/dark_factory_pipeline.yaml`。
- 想让多个 Agent 互相发消息协作（而非按 DAG 编排）？见 [协作模式最佳实践](协作模式最佳实践.md)。
