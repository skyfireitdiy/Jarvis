# AI Agent 黑灯工厂（AI Dark Factory）调研报告

> 调研日期：2026-10-06
> 背景：管理员纠正方向——要的是「Agent 黑灯工厂」而非工业黑灯工厂。本报告调研 AI Agent 黑灯工厂的概念、架构与落地方式，为 Jarvis 版黑灯工厂插件设计提供依据。

## 1. 什么是 AI Agent 黑灯工厂

**AI Dark Factory** 是一种**软件交付模型**：AI Agent 自主编写、测试、发布代码（"关灯运行"）。人类工程师定义规格（spec）、审查输出、控制信任边界。**Specs 进，可工作的软件出**——没有人类写代码，也没有人类逐行审查代码。

名称借自制造业的"黑灯工厂"（lights-out factory，无人值守的全自动工厂）。AI 黑灯工厂追求同样的境界：给定一份良好定义的规格，系统能自主完成生产、测试、审查并交付完整软件模块，人类仅在审批关口（approval gates）介入，而非逐行编码。

**来源**：由 Dan Shapiro（Glowforge）于 2026 年 1 月提出，是 AI 驱动开发成熟度的 **Level 5 终点**。

## 2. AI 驱动开发的六级框架

| 等级 | 名称         | 你在做什么         | 关键解锁                  |
| ---- | ------------ | ------------------ | ------------------------- |
| L0   | 手动         | 手写每个字符       | —                         |
| L1   | 任务委派     | 交接独立任务       | 学会写好 prompt           |
| L2   | 协作         | 与 AI 结对编程     | AGENTS.md + 结构化上下文  |
| L3   | 人审循环     | 审 diff 而非写代码 | Specs + holdout scenarios |
| L4   | Spec 驱动    | 写规格、验证结果   | 自动化评估 + 自动合并     |
| L5   | **黑灯工厂** | 设计系统而非功能   | 数字孪生 + 全流水线       |

大多数开发者停留在 L2（结对编程）。研究显示（METR 2025 随机试验）L2 的开发者反而慢 19%，因为他们审查每个 diff。跨越 L2 需要写结构化 spec 并放弃逐行代码审查。

## 3. 核心三要素（缺一不可）

真正的黑灯工厂必须同时具备以下三条，否则退化为"带自动化增强的 agentic coding"：

1. **Spec 驱动输入**：以 NLSpec（自然语言规格）为输入。NLSpec 是带形式化约束的结构化英文——精确到 agent 无法用判断填补空白。典型结构：Goal / Constraints / Interfaces / Non-goals。

2. **隔离的评估器 + holdout scenarios**：编码 agent **永远看不到**验收场景（holdout scenarios）。由独立的评估器 agent 用这些隐藏场景测试产出代码。这是 train/test 分离——防止推理模型"过拟合"到它见过的规格上（研究证实，推理模型会针对它们能看到的规格作弊，即使有明确反指令）。

3. **零人工 diff 审查**：人类不逐行审查代码，只审查评估器的 **pass/fail 报告**。质量门禁从"人工 code review"变成"自动化场景评估"。

## 4. 四层核心架构

```text
┌─────────────────────────────────────────────┐
│  Orchestrator（编排器）—— 流水线的神经系统   │
│  读取 spec → 调度生成器 → 调度验证器 → 门禁   │
├─────────────────────────────────────────────┤
│  Planner（规划器）—— 拆解任务、生成计划       │
├─────────────────────────────────────────────┤
│  Generators（生成器）—— 从 spec 写代码       │
├─────────────────────────────────────────────┤
│  Validators（验证器）—— 跑测试、评估场景      │
└─────────────────────────────────────────────┘
```

关键洞察：**先设计编排逻辑，再关注单个 agent**。一个强生成 agent 配弱编排器会表现不佳；一个简单生成 agent 配设计良好的编排器反而会胜出。编排器是流水线的"神经系统"，不是事后补充。

## 5. 关键概念

- **NLSpec（自然语言规格）**：结构化英文，含 Goal / Constraints / Interfaces / Non-goals。约束必须显式，agent 不能靠判断填补空白。
- **Holdout scenarios（保留验收场景）**：用纯英文写的验收测试，编码 agent 永远看不到。评估器 agent 用它测产出代码。每个场景跑 3 次，2-of-3 通过以平滑 LLM 方差。
- **Auto-merge 门禁**：≥90% 场景通过才允许自动合并；<90% 则重试。不要过早启用——先收集 20-30 个 PR 对比评估器判断与人类判断，满足（场景通过率 ≥90%、假阳性率 <5%、人类推翻率 <10%）才启用。
- **AGENTS.md**：给 agent 的项目结构化上下文（构建步骤、约定、架构规则）。开放标准，60,000+ 项目使用。是每一级的地基。
- **Digital twins（数字孪生）**：外部服务（Stripe/Okta/数据库）的高保真行为克隆。让 agent 在完全隔离中测试——毫秒级运行、无 API key、可注入故障、确定性。AI 让构建数字孪生变得经济可行。
- **Ephemeral environment（临时环境）**：PR 以容器修订版部署，评估器在其中测试。

## 6. 完整流水线（Level 5）

