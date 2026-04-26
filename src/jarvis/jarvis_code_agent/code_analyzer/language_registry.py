"""语言注册表。

管理所有语言支持的注册和发现机制。
"""

from jarvis.jarvis_utils.output import PrettyOutput

import os
from typing import Dict
from typing import Optional
from typing import Set

from .base_language import BaseLanguageSupport
from .dependency_analyzer import DependencyAnalyzer
from .symbol_extractor import SymbolExtractor


class LanguageRegistry:
    """语言支持注册表。

    负责管理所有已注册的语言支持，提供语言检测和工厂方法。
    """

    def __init__(self) -> None:
        self._languages: Dict[str, BaseLanguageSupport] = {}
        self._extension_map: Dict[str, str] = {}  # extension -> language_name

    def register(self, language_support: BaseLanguageSupport) -> None:
        """注册一个语言支持。

        Args:
            language_support: 语言支持实例
        """
        lang_name = language_support.language_name
        self._languages[lang_name] = language_support

        # 注册文件扩展名映射
        for ext in language_support.file_extensions:
            # 如果扩展名已存在，记录警告但不覆盖（保留第一个注册的）
            if ext in self._extension_map and self._extension_map[ext] != lang_name:
                PrettyOutput.auto_print(
                    f"Warning: Extension {ext} already registered for "
                    f"{self._extension_map[ext]}, ignoring registration for {lang_name}"
                )
            else:
                self._extension_map[ext] = lang_name

    def unregister(self, language_name: str) -> None:
        """取消注册一个语言支持。

        Args:
            language_name: 语言名称
        """
        if language_name in self._languages:
            self._languages.pop(language_name)
            # 移除扩展名映射
            extensions_to_remove = [
                ext
                for ext, lang in self._extension_map.items()
                if lang == language_name
            ]
            for ext in extensions_to_remove:
                del self._extension_map[ext]

    def detect_language(self, file_path: str) -> Optional[str]:
        """根据文件路径检测编程语言。

        Args:
            file_path: 文件路径

        Returns:
            语言名称，如果无法检测则返回None
        """
        _, ext = os.path.splitext(file_path)
        return self._extension_map.get(ext)

    def get_language_support(self, language_name: str) -> Optional[BaseLanguageSupport]:
        """获取指定语言的支持实例。

        Args:
            language_name: 语言名称

        Returns:
            语言支持实例，如果未注册则返回None
        """
        return self._languages.get(language_name)

    def get_symbol_extractor(self, language_name: str) -> Optional[SymbolExtractor]:
        """获取指定语言的符号提取器。

        Args:
            language_name: 语言名称

        Returns:
            SymbolExtractor实例，如果不支持则返回None
        """
        lang_support = self.get_language_support(language_name)
        if lang_support:
            return lang_support.create_symbol_extractor()
        return None

    def get_dependency_analyzer(
        self, language_name: str
    ) -> Optional[DependencyAnalyzer]:
        """获取指定语言的依赖分析器。

        Args:
            language_name: 语言名称

        Returns:
            DependencyAnalyzer实例，如果不支持则返回None
        """
        lang_support = self.get_language_support(language_name)
        if lang_support:
            return lang_support.create_dependency_analyzer()
        return None

    def get_supported_languages(self) -> Set[str]:
        """获取所有已注册的语言名称集合。

        Returns:
            语言名称集合
        """
        return set(self._languages.keys())

    def is_supported(self, file_path: str) -> bool:
        """检查文件是否被支持。

        Args:
            file_path: 文件路径

        Returns:
            如果文件被支持返回True，否则返回False
        """
        return self.detect_language(file_path) is not None


# 全局注册表实例
_registry = LanguageRegistry()


def get_registry() -> LanguageRegistry:
    """获取全局语言注册表实例。

    Returns:
        全局LanguageRegistry实例
    """
    return _registry


def register_language(language_support: BaseLanguageSupport) -> None:
    """注册一个语言支持（便捷函数）。

    Args:
        language_support: 语言支持实例
    """
    _registry.register(language_support)


def detect_language(file_path: str) -> Optional[str]:
    """检测文件的语言（便捷函数）。

    Args:
        file_path: 文件路径

    Returns:
        语言名称，如果无法检测则返回None
    """
    return _registry.detect_language(file_path)


def get_symbol_extractor(language: str) -> Optional[SymbolExtractor]:
    """获取指定语言的符号提取器（便捷函数）。

    Args:
        language: 语言名称

    Returns:
        SymbolExtractor实例，如果不支持则返回None
    """
    return _registry.get_symbol_extractor(language)


def get_dependency_analyzer(language: str) -> Optional[DependencyAnalyzer]:
    """获取指定语言的依赖分析器（便捷函数）。

    Args:
        language: 语言名称

    Returns:
        DependencyAnalyzer实例，如果不支持则返回None
    """
    return _registry.get_dependency_analyzer(language)
