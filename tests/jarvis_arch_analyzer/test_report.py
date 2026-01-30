"""测试架构健康度报告生成模块。"""

from __future__ import annotations

import json

from jarvis.jarvis_arch_analyzer.analyzer import AnalysisResult
from jarvis.jarvis_arch_analyzer.report import (
    ArchitectureHealthReport,
    HealthDimension,
    HealthScoreCalculator,
    ImprovementSuggestion,
    Priority,
    ReportGenerator,
    RiskLevel,
)


class TestRiskLevel:
    """测试RiskLevel枚举。"""

    def test_from_score_healthy(self) -> None:
        """测试健康等级。"""
        assert RiskLevel.from_score(95) == RiskLevel.HEALTHY
        assert RiskLevel.from_score(90) == RiskLevel.HEALTHY

    def test_from_score_good(self) -> None:
        """测试良好等级。"""
        assert RiskLevel.from_score(85) == RiskLevel.GOOD
        assert RiskLevel.from_score(70) == RiskLevel.GOOD

    def test_from_score_warning(self) -> None:
        """测试警告等级。"""
        assert RiskLevel.from_score(60) == RiskLevel.WARNING
        assert RiskLevel.from_score(50) == RiskLevel.WARNING

    def test_from_score_danger(self) -> None:
        """测试危险等级。"""
        assert RiskLevel.from_score(30) == RiskLevel.DANGER
        assert RiskLevel.from_score(0) == RiskLevel.DANGER


class TestHealthDimension:
    """测试HealthDimension数据类。"""

    def test_weighted_score(self) -> None:
        """测试加权分数计算。"""
        dimension = HealthDimension(
            name="测试维度", score=80.0, weight=0.3, status="pass"
        )
        assert dimension.weighted_score == 24.0

    def test_zero_weight(self) -> None:
        """测试零权重。"""
        dimension = HealthDimension(
            name="测试维度", score=80.0, weight=0.0, status="pass"
        )
        assert dimension.weighted_score == 0.0


class TestImprovementSuggestion:
    """测试ImprovementSuggestion数据类。"""

    def test_to_dict(self) -> None:
        """测试转换为字典。"""
        suggestion = ImprovementSuggestion(
            priority=Priority.P0,
            category="测试类别",
            description="测试描述",
            impact="测试影响",
            effort="low",
        )
        result = suggestion.to_dict()
        assert result["priority"] == "P0"
        assert result["category"] == "测试类别"
        assert result["description"] == "测试描述"
        assert result["impact"] == "测试影响"
        assert result["effort"] == "low"


class TestHealthScoreCalculator:
    """测试健康度评分计算器。"""

    def test_calculate_empty_results(self) -> None:
        """测试空结果列表。"""
        calculator = HealthScoreCalculator()
        score, dimensions = calculator.calculate([])
        assert score == 0.0
        assert dimensions == []

    def test_calculate_single_result(self) -> None:
        """测试单个结果。"""
        calculator = HealthScoreCalculator()
        result = AnalysisResult(name="测试分析", status="pass", score=85.0, details={})
        score, dimensions = calculator.calculate([result])
        assert score == 85.0
        assert len(dimensions) == 1
        assert dimensions[0].score == 85.0

    def test_calculate_multiple_results(self) -> None:
        """测试多个结果。"""
        calculator = HealthScoreCalculator()
        results = [
            AnalysisResult(
                name="代码复杂度分析", status="pass", score=80.0, details={}
            ),
            AnalysisResult(
                name="依赖关系分析", status="warning", score=70.0, details={}
            ),
            AnalysisResult(
                name="代码重复度分析", status="pass", score=90.0, details={}
            ),
        ]
        score, dimensions = calculator.calculate(results)

        # 加权平均: (80*0.3 + 70*0.35 + 90*0.35) / (0.3+0.35+0.35) = 80.0
        expected_score = (80.0 * 0.3 + 70.0 * 0.35 + 90.0 * 0.35) / 1.0
        assert abs(score - expected_score) < 0.01
        assert len(dimensions) == 3

    def test_calculate_custom_weights(self) -> None:
        """测试自定义权重。"""
        calculator = HealthScoreCalculator()
        results = [
            AnalysisResult(
                name="代码复杂度分析", status="pass", score=80.0, details={}
            ),
        ]
        custom_weights = {"代码复杂度分析": 0.5}
        score, dimensions = calculator.calculate(results, custom_weights)
        assert score == 80.0
        assert dimensions[0].weight == 0.5

    def test_calculate_unknown_name(self) -> None:
        """测试未知的分析名称。"""
        calculator = HealthScoreCalculator()
        result = AnalysisResult(name="未知分析", status="pass", score=85.0, details={})
        score, dimensions = calculator.calculate([result])
        # 应该使用默认权重0.1
        assert dimensions[0].weight == 0.1


