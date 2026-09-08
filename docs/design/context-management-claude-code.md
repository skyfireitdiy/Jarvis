# 将 Claude Code 上下文管理机制引入 Jarvis —— 方案设计

> 状态：**方案设计（待评审）**
> 日期：2026-09-08
> 范围：`src/jarvis/jarvis_agent/`、`src/jarvis/jarvis_platform/`、`src/jarvis/jarvis_utils/config.py`
> 关联：本方案基于对 Claude Code 上下文机制的调研（见文末"调研依据"）

---

## 1. 背景与问题

### 1.1 Jarvis 现状（代码事实）

Jarvis 的上下文/token 管理已具备以下能力：

| 能力         | 实现位置                                               | 说明                                              |
| ------------ | ------------------------------------------------------ | ------------------------------------------------- |
| token 统计   | `base.py:766-797` `get_used_token_count`               | 遍历消息 content + tool_calls 字段，tiktoken 估算 |
| 剩余空间     | `base.py:786-795` `get_remaining_token_count`          | 上限 - 已用                                       |
| 后台预压缩   | `__init__.py:2330` `_start_background_pre_compression` | 75% 阈值启动，后台线程生成摘要                    |
| 摘要立即生效 | `run_loop.py:335-346`                                  | 后台完成后立即应用（已实现）                      |
| 触发压缩     | `run_loop.py:348` `_adaptive_compression`              | 80% 阈值，用预压缩摘要或滑动窗口                  |
| 滑动窗口     | `__init__.py:2173` `_sliding_window_compression`       | 保留最近 N 条，压缩更早对话                       |
| 工具结果回填 | `base.py:118-124` `append_native_tool_result`          | role=tool 消息 content 存完整结果                 |

### 1.2 与 Claude Code 的差距（调研结论）

Claude Code 的上下文管理是**五层级联**体系，其中三层 Jarvis 缺失或不足：

| Claude Code 层级           | 作用                                                                      | Jarvis 现状                       |
| -------------------------- | ------------------------------------------------------------------------- | --------------------------------- |
| **Layer 0 落盘截断**       | 工具结果 >~50K 字符时完整 payload 写文件，上下文只留 ~2KB 预览 + 文件路径 | ❌ **缺失**：工具结果全量进上下文 |
| **Microcompact**           | 无模型调用，直接剥离旧工具结果，外科手术式、频繁、便宜                    | ❌ **缺失**：无此层               |
| **Session memory compact** | 用预提取笔记重建精简历史，无摘要调用                                      | ⚠️ 部分：后台预压缩类似           |
| **Full compact**           | fork agent 总结整个对话（最贵）                                           | ⚠️ 部分：滑动窗口/摘要压缩类似    |
| 自动压缩阈值               | ≈ context_window - max_output_tokens - buffer                             | ✅ 已有（80% 阈值）               |

**核心差距**：Jarvis 缺少"大工具结果落盘截断"与"剥离旧工具结果"两层，导致：

1. 单次大工具输出（如 `execute_script` 读大文件、`read_code` 大范围）会一次性占用大量上下文；
2. 历史中已无用的旧工具结果（如早期 `ls`/`grep` 输出）长期滞留，直到触发整体压缩才被清理。

---

## 2. 设计目标与原则

### 2.1 目标

1. **大工具结果落盘截断**：超阈值工具结果写临时文件，上下文只留预览 + 路径，模型可按需读取。
2. **剥离旧工具结果（微压缩）**：在 token 压力下无模型调用地丢弃最旧的工具结果，降低上下文占用。
3. **与现有压缩体系共存**：新机制作为现有 75%/80% 压缩的**前置补充层**，不破坏既有后台预压缩/滑动窗口逻辑。
4. **可配置、可回退**：所有阈值走配置，默认关闭或保守开启，避免行为突变。

### 2.2 原则

- **最小侵入**：改动集中在工具结果回填入口与压缩检查点，不重构现有压缩主流程。
- **配对安全**：任何裁剪必须保证 assistant tool_calls 与 role=tool 回包配对完整（否则 OpenAI/Anthropic 400），复用 `ensure_tool_pairing`。
- **可观测**：落盘/剥离动作有日志与统计，便于验证与调参。

---

## 3. 分层机制设计

将 Claude Code 的机制映射为 Jarvis 的**三层补充**，叠加在现有压缩体系之上。整体触发顺序（每轮模型调用前，`run_loop.check_and_compress_context` 内）：

