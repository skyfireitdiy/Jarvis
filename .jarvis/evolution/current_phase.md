# 当前进化阶段

**阶段名称**：阶段 A - 自我进化闭环（效率优先）
**开始时间**：2026-10-04
**预计完成**：待定（约 4-6 周）
**当前进度**：A3 已完成，A1/A2 已回退（详见下文）

**阶段目标**：让 Jarvis 形成「需求澄清 → 主动建议 → 跨会话学习」的闭环，越用越聪明、越用越高效。

---

## 现状说明（2026-10-04 核实）

> ⚠️ **重要**：本文件此前（2026-02-01 版）记录了大量「已完成」的组件与模块，经 2026-10-04 源码核查，**绝大多数并不存在**（如 jarvis_arch_analyzer、jarvis_auto_fix、knowledge_graph_tool、smart_advisor_tool、DialogueManager、EmotionRecognizer、AutonomousManager 等）。本文件已重写，如实反映真实状态。

### ✅ 实际已实现的核心能力（真实存在）

| 模块/能力                                                       | 说明                                                                                                         |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| jarvis_agent                                                    | Agent 运行循环（run_loop）、会话管理、任务分析、上下文压缩、模型切换                                         |
| jarvis_code_agent                                               | 代码审查（CodeReviewer）、构建验证（BuildValidator）、lint 自动修复、影响分析（ImpactAnalyzer）、diff 可视化 |
| jarvis_code_agent.code_analyzer                                 | 依赖分析、符号表数据库（SymbolTableDB）、图遍历（GraphTraverser）、上下文推荐                                |
| jarvis_memory_organizer                                         | 记忆整理、智能语义检索（smart_retrieval）                                                                    |
| jarvis_methodology                                              | 方法论（可复用解法库）管理                                                                                   |
| jarvis_rules_index                                              | 规则索引与加载                                                                                               |
| jarvis_tools                                                    | 30 个内置工具（代码编辑、执行、搜索、浏览器、daemon 等）                                                     |
| jarvis_platform                                                 | 多平台接入（OpenAI/Claude/JEV 等）                                                                           |
| jarvis_sec                                                      | 安全扫描（C/Rust 等）                                                                                        |
| jarvis_lsp / jarvis_mcp / jarvis_git_utils / jarvis_smart_shell | 语言服务器 / MCP / Git / 智能 Shell                                                                          |
| 子代理 / 元代理                                                 | sub_agent、sub_code_agent、meta_agent（可生成新工具）                                                        |
| 技能发现                                                        | skill_discovery（搜索/安装技能）                                                                             |

---

## 当前任务（阶段 A）

- [x] A1. 需求澄清与意图理解（P0）⚠️ 已回退（2026-10-05）
  - ~~动手前识别「需求是否明确」，含糊时主动澄清~~（已回退：与大模型原生澄清能力重复，且固定规则误报损害体验）
  - 识别任务类型，选择对应执行策略
- [x] A2. 主动服务 / 主动建议（P0）⚠️ 已回退（2026-10-05）
  - ~~任务完成后主动给出「下一步建议」~~（已回退：提醒类功能价值有限，可能轻微冗余）
  - ~~发现重复劳动时主动提醒沉淀为方法论/工具~~（已回退）
- [x] A3. 跨会话持续学习（P0）✅ 已完成（2026-10-05）
  - 任务开始前自动检索相关历史经验
  - 任务结束后自动判断并沉淀值得保留的经验
- [x] A4. 进化状态修正（P0 前置）✅ 已完成（2026-10-04）
  - 修正 current_phase.md 中与事实不符的「已完成」标记
  - 重写 evolution_plan.md 为效率优先的 A/B/C 阶段

---

## 遇到的问题

- 旧版进化状态文档（current_phase.md / evolution_plan.md）存在大量与源码不符的「已完成」记录，已核实并修正。
- 旧计划中的「架构分析、自动修复、知识图谱、智能顾问」多数已被现有 code_analyzer / code_agent_lint / code_reviewer 覆盖，无需重复建设（详见 evolution_plan.md 复核表）。

---

## 自由进化会话（2026-10-05）

