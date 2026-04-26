# Jarvis CodeAgent 与 Claude Code 代码代理能力对比分析

## 1. 研究范围与信息来源

本文基于以下实际代码与文档进行对比分析，聚焦“代码 Agent / 任务执行代理”能力，不讨论与代码代理无关的外围业务。

### 1.1 Jarvis 代码来源

- `src/jarvis/jarvis_code_agent/code_agent.py` - Jarvis CodeAgent 主实现、工具装配、上下文管理器初始化、运行流程
- `src/jarvis/jarvis_code_agent/code_agent_prompts.py` - 场景化系统提示词与需求分类
- `src/jarvis/jarvis_tools/task_list_manager.py` - 任务列表、验证 Agent、任务执行约束
- `src/jarvis/jarvis_agent/__init__.py` - 通用 Agent 基座、ARCHER 工作流、记忆/规则/事件机制
- `src/jarvis/jarvis_agent/sub_agent.py` - 通用子 Agent 实现
- `src/jarvis/jarvis_code_agent/sub_code_agent.py` - CodeAgent 子代理实现
- `src/jarvis/jarvis_code_agent/code_analyzer/__init__.py` - 代码分析能力总入口
- `src/jarvis/jarvis_code_agent/code_analyzer/llm_context_recommender.py` - LLM 驱动上下文推荐与符号扫描

### 1.2 Claude Code 代码来源

- `../claude-code/README.md` - 项目架构总览、能力目录、关键设计说明
- `../claude-code/src/context.ts` - 系统/用户上下文收集与缓存
- `../claude-code/src/tools/EnterPlanModeTool/EnterPlanModeTool.ts` - 显式 plan mode 实现
- `../claude-code/src/tools/FileEditTool/FileEditTool.ts` - 文件编辑安全校验、权限检查、文件状态验证
- `../claude-code/src/tools/TaskListTool/TaskListTool.ts` - 任务列表读取
- `../claude-code/src/tools/TaskCreateTool/TaskCreateTool.ts` - 任务创建
- `../claude-code/src/tools/TaskUpdateTool/TaskUpdateTool.ts` - 任务更新、完成钩子、验证提示
- `../claude-code/src/tools/AgentTool/AgentTool.tsx` - 子代理/队友代理生成
- `../claude-code/src/tools/AgentTool/agentToolUtils.ts` - 子代理收尾、安全交接、后台生命周期
- `../claude-code/src/tools/AgentTool/runAgent.ts` - 子代理运行与工具解析

### 1.3 分析边界

- 重点对比：执行工作流、任务规划、上下文管理、工具系统、子代理、多任务协作、安全/权限、编辑可靠性、记忆与状态管理、可观测性
- 不重点展开：UI 皮肤、账号系统、商业闭源能力、与代码代理关系较弱的外围集成
- 结论仅基于当前仓库快照，不假设未读代码中的隐藏实现

---

## 2. 总体判断

**结论先行：**

Jarvis 当前已经具备一个相当完整的“项目级代码 Agent”基础框架，优势在于：

- 有清晰的 ARCHER 工作流约束
- 有规则系统、方法论系统、记忆系统
- 有项目级代码分析、上下文推荐、影响分析、构建验证、lint、post-process
- 有 task_list_manager，可做复杂任务拆解与验证
- 有通用 Agent 与 CodeAgent 分层，扩展能力较强

但和 Claude Code 对比后，可以看出 Jarvis 仍有几个明显短板：

1. **计划模式还不够“产品化”与“可状态化”**：Jarvis 有 HYPOTHESIZE / EXECUTE 语义，但缺少像 Claude Code 那样显式可切换、可约束、可审计的 `plan mode` 状态机。
2. **权限与编辑安全模型不够细粒度**：Jarvis 主要依赖提示词约束和人工确认，Claude Code 则把权限检查、路径规则、文件状态一致性校验放进工具实现层。
3. **多 Agent 协作能力仍偏“子任务调用”而非“协作系统”**：Jarvis 有 `sub_agent` / `sub_code_agent`，但 Claude Code 已经形成代理类型、团队、邮箱、后台执行、恢复、交接分类等完整体系。
4. **上下文注入机制还不够轻量、缓存化、可视化**：Jarvis 更偏“运行时搜索 + LLM 推荐”，Claude Code 更强调“系统上下文/用户上下文分层缓存 + 自动记忆注入 + 上下文可视化”。
5. **编辑工具层的鲁棒性还有提升空间**：Claude Code 的 FileEditTool 在权限、路径标准化、文件大小、文件存在性、并发修改检测等方面更系统；Jarvis 目前更强调搜索替换准确性，但工具级保护相对少。
6. **可观测性和运行期状态反馈不足**：Claude Code 对 plan/task/agent/progress/context 都有更强的 UI 与状态反馈，而 Jarvis 更多依赖文本流程约束。

