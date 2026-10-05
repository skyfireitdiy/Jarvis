# Jarvis 四大系统「降低模型输入量」优化设计方案

> 目标规模：方法论上千 / 记忆上万 / 工具几百 / 规则上千
> 当前规模：方法论 67 / 记忆 1919 / 工具 36 / 规则被剪枝到 47
> 本文档为**设计**，不包含实现。核心目标：**降低每次调用给模型的输入量（prompt/token）**。
> 内存加载量的优化优先级放低（不阻塞、不优先），仅在顺带可做时处理。

---

## 0. 核心结论（聚焦模型输入量）

四个系统里，真正会**膨胀模型输入量**的路径只有三处，其余路径已有 token/条数防御：

| 系统       | 给模型的输入路径                   | 现状                                                                                                                                                                                     |  是否膨胀   |
| ---------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :---------: |
| **方法论** | 选择阶段**全量标题/候选**塞给 LLM  | eval 走 decide_choice 为每个候选构造一个 noul 问题（decision.py:136）；normal 把全部标题拼进 prompt（methodology.py:262-264）                                                            | 🔴 **膨胀** |
| **规则**   | 选择阶段**全量候选+描述**塞给 LLM  | `select_rule_by_task` 全量候选 + 每个候选完整描述拼进 prompt（rules_manager.py:1162-1168）                                                                                               | 🔴 **膨胀** |
| **工具**   | 全量工具 schema 传给模型           | 原生模式 `build_openai_tools`/`build_anthropic_tools` 全量工具完整 schema 传 API tools（native_tools.py:372-404）；非原生模式 `prompt()` 全量 JSON 注入系统提示词（registry.py:240-274） | 🔴 **膨胀** |
| **记忆**   | memory 工具 retrieve 返回 Markdown | 普通检索已有 token 限制（memory.py:380-419）+ 50 条上限；**smart_search 无 token 限制**（memory.py:477-543）                                                                             |   🟡 部分   |

**已防御、无需优化的路径**：

- 方法论**最终注入**：有 token 限制（`methodology_token_limit = max_input*0.8`，methodology.py:418-435）
- 规则**最终加载**：有 `MAX_AUTO_RULES = 3` 上限（rules_manager.py:1128）
- 记忆**普通检索注入**：有 token 限制 + 50 条上限（memory.py:380-419）

**优化优先级**（按降低输入量的收益）：

- **P0**：方法论选择阶段预筛选（B1）
- **P0**：规则选择阶段预筛选（C2）
- **P1**：工具 schema 摘要/分组（D1/D2）
- **P2**：记忆 smart_search 加 token 限制（A3）

---

## 1. 方法论系统（P0，核心膨胀点）

### 1.1 问题确认（代码事实）

文件：`src/jarvis/jarvis_utils/methodology.py` + `src/jarvis/jarvis_utils/decision.py`

`load_methodology`（347）每次会话（use_methodology 开启时）调用：

1. `_load_all_methodologies`（109-196）全量加载所有 json
2. `methodology_titles = [title for title, _ in methodologies]`（383）——**全量标题**
3. 选择阶段：
   - **eval 模式**：`_select_methodologies_with_eval_model`（199）→ `decide_choice`（decision.py:136）为**每个候选**构造一个 noul 问题，一次请求把**所有候选的问题**发给评估模型（decision.py:155-166）。上千方法论 = 上千个问题 = 巨大输入量
   - **normal 模式**：`_select_methodologies_with_normal_model`（241）把**全部标题**拼进 prompt（262-264）

### 1.2 优化方案

#### 方案 B1（P0，推荐）：选择阶段预筛选 Top-N

- 在调用 `_select_methodologies_with_eval_model` / `_select_methodologies_with_normal_model` **之前**，用关键词对 `methodology_titles` 做粗筛，只保留 Top-N（如 30-50）候选
- 粗筛方式：jieba 分词提取用户输入关键词，与标题做子串/关键词匹配打分，取 Top-N
- **收益**：上千方法论时，LLM 候选从全量降到 Top-N，输入量降一个数量级
- **风险**：可能漏掉正确方法论——**必须保留 fallback**：预筛结果为空时回退全量
- 实现位置：`load_methodology`（347）在 383 行得到 `methodology_titles` 后、389 行选择前插入预筛

#### 方案 B2（P2，可选）：加载缓存

- `_load_all_methodologies` 每次全量 glob + json.load，加 mtime 缓存（属内存加载优化，优先级低）

---

## 2. 规则系统（P0，核心膨胀点）

### 2.1 问题确认（代码事实）

文件：`src/jarvis/jarvis_agent/rules_manager.py`

`select_rule_by_task`（1117）：

1. `get_all_available_rule_names`（684-759）os.walk 全量遍历（仅 skill.md 目录剪枝）
2. 对**每个候选** `_extract_rule_description` 读文件提取描述（1147-1159，IO）
3. `top_rules = all_rules_list`（1162）——**全量候选**
4. 构造编号列表，**全量候选+描述拼进 prompt**（1164-1168）发给 LLM

上千规则时：全量候选+描述塞给 LLM = 巨大输入量。

### 2.2 优化方案

#### 方案 C2（P0，推荐）：选择阶段预筛选 Top-N

- 在构造编号列表（1164）之前，用关键词对候选做粗筛，只保留 Top-N（如 30-50）
- 粗筛方式：jieba 分词提取用户输入关键词，与规则 name/description 做关键词匹配打分
- **收益**：上千规则时，LLM 候选从全量降到 Top-N，输入量降一个数量级
- **风险**：可能漏掉正确规则——**必须保留 fallback**：预筛结果为空时回退全量
- 实现位置：`select_rule_by_task`（1117）在 1162 行 `top_rules = all_rules_list` 处改为预筛结果

