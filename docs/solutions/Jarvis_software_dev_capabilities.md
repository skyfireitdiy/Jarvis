# Jarvis 在软件开发领域的能力说明

## Jarvis 功能介绍

### 概述与定位
- Jarvis 是一个面向个人开发者的命令行 AI 助手框架，以“工具驱动 + 人机协作”为核心，将 LLM 的思考与本地执行能力结合起来，帮助开发者在需求分析、设计、编码、测试、文档与运维等环节提升效率。
- 相较于固定流程的自动化平台，Jarvis更擅长处理一次性、碎片化、探索式的开发任务，强调从模糊目标快速落地到可验证产出。

### 核心能力总览（面向软件开发方面）
- 代码理解与修改
  - 工具：read_code、PATCH/REWRITE（精确补丁/整文件重写）、execute_script（结合 rg/grep 等）
  - 代理：jarvis-code-agent（jca）对代码任务深度优化，自动分析代码结构与变更、生成精确补丁并迭代
- 自动化 Git 工作流
  - 工具/命令：jarvis-git-commit（jgc）自动生成规范化提交信息；jarvis-git-squash（jgs）交互式 squash 整理历史
- 代码审查与质量
  - 代理/命令：jarvis-code-review（jcr）基于语言清单与 SCRIPPPS 框架输出详尽审查报告
- 脚本生成与执行
  - 代理：脚本生成专家（script-generator）
  - 工具/命令：execute_script（非交互脚本运行）、virtual_tty（交互式终端）、jarvis-smart-shell（jss）自然语言转 Shell
- 安全分析与演进
  - 代理：安全漏洞分析师（security_vulnerability_analyst）定位逻辑/安全问题
  - 多智能体：security_evolution 安全演进流水线（理解/分析/评估/规划/生成/验证/协作），支持多语言代码安全与演进路径输出
- 多智能体协作
  - 命令：jarvis-multi-agent（jma）通过 YAML 定义角色协作，消息驱动路由，实现复杂任务分工协作

### 与软件开发密切相关的部分内置 Agent
- 开源部署专家（opensource-deployment-expert）
  - 将开源项目部署到目标环境
- 重构检查专家（refactor_checker）
  - 校验重构后逻辑与原代码一致性，降低功能回归风险
- 脚本生成专家（script-generator）
  - 根据需求生成各类脚本（运维/工具/测试）
- 安全漏洞分析师（security_vulnerability_analyst）
  - 分析代码逻辑/安全漏洞，定位问题点，必要时与用户澄清风险

### 多智能体配置（部分与开发相关）
- security_evolution
  - 基础软件库安全演进全流程编排（理解/分析/评估/规划/生成/验证/协作），角色涵盖内存/并发/逻辑安全等专家与代码变更工程师、验证工程师等
- researcher
  - 技术研究协作（研究主导/技术专家/实施专家）产出可执行研究报告
- problem_solver
  - 咨询式问题解决流水线（结构化 -> 分析 -> 建议 -> 汇总），适合复杂方案论证与技术/产品选型
- thinker
  - 批判-推理双人协作，强化推理与审辩，适合高风险技术决策的严谨性提升

### 典型工作场景示例
- 场景1：新增功能从需求到提交
  - jca 描述需求 -> 自动定位相关模块与文件 -> 生成补丁/代码 -> 运行基础测试 -> jcr 自查审查 -> jgc 规范提交
- 场景2：Bug 修复与回归
  - jvs/jca 定位错误栈与文件 -> 生成修复补丁（保守最小改动） -> execute_script 运行回归测试 -> jcr 审查边界与接口影响 -> jgc 提交
- 场景3：安全演进专项
  - jma -c builtin/multi_agent/security_evolution.yaml 启动 -> 分角色协作输出缺陷归档、风险评估、演进路线与补丁建议 -> 人机审定与验证

### 人机协作与安全控制
- 执行前确认与中断
  - 高风险操作（执行脚本、修改文件）前可确认；思考后介入：Ctrl+C 打断下一步工具执行并人工裁决
- 非交互模式与超时
  - 自动化场景使用 -n/--non-interactive；execute_script 在非交互下默认 5 分钟超时
- 工具组与模型组
  - 通过工具组（JARVIS_TOOL_GROUPS）限制或精简工具集；通过模型组（JARVIS_LLM_GROUPS）切换平台/模型组合
- 大输出处理
  - 支持上传文件承载大结果或智能截断，避免上下文溢出（ToolRegistry 内置处理）
- 记忆与方法论沉淀
  - 关键节点提示保存记忆（short/project/global），方法论可共享到中心库，团队复用最佳实践


### 边界与注意事项
- Jarvis 更适合一次性与探索式开发任务；对高度固定的流水线，建议编写专用脚本或使用 CI 系统
- 命令执行风险：谨慎对待执行脚本与系统操作；可启用 JARVIS_EXECUTE_TOOL_CONFIRM
- 模型接入风险：使用第三方平台（如腾讯元宝、Kimi）需自担账号风险（参考 README.md 的免责声明）
- 团队功能边界：Jarvis定位为个人助手，不含企业级权限/组织管理能力

### 常用命令与工具（开发相关）
- 通用/代码：jvs、jca、read_code、execute_script、PATCH/REWRITE
- 审查/提交：jcr、jgc、jgs
- 多代理/角色：jma、jpm role
- 知识/记忆/方法论：jrg、jm、save_memory/retrieve_memory/clear_memory、jmo
- 终端与脚本：jss、virtual_tty、jt（工具清单/调用/统计）、jst（使用统计）

### 结语
- 通过“思考-行动-观察”循环与工具驱动执行，Jarvis 为软件开发全过程提供可验证、可协作、可扩展的智能支持。结合记忆与方法论沉淀，它不仅是一个助手，更是持续进化的开发伙伴。

## 为什么没有使用Cursor，而是使用Jarvis

Jarvis 使用命令行界面，并且是完全自主开发，定制与修改方便，其他工具固然强大，但其实现为黑盒，难以定制优化。并且 Cursor 无法使用公司自研模型，敏感代码存在信息安全风险。