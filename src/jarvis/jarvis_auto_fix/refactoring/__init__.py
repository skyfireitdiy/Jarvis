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

__all__ = [
    "ExtractFunctionRefactorer",
    "ExtractionResult",
    "VariableInfo",
    "ExtractClassRefactorer",
    "ClassExtractionResult",
    "ClassMemberInfo",
    "ExtractionPlan",
    "InlineFunctionRefactorer",
    "InlineResult",
    "FunctionInfo",
    "MoveMethodRefactorer",
    "MoveResult",
    "MethodInfo",
]
