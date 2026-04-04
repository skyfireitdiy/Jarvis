# Jarvis CodeAgent 功能补充方案与实施计划

## 1. 文档目标

本文档在《`docs/compare/jarvis_vs_claude_code_agent.md`》对比分析结论的基础上，给出 Jarvis CodeAgent 的下一阶段功能补充方案与实施计划。

本计划坚持以下总原则：

> **保留 Jarvis 在规则、研究、分析、验证上的优势，同时吸收 Claude Code 在状态管理、权限治理、协作系统上的成熟设计。**

本文不是代码实现文档，而是后续架构演进和迭代开发的统一规划文档，用于指导后续分阶段实施。

---

## 2. 演进目标

Jarvis 当前已经具备较强的项目级代码分析与任务执行能力，尤其在以下方面具有明显优势：

- **规则系统强**：支持 `load_rule`，可沉淀最佳实践、架构原则与任务约束
- **研究型工作流强**：ARCHER 流程适合复杂代码研究、项目反构、技术调研与方案对比
- **代码分析能力强**：具备上下文推荐、依赖分析、影响分析、构建验证、lint 与 post-process
- **验证链较完整**：具备 review、task_list_manager、verification agent 等基础设施
- **记忆体系成熟**：具备短期/项目长期/全局长期三层记忆能力

但从产品化执行、安全治理和多代理协作的角度看，仍存在以下不足：

- 计划阶段与执行阶段的系统状态边界不够清晰
- 工具权限控制主要依赖提示词与人工确认，缺少统一权限上下文
- 子代理存在，但还不是完整的协作系统
- 上下文管理偏重“实时分析”，缺少稳定的分层缓存与可视化
- 编辑工具在路径治理、并发写保护、文件状态校验方面还有增强空间

因此，本轮功能补充的目标不是重写 Jarvis，而是让 Jarvis 完成一次**从“工程能力强”到“工程能力强 + 状态治理强 + 协作能力强”**的升级。

---

## 3. 总体设计原则

### 3.1 保留项原则

以下能力属于 Jarvis 核心优势，后续演进中必须保留并继续强化：

1. **规则优先**
   - 继续保持 `load_rule`、项目规则、组织规则、专项规则的优先级
   - 新能力不得绕过规则系统独立生长

2. **研究型工作流优先**
   - ARCHER 仍然作为复杂技术任务的主流程
   - 新增状态机不应削弱 ANALYZE / COLLECT / REVIEW 的深度要求

3. **分析与验证优先**
   - 新能力必须服务于更安全、更可验证的代码修改
   - 必须保留影响分析、构建验证、静态检查、验证代理等机制

4. **记忆与方法论优先**
   - 记忆系统和方法论系统是 Jarvis 差异化能力，不应被弱化
   - 后续应将其更深地嵌入执行流程，而不是边缘化

### 3.2 吸收项原则

Claude Code 的下列成熟设计值得吸收，但要以 Jarvis 架构为中心做本地化改造：

1. **状态管理**：引入显式执行状态，而不是仅靠提示词约定
2. **权限治理**：把权限判断沉到工具层，而不是仅靠模型自律
3. **协作系统**：把子代理从“一次性子任务执行”升级为“角色化协作单元”
4. **上下文基础设施化**：从实时搜索增强到“分层缓存 + 自动注入 + 可视化”
5. **运行态可观测性**：任务、代理、模式、验证状态要可展示、可追踪

### 3.3 演进方式原则

- 不做一次性大重构
- 优先采用**增量演进**
- 每一阶段都要有可落地的最小闭环
- 每一阶段都必须可验证、可回退、可继续扩展

---

## 4. 目标能力蓝图

本次功能补充计划，建议围绕以下五条主线展开：

### 4.1 主线 A：状态管理升级

目标：让 Jarvis 从“流程提示词驱动”升级为“状态驱动执行”。

关键能力：