换句话说，**Jarvis 的“方法论”和“工程分析能力”偏强，Claude Code 的“执行产品化”和“状态机化工具治理”更成熟。**

---

## 3. 两个项目的代码 Agent 架构对比

### 3.1 Jarvis 的架构特征

从 `CodeAgent(Agent)` 可以看出，Jarvis 采用的是**通用 Agent 基座 + 代码专用增强层**的模式：

- 通用能力在 `jarvis_agent` 中统一管理：事件总线、PromptManager、MemoryManager、RulesManager、TaskAnalyzer、TaskListManager、SessionManager、ToolExecutor 等
- 代码能力在 `jarvis_code_agent` 中增强：
  - `ContextManager`
  - `ContextRecommender`
  - `GitManager`
  - `DiffManager`
  - `ImpactManager`
  - `BuildValidationManager`
  - `LintManager`
  - `PostProcessManager`

`code_agent.py` 中可直接看到：

- `CodeAgent` 继承 `Agent`
- 初始化时分离“基础属性 / 上下文管理器 / 代码管理器 / 工具列表 / 父类初始化后设置”
- 使用 `ContextManager(self.root_dir)` 做项目上下文管理
- 用 `ContextRecommender` 做 LLM 驱动的语义上下文推荐
- 用事件总线订阅 `AFTER_TOOL_CALL`，说明其执行后处理与 diff/提交联动较深

这说明 Jarvis 的设计重心是：**把代码任务当作 Agent 基座上的一种专业形态**。

### 3.2 Claude Code 的架构特征

Claude Code 从 README 和目录结构看，采用的是更明显的**工具平台化 + 状态化 CLI + 多代理编排**模式：

- `QueryEngine.ts` 负责 LLM query/tool-call loop
- `Tool.ts` 负责所有工具统一定义
- `tools/` 下每个工具独立模块化，包含：
  - schema
  - permission model
  - execution logic
  - UI rendering
- `context.ts` 负责系统/用户上下文的集中收集与缓存
- `AgentTool`、`Task*Tool`、`EnterPlanModeTool` 等工具把“代理系统”本身工具化
- `coordinator/`、`tasks/`、`memdir/`、`services/extractMemories/`、`teamMemorySync/` 体现出更强的运行态系统设计

Claude Code 的重点不是“一个大 Agent 类”，而是：

> 让 Agent 成为被状态机、权限系统、任务系统、上下文系统、UI 系统共同约束和驱动的执行单元。

### 3.3 架构差异总结

| 维度         | Jarvis                                 | Claude Code                      |
| ------------ | -------------------------------------- | -------------------------------- |
| 核心组织方式 | 通用 Agent 基座 + CodeAgent 扩展       | 工具平台 + 状态机 + 多代理编排   |
| 重点         | 规则/方法论/代码分析深度               | 权限/状态/交互/多代理协作        |
| 可扩展方向   | 更适合快速接入新规则、新工具、新分析器 | 更适合大规模交互式使用和复杂协作 |
| 当前成熟度   | 工程能力强                             | 产品化和协作化更强               |

---

## 4. 工作流设计对比

### 4.1 Jarvis：ARCHER 工作流优势明显

Jarvis 在系统提示词中强制定义了 ARCHER：

- ANALYZE
- RULE
- COLLECT
- HYPOTHESIZE
- EXECUTE
- REVIEW

其优点：

