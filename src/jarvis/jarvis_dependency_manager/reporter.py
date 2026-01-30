"""
Dependency Reporter - Generate Dependency Reports

This module provides functionality to generate dependency reports
in various formats (Markdown, JSON, etc.).
"""

import json
from enum import Enum
from typing import Dict, List, Optional

from jarvis.jarvis_dependency_manager.manager import (
    DependencyInfo,
    UpdateSuggestion,
    UpdateType,
)


class ReportFormat(Enum):
    """Available report formats."""

    MARKDOWN = "markdown"
    JSON = "json"
    PLAIN = "plain"


class DependencyReporter:
    """Generates dependency reports.

    This class provides functionality to:
    - Generate Markdown reports
    - Generate JSON reports
    - Generate plain text reports
    - Customize report content

    Example:
        >>> reporter = DependencyReporter()
        >>> report = reporter.generate_report(dependencies, suggestions)
        >>> print(report)
    """

    def __init__(self, format: ReportFormat = ReportFormat.MARKDOWN) -> None:
        """Initialize DependencyReporter.

        Args:
            format: Output format for reports (default: Markdown).
        """
        self.format = format

    def generate_report(
        self,
        dependencies: List[DependencyInfo],
        suggestions: List[UpdateSuggestion],
        project_path: Optional[str] = None,
    ) -> str:
        """Generate a dependency report.

        Args:
            dependencies: List of dependency information.
            suggestions: List of update suggestions.
            project_path: Path to project being reported on.

        Returns:
            Formatted report string.
        """
        if self.format == ReportFormat.JSON:
            return self._format_json_report(dependencies, suggestions, project_path)
        elif self.format == ReportFormat.PLAIN:
            return self._format_plain_report(dependencies, suggestions, project_path)
        else:
            return self._format_markdown_report(dependencies, suggestions, project_path)

    def _format_markdown_report(
        self,
        dependencies: List[DependencyInfo],
        suggestions: List[UpdateSuggestion],
        project_path: Optional[str],
    ) -> str:
        """Format report as Markdown.

        Args:
            dependencies: List of dependency information.
            suggestions: List of update suggestions.
            project_path: Path to project.

        Returns:
            Markdown formatted report.
        """
        lines: List[str] = []

        # Header
        lines.append("# Dependency Update Report")
        lines.append("")

        if project_path:
            lines.append(f"**Project:** `{project_path}`")
            lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total Dependencies:** {len(dependencies)}")
        lines.append(f"- **Updates Available:** {len(suggestions)}")
        lines.append("")

        # Update breakdown by type
        update_types: Dict[str, int] = {
            UpdateType.MAJOR.value: 0,
            UpdateType.MINOR.value: 0,
            UpdateType.PATCH.value: 0,
        }
        for suggestion in suggestions:
            update_types[suggestion.update_type.value] += 1

        lines.append("### Updates by Type")
        lines.append("")
        lines.append(f"- Major Updates: {update_types[UpdateType.MAJOR.value]}")
        lines.append(f"- Minor Updates: {update_types[UpdateType.MINOR.value]}")
        lines.append(f"- Patch Updates: {update_types[UpdateType.PATCH.value]}")
        lines.append("")

        # Risk breakdown
        risk_levels: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        for suggestion in suggestions:
            risk_levels[suggestion.risk_level] += 1

        lines.append("### Risk Levels")
        lines.append("")
        lines.append(f"- High Risk: {risk_levels['high']}")
        lines.append(f"- Medium Risk: {risk_levels['medium']}")
        lines.append(f"- Low Risk: {risk_levels['low']}")
        lines.append("")

        # Update suggestions
        if suggestions:
            lines.append("## Update Suggestions")
            lines.append("")

            # Group by risk level
            high_risk = [s for s in suggestions if s.risk_level == "high"]
            medium_risk = [s for s in suggestions if s.risk_level == "medium"]
            low_risk = [s for s in suggestions if s.risk_level == "low"]

            # High risk updates
            if high_risk:
                lines.append("### 🔴 High Risk Updates")
                lines.append("")
                for suggestion in high_risk:
                    lines.append(self._format_suggestion_markdown(suggestion))
                lines.append("")

            # Medium risk updates
            if medium_risk:
                lines.append("### 🟡 Medium Risk Updates")
                lines.append("")
                for suggestion in medium_risk:
                    lines.append(self._format_suggestion_markdown(suggestion))
                lines.append("")

            # Low risk updates
            if low_risk:
                lines.append("### 🟢 Low Risk Updates")
                lines.append("")
                for suggestion in low_risk:
                    lines.append(self._format_suggestion_markdown(suggestion))
                lines.append("")
        else:
            lines.append("## ✅ No Updates Available")
            lines.append("")
            lines.append("All dependencies are up to date!")
            lines.append("")

        # All dependencies
        lines.append("## All Dependencies")
        lines.append("")
        for dep in dependencies:
            lines.append(f"- **{dep.name}**: `{dep.current_version}`")
            if dep.latest_version:
                if dep.latest_version != dep.current_version:
                    lines.append(f"  - Latest: `{dep.latest_version}`")
            lines.append("")

        return "\n".join(lines)

    def _format_suggestion_markdown(self, suggestion: UpdateSuggestion) -> str:
        """Format a single suggestion as Markdown.

        Args:
            suggestion: Update suggestion to format.

        Returns:
            Markdown formatted suggestion.
        """
        lines: List[str] = []

        # Update type icon
        icon = {
            UpdateType.MAJOR: "🔴",
            UpdateType.MINOR: "🟡",
            UpdateType.PATCH: "🟢",
            UpdateType.NONE: "✅",
        }.get(suggestion.update_type, "ℹ️")

        lines.append(f"{icon} **{suggestion.dependency}**")
        lines.append(
            f"  - Update: `{suggestion.current_version}` → `{suggestion.latest_version}`"
        )
        lines.append(f"  - Type: {suggestion.update_type.value}")
        lines.append(f"  - Risk: {suggestion.risk_level}")
        lines.append(f"  - Compatible: {'Yes' if suggestion.compatible else 'No'}")
        lines.append(f"  - Reason: {suggestion.reason}")

        return "\n".join(lines)

    def _format_json_report(
        self,
        dependencies: List[DependencyInfo],
        suggestions: List[UpdateSuggestion],
        project_path: Optional[str],
    ) -> str:
        """Format report as JSON.

        Args:
            dependencies: List of dependency information.
            suggestions: List of update suggestions.
            project_path: Path to project.

        Returns:
            JSON formatted report.
        """
        # Convert dependencies to dicts
        deps_list = [
            {
                "name": dep.name,
                "current_version": dep.current_version,
                "latest_version": dep.latest_version,
                "installed": dep.installed,
                "specifiers": dep.specifiers,
            }
            for dep in dependencies
        ]

        # Convert suggestions to dicts
        suggestions_list = [
            {
                "dependency": s.dependency,
                "current_version": s.current_version,
                "latest_version": s.latest_version,
                "update_type": s.update_type.value,
                "compatible": s.compatible,
                "risk_level": s.risk_level,
                "reason": s.reason,
            }
            for s in suggestions
        ]

        # Build report
        report: Dict = {
            "project_path": project_path,
            "summary": {
                "total_dependencies": len(dependencies),
                "updates_available": len(suggestions),
            },
            "dependencies": deps_list,
            "suggestions": suggestions_list,
        }

        return json.dumps(report, indent=2)

    def _format_plain_report(
        self,
        dependencies: List[DependencyInfo],
        suggestions: List[UpdateSuggestion],
        project_path: Optional[str],
    ) -> str:
        """Format report as plain text.

        Args:
            dependencies: List of dependency information.
            suggestions: List of update suggestions.
            project_path: Path to project.

        Returns:
            Plain text formatted report.
        """
        lines: List[str] = []

        # Header
        lines.append("=" * 60)
        lines.append("DEPENDENCY UPDATE REPORT")
        lines.append("=" * 60)
        lines.append("")

        if project_path:
            lines.append(f"Project: {project_path}")
            lines.append("")

        # Summary
        lines.append("SUMMARY")
        lines.append("-" * 40)
        lines.append(f"Total Dependencies: {len(dependencies)}")
        lines.append(f"Updates Available: {len(suggestions)}")
        lines.append("")

        # Update suggestions
        if suggestions:
            lines.append("UPDATE SUGGESTIONS")
            lines.append("-" * 40)
            for suggestion in suggestions:
                lines.append("")
                lines.append(f"Package: {suggestion.dependency}")
                lines.append(
                    f"  Update: {suggestion.current_version} -> {suggestion.latest_version}"
                )
                lines.append(f"  Type: {suggestion.update_type.value}")
                lines.append(f"  Risk: {suggestion.risk_level}")
                lines.append(
                    f"  Compatible: {'Yes' if suggestion.compatible else 'No'}"
                )
                lines.append(f"  Reason: {suggestion.reason}")
        else:
            lines.append("No updates available!")
            lines.append("")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)
