"""
Auto Fixer Module - Core Code Detection and Fixing Logic

This module provides automatic detection and fixing of common code issues.
"""

import ast
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from jarvis.jarvis_auto_fix.fix_history import FixHistory, FixRecord, generate_fix_id


@dataclass
class Issue:
    """Represents a detected code issue.

    Attributes:
        issue_type: Type of the issue (syntax_error, import_error, format_issue)
        file_path: Path to the file with the issue
        line_number: Line number where the issue occurs
        severity: Severity level (error, warning, info)
        message: Human-readable description of the issue
        suggestion: Suggested fix or None if no suggestion available
        fixable: Whether this issue can be automatically fixed
    """

    issue_type: str
    file_path: str
    line_number: int
    severity: str
    message: str
    suggestion: Optional[str] = None
    fixable: bool = False


class AutoFixer:
    """Automatic code issue detector and fixer.

    This class provides functionality to detect common code issues and
    automatically fix them when possible. It integrates with FixHistory to
    track all fixes and enable rollbacks.

    Attributes:
        history: FixHistory instance for tracking fixes

    Example:
        >>> fixer = AutoFixer()
        >>> issues = fixer.detect_issues("/path/to/file.py")
        >>> fixer.fix_issues("/path/to/file.py")
    """

    # Issue types
    ISSUE_SYNTAX_ERROR = "syntax_error"
    ISSUE_IMPORT_ERROR = "import_error"
    ISSUE_FORMAT_ISSUE = "format_issue"

    # Severity levels
    SEVERITY_ERROR = "error"
    SEVERITY_WARNING = "warning"
    SEVERITY_INFO = "info"

    def __init__(self, history: Optional[FixHistory] = None) -> None:
        """Initialize the AutoFixer.

        Args:
            history: Optional FixHistory instance. If None, creates a new one.
        """
        self.history = history or FixHistory()

    def detect_issues(self, file_path: str) -> List[Issue]:
        """Detect code issues in a file.

        Args:
            file_path: Path to the file to analyze.

        Returns:
            List of detected issues.
        """
        issues: List[Issue] = []

        # Check if file exists
        if not os.path.exists(file_path):
            return []

        # Detect syntax errors
        syntax_issues = self._detect_syntax_errors(file_path)
        issues.extend(syntax_issues)

        # Detect import errors
        import_issues = self._detect_import_errors(file_path)
        issues.extend(import_issues)

        # Detect format issues
        format_issues = self._detect_format_issues(file_path)
        issues.extend(format_issues)

        return issues

    def _detect_syntax_errors(self, file_path: str) -> List[Issue]:
        """Detect syntax errors using AST parsing.

        Args:
            file_path: Path to the file to analyze.

        Returns:
            List of syntax error issues.
        """
        issues: List[Issue] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            ast.parse(content)
        except SyntaxError as e:
            issues.append(
                Issue(
                    issue_type=self.ISSUE_SYNTAX_ERROR,
                    file_path=file_path,
                    line_number=e.lineno or 0,
                    severity=self.SEVERITY_ERROR,
                    message=f"Syntax error: {e.msg}",
                    suggestion="Check for missing parentheses, brackets, or quotes",
                    fixable=False,  # Syntax errors are not automatically fixable
                )
            )
        except Exception:
            # Other exceptions (e.g., encoding errors) are not syntax errors
            pass

        return issues

    def _detect_import_errors(self, file_path: str) -> List[Issue]:
        """Detect import errors.

        Args:
            file_path: Path to the file to analyze.

        Returns:
            List of import error issues.
        """
        issues: List[Issue] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (UnicodeDecodeError, OSError):
            # Skip files with encoding issues or other IO errors
            return issues

        try:
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if self._is_broken_import(alias.name):
                            issues.append(
                                Issue(
                                    issue_type=self.ISSUE_IMPORT_ERROR,
                                    file_path=file_path,
                                    line_number=node.lineno,
                                    severity=self.SEVERITY_ERROR,
                                    message=f"Import error: module '{alias.name}' not found",
                                    suggestion="Install the required package or check import path",
                                    fixable=False,
                                )
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module and self._is_broken_import(node.module):
                        issues.append(
                            Issue(
                                issue_type=self.ISSUE_IMPORT_ERROR,
                                file_path=file_path,
                                line_number=node.lineno,
                                severity=self.SEVERITY_ERROR,
                                message=f"Import error: module '{node.module}' not found",
                                suggestion="Install the required package or check import path",
                                fixable=False,
                            )
                        )
        except SyntaxError:
            # Skip if file has syntax errors
            pass

        return issues

    def _is_broken_import(self, module_name: str) -> bool:
        """Check if an import is broken.

        Args:
            module_name: Name of the module to check.

        Returns:
            True if the import is broken, False otherwise.
        """
        # Check for local imports first
        if module_name.startswith("."):
            return False

        # Try to import the module
        try:
            __import__(module_name.split(".")[0])
            return False
        except ImportError:
            return True
        except Exception:
            # Other errors (e.g., ValueError) mean it's not a broken import
            return False

    def _detect_format_issues(self, file_path: str) -> List[Issue]:
        """Detect format issues using ruff.

        Args:
            file_path: Path to the file to analyze.

        Returns:
            List of format issue issues.
        """
        issues: List[Issue] = []

        try:
            # Run ruff check
            result = subprocess.run(
                ["ruff", "check", "--select=F,W,E", "--output-format=json", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.stdout:
                import json

                ruff_output = json.loads(result.stdout)

                for item in ruff_output:
                    # Safely extract fix suggestion (fix field may be None)
                    fix_data = item.get("fix")
                    suggestion = fix_data.get("message") if fix_data else None

                    issues.append(
                        Issue(
                            issue_type=self.ISSUE_FORMAT_ISSUE,
                            file_path=file_path,
                            line_number=item.get("location", {}).get("row", 0),
                            severity=self._ruff_code_to_severity(item.get("code", "W")),
                            message=item.get("message", "Unknown format issue"),
                            suggestion=suggestion,
                            fixable=bool(item.get("fix")),
                        )
                    )
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            # Ruff not available or timeout, skip format checking
            pass

        return issues

    def _ruff_code_to_severity(self, code: str) -> str:
        """Convert ruff error code to severity level.

        Args:
            code: Ruff error code (e.g., "F401", "W503").

        Returns:
            Severity level (error, warning, info).
        """
        if code.startswith("F"):
            return self.SEVERITY_ERROR
        elif code.startswith("W"):
            return self.SEVERITY_WARNING
        else:
            return self.SEVERITY_INFO

    def fix_issues(self, file_path: str) -> List[FixRecord]:
        """Fix all fixable issues in a file.

        Args:
            file_path: Path to the file to fix.

        Returns:
            List of fix records for the fixes that were applied.
        """
        fix_records: List[FixRecord] = []

        # Detect issues
        issues = self.detect_issues(file_path)

        # Fix format issues
        format_fixes = self._fix_format_issues(file_path)
        fix_records.extend(format_fixes)

        # Fix other fixable issues
        for issue in issues:
            if issue.fixable:
                record = self._fix_issue(issue)
                if record:
                    fix_records.append(record)

        return fix_records

    def _fix_format_issues(self, file_path: str) -> List[FixRecord]:
        """Fix format issues using ruff.

        Args:
            file_path: Path to the file to fix.

        Returns:
            List of fix records for the fixes that were applied.
        """
        fix_records: List[FixRecord] = []

        try:
            # Read original content
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()

            # Run ruff fix
            subprocess.run(
                ["ruff", "check", "--fix", "--select=F,W,E", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Read fixed content
            with open(file_path, "r", encoding="utf-8") as f:
                fixed_content = f.read()

            # If content changed, record the fix
            if original_content != fixed_content:
                record_id = generate_fix_id()
                record = FixRecord(
                    record_id=record_id,
                    file_path=file_path,
                    issue_type=self.ISSUE_FORMAT_ISSUE,
                    original_content=original_content,
                    fixed_content=fixed_content,
                    timestamp=datetime.now().isoformat(),
                    fix_applied="Applied ruff auto-fixes",
                    rollback_available=True,
                )
                self.history.record_fix(record)
                fix_records.append(record)

        except (subprocess.TimeoutExpired, FileNotFoundError, IOError):
            # Ruff not available or timeout, skip fixing
            pass

        return fix_records

    def _fix_issue(self, issue: Issue) -> Optional[FixRecord]:
        """Fix a specific issue.

        Args:
            issue: The issue to fix.

        Returns:
            Fix record if fix was applied, None otherwise.
        """
        # Currently, only format issues are automatically fixable
        if issue.issue_type != self.ISSUE_FORMAT_ISSUE:
            return None

        return None

    def fix_all_files(self, directory: str, pattern: str = "*.py") -> List[FixRecord]:
        """Fix all Python files in a directory.

        Args:
            directory: Path to the directory to fix.
            pattern: File pattern to match (default: *.py).

        Returns:
            List of all fix records.
        """
        all_fixes: List[FixRecord] = []

        for file_path in Path(directory).rglob(pattern):
            try:
                fixes = self.fix_issues(str(file_path))
                all_fixes.extend(fixes)
            except Exception:
                # Skip files that can't be fixed
                continue

        return all_fixes