1. **流程完整**：分析、规则加载、信息收集、方案设计、执行、复盘都被定义了。
2. **适合研究/复杂工程任务**：尤其适合需要大量信息收集和多轮分析的代码任务。
3. **强调证据与可追溯性**：禁止臆测，强调工具优先。
4. **带 REVIEW 闭环**：比很多只会“写代码”的 agent 更稳。

`code_agent_prompts.py` 还支持根据场景动态选择系统提示词，这说明 Jarvis 已经开始从“统一 Agent”走向“场景化 Agent”。

### 4.2 Claude Code：Plan Mode 更显式、更可执行

Claude Code 的 `EnterPlanModeTool` 很值得关注：

- 它不是纯提示词约定，而是**显式工具**
- 进入后会修改 `toolPermissionContext.mode`
- 明确规定：**plan mode 下不要编辑文件**
- 要求先探索、比较方案、必要时向用户提问，再退出计划模式等待批准
- 还是只读工具、可并发安全工具

这意味着 Claude Code 的“计划”不是软约束，而是**带系统状态切换的硬约束**。

### 4.3 Jarvis 当前缺口

Jarvis 虽然语义上有 HYPOTHESIZE，但缺少以下能力：

- 没有一个真正的“计划态 / 执行态”系统状态切换
- 没有工具级只读限制来确保计划阶段不发生写操作
- 非交互模式里往往直接继续执行，计划与执行的边界不如 Claude Code 清晰
- 缺少一个显式的“批准后退出计划态”的状态记录点

### 4.4 改进建议

**建议 1：为 Jarvis 引入显式 Plan Mode。**

建议实现：

- `enter_plan_mode` / `exit_plan_mode` 工具
- 在 Agent 状态中记录当前 mode：`analyze` / `plan` / `execute` / `review`
- plan mode 下，工具层直接禁止 `edit_file`、写文件型 `execute_script`、危险 shell
- 允许 `read_code`、`execute_script`（只读命令）、`search_web`、`load_rule`
- 退出 plan mode 时要求生成结构化计划摘要并写入短期记忆

**收益：**

- 降低误改代码风险
- 让“先分析再修改”真正落在系统状态上
- 更适合将来接 UI、审批流、远程协作

---

## 5. 上下文管理对比

### 5.1 Jarvis：语义推荐 + 项目扫描

Jarvis 的 `ContextRecommender` 采用了较重但较智能的路径：

- 必要时扫描项目构建符号表
- 基于 LLM 提取关键词
- 在符号表中模糊搜索候选符号
- 再用 LLM 从候选符号中二次筛选
- 返回推荐符号作为上下文

这个设计的优点：

- 对大型工程任务有更强的“语义理解”能力
- 不只是 grep，而是结合项目符号和意图理解
- 与 `ImpactAnalyzer`、`DependencyAnalyzer` 体系天然兼容

但它也有明显成本：

- 首次扫描成本较高
- 对项目规模敏感
- 更像“按需理解代码”，不够像“会话级上下文系统”

### 5.2 Claude Code：系统上下文 / 用户上下文分层缓存

`context.ts` 显示 Claude Code 把上下文收集做成了独立模块：

- `getSystemContext()`：收集 git 状态、分支、最近提交、调试注入等
- `getUserContext()`：收集 `CLAUDE.md`、memory files、日期等
- 两者都做了 memoize 缓存
- 还考虑是否在某些场景跳过 git 状态以减少开销
- 对用户上下文有明确的“裸模式 / 禁用注入”处理

这是一种**更轻、更稳定、更像基础设施**的设计。

### 5.3 Jarvis 可改进点

Jarvis 还可以补这些能力：

1. **上下文分层缓存**：
   - 系统上下文：git 状态、分支、最近提交、工具可用性、工作目录
   - 用户上下文：规则、项目记忆、短期计划、README 摘要
   - 工程上下文：最近编辑文件、推荐符号、任务清单

2. **增量上下文刷新**：
   - 不是每轮都重新做重分析
   - 按文件改动、分支变化、任务变化做失效

3. **上下文可视化**：
   - Claude Code 有 `/context`
   - Jarvis 目前缺少“当前到底把什么喂给模型”的直观展示

