# 记忆系统 Pin 内容优化规范

## 功能概述

优化记忆系统的 `pin_content` 机制，避免其无限增长。将当前每次保存记忆就追加到字符串的方式，改为使用独立列表保存最近 10 条记忆内容，在需要组成提示词时再进行拼接。

### 背景与问题

**当前问题：**
- 每次调用 `save_memory` 时，都会将记忆内容追加到 `agent.pin_content` 字符串
- `pin_content` 随着时间推移无限增长，占用内存不断增加
- 在 `_handle_history_with_summary` 中，`pin_content` 被完整添加到提示词中，导致提示词过长

**目标：**
- 限制 pin 内容的大小，只保留最近 10 条记忆
- 优化内存占用
- 保持功能不变，向后兼容

## 接口定义

### Agent 类新增属性

```python
class Agent:
    def __init__(self):
        # ... 现有属性 ...
        self.recent_memories: List[str] = []  # 最近10条记忆内容列表
        self.MAX_RECENT_MEMORIES = 10  # 最大记忆数量
```

### save_memory 工具修改

**内部行为变化：**
- 修改 `_save_single_memory` 方法
- 不再追加到 `agent.pin_content`
- 改为添加到 `agent.recent_memories` 列表
- 自动维护最大 10 条，超过时移除最早的

### _handle_history_with_summary 方法修改

**行为变化：**
- 将 `agent.pin_content.strip()` 替换为 `"\n".join(agent.recent_memories)`
- 如果列表为空，不显示该 section

## 输入输出说明

### Agent 类

**输入：** 无（新增属性）

**输出：**
- `recent_memories`：List[str]，包含最近 10 条记忆内容

### save_memory._save_single_memory

**输入：**
- `memory_data`: Dict[str, Any]，包含记忆信息
- `agent`: Agent 实例

**输出：**
- 修改 `agent.recent_memories`（追加新记忆，限制最大 10 条）

### _handle_history_with_summary

**输入：** 无（使用 Agent 实例属性）

**输出：**
- 返回格式化的摘要字符串，其中包含最近 10 条记忆

## 功能行为

### 正常情况

1. **保存记忆时：**
   - 调用 `save_memory` 保存记忆
   - 记忆内容被添加到 `agent.recent_memories` 列表末尾
   - 如果列表长度超过 10，移除最早的元素

2. **生成提示词时：**
   - 调用 `_handle_history_with_summary`
   - 使用 `"\n".join(agent.recent_memories)` 拼接记忆
   - 添加到摘要中的「用户的原始需求和要求」section

3. **多 Agent 场景：**
   - 每个 Agent 有独立的 `recent_memories` 列表
   - 互不干扰

### 边界情况

1. **记忆不足 10 条：**
   - 显示实际数量的记忆
   - 不进行截断

2. **空列表：**
   - `recent_memories` 为空时
   - 不显示「用户的原始需求和要求」section

3. **首次保存：**
   - 列表从空开始
   - 第一条记忆正常添加

### 异常情况

1. **Agent 没有 recent_memories 属性：**
   - 兼容旧版本 Agent
   - 静默失败，不抛出异常

2. **记忆内容为空：**
   - 不添加到列表
   - 避免空字符串污染

3. **并发访问：**
   - 当前不涉及并发场景
   - 单线程运行

## 数据结构设计

### recent_memories 列表

```python
recent_memories: List[str] = [
    "记忆1内容",
    "记忆2内容",
    ...
]
```

**特点：**
- 列表索引 0 是最早的记忆
- 列表索引 -1 是最新的记忆
- 最大长度为 10

### 维护逻辑

```python
def add_memory(self, content: str):
    if not content or not content.strip():
        return  # 跳过空内容
    
    self.recent_memories.append(content.strip())
    
    if len(self.recent_memories) > self.MAX_RECENT_MEMORIES:
        self.recent_memories.pop(0)  # 移除最早的
```

## 向后兼容

### 保留 pin_content 属性

```python
class Agent:
    def __init__(self):
        self.pin_content = ""  # 保留但不使用，避免外部代码报错
        self.recent_memories = []  # 新的列表
```

### 兼容性处理

- 读取 `pin_content` 的代码不会报错（属性存在）
- 写入 `pin_content` 的代码不会影响新逻辑
- 建议逐步迁移使用方

## 迁移策略

### 阶段1：添加新数据结构

1. 在 `Agent.__init__` 中添加 `recent_memories` 列表
2. 在 `save_memory._save_single_memory` 中添加到新列表
3. 保留 `pin_content` 属性，不再写入

### 阶段2：修改使用方

1. 在 `_handle_history_with_summary` 中使用新列表
2. 其他使用 `pin_content` 的地方逐步迁移

### 阶段3：清理（可选，未来版本）

1. 移除 `pin_content` 属性
2. 确认没有外部依赖

## 验收标准

1. **功能正确性：**
   - ✅ 保存记忆时，内容正确添加到 `recent_memories`
   - ✅ 列表长度不超过 10 条
   - ✅ 超过 10 条时，正确移除最早的元素
   - ✅ 列表按时间顺序排列（最早的在前）

2. **提示词生成：**
   - ✅ `_handle_history_with_summary` 正确拼接记忆内容
   - ✅ 空列表时不显示 section
   - ✅ 内容格式正确（使用 `\n` 分隔）

3. **内存优化：**
   - ✅ 内存占用不再无限增长
   - ✅ 长时间运行后，内存占用稳定

4. **向后兼容：**
   - ✅ 外部代码访问 `pin_content` 不会报错
   - ✅ 现有功能不受影响

5. **多 Agent 隔离：**
   - ✅ 不同 Agent 的 `recent_memories` 互不干扰
   - ✅ 每个 Agent 独立维护自己的记忆列表

6. **边界处理：**
   - ✅ 空内容不添加到列表
   - ✅ 记忆不足 10 条时正常显示
   - ✅ 兼容旧版本 Agent（没有 recent_memories 属性）

## 测试用例

### 单元测试

1. 测试添加记忆到列表
2. 测试列表长度限制
3. 测试空内容过滤
4. 测试提示词拼接
5. 测试边界条件（0条、1条、10条、11条）

### 集成测试

1. 测试多次保存记忆后的行为
2. 测试多 Agent 场景
3. 测试会话恢复后的状态
4. 测试与现有功能的兼容性

## 性能指标

- **内存占用：** 长时间运行后，pin 相关内存占用 < 1MB（假设每条记忆 < 10KB）
- **时间复杂度：** 添加记忆 O(1)，拼接提示词 O(n)，其中 n ≤ 10

## 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| 外部代码依赖 pin_content | 高 | 中 | 保留属性，向后兼容 |
| 记忆丢失 | 高 | 低 | 保留到短期记忆，不丢失数据 |
| 性能回退 | 中 | 低 | 列表操作比字符串拼接更高效 |
| 并发问题 | 低 | 低 | 单线程运行，暂不考虑 |

## 参考资料

- 相关文件：
  - `src/jarvis/jarvis_tools/save_memory.py`
  - `src/jarvis/jarvis_agent/__init__.py`
  - `src/jarvis/jarvis_utils/globals.py`
- 相关方法论：
  - `.jarvis/rules/development_workflow/sdd.md`（SDD 规则）
  - 全局方法论：防止数据结构无限增长优化