# Agent 领域最新技术调研报告（2026 年 7 月—10 月）

> **性质**：纯研究文档，不涉及任何代码实施。
> **调研时间**：2026-10-08
> **调研对象**：近两三个月（2026 年 7 月—10 月）Agent 领域最新技术与理念
> **参考代码库**：Jarvis（`/home/skyfire/code/Jarvis`）
> **产出**：本报告（技术全景 + 与 Jarvis 的结合点分析 + 价值/限制/影响评估）+ 针对值得引入项的各方案文档（见 `docs/research/` 下独立文件）
> **读者**：Jarvis 项目维护者（决策是否引入，当前不实施）

---

## 目录

1. [研究范围与方法](#1-研究范围与方法)
2. [执行摘要](#2-执行摘要)
3. [Jarvis 现状速览（架构摸底）](#3-jarvis-现状速览架构摸底)
4. [近两三月 Agent 技术全景](#4-近两三月-agent-技术全景)
5. [与 Jarvis 的结合点交叉分析](#5-与-jarvis-的结合点交叉分析)
6. [价值/限制/影响评估表](#6-价值限制影响评估表)
7. [结论与建议](#7-结论与建议)
8. [参考资料](#8-参考资料)

---

## 1. 研究范围与方法

### 1.1 范围

聚焦 2026 年 7 月—10 月（近两三个月）Agent 领域的技术与理念，覆盖以下维度：

- 多智能体协作与编排（框架、模式、协议）
- Agent 记忆与上下文工程
- 工具使用与标准化协议（MCP / A2A）
- Agent 安全（prompt injection、权限、治理）
- Agent 可观测性与评估
- Agentic Coding 行业趋势

### 1.2 方法

- 通过互联网搜索收集 2026 年 Q3 前后的行业文章、框架文档、研究报告与论文。
- 阅读 Jarvis 仓库核心模块代码，形成「现状基线」。
- 将外部技术与现状基线做交叉映射，评估价值、引入难度、影响面。
- 所有引用均标注来源；对无法核实的数据标注「待核实」，不做猜测。

---

## 2. 执行摘要

2026 年 Q3，Agent 领域的主旋律是**从「能用」走向「好用、可控、可观测」**。技术栈在三个层面成熟：

1. **中间层协议标准化**：MCP 成为工具接入的事实标准，A2A 协议推动 Agent 间互操作，生态红利显现。
2. **记忆/上下文工程成为独立学科**：「上下文窗口 ≠ 记忆」成为共识，分层记忆（短期/长期/程序性/情景）、选择性存储、压缩、学习回路（ACE）等模式成熟。
3. **多智能体编排从「学术演示」走向「生产基础设施」**：supervisor / handoff / swarm 三大模式被广泛讨论，编排框架（LangGraph / CrewAI / AutoGen）在 2026 年完成整合收敛，但**生产环境仍倾向自定义编排**而非套用框架。

**对 Jarvis 的核心结论**：Jarvis 已经拥有相当成熟的**自研多 Agent 编排引擎（pipeline_runner）+ 网关/节点架构 + 记忆系统 + MCP 客户端**，与 2026 年业界主流方向高度吻合，甚至在「编排」维度领先于多数开源框架。真正值得引入/借鉴的方向集中在：**记忆系统的分层与选择性存储、上下文工程的系统化、Agent 可观测性/评估、以及编排引擎的失败处理与人工审批增强**。详见第 6 节评估表。

---

## 3. Jarvis 现状速览（架构摸底）

> 以下基于对 Jarvis 仓库核心模块的实际阅读（2026-10-08）。

### 3.1 核心模块清单

| 模块       | 路径                                                 | 职责                                                                                         |
| ---------- | ---------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| 核心 Agent | `src/jarvis/jarvis_agent/`、`jarvis_code_agent/`     | 对话 Agent（jvs）、代码 Agent（jca）                                                         |
| 网关       | `jarvis_gateway/`、`jarvis_web_gateway/`             | Web 网关、跨节点转发（`node_manager.py`）                                                    |
| 工具系统   | `jarvis_tools/`                                      | 每个工具一个 .py，含 pipeline_runner、gateway_manager、memory、sub_agent、plugin_registry 等 |
| 编排引擎   | `jarvis_tools/pipeline_runner.py`                    | 内置多 Agent 编排执行引擎（DAG、flow、产物传递、门禁）                                       |
| 事件总线   | `jarvis_tools/pipeline_events.py`                    | pipeline_runner 与 web_gateway 的解耦桥梁（跨进程）                                          |
| 记忆系统   | `jarvis_tools/memory.py`、`jarvis_memory_organizer/` | MemoryTool + SmartRetriever + memory_organizer                                               |
| MCP        | `jarvis_mcp/`                                        | SSE / stdio / streamable 三种客户端                                                          |
| 插件机制   | `jarvis_tools/plugin_registry.py`                    | 可逆效应注册追踪                                                                             |
| 前端       | `jarvis_service/frontend/`                           | Vue（App.vue 约 2.6 万行）                                                                   |
| 安全       | `jarvis_sec/`                                        | 安全分析能力                                                                                 |

### 3.2 关键能力现状

**多 Agent 协作（gateway_manager）**：已具备 `send_to_agent`（wait + status_file 同步等待）、`create_agent`、`_list_agents`、群组（create_group/join/leave/send_group_message）、定时任务（create_timer）、跨节点转发（node_manager 的 `send_request_to_node`）、Agent 再生（regenerate_agent）等完整能力。

**编排引擎（pipeline_runner）**：这是 Jarvis 相对业界最突出的自研能力。它实现了：

- `flow` 字段描述阶段顺序与产物契约（`depends_on` / `input` 多输入 / `when` 条件 / `on_error` 失败策略 / `retry` 重试）
- DAG 构建与并行调度（`max_workers` 默认 4）
- 产物按 pipeline_id 隔离（`work_dir/.jarvis/artifacts/<pipeline_id>/`）
- 门禁（`gate: true` 停住等人工审批，默认 `approve=false`）
- 事件总线 `pipeline_events`（跨进程、有界队列、前端 DAG 可视化）
- 阶段 Agent 就绪等待（`_wait_agent_ready`，轮询状态直到网关代理成功）

**记忆系统**：MemoryTool 支持 save/retrieve/clear，分短期（short_term）、项目长期（project_long_term）、全局长期（global_long_term）；SmartRetriever 提供语义检索、知识推荐、相关知识关联（基于 jieba 分词 + embedding）。

**MCP**：已实现 SSE、stdio、streamable 三种客户端，可对接外部 MCP 服务器。

**插件机制**：plugin_registry 借鉴 Cordis 的 reversible effects 理念，实现注册/卸载完全对称。

### 3.3 现状的关键设计点与潜在局限

| 维度     | 现状                                       | 潜在局限                                                |
| -------- | ------------------------------------------ | ------------------------------------------------------- |
| 编排     | 自研 DAG 引擎，强                          | 失败清理（abort 时残留 Agent）待增强；无跨流水线复用    |
| 记忆     | 三类记忆 + 语义检索                        | 无「程序性记忆/情景记忆」显式分层；选择性存储与压缩较弱 |
| 上下文   | 有 token 预算管理（calculate_token_limit） | 缺少系统化的上下文工程（分层注入、检索预算）            |
| 可观测性 | 前端 DAG 可视化 + 事件总线                 | 无 OpenTelemetry 标准化追踪、无成本/耗时指标沉淀        |
| 评估     | 有 `jarvis_eval/`                          | 缺少面向 Agent 行为的系统化评估基准接入                 |
| 安全     | `jarvis_sec/` 安全分析                     | prompt injection 防御、工具沙箱化待评估                 |

---

## 4. 近两三月 Agent 技术全景

> 以下技术均收集自 2026 年 Q3 前后的公开资料，标注时间与来源。数据为引用来源所载，个别无法独立核实处标注「待核实」。

### 4.1 多智能体编排：三大模式与框架收敛

**核心趋势**：多智能体系统从「学术演示」走向「生产基础设施」。业界普遍认可三种基础编排模式：

1. **Supervisor（主管）模式**：中央编排 Agent 读取目标、决定调用哪些子 Agent 及顺序，汇总结果。适合「先 X 后 Y 再 Z」的多阶段任务（研究流水线、内容生产、代码生成+测试）。风险：主管成为瓶颈，且多一次 LLM 调用增加延迟。
2. **Handoff（交接）模式**：每个 Agent 完成后显式把控制权交给链上下一个，无中央规划器。适合线性固定流程。风险：僵化，分支/循环需退回 supervisor。
3. **Swarm（蜂群）模式**：多 Agent 同时从不同角度/分片处理同一问题，输出聚合或投票。适合高并行分片处理与质量关键型多稿择优。成本最高、最难调试。

**框架对比（2026 年）**：

| 框架      | 最佳模式     | 状态管理       | 并行度             | 生产成熟度 |
| --------- | ------------ | -------------- | ------------------ | ---------- |
| LangGraph | Supervisor   | 显式图状态     | 支持（async 节点） | 高         |
| CrewAI    | Handoff      | 任务上下文注入 | 有限               | 中         |
| AutoGen   | Swarm / 对话 | 会话历史       | 原生               | 中         |

来源：agentbrisk.com《Multi-Agent Orchestration in 2026》(2026-05-19)、presenc.ai《Multi-Agent Orchestration Frameworks 2026》。

**关键洞察（对 Jarvis 最有价值）**：2026 年生产环境**仍倾向自定义编排**而非套用框架（presenc.ai 指出 "Production deployments still favour custom orchestration over framework adoption"）。这印证了 Jarvis 自研 pipeline_runner 的方向是正确的——比引入 LangGraph/CrewAI 更贴合自身架构。

**上下文传递是编排成败关键**：业界强调「结构化交接对象」（定义 schema，传 `{findings, sources, confidence}` 而非原始草稿）、「摘要式交接」（小模型压缩）、「共享记忆」（KV/向量库）。这与 Jarvis pipeline_runner 的产物传递设计方向一致。

### 4.2 Agent 记忆与上下文工程

**核心共识**：「上下文窗口 ≠ 记忆」。上下文窗口是 RAM（工作记忆，会话结束即消失），持久记忆在外部存储（磁盘），按需换页（paging）。

**四类记忆分层**（2026 年主流框架普遍采用）：

| 记忆类型         | 内容                         | 存储位置                 | 检索时机         |
| ---------------- | ---------------------------- | ------------------------ | ---------------- |
| 短期（工作）     | 当前任务、近期轮次、计划     | Agent 状态/上下文        | 本次运行始终存在 |
| 长期（语义）     | 用户事实、历史决策           | 向量库/知识图谱          | 按相关性         |
| 程序性           | 学会的 how-to 规则、playbook | 结构化存储/playbook 文件 | 按任务类型       |
| 情景（episodic） | 历史会话记录                 | 归档存储                 | 按回忆查询       |

**代表框架**：

- **Mem0**：框架无关，社区最流行（约 48K~60K GitHub stars，来源不同口径），20+ 框架集成，向量+图混合后端。
- **Letta**：基于 MemGPT 论文，完整运行时，虚拟上下文管理（上下文=RAM、外部=磁盘，agent 自己调工具换页），三层记忆（core/recall/archival）。
- **Zep**：时序知识图谱后端，LongMemEval 上 63.8% vs Mem0 49.0%（来源：whysogeek.com）。

**关键模式**：

- **选择性存储**：写时过滤，只存「改变未来行为」的事实（"用户偏好公制单位"值得存，"用户说了谢谢"不存）。
- **压缩**：Active Context Compression 报告 22.7% token 缩减且准确率持平（来源：whysogeek.com）。
- **Agentic Context Engineering（ACE）**（ICLR 2026）：三 Agent 回路（Generator → Reflector → Curator），Curator 把教训写进持久化「上下文 playbook」，无需微调模型。报告 AppWorld 基准 +10.6%、XBRL 金融推理 +8.6%、适应延迟 -86.9%、金融任务 token 成本 -83.6%（来源：whysogeek.com，数据待独立核实）。

**对 Jarvis 的意义**：Jarvis 已有短期/项目长期/全局长期三类记忆 + 语义检索，但缺少**程序性/情景记忆的显式分层**、**写时选择性存储**、**压缩**与**学习回路（ACE）**。这些是低成本高价值的增强方向。

### 4.3 工具标准化协议：MCP 与 A2A

**MCP（Model Context Protocol）**：成为 Agent 与外部资源交互的事实标准，「一次对接，处处可用」。主流大模型厂商与 Agent 框架已全面支持。生态爆发（如 OpenClaw 类 6 万+ 技能生态，来源：open2ai.cn）。

**A2A（Agent2Agent）**：Google 主导的 Agent 间互操作协议，解决 Agent 间互操作性问题，提供统一、安全的通信框架（来源：什么值得买深度长文，2025-06-13 发布，2026 持续演进）。

**对 Jarvis 的意义**：Jarvis 已实现 MCP 三种客户端（SSE/stdio/streamable），方向正确。可考虑：① 作为 MCP **服务器**暴露自身工具（让外部 Agent 调用 Jarvis 能力）；② 评估 A2A 协议支持，实现与外部 Agent 互操作。

### 4.4 Agent 安全

**核心威胁**：prompt injection（直接注入/间接注入）、越权、敏感信息泄露。2026 年安全焦点从「模型能力」转向「Agent 行为治理」。

**关键方向**：

- **工具调用前对不受信任输入脱敏**（2025-12 已有讨论，2026 持续演进）。
- **身份认证、行为审计、权限最小化**成为企业级刚需（来源：open2ai.cn 十大趋势）。
- **治理监管**：各国出台 AI 法案，要求 Agent 可追溯、可关闭、可解释。

**对 Jarvis 的意义**：Jarvis 有 `jarvis_sec/` 安全分析能力，但需评估是否具备：工具沙箱化、prompt injection 检测、权限最小化（Agent 只授必要工具）等。多 Agent 编排场景下，跨 Agent 传递的产物/消息可能成为注入载体，值得专门评估。

### 4.5 Agent 可观测性与评估

**可观测性**：OpenTelemetry GenAI 语义约定（semantic conventions）成为标准化方向，Microsoft Build 2026 有「any agent any cloud standardized tracing」演示（来源：github.com/microsoft/Build26-DEM341）。MCP trace propagation 规范 2026-07-28 更新。

**评估**：AgentBench、SWE-bench 等基准持续演进；Agent 行为评估（工具使用、多步推理、决策质量）成为独立方向。

**对 Jarvis 的意义**：Jarvis 有前端 DAG 可视化 + 事件总线，但缺少标准化的耗时/成本/token 指标沉淀与跨 Agent 追踪。可考虑引入 OpenTelemetry GenAI 语义约定做标准化观测，以及接入 Agent 行为评估。

### 4.6 Agentic Coding 行业趋势

**Anthropic《2026 Agentic Coding Trends Report》**（来源：腾讯云/CSDN 解读）：

- 软件开发正从「人类写代码」转向「人类编排 AI 写代码」。
- 工程师角色从「代码实现者」变为「Agent 指挥/架构师」。
- 开发周期从数周压缩至数小时。
- 约 60% 的人已用 AI 写代码，但只有不到 20% 敢完全放手（来源：腾讯云解读，数据待核实）。

**对 Jarvis 的意义**：Jarvis 定位「协作式 AI 开发平台」，与这一趋势高度契合。pipeline_runner 的「人工审批关口」设计（gate: true、approve=false）正好对应「不完全无人值守」的行业共识，是差异化优势。

---

## 5. 与 Jarvis 的结合点交叉分析

将第 4 节外部技术与第 3 节 Jarvis 现状做交叉映射，识别「已具备」「值得增强」「可探索」三类。

### 5.1 已具备（方向正确，无需大改）

| 技术                                            | Jarvis 现状                   | 差距                     |
| ----------------------------------------------- | ----------------------------- | ------------------------ |
| 自定义编排（业界倾向）                          | pipeline_runner 自研 DAG 引擎 | 已领先，无需引入外部框架 |
| 多 Agent 协作（send_to_agent/群组/定时/跨节点） | gateway_manager 完整能力      | 已具备                   |
| 人工审批关口                                    | pipeline_runner gate 设计     | 已具备，符合行业共识     |
| MCP 客户端                                      | SSE/stdio/streamable 三种     | 已具备                   |
| 记忆分层（短期/长期）                           | 短期/项目长期/全局长期        | 部分具备，见 5.2         |
| 产物传递（结构化交接）                          | pipeline_runner 产物契约      | 已具备                   |

### 5.2 值得增强（低成本高价值）

| 技术                                   | 建议                                  | 价值                 | 难度  |
| -------------------------------------- | ------------------------------------- | -------------------- | ----- |
| 程序性记忆/情景记忆分层                | 在现有三类记忆上增加显式分层          | 中                   | 中    |
| 写时选择性存储 + 压缩                  | MemoryTool save 时过滤/压缩           | 高（降噪、省 token） | 低-中 |
| 上下文工程系统化（检索预算、分层注入） | 建立上下文预算与注入策略              | 高                   | 中    |
| ACE 学习回路                           | 借鉴 Generator/Reflector/Curator 模式 | 中（需验证）         | 中-高 |
| 编排失败清理                           | abort 时清理已创建 Agent              | 高（已有待办）       | 中    |

### 5.3 可探索（需评估投入产出）

| 技术                               | 建议                         | 价值  | 难度  |
| ---------------------------------- | ---------------------------- | ----- | ----- |
| OpenTelemetry GenAI 观测           | 标准化追踪 + 指标沉淀        | 中-高 | 中-高 |
| Agent 行为评估基准                 | 接入 AgentBench/SWE-bench 类 | 中    | 中    |
| MCP 服务器（暴露自身工具）         | 让外部 Agent 调用 Jarvis     | 中    | 中    |
| A2A 协议                           | 与外部 Agent 互操作          | 中    | 高    |
| 工具沙箱化 / prompt injection 防御 | 安全增强                     | 高    | 高    |

---

## 6. 价值/限制/影响评估表

> 评分 1-5（5 最高）。「影响面」指改动波及范围。

| 技术方向                  | 价值 | 引入难度 | 影响面                 | 与现状差距     | 优先级建议 |
| ------------------------- | ---- | -------- | ---------------------- | -------------- | ---------- |
| 记忆写时选择性存储 + 压缩 | 5    | 2        | 小（memory.py）        | 中             | **高**     |
| 程序性/情景记忆分层       | 4    | 3        | 中（memory 系统）      | 中             | 高         |
| 上下文工程系统化          | 4    | 3        | 中（Agent 上下文构建） | 中             | 高         |
| 编排失败清理              | 5    | 3        | 小（pipeline_runner）  | 小（已有待办） | **高**     |
| 编排人工审批增强          | 4    | 2        | 小                     | 小             | 中-高      |
| ACE 学习回路              | 3    | 4        | 中                     | 大             | 中         |
| OpenTelemetry 观测        | 3    | 4        | 大（全链路）           | 大             | 中         |
| Agent 行为评估            | 3    | 3        | 中（eval 模块）        | 中             | 中         |
| MCP 服务器                | 3    | 3        | 中                     | 中             | 中         |
| A2A 协议                  | 2    | 5        | 大                     | 大             | 低（观望） |
| 工具沙箱化/注入防御       | 4    | 4        | 大（安全体系）         | 大             | 中-高      |

---

## 7. 结论与建议

### 7.1 总体判断

Jarvis 的架构方向与 2026 年 Q3 业界主流高度一致，尤其在**自研多 Agent 编排引擎**上领先于多数开源框架。不建议引入 LangGraph/CrewAI/AutoGen 等外部编排框架——这与 2026 年「生产环境倾向自定义编排」的行业结论一致，且会破坏现有架构。

### 7.2 建议优先引入（写详细方案）

1. **记忆系统增强：写时选择性存储 + 压缩 + 程序性/情景记忆分层**——低成本高价值，直击「上下文窗口 ≠ 记忆」这一 2026 核心共识，降噪省 token。
2. **上下文工程系统化**——建立检索预算与分层注入策略，让 Agent 在有限上下文内拿到高信号信息。
3. **编排引擎失败清理与人工审批增强**——补齐已识别的待办（abort 清理残留 Agent），并增强门禁体验。

### 7.3 建议观望/评估

- ACE 学习回路（需验证对本项目任务的增益）
- OpenTelemetry 标准化观测（投入大，可先做轻量指标）
- 工具沙箱化 / prompt injection 防御（安全刚需，但改动大，需专项设计）
- A2A 协议（生态未完全成熟，先观望）

### 7.4 不引入

- 外部编排框架（LangGraph/CrewAI/AutoGen）——与自研方向冲突，破坏架构。

---

## 8. 参考资料

> 以下为调研过程中收集的公开资料。部分来源为聚合/解读文章，数据以原文为准；标注「待核实」的数据需进一步查证。

1. agentbrisk.com《Multi-Agent Orchestration in 2026: Patterns, Frameworks, and When to Use Each》(2026-05-19)
2. presenc.ai《Multi-Agent Orchestration Frameworks 2026》
3. whysogeek.com《AI Agent Memory: Context Engineering Patterns for 2026》(2026-06-29)
4. open2ai.cn《2026 AI Agent 智能体十大趋势》(2026-07-21)
5. 什么值得买《谷歌 Agent2Agent (A2A) 协议权威详解》(2025-06-13)
6. github.com/microsoft/Build26-DEM341（OpenTelemetry GenAI 语义约定多 Agent 观测演示，Build 2026）
7. 腾讯云开发者社区《Anthropic〈2026 Agentic Coding Trends Report〉解读》
8. CSDN《2026年AI Agent技术最新进展：从工具调用到自主决策的范式跃迁》
9. 刘道玉 AI 工作坊《Agent 研究最新趋势》(2026-04-29)
10. zylos.ai《Context Engineering for AI Agents》(2026-06-26)
11. Mem0 / Letta / Zep 官方文档与社区资料（记忆框架）
12. arXiv《The Orchestration of Multi-Agent Systems》(2601.13671)