> Administrator 授权的一次自由进化会话（不设限、允许任意手段），目标「充分进化当前系统，以实现高效、智能的 AI 智能体」，并留下进化路线与日志。完整日志见 `free_evolution_20261005.md`。

### ✅ 本次会话完成的进化项

1. **Agent 状态变更 WebSocket 广播**（commit 3396dcb）：实现 `_on_agent_status_change`（原 TODO 空实现），Agent 生命周期状态（stopped/deleted/error）实时广播到前端。
2. **修复 15 个 ruff 代码质量问题**（commit 85db0cc / 6ba8d44 / 4393e67）：`ruff check src/jarvis/` 现为 0 错误。
3. **验证 daemon self-update ARM 修复完整性**（commit f757bbf4）：完整复核，linux/arm 构建与测试全通过。

### ✅ 第二轮进化（2026-10-05 晚）—— 完成 A3，A1/A2 已回退

1. **A3 跨会话主动检索增强**：`memory_manager.py` 新增 `prepare_memory_context_prompt(user_input)`，用 `SmartRetriever.semantic_search` 检索 `project_long_term`/`global_long_term` 记忆（limit=5，单条截断 500 字符），在 `_first_run` 中调用并注入会话 prompt。跨会话学习不再依赖模型自觉。测试 7 个用例。
2. **A2 主动建议机制（已回退）**：曾实现 `Agent._generate_proactive_suggestions`，经 Administrator 评审后回退。原因：提醒类功能价值有限，可能轻微冗余。已删除方法定义、调用及测试。
3. **A1 需求澄清增强（已回退）**：曾实现 `requirement_clarifier.py` 与 `Agent._clarify_ambiguous_requirement`，经 Administrator 评审后回退。原因：与大模型原生澄清能力重复（模型本就会在需求不清时主动询问），且固定规则在"明天西安天气"等语义完整需求上误报，制造"蠢"的体验。已删除相关代码与测试。

### ✅ 第三轮进化（2026-10-05 深夜）—— 审计系统（可配置、默认关闭）

1. **审计系统**：新增 `src/jarvis/jarvis_audit/` 模块，提供 `AuditLogger`（写入 `~/.jarvis/audit/YYYY-MM-DD.jsonl`，JSONL 格式，敏感字段脱敏，进程安全追加）与 `log_event()` 统一入口。新增 `enable_audit` 配置项（`config.py` 的 `is_enable_audit()`，默认 `false`；`config_schema.json` 同步）。Agent 层接入 4 个审计点：`run()` 记录 `user_input`、`_call_tools` 与 `_execute_pending_native_calls` 记录 `tool_call`、`_complete_task` 记录 `task_completed`。全部惰性导入 + 异常静默，默认关闭零开销。测试 6 个用例。
2. **审计系统缺陷修复**：① `_redact` 由精确匹配改为子串匹配（新增 `_is_sensitive_key`），覆盖 `api_key`/`access_token`/`secret_key`/`client_secret` 等复合敏感键；② `_call_tools` 新增 `_extract_tool_arguments` 从文本协议 response 解析 arguments 字典传入 `_audit_log`，使文本协议工具调用的敏感值也能正确脱敏（解析失败静默返回空字典）；③ `evolution_history.json` 末尾补换行。审计测试增至 8 个用例。
3. **审计系统审查修复**：① `_call_tools` 不再记录原始 response 字符串，改为仅记录 `tool_name` + 已脱敏 `arguments` 字典，杜绝 `data.response` 中敏感明文泄露；② 新增 `_is_audit_enabled` 前置检查（读取 `config.is_enable_audit`），默认关闭时不执行 `_extract_tool_arguments` 解析，保证严格零开销。审计测试增至 10 个用例。

### ✅ 第四轮进化（2026-10-06 凌晨）—— 任意代码热补丁 hotpatch

1. **hotpatch 热补丁工具**：新增 `src/jarvis/jarvis_tools/hotpatch.py`（`HotpatchTool`，经 `_load_builtin_tools` 自动注册）。两种使用方式：
   - **方式① 生效已修改代码**：`module_name` 热更新已有模块（支持逗号分隔**批量多模块**）；reload 后自动用 `gc.get_objects()` 把旧类实例 `__class__` **重绑到新类**，使已有类实例的新方法立即生效（用户明确要求）。
   - **方式② 临时注入代码**：`code` 注入任意语句/代码块/函数/全新模块（不落盘、不持久化），命名空间注入 `agent`/`sys`/`globals`，可访问/修改 **agent 内外任意对象**。
