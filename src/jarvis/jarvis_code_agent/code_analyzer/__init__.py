"""Jarvis代码分析器模块。

提供符号提取、依赖分析和上下文管理功能。
"""

from .base_language import BaseLanguageSupport
from .context_manager import ContextManager
from .context_manager import EditContext
from .context_manager import Reference
from .context_recommender import ContextRecommendation
from .dependency_analyzer import Dependency
from .dependency_analyzer import DependencyAnalyzer
from .dependency_analyzer import DependencyGraph
from .impact_analyzer import Edit
from .impact_analyzer import Impact
from .impact_analyzer import ImpactAnalyzer
from .impact_analyzer import ImpactReport
from .impact_analyzer import ImpactType
from .impact_analyzer import InterfaceChange
from .impact_analyzer import RiskLevel
from .impact_analyzer import TestDiscoverer
from .impact_analyzer import parse_git_diff_to_edits
from .language_registry import LanguageRegistry
from .language_registry import get_registry
from .language_registry import register_language
from .language_support import detect_language
from .language_support import get_dependency_analyzer
from .language_support import get_symbol_extractor
from .llm_context_recommender import ContextRecommender
from .symbol_extractor import Symbol
from .symbol_extractor import SymbolExtractor
from .symbol_extractor import SymbolTable

__all__ = [
    # Symbol extraction
    "Symbol",
    "SymbolTable",
    "SymbolExtractor",
    # Dependency analysis
    "Dependency",
    "DependencyGraph",
    "DependencyAnalyzer",
    # Context management
    "ContextManager",
    "EditContext",
    "Reference",
    # Context recommendation
    "ContextRecommender",
    "ContextRecommendation",
    # Language support
    "detect_language",
    "get_symbol_extractor",
    "get_dependency_analyzer",
    # Language registry
    "BaseLanguageSupport",
    "LanguageRegistry",
    "get_registry",
    "register_language",
    # Impact analysis
    "ImpactAnalyzer",
    "Impact",
    "ImpactReport",
    "ImpactType",
    "RiskLevel",
    "InterfaceChange",
    "Edit",
    "TestDiscoverer",
    "parse_git_diff_to_edits",
]
