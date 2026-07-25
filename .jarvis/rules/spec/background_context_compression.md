---
name: background_context_compression
description: 上下文后台并行压缩方案 - 压缩与对话并行执行，完成后替换历史
---

# 上下文后台并行压缩 详细设计文档

## 1. 需求分析

### 1.1 功能需求

- **后台压缩**：当检测到需要压缩时，在后台线程中启动压缩任务，不阻塞主对话循环
- **并行执行**：压缩期间主对话继续正常进行，用户无需等待
- **完成后替换**：压缩完成后，将压缩结果替换到当前会话的历史消息中
- **全程静默**：压缩过程对用户完全不可见，不输出任何进度提示
- **安全替换**：替换时需保证不丢失压缩期间产生的新消息

### 1.2 非功能需求

| 类型     | 要求                           | 指标                          |
| -------- | ------------------------------ | ----------------------------- |
| 性能     | 压缩不阻塞主对话               | 主对话零延迟感知              |
| 静默     | 压缩过程用户无感知             | 不输出任何压缩相关提示        |
| 安全     | 替换不丢失压缩期间新消息       | 100%保留新消息                |
| 可靠     | 压缩失败不影响主对话           | 降级为同步压缩                |
| 一致性   | 避免并发压缩冲突               | 同一时刻仅一个压缩任务        |
| 资源     | 后台压缩使用独立模型实例       | 不污染主会话状态              |

### 1.3 设计约束

- **技术约束**：Python 3.12，使用 threading 模块（非 asyncio，因为主循环是同步的）
- **兼容约束**：需兼容现有 `_sliding_window_compression` 和 `_summarize_and_clear_history` 接口
- **环境约束**：压缩使用临时模型实例，需消耗额外的 API 配额

## 2. 系统架构设计

### 2.1 架构概览

```text
┌─────────────────────────────────────────────────────┐
│                   主对话循环 (Main Thread)            │
│                                                       │
│  ┌─────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │ 检查触发 │───>│ 启动后台压缩 │───>│ 继续主对话   │ │
│  └─────────┘    └──────┬───────┘    └──────┬───────┘ │
│                        │                     │         │
│                        │ (异步)              │ (同步)  │
│                        ▼                     │         │
│              ┌──────────────────┐            │         │
│              │ 后台压缩线程      │            │         │
│              │                  │            │         │
│              │ 1.快照历史消息    │            │         │
│              │ 2.创建临时模型    │            │         │
│              │ 3.调用LLM压缩    │            │         │
│              │ 4.生成压缩结果   │            │         │
│              └────────┬─────────┘            │         │
│                       │                      │         │
│                       ▼                      │         │
│              ┌──────────────────┐            │         │
│              │ 压缩结果暂存      │            │         │
│              │ (pending_replacement)         │         │
│              └────────┬─────────┘            │         │
│                       │                      │         │
│                       ▼                      ▼         │
│              ┌──────────────────────────────────┐      │
│              │ 下一轮循环：检查并应用压缩结果     │      │
│              │ (合并压缩结果 + 压缩期间新消息)    │      │
│              └──────────────────────────────────┘      │
└─────────────────────────────────────────────────────┘
```

**架构说明**：

- **主线程**：继续执行对话循环，不等待压缩完成
- **后台线程**：独立执行压缩，结果暂存到 `pending_replacement`
- **合并点**：下一轮循环开始时，检查是否有待应用的压缩结果，安全合并

### 2.2 关键设计决策

| 决策点                     | 选择方案                  | 理由                                      | 备选方案              |
| -------------------------- | ------------------------- | ----------------------------------------- | --------------------- |
| 并发模型                   | threading.Thread          | 主循环是同步的，threading最简单直接        | asyncio（需大重构）   |
| 快照时机                   | 启动压缩时快照历史        | 避免压缩期间历史被修改导致不一致          | 深拷贝整个model       |
| 替换时机                   | 下一轮循环开始时          | 确保不在模型调用中途替换，避免竞态        | 压缩完成立即替换      |
| 压缩期间再次触发           | 忽略（跳过）              | 避免并发压缩冲突                          | 排队等待              |
| 压缩失败处理               | 降级为同步压缩            | 确保压缩最终一定能执行                    | 静默忽略              |

### 2.3 技术选型

| 技术领域   | 选择技术          | 版本    | 选择理由                     |
| ---------- | ----------------- | ------- | ---------------------------- |
| 并发       | threading.Thread  | 3.12内置 | 同步代码最简方案，无需重构   |
| 线程安全   | threading.Lock    | 3.12内置 | 保护共享状态                 |
| 模型实例   | _create_temp_model | 现有    | 复用已有临时模型创建逻辑     |

## 3. 模块设计

### 3.1 模块划分

```text
jarvis_agent/
  ├── __init__.py (Agent类)
  │   ├── BackgroundCompressionManager  (新增类)
  │   └── _sliding_window_compression()  (修改：支持异步模式)
  └── run_loop.py (AgentRunLoop类)
      └── check_and_compress_context()   (修改：触发后台压缩)
```

### 3.2 模块职责

| 模块/类                        | 职责描述                               | 依赖模块       |
| ------------------------------ | -------------------------------------- | -------------- |
| BackgroundCompressionManager   | 管理后台压缩生命周期、线程安全、结果暂存 | Agent, threading |
| _sliding_window_compression    | 执行实际压缩逻辑（同步/异步）          | BasePlatform   |
| check_and_compress_context     | 检查触发条件，启动压缩                 | BackgroundCompressionManager |

