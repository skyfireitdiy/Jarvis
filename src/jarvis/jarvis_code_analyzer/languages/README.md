# 语言支持扩展指南

本文档说明如何为 `jarvis_code_analyzer` 添加新的编程语言支持。

## 架构概述

语言支持系统采用插件化架构：

1. **BaseLanguageSupport** - 基础抽象类，定义所有语言支持需要实现的接口
2. **LanguageRegistry** - 语言注册表，管理所有已注册的语言支持
3. **Language Support Classes** - 各语言的具体实现类

## 添加新语言支持的步骤

### 1. 创建语言支持类

在 `languages/` 目录下创建新的语言支持文件，例如 `javascript_language.py`：

```python
"""JavaScript语言支持实现。"""

from typing import Optional, Set

from ..base_language import BaseLanguageSupport
from ..dependency_analyzer import DependencyAnalyzer
from ..symbol_extractor import SymbolExtractor


class JavaScriptSymbolExtractor(SymbolExtractor):
    """JavaScript符号提取器实现。"""
    
    def extract_symbols(self, file_path: str, content: str) -> List[Symbol]:
        # 实现符号提取逻辑
        pass


class JavaScriptDependencyAnalyzer(DependencyAnalyzer):
    """JavaScript依赖分析器实现。"""
    
    def analyze_imports(self, file_path: str, content: str) -> List[Dependency]:
        # 实现依赖分析逻辑
        pass


class JavaScriptLanguageSupport(BaseLanguageSupport):
    """JavaScript语言支持类。"""

    @property
    def language_name(self) -> str:
        return 'javascript'

    @property
    def file_extensions(self) -> Set[str]:
        return {'.js', '.jsx', '.mjs'}

    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        return JavaScriptSymbolExtractor()

    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        return JavaScriptDependencyAnalyzer()
```

### 2. 在 `languages/__init__.py` 中导出

```python
from .javascript_language import JavaScriptLanguageSupport

__all__ = [
    # ... 其他语言
    'JavaScriptLanguageSupport',
]
```

### 3. 在 `language_support.py` 中注册

```python
from .languages import JavaScriptLanguageSupport

# 注册语言支持
register_language(JavaScriptLanguageSupport())
```

## 实现要求

### BaseLanguageSupport 接口

所有语言支持类必须实现以下接口：

- `language_name: str` - 语言名称（如 'python', 'rust'）
- `file_extensions: Set[str]` - 支持的文件扩展名集合
- `create_symbol_extractor() -> Optional[SymbolExtractor]` - 创建符号提取器
- `create_dependency_analyzer() -> Optional[DependencyAnalyzer]` - 创建依赖分析器

### 可选实现

- `is_source_file(file_path: str) -> bool` - 检查文件是否为源文件（有默认实现）
- `detect_language(file_path: str) -> Optional[str]` - 检测文件语言（有默认实现）

## 示例：完整的语言支持实现

参考以下文件作为完整实现的示例：

- `python_language.py` - Python语言支持（包含符号提取和依赖分析）
- `rust_language.py` - Rust语言支持（使用tree-sitter）
- `go_language.py` - Go语言支持（使用tree-sitter）
- `c_cpp_language.py` - C/C++语言支持（使用tree-sitter）

## 注意事项

1. **符号提取器**：如果语言不支持符号提取，`create_symbol_extractor()` 应返回 `None`
2. **依赖分析器**：如果语言不支持依赖分析，`create_dependency_analyzer()` 应返回 `None`
3. **错误处理**：在创建提取器或分析器时，如果依赖不可用（如tree-sitter语法），应优雅地返回 `None` 而不是抛出异常
4. **扩展名冲突**：如果多个语言支持相同的扩展名，第一个注册的将生效

## 测试新语言支持

添加新语言支持后，可以通过以下方式测试：

```python
from jarvis.jarvis_code_analyzer import detect_language, get_symbol_extractor, get_dependency_analyzer

# 检测语言
lang = detect_language('example.js')
assert lang == 'javascript'

# 获取符号提取器
extractor = get_symbol_extractor('javascript')
assert extractor is not None

# 获取依赖分析器
analyzer = get_dependency_analyzer('javascript')
assert analyzer is not None
```

