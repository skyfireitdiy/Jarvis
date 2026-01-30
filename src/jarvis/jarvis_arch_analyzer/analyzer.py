"""架构分析器核心模块。

提供架构分析的统一接口和基础功能。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

# 为了类型注解，导入但不直接使用
if TYPE_CHECKING:
    from jarvis.jarvis_arch_analyzer.report import ArchitectureHealthReport


@dataclass
class AnalysisResult:
    """分析结果数据类。

    Attributes:
        name: 分析项名称
        status: 状态（pass/fail/warning）
        score: 评分（0-100）
        details: 详细信息
        suggestions: 改进建议
    """

    name: str
    status: str
    score: float
    details: dict[str, Any] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "name": self.name,
            "status": self.status,
            "score": self.score,
            "details": self.details,
            "suggestions": self.suggestions,
        }


@dataclass
class ArchitectureReport:
    """架构分析报告。

    Attributes:
        project_path: 项目路径
        overall_score: 总体评分（0-100）
        results: 各项分析结果
        summary: 摘要
        timestamp: 分析时间戳
    """

    project_path: str
    overall_score: float
    results: list[AnalysisResult] = field(default_factory=list)
    summary: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "project_path": self.project_path,
            "overall_score": self.overall_score,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary,
            "timestamp": self.timestamp,
        }

    def to_json(self, indent: int = 2) -> str:
        """转换为JSON字符串。"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class ArchitectureAnalyzer:
    """架构分析器主类。

    提供代码架构分析的统一接口，整合各种分析功能。

    示例：
        analyzer = ArchitectureAnalyzer()
        report = analyzer.analyze_project("src/jarvis")
        print(report.summary)

        # 使用健康度报告
        health_report = analyzer.analyze_project_health("src/jarvis")
        print(health_report.to_markdown())
    """

    def __init__(self, project_path: str | None = None) -> None:
        """初始化分析器。

        Args:
            project_path: 项目根路径
        """
        self.project_path = Path(project_path) if project_path else Path.cwd()
        self._results: list[AnalysisResult] = []

    def analyze_project(
        self,
        path: str | None = None,
        include_complexity: bool = True,
        include_dependency: bool = True,
        include_duplication: bool = True,
    ) -> ArchitectureReport:
        """分析项目架构。

        Args:
            path: 项目路径（可选，默认使用初始化时的路径）
            include_complexity: 是否包含复杂度分析
            include_dependency: 是否包含依赖分析
            include_duplication: 是否包含重复度分析

        Returns:
            架构分析报告
        """
        target_path = Path(path) if path else self.project_path

        self._results.clear()

        # 执行各项分析
        if include_complexity:
            complexity_result = self._analyze_complexity(target_path)
            self._results.append(complexity_result)

        if include_dependency:
            dependency_result = self._analyze_dependency(target_path)
            self._results.append(dependency_result)

        if include_duplication:
            duplication_result = self._analyze_duplication(target_path)
            self._results.append(duplication_result)

        # 计算总体评分
        overall_score = self._calculate_overall_score()

        # 生成摘要
        summary = self._generate_summary()

        return ArchitectureReport(
            project_path=str(target_path),
            overall_score=overall_score,
            results=self._results,
            summary=summary,
            timestamp=self._get_timestamp(),
        )

    def _analyze_complexity(self, path: Path) -> AnalysisResult:
        """分析代码复杂度。

        Args:
            path: 项目路径

        Returns:
            复杂度分析结果
        """
        from jarvis.jarvis_arch_analyzer.complexity import ComplexityAnalyzer

        analyzer = ComplexityAnalyzer(high_complexity_threshold=10)
        report = analyzer.analyze_directory(path)

        # 计算评分（基于高复杂度函数占比）
        if report.total_functions == 0:
            score = 100.0
            status = "pass"
        else:
            high_complexity_ratio = (
                len(report.high_complexity_functions) / report.total_functions
            )
            # 高复杂度函数占比越低，分数越高
            score = max(0, 100 - high_complexity_ratio * 100)

            if high_complexity_ratio == 0:
                status = "pass"
            elif high_complexity_ratio < 0.1:  # 少于10%
                status = "warning"
            else:
                status = "fail"

        # 生成建议
        suggestions = []
        if report.high_complexity_functions:
            suggestions.append(
                f"发现 {len(report.high_complexity_functions)} 个高复杂度函数（圈复杂度>10）"
            )
            suggestions.append("建议重构高复杂度函数，拆分为更小的函数")
            suggestions.append(f"平均圈复杂度: {report.average_cyclomatic:.1f}")
            suggestions.append(f"平均认知复杂度: {report.average_cognitive:.1f}")
        else:
            suggestions.append("代码复杂度控制良好")

        # 高复杂度函数详情
        high_complexity_details = [
            {
                "file": f.file_path,
                "function": f.function_name,
                "line": f.line_no,
                "cyclomatic": f.cyclomatic,
                "cognitive": f.cognitive,
            }
            for f in report.high_complexity_functions[:10]  # 只显示前10个
        ]

        return AnalysisResult(
            name="代码复杂度分析",
            status=status,
            score=score,
            details={
                "total_functions": report.total_functions,
                "high_complexity_count": len(report.high_complexity_functions),
                "average_cyclomatic": report.average_cyclomatic,
                "average_cognitive": report.average_cognitive,
                "max_cyclomatic": report.max_cyclomatic,
                "max_cognitive": report.max_cognitive,
                "high_complexity_functions": high_complexity_details,
            },
            suggestions=suggestions,
        )

    def _analyze_dependency(self, path: Path) -> AnalysisResult:
        """分析依赖关系。

        Args:
            path: 项目路径

        Returns:
            依赖分析结果
        """
        from jarvis.jarvis_arch_analyzer.dependency import DependencyAnalyzer

        analyzer = DependencyAnalyzer()
        report = analyzer.analyze_directory(path)

        # 计算评分（基于循环依赖和耦合度）
        score = 100.0
        status = "pass"

        # 循环依赖扣分
        circular_penalty = len(report.circular_dependencies) * 10
        score = max(0, score - circular_penalty)

        # 高耦合度扣分（平均耦合度>3）
        if report.average_coupling > 3:
            coupling_penalty = (report.average_coupling - 3) * 5
            score = max(0, score - coupling_penalty)

        # 确定状态
        if len(report.circular_dependencies) > 0:
            status = "fail"
        elif report.average_coupling > 3:
            status = "warning"

        # 生成建议
        suggestions = []
        if report.circular_dependencies:
            suggestions.append(f"发现 {len(report.circular_dependencies)} 个循环依赖")
            suggestions.append("建议重构代码消除循环依赖")
            for cycle in report.circular_dependencies[:3]:
                suggestions.append(f"  - {cycle.to_dict()['cycle_str']}")
        else:
            suggestions.append("未发现循环依赖")

        if report.average_coupling > 3:
            suggestions.append(f"平均耦合度较高: {report.average_coupling:.1f}")
            suggestions.append("建议降低模块间耦合度")
        elif report.average_coupling > 0:
            suggestions.append(f"平均耦合度: {report.average_coupling:.1f} (正常)")
        else:
            suggestions.append("模块间耦合度良好")

        suggestions.append(f"最大依赖深度: {report.max_depth}")

        # 高耦合模块详情
        high_coupling_modules = [
            {"module": m.module_name, "coupling": m.efferent_coupling}
            for m in report.coupling_metrics
            if m.efferent_coupling > 5
        ][:5]

        return AnalysisResult(
            name="依赖关系分析",
            status=status,
            score=score,
            details={
                "total_modules": report.total_modules,
                "circular_dependencies_count": len(report.circular_dependencies),
                "average_coupling": report.average_coupling,
                "max_depth": report.max_depth,
                "high_coupling_modules": high_coupling_modules,
            },
            suggestions=suggestions,
        )

    def _analyze_duplication(self, path: Path) -> AnalysisResult:
        """分析代码重复度。

        Args:
            path: 项目路径

        Returns:
            重复度分析结果
        """
        from jarvis.jarvis_arch_analyzer.duplication import DuplicationAnalyzer

        analyzer = DuplicationAnalyzer(min_similarity=0.85, min_lines=5)
        report = analyzer.analyze_directory(path)

        # 计算评分（基于重复率）
        if report.total_functions == 0:
            score = 100.0
            status = "pass"
        else:
            # 重复率越低，分数越高
            # 重复率 < 5%: pass, 5-15%: warning, > 15%: fail
            score = max(0, 100 - report.duplication_rate * 100 * 3)

            if report.duplication_rate < 0.05:
                status = "pass"
            elif report.duplication_rate < 0.15:
                status = "warning"
            else:
                status = "fail"

        # 生成建议
        suggestions = []
        if report.duplication_pairs:
            suggestions.append(f"发现 {len(report.duplication_pairs)} 对重复/相似函数")
            suggestions.append(
                f"重复率: {report.duplication_rate:.1%} ({report.duplicated_functions}/{report.total_functions})"
            )
            suggestions.append(f"总重复代码行数: {report.total_duplicated_lines} 行")
            if report.average_similarity > 0:
                suggestions.append(f"平均相似度: {report.average_similarity:.1%}")
            suggestions.append("建议提取公共函数消除重复代码")
        else:
            suggestions.append("未发现明显的代码重复")

        # 重复对详情（只显示前10个）
        duplication_details = [
            {
                "file1": pair.block1.file_path,
                "function1": pair.block1.function_name,
                "line1": pair.block1.start_line,
                "file2": pair.block2.file_path,
                "function2": pair.block2.function_name,
                "line2": pair.block2.start_line,
                "similarity": f"{pair.similarity:.1%}",
                "type": pair.duplication_type,
            }
            for pair in report.duplication_pairs[:10]
        ]

        return AnalysisResult(
            name="代码重复度分析",
            status=status,
            score=score,
            details={
                "total_functions": report.total_functions,
                "duplicated_functions": report.duplicated_functions,
                "duplication_rate": report.duplication_rate,
                "duplication_pairs_count": len(report.duplication_pairs),
                "total_duplicated_lines": report.total_duplicated_lines,
                "average_similarity": report.average_similarity,
                "duplication_pairs": duplication_details,
            },
            suggestions=suggestions,
        )

    def _calculate_overall_score(self) -> float:
        """计算总体评分。

        Returns:
            总体评分（0-100）
        """
        if not self._results:
            return 0.0

        # 计算所有结果的平均分
        total_score = sum(result.score for result in self._results)
        return total_score / len(self._results)

    def _generate_summary(self) -> str:
        """生成分析摘要。

        Returns:
            摘要文本
        """
        if not self._results:
            return "无分析结果"

        lines = ["# 架构分析报告\n"]

        for result in self._results:
            lines.append(f"## {result.name}")
            lines.append(f"状态: {result.status}")
            lines.append(f"评分: {result.score:.1f}/100")
            if result.suggestions:
                lines.append("建议:")
                for suggestion in result.suggestions:
                    lines.append(f"  - {suggestion}")
            lines.append("")

        return "\n".join(lines)

    def _get_timestamp(self) -> str:
        """获取当前时间戳。

        Returns:
            ISO格式时间戳
        """
        from datetime import datetime

        return datetime.now().isoformat()

    def analyze_project_health(
        self,
        path: str | None = None,
        include_complexity: bool = True,
        include_dependency: bool = True,
        include_duplication: bool = True,
        weights: dict[str, float] | None = None,
    ) -> ArchitectureHealthReport:
        """分析项目架构健康度。

        使用新的健康度报告生成器，提供更全面的分析和建议。

        Args:
            path: 项目路径（可选，默认使用初始化时的路径）
            include_complexity: 是否包含复杂度分析
            include_dependency: 是否包含依赖分析
            include_duplication: 是否包含重复度分析
            weights: 自定义权重配置（可选）

        Returns:
            架构健康度报告

        示例：
            analyzer = ArchitectureAnalyzer()
            health_report = analyzer.analyze_project_health("src/jarvis")
            print(health_report.to_markdown())
            # 或保存为HTML
            with open("report.html", "w") as f:
                f.write(health_report.to_html())
        """
        from jarvis.jarvis_arch_analyzer.report import ReportGenerator

        target_path = Path(path) if path else self.project_path

        self._results.clear()

        # 执行各项分析
        if include_complexity:
            complexity_result = self._analyze_complexity(target_path)
            self._results.append(complexity_result)

        if include_dependency:
            dependency_result = self._analyze_dependency(target_path)
            self._results.append(dependency_result)

        if include_duplication:
            duplication_result = self._analyze_duplication(target_path)
            self._results.append(duplication_result)

        # 使用新的报告生成器
        generator = ReportGenerator()
        health_report = generator.generate(
            project_path=str(target_path),
            results=self._results,
            weights=weights,
        )

        return health_report
