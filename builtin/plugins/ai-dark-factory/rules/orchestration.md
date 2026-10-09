---
name: orchestration
description: AI Agent 黑灯工厂的编排纪律。当需要编排多 Agent 流水线（planner/generator/validator/orchestrator）时触发。要求 sw-controller 只协调不执行，四层架构清晰，门禁处保留人工审批关口。
---

# 编排纪律（Orchestration Discipline）

## 核心原则

黑灯工厂的编排遵循 **sw-controller 模式**：总控 agent **只协调，不执行**。编排器是流水线的神经系统，负责调度生成器、调度验证器、执行门禁，而非亲自写码或测试。

关键洞察：**先设计编排逻辑，再关注单个 agent**。一个强生成 agent 配弱编排器会表现不佳；一个简单生成 agent 配设计良好的编排器反而会胜出。

## 四层架构

```text
┌─────────────────────────────────────────────┐
│  Orchestrator（编排器）—— 流水线的神经系统   │
│  读取 spec → 调度生成器 → 调度验证器 → 门禁   │
├─────────────────────────────────────────────┤
│  Planner（规划器）—— 拆解任务、生成计划       │
├─────────────────────────────────────────────┤
│  Holdout（场景生成器）—— 生成隐藏验收场景     │
├─────────────────────────────────────────────┤
│  Generators（生成器）—— 从 spec 写代码       │
├─────────────────────────────────────────────┤
│  Validators（验证器）—— 跑 holdout、评估产出  │
├─────────────────────────────────────────────┤
│  Regression（回归器）—— 跑既有测试防回归      │
└─────────────────────────────────────────────┘
```

## 编排纪律

1. **只协调不执行**：总控 agent 不亲自写码、不亲自测试，只负责调度与门禁。
2. **职责单一**：planner 只规划，holdout 只生成场景，generator 只生成，validator 只评估，regression 只跑回归，互不越界。
3. **阶段推进**：严格按 规划 → 场景生成 → 生成 → 验证 → 回归 → 门禁 顺序推进，不跳阶段。
4. **上下文注入**：每个 agent 通过 `task` 字段注入职责描述，通过规则系统注入方法论。

## 人工审批关口（不完全无人值守）

本插件采用"不完全无人值守"设计，与纯黑灯工厂（全自动 auto-merge）的关键区别：

1. **全自动段**：从 spec 到生成器写码、验证器跑 holdout scenarios，全程 AI 自主，可无人值守。
2. **人工审批关口**：验证器产出 pass/fail 报告后，**编排器不自动合并**，而是输出结构化审批报告（各场景通过率、失败场景详情、改动 diff 摘要），交人类审批。
3. **审批通过后**：人类确认后进入交付/合并阶段。
4. **门禁标准**：场景通过率 ≥90% 才建议通过；假阳性率 <5%、人类推翻率 <10% 时才考虑放宽为自动。

这样既保留黑灯工厂"人类只审 pass/fail 报告、不逐行审码"的效率，又通过人工审批关口控制信任边界，避免纯无人值守的失控风险。

## 编排文件：动态生成的结构化 plan

编排文件（含 `agents` 与 `flow`）是**每次任务动态生成的结构化 plan**，由编排 agent 根据 spec、代码库现状与用户讨论共同产出，用户确认后再执行。插件自带的 `orchestration/dark_factory_pipeline.yaml` 仅作为**参考模板**（展示四层架构与 flow 格式），不直接用于每次任务。

编排文件生成要点：

1. **agents**：按架构定义 planner / holdout / generator / validator / regression / orchestrator 的角色描述（`task`）。
2. **flow**：声明阶段顺序与产物契约（`stage`/`agent`/`input`/`output`/`gate`）。
3. **适配已有代码库**：generator 阶段**无独立代码目录产物**——直接在 `working_dir`（已有代码库）中修改现有代码；validator 验证修改后的工作目录。
4. **门禁**：orchestrator 阶段设 `gate: true`，停住等人工审批。
5. 生成后落盘到 `.df/pipeline.yaml`，**用户确认无误后再执行**。

### holdout 场景生成与隔离

