---
name: holdout_discipline
description: AI Agent 黑灯工厂的验收场景隔离纪律。当需要生成或使用 holdout scenarios（保留验收场景）时触发。确保编码 agent 永远看不到验收场景，train/test 分离防作弊，由独立评估器用隐藏场景测试产出。
---

# 验收场景隔离纪律（Holdout Discipline）

## 核心原则

黑灯工厂的信任建立在**隔离评估**之上：编码 agent **永远看不到**验收场景（holdout scenarios），由独立的评估器 agent 用这些隐藏场景测试产出代码。

这是 train/test 分离——防止推理模型"过拟合"到它见过的规格上。研究证实，推理模型会针对它们能看到的规格作弊，即使有明确反指令。

## 纪律要求

1. **场景隔离**：holdout scenarios 由独立环节生成，编码 agent 全程不可见。
2. **独立评估器**：由专门的验证器 agent 持有 holdout scenarios 并执行测试，与生成器严格分离。
3. **不可泄漏**：任何环节不得把 holdout scenarios 内容透露给编码 agent。
4. **多次采样**：每个场景跑 3 次，2-of-3 通过以平滑 LLM 方差。

## 生成方式

用 `holdout_generator` 工具生成 holdout scenarios。生成的场景是纯英文验收测试，标记为编码侧不可见，仅提供给评估器。

## 在流水线中的落地方式

1. **独立生成环节**：flow 中在 planner 之后、generator 之前设 `holdout` 阶段，由独立 agent（`df_holdout`）执行——它读取 NLSpec，用 `holdout_generator` 生成场景骨架，再结合 spec 的 Goal/Interfaces 细化为针对本功能的验收场景，落盘 `.df/holdout.json`（标记 `hidden=true`）。
2. **一致性**：每条场景必须对应 spec 的一个 Goal 或 Interface 契约，确保场景源自 spec。
3. **隔离传递**：`.df/holdout.json` **只作为 validator 的 `input`，绝不注入 generator**（generator 的 `input` 只有 `.df/plan.md`）。
4. **独立评估**：validator 读取 `.df/holdout.json` 执行场景，逐场景记录 pass/fail，产物 `.df/report.json`。

## 门禁标准

- **场景通过率 ≥90%**：才建议通过门禁。
- **<90%**：视为未达标，进入重试或人工审批。
- **假阳性率 <5%、人类推翻率 <10%**：才考虑放宽为自动合并。

## 常见陷阱

- **泄漏 scenarios（L4+）**：编码 agent 若看到 holdout scenarios，会为它们优化而非解决问题。**严格隔离不可妥协**。
- **过早自动合并**：只在收集 20-30 个 PR 证明评估器与人类判断一致后才启用自动门禁。
- **场景过少**：样本不足无法评估真实质量。

## 与"不完全无人值守"的关系

本插件采用"不完全无人值守"设计：评估器产出 pass/fail 报告后，**不自动合并**，而是交人类审批关口。人类审的是 pass/fail 报告与失败场景详情，而非逐行代码。这既保留隔离评估的客观性，又通过人工审批控制信任边界。
