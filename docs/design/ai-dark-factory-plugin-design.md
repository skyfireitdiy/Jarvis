# AI Agent 黑灯工厂插件实施设计方案

> 设计日期：2026-10-06
> 依据：`docs/design/ai-dark-factory-research.md`（调研报告）
> 管理员决策：按最优效果实施，**可以不完全无人值守**（纯无人值守易出问题，门禁处保留人工审批关口）。

## 1. 插件定位

**AI Dark Factory** 是一种软件交付模型：AI Agent 自主编写、测试、评估代码（"关灯运行"），人类工程师定义规格（spec）、审查 pass/fail 报告、控制信任边界。**Specs 进，可工作的软件出**。

本插件把 Jarvis 变成一台 AI 黑灯工厂：给定一份 NLSpec（自然语言规格），系统编排多 Agent 完成"规划 → 生成 → 验证 → 门禁 → 交付"，人类仅在审批关口介入，不逐行写码、不逐行审码。

**关键设计取向（管理员决策）**：不追求全自动 auto-merge 的完全无人值守，而是在**评估门禁处保留人工审批关口**——orchestrator 汇总各验证器的 pass/fail 报告，交人类审批通过后才进入交付/合并。这既符合黑灯工厂"人类只审 pass/fail 报告"的原则，又避免纯无人值守的失控风险。

## 2. 插件目录结构

```text
builtin/plugins/ai-dark-factory/
├── config.yaml                     # 插件元数据 + 加载目录（{{plugin_dir}} 模板变量）
├── rules/                          # 方法论规则（.md，带 YAML front matter）
│   ├── spec_writing.md             # NLSpec 编写规范
│   ├── holdout_discipline.md       # 验收场景隔离纪律
│   ├── tdd_iron_rule.md            # TDD 铁律
│   └── orchestration.md            # 编排纪律 + 人工审批关口
├── tools/                          # 工具（.py，class XxxTool）
│   ├── spec_validator.py           # 校验 NLSpec 完整性
│   ├── holdout_generator.py        # 生成 holdout scenarios
│   ├── gate_calculator.py          # 评估门禁计算
│   └── pipeline_generator.py       # 生成编排 YAML
└── orchestration/
    └── dark_factory_pipeline.yaml  # 预置多 Agent 流水线编排模板
```

## 3. config.yaml 设计

```yaml
name: ai-dark-factory
description: AI Agent 黑灯工厂——Specs 进，可工作的软件出。编排多 Agent 自主写码/测试/评估，人类审 pass/fail 报告控制信任边界。
version: 0.1.0
license: MIT
rules_load_dirs:
  - "{{plugin_dir}}/rules"
tool_load_dirs:
  - "{{plugin_dir}}/tools"
```

- `name`：`ai-dark-factory`（与已删除的工业版 `dark-factory` 区分）
- `rules_load_dirs` / `tool_load_dirs`：用 `{{plugin_dir}}` 模板变量指向插件内目录，安装后自动渲染为插件实际路径。
- 插件安装到 `~/.jarvis/plugins/ai-dark-factory/` 后，启动时自动发现并合并进全局配置。

## 4. 规则文件清单（rules/）

| 文件                    | 作用             | 关键内容                                                                                                                          |
| ----------------------- | ---------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `spec_writing.md`       | NLSpec 编写规范  | Goal / Constraints / Interfaces / Non-goals 四要素；约束必须显式；一个功能一个 spec；巨型 spec 压垮上下文                         |
| `holdout_discipline.md` | 验收场景隔离纪律 | 编码 agent **永远看不到** holdout scenarios；train/test 分离防作弊；由独立评估器用隐藏场景测试                                    |
| `tdd_iron_rule.md`      | TDD 铁律         | 无失败测试不写代码；先写测试再实现                                                                                                |
| `orchestration.md`      | 编排纪律         | sw-controller 只协调不执行；四层架构（Orchestrator/Planner/Generators/Validators）；**人工审批关口**——门禁处人类审 pass/fail 报告 |

每个规则文件带 YAML front matter（`name` / `description` / `license`）。

## 5. 工具清单（tools/）

| 工具类                  | 功能                   | 输入 → 输出                                                                 |
| ----------------------- | ---------------------- | --------------------------------------------------------------------------- |
| `SpecValidatorTool`     | 校验 NLSpec 完整性     | 规格文本 → 是否含 Goal/Constraints/Interfaces/Non-goals 四要素 + 缺失项提示 |
| `HoldoutGeneratorTool`  | 生成 holdout scenarios | 功能描述 + 数量 → 隐藏验收场景列表（标记为编码侧不可见）                    |
| `GateCalculatorTool`    | 评估门禁计算           | 各场景 pass/fail → 场景通过率、假阳性率、人类推翻率 + 是否达标（≥90%）      |
| `PipelineGeneratorTool` | 生成编排 YAML          | 功能描述 → sw-controller 风格多 Agent 流水线编排 YAML                       |

