# CodeAgent上下文集成分析

## 当前实现状态

### 1. 上下文管理器的初始化

**位置**: `CodeAgent.__init__`

```python
# 初始化上下文管理器
self.context_manager = ContextManager(self.root_dir)
```

**时机**: CodeAgent创建时
**状态**: ✅ 已实现

### 2. 上下文更新机制

**位置**: `CodeAgent._on_after_tool_call`

```python
# 更新上下文管理器：当文件被修改后，更新符号表和依赖图
for file_path in modified_files:
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self.context_manager.update_context_for_file(file_path, content)
        except Exception:
            pass
```

**时机**: 文件修改后（工具调用后回调）
**状态**: ✅ 已实现
**作用**: 维护符号表和依赖图的增量更新

### 3. 上下文提供机制

**位置**: 目前**未实现**
**状态**: ❌ 缺失

## 问题分析

### 当前问题

1. **被动更新，主动使用缺失**
   - 上下文管理器只在文件修改后更新
   - 没有在编辑前主动提供上下文信息给Agent

2. **上下文信息未注入到Agent提示词**
   - Agent无法获取编辑位置的上下文信息
   - 无法利用符号表、依赖关系等信息

3. **缺少编辑前上下文分析**
   - 没有在应用补丁前分析编辑位置
   - 无法提供当前作用域、使用的符号等信息

## 上下文内容分析

### ContextManager提供的上下文信息

`get_edit_context()` 方法返回的 `EditContext` 包含：

1. **当前作用域** (`current_scope`)
   - 函数或类定义
   - 包含签名和文档字符串

2. **使用的符号** (`used_symbols`)
   - 编辑区域使用的函数、类、变量等

3. **导入的符号** (`imported_symbols`)
   - 文件中导入的所有符号

4. **相关文件** (`relevant_files`)
   - 依赖的文件（导入的模块）
   - 依赖该文件的文件（被导入的模块）

5. **上下文摘要** (`context_summary`)
   - 人类可读的上下文摘要

### 其他可用方法

1. **`find_references(symbol_name, file_path)`**
   - 查找符号的所有引用位置

2. **`find_definition(symbol_name, file_path)`**
   - 查找符号的定义位置

## 集成方案

### 方案1: 在read_code工具中自动提供上下文（已实现）⭐

**时机**: Agent读取代码文件时

**实现位置**: `jarvis_tools/read_code.py`

**步骤**:
1. 在 `ReadCodeTool._handle_single_file()` 中，读取文件后自动获取上下文
2. 从Agent获取CodeAgent实例，进而获取ContextManager
3. 调用 `get_edit_context()` 获取读取区域的上下文
4. 将上下文信息附加到文件内容输出中

**优点**:
- ✅ **时机正确**：在Agent读取代码时提供，此时Agent还未生成patch
- ✅ **自动提供**：无需Agent主动调用，自动附在read_code的输出中
- ✅ **精准定位**：根据读取的行号范围提供精确的上下文
- ✅ **不影响性能**：只在读取代码时提供，不影响其他操作
- ✅ **符合工作流**：Agent通常先read_code再编辑，符合"先分析再修改"的原则

**缺点**:
- 如果Agent不读取代码直接编辑，则无法获取上下文（这种情况较少）

### 方案2: 在Agent提示词中提供上下文工具（可选）

**时机**: Agent需要时主动调用

**实现方式**: 创建新的工具 `get_edit_context`

**步骤**:
1. 在CodeAgent中添加工具 `get_edit_context`
2. Agent可以在编辑前调用此工具获取上下文
3. 工具返回格式化的上下文信息

**优点**:
- 按需获取，不增加不必要的开销
- Agent可以灵活决定何时需要上下文

**缺点**:
- 需要Agent主动调用
- 可能被忽略

### 方案3: 在系统提示词中说明上下文能力（已实现）

**时机**: CodeAgent初始化时

**实现方式**: 在系统提示词中添加上下文使用说明

**步骤**:
1. 在 `_get_system_prompt()` 中添加上下文使用指南
2. 说明如何利用上下文信息进行更好的编辑

**优点**:
- 简单易实现
- 引导Agent使用上下文

**缺点**:
- 只是说明，不主动提供
- 依赖Agent的理解和执行

## 推荐实现方案

### 当前实现：方案1（read_code工具集成）⭐

**已实现的功能**:
1. ✅ 在 `read_code` 工具中自动提供上下文
2. ✅ 在 `CodeAgent` 中建立与Agent的关联
3. ✅ 在系统提示词中说明上下文能力

**工作流程**:
```
Agent调用read_code工具
    ↓
读取文件内容
    ↓
自动获取文件上下文（当前作用域、使用的符号、导入的符号、相关文件）
    ↓
将上下文信息附加到输出中
    ↓
Agent看到代码+上下文信息
    ↓
Agent基于上下文信息生成更准确的patch
```

