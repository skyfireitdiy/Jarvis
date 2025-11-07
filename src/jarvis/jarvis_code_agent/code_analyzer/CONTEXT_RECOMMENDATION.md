# 智能上下文推荐功能说明

## 功能概述

智能上下文推荐功能使用LLM进行语义理解，根据用户的编辑意图（任务描述、目标文件、符号名称等）自动推荐相关的上下文信息，帮助Agent更好地理解代码结构，做出更准确的编辑决策。

**重要**：本功能完全基于LLM实现，不依赖硬编码规则，能够进行真正的语义理解。

## 工作原理

### 1. LLM意图提取

使用LLM从用户输入中提取结构化信息：
- **意图识别**：识别编辑意图类型（add_feature, fix_bug, refactor, modify, optimize等）
- **目标文件提取**：从任务描述中推断目标文件路径
- **目标符号提取**：提取函数名、类名、变量名等
- **关键词提取**：提取关键概念和技术术语
- **任务描述**：生成任务的核心描述

### 2. 上下文推荐策略

结合LLM语义理解和代码结构分析：

#### 基于目标文件的推荐
- **依赖文件**：推荐目标文件导入/依赖的文件
- **被依赖文件**：推荐依赖目标文件的其他文件
- **测试文件**：推荐与目标文件相关的测试文件

#### 基于目标符号的推荐
- **符号定义**：推荐符号的定义位置
- **符号引用**：推荐符号的所有引用位置

#### LLM语义搜索
- **符号语义搜索**：使用LLM在符号表中进行语义搜索，找到真正相关的符号
- **文件语义搜索**：使用LLM在项目中进行语义搜索，找到真正相关的文件

#### LLM相关性评分
- **文件评分**：使用LLM对推荐的文件进行相关性评分（0-10分）
- **符号评分**：使用LLM对推荐的符号进行相关性评分（0-10分）
- **智能排序**：按相关性分数排序，最相关的排在前面

### 3. 推荐结果过滤和排序

- **去重**：移除重复的推荐项
- **过滤**：排除目标文件本身
- **LLM评分排序**：按LLM评分排序，而非简单的路径长度
- **限制数量**：限制推荐数量（文件最多10个，符号最多10个），避免信息过载

## 使用方式

### 自动集成

智能上下文推荐已自动集成到 `CodeAgent.run()` 方法中：

```python
agent = CodeAgent()
agent.run("修复 process_data 函数中的bug")
```

在Agent执行任务前，系统会：
1. 从用户输入中提取目标文件和符号
2. 生成上下文推荐
3. 将推荐结果注入到Agent的提示词中

### 手动使用

也可以手动使用上下文推荐器：

```python
from jarvis.jarvis_code_agent.code_analyzer import ContextManager, ContextRecommender

# 初始化
context_manager = ContextManager(project_root)
recommender = ContextRecommender(context_manager)

# 生成推荐
recommendation = recommender.recommend_context(
    user_input="修复 process_data 函数中的bug",
    target_files=["src/main.py"],
    target_symbols=["process_data"],
)

# 格式化输出
recommendation_text = recommender.format_recommendation(recommendation)
print(recommendation_text)
```

## 推荐结果格式

推荐结果包含以下信息：

```
💡 智能上下文推荐:
────────────────────────────────────────────────────────────
📌 推荐原因: 文件 main.py 的依赖文件；符号 process_data 的定义；关键词 'process_data' 相关的符号
📁 推荐文件 (5个):
   • src/utils/file_utils.py
   • src/utils/validation.py
   • src/models/data_model.py
   • src/tests/test_process.py
   • src/config/settings.py
   ... 还有2个文件
🔗 推荐符号 (3个):
   • function `process_data` (src/main.py:45)
   • function `validate_data` (src/utils/validation.py:12)
   • class `DataProcessor` (src/models/data_model.py:8)
🧪 相关测试 (2个):
   • tests/test_process.py
   • tests/integration/test_data_flow.py
────────────────────────────────────────────────────────────
```

## 推荐策略详解

### 关键词提取

从用户输入中提取可能的代码标识符：
- **驼峰命名**：`MyClass`, `ProcessData`（通常为类名）
- **下划线命名**：`process_data`, `get_user_info`（通常为函数名、变量名）
- **引号中的名称**：`"function_name"` 或 `'ClassName'`

过滤规则：
- 排除常见停用词（the, and, for等）
- 排除过短的词（长度 <= 2）
- 排除常见的中文停用词

### 意图检测

识别编辑意图类型：

| 意图类型 | 关键词 | 推荐策略 |
|---------|--------|---------|
| `add_feature` | 添加、新增、实现、add、implement | 推荐相关功能文件和测试文件 |
| `fix_bug` | 修复、解决、bug、fix、resolve | 推荐错误处理文件和测试文件 |
| `refactor` | 重构、优化、改进、refactor | 推荐所有相关文件和依赖 |
| `modify` | 修改、更新、改变、modify | 推荐直接相关的文件 |
| `unknown` | 其他 | 基于关键词和文件推荐 |

### 测试文件查找

自动查找与源文件相关的测试文件，支持以下命名模式：

**Python**:
- `test_<filename>.py`
- `<filename>_test.py`

**JavaScript/TypeScript**:
- `test_<filename>.js`
- `<filename>.test.js`
- `test_<filename>.ts`
- `<filename>.test.ts`