- 引入 Agent 执行状态模型
- 引入显式 Plan Mode / Execute Mode / Review Mode
- 让计划阶段真正只读，执行阶段才允许修改
- 状态变化可被记录、展示、验证

### 4.2 主线 B：权限治理升级

目标：让 Jarvis 的工具系统具备统一权限上下文，降低误操作与越权写操作风险。

关键能力：

- 工具调用前执行权限判定
- 路径级读写控制
- shell 命令风险分级
- 非交互模式下的自动判定策略

### 4.3 主线 C：协作系统升级

目标：把现有 `sub_agent` / `sub_code_agent` 升级为角色化、可追踪、可验证的协作体系。

关键能力：

- 角色化子代理类型
- 子代理输出结构统一
- 子代理结果回传、验证、汇总机制
- 后续支持 mailbox / background / coordinator

### 4.4 主线 D：上下文系统升级

目标：在保持 Jarvis 深度分析能力的同时，补齐轻量、缓存化、稳定注入的上下文基础设施。

关键能力：

- system context / project context / task context 分层
- 上下文缓存与增量刷新
- 项目设计文档与规则自动注入
- 上下文可视化

### 4.5 主线 E：可观测性与验证升级

目标：让任务执行态、子代理状态、权限状态、上下文状态、验证状态都能被可视化和追踪。

关键能力：

- 当前 mode 展示
- 当前任务列表摘要
- 当前上下文来源展示
- 当前 diff / 风险 / 验证结果展示
- 任务 hooks 与验证 hooks 联动

---

## 5. 推荐架构增量设计

### 5.1 新增统一运行态对象：ExecutionContext

建议新增统一运行态上下文对象，例如：

- `mode`: 当前执行模式（analyze / plan / execute / review）
- `permission_context`: 当前权限上下文
- `task_context`: 当前任务、依赖、阶段状态
- `context_layers`: 当前系统上下文、项目上下文、任务上下文
- `verification_state`: 当前验证状态
- `risk_level`: 当前风险级别

用途：

- 让 Agent、CodeAgent、工具、task_list_manager 共用同一运行态
- 让“模式切换 / 权限判断 / 输出展示”具备统一依据

### 5.2 新增统一权限对象：PermissionContext

建议新增统一权限对象，用于工具层执行前判定：

- `mode`: default / plan / execute / dangerous
- `file_read_rules`
- `file_write_rules`
- `shell_rules`
- `network_rules`
- `interactive_policy`
- `non_interactive_policy`

其核心职责：

- 在工具调用前做统一裁决
- 为 `edit_file`、`execute_script`、`virtual_tty`、未来的 write 类工具提供一致约束

### 5.3 子代理统一抽象：AgentRole / AgentTask

建议把子代理从“工具调用参数”提升到统一抽象：

- `agent_role`: explore / plan / implement / verify
- `task_goal`
- `task_scope`
- `allowed_tools`
- `required_output_schema`
- `handoff_policy`

这样后续无论是同步子代理、后台子代理还是 team agent，都可以复用同一抽象。

### 5.4 上下文层统一抽象：ContextLayers

建议把上下文分为：

1. **System Context**
   - 当前目录
   - git 状态摘要
   - 当前分支
   - 最近提交
   - 当前工具可用性

2. **Project Context**
   - 项目总览
   - 规则摘要
   - `project_info` 文档摘要
   - 项目长期记忆

3. **Task Context**
   - 当前任务计划
   - 当前任务列表摘要
   - 当前推荐文件与符号
   - 最近编辑文件
   - 当前 diff 摘要

这样可以兼顾：

- Jarvis 现有深度分析能力
- Claude Code 风格的稳定注入与缓存

---

## 6. 分阶段实施计划

以下采用 **Phase 1 / Phase 2 / Phase 3** 的方式推进。

---

## 7. Phase 1：状态治理与安全基础设施

### 7.1 目标

建立最小可用的状态管理与权限治理基础，让 Jarvis 从“靠提示词约束”进化为“系统状态约束 + 工具权限裁决”。

### 7.2 核心交付

