# Tree-sitter 分析工具使用指南

本文档说明如何使用 Jarvis 的 Tree-sitter 分析工具来查找代码中的符号定义、引用和调用关系。

## 概述

Tree-sitter 分析工具 (`treesitter_analyzer`) 可以帮助你快速分析代码库，查找符号的定义位置、引用位置和调用关系，支持多种编程语言，包括：

- Python
- C
- C++
- Go
- Rust

## 功能特点

- **自动下载语法文件**：工具会自动下载和编译需要的语法文件，保存在 `~/.jarvis/treesitter` 目录
- **多语言支持**：支持多种常用编程语言
- **符号查找**：查找函数、类、变量等符号的定义位置
- **引用查找**：查找符号的所有引用位置
- **调用关系**：查找函数的所有调用位置
- **自动索引**：每次操作前会自动索引指定目录的代码

## 使用方法

在 Jarvis 中，可以通过工具调用格式来使用这个工具：

```yaml
<TOOL_CALL>
name: treesitter_analyzer
arguments:
    action: find_symbol
    symbol_name: main
    directory: /path/to/code
    extensions: [".c", ".h"]
    max_results: 10
</TOOL_CALL>
```

## 支持的操作

Tree-sitter 分析工具支持以下操作类型：

1. **查找符号** (`find_symbol`)：查找符号的定义位置
2. **查找引用** (`find_references`)：查找符号的引用位置
3. **查找调用者** (`find_callers`)：查找函数的调用位置

**注意**：每个操作前都会自动先索引指定目录下的代码文件，不需要单独执行索引步骤。

## 参数说明

工具接受以下参数：

- `action`：**必需**，操作类型，可选值：`find_symbol`、`find_references`、`find_callers`
- `symbol_name`：**必需**，符号名称，如函数名、类名、变量名
- `directory`：**必需**，要索引的代码目录，默认为当前目录
- `extensions`：可选，要索引的文件扩展名列表，如 `[".py", ".c"]`，不指定则索引所有支持的文件类型
- `max_results`：可选，最大返回结果数量，默认为 20

## 使用示例

### 查找符号定义

```yaml
<TOOL_CALL>
name: treesitter_analyzer
arguments:
    action: find_symbol
    symbol_name: main
    directory: /path/to/code
</TOOL_CALL>
```

### 查找符号引用

```yaml
<TOOL_CALL>
name: treesitter_analyzer
arguments:
    action: find_references
    symbol_name: add_user
    directory: /path/to/code
    extensions: [".py"]
</TOOL_CALL>
```

### 查找函数调用者

```yaml
<TOOL_CALL>
name: treesitter_analyzer
arguments:
    action: find_callers
    symbol_name: process_data
    directory: /path/to/code
    max_results: 50
</TOOL_CALL>
```

## 返回结果

工具返回的结果包含以下字段：

- `success`：操作是否成功
- `stdout`：操作的输出信息，包括索引摘要和查询结果
- `stderr`：操作的错误信息（如果有）

此外，不同操作还会返回其他特定字段：

- `find_symbol`：返回 `symbols` 列表
- `find_references`：返回 `symbol` 和 `references` 列表
- `find_callers`：返回 `function` 和 `callers` 列表
- 所有操作都会包含 `indexed_files` 和 `skipped_files` 的信息

## 注意事项

1. 首次使用时，工具会自动下载和编译语法文件，可能需要一些时间
2. 大型代码库索引可能较慢，请耐心等待
3. 为提高性能，可以使用 `extensions` 参数限制索引的文件类型
4. 工具会缓存索引结果，后续查询同一代码库速度会更快
5. 每次操作都会重新索引目录，确保分析结果基于最新的代码 