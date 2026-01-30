"""
jarvis_dependency_manager - Dependency Auto-Management Module

This module provides automatic dependency checking and update suggestions.

Features:
    - Check dependency versions (pyproject.toml, requirements.txt)
    - Query PyPI for latest versions
    - Provide update suggestions with compatibility analysis
    - Generate dependency reports
    - Track dependency check history

Usage:
    >>> from jarvis.jarvis_dependency_manager import DependencyManager, DependencyReporter
    >>> manager = DependencyManager()
    >>> dependencies = manager.check_dependencies()
    >>> suggestions = manager.get_update_suggestions(dependencies)
    >>> reporter = DependencyReporter()
    >>> report = reporter.generate_report(dependencies, suggestions)
    >>> print(report)

Safety:
    - Does not automatically execute pip install
    - Does not modify pyproject.toml
    - Only provides suggestions and analysis
"""

# Public API exports
from jarvis.jarvis_dependency_manager.manager import (
    DependencyInfo,
    DependencyManager,
    UpdateSuggestion,
    UpdateType,
)
from jarvis.jarvis_dependency_manager.history import (
    DependencyHistory,
    DependencyRecord,
)
from jarvis.jarvis_dependency_manager.reporter import (
    DependencyReporter,
    ReportFormat,
)

__version__ = "0.1.0"
__all__ = [
    "DependencyManager",
    "DependencyReporter",
    "DependencyHistory",
    "DependencyInfo",
    "UpdateSuggestion",
    "UpdateType",
    "DependencyRecord",
    "ReportFormat",
]
