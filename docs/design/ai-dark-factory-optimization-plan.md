# AI 黑灯工厂插件优化方案：对齐最新编排引擎 + 补全研发流程

> 状态：**已评审，实施中**
> 目标：让黑灯工厂插件（`builtin/plugins/ai-dark-factory/`）充分利用最新 `pipeline_runner` 编排引擎能力，并补全研发流程的薄弱环节。
> 依据：对插件现状（规则/工具/编排模板/config）与 `pipeline_runner` 最新能力的交叉分析。
> 相关：`docs/design/ai-dark-factory-orchestration-engine.md`（编排引擎设计）、`docs/design/orchestration-python-dsl.md`（.flow DSL）。

---

## 0. 背景

黑灯工厂插件已接入 `pipeline_runner` 编排引擎，四层流水线（planner → generator → validator → orchestrator 门禁）方向正确。但自插件设计以来，编排引擎已新增多项能力（loop 运行时循环原语、DAG 并行、when 条件分支、retry/on_error、spec 顶层字段注入、门禁审批增强），而插件的**编排模板**与**规则文档**仍停留在引擎最基础的线性能力上。

同时，审视整个研发流程后发现若干**流程完备性缺口**：holdout 场景的生成环节缺失、隔离机制薄弱、validator 多次采样未用引擎原语、门禁历史指标无处持久化等。

本方案分两部分：

- **A. 能力对齐**：让编排模板与规则文档展示并使用最新引擎能力。
- **B. 流程补全**：补全研发流程的薄弱环节。

---

## 1. 现状梳理

### 1.1 插件构成

| 类别 | 文件 | 作用 |
|---|---|---|
| 配置 | `config.yaml` | 插件元信息、规则/工具加载目录、编排入口、三种 replace_map 入口（run/issue/pr） |
| 规则 | `rules/spec_writing.md` | NLSpec 四要素编写规范 |
| 规则 | `rules/tdd_iron_rule.md` | TDD 铁律（无失败测试不写代码） |
| 规则 | `rules/holdout_discipline.md` | 验收场景隔离纪律 |
| 规则 | `rules/orchestration.md` | 编排纪律（sw-controller、四层架构、人工审批关口） |
| 工具 | `tools/spec_validator.py` | 校验 NLSpec 是否含四要素 |
| 工具 | `tools/holdout_generator.py` | 生成 holdout scenarios（编码侧不可见） |
| 工具 | `tools/gate_calculator.py` | 计算门禁指标（通过率/假阳性率/人类推翻率） |
| 编排 | `orchestration/dark_factory_pipeline.yaml` | 四层流水线参考模板（agents + flow） |

### 1.2 研发流程（现状）

```text
需求输入(Issue/PR/run)
  → ① NLSpec 编写（spec_writing 规则 + spec_validator 工具）
  → ② 编排文件动态生成（agents + flow，用户确认）
  → ③ pipeline_runner 驱动四层流水线
        planner → generator(TDD) → validator → orchestrator(gate)
  → ④ 门禁计算（gate_calculator）→ 人工审批
  → ⑤ 交付/合并
```

### 1.3 最新编排引擎能力（`pipeline_runner`）

| 能力 | 说明 |
|---|---|
| **loop 运行时循环原语** | `loop(name, body, until, max_iterations)`：body 为已声明 stage 组成的子图，整段重跑直到 `until` 满足或达上限；`until` 支持白名单函数 `file(path)`（读 work_dir 内产物正文）与 `contains(text, substr)` |
| **DAG 并行** | `depends_on` 显式声明依赖；`input` 支持多输入列表；`max_workers` 默认 4 并行 |
| **when 条件分支** | `stage.field` 引用上游 status_file/产物 JSON 字段，支持 `== != >= <= > < && \|\| !` |
| **retry / on_error** | `retry` 失败重试次数；`on_error: abort/continue/skip_dependents` 失败策略；顶层 `default_on_error` |
| **spec 顶层字段注入** | 编排文件顶层 `spec` 字段作为各阶段背景注入（可选） |
| **门禁审批增强** | `gate: true` 停住，前端审批浮层 approve/reject/retry，后端 `record_approval` 审计 |
| **预览** | 前端「预览」按钮不执行只绘制静态 DAG |

