# 对标 Claude Code 的改进方案与改进方法

> 状态：**方案设计（待评审）**
> 日期：2026-10-05
> 范围：`src/jarvis/jarvis_agent/`、`src/jarvis/jarvis_utils/`、`src/jarvis/jarvis_tools/`、`src/jarvis/jarvis_service/`、`browser_extension/`
> 关联：本文基于《Jarvis vs Claude Code 功能差距分析》及用户逐条澄清修订而成

---

## 0. 背景

此前对 Jarvis 与 Claude Code 做了功能差距分析，列出了 8 项"Claude Code 有、Jarvis 缺失/较弱"的能力。经用户逐条澄清，其中多项**Jarvis 已有对应物**，只是机制/形态不同，需按 Jarvis 既有设计对齐而非照搬 Claude Code。

本文在**源码核实**基础上，逐条回应 8 项差距，给出改进方案与改进方法。

---

## 1. 差距逐条澄清与现状核实

| #   | 原差距项                              | 用户澄清                                          | 源码核实结论                                                                                                                                                                               |
| --- | ------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | 项目级指令文件（CLAUDE.md/AGENTS.md） | rules 中的 rule.md 也是自动加载，对标 CLAUDE.md   | ✅ 已确认：Jarvis 已有三层规则体系（builtin/project/global），项目级 `.jarvis/rules/` 自动扫描，`.jarvis/rules/rule.md` 作为项目综述自动加载（`rules_manager.py:_load_project_rule_file`） |
| 2   | Hooks 生命周期                        | hook 也可配置，用 Python 文件注册，可补充 hook 点 | ✅ 已确认：`callback_loader.py` 已支持 16 个事件，Python 文件注册，含拦截/修改/通知三种类型                                                                                                |
| 3   | Skills + Plugins + `/` 命令           | Jarvis 用 `@` 而不是 `/`                          | ✅ 已确认：Jarvis 用 `@` 触发内置命令（`input.py:BUILTIN_COMMANDS` + `builtin_replace_map.py`）                                                                                            |
| 4   | 多端/远程控制                         | Jarvis 的 Web 端可跨端访问                        | ✅ 已确认：Jarvis 有 Web 网关，天然跨端                                                                                                                                                    |
| 5   | CI/CD 深度集成                        | 可以补充一下                                      | ⚠️ 需补充：无官方 CI action 模板、PR 自动审查                                                                                                                                              |
| 6   | Agent SDK                             | 可以优化提供一下                                  | ⚠️ 需优化：有 Python SDK，但定位与生态可增强                                                                                                                                               |
| 7   | 交互式 diff/IDE 插件                  | IDE 不重要，也可以不做                            | ❌ 忽略（用户判定不重要，不做）                                                                                                                                                            |
| 8   | Prompt Caching                        | 这个不重要                                        | ❌ 忽略（用户判定不重要）                                                                                                                                                                  |

---

## 2. 逐项改进方案

### 2.1 项目级指令文件（对标 CLAUDE.md）

**现状核实**：Jarvis 已具备三层规则体系，且项目级规则随仓库走（`<项目根>/.jarvis/rules/`），`rule.md` 自动加载为项目综述。与 Claude Code 的 CLAUDE.md 定位一致，但**触发方式不同**：Claude Code 是"固定加载项目根 CLAUDE.md"，Jarvis 是"规则文件 + 任务自动匹配"。

**改进方向**：让 Jarvis 能**兼容读取仓库根 `AGENTS.md`/`CLAUDE.md`**（社区通用约定，跨工具共享），作为项目综述的补充来源。

**改进方法**：

1. 在 `rules_manager.py` 的 `_load_project_rule_file()` 中，除加载 `.jarvis/rules/rule.md` 外，**额外检测仓库根 `AGENTS.md`（无则 `CLAUDE.md`）**，将其内容包装为 `project:agents` 规则加载。
2. 优先级：`.jarvis/rules/rule.md` > `AGENTS.md` > `CLAUDE.md`（避免冲突时覆盖）。
3. 需处理：AGENTS.md 可能很大，应做 token 预算截断（复用 `get_context_token_count` 与 `methodology_token_limit` 同款预算逻辑）。
4. 兼容：若项目已有 `.jarvis/rules/rule.md`，AGENTS.md 作为补充而非替代，合并注入。

