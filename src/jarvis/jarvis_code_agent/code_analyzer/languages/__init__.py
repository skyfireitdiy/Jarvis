"""语言支持实现模块。

包含各种编程语言的支持实现。
"""

# 导入所有语言支持类，以便自动注册
# 使用try-except确保某个语言支持导入失败不影响其他语言

from .python_language import PythonLanguageSupport

__all__ = ['PythonLanguageSupport']

# 尝试导入tree-sitter相关的语言支持
try:
    from .rust_language import RustLanguageSupport
    __all__.append('RustLanguageSupport')
except (ImportError, RuntimeError):
    pass

try:
    from .go_language import GoLanguageSupport
    __all__.append('GoLanguageSupport')
except (ImportError, RuntimeError):
    pass

try:
    from .c_cpp_language import CLanguageSupport, CppLanguageSupport
    __all__.extend(['CLanguageSupport', 'CppLanguageSupport'])
except (ImportError, RuntimeError):
    pass