---

## 2. 流程完备性缺口（审视结论）

| 编号 | 缺口 | 现状 | 影响 |
|---|---|---|---|
| **G1** | holdout 生成环节缺失 | 编排模板中 validator 声称"持有 holdout scenarios"，但流程中**无任何环节调用 `holdout_generator` 生成场景**，也未定义 holdout 产物路径 | 隔离评估的"隐藏场景"实际没有可靠来源，validator 无场景可测 |
| **G2** | holdout 隔离机制薄弱 | generator 与 validator 共享 `.df/` 产物目录，无机制保证 holdout 文件不被 generator 看到 | 违反 holdout_discipline 的"编码 agent 永远看不到验收场景" |
| **G3** | validator 多次采样未用引擎原语 | holdout_discipline 要求"每场景跑 3 次，2-of-3 通过"，但靠 validator agent 自行实现 | 不可靠、不可观测；引擎已有 loop 原语可表达 |
| **G4** | 门禁历史指标无持久化 | `gate_calculator` 需要 `false_positives`/`human_overrides`/`total_human_reviews`（跨任务累计），流程中无处持久化这些历史数据 | 假阳性率/人类推翻率指标无法真实计算，门禁决策依据不全 |
| **G5** | 无回归验证环节 | holdout_generator 有"与既有模块兼容性"模板，但流程没有明确跑既有测试套件防回归的阶段 | 改动可能引入回归却无检查 |
| **G6** | spec→holdout 一致性无校验 | holdout 应源自 spec，但无环节保证二者一致 | holdout 可能与 spec 脱节，评估失真 |
| **G7** | 编排模板未展示最新引擎能力 | 模板只用线性 flow，未展示 loop/DAG/when/retry | 动态生成编排文件的 agent 不知道引擎能力边界，无法产出更优编排 |

---

## 3. 方案

### 3.1 A 部分：能力对齐（G7）

#### A1. 编排模板补充能力示例与说明

在 `orchestration/dark_factory_pipeline.yaml` 中：

- 保留四层线性流水线作为**默认参考**（向后兼容，仍可直接跑）。
- 在注释区补充 loop/DAG/when/retry 的能力说明与**可复制示例**（如 validator 3 次采样用 loop 表达）。
- 明确标注"编排文件是动态生成的，模板仅展示格式与能力"。

#### A2. orchestration.md 规则补充引擎能力说明

在 `rules/orchestration.md` 中新增「编排引擎能力清单」小节，列出 loop/DAG 并行/when/retry/on_error 的语义与适用场景，让动态生成编排文件的 agent 知道可用原语。

### 3.2 B 部分：流程补全（G1–G6）

#### B1. 补全 holdout 生成环节（G1 + G2 + G6）

在编排模板的 flow 中，于 planner 之后、generator 之前插入一个 **`holdout` 阶段**：

- 该阶段由**独立 agent**（`df_holdout`）执行，职责：读取 NLSpec，用 `holdout_generator` 工具生成隐藏验收场景，落盘到 `.df/holdout.json`。
- **隔离**：`.df/holdout.json` 只作为 validator 的 input，**不注入 generator**；generator 的 input 只有 `.df/plan.md`。
- **一致性**：holdout 阶段的任务描述要求"场景必须源自 spec 的 Goal/Interfaces，逐条对应"，由该 agent 保证一致性。

> 说明：`holdout_generator` 当前是模板化生成器（8 个固定模板循环），生成的是**场景骨架**。holdout agent 需在此基础上结合 spec 细化，产出真正针对该功能的验收场景。方案不改工具本身（保持最小改动），而是通过 agent 职责与规则约束保证质量。

#### B2. validator 用 loop 原语表达多次采样（G3）

在编排模板中，将 validator 拆为 loop 表达：

```yaml
flow:
  - stage: "holdout"
    agent: "df_holdout"
    input: ".df/plan.md"
    output: ".df/holdout.json"     # 编码侧不可见，仅传 validator
  - stage: "validator"
    agent: "df_validator"
    input: ".df/holdout.json"      # 只吃 holdout，不吃 plan（隔离）
    output: ".df/report.json"
    retry: 2                        # 失败重试，配合 2-of-3 语义
```

