"""语言支持模块。

提供语言检测和工厂函数，使用语言注册表管理所有语言支持。
"""

from jarvis.jarvis_utils.output import PrettyOutput

from typing import Optional

from .dependency_analyzer import DependencyAnalyzer
from .language_registry import detect_language as _detect_language
from .language_registry import get_dependency_analyzer as _get_dependency_analyzer
from .language_registry import get_symbol_extractor as _get_symbol_extractor
from .language_registry import register_language
from .symbol_extractor import SymbolExtractor

# 自动注册所有语言支持
# 使用try-except确保某个语言支持导入失败不影响其他语言

# Python语言支持（必需，因为它是核心语言）
try:
    from .languages import PythonLanguageSupport

    register_language(PythonLanguageSupport())
except ImportError as e:
    PrettyOutput.auto_print(f"⚠️ Warning: Failed to import PythonLanguageSupport: {e}")

# Rust语言支持（可选，需要tree-sitter）
try:
    from .languages import RustLanguageSupport

    register_language(RustLanguageSupport())
except (ImportError, RuntimeError):
    pass  # 静默失败，tree-sitter可能不可用

# Go语言支持（可选，需要tree-sitter）
try:
    from .languages import GoLanguageSupport

    register_language(GoLanguageSupport())
except (ImportError, RuntimeError):
    pass  # 静默失败，tree-sitter可能不可用

# C语言支持（可选，需要tree-sitter）
try:
    from .languages import CLanguageSupport

    register_language(CLanguageSupport())
except (ImportError, RuntimeError):
    pass  # 静默失败，tree-sitter可能不可用

# C++语言支持（可选，需要tree-sitter）
try:
    from .languages import CppLanguageSupport

    register_language(CppLanguageSupport())
except (ImportError, RuntimeError):
    pass  # 静默失败，tree-sitter可能不可用

# JavaScript语言支持（可选，需要tree-sitter）
try:
    from .languages import JavaScriptLanguageSupport

    register_language(JavaScriptLanguageSupport())
except (ImportError, RuntimeError):
    pass  # 静默失败，tree-sitter可能不可用

# TypeScript语言支持（可选，需要tree-sitter）
try:
    from .languages import TypeScriptLanguageSupport

    register_language(TypeScriptLanguageSupport())
except (ImportError, RuntimeError):
    pass  # 静默失败，tree-sitter可能不可用

# Java语言支持（可选，需要tree-sitter）
try:
    from .languages import JavaLanguageSupport

    register_language(JavaLanguageSupport())
except (ImportError, RuntimeError):
    pass  # 静默失败，tree-sitter可能不可用


def detect_language(file_path: str) -> Optional[str]:
    """检测文件的编程语言。

    Args:
        file_path: 文件路径

    Returns:
        语言名称，如果无法检测则返回None
    """
    return _detect_language(file_path)


def get_symbol_extractor(language: str) -> Optional[SymbolExtractor]:
    """获取指定语言的符号提取器。

    Args:
        language: 语言名称

    Returns:
        SymbolExtractor实例，如果不支持则返回None
    """
    return _get_symbol_extractor(language)


def get_dependency_analyzer(language: str) -> Optional[DependencyAnalyzer]:
    """获取指定语言的依赖分析器。

    Args:
        language: 语言名称

    Returns:
        DependencyAnalyzer实例，如果不支持则返回None
    """
    return _get_dependency_analyzer(language)