class TestReportGenerator:
    """测试报告生成器。"""

    def test_generate_basic_report(self) -> None:
        """测试生成基本报告。"""
        generator = ReportGenerator()
        results = [
            AnalysisResult(
                name="代码复杂度分析",
                status="pass",
                score=85.0,
                details={"total_functions": 100, "high_complexity_count": 5},
            ),
            AnalysisResult(
                name="依赖关系分析",
                status="pass",
                score=90.0,
                details={"circular_dependencies_count": 0, "average_coupling": 2.0},
            ),
            AnalysisResult(
                name="代码重复度分析",
                status="pass",
                score=95.0,
                details={"duplication_rate": 0.03, "duplicated_functions": 3},
            ),
        ]

        report = generator.generate("/test/project", results)

        assert report.project_path == "/test/project"
        assert report.overall_score > 0
        assert (
            report.risk_level == RiskLevel.HEALTHY
            or report.risk_level == RiskLevel.GOOD
        )
        assert len(report.dimensions) == 3
        assert len(report.suggestions) >= 0
        assert report.summary != ""
        assert report.timestamp != ""

    def test_generate_report_with_issues(self) -> None:
        """测试生成包含问题的报告。"""
        generator = ReportGenerator()
        results = [
            AnalysisResult(
                name="依赖关系分析",
                status="fail",
                score=40.0,
                details={
                    "circular_dependencies_count": 3,
                    "average_coupling": 5.0,
                },
            ),
            AnalysisResult(
                name="代码复杂度分析",
                status="warning",
                score=60.0,
                details={
                    "total_functions": 100,
                    "high_complexity_count": 15,
                    "average_cyclomatic": 8.0,
                },
            ),
            AnalysisResult(
                name="代码重复度分析",
                status="fail",
                score=30.0,
                details={
                    "duplication_rate": 0.20,
                    "duplicated_functions": 25,
                },
            ),
        ]

        report = generator.generate("/test/project", results)

        # 应该有P0建议
        p0_suggestions = [s for s in report.suggestions if s.priority == Priority.P0]
        assert len(p0_suggestions) > 0

        # 应该有P1建议
        p1_suggestions = [s for s in report.suggestions if s.priority == Priority.P1]
        assert len(p1_suggestions) > 0

        # 风险等级应该是warning或danger
        assert report.risk_level in [RiskLevel.WARNING, RiskLevel.DANGER]

    def test_generate_suggestions_for_circular_dependencies(self) -> None:
        """测试循环依赖建议生成。"""
        generator = ReportGenerator()
        result = AnalysisResult(
            name="依赖关系分析",
            status="fail",
            score=50.0,
            details={"circular_dependencies_count": 2, "average_coupling": 2.0},
        )

        suggestions = generator._generate_dependency_suggestions(result)
        assert len(suggestions) > 0
        assert suggestions[0].priority == Priority.P0
        assert "循环依赖" in suggestions[0].description

    def test_generate_suggestions_for_high_coupling(self) -> None:
        """测试高耦合度建议生成。"""
        generator = ReportGenerator()
        result = AnalysisResult(
            name="依赖关系分析",
            status="warning",
            score=70.0,
            details={"circular_dependencies_count": 0, "average_coupling": 4.5},
        )

        suggestions = generator._generate_dependency_suggestions(result)
        assert len(suggestions) > 0
        assert suggestions[0].priority == Priority.P1
        assert "耦合" in suggestions[0].category

    def test_generate_suggestions_for_high_complexity(self) -> None:
        """测试高复杂度建议生成。"""
        generator = ReportGenerator()
        result = AnalysisResult(
            name="代码复杂度分析",
            status="warning",
            score=70.0,
            details={
                "high_complexity_count": 10,
                "average_cyclomatic": 7.0,
            },
        )

        suggestions = generator._generate_complexity_suggestions(result)
        assert len(suggestions) > 0
        assert suggestions[0].priority == Priority.P1
        assert "复杂度" in suggestions[0].category

    def test_generate_suggestions_for_high_duplication(self) -> None:
        """测试高重复率建议生成。"""
        generator = ReportGenerator()
        result = AnalysisResult(
            name="代码重复度分析",
            status="fail",
            score=40.0,
            details={"duplication_rate": 0.18, "duplicated_functions": 20},
        )

        suggestions = generator._generate_duplication_suggestions(result)
        assert len(suggestions) > 0
        assert suggestions[0].priority == Priority.P0
        assert "重复" in suggestions[0].category

    def test_generate_suggestions_for_low_duplication(self) -> None:
        """测试低重复率建议生成。"""
        generator = ReportGenerator()
        result = AnalysisResult(
            name="代码重复度分析",
            status="pass",
            score=95.0,
            details={"duplication_rate": 0.03, "duplicated_functions": 2},
        )

        suggestions = generator._generate_duplication_suggestions(result)
        # 低重复率应该生成P2建议或不生成建议
        assert len(suggestions) <= 1
        if suggestions:
            assert suggestions[0].priority == Priority.P2