每个工具类实现 `name` / `description` / `parameters` / `check` / `execute` 接口（参考 `src/jarvis/jarvis_tools/read_symbols.py`）。

## 6. 编排模板设计（orchestration/dark_factory_pipeline.yaml）

复用 Jarvis 的 `@OrganizeAgents` + YAML 编排文件机制（格式参考 `builtin/agent_orchestration/self_evolving_network.yaml`），预置一份流水线编排模板，体现四层架构：

```text
planner（规划器）—— 读 spec，拆解任务、生成实现计划
  → generators（生成器）—— 从 spec 写代码（TDD：先写测试）
  → validators（验证器）—— 用 holdout scenarios 跑测试、评估
  → orchestrator（编排器）—— 汇总 pass/fail 报告 → 人工审批关口
```

编排模板中每个 agent 以 `task` 字段注入职责描述。**刻意不设 `no_interaction_mode`**：本插件坚持"不完全无人值守"，每个阶段（规划/生成/验证/门禁）都保留人工介入关口，门禁决策 agent 输出 pass/fail 报告后停住，等待人工审批，不自动合并。这是管理员特意设计，不是实现缺口。

## 7. "不完全无人值守"的人工审批关口设计

这是本方案的核心设计取向，与纯黑灯工厂（全自动 auto-merge）的关键区别，**也是管理员特意设计、刻意为之**：本插件默认不在编排 agent 上启用 `no_interaction_mode`，坚持"人类审 pass/fail 报告、控制信任边界"，绝不纯无人值守。

1. **全自动段**：从 spec 到生成器写码、验证器跑 holdout scenarios，全程 AI 自主。Jarvis 底层能力支持无人值守（`no_interaction_mode` + `jca -n --task-file` + `status_file`），但**本插件默认不启用**，各阶段均保留人工介入关口。
2. **人工审批关口**：验证器产出 pass/fail 报告后，**编排器不自动合并**，而是输出结构化审批报告（各场景通过率、失败场景详情、改动 diff 摘要），交人类审批。
3. **审批通过后**：人类确认后进入交付/合并阶段（可再次自动化）。
4. **门禁标准**：参考调研报告——场景通过率 ≥90% 才建议通过；假阳性率 <5%、人类推翻率 <10% 时才考虑放宽为自动。

这样既保留了黑灯工厂"人类只审 pass/fail 报告、不逐行审码"的效率，又通过人工审批关口控制信任边界，避免纯无人值守的失控风险。

## 8. 复用的 Jarvis 机制（均已核实存在）

| 机制                              | 对应黑灯工厂层          | 位置                                      |
| --------------------------------- | ----------------------- | ----------------------------------------- |
| `@OrganizeAgents` + YAML 编排文件 | Orchestrator / Planner  | `builtin/agent_orchestration/` 有格式示例 |
| 多 Agent 协作 / 通信 / 子代理     | Generators / Validators | 内置                                      |
| `no_interaction_mode` 编排字段    | 无人值守执行            | 编排文件字段                              |
| `jca -n --task-file`              | 非交互流水线入口        | `jarvis.py:819`                           |
| `status_file` 机制                | 自动门禁状态回传        | `jarvis.py:1053`                          |
| 三层规则系统 + AGENTS.md 兼容     | Agent 上下文            | 内置                                      |

> 注：调研报告中提到的 SDK（`pipeline` / `run_agents_parallel` / `run_structured`）经核实**当前代码中不存在**，本方案不依赖它们，仅使用上述已验证机制。

## 9. 实施步骤

1. 创建 `builtin/plugins/ai-dark-factory/` 目录结构与 `config.yaml`（yamllint 校验）
2. 编写 4 个规则文件（markdownlint 校验）
3. 编写 4 个工具文件（实测通过）
4. 编写编排模板 `dark_factory_pipeline.yaml`（yamllint 校验）
5. 验证：`jarvis --install-plugin builtin/plugins/ai-dark-factory` 安装成功 + `jarvis --list-plugins` 识别
6. git 提交插件源码

## 10. 验证方式

- **config.yaml / 编排 YAML**：yamllint 通过
- **规则 .md**：markdownlint 通过
- **工具 .py**：合法输入返回正确结果、非法输入返回错误
- **插件安装**：`jarvis --install-plugin` 成功、`jarvis --list-plugins` 能列出 `ai-dark-factory`