### 3.3 模块交互

**交互流程（正常情况）**：

1. 主循环调用 `check_and_compress_context()`
2. 检测到需要压缩 -> 调用 `compression_manager.start_background_compression()`
3. 后台线程启动，快照当前历史，开始压缩
4. 主循环继续执行（不等待）
5. 后台线程完成，结果存入 `pending_replacement`
6. 下一轮主循环，`check_and_compress_context()` 检测到 `pending_replacement`
7. 调用 `compression_manager.apply_pending_replacement()` 合并结果

**交互流程（压缩失败）**：

1-4. 同上
5. 后台线程压缩失败，设置 `compression_failed = True`
6. 下一轮主循环检测到失败，降级执行同步压缩

## 4. 接口设计

### 4.1 BackgroundCompressionManager 类

- **类定义**：`BackgroundCompressionManager(agent)`
- **功能**：管理后台压缩线程生命周期，确保线程安全和结果正确合并
- **核心属性**：
  - `_lock: threading.Lock` - 保护共享状态
  - `_is_compressing: bool` - 是否正在压缩
  - `_pending_replacement: CompressionResult | None` - 待应用的压缩结果
  - `_compression_failed: bool` - 压缩是否失败
  - `_snapshot_turn: int` - 快照时的对话轮次

#### start_background_compression

- **签名**：`def start_background_compression(self, model_instance, current_message_tokens: int) -> bool`
- **功能**：启动后台压缩线程（非阻塞，静默）
- **返回**：True成功启动，False已有压缩在运行
- **异常**：线程启动失败返回False，不抛异常

#### check_and_apply

- **签名**：`def check_and_apply(self, model_instance) -> tuple[bool, bool]`
- **功能**：检查压缩状态并应用结果（供主循环每轮调用，静默）
- **返回**：`(applied, need_fallback)` - applied是否应用了结果，need_fallback是否需要降级同步压缩

### 4.2 修改的现有接口

#### check_and_compress_context（修改）

- **位置**：`run_loop.py:check_and_compress_context()`
- **修改**：
  1. 每轮开始先调用 `compression_manager.check_and_apply()`
  2. 触发压缩时调用 `start_background_compression()` 而非同步压缩
  3. 后台压缩失败时降级为同步压缩
  4. 移除所有压缩相关的 PrettyOutput 提示

#### _sliding_window_compression（修改）

- **位置**：`__init__.py:_sliding_window_compression()`
- **修改**：
  1. 新增参数 `snapshot` 和 `snapshot_turn`，支持基于快照压缩
  2. 返回压缩结果而非直接修改历史
  3. 移除所有压缩相关的 PrettyOutput 提示

## 5. 数据结构设计

### 5.1 CompressionResult

| 字段名              | 类型                  | 必填 | 说明                           |
| ------------------- | --------------------- | ---- | ------------------------------ |
| summary_text        | str                   | 是   | 压缩生成的摘要文本             |
| snapshot_turn       | int                   | 是   | 对应快照的对话轮次             |
| compressed_turns    | int                   | 是   | 被压缩的对话轮数               |
| success             | bool                  | 是   | 压缩是否成功                   |

### 5.2 数据流转

```text
1. 快照阶段（主线程，持锁）
   model.history_messages -> copy.deepcopy -> snapshot
   model.get_conversation_turn() -> snapshot_turn

2. 压缩阶段（后台线程，无锁）
   snapshot -> temp_model.chat() -> summary_text
   summary_text + snapshot_turn -> CompressionResult
   CompressionResult -> pending_replacement（持锁写入）

3. 合并阶段（主线程，持锁读取后无锁合并）
   CompressionResult + 当前历史 -> 新历史
   新历史 = [system_prompt] + [压缩摘要msg] + [snapshot_turn之后的新消息]
```

## 6. 核心算法设计

### 6.1 后台压缩执行算法

- **算法目标**：在后台线程中执行上下文压缩，生成摘要
- **输入**：历史消息快照、当前消息token数
- **输出**：CompressionResult
- **算法流程**：
  1. 创建临时模型实例（复用 `_create_temp_model`）
  2. 将快照历史注入临时模型
  3. 构建压缩提示词（复用 `SUMMARY_REQUEST_PROMPT`）
  4. 调用临时模型生成摘要
  5. 验证摘要完整性（复用 `_validate_summary`）
  6. 封装为 CompressionResult
  7. 持锁写入 `pending_replacement`
- **异常处理**：任何步骤失败，持锁设置 `compression_failed = True`
- **静默要求**：全程不调用 PrettyOutput，仅用 logging 记录

### 6.2 安全合并算法

- **算法目标**：将压缩结果安全合并到当前历史，不丢失新消息
- **输入**：CompressionResult、当前历史消息
- **输出**：合并后的新历史
- **算法流程**：
  1. 获取当前对话轮次 `current_turn`
  2. 从当前历史中提取 `snapshot_turn` 之后的新消息
  3. 构建新历史：`[system_prompt] + [压缩摘要] + new_messages`
  4. 替换模型的历史消息
- **关键保证**：新消息是快照之后产生的，压缩未触及，必须100%保留