- **生成环节**：flow 中在 planner 之后、generator 之前设 **`holdout` 阶段**，由独立 agent（`df_holdout`）读取 NLSpec，用 `holdout_generator` 工具生成场景骨架，再结合 spec 的 Goal/Interfaces 细化为验收场景，落盘 `.df/holdout.json`（标记 `hidden=true`）。
- **隔离**：`.df/holdout.json` **只作为 validator 的 `input`，绝不注入 generator**（generator 的 `input` 只有 `.df/plan.md`）。这是 holdout_discipline 的硬性要求。
- **一致性**：场景必须源自 spec——每条场景对应 spec 的一个 Goal 或 Interface 契约。

### 回归验证环节

- flow 中在 validator 之后、orchestrator 之前设 **`regression` 阶段**，由独立 agent（`df_regression`）跑项目既有测试套件，产物 `.df/regression.json`。
- 该阶段 `on_error: abort`：回归失败即中止，交人工。

### 门禁历史指标台账

- `gate_calculator` 的假阳性率/人类推翻率需**跨任务累计**。约定台账文件 `.df/gate_metrics.json`：
  - orchestrator 阶段读取台账，把累计的 `false_positives`/`human_overrides`/`total_human_reviews` 与本次结果一起交给 `gate_calculator`。
  - 人工审批后，把本次结果追加回台账。
- 台账不存在时按首次任务处理（各项为 0）。

## 编排引擎能力清单（pipeline_runner）

动态生成编排文件时，可选用以下引擎能力（字段全部可选，缺省即线性行为）：

| 能力 | 字段/语法 | 适用场景 |
|---|---|---|
| 线性/DAG | `depends_on`（缺省=上一 stage）；`input` 支持列表多输入 | 阶段依赖、并行分支 |
| 并行 | 顶层 `max_workers`（默认 4） | 多个独立阶段（如多 generator）并行 |
| 条件分支 | `when`（`stage.field` 比较/逻辑，`== != >= <= > < && \|\| !`） | 按上游结果跳过/执行阶段 |
| 失败重试 | `retry`（整数） | 易抖动阶段兜底 |
| 失败策略 | `on_error: abort/continue/skip_dependents`；顶层 `default_on_error` | 控制失败传播 |
| 门禁 | `gate: true` | 人工审批关口 |
| 背景注入 | 顶层 `spec` 字段（或 `spec_file` 参数） | 给所有阶段注入 spec 背景 |
| 运行时循环 | `loop(name, body, until, max_iterations)`：body 为已声明 stage 组成的子图，整段重跑直到 `until` 满足或达上限；`until` 支持 `file("相对路径")`、`contains(text, substr)` | "重跑直到达标"（如修复→重验循环） |

> 注意：`loop` 适合"整段重跑直到达标"，而 holdout 的"每场景跑 3 次取 2-of-3"是**场景内**多次采样，由 validator agent 内部按 holdout_discipline 执行，配合 `retry` 兜底，**不强行套用 loop**。

## 用内置编排引擎执行（pipeline_runner）

编排文件确认后，用内置编排引擎 `pipeline_runner` 工具**自动按序驱动**四层流水线：

1. **触发**：用户输入 `<dark-factory/run>`，或主 agent 直接调用 `pipeline_runner` 工具。
2. **驱动方式**：`pipeline_runner` 按 `flow` 顺序，用 `jca -n --task-file` 逐个启动阶段 agent，poll `status_file` 同步等待完成，校验产物落盘后传入下一阶段。
3. **产物契约**：planner → `.df/plan.md`（实现计划）；holdout → `.df/holdout.json`（隐藏验收场景，仅传 validator）；generator → **无独立代码目录**，直接在已有代码库中修改（产物为代码库改动，git diff 可查）；validator → `.df/report.json`（pass/fail 报告）；regression → `.df/regression.json`（回归结果）；orchestrator → `.df/approval.md`（审批报告）。
4. **门禁停住**：orchestrator 阶段（`gate: true`）产出审批报告后，引擎**停住**，默认 `approve=false`，等人工审批通过后以 `approve=true` 重跑门禁确认才放行。

- 编排引擎**只协调不执行**：不写码、不测试，只负责按序调度与产物传递。
- `flow` 为可选字段：无 `flow` 时 `@OrganizeAgents` 仍只创建 agent（向后兼容）。

## 常见陷阱

- **编排器越界执行**：总控亲自写码，失去调度纪律。
- **职责混乱**：生成器兼做验证，评估失去独立性。
- **跳过门禁**：不评估直接交付，信任边界失控。
- **过早全自动**：未积累足够评估器与人类判断一致的证据就启用自动合并。