4. **自动注入项目约定文档**：
   - 类似 Claude Code 的 `CLAUDE.md`
   - Jarvis 可把 `.jarvis/rules/project_info/README.md`、项目规则、关键方法论摘要作为稳定上下文层

### 5.4 建议优先级

- **高优先级**：会话级系统上下文缓存与增量刷新
- **中优先级**：上下文可视化命令/工具
- **中优先级**：自动注入项目设计文档与约定摘要

---

## 6. 工具系统与编辑可靠性对比

### 6.1 Jarvis 工具系统特点

Jarvis 在 `CodeAgent._build_code_agent_tool_list()` 中默认挂载：

- `execute_script`
- `read_code`
- `edit_file`
- `load_rule`
- `virtual_tty`
- `search_web`
- `read_webpage`
- `memory`
- `methodology`
- `task_list_manager`（可选）

优点：

- 工具覆盖面广
- 偏向“研究 + 编码 +知识积累”统一平台
- 有 memory / methodology 这类 Claude Code 没有完全同构的能力

### 6.2 Claude Code FileEditTool 的强项

`FileEditTool.ts` 暴露出非常成熟的工具治理设计：

- schema 校验严格
- 路径标准化，避免相对路径/`~` 绕过规则
- 权限检查在工具层执行
- 拒绝编辑受 deny 规则限制的目录
- 防 UNC 路径导致凭证泄漏（Windows 安全细节）
- 限制最大可编辑文件大小，防 OOM
- 文件不存在时给出相似路径建议
- 处理空文件、创建文件、已有文件等边界情况
- 编辑前读取文件当前状态，具备防意外覆盖的基础
- 与 git diff、file history、LSP、VSCode 通知联动

这说明 Claude Code 的编辑工具不是“文本替换函数”，而是**具备安全、状态、反馈、诊断意识的基础设施工具**。

### 6.3 Jarvis 当前短板

Jarvis 的 `edit_file` 使用 search/replace 很适合精确补丁，但当前从系统层面看还缺少一些能力：

- 缺少显式路径级权限模型
- 缺少大文件编辑保护
- 缺少“文件已被外部改动”的并发写保护
- 缺少统一的编辑历史与 IDE 联动
- 缺少基于规则的 deny/allow 路径治理

### 6.4 改进建议

**建议 2：增强 Jarvis 的 edit_file/execute_script 安全治理层。**

建议新增：

- 路径白名单/黑名单策略
- 文件大小限制
- 编辑前 mtime/hash 校验
- 受保护路径（如 `.git/`, `node_modules/`, `dist/`, 二进制目录）默认拒绝
- 对 `execute_script` 增加“只读命令 / 写命令 / 危险命令”分类
- 在非交互模式下对高风险命令执行额外拦截策略

**建议 3：引入统一 patch 会话与编辑历史。**

至少应记录：

- 本轮修改的文件
- 每次编辑前后的摘要
- 是否通过后续验证
- 是否触发回退

---

## 7. 任务系统与验证机制对比

### 7.1 Jarvis：task_list_manager 已经很强

Jarvis 的 `task_list_manager` 其实是本项目很强的一个资产：

- 支持 `add_tasks` / `execute_task` / `update_task`
- 强制任务描述包含约束、必须项、禁止项、验证标准
- 支持 `main` 与 `sub` 两种任务代理类型
- 支持依赖管理
- 支持验证 Agent
- 支持记录 verification_method
- 还能统计模型调用轮次

这已经不是简单 todo list，而是**带验证语义的执行计划系统**。

### 7.2 Claude Code：任务系统更轻，但和多代理/状态系统结合更紧

Claude Code 的任务工具：

- `TaskCreateTool`
- `TaskListTool`
- `TaskUpdateTool`

其特点是：

- schema 非常明确
- UI 自动展开 task panel
- 有 task created / completed hooks
- 在 agent swarm 模式下可自动关联 owner
- `TaskUpdateTool` 与验证代理类型有联动（`VERIFICATION_AGENT_TYPE`）
- 可通过 teammate mailbox 进行协作

Claude Code 不是靠“任务描述很严格”来保证质量，而是依赖：

- 工具 schema
- 系统状态
- hooks
- UI 可见性
- 多代理协作机制