1. **引入 Agent Mode 状态模型**
   - 新增 mode 字段
   - 初始支持：`analyze` / `plan` / `execute` / `review`

2. **新增显式 Plan Mode 工具**
   - `enter_plan_mode`
   - `exit_plan_mode`

3. **新增 PermissionContext**
   - 允许 plan mode 下只读工具调用
   - 禁止写工具与危险脚本

4. **增强 edit_file / execute_script 工具保护**
   - 路径规则
   - 文件大小限制
   - 文件状态校验（mtime/hash）
   - 高风险命令识别

5. **执行态面板初版**
   - 显示 mode、当前任务、权限状态、上下文来源摘要

### 7.3 影响模块

- `src/jarvis/jarvis_agent/`
- `src/jarvis/jarvis_code_agent/`
- `src/jarvis/jarvis_tools/`
- `src/jarvis/jarvis_utils/`

### 7.4 推荐拆分

#### 子模块 1：Mode 状态管理

建议位置：

- `jarvis_agent` 基座层

建议内容：

- 定义 mode enum
- 提供 mode 切换 API
- 与 system prompt / run loop 集成

#### 子模块 2：PermissionContext

建议位置：

- `jarvis_tools` 或 `jarvis_agent` 共享层

建议内容：

- 统一工具权限判断接口
- 提供按 mode 判定逻辑
- 提供非交互模式的自动策略

#### 子模块 3：工具安全增强

建议位置：

- `edit_file`
- `execute_script`
- `virtual_tty`

建议内容：

- 编辑前校验
- 路径标准化
- 高风险命令拦截
- 文件并发修改检测

### 7.5 风险

- 修改 Agent 基座可能影响现有行为
- 工具权限收紧后可能暴露旧流程中对危险行为的隐式依赖
- 非交互模式下如果策略过严，可能降低自动化完成率

### 7.6 缓解措施

- 默认以兼容模式上线
- 先记录权限判定结果，再逐步启用强拦截
- 为 plan mode 和 execute mode 提供清晰日志输出

### 7.7 验收标准

- Agent 可以明确报告当前 mode
- plan mode 下无法直接编辑文件
- `edit_file` 和 `execute_script` 能执行权限判定
- 高风险路径与命令能被拒绝或要求确认
- 执行态面板可显示当前模式与权限状态

---

## 8. Phase 2：协作系统与验证系统升级

### 8.1 目标

在 Phase 1 的基础上，将子代理、任务系统与验证机制整合为角色化协作系统。

### 8.2 核心交付

1. **角色化子代理**
   - explore agent
   - plan agent
   - implement agent
   - verify agent

2. **统一子代理输出协议**
   - 结构化结果
   - 关键发现
   - 风险说明
   - 可验证产出位置

3. **验证代理产品化**
   - task 完成后自动触发 verify agent
   - 验证失败回写任务状态

4. **task hooks 初版**
   - on_task_created
   - on_task_started
   - on_task_completed
   - on_task_verified

5. **任务与 diff/文件集联动**
   - 任务自动记录相关文件
   - 任务结束输出变更摘要

### 8.3 影响模块

- `src/jarvis/jarvis_agent/sub_agent.py`
- `src/jarvis/jarvis_code_agent/sub_code_agent.py`
- `src/jarvis/jarvis_tools/task_list_manager.py`
- `src/jarvis/jarvis_agent/`
- `src/jarvis/jarvis_code_agent/`

### 8.4 推荐拆分

#### 子模块 1：AgentRole 定义

- 定义角色
- 配置默认工具集
- 配置默认系统提示词

#### 子模块 2：统一 handoff 输出格式

建议结构：

- `summary`
- `findings`
- `modified_files`
- `risks`
- `verification_suggestions`

#### 子模块 3：验证自动化

- 子任务完成后自动进入 verify 阶段
- 将验证结果写回 task_list_manager

### 8.5 风险

