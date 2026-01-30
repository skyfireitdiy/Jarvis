"""Jarvis架构分析器模块。

该模块提供代码架构分析功能，包括：
- 代码复杂度分析（圈复杂度、认知复杂度）
- 依赖关系分析（循环依赖、耦合度）
- 代码重复度分析
- 架构健康度评估

示例：
    from jarvis.jarvis_arch_analyzer import ArchitectureAnalyzer

    analyzer = ArchitectureAnalyzer()
    report = analyzer.analyze_project("src/jarvis")
    print(report.summary)
"""

from jarvis.jarvis_arch_analyzer.analyzer import ArchitectureAnalyzer

__all__ = [
    "ArchitectureAnalyzer",
]

__version__ = "0.1.0"
