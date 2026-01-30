"""Configuration analyzer for jarvis_config_optimizer.

This module provides functionality to parse and analyze project configuration files,
including pyproject.toml and tool-specific configurations.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass
class ConfigIssue:
    """Represents a configuration issue found during analysis.

    Attributes:
        issue_type: Type of issue (deprecated, conflict, missing)
        severity: Severity level (low, medium, high)
        location: Location in config file (e.g., "tool.ruff.line-length")
        current_value: Current configured value
        recommended_value: Recommended value
        reason: Reason for the issue
        category: Category of optimization (security, performance, maintainability)
    """

    issue_type: Literal["deprecated", "conflict", "missing"]
    severity: Literal["low", "medium", "high"]
    location: str
    current_value: Any | None
    recommended_value: Any
    reason: str
    category: Literal["security", "performance", "maintainability"]


@dataclass
class ToolConfig:
    """Represents configuration for a specific tool.

    Attributes:
        tool_name: Name of the tool (e.g., "ruff", "mypy", "pytest")
        config: Raw configuration dictionary
        issues: List of configuration issues found
    """

    tool_name: str
    config: dict[str, Any]
    issues: list[ConfigIssue] = field(default_factory=list)


class ConfigAnalyzer:
    """Analyzer for project configuration files.

    This class parses pyproject.toml and analyzes tool configurations
    to identify issues and optimization opportunities.
    """

    def __init__(self, config_path: str | Path = "pyproject.toml") -> None:
        """Initialize the configuration analyzer.

        Args:
            config_path: Path to the pyproject.toml file.

        Raises:
            FileNotFoundError: If the config file doesn't exist.
            tomllib.TOMLDecodeError: If the config file is invalid TOML.
        """
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(self.config_path, "rb") as f:
            self.config = tomllib.load(f)

        self.tool_configs: dict[str, ToolConfig] = {}

    def parse(self) -> dict[str, ToolConfig]:
        """Parse all tool configurations from pyproject.toml.

        Returns:
            Dictionary mapping tool names to their configurations.
        """
        tools_section = self.config.get("tool", {})

        # Parse ruff configuration
        if "ruff" in tools_section:
            self._parse_ruff_config(tools_section["ruff"])

        # Parse mypy configuration
        if "mypy" in tools_section:
            self._parse_mypy_config(tools_section["mypy"])

        # Parse pytest configuration
        if "pytest" in tools_section:
            self._parse_pytest_config(tools_section["pytest"])

        # Parse bandit configuration
        if "bandit" in tools_section:
            self._parse_bandit_config(tools_section["bandit"])

        # Analyze each tool configuration
        self._analyze_all_configs()

        return self.tool_configs

    def _parse_ruff_config(self, config: dict[str, Any]) -> None:
        """Parse ruff tool configuration.

        Args:
            config: Ruff configuration dictionary.
        """
        self.tool_configs["ruff"] = ToolConfig(tool_name="ruff", config=config)

    def _parse_mypy_config(self, config: dict[str, Any]) -> None:
        """Parse mypy tool configuration.

        Args:
            config: Mypy configuration dictionary.
        """
        self.tool_configs["mypy"] = ToolConfig(tool_name="mypy", config=config)

    def _parse_pytest_config(self, config: dict[str, Any]) -> None:
        """Parse pytest tool configuration.

        Args:
            config: Pytest configuration dictionary.
        """
        self.tool_configs["pytest"] = ToolConfig(tool_name="pytest", config=config)

    def _parse_bandit_config(self, config: dict[str, Any]) -> None:
        """Parse bandit tool configuration.

        Args:
            config: Bandit configuration dictionary.
        """
        self.tool_configs["bandit"] = ToolConfig(tool_name="bandit", config=config)

    def _analyze_all_configs(self) -> None:
        """Analyze all parsed tool configurations for issues."""
        for tool_name, tool_config in self.tool_configs.items():
            if tool_name == "ruff":
                self._analyze_ruff(tool_config)
            elif tool_name == "mypy":
                self._analyze_mypy(tool_config)
            elif tool_name == "pytest":
                self._analyze_pytest(tool_config)
            elif tool_name == "bandit":
                self._analyze_bandit(tool_config)

    def _analyze_ruff(self, tool_config: ToolConfig) -> None:
        """Analyze ruff configuration for issues.

        Args:
            tool_config: Ruff tool configuration.
        """
        config = tool_config.config

        # Check for line-length configuration
        line_length = config.get("line-length", 88)
        if line_length != 88:
            tool_config.issues.append(
                ConfigIssue(
                    issue_type="deprecated",
                    severity="low",
                    location="tool.ruff.line-length",
                    current_value=line_length,
                    recommended_value=88,
                    reason="Line length of 88 is the default and recommended for ruff",
                    category="maintainability",
                )
            )

        # Check for target-version
        target_version = config.get("target-version")
        if target_version and target_version < "py312":
            tool_config.issues.append(
                ConfigIssue(
                    issue_type="deprecated",
                    severity="medium",
                    location="tool.ruff.target-version",
                    current_value=target_version,
                    recommended_value="py312",
                    reason="Python 3.12 is the current stable version",
                    category="maintainability",
                )
            )

        # Check for select configuration (too restrictive or too permissive)
        select = config.get("select", ["E", "F"])
        if not select or select == []:
            tool_config.issues.append(
                ConfigIssue(
                    issue_type="missing",
                    severity="high",
                    location="tool.ruff.select",
                    current_value=select,
                    recommended_value=["E", "F"],
                    reason="No rules selected for linting",
                    category="maintainability",
                )
            )

    def _analyze_mypy(self, tool_config: ToolConfig) -> None:
        """Analyze mypy configuration for issues.

        Args:
            tool_config: Mypy tool configuration.
        """
        config = tool_config.config

        # Check for strict mode
        strict = config.get("strict", False)
        if not strict:
            tool_config.issues.append(
                ConfigIssue(
                    issue_type="missing",
                    severity="medium",
                    location="tool.mypy.strict",
                    current_value=strict,
                    recommended_value=True,
                    reason="Strict mode catches more type errors",
                    category="security",
                )
            )

        # Check for warn_return_any
        warn_return_any = config.get("warn_return_any", False)
        if not warn_return_any:
            tool_config.issues.append(
                ConfigIssue(
                    issue_type="missing",
                    severity="low",
                    location="tool.mypy.warn_return_any",
                    current_value=warn_return_any,
                    recommended_value=True,
                    reason="Warn when functions return Any",
                    category="maintainability",
                )
            )

    def _analyze_pytest(self, tool_config: ToolConfig) -> None:
        """Analyze pytest configuration for issues.

        Args:
            tool_config: Pytest tool configuration.
        """
        config = tool_config.config

        # Check for testpaths configuration
        testpaths = config.get("testpaths")
        if not testpaths:
            tool_config.issues.append(
                ConfigIssue(
                    issue_type="missing",
                    severity="low",
                    location="tool.pytest.testpaths",
                    current_value=testpaths,
                    recommended_value=["tests"],
                    reason="Define explicit test paths for better organization",
                    category="maintainability",
                )
            )

        # Check for pythonpath
        pythonpath = config.get("pythonpath")
        if not pythonpath:
            tool_config.issues.append(
                ConfigIssue(
                    issue_type="missing",
                    severity="low",
                    location="tool.pytest.pythonpath",
                    current_value=pythonpath,
                    recommended_value=["."],
                    reason="Add current directory to Python path",
                    category="maintainability",
                )
            )

    def _analyze_bandit(self, tool_config: ToolConfig) -> None:
        """Analyze bandit configuration for issues.

        Args:
            tool_config: Bandit tool configuration.
        """
        config = tool_config.config

        # Check for skips - should not skip critical tests
        skips = config.get("skips", [])
        critical_tests = ["B101", "B301", "B302"]  # assert_used, pickle, marshal
        for test in critical_tests:
            if test in skips:
                tool_config.issues.append(
                    ConfigIssue(
                        issue_type="conflict",
                        severity="high",
                        location="tool.bandit.skips",
                        current_value=skips,
                        recommended_value=[s for s in skips if s != test],
                        reason=f"Skipping critical security test {test} is not recommended",
                        category="security",
                    )
                )

    def get_issues(self) -> list[ConfigIssue]:
        """Get all configuration issues found.

        Returns:
            List of all ConfigIssue objects.
        """
        issues: list[ConfigIssue] = []
        for tool_config in self.tool_configs.values():
            issues.extend(tool_config.issues)
        return issues

    def get_issues_by_category(
        self, category: Literal["security", "performance", "maintainability"]
    ) -> list[ConfigIssue]:
        """Get issues filtered by category.

        Args:
            category: Category to filter by.

        Returns:
            List of ConfigIssue objects for the category.
        """
        return [issue for issue in self.get_issues() if issue.category == category]

    def get_issues_by_severity(
        self, severity: Literal["low", "medium", "high"]
    ) -> list[ConfigIssue]:
        """Get issues filtered by severity.

        Args:
            severity: Severity to filter by.

        Returns:
            List of ConfigIssue objects for the severity.
        """
        return [issue for issue in self.get_issues() if issue.severity == severity]
