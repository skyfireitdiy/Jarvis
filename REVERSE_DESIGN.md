### 代码反构设计方案

**1. 项目概述**
- **代码功能**：
  - 提供一个可交互的通用 AI 代理系统，具备可插拔的大语言模型平台适配（Platform）、可扩展的工具系统（Tool），以及围绕对话、工具调用、任务流转的统一运行循环（RunLoop）。
  - 支持命令行入口、预定义任务选择、方法论/工具分享、配置向导、会话保存/恢复、事件发布订阅、工具筛选、统计上报、内容截断与文件上传、多种输入处理器等。
- **设计目标**：
  - 语言无关的架构抽象：明确 Platform/Tool/Agent/RunLoop/OutputHandler/InputHandler/Session/EventBus/ShareManager 等组件职责边界。
  - 行为保持一致：严格对齐原有功能、边界条件与错误处理，确保可回归测试通过。
  - 渐进式可重构：模块化分层+插件化扩展，保留工具协议 v1/v2 并行，支持内置/外部/MCP 工具与多平台加载。
  - 可测试与可观测：核心流程具备清晰接口与事件，便于单元测试、集成测试与统计观测。

**2. 架构设计**

**2.1 整体架构**
- **架构模式**：分层 + 插件化
  - 表层：CLI/Bootstrap（jarvis.py、main.py）负责参数解析、环境初始化、入口编排
  - 应用层：Agent 核心与 AgentRunLoop（对话编排、工具调用、用户交互、任务闭环）
  - 能力层：OutputHandler（如 ToolRegistry、EditFileHandler）解析模型输出并执行动作；PromptManager/PromptBuilder 构建系统/附加提示；SessionManager 管理会话与持久化；MemoryManager/TaskAnalyzer/FileMethodologyManager 提供记忆/分析/方法论与文件上传能力
  - 插件层：Platform（jarvis_platform）与 Tool（jarvis_tools），由 Registry 动态加载；ShareManager 支持工具/方法论分享（git 仓库）
  - 跨切面：EventBus 事件系统；统计与输出；配置与每日更新机制；工具筛选（基于模型）
- **设计原则**：
  - 单一职责与清晰边界；以 Protocol/抽象基类约束行为，解耦实现
  - 前向兼容：工具协议 v1.0/v2.0 并存；多来源工具（内置/外部/MCP/中心仓库）
  - 容错与幂等：解析与执行过程尽量降级与提示，避免中断主流程

**2.2 模块设计**
- **模块A：CLI/Bootstrap**
  - 文件：jarvis_agent/jarvis.py, jarvis_agent/main.py
  - 核心职责：
    - 命令行入口、选项解析、配置引导（编辑/交互式）、环境初始化
    - 内置配置选择（agent/multi_agent/roles），Git 仓库检测并可切换子命令
    - 调用 AgentManager 统一启动 Agent 流程
  - 输入输出：命令行参数 → 运行 Agent 并输出用户可视化信息
  - 依赖：配置、AgentManager、fzf、PrettyOutput、init_env、预定义目录
- **模块B：Agent 核心**
  - 文件：jarvis_agent/__init__.py
  - 核心职责：
    - 承载对话、工具调用、附加提示、会话管理、总结与历史清理、事件发布、工具筛选、回调加载等
    - 公共 API：run/save_session/restore_session/set_addon_prompt/get_tool_registry/get_event_bus 等
  - 输入输出：输入用户任务与交互，输出模型响应/工具结果/总结
  - 依赖：PlatformRegistry、SessionManager、ToolRegistry、PromptManager、MemoryManager、TaskAnalyzer、FileMethodologyManager、EventBus、配置与统计
- **模块C：AgentRunLoop**
  - 文件：jarvis_agent/run_loop.py
  - 核心职责：主循环逻辑（调用模型→处理中断→广播播发→工具解析与执行→拼接下一轮→自动完成/用户下一步）
  - 依赖：Agent（委派 _first_run/_call_model/_handle_run_interrupt/_call_tools/_complete_task/_get_next_user_action）
