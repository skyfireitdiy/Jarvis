"""Jarvis代码分析器模块。

提供符号提取、依赖分析和上下文管理功能。
"""

from .symbol_extractor import Symbol, SymbolTable, SymbolExtractor
from .dependency_analyzer import Dependency, DependencyGraph, DependencyAnalyzer
from .context_manager import ContextManager, EditContext, Reference
from .context_recommender import ContextRecommendation
from .llm_context_recommender import ContextRecommender
from .language_support import (
    detect_language,
    get_symbol_extractor,
    get_dependency_analyzer,
)
from .base_language import BaseLanguageSupport
from .language_registry import LanguageRegistry, get_registry, register_language
from .impact_analyzer import (
    ImpactAnalyzer,
    Impact,
    ImpactReport,
    ImpactType,
    RiskLevel,
    InterfaceChange,
    Edit,
    TestDiscoverer,
    parse_git_diff_to_edits,
)
from .structured_code import StructuredCodeExtractor

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
    # Structured code extraction
    "StructuredCodeExtractor",
]