**涉及文件**：`src/jarvis/jarvis_agent/rules_manager.py`
**优先级**：P1（价值高、改动小、兼容社区约定）
**验证**：新建含 `AGENTS.md` 的项目，确认其内容注入系统提示词；含 `.jarvis/rules/rule.md` 时两者共存不冲突。

---

### 2.2 Hooks 生命周期（补充 hook 点）

**现状核实**：`callback_loader.py` 已支持 16 个事件（`events.py`），三类回调：

- **拦截型（hook）**：`BEFORE_TOOL_CALL`（返回 False 拦截）
- **修改型（modifier）**：`BEFORE_MODEL_CALL`、`BEFORE_SUMMARY`（返回修改后的值）
- **通知型（event）**：`AFTER_TOOL_CALL`、`AFTER_SUMMARY` 等

通过 `~/.jarvis/hooks/`（或配置目录）下的 Python 文件注册，支持 `# requirements:` 自动装依赖。

**改进方向**：补充**编码工作流**相关的高价值 hook 点，对标 Claude Code 的 PreToolUse/PostToolUse/SessionStart 覆盖度。

**改进方法**（新增 hook 点，按价值排序）：

| 新增 hook 点           | 类型   | 触发时机           | 典型用途                                  |
| ---------------------- | ------ | ------------------ | ----------------------------------------- |
| `AFTER_FILE_EDIT`      | 通知型 | 每次文件编辑完成后 | 自动格式化、lint、git diff 提示           |
| `BEFORE_GIT_COMMIT`    | 拦截型 | Agent 提交前       | 提交前 lint/测试门禁、commit message 校验 |
| `AFTER_GIT_COMMIT`     | 通知型 | 提交完成后         | 推送、CI 触发、通知                       |
| `BEFORE_TASK_START`    | 拦截型 | 每次任务开始前     | 环境准备、权限校验                        |
| `AFTER_TASK_COMPLETE`  | 通知型 | 任务完成后         | 汇总、上报、清理                          |
| `BEFORE_SESSION_START` | 拦截型 | 会话开始时         | 加载项目专属配置                          |
| `AFTER_SESSION_END`    | 通知型 | 会话结束时         | 保存状态、统计                            |

**实现要点**：

1. 在 `events.py` 定义新事件常量与 TypedDict 负载类型。
2. 在 Agent 主循环（`run_loop.py`）的对应生命周期点 `emit` 新事件。
3. 复用 `callback_loader.load_event_callbacks()` 通用加载器，只需在 `load_all_event_callbacks()` 中追加注册即可，无需新增加载逻辑。
4. 文件编辑 hook 需在 `edit_file`/`write_file` 工具执行后触发（可在工具执行包装层加）。

**涉及文件**：`src/jarvis/jarvis_agent/events.py`、`src/jarvis/jarvis_agent/callback_loader.py`、`src/jarvis/jarvis_agent/run_loop.py`、`src/jarvis/jarvis_tools/`（工具执行点）
**优先级**：P1（直接提升编码工作流自动化，复用现有加载器，改动可控）
**验证**：为每个新事件写一个测试回调，确认触发时机与负载正确；确认不影响无回调时的默认行为。

---

### 2.3 `@` 内置命令（对标 `/` 命令）

**现状核实**：Jarvis 用 `@` 触发内置命令，分两类：

- **提示词模板命令**：`builtin_replace_map.py` 的 `BUILTIN_REPLACE_MAP`，如 `@Web`、`@Dev`、`@Fix`、`@Check`（追加/替换用户输入）
- **内置命令标记**：`input.py` 的 `BUILTIN_COMMANDS` + `builtin_input_handler.py` 处理，立即执行

`@` 与 `/` 只是触发符号差异，功能等价。

**改进方向**：**丰富 `@` 命令库**，对标 Claude Code 的 `/init`、`/review`、`/plan`、`/clear`、`/compact` 等常用命令。

**改进方法**：