class TestArchitectureHealthReport:
    """测试ArchitectureHealthReport数据类。"""

    def test_to_dict(self) -> None:
        """测试转换为字典。"""
        report = ArchitectureHealthReport(
            project_path="/test",
            overall_score=85.0,
            risk_level=RiskLevel.GOOD,
            dimensions=[
                HealthDimension(name="测试", score=80.0, weight=0.3, status="pass")
            ],
            suggestions=[],
            summary="测试摘要",
            timestamp="2024-01-01",
        )

        result = report.to_dict()
        assert result["project_path"] == "/test"
        assert result["overall_score"] == 85.0
        assert result["risk_level"] == "good"
        assert len(result["dimensions"]) == 1
        assert result["summary"] == "测试摘要"

    def test_to_json(self) -> None:
        """测试转换为JSON。"""
        report = ArchitectureHealthReport(
            project_path="/test",
            overall_score=85.0,
            risk_level=RiskLevel.GOOD,
            dimensions=[],
            suggestions=[],
            summary="测试",
            timestamp="2024-01-01",
        )

        json_str = report.to_json()
        data = json.loads(json_str)
        assert data["overall_score"] == 85.0

    def test_to_markdown(self) -> None:
        """测试转换为Markdown。"""
        report = ArchitectureHealthReport(
            project_path="/test",
            overall_score=85.0,
            risk_level=RiskLevel.GOOD,
            dimensions=[
                HealthDimension(name="测试维度", score=80.0, weight=0.3, status="pass")
            ],
            suggestions=[
                ImprovementSuggestion(
                    priority=Priority.P0,
                    category="测试",
                    description="测试建议",
                    impact="测试影响",
                    effort="low",
                )
            ],
            summary="测试摘要",
            timestamp="2024-01-01",
        )

        md = report.to_markdown()
        assert "# 架构健康度报告" in md
        assert "85.0" in md
        assert "GOOD" in md
        assert "测试维度" in md
        assert "P0" in md

    def test_to_html(self) -> None:
        """测试转换为HTML。"""
        report = ArchitectureHealthReport(
            project_path="/test",
            overall_score=85.0,
            risk_level=RiskLevel.GOOD,
            dimensions=[
                HealthDimension(name="测试维度", score=80.0, weight=0.3, status="pass")
            ],
            suggestions=[],
            summary="测试摘要",
            timestamp="2024-01-01",
        )

        html = report.to_html()
        assert "<!DOCTYPE html>" in html
        assert "85.0" in html
        assert "good" in html
        assert "测试维度" in html
        assert "测试摘要" in html

    def test_empty_suggestions_markdown(self) -> None:
        """测试空建议列表的Markdown生成。"""
        report = ArchitectureHealthReport(
            project_path="/test",
            overall_score=95.0,
            risk_level=RiskLevel.HEALTHY,
            dimensions=[],
            suggestions=[],
            summary="完美",
            timestamp="2024-01-01",
        )

        md = report.to_markdown()
        assert "恭喜" in md

    def test_empty_suggestions_html(self) -> None:
        """测试空建议列表的HTML生成。"""
        report = ArchitectureHealthReport(
            project_path="/test",
            overall_score=95.0,
            risk_level=RiskLevel.HEALTHY,
            dimensions=[],
            suggestions=[],
            summary="完美",
            timestamp="2024-01-01",
        )

        html = report.to_html()
        assert "恭喜" in html
