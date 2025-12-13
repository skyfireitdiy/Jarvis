"""基础语言支持抽象类。

定义所有语言支持需要实现的接口，便于扩展新的语言支持。
"""

from abc import ABC
from abc import abstractmethod
from typing import Optional
from typing import Set

from .dependency_analyzer import DependencyAnalyzer
from .symbol_extractor import SymbolExtractor


class BaseLanguageSupport(ABC):
    """语言支持的基础抽象类。

    所有语言支持类都应该继承此类并实现所需的方法。
    """

    @property
    @abstractmethod
    def language_name(self) -> str:
        """返回语言名称（如 'python', 'rust', 'go'）。"""
        pass

    @property
    @abstractmethod
    def file_extensions(self) -> Set[str]:
        """返回该语言支持的文件扩展名集合（如 {'.py', '.pyw'}）。"""
        pass

    @abstractmethod
    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        """创建并返回该语言的符号提取器实例。

        Returns:
            SymbolExtractor实例，如果不支持符号提取则返回None
        """
        pass

    @abstractmethod
    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        """创建并返回该语言的依赖分析器实例。

        Returns:
            DependencyAnalyzer实例，如果不支持依赖分析则返回None
        """
        pass

    def is_source_file(self, file_path: str) -> bool:
        """检查文件是否为该语言的源文件。

        Args:
            file_path: 文件路径

        Returns:
            如果是该语言的源文件返回True，否则返回False
        """
        import os

        _, ext = os.path.splitext(file_path)
        return ext in self.file_extensions

    def detect_language(self, file_path: str) -> Optional[str]:
        """检测文件是否属于该语言。

        Args:
            file_path: 文件路径

        Returns:
            如果属于该语言返回language_name，否则返回None
        """
        if self.is_source_file(file_path):
            return self.language_name
        return None