- **模块D：OutputHandlers**
  - 文件：jarvis_agent/output_handler.py, protocols.py, jarvis_tools/registry.py（作为 Tool 输出处理器）
  - 核心职责：基于模型输出判断是否可处理，执行对应逻辑（工具调用、文件编辑等）
  - 代表实现：
    - ToolRegistry: 检测 <TOOL_CALL> 块，解析 YAML，执行工具（v1/v2 兼容）、格式化输出、超长截断/上传，统计上报
    - EditFileHandler: 解析 PATCH/DIFF/SEARCH/REPLACE 块，执行快速文件补丁（唯一匹配校验、缩进容忍、部分成功报告）
  - 依赖：StatsManager、配置、输出、标签工具、临时文件/上传
- **模块E：InputHandlers**
  - 文件：builtin_input_handler.py, shell_input_handler.py
  - 核心职责：在模型调用前预处理用户输入
    - builtin_input_handler: 处理特殊标记 '<Summary>' '<Clear>' '<ToolUsage>' '<ReloadConfig>' '<SaveSession>' 及配置替换映射
    - shell_input_handler: 处理以 '!' 开头的行，组合成脚本，确认后通过 execute_script 工具执行，可选择回注执行结果
  - 返回签名：(processed_message, need_return) 控制是否短路循环
- **模块F：Prompt 系统**
  - 文件：prompt_builder.py, prompt_manager.py, prompts.py
  - 核心职责：
    - PromptBuilder: 汇总 OutputHandler 的 prompt，用于系统工具使用说明
    - PromptManager: 构建系统提示（内含工具用法）与默认附加提示（操作列表、记忆提示、完成标记）
    - prompts.py: 预置模板（默认总结、总结请求、任务分析流程）
- **模块G：Tool 系统**
  - 文件：jarvis_tools/base.py, jarvis_tools/registry.py
  - 核心职责：
    - Tool 抽象（name/description/parameters/func/execute/protocol_version）
    - 工具加载（内置/外部目录/中心仓库/MCP 配置）、use/dont_use 过滤、执行与统计
    - 工具执行结果包装/截断/上传，工具使用帮助（工具列表+系统指南）
- **模块H：Platform 系统**
  - 文件：jarvis_platform/base.py, registry.py
  - 核心职责：
    - BasePlatform 抽象（chat/upload_files/save/restore/name/platform_name/system_prompt 等）
    - 长上下文分批提交流程，UI 渲染（rich）或非美化输出；中断即时返回；think 标签清理
    - PlatformRegistry 动态加载平台类、校验必需方法签名、创建实例、设置模型名
- **模块I：Session 管理**
  - 文件：session_manager.py
  - 核心职责：管理 prompt/addon_prompt/user_data/conversation_length，会话保存/恢复与历史清理
  - 持久化命名：saved_session_{agent}_{platform}_{model}.json
- **模块J：记忆与任务分析**
  - 文件：memory_manager.py, task_analyzer.py
  - 核心职责：
    - MemoryManager：记忆标签提示、自动保存记忆（save_memory 工具检测）、在 addon 提示中注入记忆工具提示；事件订阅（任务开始、清理历史前、任务完成）
    - TaskAnalyzer：任务结束时的任务分析/满意度收集/方法论生成引导（TASK_ANALYSIS_PROMPT），可循环执行工具调用；中断处理（用户补充信息、继续/拒绝工具执行分支）
- **模块K：方法论与文件管理**
  - 文件：file_methodology_manager.py
  - 核心职责：根据平台是否支持文件上传选择处理路径；上传方法论或本地加载方法论文本并注入 prompt；历史通过临时文件上传以减少上下文占用
- **模块L：分享管理**
  - 文件：share_manager.py, tool_share_manager.py, methodology_share_manager.py
  - 核心职责：工具/方法论分享到中心仓库（git），本地资源扫描/用户选择/移动或复制/提交推送；空仓库/未提交变更/网络问题的降级与提示