- 子代理行为差异会增加调试复杂度
- 任务与代理双系统若设计不好，容易职责重叠
- 自动验证可能增加 token 与执行成本

### 8.6 缓解措施

- 先实现少量内建角色，不一开始铺开 team 协作
- 统一输出协议，降低代理差异带来的复杂度
- 验证代理仅在复杂任务或显式标记任务中默认启用

### 8.7 验收标准

- 可以显式创建不同角色的子代理
- 子代理输出结构统一
- task 完成后支持自动验证
- 验证结果能回写任务状态
- 任务可展示关联文件和变更摘要

---

## 9. Phase 3：上下文系统与运行态可观测性升级

### 9.1 目标

把 Jarvis 的上下文能力从“强分析”继续升级为“强分析 + 强上下文基础设施 + 强可视化”。

### 9.2 核心交付

1. **ContextLayers 分层实现**
   - system context
   - project context
   - task context

2. **上下文缓存与增量刷新**
   - git 状态变化触发刷新
   - 文件变更触发 task context 刷新
   - 规则变化触发 project context 刷新

3. **上下文可视化工具**
   - 查看当前注入上下文
   - 查看当前任务上下文来源
   - 查看当前推荐文件/符号

4. **项目文档自动注入**
   - `.jarvis/rules/project_info/README.md`
   - 关键模块设计文档
   - 任务相关规则摘要

5. **运行态面板增强版**
   - 当前 mode
   - 当前 task
   - 当前 context layers
   - 当前 diff 状态
   - 当前 verification 状态
   - 当前风险级别

### 9.3 影响模块

- `src/jarvis/jarvis_code_agent/code_analyzer/`
- `src/jarvis/jarvis_agent/`
- `src/jarvis/jarvis_utils/`
- `docs/`

### 9.4 风险

- 上下文层过多，可能导致注入膨胀
- 缓存失效策略处理不好，可能造成过时信息误用
- 可视化做得太重会影响 CLI 简洁性

### 9.5 缓解措施

- 先做摘要级注入，不直接注入整份文档
- 缓存对象增加版本与失效时间
- CLI 先做轻量文本面板，避免过早复杂 UI 化

### 9.6 验收标准

- 上下文被分层管理
- 常用上下文可缓存且可刷新
- 可以查看当前上下文来源与摘要
- 项目设计文档可作为上下文来源被自动使用
- 执行态面板可展示上下文与验证信息

---

## 10. 长期方向（Phase 4+）

在前三阶段稳定后，再考虑以下长期能力：

1. **后台代理与恢复机制**
2. **agent mailbox / send_message**
3. **team / coordinator 协作模型**
4. **worktree 隔离执行**
5. **子代理输出安全分类器**
6. **IDE / Web 统一运行态展示**
7. **自动记忆提炼与自动任务归档**

这些方向不建议过早推进，否则会增加系统复杂度并稀释当前主目标。

---

## 11. 优先级建议

### P0（最先做）

- 显式 Plan Mode
- Agent 状态模型
- PermissionContext
- `edit_file` / `execute_script` 安全增强
- 执行态面板初版

### P1（第二批）

- 角色化子代理
- 验证代理产品化
- task hooks
- 任务与 diff/文件关联

### P2（第三批）

- ContextLayers
- 上下文缓存
- 上下文可视化
- 项目文档自动注入

### P3（长期）

- 背景代理
- 协作邮箱
- coordinator 模型
- worktree 隔离
- 更强 UI/IDE 集成

---

## 12. 实施顺序建议

建议采用以下顺序推进，而不是按模块并行大改：

1. **先做状态管理，再做权限治理**
   - 没有状态，就没有权限模式的依据

2. **先做权限治理，再做协作系统**
   - 没有权限约束，多代理协作风险会被放大

3. **先做协作系统，再做上下文系统增强**
   - 多代理对上下文抽象的要求更明确，先协作后上下文更容易收敛

4. **可观测性贯穿全过程**
   - 每个阶段都至少补基础状态展示，防止系统演进后不可调试

---