2. **关键坑解决**：`importlib.reload` 会复用**过期 `.pyc` 字节码缓存**，导致源码已改但 reload 后仍是旧代码。实现 `_clear_pycache`（reload 前 `shutil.rmtree` 清理 `__pycache__`）强制重新编译，否则"修改后立即生效"失效。
3. **方案文档**：`.jarvis/evolution/decisions/hotpatch_design.md` 完整记录两种方式、多模块、实例自动切换、reload 生效边界（正在执行的调用不生效）、命名空间注入设计。

### ✅ 第五轮进化（2026-10-06 凌晨）—— 调研 Agent 评测基准，评估自进化量化标尺

1. **调研业界公认 Agent 评测基准**：确认 Claude Code 与 Codex 都在公开报告的编码 Agent 测试集为 **SWE-bench Verified**（最权威编码能力标尺，OpenAI 联合创建）+ **Terminal-Bench**（真实终端任务）。
2. **深入调研 Terminal-Bench 2.0 接入方式**：评测框架 **Harbor**（`pip install harbor`），任务在隔离 Docker 容器执行（`task.toml`/`instruction.md`/`Dockerfile`/`solve.sh`/`tests`，验证产出 `reward.txt` 0/1）。命令：`harbor run --dataset terminal-bench@2.0 --agent <oracle|terminus-2|claude-code> --model ... --n-concurrent N`。自定义 Agent 需 subclass `BaseInstalledAgent`/`BaseAgent`（参考 `claude_code.py`）。
3. **路线决策（未写代码）**：TB 与 Jarvis `execute_script`/终端能力高度契合，可作自进化量化标尺（进化前后对比 reward 通过率）；但接入需写 Harbor 适配层 + Docker 环境，属大工程，且是"评估能力"而非"增强能力"本身，短期 ROI 低于直接增强。**决策：后置为长期量化标尺**，当前聚焦更高 ROI 进化方向。

### ✅ 第六轮进化（2026-10-06 凌晨）—— 实现 Terminal-Bench 2.0 Harbor 适配层（自进化量化标尺）

1. **Harbor 适配层**：新增 `src/jarvis/jarvis_eval/harbor_agent.py`（`JarvisInstalledAgent` 继承 Harbor `BaseInstalledAgent`）+ 轻量 `__init__.py` + `tests/jarvis_eval/test_harbor_agent.py`（11 个单元测试）。方案从第五轮调研的 `BaseAgent`（外部 agent + 命令重定向）改为 **`BaseInstalledAgent`（jca CLI 装进容器）**——Administrator 指出 Jarvis 有命令行工具 jca，Agent loop 跑在任务容器内，与 Harbor 隔离模型天然契合，大幅简化。
2. **适配层要点**：`install()` 容器内 `pip install jarvis-ai-assistant`；`run()` 用 `@with_prompt_template` 把 instruction base64 写入容器文件后调 `jca -n --task-file`；`_build_passthrough_env` 透传 11 个 API key 环境变量（OPENAI_API_KEY 等）使容器内 jca 能访问模型 API。
3. **关键技术决策**：顶层 import harbor（Harbor `import_class` 要求类是 `type` 而非工厂函数）；`__init__.py` 保持轻量不 import harbor，Jarvis 主项目 import `jarvis_eval` 包安全；`# type: ignore` 需用通用形式（`[unresolved-import]` 对 ty 不生效）；`BaseInstalledAgent._exec` 自动加 `set -o pipefail`（run 命令不再自己加）；`jca -n --task-file` 非交互模式读任务（不需要 `-w` worktree）。
4. **方案文档**：`.jarvis/evolution/decisions/terminal_bench_adapter.md` 完整记录选型、实现、验证、运行命令（`harbor run --dataset terminal-bench@2.0 -a jarvis_eval.harbor_agent:JarvisInstalledAgent --ae OPENAI_API_KEY=...`）与边界。

