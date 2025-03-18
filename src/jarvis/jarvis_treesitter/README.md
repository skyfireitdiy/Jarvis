# Tree-sitter 代码数据库

基于 tree-sitter 的代码分析工具，支持快速查询符号的定义位置、声明位置、引用位置和调用关系。

## 功能特点

- 支持多种编程语言：Python、C、C++、Go、Rust
- 自动下载和编译语言语法文件
- 查找符号定义
- 查找符号引用
- 查找函数调用者

## 安装

```bash
pip install -r requirements.txt
```

## 使用方法

### 基本用法

```python
from jarvis.jarvis_treesitter import CodeDatabase

# 初始化代码数据库（自动下载所需的语法文件）
db = CodeDatabase()  # 语法文件将保存到 ~/.jarvis/treesitter 目录

# 索引源文件
db.index_file("path/to/file.py")

# 查找符号
symbols = db.find_symbol("function_name")

# 查找符号引用
references = db.find_references(symbols[0])

# 查找函数调用者
callers = db.find_callers(symbols[0])
```

### 自定义语法文件位置

虽然默认会使用 `~/.jarvis/treesitter` 目录，但您仍然可以指定自定义目录：

```python
from jarvis.jarvis_treesitter import CodeDatabase

# 使用自定义语法文件目录
db = CodeDatabase(grammar_dir="/path/to/grammars")

# 不自动下载缺失的语法文件
db = CodeDatabase(auto_download=False)
```

### 手动下载语法文件

```python
from jarvis.jarvis_treesitter import setup_default_grammars, GrammarBuilder, LanguageType, DEFAULT_GRAMMAR_DIR

# 下载所有支持的语言的语法文件到默认目录 (~/.jarvis/treesitter)
setup_default_grammars()

# 或者使用自定义目录
grammar_dir = "/path/to/grammars"
builder = GrammarBuilder(grammar_dir)
builder.ensure_all_grammars()  # 下载所有语言
builder.ensure_grammar(LanguageType.PYTHON)  # 只下载特定语言

# 查看默认语法文件目录
print(DEFAULT_GRAMMAR_DIR)  # 输出: ~/.jarvis/treesitter
```

## 命令行工具

提供了一个示例脚本 `example.py` 演示基本用法：

```bash
# 索引当前目录并查找名为 "main" 的符号
python -m jarvis.jarvis_treesitter.example --dir . --symbol main

# 只索引Python文件
python -m jarvis.jarvis_treesitter.example --dir . --ext .py --symbol main

# 使用自定义语法文件目录（默认是 ~/.jarvis/treesitter）
python -m jarvis.jarvis_treesitter.example --dir . --grammar-dir /path/to/grammars --symbol main

# 不自动下载语法文件
python -m jarvis.jarvis_treesitter.example --dir . --no-download --symbol main
```

## 语法文件位置

默认情况下，所有tree-sitter语法文件将保存在 `~/.jarvis/treesitter` 目录中。这些文件只需要下载和编译一次，后续使用时会自动加载。

## 支持的语言

| 语言   | 文件扩展名                | 支持的符号类型                                   |
|--------|--------------------------|--------------------------------------------------|
| Python | .py                      | 函数、类、变量、导入、方法                        |
| C      | .c, .h                   | 函数、结构体、枚举、类型定义、宏、变量            |
| C++    | .cpp, .hpp, .cc, .hh     | 函数、类、结构体、枚举、命名空间、模板、变量      |
| Go     | .go                      | 函数、结构体、接口、包、导入、变量                |
| Rust   | .rs                      | 函数、结构体、枚举、特征、实现、模块、变量        | 