### 7.3 Jarvis 与 Claude Code 的互补关系

- Jarvis 强在**任务内容规范化**
- Claude Code 强在**任务运行态集成化**

### 7.4 Jarvis 改进建议

**建议 4：把 task_list_manager 从“强提示约束”升级为“强状态系统”。**

可增加：

1. 任务 owner / worker agent 概念
2. 任务运行中可视状态
3. 任务完成 hooks
4. 任务验证 hooks
5. 任务与当前 diff/文件修改自动关联
6. 支持“任务恢复 / 挂起 / 后台继续”

**建议 5：将验证 Agent 产品化。**

Jarvis 已有验证 Agent 雏形，建议补齐：

- `verification` 作为显式 agent type
- 任务完成后自动触发验证代理
- 对失败验证自动回写任务状态
- 把验证结果结构化展示为 checklist

---

## 8. 多 Agent 协作能力对比

### 8.1 Jarvis 当前状态

Jarvis 有：

- `sub_agent`
- `sub_code_agent`
- `task_list_manager` 中主/子任务代理分派

优势：

- 已经具备多代理执行的基础
- 通用任务与代码任务可以分流
- 可通过父代理继承部分规则/工具

但限制也很明显：

- 子代理更多是“一次性调用”
- 缺少长期存活 agent identity
- 缺少 agent 间消息通道
- 缺少团队/角色/队列/后台生命周期
- 缺少清晰的 agent handoff 安全检查

### 8.2 Claude Code 的领先点

从 `AgentTool` 目录可见，Claude Code 已经形成了完整多代理体系：

- 内建代理类型：`exploreAgent`、`planAgent`、`verificationAgent`、`generalPurposeAgent`
- `runAgent.ts` 负责子代理运行
- `resumeAgent.ts` 负责恢复
- `forkSubagent.ts` 负责异步/后台子代理
- `agentMemory.ts` / `agentMemorySnapshot.ts` 负责代理记忆
- `SendMessageTool` 支持向代理发消息
- `TeamCreateTool` / `TeamDeleteTool` 支持 team agent 管理
- `spawnTeammate()` 表明支持团队/队友模式
- 有 mailbox、owner、team_name、agent_id 等概念
- 有 handoff classifier，对子代理输出做安全分类

这是从“子任务执行”进化到了“代理协作系统”。

### 8.3 Jarvis 改进建议

**建议 6：将 Jarvis 的子代理系统升级为“角色化协作代理”。**

第一阶段可先做：

- 内建 agent types：`explore`、`plan`、`implement`、`verify`
- 每种 agent type 有独立系统提示词和默认工具集
- 子代理输出结构统一
- 支持将子代理结果显式回传主代理

第二阶段可做：

- agent_id / mailbox / send_message
- 后台代理与恢复机制
- team coordinator
- 代理工作树隔离

### 8.4 特别值得借鉴的点

Claude Code 的 `AgentTool` 明确限制：

- 队友不能再生成队友，保持 team roster 扁平
- in-process teammate 不能生成后台代理
- 对子代理输出进行安全交接分类

这类约束非常关键，因为多代理一旦没有规则，系统复杂度会迅速失控。

---

## 9. 权限与安全模型对比

### 9.1 Jarvis 的现状

Jarvis 的安全性更多依赖：

- 系统提示词约束
- 用户确认
- review/revert 工作流
- Git diff 与回滚能力
- 构建验证 / lint / 影响分析

这对工程任务已经有帮助，但更多是**执行后治理**与**流程约束**。

### 9.2 Claude Code 的现状

Claude Code 明显更偏**执行前治理**：

- 每个工具有 permission model
- `EnterPlanModeTool` 会修改 permission mode
- `FileEditTool` 在工具层做权限判断
- 有 `default/plan/acceptEdits/dontAsk/auto` 等模式
- 子代理生成也需要权限
- 支持组织策略限制（README 提到 `policyLimits/`）

### 9.3 Jarvis 改进建议

**建议 7：为 Jarvis 增加统一 PermissionContext。**

建议至少支持：

