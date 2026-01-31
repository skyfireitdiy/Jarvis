"""Refactoring Module

This module provides code refactoring capabilities.
"""

from jarvis.jarvis_auto_fix.refactoring.extract_class import (
    ClassExtractionResult,
    ClassMemberInfo,
    ExtractClassRefactorer,
    ExtractionPlan,
)
from jarvis.jarvis_auto_fix.refactoring.extract_function import (
    ExtractFunctionRefactorer,
    ExtractionResult,
    VariableInfo,
)
from jarvis.jarvis_auto_fix.refactoring.extract_interface import (
    ExtractInterfaceRefactorer,
    InterfaceExtractionResult,
    InterfaceInfo,
)
from jarvis.jarvis_auto_fix.refactoring.inline_function import (
    InlineFunctionRefactorer,
    InlineResult,
    FunctionInfo,
)
from jarvis.jarvis_auto_fix.refactoring.move_method import (
    MoveMethodRefactorer,
    MoveResult,
    MethodInfo,
)
from jarvis.jarvis_auto_fix.refactoring.split_module import (
    SplitModuleRefactorer,
    ModuleSplitResult,
    SplitPlan,
    ModuleInfo,
    SplitGroup,
)
from jarvis.jarvis_auto_fix.refactoring.dependency_injection import (
    DependencyInjectionAnalyzer,
    DependencyInjectionRefactorer,
    DependencyInfo,
    InjectionResult,
)

__all__ = [
    "ExtractFunctionRefactorer",
    "ExtractionResult",
    "VariableInfo",
    "ExtractClassRefactorer",
    "ClassExtractionResult",
    "ClassMemberInfo",
    "ExtractionPlan",
    "ExtractInterfaceRefactorer",
    "InterfaceExtractionResult",
    "InterfaceInfo",
    "InlineFunctionRefactorer",
    "InlineResult",
    "FunctionInfo",
    "MoveMethodRefactorer",
    "MoveResult",
    "MethodInfo",
    "SplitModuleRefactorer",
    "ModuleSplitResult",
    "SplitPlan",
    "ModuleInfo",
    "SplitGroup",
    "DependencyInjectionAnalyzer",
    "DependencyInjectionRefactorer",
    "DependencyInfo",
    "InjectionResult",
]
