"""Tests for jarvis_config_optimizer module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from jarvis.jarvis_config_optimizer import (
    AnalysisHistory,
    ConfigAnalyzer,
    ConfigIssue,
    ConfigOptimizer,
    OptimizationReport,
    OptimizationSuggestion,
    ToolConfig,
)


@pytest.fixture
def sample_config():
    """Create a sample pyproject.toml configuration."""
    return """
[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F"]

[tool.mypy]
strict = false
warn_return_any = false

[tool.pytest]
testpaths = ["tests"]

[tool.bandit]
skips = ["B101", "B102"]
"""


@pytest.fixture
def minimal_config():
    """Create a minimal pyproject.toml configuration."""
    return """
[tool.ruff]

[tool.mypy]

[tool.pytest]

[tool.bandit]
"""


@pytest.fixture
def optimized_config():
    """Create an optimized pyproject.toml configuration."""
    return """
[tool.ruff]
line-length = 88
target-version = "py312"
select = ["E", "F"]

[tool.mypy]
strict = true
warn_return_any = true

[tool.pytest]
testpaths = ["tests"]
pythonpath = ["."]

[tool.bandit]
skips = []
"""


@pytest.fixture
def temp_config_file(sample_config):
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(sample_config)
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    if temp_path.exists():
        temp_path.unlink()

    # Cleanup history file
    history_dir = temp_path.parent / ".jarvis"
    if history_dir.exists():
        for file in history_dir.glob("*config_optimizer_history.json"):
            file.unlink()
        if history_dir.is_dir() and not any(history_dir.iterdir()):
            history_dir.rmdir()


class TestConfigAnalyzer:
    """Test cases for ConfigAnalyzer class."""

    def test_init_nonexistent_file(self):
        """Test initialization with nonexistent file."""
        with pytest.raises(FileNotFoundError):
            ConfigAnalyzer("nonexistent.toml")

    def test_parse_ruff_config(self, temp_config_file):
        """Test parsing ruff configuration."""
        analyzer = ConfigAnalyzer(temp_config_file)
        tool_configs = analyzer.parse()

        assert "ruff" in tool_configs
        assert tool_configs["ruff"].tool_name == "ruff"
        assert tool_configs["ruff"].config["line-length"] == 100
        assert tool_configs["ruff"].config["target-version"] == "py311"

    def test_parse_mypy_config(self, temp_config_file):
        """Test parsing mypy configuration."""
        analyzer = ConfigAnalyzer(temp_config_file)
        tool_configs = analyzer.parse()

        assert "mypy" in tool_configs
        assert tool_configs["mypy"].tool_name == "mypy"
        assert tool_configs["mypy"].config["strict"] is False

    def test_parse_pytest_config(self, temp_config_file):
        """Test parsing pytest configuration."""
        analyzer = ConfigAnalyzer(temp_config_file)
        tool_configs = analyzer.parse()

        assert "pytest" in tool_configs
        assert tool_configs["pytest"].tool_name == "pytest"
        assert tool_configs["pytest"].config["testpaths"] == ["tests"]

    def test_parse_bandit_config(self, temp_config_file):
        """Test parsing bandit configuration."""
        analyzer = ConfigAnalyzer(temp_config_file)
        tool_configs = analyzer.parse()

        assert "bandit" in tool_configs
        assert tool_configs["bandit"].tool_name == "bandit"
        assert "B101" in tool_configs["bandit"].config["skips"]

    def test_analyze_ruff_line_length(self, temp_config_file):
        """Test analysis of ruff line-length configuration."""
        analyzer = ConfigAnalyzer(temp_config_file)
        tool_configs = analyzer.parse()
        ruff_config = tool_configs["ruff"]

        # Should find issue with line-length not being 88
        line_length_issues = [
            i for i in ruff_config.issues if "line-length" in i.location
        ]
        assert len(line_length_issues) > 0
        assert line_length_issues[0].current_value == 100
        assert line_length_issues[0].recommended_value == 88

    def test_analyze_ruff_target_version(self, temp_config_file):
        """Test analysis of ruff target-version configuration."""
        analyzer = ConfigAnalyzer(temp_config_file)
        tool_configs = analyzer.parse()
        ruff_config = tool_configs["ruff"]

        # Should find issue with target-version not being py312
        version_issues = [
            i for i in ruff_config.issues if "target-version" in i.location
        ]
        assert len(version_issues) > 0
        assert version_issues[0].current_value == "py311"
        assert version_issues[0].recommended_value == "py312"

    def test_analyze_mypy_strict(self, temp_config_file):
        """Test analysis of mypy strict configuration."""
        analyzer = ConfigAnalyzer(temp_config_file)
        tool_configs = analyzer.parse()
        mypy_config = tool_configs["mypy"]

        # Should find issue with strict being false
        strict_issues = [i for i in mypy_config.issues if "strict" in i.location]
        assert len(strict_issues) > 0
        assert strict_issues[0].current_value is False
        assert strict_issues[0].recommended_value is True

    def test_analyze_bandit_skips(self, temp_config_file):
        """Test analysis of bandit skips configuration."""
        analyzer = ConfigAnalyzer(temp_config_file)
        tool_configs = analyzer.parse()
        bandit_config = tool_configs["bandit"]

        # Should find issue with skipping critical test B101
        skip_issues = [i for i in bandit_config.issues if i.issue_type == "conflict"]
        assert len(skip_issues) > 0

    def test_get_all_issues(self, temp_config_file):
        """Test getting all issues."""
        analyzer = ConfigAnalyzer(temp_config_file)
        analyzer.parse()
        issues = analyzer.get_issues()

        assert len(issues) > 0
        assert all(isinstance(issue, ConfigIssue) for issue in issues)

    def test_get_issues_by_category(self, temp_config_file):
        """Test filtering issues by category."""
        analyzer = ConfigAnalyzer(temp_config_file)
        analyzer.parse()

        security_issues = analyzer.get_issues_by_category("security")
        maintainability_issues = analyzer.get_issues_by_category("maintainability")

        assert all(issue.category == "security" for issue in security_issues)
        assert all(
            issue.category == "maintainability" for issue in maintainability_issues
        )

    def test_get_issues_by_severity(self, temp_config_file):
        """Test filtering issues by severity."""
        analyzer = ConfigAnalyzer(temp_config_file)
        analyzer.parse()

        high_issues = analyzer.get_issues_by_severity("high")
        medium_issues = analyzer.get_issues_by_severity("medium")

        assert all(issue.severity == "high" for issue in high_issues)
        assert all(issue.severity == "medium" for issue in medium_issues)

    def test_optimized_config_no_issues(self, optimized_config):
        """Test that optimized config has minimal issues."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(optimized_config)
            temp_path = Path(f.name)

        try:
            analyzer = ConfigAnalyzer(temp_path)
            analyzer.parse()
            issues = analyzer.get_issues()
            # Only potential issues might be missing testpaths in pytest
            # but we have pythonpath now
            maintainability_issues = [
                i for i in issues if i.category == "maintainability"
            ]
            assert len(maintainability_issues) == 0
        finally:
            temp_path.unlink()


class TestConfigOptimizer:
    """Test cases for ConfigOptimizer class."""

    def test_init(self, temp_config_file):
        """Test optimizer initialization."""
        optimizer = ConfigOptimizer(temp_config_file)
        assert optimizer.config_path == temp_config_file
        assert optimizer.analyzer is not None

    def test_analyze(self, temp_config_file):
        """Test configuration analysis."""
        optimizer = ConfigOptimizer(temp_config_file)
        report = optimizer.analyze()

        assert isinstance(report, OptimizationReport)
        assert report.total_issues > 0
        assert len(report.tool_configs) > 0
        assert len(report.suggestions) > 0

    def test_generate_suggestions(self, temp_config_file):
        """Test optimization suggestion generation."""
        optimizer = ConfigOptimizer(temp_config_file)
        report = optimizer.analyze()

        assert all(
            isinstance(suggestion, OptimizationSuggestion)
            for suggestion in report.suggestions
        )

        # Check that suggestions are sorted by severity
        for i in range(len(report.suggestions) - 1):
            severity_order = ["high", "medium", "low"]
            current_index = severity_order.index(report.suggestions[i].issue.severity)
            next_index = severity_order.index(report.suggestions[i + 1].issue.severity)
            assert current_index >= next_index

    def test_issues_by_severity(self, temp_config_file):
        """Test issue counting by severity."""
        optimizer = ConfigOptimizer(temp_config_file)
        report = optimizer.analyze()

        assert "high" in report.issues_by_severity
        assert "medium" in report.issues_by_severity
        assert "low" in report.issues_by_severity
        assert report.total_issues == sum(report.issues_by_severity.values())

    def test_issues_by_category(self, temp_config_file):
        """Test issue counting by category."""
        optimizer = ConfigOptimizer(temp_config_file)
        report = optimizer.analyze()

        assert "security" in report.issues_by_category
        assert "performance" in report.issues_by_category
        assert "maintainability" in report.issues_by_category

    def test_summary_generation(self, temp_config_file):
        """Test summary generation."""
        optimizer = ConfigOptimizer(temp_config_file)
        report = optimizer.analyze()

        assert report.summary is not None
        assert len(report.summary) > 0

    def test_print_report(self, temp_config_file, capsys):
        """Test report printing."""
        optimizer = ConfigOptimizer(temp_config_file)
        report = optimizer.analyze()

        optimizer.print_report(report)
        captured = capsys.readouterr()

        assert "配置优化报告" in captured.out
        assert "问题总数" in captured.out
        assert "优化建议" in captured.out

    def test_history_management(self, temp_config_file):
        """Test analysis history management."""
        optimizer = ConfigOptimizer(temp_config_file)

        # First analysis
        report1 = optimizer.analyze()
        history = optimizer.get_history()

        assert len(history) > 0
        assert history[0].total_issues == report1.total_issues

        # Second analysis
        report2 = optimizer.analyze()
        history2 = optimizer.get_history()

        assert len(history2) == 2
        assert history2[0].total_issues == report2.total_issues

    def test_history_limit(self, temp_config_file):
        """Test history limit (max 50 records)."""
        optimizer = ConfigOptimizer(temp_config_file)

        # Run 60 analyses to test limit
        for _ in range(60):
            optimizer.analyze()

        history = optimizer.get_history(limit=100)
        assert len(history) == 50

    def test_history_persistence(self, temp_config_file):
        """Test that history persists across optimizer instances."""
        # First optimizer
        optimizer1 = ConfigOptimizer(temp_config_file)
        optimizer1.analyze()
        history1 = optimizer1.get_history()

        # Second optimizer (should read same history)
        optimizer2 = ConfigOptimizer(temp_config_file)
        history2 = optimizer2.get_history()

        assert len(history2) == len(history1)  # type: ignore[arg-type]

    def test_issues_fixed_calculation(self, temp_config_file):
        """Test calculation of fixed issues."""
        optimizer = ConfigOptimizer(temp_config_file)

        # First analysis with problematic config
        report1 = optimizer.analyze()
        initial_issues = report1.total_issues
        assert initial_issues > 0

        history = optimizer.get_history()
        assert history[0].issues_fixed == 0

        # Create a fully optimized config with minimal issues
        with open(temp_config_file, "w") as f:
            f.write("""
[tool.ruff]
line-length = 88
target-version = "py312"
select = ["E", "F", "W", "I"]

[tool.mypy]
strict = true
warn_return_any = true

[tool.pytest]
testpaths = ["tests"]
pythonpath = ["."]

[tool.bandit]
""")

        # Second analysis with fewer issues
        optimizer = ConfigOptimizer(temp_config_file)  # Re-create to reload config
        report2 = optimizer.analyze()
        final_issues = report2.total_issues

        history = optimizer.get_history()
        assert history[0].issues_fixed == initial_issues - final_issues
        assert history[0].issues_fixed > 0


class TestDataStructures:
    """Test cases for data structures."""

    def test_config_issue_creation(self):
        """Test ConfigIssue dataclass."""
        issue = ConfigIssue(
            issue_type="deprecated",
            severity="low",
            location="test.location",
            current_value="old",
            recommended_value="new",
            reason="test reason",
            category="maintainability",
        )

        assert issue.issue_type == "deprecated"
        assert issue.severity == "low"
        assert issue.location == "test.location"

    def test_tool_config_creation(self):
        """Test ToolConfig dataclass."""
        config = ToolConfig(tool_name="test", config={"key": "value"})

        assert config.tool_name == "test"
        assert config.config == {"key": "value"}
        assert config.issues == []

    def test_optimization_suggestion_creation(self):
        """Test OptimizationSuggestion dataclass."""
        issue = ConfigIssue(
            issue_type="deprecated",
            severity="low",
            location="test.location",
            current_value="old",
            recommended_value="new",
            reason="test reason",
            category="maintainability",
        )
        suggestion = OptimizationSuggestion(
            issue=issue, action="test action", impact="test impact", effort="low"
        )

        assert suggestion.issue == issue
        assert suggestion.action == "test action"
        assert suggestion.impact == "test impact"
        assert suggestion.effort == "low"

    def test_analysis_history_creation(self):
        """Test AnalysisHistory dataclass."""
        history = AnalysisHistory(
            timestamp=None,
            config_path="test.toml",
            total_issues=5,
            issues_fixed=2,
            report={"test": "data"},
        )

        assert history.config_path == "test.toml"
        assert history.total_issues == 5
        assert history.issues_fixed == 2