- 模式：`default` / `plan` / `execute` / `dangerous`
- 路径权限：读/写/拒绝
- 工具权限：允许/需要确认/禁止
- shell 命令风险分级
- 非交互模式下的权限自动决策规则

这会让 Jarvis 从“依赖提示词自律”提升到“系统层约束执行”。

---

## 10. 记忆系统对比

### 10.1 Jarvis 的优势

Jarvis 的记忆系统明显比 Claude Code 当前代码快照中暴露的能力更系统化：

- `memory` 工具统一支持 save/retrieve/clear
- 记忆分层：短期 / 项目长期 / 全局长期
- 结合 methodology 与 rules，可形成长期知识积累
- 在 Agent 启动统计中直接展示记忆数量
- `sub_agent` / `sub_code_agent` 还会把 memory tags 合并回父代理

这是 Jarvis 的强项，建议继续保留并加强。

### 10.2 Claude Code 的亮点

Claude Code 也有值得借鉴之处：

- `context.ts` 中会读取 memory files / CLAUDE.md
- README 中提到 `extractMemories/`、`teamMemorySync/`
- `agentMemory.ts`、`agentMemorySnapshot.ts` 显示其记忆与子代理生命周期绑定更深

### 10.3 Jarvis 可加强方向

**建议 8：把记忆系统从“存储能力”升级为“自动注入与自动提炼能力”。**

建议：

- 每轮结束自动抽取候选记忆
- 区分事实、偏好、项目约定、临时执行计划
- 子代理结果自动总结为结构化短期记忆
- 任务完成后自动形成“经验记忆”候选
- 项目设计文档自动纳入可检索上下文层

---

## 11. 可观测性与用户体验对比

### 11.1 Claude Code 的明显优势

从目录与工具实现可见，Claude Code 在这几方面明显更成熟：

- `renderToolUseMessage` / `renderToolResultMessage` / `renderToolUseRejectedMessage`
- 任务列表自动展开
- 子代理进度 UI 分组展示
- 上下文可视化
- plan mode、task、agent 都是状态化对象
- progress 事件丰富

### 11.2 Jarvis 当前状态

Jarvis 现在的优势在信息和方法论，但运行态体验更偏“终端日志流”：

- 状态存在于 prompt 和文本输出中
- 工具执行结果较少形成统一可视状态
- 子任务/验证/回顾缺少统一面板式表示

### 11.3 Jarvis 改进建议

**建议 9：为 Jarvis 增加执行态可视化对象。**

例如：

- 当前模式
- 当前任务列表摘要
- 当前收集到的上下文文件
- 当前变更文件集
- 当前验证状态
- 当前风险级别

哪怕先做纯终端文本面板，也会显著提升可用性。

---

## 12. Jarvis 还没有实现、但 Claude Code 值得借鉴的设计

下面列出当前最值得借鉴、且 Jarvis 尚未完整实现的设计。

### 12.1 显式 Plan Mode 状态机

**Claude Code 现状：** `EnterPlanModeTool` 显式切换状态、限制行为。

**Jarvis 当前：** 只有流程约定，没有真正状态机。

**建议：高优先级引入。**

---

### 12.2 工具级权限系统

**Claude Code 现状：** 工具自带 permission check，按 mode 与路径规则裁决。

**Jarvis 当前：** 主要靠提示词、确认和流程控制。

**建议：高优先级引入。**

---

### 12.3 角色化子代理体系

**Claude Code 现状：** explore / plan / verification / teammate / team。

**Jarvis 当前：** sub_agent / sub_code_agent 较通用。

**建议：高优先级分阶段引入。**

---

### 12.4 子代理安全交接分类器

**Claude Code 现状：** 对 sub-agent handoff 做 classifier 检查并生成 warning。

**Jarvis 当前：** 子代理结果回传缺少专门安全分类。

**建议：中高优先级。**

---

### 12.5 后台代理与恢复机制

**Claude Code 现状：** async/background agent、resume、mailbox。

**Jarvis 当前：** 子代理多为同步单次执行。

**建议：中优先级。**

---

### 12.6 上下文分层缓存

**Claude Code 现状：** system/user context 分层并缓存。

**Jarvis 当前：** 更依赖按需分析与推荐。

