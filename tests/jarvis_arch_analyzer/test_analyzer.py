"""测试架构分析器核心功能。"""

from jarvis.jarvis_arch_analyzer import ArchitectureAnalyzer


class TestArchitectureAnalyzer:
    """测试ArchitectureAnalyzer类。"""

    def test_init(self) -> None:
        """测试初始化。"""
        analyzer = ArchitectureAnalyzer()
        assert analyzer.project_path is not None

    def test_init_with_path(self, tmp_path) -> None:
        """测试使用指定路径初始化。"""
        analyzer = ArchitectureAnalyzer(str(tmp_path))
        assert str(analyzer.project_path) == str(tmp_path)

    def test_analyze_project_returns_report(self) -> None:
        """测试分析项目返回报告。"""
        analyzer = ArchitectureAnalyzer()
        report = analyzer.analyze_project("tests/jarvis_arch_analyzer")

        assert report.project_path is not None
        # 复杂度100分 + 依赖分析100分 + 重复度0分 = 平均66.67分
        assert report.overall_score >= 60.0  # 已实现依赖分析
        assert len(report.results) == 3  # 三项分析
        assert report.summary != ""
        assert report.timestamp != ""

    def test_analyze_project_with_filters(self) -> None:
        """测试选择性分析。"""
        analyzer = ArchitectureAnalyzer()

        # 只分析复杂度
        report = analyzer.analyze_project(
            "tests/jarvis_arch_analyzer",
            include_complexity=True,
            include_dependency=False,
            include_duplication=False,
        )
        assert len(report.results) == 1
        assert report.results[0].name == "代码复杂度分析"

        # 只分析依赖
        report = analyzer.analyze_project(
            "tests/jarvis_arch_analyzer",
            include_complexity=False,
            include_dependency=True,
            include_duplication=False,
        )
        assert len(report.results) == 1
        assert report.results[0].name == "依赖关系分析"

    def test_report_to_dict(self) -> None:
        """测试报告转换为字典。"""
        analyzer = ArchitectureAnalyzer()
        report = analyzer.analyze_project("tests/jarvis_arch_analyzer")

        report_dict = report.to_dict()
        assert "project_path" in report_dict
        assert "overall_score" in report_dict
        assert "results" in report_dict
        assert "summary" in report_dict
        assert "timestamp" in report_dict

    def test_report_to_json(self) -> None:
        """测试报告转换为JSON。"""
        analyzer = ArchitectureAnalyzer()
        report = analyzer.analyze_project("tests/jarvis_arch_analyzer")

        json_str = report.to_json()
        assert "project_path" in json_str
        assert "overall_score" in json_str

    def test_analysis_result_to_dict(self) -> None:
        """测试分析结果转换为字典。"""
        from jarvis.jarvis_arch_analyzer.analyzer import AnalysisResult

        result = AnalysisResult(
            name="测试",
            status="pass",
            score=100.0,
            details={"key": "value"},
            suggestions=["建议1", "建议2"],
        )

        result_dict = result.to_dict()
        assert result_dict["name"] == "测试"
        assert result_dict["status"] == "pass"
        assert result_dict["score"] == 100.0
        assert result_dict["details"] == {"key": "value"}
        assert result_dict["suggestions"] == ["建议1", "建议2"]