- **模块M：Agent 管理器**
  - 文件：agent_manager.py
  - 核心职责：封装 Agent 初始化与运行；集成 ToolRegistry、输入处理器，支持恢复会话、预定义任务选择、命令行传入任务优先
- **模块N：配置**
  - 文件：config.py（AgentConfig）、config_editor.py
  - 核心职责：集中解析 Agent 默认配置（从全局配置与上下文推导），配置文件编辑（自动选择系统可用编辑器）
- **模块O：事件系统**
  - 文件：event_bus.py, events.py
  - 核心职责：发布订阅（异常隔离），统一事件常量与 TypedDict 负载类型
- **模块P：工具函数**
  - 文件：utils.py
  - 核心职责：join_prompts、is_auto_complete、normalize_next_action 等基础工具

**2.3 数据架构**
- **数据模型**：
  - Tool：name, description, parameters(schema-like), func/execute, protocol_version
  - ToolCall（逻辑模型）：{name, arguments, want}（嵌入 <TOOL_CALL> YAML 块）
  - Platform：抽象接口（chat, upload_files, save/restore, set_system_prompt, name, platform_name 等）
  - Session：prompt, addon_prompt, user_data, conversation_length
  - Event：主题常量与 TypedDict 负载（工具前后、任务开始/完成、总结前后、历史清理前后、模型调用前后、中断、工具筛选前后）
  - Share 资源：工具文件/方法论 JSON 文件及其元数据（目录、文件名等）
- **数据流向**：
  - 用户输入/任务 → Agent 初始化（工具筛选、文件/方法论处理、记忆标签提示）→ PromptManager 构建 system/addon → Platform.chat → 模型响应 → OutputHandlers（ToolRegistry/EditFileHandler）检测并执行 → 结果回注入 Agent.session.prompt → RunLoop 决策下一轮/完成 → Memory/TaskAnalysis 事件驱动处理
- **存储方案**：
  - 会话文件：.jarvis/saved_session_{agent}_{platform}_{model}.json（由 BasePlatform.save/restore 实现）
  - 工具与平台：数据目录（tools/models）与内置目录；中心工具/方法论仓库 clone 到数据目录；每日自动更新
  - 统计：StatsManager 记录工具（含 edit_file）调用次数
  - 配置：主配置文件；MCP YAML；工具/方法论目录路径

**3. 功能设计**

**3.1 核心功能**
- **功能点1：工具调用解析与执行（TOOL_CALL）**
  - **处理流程**：
    1) ToolRegistry.can_handle 检测 ot("TOOL_CALL")/ct("TOOL_CALL") 标签
    2) 正则提取 YAML，校验字段（name/arguments/want）；缺少结束标签尝试自动补全并校验
    3) 限制一次仅一个工具调用；多条报错
    4) 执行 Tool（v1/v2 兼容，TypeError 回退），统计上报；记录 __last_executed_tool__/__executed_tools__
    5) 格式化 stdout/stderr 为 <stdout>/<stderr>；过长则截断或写临时文件并尝试上传，成功则返回摘要提示
  - **业务规则**：
    - 工具不存在：返回可用工具列表
    - arguments 可为 JSON 字符串（尝试解析）
    - 工具调用前后广播播发 BEFORE_TOOL_CALL/AFTER_TOOL_CALL
    - 工具 use/dont_use 过滤、MCP 工具注册与资源获取
  - **边界条件**：YAML 解析失败、缺少结束标签、多个调用、未知工具、协议不匹配回退、上传失败回退为截断
- **功能点2：文件编辑 PATCH 处理**
  - **处理流程**：
    1) EditFileHandler.can_handle 识别 PATCH 块；解析包含一个或多个 DIFF（SEARCH/REPLACE）对
    2) 对每个目标文件执行快速编辑：唯一匹配校验、保持原格式、支持首尾换行裁剪与缩进容忍重试
    3) 逐文件汇总成功/失败结果；记录 edit_file 调用统计
  - **业务规则**：
    - 搜索文本必须唯一匹配；部分成功时输出详细失败清单
  - **边界条件**：文件不存在自动创建、写入失败、编码问题