> 注：loop 原语适合"整段重跑直到 until 满足"，而"每场景跑 3 次取 2-of-3"是**场景内**多次采样，语义上更适合由 validator agent 内部按 holdout_discipline 执行 + `retry` 兜底。方案采用 `retry` 表达重试，并在规则中明确 2-of-3 由 validator 内部实现。**不强行套用 loop**（避免语义错配）。

#### B3. 门禁历史指标持久化（G4）

在流程中约定一个**跨任务的指标台账**文件（如 `.df/gate_metrics.json`）：

- orchestrator 阶段读取历史台账，把累计的 `false_positives`/`human_overrides`/`total_human_reviews` 传给 `gate_calculator`。
- 人工审批后，把本次结果追加回台账。
- 在 orchestration.md 规则中说明台账位置与字段。

> 说明：本项为**流程约定**（由 agent 按规则执行），不改引擎与工具代码，保持最小改动。

#### B4. 补全回归验证环节（G5）

在编排模板的 flow 中，于 validator 之后、orchestrator 之前插入 **`regression` 阶段**：

- 职责：跑既有测试套件（如 `pytest`/项目测试命令），确认无回归。
- 产物：`.df/regression.json`（通过/失败）。
- 该阶段失败时 `on_error: abort`（回归失败即中止，交人工）。

#### B5. 更新规则文档

- `orchestration.md`：补充 holdout 生成环节、隔离约定、门禁台账、回归环节的说明。
- `holdout_discipline.md`：补充"由独立 holdout agent 生成、落盘 `.df/holdout.json`、只传 validator"的具体落地方式。

### 3.3 清理残留

`builtin/plugins-ext/ai-dark-factory/` 目录**只有 `__pycache__` 残留，无任何实际文件**，全仓代码无引用（插件只从 `builtin/plugins/` 与 `data_dir/plugins/` 加载）。**删除该残留目录**。

---

## 4. 实施步骤

1. **清理残留**：删除 `builtin/plugins-ext/ai-dark-factory/`。
2. **编排模板**：更新 `orchestration/dark_factory_pipeline.yaml`，新增 holdout/regression 阶段、补全能力说明注释。
3. **规则文档**：更新 `orchestration.md`、`holdout_discipline.md`。
4. **验证**：跑 `tests/jarvis_plugins/test_ai_dark_factory.py`；用 `pipeline_runner` 的 dry-run 校验新编排模板可解析（无环、agent 引用有效、产物唯一）。

---

## 5. 风险与权衡

| 风险 | 缓解 |
|---|---|
| 编排模板改动破坏现有可用性 | 保留原四层流水线为核心，新增阶段为可选参考；dry-run 校验 |
| holdout_generator 是模板化生成器，质量有限 | 通过 holdout agent 职责 + 规则约束细化；不改工具（最小改动） |
| 新增阶段增加流水线耗时 | holdout/regression 阶段轻量；可 `when` 条件跳过 |
| 门禁台账为流程约定，agent 可能不遵守 | 规则文档明确要求；后续可考虑工具化（本次不做） |

---

## 6. 不做的部分（明确边界）

- **不改 `pipeline_runner` 引擎代码**：引擎能力已足够，本方案只在插件侧对齐。
- **不改三个工具（spec_validator/holdout_generator/gate_calculator）的代码**：保持最小改动，通过规则与流程约定落地。
- **不引入外部编排框架**：与 `docs/research/agent-tech-report-2026q3.md` 结论一致，自研引擎方向正确。

---

## 7. 验证标准

1. `builtin/plugins-ext/ai-dark-factory/` 已删除。
2. `dark_factory_pipeline.yaml` 含 holdout/regression 阶段，且 `pipeline_runner` dry-run 解析通过（无环、agent 引用有效、产物唯一）。
3. `orchestration.md`/`holdout_discipline.md` 已补充新环节说明。
4. `tests/jarvis_plugins/test_ai_dark_factory.py` 全部通过。
