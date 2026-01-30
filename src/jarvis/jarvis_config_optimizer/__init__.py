"""Jarvis Configuration Optimizer.

This module provides functionality to analyze and optimize project configurations,
including pyproject.toml and tool-specific configurations.

Example usage:
    >>> from jarvis.jarvis_config_optimizer import ConfigOptimizer
    >>> optimizer = ConfigOptimizer("pyproject.toml")
    >>> report = optimizer.analyze()
    >>> optimizer.print_report(report)
"""

from __future__ import annotations

from .analyzer import ConfigAnalyzer, ConfigIssue, ToolConfig
from .optimizer import (
    AnalysisHistory,
    ConfigOptimizer,
    OptimizationReport,
    OptimizationSuggestion,
)

__all__ = [
    "ConfigAnalyzer",
    "ConfigIssue",
    "ToolConfig",
    "AnalysisHistory",
    "ConfigOptimizer",
    "OptimizationReport",
    "OptimizationSuggestion",
]