## 13. 模块影响地图

| 模块                              | 影响方向 | 主要职责                                           |
| --------------------------------- | -------- | -------------------------------------------------- |
| `jarvis_agent`                    | 高       | mode、运行态、状态展示、基座扩展                   |
| `jarvis_code_agent`               | 高       | 代码任务流程、上下文整合、plan/execute/review 绑定 |
| `jarvis_tools`                    | 高       | 权限判定、任务 hooks、工具级安全治理               |
| `jarvis_code_agent/code_analyzer` | 中       | 上下文分层、缓存、文档注入                         |
| `jarvis_utils`                    | 中       | 配置、缓存、风险分类、全局共享工具                 |
| `docs`                            | 中       | 项目设计文档与实施路线维护                         |

---

## 14. 风险总览

### 14.1 主要风险

1. **演进范围过大，导致阶段失焦**
2. **状态机与现有 prompt 流程不一致**
3. **权限系统过严导致自动化效率下降**
4. **协作系统复杂度过快上升**
5. **上下文系统新增后 token 成本上升**

### 14.2 缓解策略

1. 坚持分阶段交付
2. 先兼容、后收紧
3. 先做只读/高风险能力的限制，不一次性全拦
4. 先做角色化子代理，不立刻做 team/coordinator
5. 上下文一律先做摘要，再做深度自动注入

---

## 15. 每阶段验收方式

### Phase 1 验收

- 读取关键代码位置，确认 mode 与 permission context 已引入
- 验证 plan mode 下无法执行写操作
- 验证 `edit_file` / `execute_script` 可输出明确权限判定结果
- 验证执行态面板能反映当前模式与权限状态

### Phase 2 验收

- 验证可以创建不同角色子代理
- 验证子代理输出结构统一
- 验证 task 完成后可自动进入验证流程
- 验证验证结果能反馈到任务状态

### Phase 3 验收

- 验证上下文已按 system/project/task 分层
- 验证上下文缓存存在且可失效
- 验证可以查看当前上下文来源摘要
- 验证项目设计文档可被自动作为上下文来源使用

---

## 16. 建议的第一轮落地切片

如果只启动一轮短周期功能补充，建议范围控制在以下内容：

### 16.1 必做

- 新增 mode 状态模型
- 新增 `enter_plan_mode` / `exit_plan_mode`
- 为 `edit_file` 增加基础路径保护与文件状态校验
- 为 `execute_script` 增加只读/高风险分类
- 增加轻量执行态面板

### 16.2 暂缓

- mailbox
- background agent
- team/coordinator
- worktree 隔离
- 复杂 UI

### 16.3 原因

这组改动最能体现：

- 保留 Jarvis 原有研究与分析优势
- 吸收 Claude Code 的状态管理与权限治理能力
- 风险可控
- 易形成最小闭环

---

## 17. 最终结论

Jarvis 下一阶段最正确的方向，不是复制 Claude Code，而是做一次**差异化增强**：

- **坚持 Jarvis 的规则、研究、分析、验证优势**
- **吸收 Claude Code 的状态管理、权限治理、协作系统经验**
- **通过分阶段演进，把 Jarvis 从“分析能力强的代码 Agent”升级为“分析强 + 治理强 + 协作强的项目级代码 Agent 平台”**

本计划建议先完成 Phase 1，再根据实施效果决定是否推进 Phase 2 和 Phase 3 的深水区能力。

---

## 18. 后续配套文档建议

建议后续继续补充以下文档：

1. `jarvis_code_agent_state_model_design.md`
   - 专门说明 mode 状态机设计

2. `jarvis_permission_context_design.md`
   - 专门说明权限判定模型与工具接入规范

3. `jarvis_agent_role_collaboration_design.md`
   - 专门说明角色化子代理方案

4. `jarvis_context_layers_design.md`
   - 专门说明上下文分层与缓存策略

5. `jarvis_execution_observability_design.md`
   - 专门说明运行态可视化与状态展示方案
