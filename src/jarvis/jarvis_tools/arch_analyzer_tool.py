# -*- coding: utf-8 -*-
"""架构分析工具

将架构分析能力暴露给Agent使用，支持项目架构分析、复杂度分析、依赖分析、重复度分析。
"""

from typing import Any, Dict, Optional


class arch_analyzer_tool:
    """架构分析工具

    提供项目架构分析功能，包括：
    - 项目整体架构分析
    - 代码复杂度分析
    - 依赖关系分析
    - 代码重复度分析
    """

    name = "arch_analyzer_tool"
    description = """架构分析工具，提供项目架构分析、复杂度分析、依赖分析、重复度分析。

操作说明：
- analyze_project: 分析项目整体架构健康度
- analyze_complexity: 分析代码复杂度（圈复杂度、认知复杂度）
- analyze_dependency: 分析依赖关系（循环依赖、耦合度）
- analyze_duplication: 分析代码重复度"""

    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "analyze_project",
                    "analyze_complexity",
                    "analyze_dependency",
                    "analyze_duplication",
                ],
                "description": "操作类型",
            },
            "path": {
                "type": "string",
                "description": "要分析的项目或目录路径（默认当前目录）",
            },
            "include_details": {
                "type": "boolean",
                "description": "是否包含详细信息（默认False，仅返回摘要）",
            },
        },
        "required": ["operation"],
    }

    def __init__(self) -> None:
        self._analyzer: Optional[Any] = None

    def _get_analyzer(self) -> Any:
        """获取或创建分析器实例"""
        if self._analyzer is None:
            from jarvis.jarvis_arch_analyzer import ArchitectureAnalyzer

            self._analyzer = ArchitectureAnalyzer()
        return self._analyzer

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """执行架构分析操作"""
        operation = kwargs.get("operation")
        if operation == "analyze_project":
            return self._handle_analyze_project(kwargs)
        elif operation == "analyze_complexity":
            return self._handle_analyze_complexity(kwargs)
        elif operation == "analyze_dependency":
            return self._handle_analyze_dependency(kwargs)
        elif operation == "analyze_duplication":
            return self._handle_analyze_duplication(kwargs)
        return {"success": False, "error": f"未知操作: {operation}"}

    def _handle_analyze_project(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """处理项目整体分析"""
        path = kwargs.get("path", ".")
        include_details = kwargs.get("include_details", False)
        try:
            analyzer = self._get_analyzer()
            report = analyzer.analyze_project(path)

            result: Dict[str, Any] = {
                "success": True,
                "project_path": report.project_path,
                "overall_score": report.overall_score,
                "summary": report.summary,
                "timestamp": report.timestamp,
            }

            if include_details:
                result["results"] = [r.to_dict() for r in report.results]

            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_analyze_complexity(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """处理复杂度分析"""
        path = kwargs.get("path", ".")
        include_details = kwargs.get("include_details", False)
        try:
            from jarvis.jarvis_arch_analyzer.complexity import ComplexityAnalyzer

            analyzer = ComplexityAnalyzer(high_complexity_threshold=10)
            report = analyzer.analyze_directory(path)

            result: Dict[str, Any] = {
                "success": True,
                "total_functions": report.total_functions,
                "average_cyclomatic": report.average_cyclomatic,
                "average_cognitive": report.average_cognitive,
                "high_complexity_count": len(report.high_complexity_functions),
            }

            if include_details and report.high_complexity_functions:
                result["high_complexity_functions"] = [
                    {
                        "file": f.file_path,
                        "function": f.function_name,
                        "cyclomatic": f.cyclomatic,
                        "cognitive": f.cognitive,
                    }
                    for f in report.high_complexity_functions[:20]  # 限制数量
                ]

            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_analyze_dependency(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """处理依赖分析"""
        path = kwargs.get("path", ".")
        include_details = kwargs.get("include_details", False)
        try:
            from jarvis.jarvis_arch_analyzer.dependency import DependencyAnalyzer

            analyzer = DependencyAnalyzer()
            report = analyzer.analyze_directory(path)

            # 计算总依赖数
            total_deps = sum(
                len(node.dependencies) for node in report.dependency_graph.values()
            )

            result: Dict[str, Any] = {
                "success": True,
                "total_modules": report.total_modules,
                "total_dependencies": total_deps,
                "circular_dependency_count": len(report.circular_dependencies),
                "average_coupling": report.average_coupling,
            }

            if include_details:
                if report.circular_dependencies:
                    result["circular_dependencies"] = [
                        cycle.cycle_path for cycle in report.circular_dependencies[:10]
                    ]
                if report.coupling_metrics:
                    # 按不稳定性排序，取高耦合模块
                    high_coupling = sorted(
                        report.coupling_metrics,
                        key=lambda m: m.efferent_coupling,
                        reverse=True,
                    )[:10]
                    result["high_coupling_modules"] = [
                        {
                            "module": m.module_name,
                            "efferent_coupling": m.efferent_coupling,
                            "afferent_coupling": m.afferent_coupling,
                        }
                        for m in high_coupling
                    ]

            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_analyze_duplication(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """处理重复度分析"""
        path = kwargs.get("path", ".")
        include_details = kwargs.get("include_details", False)
        try:
            from jarvis.jarvis_arch_analyzer.duplication import DuplicationAnalyzer

            analyzer = DuplicationAnalyzer(min_similarity=0.85, min_lines=6)
            report = analyzer.analyze_directory(path)

            result: Dict[str, Any] = {
                "success": True,
                "total_functions": report.total_functions,
                "duplicated_functions": report.duplicated_functions,
                "duplication_pairs_count": len(report.duplication_pairs),
                "duplication_rate": report.duplication_rate,
                "total_duplicated_lines": report.total_duplicated_lines,
            }

            if include_details and report.duplication_pairs:
                result["duplicate_examples"] = [
                    {
                        "file1": pair.block1.file_path,
                        "file2": pair.block2.file_path,
                        "similarity": pair.similarity,
                        "type": pair.duplication_type,
                    }
                    for pair in report.duplication_pairs[:10]
                ]

            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