```text
Issue Tracker → Coding Agent → Ephemeral Env → Evaluator Agent → Auto-Merge Gate → 生产部署
(Jira/Linear/GitHub Issues)  (读 AGENTS.md+spec    (PR 部署为容器    (跑 holdout     (≥90% 通过→合并   (标准 CI/CD
                             →实现→测试)          修订版)            scenarios 3x)   <90%→重试)         不变)
                                                                                          ↑
                                                    Monitoring（告警成为下一轮 bug spec）——反馈环
```

## 7. 参考实现

### 7.1 GitHub wenxueliu/darkfactory（最直接参考）

**人机协同软件生成系统**：协调多个专业化 AI Agent 组成流水线，从需求到交付端到端自动化。遵循**验收驱动开发**和 **TDD 铁律**（无失败测试不写代码）。32 个 skills 覆盖完整 E2E 流水线。

Agent 架构（v2）：

```text
sw-controller（总控：Intent Gate + Phase Transition + 委派纪律 — 只协调，不执行）
  ├── [需求层] sw-requirements-clarifier / sw-value-judgment
  ├── [规划层] sw-strategic-planner（+ pre-planning-consultant / plan-reviewer / codebase-explorer / external-researcher）
  ├── [设计层] sw-brainstorming / sw-feature-designer → sw-service-designer × N → sw-e2e-designer
  ├── [拆分层] sw-task-decomposer
  ├── [执行层] sw-plan-executor → sw-worktree-controller × N → sw-tdd-agent（+ reviewer-logic/security/performance/context）
  ├── [测试层] sw-integration-tester
  ├── [交付层] sw-delivery-manager
  └── [基础设施] sw-setup / sw-knowledge-agent / sw-systematic-debugging / sw-verification-before-completion / ...
```

配置项：`architecture`（monolith/microservices）、`business_domain`（general/fintech/ecommerce/internal-tools）、`min_iteration_before_human`（AI 自主迭代几次后升级到人工）、`enabled_reviewers`（security,logic,performance）、`merge_strategy`。

### 7.2 bborbe/agent 的 Dark Factory CI/CD pipeline

自动化实现流水线，用于演化 agent 代码库。架构变更定义为 spec，人类批准后由 Claude Code 在临时容器中实现。README 62-71 行描述。

## 8. 真实案例

**StrongDM 的 Attractor 系统**：三名工程师用此模式，从 3 个 markdown 规格文件产出 **16,000 行 Rust + 9,500 行 Go + 6,700 行 TypeScript**。无人工写代码，无人工审查代码。

| 指标         | 传统开发         | 黑灯工厂                    |
| ------------ | ---------------- | --------------------------- |
| 8 人团队产出 | 8 工程师         | 25-30 工程师等效            |
| 主要瓶颈     | 开发者时间       | 规格质量                    |
| 主导成本     | 工资             | ~$1k/天/工程师等效（token） |
| 质量门禁     | 人工 code review | 自动化场景评估              |
| 反馈环       | 数小时到数天     | 分钟级                      |

## 9. 常见陷阱

- **模糊的 spec（L3+）**：agent 无法推断意图。"加 auth"会失败，"加 OAuth2 PKCE 流程并带这 5 个约束"会成功。
- **泄漏 scenarios（L4+）**：编码 agent 若看到 holdout scenarios，会为它们优化而非解决问题。严格隔离不可妥协。
- **跳过 AGENTS.md（所有级别）**：没有结构化上下文，agent 产出泛化代码。
- **过早 auto-merge（L4）**：只在 20-30 个 PR 证明评估器与人类判断一致后才启用。
- **J 曲线（L2→3）**：学会写 spec 前会变慢，属正常，坚持。
- **巨型 spec（L3+）**：大 spec 压垮上下文窗口。一个功能一个 spec。

## 10. 对 Jarvis 的启示与落地建议

Jarvis 已具备构建黑灯工厂插件的底层能力：

- **编排机制**：`@OrganizeAgents` + YAML 编排文件，可一键批量创建多 Agent 协作拓扑（对应 Orchestrator/Planner 层）
- **多 Agent 协作**：Agent 间通信、点对点、群聊、子代理（对应 Generators/Validators 层）
- **无人值守**：`no_interaction_mode=True` 进程级无人值守 + 定时任务（对应全自动流水线）
- **SDK**：`pipeline` / `run_agents_parallel` / `run_structured`（对应编排与结构化输出）
- **CI 集成**：`jca -n --task-file` 非交互 + status_file 机制（对应自动门禁）
- **规则系统**：三层规则体系（builtin/project/global）+ AGENTS.md 兼容（对应 agent 上下文）

**建议插件形态**：一个可被 `jarvis --install-plugin` 安装的插件包，提供：

1. **规则文件**：定义黑灯工厂方法论（spec 编写规范、holdout scenarios 隔离纪律、TDD 铁律、编排纪律）
2. **工具**：spec 生成/校验、holdout scenarios 生成、评估门禁计算、编排文件生成
3. **编排模板**：预置 sw-controller 风格的多 Agent 流水线编排 YAML

> 注：本报告为调研成果。插件具体设计需与管理员确认后实施。