**上下文信息格式**:
```
📋 代码上下文信息:
────────────────────────────────────────────────────────────
📍 当前作用域: function `process_data`
   └─ 签名: def process_data(input_file: str, output_file: str) -> None
🔗 使用的符号: `read_file`, `write_file`, `validate_data`
📦 导入的符号: `os`, `json`, `logging`
📁 相关文件 (3个):
   • src/utils/file_utils.py
   • src/utils/validation.py
   • tests/test_process.py
────────────────────────────────────────────────────────────
```

### 具体实现步骤（已实现）

#### 步骤1: 在read_code工具中集成上下文提供 ✅

**文件**: `jarvis_tools/read_code.py`

**实现**:
- 在 `_handle_single_file()` 方法中，读取文件后自动调用 `_get_file_context()`
- `_get_file_context()` 方法从Agent获取CodeAgent实例和ContextManager
- 根据读取的行号范围获取编辑上下文
- 将格式化的上下文信息附加到文件内容输出中

#### 步骤2: 在CodeAgent中建立与Agent的关联 ✅

**文件**: `jarvis_code_agent/code_agent.py`

**实现**:
```python
# 在CodeAgent.__init__中
self.agent = Agent(...)
self.agent._code_agent = self  # 建立关联
```

#### 步骤3: 更新系统提示词 ✅

**文件**: `jarvis_code_agent/code_agent.py`

**实现**:
在 `_get_system_prompt()` 中已添加：
```python
- 上下文理解：系统已维护项目的符号表和依赖关系图，可以帮助理解代码结构和依赖关系
```

## 上下文提供的时机总结

### 当前实现状态

| 时机 | 操作 | 状态 |
|------|------|------|
| CodeAgent初始化 | 创建ContextManager | ✅ 已实现 |
| Agent读取代码时 | 自动提供上下文信息 | ✅ 已实现 |
| 文件修改后 | 更新符号表和依赖图 | ✅ 已实现 |

### 可选增强

| 时机 | 操作 | 优先级 |
|------|------|--------|
| 项目启动时（可选） | 构建初始符号表和依赖图 | 🔶 可选 |
| Agent主动查询 | 提供符号查找、引用查找工具 | 🔶 可选 |

## 上下文内容详细说明

### EditContext包含的信息

```python
@dataclass
class EditContext:
    file_path: str                    # 文件路径
    line_start: int                   # 编辑起始行
    line_end: int                     # 编辑结束行
    current_scope: Optional[Symbol]   # 当前作用域（函数/类）
    used_symbols: List[Symbol]        # 使用的符号
    imported_symbols: List[Symbol]    # 导入的符号
    relevant_files: List[str]         # 相关文件
    context_summary: str               # 上下文摘要（人类可读）
```

### 上下文摘要示例

```
Current scope: function process_data
  Signature: def process_data(input_file: str, output_file: str) -> None
Used symbols: read_file, write_file, validate_data
Imported symbols: os, json, logging
Relevant files: 3 files
  - src/utils/file_utils.py
  - src/utils/validation.py
  - tests/test_process.py
```

## 性能考虑

### 上下文获取的性能

- **符号提取**: O(n)，n为文件大小
- **依赖分析**: O(m)，m为导入语句数量
- **上下文构建**: O(k)，k为符号数量

### 优化建议

1. **缓存机制**: ContextManager已实现文件内容缓存
2. **增量更新**: 文件修改后只更新该文件的符号和依赖
3. **延迟加载**: 只在需要时构建依赖图
4. **异步处理**: 大型项目可以考虑异步构建初始符号表

## 总结

### 已实现的集成方案 ✅

当前实现已经完成了上下文管理的完整集成：

1. ✅ **上下文管理器**: 在CodeAgent初始化时创建
2. ✅ **自动上下文提供**: 在read_code工具中自动提供上下文信息
3. ✅ **增量更新**: 文件修改后自动更新符号表和依赖图
4. ✅ **系统提示**: 在系统提示词中说明上下文能力

### 工作流程

```
用户请求 → CodeAgent.run()
    ↓
Agent调用read_code工具读取代码
    ↓
read_code工具自动获取并附加上下文信息
    ↓
Agent看到：代码内容 + 上下文信息（作用域、符号、依赖等）
    ↓
Agent基于上下文信息生成更准确的patch
    ↓
EditFileHandler应用patch
    ↓
_on_after_tool_call更新上下文管理器
```

### 优势

1. **时机正确**: 在Agent读取代码时提供，此时还未生成patch
2. **自动提供**: 无需Agent主动调用，自动附在read_code输出中
3. **精准定位**: 根据读取的行号范围提供精确的上下文
4. **不影响性能**: 只在读取代码时提供，不影响其他操作
5. **符合工作流**: Agent通常先read_code再编辑，符合"先分析再修改"的原则

### 可选增强

1. **项目启动时构建初始符号表**: 可以预先分析整个项目
2. **提供上下文查询工具**: 让Agent可以主动查询符号定义和引用
3. **智能上下文推荐**: 根据编辑意图推荐相关上下文

