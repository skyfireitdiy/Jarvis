"""
jarvis_auto_fix - Code Auto-Fix Module

This module provides automatic detection and fixing capabilities for common code issues.

Features:
    - Automatic detection of syntax errors
    - Automatic detection of import errors
    - Automatic detection of formatting issues
    - Safe code fixing based on rules
    - Fix history tracking
    - Rollback capability

Usage:
    >>> from jarvis.jarvis_auto_fix import AutoFixer, FixHistory
    >>> fixer = AutoFixer()
    >>> issues = fixer.detect_issues("/path/to/file.py")
    >>> fixer.fix_issues("/path/to/file.py")
    >>> history = FixHistory()
    >>> history.get_all_fixes()

Safety:
    - Does not modify business logic
    - Does not automatically commit code
    - All fixes are reversible
"""

# Public API exports
from jarvis.jarvis_auto_fix.fixer import AutoFixer
from jarvis.jarvis_auto_fix.fix_history import FixHistory

__version__ = "0.1.0"
__all__ = ["AutoFixer", "FixHistory"]