```text
工具结果回填时（append_native_tool_result）
   └─ [新增] L0 大结果落盘截断（写文件，留预览）
每轮模型调用前（check_and_compress_context）
   ├─ [新增] L1 微压缩：剥离最旧工具结果（无模型调用）
   ├─ [现有] 75% 后台预压缩
   ├─ [现有] 后台完成即应用
   └─ [现有] 80% 触发 _adaptive_compression
```

### 3.1 L0：大工具结果落盘截断（新增）

**目标**：单条工具结果过大时，不让完整文本进上下文，改为"预览 + 文件路径"，模型需要时用 `read_code`/`execute_script` 按需读取。

**触发点**：`base.py:118-124` `append_native_tool_result`（原生工具结果回填唯一入口）。

**规则**：

- 阈值 `tool_result_disk_threshold`（默认如 20000 字符，可配）。
- 结果长度 ≤ 阈值：原样进上下文（现状不变）。
- 结果长度 > 阈值：完整内容写入临时文件（`jarvis_data_dir/tool_results/`），上下文 content 替换为结构化预览：

```text
[工具 {name} 结果过大，已落盘]
完整结果文件: {abs_path}（{N} 字符）
预览（前 {preview_len} 字符）:
{preview}
如需完整内容，请用 read_code 读取该文件。
```

- 预览长度 `tool_result_preview_len`（默认如 2000 字符）。
- 落盘文件按会话清理（会话结束/压缩时删除，避免磁盘堆积）。

**关键点**：

- 只改 `append_native_tool_result` 一处，文本协议与原生协议的工具结果都经此回填（需确认文本协议是否也走此方法，见 §6 待确认）。
- 落盘后模型若需完整内容，会主动发起 `read_code` 读取——这是 Claude Code 的既有行为模式，模型已习惯。

### 3.2 L1：剥离旧工具结果（微压缩，新增）

**目标**：无模型调用、外科手术式地丢弃历史中最旧的、已无用的工具结果，降低上下文占用。对应 Claude Code 的 Microcompact。

**触发点**：`run_loop.check_and_compress_context` 内、现有 75% 预压缩**之前**。

**规则**：

- 阈值 `microcompact_trigger_ratio`（默认如剩余 ≤ 35%，即已用 65% 时启动，早于 75% 预压缩）。
- 从历史**最旧**开始，逐个剥离"已配对的 role=tool 结果消息"，直到：
  - 释放的 token 达到 `microcompact_target_ratio`（默认如释放 10% 上限），或
  - 无更多可剥离的旧工具结果。
- **配对安全**：剥离 role=tool 时，必须同时剥离其对应的 assistant tool_calls 消息（否则 400）。复用 `ensure_tool_pairing` 语义。
- **保护**：最近 K 条工具结果（默认如最近 3 轮）不剥离，保留近期上下文；系统消息、用户最新消息、assistant 纯文本消息不剥离。

**关键点**：

- 无模型调用，纯消息列表操作，成本极低，可频繁运行。
- 剥离后调用 `set_messages` 重建历史（与现有压缩一致）。
- 若剥离后仍触发 75%/80%，继续走现有后台预压缩/滑动窗口——L1 只是前置减负。

### 3.3 与现有压缩的衔接

- L1 剥离后重新计算剩余 token；若仍 ≤25% 启动后台预压缩，≤20% 触发 `_adaptive_compression`（逻辑不变）。
- L0 落盘在回填时即完成，天然减少后续所有层级的输入规模。
- 三层叠加后，大工具结果不再一次性撑爆上下文，旧工具结果可被渐进清理，整体压缩触发频率下降。

---

## 4. 配置项设计（新增，`config.py`）

| 配置键                       | 默认值                | 说明                                           |
| ---------------------------- | --------------------- | ---------------------------------------------- |
| `tool_result_disk_threshold` | 20000                 | 工具结果超过该字符数即落盘截断（0=禁用 L0）    |
| `tool_result_preview_len`    | 2000                  | 落盘后上下文保留的预览字符数                   |
| `tool_result_disk_dir`       | `<data>/tool_results` | 落盘文件目录                                   |
| `microcompact_trigger_ratio` | 0.35                  | 剩余 token 比例 ≤ 该值触发 L1 微压缩（0=禁用） |
| `microcompact_release_ratio` | 0.10                  | L1 单次最多释放的上限 token 比例               |
| `microcompact_keep_recent`   | 3                     | 最近 N 轮工具结果不剥离                        |

> 默认值均为保守估计，落地时以实测为准；全部可配，默认开启但阈值宽松，避免行为突变。

---

## 5. 实现步骤（落地计划）

按依赖顺序分 3 个阶段，每阶段独立可验证、可回退。

