"""Configuration optimizer for jarvis_config_optimizer.

This module provides functionality to generate optimization suggestions
based on configuration analysis results and best practices.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from .analyzer import ConfigAnalyzer, ConfigIssue, ToolConfig


@dataclass
class OptimizationSuggestion:
    """Represents an optimization suggestion.

    Attributes:
        issue: The configuration issue this suggestion addresses.
        action: Recommended action to take.
        impact: Expected impact of the optimization.
        effort: Effort required to implement.
    """

    issue: ConfigIssue
    action: str
    impact: str
    effort: Literal["low", "medium", "high"]


@dataclass
class OptimizationReport:
    """Represents a complete optimization report.

    Attributes:
        timestamp: When the report was generated.
        tool_configs: All tool configurations analyzed.
        total_issues: Total number of issues found.
        issues_by_severity: Issues grouped by severity.
        issues_by_category: Issues grouped by category.
        suggestions: List of optimization suggestions.
        summary: Summary of the analysis.
    """

    timestamp: datetime
    tool_configs: dict[str, ToolConfig]
    total_issues: int
    issues_by_severity: dict[str, int]
    issues_by_category: dict[str, int]
    suggestions: list[OptimizationSuggestion]
    summary: str


@dataclass
class AnalysisHistory:
    """Represents a historical analysis record.

    Attributes:
        timestamp: When the analysis was performed.
        config_path: Path to the configuration file.
        total_issues: Number of issues found.
        issues_fixed: Number of issues fixed since last analysis.
        report: Full optimization report data.
    """

    timestamp: datetime
    config_path: str
    total_issues: int
    issues_fixed: int
    report: dict[str, Any]


class ConfigOptimizer:
    """Optimizer for project configurations.

    This class uses ConfigAnalyzer to identify issues and generates
    optimization suggestions based on best practices.
    """

    def __init__(self, config_path: str | Path = "pyproject.toml") -> None:
        """Initialize the configuration optimizer.

        Args:
            config_path: Path to the pyproject.toml file.
        """
        self.config_path = Path(config_path)
        self.analyzer = ConfigAnalyzer(config_path)
        self.history_file = (
            self.config_path.parent / ".jarvis" / "config_optimizer_history.json"
        )
        self._ensure_history_dir()

    def _ensure_history_dir(self) -> None:
        """Ensure the history directory exists."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

    def analyze(self) -> OptimizationReport:
        """Analyze configuration and generate optimization report.

        Returns:
            OptimizationReport containing analysis results.
        """
        # Parse and analyze configuration
        tool_configs = self.analyzer.parse()
        issues = self.analyzer.get_issues()

        # Generate suggestions
        suggestions = self._generate_suggestions(issues)

        # Build report
        report = OptimizationReport(
            timestamp=datetime.now(),
            tool_configs=tool_configs,
            total_issues=len(issues),
            issues_by_severity=self._count_by_severity(issues),
            issues_by_category=self._count_by_category(issues),
            suggestions=suggestions,
            summary=self._generate_summary(issues),
        )

        # Save to history
        self._save_to_history(report)

        return report

    def _generate_suggestions(
        self, issues: list[ConfigIssue]
    ) -> list[OptimizationSuggestion]:
        """Generate optimization suggestions from issues.

        Args:
            issues: List of configuration issues.

        Returns:
            List of optimization suggestions.
        """
        suggestions: list[OptimizationSuggestion] = []

        for issue in issues:
            action, impact, effort = self._get_suggestion_details(issue)
            suggestions.append(
                OptimizationSuggestion(
                    issue=issue,
                    action=action,
                    impact=impact,
                    effort=effort,
                )
            )

        # Sort by severity (high first)
        suggestions.sort(
            key=lambda s: ("high", "medium", "low").index(s.issue.severity),
            reverse=True,
        )

        return suggestions

    def _get_suggestion_details(
        self, issue: ConfigIssue
    ) -> tuple[str, str, Literal["low", "medium", "high"]]:
        """Get suggestion details for an issue.

        Args:
            issue: Configuration issue.

        Returns:
            Tuple of (action, impact, effort).
        """
        if issue.issue_type == "deprecated":
            return (
                f"Update '{issue.location}' from '{issue.current_value}' to '{issue.recommended_value}'",
                "Improved consistency with best practices",
                "low",
            )
        elif issue.issue_type == "conflict":
            return (
                f"Resolve conflict in '{issue.location}': {issue.reason}",
                "Prevents potential security issues",
                "medium",
            )
        else:  # missing
            return (
                f"Add '{issue.location}' with recommended value '{issue.recommended_value}'",
                f"Improves {issue.category}",
                "low",
            )

    def _count_by_severity(self, issues: list[ConfigIssue]) -> dict[str, int]:
        """Count issues by severity.

        Args:
            issues: List of configuration issues.

        Returns:
            Dictionary mapping severity to count.
        """
        counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        for issue in issues:
            counts[issue.severity] += 1
        return counts

    def _count_by_category(self, issues: list[ConfigIssue]) -> dict[str, int]:
        """Count issues by category.

        Args:
            issues: List of configuration issues.

        Returns:
            Dictionary mapping category to count.
        """
        counts: dict[str, int] = {"security": 0, "performance": 0, "maintainability": 0}
        for issue in issues:
            counts[issue.category] += 1
        return counts

    def _generate_summary(self, issues: list[ConfigIssue]) -> str:
        """Generate a summary of the analysis.

        Args:
            issues: List of configuration issues.

        Returns:
            Summary string.
        """
        if not issues:
            return "No configuration issues found. Configuration is optimal."

        high_count = sum(1 for i in issues if i.severity == "high")
        medium_count = sum(1 for i in issues if i.severity == "medium")
        low_count = sum(1 for i in issues if i.severity == "low")

        summary_parts = [f"Found {len(issues)} configuration issues:"]
        if high_count > 0:
            summary_parts.append(f"  - {high_count} high severity")
        if medium_count > 0:
            summary_parts.append(f"  - {medium_count} medium severity")
        if low_count > 0:
            summary_parts.append(f"  - {low_count} low severity")

        return "\n".join(summary_parts)

    def _save_to_history(self, report: OptimizationReport) -> None:
        """Save analysis to history file.

        Args:
            report: Optimization report to save.
        """
        history = self._load_history()

        # Create history record
        record = AnalysisHistory(
            timestamp=report.timestamp,
            config_path=str(self.config_path),
            total_issues=report.total_issues,
            issues_fixed=self._calculate_issues_fixed(history, report.total_issues),
            report=self._report_to_dict(report),
        )

        # Append to history (keep last 50 records)
        history.append(record)
        if len(history) > 50:
            history = history[-50:]

        # Save to file
        with open(self.history_file, "w") as f:
            json.dump(
                [self._history_to_dict(h) for h in history], f, indent=2, default=str
            )

    def _load_history(self) -> list[AnalysisHistory]:
        """Load analysis history from file.

        Returns:
            List of historical analysis records.
        """
        if not self.history_file.exists():
            return []

        try:
            with open(self.history_file, "r") as f:
                data = json.load(f)
                return [self._dict_to_history(d) for d in data]
        except (json.JSONDecodeError, KeyError):
            return []

    def _calculate_issues_fixed(
        self, history: list[AnalysisHistory], current_total: int
    ) -> int:
        """Calculate number of issues fixed since last analysis.

        Args:
            history: Historical analysis records.
            current_total: Current total issues.

        Returns:
            Number of issues fixed.
        """
        if not history:
            return 0
        last_total = history[-1].total_issues
        return max(0, last_total - current_total)

    def _report_to_dict(self, report: OptimizationReport) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization.

        Args:
            report: Optimization report.

        Returns:
            Dictionary representation.
        """
        return {
            "timestamp": report.timestamp.isoformat(),
            "total_issues": report.total_issues,
            "issues_by_severity": report.issues_by_severity,
            "issues_by_category": report.issues_by_category,
            "summary": report.summary,
            "tool_names": list(report.tool_configs.keys()),
        }

    def _history_to_dict(self, history: AnalysisHistory) -> dict[str, Any]:
        """Convert history record to dictionary.

        Args:
            history: Analysis history record.

        Returns:
            Dictionary representation.
        """
        return {
            "timestamp": history.timestamp.isoformat(),
            "config_path": history.config_path,
            "total_issues": history.total_issues,
            "issues_fixed": history.issues_fixed,
            "report": history.report,
        }

    def _dict_to_history(self, data: dict[str, Any]) -> AnalysisHistory:
        """Convert dictionary to history record.

        Args:
            data: Dictionary representation.

        Returns:
            Analysis history record.
        """
        return AnalysisHistory(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            config_path=data["config_path"],
            total_issues=data["total_issues"],
            issues_fixed=data["issues_fixed"],
            report=data["report"],
        )

    def get_history(self, limit: int = 10) -> list[AnalysisHistory]:
        """Get analysis history.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of historical analysis records (most recent first).
        """
        history = self._load_history()
        return list(reversed(history[-limit:]))

    def print_report(self, report: OptimizationReport) -> None:
        """Print a formatted optimization report.

        Args:
            report: Optimization report to print.
        """
        from jarvis.jarvis_utils.output import PrettyOutput

        PrettyOutput.auto_print("=" * 60)
        PrettyOutput.auto_print("📋 配置优化报告")
        PrettyOutput.auto_print(
            f"🕐 生成时间: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        PrettyOutput.auto_print("=" * 60)
        PrettyOutput.auto_print("")
        PrettyOutput.auto_print(f"📁 配置文件: {self.config_path}")
        PrettyOutput.auto_print(f"📊 问题总数: {report.total_issues}")
        PrettyOutput.auto_print("")

        # Print issues by severity
        PrettyOutput.auto_print("🔴 按严重程度分类的问题:")
        for severity in ["high", "medium", "low"]:
            count = report.issues_by_severity.get(severity, 0)
            if count > 0:
                severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                    severity, "⚪"
                )
                PrettyOutput.auto_print(
                    f"  {severity_emoji} {severity.capitalize()}: {count}"
                )
        PrettyOutput.auto_print("")

        # Print issues by category
        PrettyOutput.auto_print("📂 按类别分类的问题:")
        for category in ["security", "performance", "maintainability"]:
            count = report.issues_by_category.get(category, 0)
            if count > 0:
                category_emoji = {
                    "security": "🔒",
                    "performance": "⚡",
                    "maintainability": "🔧",
                }.get(category, "📋")
                PrettyOutput.auto_print(
                    f"  {category_emoji} {category.capitalize()}: {count}"
                )
        PrettyOutput.auto_print("")

        # Print suggestions
        PrettyOutput.auto_print("💡 优化建议:")
        PrettyOutput.auto_print("-" * 60)
        for suggestion in report.suggestions:
            severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                suggestion.issue.severity.lower(), "⚪"
            )
            PrettyOutput.auto_print(
                f"\n{severity_emoji} [{suggestion.issue.severity.upper()}] {suggestion.issue.category}"
            )
            PrettyOutput.auto_print(f"📍 位置: {suggestion.issue.location}")
            PrettyOutput.auto_print(f"❓ 问题: {suggestion.issue.issue_type}")
            PrettyOutput.auto_print(f"✅ 操作: {suggestion.action}")
            PrettyOutput.auto_print(f"📈 影响: {suggestion.impact}")
            PrettyOutput.auto_print(f"⚙️ 工作量: {suggestion.effort}")
            PrettyOutput.auto_print(f"💭 原因: {suggestion.issue.reason}")
        PrettyOutput.auto_print("")

        # Print summary
        PrettyOutput.auto_print("📝 总结:")
        PrettyOutput.auto_print("-" * 60)
        PrettyOutput.auto_print(report.summary)
        PrettyOutput.auto_print("=" * 60)
