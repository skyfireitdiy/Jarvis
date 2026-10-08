# 方案：编排引擎失败清理与人工审批增强

> **状态**：待评审（先方案后实施）
> **关联报告**：`docs/research/agent-tech-report-2026q3.md`（第 4.1、6 节）
> **性质**：方案设计文档，当前**不实施**，供维护者审阅后决定。
> **日期**：2026-10-08

---

## 1. 背景与动机

2026 年 Q3，多智能体编排从「学术演示」走向「生产基础设施」。业界强调三类可靠性模式：**每个交接点输出校验**、**显式终止条件**（最大重试次数/循环上限）、**人工审批断点**（human-in-the-loop）。多 Agent 系统失败时最难调试——错误可能在第 3 个 Agent，但表象在第 5 个 Agent（来源：agentbrisk.com）。

Jarvis 现状（`src/jarvis/jarvis_tools/pipeline_runner.py`）：

- 已有 DAG 编排、`on_error` 失败策略、`retry` 重试、`gate: true` 人工审批关口。
- **已识别待办**：abort/失败时**未清理已创建的 Agent**，导致残留 running Agent（占用资源）。这是 2026-10-08 排查「编排的 Agent 全创建但都不执行」时发现的增强项。
- 门禁（gate）目前是「停住等审批」，但审批后的放行/拒绝流程、以及审批界面体验有增强空间。

**痛点**：

1. 流水线失败（abort）后，已创建但未完成的阶段 Agent 残留在系统中，需手动清理。
2. 门禁审批缺乏明确的「放行/拒绝/重试」交互与审计记录。

## 2. 目标

1. **失败清理**：流水线 abort/失败时，自动清理该 pipeline 已创建但未正常完成的阶段 Agent，避免残留。
2. **人工审批增强**：门禁处提供明确的放行/拒绝/重试操作，并记录审批日志（谁、何时、决定）。
3. 保持向后兼容：现有编排文件与行为不破坏。

## 3. 技术方案设计

### 3.1 失败清理（pipeline_runner）

在 pipeline_runner 的失败/abort 路径增加清理逻辑：

- **追踪已创建 Agent**：pipeline_runner 在创建每个阶段 Agent 时，记录其 agent_id 到 pipeline 上下文（`created_agents` 列表）。
- **失败清理**：当阶段 failed 且 `on_error=abort`（或整体 abort）时，遍历 `created_agents`，对仍处于 running 状态的 Agent 调用删除/停止（复用 gateway_manager 的 `_delete_agent` 或 `_handle_agent_stop`）。
- **保留产物**：清理 Agent 不删除已落盘的产物（产物按 pipeline_id 隔离在 `work_dir/.jarvis/artifacts/<pipeline_id>/`），便于事后排查。
- **幂等**：清理操作幂等，重复清理不报错。
- **可选开关**：提供 `cleanup_on_failure` 配置（默认 true），允许关闭。

### 3.2 人工审批增强

在 gate 阶段增强审批交互：

- **审批动作**：放行（approve）/ 拒绝（reject）/ 重试（retry）。
  - 放行：继续后续阶段。
  - 拒绝：中止流水线并清理。
  - 重试：重新执行当前门禁阶段。
- **审批日志**：记录审批人、时间、动作、备注，写入 pipeline 事件（供前端展示与审计）。
- **审批界面**：前端门禁浮层提供三按钮 + 备注输入框。

### 3.3 与现有系统集成

| 现有组件                            | 改动                                               |
| ----------------------------------- | -------------------------------------------------- |
| `pipeline_runner.py`                | 记录 created_agents；失败清理逻辑；审批动作处理    |
| `gateway_manager.py`                | 复用 `_delete_agent` / `_handle_agent_stop` 做清理 |
| `pipeline_events.py`                | 新增审批事件（approve/reject/retry）               |
| 前端（App.vue / OrchestrationView） | 门禁浮层增强                                       |

## 4. 实施步骤

1. **Agent 追踪**：pipeline_runner 创建 Agent 时记录 agent_id 到 pipeline 上下文。
2. **失败清理**：abort/失败路径遍历清理 running Agent（复用 gateway_manager 删除/停止）。
3. **审批动作**：gate 阶段支持 approve/reject/retry，写审批日志事件。
4. **前端增强**：门禁浮层三按钮 + 备注。
5. **测试**：新增失败清理（模拟失败→验证 Agent 被清理）、审批动作（approve/reject/retry）的单测。

## 5. 风险与限制

- **误清理**：清理可能误删「其他用途」的 Agent → 只清理本 pipeline 创建的、且仍 running 的 Agent，严格按 created_agents 追踪。
- **清理失败**：删除/停止接口可能失败 → 记录失败日志，提示人工处理，不阻塞。
- **审批误操作**：reject 会中止流水线 → 需二次确认。
- **向后兼容**：cleanup_on_failure 默认 true，但可关闭；审批动作向后兼容现有 approve。

## 6. 验证方式

- 单测：失败清理（模拟 abort → 断言 created_agents 被清理）、审批动作、幂等清理。
- 集成：跑一次含失败阶段的流水线，观察 Agent 是否被清理、产物是否保留。
- 回归：现有 pipeline_runner 测试全通过。

## 7. 影响面

- 主要改动：`pipeline_runner.py`、`pipeline_events.py`、前端门禁浮层。
- 影响：编排引擎核心路径，需谨慎回归；清理逻辑默认开启但可配置关闭。

## 8. 参考

- agentbrisk.com《Multi-Agent Orchestration in 2026》(2026-05-19)（输出校验/终止条件/人工审批断点）
- 本仓库 `docs/design/ai-dark-factory-orchestration-engine.md`（编排引擎设计）
- 2026-10-08 排查记录（abort 残留 Agent 待办）