1. 新增提示词模板命令（`builtin_replace_map.py`）：
   - `@Review`：代码审查模板（复用 code_review 规则）
   - `@Plan`：生成实施计划
   - `@Test`：为选中模块补测试
   - `@Refactor`：重构检查模板
   - `@Security`：安全扫描模板
2. 新增内置命令标记（`input.py` + `builtin_input_handler.py`）：
   - `@clear`：清空当前会话上下文
   - `@compact`：手动触发上下文压缩
   - `@status`：查看当前任务/上下文状态
   - `@help`：列出所有 `@` 命令
3. 命令描述写入 `BUILTIN_COMMANDS`，自动补全（prompt_toolkit + fzf）自动生效，无需额外改补全逻辑。

**涉及文件**：`src/jarvis/jarvis_utils/builtin_replace_map.py`、`src/jarvis/jarvis_utils/input.py`、`src/jarvis/jarvis_agent/builtin_input_handler.py`
**优先级**：P2（体验增强，不阻塞核心功能）
**验证**：输入 `@` 触发自动补全，选择命令后行为正确；`@help` 能列出全部命令。

---

### 2.4 Web 端跨端访问

**现状核实**：Jarvis 有 Web 网关（`jarvis-service`），浏览器访问即可，天然跨端（任何有浏览器的设备）。

**改进方向**：**优化移动端适配与跨端续接体验**，而非新增端。

**改进方法**：

1. **移动端响应式优化**：检查前端（`src/jarvis/jarvis_service/frontend/src/App.vue`）在小屏下的布局，重点优化宠物大厅、命令面板、会话列表的移动端展示。
2. **跨端续接**：会话已支持自动保存/恢复（README 确认），确保 Web 端换设备后能恢复同一会话（会话存储与设备解耦）。
3. **PWA 支持**：前端已有 `manifest.webmanifest` 与 `sw.js`（构建产物确认），可完善为可安装的 PWA，提升移动端体验。

**涉及文件**：`src/jarvis/jarvis_service/frontend/src/`
**优先级**：P3（体验优化）
**验证**：移动端浏览器访问 Web 网关，核心功能可用；会话跨设备可恢复。

---

### 2.5 CI/CD 深度集成（补充）

**现状核实**：Jarvis 有 headless 模式（`no_interaction_mode`）、定时任务、`-p` 类非交互入口，但**无官方 CI action 模板、无 PR 自动审查现成集成**。

**改进方向**：提供**开箱即用的 CI 集成**，让 Jarvis 能跑进 GitHub Actions / GitLab CI。

**改进方法**：

1. **新增 `.github/workflows/` 模板**（放仓库 `scripts/ci/` 或文档示例）：
   - `jarvis-pr-review.yml`：PR 触发，对 diff 做代码审查并评论（复用 code_review 规则）
   - `jarvis-issue-triage.yml`：issue 触发，自动分类/打标签
   - `jarvis-ci-test.yml`：提交触发，跑测试并汇报
2. **提供 `jca -p` 非交互审查命令封装**：确认 `jarvis-code-agent` 支持非交互 + 结构化输出（`--output-format json`），供 CI 解析。
3. **文档化**：在 README 或 `docs/` 增加"CI 集成指南"，给出可复制粘贴的 action 模板。
4. **PR 自动审查**：用 `sub_code_agent` 或独立 Agent 对 `git diff` 做审查，输出结构化结论（问题清单 + 严重级别 + 建议），CI 中作为 PR 评论。

**涉及文件**：`scripts/ci/`（新增）、`docs/`（新增指南）
**优先级**：P1（团队协作价值高，纯新增无回归风险）
**验证**：本地用样例 PR diff 跑通审查流程，确认输出结构化；action 模板在真实仓库试跑。

---

### 2.6 Agent SDK（优化）

**现状核实**：Jarvis 有 Python SDK（`from jarvis.jarvis_code_agent.code_agent import CodeAgent`），可调用 Agent 执行任务，但定位是"调用 Agent"而非"构建自定义 Agent 的完整 SDK 生态"。

**改进方向**：**增强 SDK 的可编程性**，让开发者能编排多 Agent、注入自定义工具/规则、控制权限。

**改进方法**：