**Rust**:
- `<filename>_test.rs`

**Go**:
- `test_<filename>.go`

查找范围：
- 在项目根目录中搜索
- 优先在 `test` 或 `tests` 目录中查找
- 跳过隐藏目录和常见忽略目录（node_modules, __pycache__, target等）

## 性能考虑

### 优化措施

1. **限制推荐数量**
   - 推荐文件：最多10个
   - 推荐符号：最多10个
   - 推荐测试：最多5个

2. **缓存机制**
   - 利用ContextManager的文件缓存
   - 避免重复读取文件

3. **延迟计算**
   - 只在需要时进行文件搜索
   - 避免全项目扫描

4. **错误处理**
   - 推荐失败不影响主流程
   - 静默处理异常

### 性能影响

- **关键词提取**：O(n)，n为输入文本长度
- **符号搜索**：O(m)，m为符号表大小
- **文件搜索**：O(k)，k为项目文件数量（有优化）
- **总体耗时**：通常 < 1秒

## 扩展建议

### 1. 增强意图识别

- 使用NLP模型进行更准确的意图识别
- 支持更复杂的意图组合

### 2. 改进推荐算法

- 基于代码相似度的推荐
- 基于历史编辑模式的推荐
- 基于代码依赖深度的推荐

### 3. 个性化推荐

- 学习用户的编辑习惯
- 根据项目类型调整推荐策略

### 4. 实时更新

- 在文件修改后实时更新推荐
- 支持增量推荐更新

## 使用示例

### 示例1：修复bug

```python
# 用户输入
"修复 process_data 函数中的空指针异常"

# 系统推荐
💡 智能上下文推荐:
📌 推荐原因: 符号 process_data 的定义；符号 process_data 的引用位置；关键词 'process_data' 相关的符号
📁 推荐文件 (3个):
   • src/main.py (定义位置)
   • src/utils/validation.py (引用位置)
   • tests/test_process.py (测试文件)
🔗 推荐符号 (2个):
   • function `process_data` (src/main.py:45)
   • function `validate_input` (src/utils/validation.py:12)
```

### 示例2：添加功能

```python
# 用户输入
"在 UserService 类中添加 getUserProfile 方法"

# 系统推荐
💡 智能上下文推荐:
📌 推荐原因: 关键词 'UserService' 相关的符号；关键词 'getUserProfile' 相关的符号
📁 推荐文件 (4个):
   • src/services/user_service.py
   • src/models/user.py
   • src/repositories/user_repository.py
   • tests/test_user_service.py
🔗 推荐符号 (3个):
   • class `UserService` (src/services/user_service.py:10)
   • class `User` (src/models/user.py:5)
   • function `getUser` (src/repositories/user_repository.py:20)
```

### 示例3：重构代码

```python
# 用户输入
"重构 data_processor.py 中的数据处理逻辑"

# 系统推荐
💡 智能上下文推荐:
📌 推荐原因: 文件 data_processor.py 的依赖文件；文件 data_processor.py 的测试文件
📁 推荐文件 (6个):
   • src/utils/file_utils.py (依赖)
   • src/utils/validation.py (依赖)
   • src/models/data_model.py (依赖)
   • src/processors/base_processor.py (被依赖)
   • tests/test_data_processor.py (测试)
   • tests/integration/test_data_flow.py (集成测试)
```

## LLM实现

### 概述

上下文推荐功能**完全基于LLM实现**，不依赖硬编码规则。这确保了：

1. **真正的语义理解**：理解用户意图的真实含义，而不仅仅是关键词匹配
2. **智能提取**：更准确地提取目标文件、符号、概念等
3. **语义搜索**：在代码库中进行语义搜索，找到真正相关的代码
4. **相关性评分**：对推荐结果进行智能评分和排序

### 工作流程

```
用户输入
    ↓
LLM意图提取（提取目标文件、符号、意图、关键词）
    ↓
基于依赖关系的推荐（依赖文件、被依赖文件、测试文件）
    ↓
LLM语义搜索（查找更多相关符号和文件）
    ↓
LLM相关性评分（对推荐结果评分和排序）
    ↓
最终推荐结果
```

### 自动启用

LLM推荐功能已自动集成到CodeAgent中：

- **有LLM模型**：自动启用上下文推荐功能
- **无LLM模型**：跳过上下文推荐功能（不影响主流程）

### 详细说明

更多关于LLM实现的详细说明，请参考 [LLM_ENHANCEMENT.md](./LLM_ENHANCEMENT.md)。

## 总结

智能上下文推荐功能通过LLM语义理解和代码结构分析，自动推荐相关的上下文信息，帮助Agent：

1. **更快理解代码结构**：无需手动查找相关文件
2. **更准确做出决策**：基于LLM语义理解的完整上下文信息
3. **减少编辑错误**：了解依赖关系和影响范围
4. **提高编辑质量**：参考相关代码和测试文件

**核心优势**：
- ✅ **语义理解**：使用LLM理解用户意图的真实含义
- ✅ **智能搜索**：在代码库中进行语义搜索，找到真正相关的代码
- ✅ **相关性评分**：对推荐结果进行智能评分和排序

该功能已自动集成到CodeAgent中，当LLM模型可用时自动启用。如果LLM模型不可用，系统会跳过上下文推荐功能，不影响主流程。