- **功能点3：输入处理器链**
  - **处理流程**：
    - builtin_input_handler：处理 '<Summary>/<Clear>/<ToolUsage>/<ReloadConfig>/<SaveSession>' 与配置替换映射；可能短路输出（如 SaveSession 退出）或返回新的 addon 提示
    - shell_input_handler：收集以 '!' 开头的行，strip '# JARVIS-NOCONFIRM' 标记后执行 bash；确认策略（marker 跳过确认或 user_confirm）；可将执行结果拼入后续 prompt
  - **业务规则**：
    - 输入处理器返回 (message, need_return)：need_return=True 时短路主循环
  - **边界条件**：脚本执行失败、确认交互取消、无命令行
- **功能点4：工具筛选（当工具数量超阈）**
  - **处理流程**：
    1) 读取全部可用工具（应用过滤后）与阈值
    2) 以临时模型实例提示工具列表与任务描述，要求仅返回编号列表
    3) 解析数字提取所选工具名 set 到 ToolRegistry
    4) 重新设置系统提示；广播播发 BEFORE_TOOL_FILTER/TOOL_FILTERED
  - **业务规则**：
    - 失败或未选中时保留全量工具并提示
  - **边界条件**：临时模型创建失败、响应非数字
- **功能点5：对话长度管理与历史清理**
  - **处理流程**：
    - 基于 token 计数（输入与响应）控制；超限触发 _summarize_and_clear_history
    - 若平台支持上传：通过 FileMethodologyManager 将历史写入临时文件上传并提示
    - 否则：生成总结（SUMMARY_REQUEST_PROMPT），reset 平台并重新设置系统提示，将摘要作为新上下文
    - 广播播发 BEFORE_HISTORY_CLEAR/AFTER_HISTORY_CLEAR
  - **业务规则**：
    - 清理前如开启 force_save_memory，提示保存重要信息（实际保存由事件驱动的 MemoryManager 决策）
  - **边界条件**：上传失败回退为空提示；生成摘要失败保护
- **功能点6：记忆管理**
  - **处理流程**：
    - prepare_memory_tags_prompt：注入记忆工具提示与现有标签集合
    - add_memory_prompts_to_addon：在系统 addon 指令中加入 save/retrieve memory 使用建议
    - prompt_memory_save：构建提示引导模型调用 save_memory 工具，检测是否已执行保存，输出友好反馈
    - 事件旁路：TASK_STARTED 重置去重标记；BEFORE_HISTORY_CLEAR/TASK_COMPLETED 在强制保存开启时兜底触发
    - _check_and_organize_memory：每日一次检查全局/项目记忆是否需要整理（数量与重叠阈值），提示用户并调用 MemoryOrganizer
  - **业务规则**：
    - 仅在系统已注册相关工具时暴露提示与能力
  - **边界条件**：事件订阅失败不影响主流程；组织器异常降级为提示
- **功能点7：任务分析与方法论引导**
  - **处理流程**：
    - analysis_task：以 TASK_ANALYSIS_PROMPT + 满意度反馈作为 prompt，循环调用模型与工具直到无工具调用
    - collect_satisfaction_feedback：在适当时机向用户收集满意度与文字反馈
    - 中断处理：若在分析期间被中断，询问是否继续执行工具调用，拼接对应提示并继续
    - 事件旁路：BEFORE_SUMMARY/TASK_COMPLETED 时兜底触发一次分析（去重）
  - **业务规则**：
    - 每次仅一个工具调用（在提示中阐明）；保存记忆应先于工具/方法论创建
  - **边界条件**：用户拒绝执行工具调用时，提供替代文本继续分析
- **功能点8：方法论与文件处理**
  - **处理流程**：
    - 支持上传模式：upload_methodology 或上传 files，并注入「上传的文件包含历史信息」等提示
    - 本地模式：load_methodology 并注入「历史类似问题的执行经验」到 prompt
  - **边界条件**：上传失败自动回退本地模式；本地加载失败不阻断任务