### 验证结果

- 全套测试：**1404 passed, 0 failed**（第一轮）；`tests/jarvis_agent/` **233 passed**（第二轮回退后，仅 A3 保留 7 用例）；`tests/jarvis_audit/` **10 passed**（第三轮审计系统 + 复合敏感键脱敏 + response 明文修复）
- 第四轮：`tests/jarvis_tools/test_hotpatch.py` **12 passed**；`tests/jarvis_tools/` 全套 passed；`tests/jarvis_agent/` 全套 passed（无回归）；hotpatch 相关 ruff 0 错误
- 第六轮：`tests/jarvis_eval/test_harbor_agent.py` **11 passed**（有 harbor）+ **1 skipped**（无 harbor 正确跳过）；Harbor `import_class` 加载验证通过（name()=jarvis，是 `BaseInstalledAgent` 子类）；无 harbor 时 `import jarvis.jarvis_eval` 安全；`tests/jarvis_agent/` 全套 passed（无回归）
- ruff：**0 错误**（注：全量 ruff 有 5 个预存 F401 错误在 `tests/jarvis_code_agent/` 与 `tests/jarvis_web_gateway/`，与本轮改动无关）

---

## 进度说明

- 阶段 A 已启动，A4（状态修正）已完成。
- 自由进化会话（2026-10-05）已完成：WebSocket 广播、ruff 清理、daemon ARM 验证。
- 第二阶段自由进化（2026-10-05 晚）完成 A3（跨会话学习）；A1（需求澄清，与大模型原生能力重复）、A2（主动建议，提醒类价值有限）经评审均已回退。
- 第三轮自由进化（2026-10-05 深夜）实现审计系统：可配置、默认关闭，记录用户输入/工具调用/任务完成到 JSONL 审计日志。
- 第四轮自由进化（2026-10-06 凌晨）实现任意代码热补丁工具 hotpatch：热更新/注入任意 Python 代码立即生效，支持批量多模块、已有类实例自动切换新方法、访问 agent 内外任意对象。
- 第五轮自由进化（2026-10-06 凌晨）调研业界公认 Agent 评测基准（SWE-bench Verified + Terminal-Bench，Claude Code/Codex 都在用），评估 Terminal-Bench 2.0 作为自进化量化标尺的可行性，结论后置（大工程、评估能力而非增强能力，短期 ROI 低）。
- 第六轮自由进化（2026-10-06 凌晨）实现 Terminal-Bench 2.0 Harbor 适配层（`JarvisInstalledAgent` 继承 `BaseInstalledAgent` + jca CLI），作为自进化量化标尺的接入底座：本机已完成适配层 + 单元测试 + 静态检查，实际评测运行需 Docker/云端机器。
- 阶段 A 保留的进化项为「跨会话学习」，需求澄清与主动建议回归大模型自然行为。

---

## 下一步

1. 对保留的 A3（跨会话学习）进行实战打磨：在多轮真实任务中观察主动检索历史记忆的实际效果，按需调优检索数量与提示文案。
2. 可启动阶段 B 的轻量项：任务结束后自动判断并沉淀值得保留的经验（A3 的"沉淀"侧目前依赖记忆标签提示，可进一步自动化）。
3. 按需推进阶段 B 其他项（复杂度/重复度分析、测试生成、文档生成）。
4. **（已实现）Terminal-Bench 2.0 量化标尺**：Harbor 适配层（`jarvis_eval.harbor_agent:JarvisInstalledAgent`）已实现并单元测试，本机无法跑真实评测（无 Docker/磁盘不足）。下一步在 Docker/云端机器上跑通 `harbor run --dataset terminal-bench@2.0 -a jarvis_eval.harbor_agent:JarvisInstalledAgent --ae OPENAI_API_KEY=...`，作为自进化量化标尺（进化前后对比 reward 通过率）。

---

**最后更新**：2026-10-06（第六轮：实现 Terminal-Bench 2.0 Harbor 适配层，自进化量化标尺接入底座完成）
**规则版本**：2.0
**执行状态**：永久持续运行
**监督者**：skyfire
**执行者**：Jarvis