1. **SDK 编排 API**：提供高层编排函数，如 `run_agents_parallel([...])`、`pipeline([...])`，复用现有 `gateway_manager` 的多 Agent 能力。
2. **SDK 注入能力**：允许在构造 Agent 时注入自定义工具/规则/模型组（`Agent(config_file=..., tool_group=...)`），文档化参数。
3. **SDK 回调**：暴露 Agent 生命周期事件（复用 2.2 的 hook 点）给 SDK 调用方。
4. **结构化输出**：提供 `agent.run_structured(task, schema)`，返回 JSON 而非纯文本。
5. **文档化**：在 README 增加"Python SDK 进阶用法"章节，含编排、注入、回调示例。

**涉及文件**：`src/jarvis/jarvis_agent/`、`src/jarvis/jarvis_code_agent/`、`README.md`
**优先级**：P2（增强可编程性，不阻塞现有功能）
**验证**：编写 SDK 集成测试，确认编排/注入/回调可用。

---

### 2.7 交互式 diff / IDE 插件

**用户判定：不重要，不做。** 不纳入改进范围。（Jarvis 的 Web 端已内置 Monaco 编辑器 + LSP + Git diff，编码体验已基本够用；VS Code/JetBrains 插件成本高、价值有限，故不做。）

---

### 2.8 Prompt Caching

**用户判定：不重要，忽略。** 不纳入改进范围。（Jarvis 已有上下文压缩机制，且缓存策略依赖模型平台，价值有限。）

---

## 3. 总体实施路线图

| 阶段               | 内容                                                           | 优先级 | 风险                       |
| ------------------ | -------------------------------------------------------------- | ------ | -------------------------- |
| **阶段 A（近期）** | 2.1 项目级 AGENTS.md 兼容 · 2.2 补充 hook 点 · 2.5 CI 集成模板 | P1     | 低（复用现有机制，纯增量） |
| **阶段 B（中期）** | 2.3 丰富 `@` 命令 · 2.6 SDK 增强                               | P2     | 中（部分涉及前端改动）     |
| **阶段 C（远期）** | 2.4 移动端/PWA                                                 | P3     | 中（前端改动需 rebuild）   |

> 2.7（IDE 插件）与 2.8（Prompt Caching）经用户判定不重要，**不做**，不纳入路线图。

**建议启动顺序**：先做阶段 A 的 2.1（AGENTS.md 兼容）与 2.2（hook 点），两者改动小、价值高、无回归风险，可快速落地验证；再推进 2.5 CI 集成。

---

## 4. 设计原则

- **不照搬，只对齐**：Claude Code 是单人编码助手，Jarvis 是协作式平台。改进应增强 Jarvis 既有能力（规则、hook、`@`、Web），而非引入其没有的机制。
- **复用现有机制**：hook 复用 `callback_loader` 通用加载器；命令复用 `@` 体系；规则复用三层规则系统；CI 复用 headless 模式。
- **纯增量、可回退**：所有改进均为新增能力，不修改现有默认行为，无回调/无命令/无 AGENTS.md 时行为不变。
- **兼容社区约定**：AGENTS.md 是跨工具通用约定，支持它可让 Jarvis 直接复用社区项目的指令文件。

---

## 5. 附：源码核实依据

- 三层规则体系：`src/jarvis/jarvis_agent/rules_manager.py`（`_load_project_rule_file` 加载 `.jarvis/rules/rule.md`，`get_all_available_rule_names` 扫描 builtin/project/global 三类目录）
- Hook 机制：`src/jarvis/jarvis_agent/callback_loader.py`（`load_event_callbacks` 支持 hook/modifier/event 三类）、`src/jarvis/jarvis_agent/events.py`（16 个事件常量）
- `@` 命令：`src/jarvis/jarvis_utils/input.py`（`BUILTIN_COMMANDS`）、`src/jarvis/jarvis_utils/builtin_replace_map.py`、`src/jarvis/jarvis_agent/builtin_input_handler.py`
- Web 跨端：`src/jarvis/jarvis_service/frontend/`（`manifest.webmanifest`、`sw.js` 支持 PWA）
- 上下文压缩：`src/jarvis/jarvis_agent/run_loop.py`（`_adaptive_compression`）、`src/jarvis/jarvis_agent/__init__.py`（`_start_background_pre_compression`）