**建议：高优先级。**

---

### 12.7 文件编辑鲁棒性保护

**Claude Code 现状：** 路径标准化、deny 规则、大文件保护、并发变更保护。

**Jarvis 当前：** search/replace 精准，但系统保护偏少。

**建议：高优先级。**

---

### 12.8 任务 hooks 与 UI 状态联动

**Claude Code 现状：** 任务创建/完成 hooks、任务面板展开、owner 自动设置。

**Jarvis 当前：** 任务规范强，但运行态联动较弱。

**建议：中优先级。**

---

## 13. Jarvis 当前已有优势，不应盲目照搬 Claude Code

也要注意，Claude Code 不是所有方面都优于 Jarvis。Jarvis 有几项能力应继续坚持，甚至作为差异化方向加强。

### 13.1 规则系统与方法论系统

Jarvis 的 `load_rule`、`methodology`、项目级规则、可沉淀流程知识，是 Claude Code 代码快照里没有同等强度体现的。

### 13.2 研究型工作流能力

ARCHER 非常适合：

- 代码研究
- 方案对比
- 项目反向工程
- 技术选型
- 开源项目调研

Claude Code 更像产品化执行器，Jarvis 更像工程研究助手。这个定位值得保留。

### 13.3 代码分析深度

Jarvis 的 `ContextManager`、`ImpactAnalyzer`、`DependencyAnalyzer`、`BuildValidationManager`、`LintManager` 形成了更明确的工程验证链。

### 13.4 记忆分层设计

Jarvis 的短期/项目/全局三层记忆非常适合长期使用，应继续强化自动提炼与自动注入，而不是削弱。

---

## 14. 建议的改进路线图

### P0：应尽快推进

1. **显式 Plan Mode**
   - 新增 `enter_plan_mode` / `exit_plan_mode`
   - 增加 Agent mode 状态字段
   - plan mode 下禁止写操作

2. **工具级权限上下文**
   - 为 `edit_file`、`execute_script`、`virtual_tty` 增加统一权限判定
   - 支持路径规则、命令风险级别、非交互自动决策

3. **上下文分层缓存**
   - system context / user context / project context 分层
   - 增量失效
   - 减少重复分析开销

4. **编辑鲁棒性增强**
   - 文件大小限制
   - hash/mtime 校验
   - 受保护路径默认拒绝
   - 编辑历史记录

### P1：建议中期推进

5. **角色化子代理**
   - explore / plan / implement / verify 四种内建 agent type
   - 不同默认工具集与系统提示词

6. **验证代理产品化**
   - task 完成后自动验证
   - 验证失败自动回写任务状态

7. **任务 hooks 与任务状态面板**
   - create/update/complete hooks
   - 与 diff、文件变更、验证状态联动

8. **上下文可视化**
   - 新增当前上下文摘要命令
   - 展示系统上下文、项目上下文、注入记忆、推荐代码文件

### P2：长期演进方向

9. **后台代理与恢复机制**
10. **agent mailbox / send_message**
11. **team/coordinator 模型**
12. **子代理输出安全分类器**
13. **IDE / Web UI 侧运行态可视化**

---

## 15. 一个可执行的落地方向示例

如果只允许先做一个“小版本迭代”，建议优先做下面这个组合：

### 15.1 目标

把 Jarvis 从“提示词驱动的流程约束”升级到“状态驱动的安全执行框架”。

### 15.2 具体范围

- 新增 Agent `mode` 状态
- 实现 plan mode 工具
- 为 `edit_file` / `execute_script` 增加 PermissionContext
- 在 `task_list_manager` 中记录任务状态与当前 mode
- 输出一个当前执行状态面板

### 15.3 预期收益

- 复杂任务更稳
- 非交互模式更安全
- 未来接 Web/IDE 更容易
- 与当前 ARCHER 设计完全兼容

---

## 16. 最终结论

### 16.1 一句话评价

- **Jarvis**：更像一个“工程研究型、规则驱动型、代码分析型”的代码 Agent 平台。
- **Claude Code**：更像一个“状态驱动型、权限内建型、协作产品化”的代码 Agent 系统。

### 16.2 对 Jarvis 最有价值的借鉴方向