#### 方案 C1（P2，可选）：规则索引缓存

- 构建规则索引（name → path → description），首次构建后缓存，按 mtime 失效
- 避免每次 `select_rule_by_task` 都 os.walk + 读所有文件（属内存/IO 优化，优先级低）

---

## 3. 工具系统（P1，核心膨胀点）

### 3.1 问题确认（代码事实）

文件：`src/jarvis/jarvis_platform/native_tools.py` + `src/jarvis/jarvis_tools/registry.py`

工具注入模型有两条路径，**默认走原生模式**（`enable_native_tool_calls` 默认 True，config.py:1261）：

1. **原生模式**：`_native_tools()`（**init**.py:1137）→ `build_openai_tools`/`build_anthropic_tools`（native_tools.py:372-404）遍历 `registry.tools.values()` **全量工具**，把每个工具的 name/description/**完整 parameters schema** 传给 API 的 tools 参数
2. **非原生模式**：`build_system_prompt`（prompt_manager.py:49）→ `get_tool_usage_prompt` → `build_action_prompt`（prompt_builder.py:19-76）→ `ToolRegistry.prompt()`（registry.py:240-274）遍历所有工具，完整 JSON 注入系统提示词

当前 21 个工具 prompt 约 13.5k token（实测）。几百工具时按比例到 100k+ token，非常可观。

### 3.2 优化方案

#### 方案 D1（P1，推荐）：工具 schema 摘要/精简

- 对工具的 `parameters` schema 做精简：只保留 `required` 字段 + 关键描述，省略冗长 `enum`/`default`/`description` 细节
- 对超长 description 截断
- **收益**：几百工具时，每个工具的 schema 显著缩小，总输入量大幅下降
- 实现位置：`build_openai_tools`/`build_anthropic_tools`（native_tools.py:372-404）和 `ToolRegistry.prompt()`（registry.py:240-274）共用同一个精简函数

#### 方案 D2（P2，可选，较大改动）：工具分组按需注入

- 按工具类别分组，只注入常用核心工具，其余按需补充
- **风险**：改动大，需保证模型能发现未注入工具（原生模式 tools 参数是静态的，动态注入需改 run_loop）

#### 方案 D3（P2，可选）：prompt 缓存

- 工具 prompt 每次会话构建，若工具集不变可缓存（属内存优化，优先级低）

---

## 4. 记忆系统（P2，部分需优化）

### 4.1 问题确认（代码事实）

文件：`src/jarvis/jarvis_tools/memory.py` + `src/jarvis/jarvis_memory_organizer/smart_retrieval.py`

记忆通过 `memory` 工具（action=retrieve）由模型主动调用，返回 Markdown 注入模型：

- **普通检索**（`_execute_retrieve`，memory.py:348）：**已有 token 限制**（380-419，剩余 token 2/3 或输入窗口 2/3）+ 50 条上限。**无需优化**
- **smart_search**（`_execute_smart_search`，memory.py:477）：**无 token 限制**，直接返回 `semantic_search` 的 top-N（默认 10 条）格式化注入。虽然条数少，但**每条 content 可能很长**，无 token 上限

### 4.2 优化方案

#### 方案 A3（P2，推荐）：smart_search 加 token 限制

- 在 `_execute_smart_search`（memory.py:477）格式化输出前，复用普通检索的 token 限制逻辑（380-419），按 token 预算筛选返回的记忆
- **收益**：防止单条超长记忆撑爆上下文
- 实现位置：`_execute_smart_search`（memory.py:477）在 527 行格式化前加 token 筛选

#### 方案 A1/A2（P3，可选，内存加载优化，优先级低）

- 删除 `_load_all_memories` 无用全量加载（smart_retrieval.py:168-169，corpus 参数实际没用）
- 标签倒排索引（smart_retrieval.py:464-482）
- **这些是内存/IO 优化，按用户指示优先级放低**

---

## 5. 实施建议

### 5.1 分阶段实施（按降低模型输入量的收益排序）

| 阶段               | 内容                            | 改动量 | 风险              |
| ------------------ | ------------------------------- | ------ | ----------------- |
| **阶段 1**         | 方法论 B1 预筛选                | 中     | 中（需 fallback） |
| **阶段 2**         | 规则 C2 预筛选                  | 中     | 中（需 fallback） |
| **阶段 3**         | 工具 D1 schema 精简             | 中     | 低-中             |
| **阶段 4**         | 记忆 A3 smart_search token 限制 | 小     | 低                |
| **阶段 5**（可选） | 内存/IO 优化（A1/A2/C1/B2/D3）  | 中     | 低                |

### 5.2 通用原则

- 所有预筛选方案**必须保留 fallback**（预筛为空时回退全量），避免漏选
- 预筛选阈值（Top-N）可配置，默认 30-50
- 每个阶段独立提交，可单独回退
- 每个阶段用当前数据量 + 模拟目标规模做基准测试验证

### 5.3 验证方法

- 阶段 1/2：对比预筛前后 `load_methodology`/`select_rule_by_task` 选中结果（预筛不应漏选，需人工抽查）；对比发送给 LLM 的输入量（token 数）
- 阶段 3：对比工具调用成功率（模型应仍能正确调用工具）；对比 tools 部分输入量
- 阶段 4：对比 smart_search 返回结果与输入量