- **功能点9：分享管理（工具/方法论）**
  - **处理流程**：
    - ShareManager：clone/pull 更新中心仓库；未提交更改时提示是否丢弃；提交并推送（空仓库设置上游分支）
    - ToolShareManager：从 data/tools 扫描本地工具（排除 __init__.py 与已存在文件），用户多选后「移动」至中心仓库并推送
    - MethodologyShareManager：从方法论目录与用户配置路径扫描 JSON；剔除在中心仓库已存在（按 problem_type+内容）与本地重复项；用户多选后复制到中心仓库并推送
  - **业务规则**：
    - 操作前有明确确认提示；输出批量结果汇总
  - **边界条件**：网络/权限失败时打印友好错误与降级处理
- **功能点10：Agent 管理与任务选择**
  - **处理流程**：
    - initialize：可设置工具组到配置；构造 Agent 并选配输入/输出处理器；可恢复会话
    - run_task：优先使用命令行任务；首次运行时尝试预定义任务选择（fzf 或编号输入）；否则提示用户输入
  - **边界条件**：未初始化 Agent 抛出运行时错误；恢复失败提示但继续

**3.2 算法设计**
- **算法1：TOOL_CALL 提取与校验**
  - 原理：正则按 ot/ct 标签提取；YAML safe_load 校验；缺少结束标签尝试自动补全并校验；限制单条
  - 步骤：提取→解析→字段校验→多条报错→返回结构体与 auto_completed 标志
  - 复杂度：O(n) 按响应长度；解析随数据规模
- **算法2：工具加载（按文件/目录/MCP）**
  - 原理：模块导入与反射查找类属性/execute，check 可选；MCP 客户端列出工具与资源注册
  - 步骤：扫描→导入→属性校验→实例化→注册→过滤
  - 复杂度：O(m+k)
- **算法3：平台加载与校验**
  - 原理：扫描导入 BasePlatform 子类，按 REQUIRED_METHODS 核验签名
  - 步骤：扫描→导入→isclass/issubclass→签名比对→platform_name→注册
  - 复杂度：O(p+q)
- **算法4：长上下文分批提交与 UI 渲染**
  - 原理：按最大 token 切分；前言握手；逐块发送并等待「已收到」；末尾继续；rich 面板增量缓冲输出
  - 步骤：阈值判断→分块→握手→发送→收尾→渲染/中断检查→清理 think 标签
- **算法5：工具协议路由（v1/v2 兼容）**
  - 原理：按 protocol_version 决定参数与 agent 分离；TypeError 回退至 v1 方式
  - 步骤：检查版本→执行→异常回退
- **算法6：输出截断与上传**
  - 原理：上下文超限评估；支持上传则写临时文件上传并清理历史＋摘要提示；否则按行截断
  - 步骤：评估→临时文件→上传→清理→提示/截断
- **算法7：PATCH/DIFF 解析与快速编辑**
  - 原理：正则匹配 PATCH 块与多个 DIFF；唯一匹配定位；首尾换行剥离与缩进重试
  - 步骤：解析→合并文件补丁→唯一替换（一次）→统计成功/失败→写回文件
- **算法8：工具筛选提示解析**
  - 原理：提示模型仅返回编号；正则提取数字；去重并映射为工具名
- **算法9：选择解析（分享管理）**
  - 原理：parse_selection 支持逗号与范围（如 1,2,4-6）；过滤非法项并排序
  - 步骤：分割→解析→范围展开→过滤→排序

**4. 接口设计**

**4.1 外部接口**
- **接口A：TOOL_CALL（模型输出约束）**
  - 输入：<TOOL_CALL> YAML </TOOL_CALL> 块
    - want: 字符串，期望提取或关注的结果
    - name: 工具名称
    - arguments: 对象（或 JSON 字符串）
  - 输出：字符串
    - <stdout> 与 <stderr> 包装；或 <无输出和错误>
    - 过长时截断或返回摘要+上传提示
  - 错误处理：标签缺失/YAML 失败/多个调用/未知工具 → 友好错误+使用指南