最值得学习的不是 Claude Code 的 UI，而是它背后的三件事：

1. **状态机化的 plan/execute 权限切换**
2. **工具层内建权限与编辑安全治理**
3. **角色化多代理协作体系**

### 16.3 对 Jarvis 最重要的坚持方向

Jarvis 不应该放弃自己已经形成优势的部分：

- ARCHER 研究型工作流
- 规则系统与方法论系统
- 分层记忆
- 深度代码分析与验证链

更合理的路线不是“把 Jarvis 做成 Claude Code 的复制品”，而是：

> 保留 Jarvis 在规则、研究、分析、验证上的优势，同时吸收 Claude Code 在状态管理、权限治理、协作系统上的成熟设计。

这会让 Jarvis 更有机会成为一个既适合深度工程研究、又适合稳定代码执行的项目级代码 Agent 平台。

---

## 17. 改进项清单速览

| 优先级 | 改进项             | 当前 Jarvis 状态 | Claude Code 参考点               |
| ------ | ------------------ | ---------------- | -------------------------------- |
| P0     | 显式 Plan Mode     | 仅提示词约束     | `EnterPlanModeTool`              |
| P0     | 工具级权限上下文   | 较弱             | tool permission system           |
| P0     | 编辑鲁棒性增强     | 部分具备         | `FileEditTool`                   |
| P0     | 上下文分层缓存     | 较弱             | `context.ts`                     |
| P1     | 角色化子代理       | 通用子代理       | `AgentTool` built-in agents      |
| P1     | 验证代理产品化     | 有雏形           | verification agent + task update |
| P1     | 任务 hooks / 面板  | 有任务系统       | `TaskCreate/Update/ListTool`     |
| P1     | 上下文可视化       | 基本缺失         | `/context` 方向                  |
| P2     | 后台代理恢复       | 基本缺失         | `resumeAgent` / background agent |
| P2     | agent mailbox      | 基本缺失         | `SendMessageTool` / mailbox      |
| P2     | 子代理交接安全分类 | 基本缺失         | `classifyHandoffIfNeeded`        |

---

## 18. 参考代码位置索引

### Jarvis

- CodeAgent 主类：`src/jarvis/jarvis_code_agent/code_agent.py:72-338`
- CodeAgent 工具列表：`src/jarvis/jarvis_code_agent/code_agent.py:189-228`
- 需求分类与场景提示词：`src/jarvis/jarvis_code_agent/code_agent_prompts.py:22-250`
- 通用 Agent 系统提示词与资源管理：`src/jarvis/jarvis_agent/__init__.py:217-260`
- 通用子代理：`src/jarvis/jarvis_agent/sub_agent.py:22-209`
- 代码子代理：`src/jarvis/jarvis_code_agent/sub_code_agent.py:18-208`
- 任务列表工具：`src/jarvis/jarvis_tools/task_list_manager.py:91-320`
- 代码分析能力导出：`src/jarvis/jarvis_code_agent/code_analyzer/__init__.py:1-69`
- LLM 上下文推荐器：`src/jarvis/jarvis_code_agent/code_analyzer/llm_context_recommender.py:27-260`

### Claude Code

- 项目总览：`../claude-code/README.md:41-271`
- system/user context：`../claude-code/src/context.ts:36-189`
- plan mode：`../claude-code/src/tools/EnterPlanModeTool/EnterPlanModeTool.ts:36-126`
- 文件编辑工具：`../claude-code/src/tools/FileEditTool/FileEditTool.ts:86-260`
- 任务列表：`../claude-code/src/tools/TaskListTool/TaskListTool.ts:33-116`
- 任务创建：`../claude-code/src/tools/TaskCreateTool/TaskCreateTool.ts:48-138`
- 任务更新：`../claude-code/src/tools/TaskUpdateTool/TaskUpdateTool.ts:88-260`
- Agent 工具：`../claude-code/src/tools/AgentTool/AgentTool.tsx`
- Agent 工具辅助：`../claude-code/src/tools/AgentTool/agentToolUtils.ts`
- Agent 运行：`../claude-code/src/tools/AgentTool/runAgent.ts`