### 阶段 A：L0 大工具结果落盘截断

1. `config.py` 新增 `tool_result_disk_threshold` / `tool_result_preview_len` / `tool_result_disk_dir` 读取函数。
2. 新增工具函数 `maybe_truncate_tool_result(name, content) -> str`（放 `native_tools.py` 或新模块）：超阈值则写文件并返回预览文本。
3. 在 `base.py:118-124` `append_native_tool_result` 内调用该函数，替换回填的 content。
4. 会话结束/压缩时清理 `tool_results/` 目录文件。
5. **验证**：mock 一条超阈值工具结果，确认 role=tool content 变为预览 + 路径、文件已落盘、token 统计显著下降；`test_native_tools` 等既有测试不回归。

### 阶段 B：L1 剥离旧工具结果（微压缩）

1. `config.py` 新增 `microcompact_trigger_ratio` / `microcompact_release_ratio` / `microcompact_keep_recent` 读取函数。
2. 新增方法 `_microcompact_old_tool_results() -> bool`（放 `__init__.py`，与现有压缩方法并列）：从最旧开始剥离已配对 tool 结果 + 对应 tool_calls，直到释放目标或无可剥离。
3. 在 `run_loop.check_and_compress_context` 内、75% 预压缩**之前**插入调用。
4. **验证**：构造含大量旧工具结果的历史，确认剥离后 token 下降、配对完整（`ensure_tool_pairing` 通过）、最近 K 轮保留；既有压缩测试不回归。

### 阶段 C：联调与调参

1. 长对话实测：确认 L0/L1 与 75% 后台预压缩、80% 触发压缩协同，无冲突、无重复压缩。
2. 依据实测调整默认阈值（落盘阈值、剥离比例、保护轮数）。
3. 补充单元测试覆盖 L0/L1 边界（阈值临界、空历史、全工具历史、配对断裂等）。

---

## 6. 待确认事项与风险

### 6.1 待确认

- **文本协议工具结果回填路径**：原生协议经 `append_native_tool_result`（base.py:118），但文本协议（`_handle_tool_calls`，run_loop.py:522）回填路径不同。需核实文本协议工具结果是否也产生 role=tool 消息、是否可复用 L0 落盘，否则需在文本协议路径单独接入。
- **落盘文件生命周期**：会话结束/压缩清理的准确钩子点需在实现时定位（`delete_chat`/`reset`/压缩方法）。
- **模型对"落盘预览 + 路径"的遵循度**：需实测模型是否会主动 `read_code` 读取落盘文件，而非忽略预览。

### 6.2 风险与缓解

| 风险                                 | 影响         | 缓解                                                       |
| ------------------------------------ | ------------ | ---------------------------------------------------------- |
| 落盘后模型不主动读文件，丢失关键信息 | 任务质量下降 | 预览保留足够上下文；提示词引导；阈值保守（仅超大结果落盘） |
| 剥离旧工具结果误伤仍在引用的结果     | 模型困惑     | 保护最近 K 轮；只剥离最旧；可配置关闭                      |
| 配对断裂导致 API 400                 | 请求失败     | 复用 `ensure_tool_pairing`；剥离时成对处理                 |
| 落盘文件磁盘堆积                     | 磁盘占用     | 会话级清理；目录上限                                       |
| 与现有压缩重复触发                   | 行为异常     | L1 剥离后重算剩余 token，仍走原阈值判断                    |

---

## 7. 调研依据

本方案基于对 Claude Code 上下文机制的调研（官方文档 + teardown 分析）：

- **Claude Code 官方 context-window 文档**：文件读取、工具输出、CLAUDE.md、memory、skills、MCP 工具名均进入上下文；`/compact` 用结构化摘要替换对话；自动压缩在接近上限时触发。
- **Claude Code 五层级联压缩**（startdebugging.net teardown）：
  - Layer 0（落盘）：工具结果超约 50K 字符时完整 payload 写文件，上下文只留约 2KB 预览 + 路径；单条消息所有 tool_result 块合计上限约 200K 字符。
  - Microcompact：无模型调用，直接剥离旧工具结果，便宜、外科手术式、频繁运行。
  - Session memory compact：用预提取笔记重建精简历史，无摘要调用。
  - Full compact：fork agent 总结整个对话（最贵）。
  - 自动压缩阈值 ≈ context_window - max_output_tokens - buffer（200K 窗口约 167K 触发）。

> 注：OpenAI Codex / Cursor / Aider 的具体机制因搜索工具多次超时未能获取，本方案以 Claude Code 为对标基准。