- **接口B：PATCH（模型输出约束）**
  - 输入：带 PATCH/DIFF/SEARCH/REPLACE 的结构化块
  - 输出：处理结果汇总（逐文件成功/失败）
  - 错误处理：唯一匹配失败/写入失败/部分成功详情
- **接口C：InputHandler**
  - 签名：(user_input: str, agent: Any) -> Tuple[str, bool]
  - 约定：need_return=True 表示短路主循环（例如 SaveSession/执行脚本后由用户决定是否反馈）
- **接口D：PlatformRegistry**
  - 输入：平台目录；输出：平台类 Map；create_platform(name) 返回实例；get_normal_platform() 提供默认平台
- **接口E：ToolRegistry**
  - 输入：工具目录与配置；输出：工具注册/执行/序列化（Ollama 风格）与统计
- **接口F：SessionManager**
  - 输入：BasePlatform；输出：保存/恢复布尔值；清理历史保留系统提示（reset 平台）
- **接口G：EventBus**
  - 输入：subscribe(event, cb), emit(event, **payload), unsubscribe
  - 说明：回调异常被吞并以保护主流程
- **接口H：ShareManager**
  - 输入：中央仓库 URL、资源列表
  - 输出：clone/pull、选择、提交/推送；工具移动与方法论复制两种策略
  - 错误：git/网络失败打印并降级

**4.2 配置接口**
- **环境配置与键**：
  - 平台：各平台必须的环境变量（BasePlatform.get_required_env_keys/get_env_defaults/get_env_config_guide）
  - 上下文与输出：max_input_token_count、pretty_output、immediate_abort
  - Agent：JARVIS_TOOL_GROUP、是否启用方法论/分析/强制记忆保存等（通过 AgentConfig 解析）
  - 工具：工具加载路径、中心工具仓库（JARVIS_CENTRAL_TOOL_REPO）、MCP 配置（type/command/base_url/name/enable）
  - 方法论：中心方法论仓库（JARVIS_CENTRAL_METHODOLOGY_REPO）、本地方法论目录列表
  - 回调目录：JARVIS_AFTER_TOOL_CALL_CB_DIRS（工具调用后回调加载）
- **参数配置**：
  - CLI 入口：-g/-G/-f/--restore-session/-I/-e 等
  - Agent 定义文件：main.py 中 -c/--agent-definition；-T 初始任务
- **扩展配置**：
  - MCP 客户端类型 stdio/sse/streamable
  - 每日更新：工具与配置目录（git pull）

**5. 实现指导**

**5.1 技术建议**
- **开发语言**：需支持抽象与反射/插件式加载；具备 YAML/JSON 安全解析库；控制台 UI 可选
- **框架选择**：
  - CLI 框架（子命令/参数解析）
  - YAML 解析（safe_load）
  - UI 渲染器（可降级）
- **依赖管理**：
  - 工具/平台的动态加载路径隔离
  - MCP 客户端与中心仓库为可选依赖，失败降级
  - 统计/上传等外设接口提供熔断

**5.2 开发顺序**
- **第一阶段**（核心闭环）
  1) BasePlatform 抽象 + PlatformRegistry 加载/校验
  2) Tool 抽象 + ToolRegistry 加载/执行（v1/v2 路由、格式化/截断上传）
  3) OutputHandler：接入 ToolRegistry 与 EditFileHandler
  4) SessionManager + PromptManager（与现有行为对齐）
  5) Agent 与 AgentRunLoop（编排主循环、事件分发、输入链）
- **第二阶段**（生态与增强）
  1) InputHandlers（builtin/shell）与工具筛选流程
  2) MemoryManager/TaskAnalyzer/FileMethodologyManager 事件旁路集成
  3) ShareManager/ToolShare/MethodologyShare（git 操作）
- **第三阶段**（优化）
  1) 统计、每日更新、中心仓库友好提示
  2) 长上下文/文件上传路径/富 UI 渲染优化
  3) 更多 OutputHandler 扩展点

**5.3 质量保证**
- **测试策略**：
  - 单元测试：
    - TOOL_CALL 解析异常分支（标签缺失/YAML 错误/多条调用/未知工具/JSON 参数解析失败）
    - 工具执行 v1/v2 路由与回退；输出格式与截断逻辑
    - PATCH 解析/唯一匹配/缩进容忍/部分成功报告
    - 平台签名校验与实例化失败降级；会话保存/恢复
    - 输入处理器：特殊标记与 shell 执行确认/跳过确认
    - 工具筛选：阈值触发、编号解析、系统提示重建
    - 事件总线：回调异常隔离；关键事件的发射覆盖
  - 集成测试：
    - AgentRunLoop 全链路（中断与继续/跳过/完成）
    - CLI：预定义任务/fzf 选择/交互式配置/内置配置选择/切换子命令
    - 分享流程：本地扫描→选择→移动/复制→提交/推送（模拟）
  - 回归测试：
    - 提示模板输出快照（系统提示/附加提示/工具指南）
    - 错误提示消息文本一致性
- **性能要求**：
  - 启动期加载工具/平台；必要时懒加载
  - UI 渲染采用批量缓冲减少刷新
  - 大输出走上传/摘要分支
- **安全考虑**：
  - 外部加载目录与导入隔离；sys.path 临时注入后回收
  - YAML/JSON 使用 safe 模式；shell 脚本明确确认与 no-confirm 标记
  - git 操作失败降级提示，避免工作区破坏

**6. 与原代码功能对齐验证**
- **功能对照表**：
  - 工具系统：Tool 抽象、注册/加载（内置/外部/MCP/中心仓库）、v1/v2 执行、统计过滤、结果格式化/截断上传 → 覆盖
  - 平台系统：BasePlatform 抽象、平台加载校验与实例化、模型名设置、对话/上传/保存/恢复/系统消息 → 覆盖
  - 运行循环：调用模型→中断处理→工具解析执行→拼接下一轮→自动完成/用户下一步 → 覆盖
  - 输出处理：OutputHandler 通用接口、ToolRegistry/编辑器处理器、一次一个操作限制 → 覆盖
  - 输入处理：builtin/shell 处理链、短路机制 → 覆盖
  - 会话管理：保存/恢复、清理保留系统提示、用户数据存取 → 覆盖
  - 长上下文/渲染：分批提交、UI 缓冲、think 标签清理、立即中断 → 覆盖
  - 记忆/分析：记忆提示/自动保存/组织器检查、任务分析与满意度反馈 → 覆盖
  - 任务与 CLI：预定义任务加载/选择/补充、内置配置选择、Git 仓库切换、交互式配置、配置编辑 → 覆盖
  - 分享管理：工具与方法论分享、中心仓库 clone/pull/commit/push、冲突与空仓库处理 → 覆盖
  - 工具筛选：阈值触发、临时模型筛选、事件广播 → 覆盖
  - 回调加载：工具调用后回调的动态加载与封装 → 覆盖
- **一致性检查**：
  - 错误提示与边界条件严格遵循原逻辑（多操作检测、YAML 引导、工具不存在提示、PATCH 唯一匹配要求等）
  - PromptManager 复用 get_tool_usage_prompt，系统提示保持一致
  - ToolRegistry.handle_tool_calls 记录执行工具名与列表；Agent 用户数据接口保持
  - 截断/上传逻辑与 context overflow 判断一致；输入链与短路行为一致
- **差异说明**：
  - 抽象更加清晰，保持行为不变；强化了扩展点与事件文档化
  - 将 RunLoop、PromptManager、EventBus、ShareManager、TaskAnalyzer、MemoryManager、InputHandlers 等归一到模块视图，便于重构与测试落地
  - 强调 v1/v2 工具协议与多来源加载的兼容策略，降低迁移风险

---
附注：
- 本设计文档覆盖 jarvis_agent、jarvis_tools、jarvis_platform 的核心文件与扩展模块，面向语言无关实现。
- 开发可按“第一阶段核心闭环→第二阶段生态增强→第三阶段优化”推进，逐步替换内部实现，确保回归一致性。