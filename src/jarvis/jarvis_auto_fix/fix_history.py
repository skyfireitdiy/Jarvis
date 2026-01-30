"""
Fix History Management Module

This module provides functionality to track, query, and rollback code fixes.
"""

import json
import os
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class FixRecord:
    """Represents a single fix record.

    Attributes:
        record_id: Unique identifier for this fix record
        file_path: Path to the file that was fixed
        issue_type: Type of the issue (syntax_error, import_error, format_issue)
        original_content: Content of the file before the fix
        fixed_content: Content of the file after the fix
        timestamp: When the fix was applied
        fix_applied: Description of the fix that was applied
        rollback_available: Whether this fix can be rolled back
    """

    record_id: str
    file_path: str
    issue_type: str
    original_content: str
    fixed_content: str
    timestamp: str
    fix_applied: str
    rollback_available: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert the fix record to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FixRecord":
        """Create a fix record from a dictionary."""
        return cls(**data)


class FixHistory:
    """Manages the history of code fixes.

    This class provides thread-safe operations to record, query, and rollback
    code fixes. All history is stored in JSON format for lightweight persistence.

    Attributes:
        history_file: Path to the JSON file storing the fix history

    Example:
        >>> history = FixHistory()
        >>> record = FixRecord(
        ...     record_id="fix-001",
        ...     file_path="/path/to/file.py",
        ...     issue_type="syntax_error",
        ...     original_content="def foo():\n    return 1\n",
        ...     fixed_content="def foo():\n    return 1\n",
        ...     timestamp="2024-01-01T00:00:00",
        ...     fix_applied="Added newline at end of file"
        ... )
        >>> history.record_fix(record)
        >>> all_fixes = history.get_all_fixes()
        >>> history.rollback_fix("fix-001")
    """

    def __init__(self, history_file: Optional[str] = None) -> None:
        """Initialize the FixHistory manager.

        Args:
            history_file: Path to the history JSON file. If None, uses default path
                         in jarvis data directory.
        """
        if history_file is None:
            # Default path in jarvis data directory
            from jarvis.jarvis_utils.config import get_data_dir

            data_dir = get_data_dir()
            history_file = os.path.join(data_dir, "fix_history.json")

        self.history_file: str = history_file
        self._lock: threading.RLock = (
            threading.RLock()
        )  # Use RLock to allow reentrant locking
        self._ensure_history_file()

    def _ensure_history_file(self) -> None:
        """Ensure the history file exists and is valid."""
        with self._lock:
            if not os.path.exists(self.history_file):
                directory = os.path.dirname(self.history_file)
                if directory:
                    os.makedirs(directory, exist_ok=True)

                with open(self.history_file, "w", encoding="utf-8") as f:
                    json.dump([], f)

    def _load_history(self) -> List[Dict[str, Any]]:
        """Load the fix history from the JSON file.

        Returns:
            List of fix record dictionaries.
        """
        with self._lock:
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    assert isinstance(data, list)
                    return data
            except (json.JSONDecodeError, FileNotFoundError):
                # If the file is corrupted or doesn't exist, return empty list
                return []

    def _save_history(self, history: List[Dict[str, Any]]) -> None:
        """Save the fix history to the JSON file.

        Args:
            history: List of fix record dictionaries to save.
        """
        with self._lock:
            directory = os.path.dirname(self.history_file)
            if directory:
                os.makedirs(directory, exist_ok=True)

            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)

    def record_fix(self, record: FixRecord) -> None:
        """Record a fix in the history.

        Args:
            record: The fix record to add to history.
        """
        with self._lock:
            history = self._load_history()
            history.append(record.to_dict())
            self._save_history(history)

    def get_all_fixes(self) -> List[FixRecord]:
        """Get all fix records from history.

        Returns:
            List of all fix records, ordered by timestamp (newest first).
        """
        with self._lock:
            history_dicts = self._load_history()
            records = [FixRecord.from_dict(data) for data in history_dicts]
            # Sort by timestamp, newest first
            records.sort(key=lambda x: x.timestamp, reverse=True)
            return records

    def get_fixes_for_file(self, file_path: str) -> List[FixRecord]:
        """Get all fix records for a specific file.

        Args:
            file_path: Path to the file.

        Returns:
            List of fix records for the file, ordered by timestamp (newest first).
        """
        with self._lock:
            all_fixes = self.get_all_fixes()
            return [fix for fix in all_fixes if fix.file_path == file_path]

    def get_fix_by_id(self, record_id: str) -> Optional[FixRecord]:
        """Get a fix record by its ID.

        Args:
            record_id: The unique ID of the fix record.

        Returns:
            The fix record if found, None otherwise.
        """
        with self._lock:
            all_fixes = self.get_all_fixes()
            for fix in all_fixes:
                if fix.record_id == record_id:
                    return fix
            return None

    def rollback_fix(self, record_id: str) -> bool:
        """Rollback a fix by restoring the original content.

        Args:
            record_id: The ID of the fix record to rollback.

        Returns:
            True if rollback was successful, False otherwise.
        """
        with self._lock:
            record = self.get_fix_by_id(record_id)
            if record is None:
                return False

            if not record.rollback_available:
                return False

            file_path = Path(record.file_path)
            if not file_path.exists():
                return False

            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(record.original_content)
                return True
            except (IOError, OSError):
                return False

    def clear_history(self) -> None:
        """Clear all fix history.

        Warning:
            This operation cannot be undone.
        """
        with self._lock:
            self._save_history([])

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the fix history.

        Returns:
            Dictionary containing statistics:
                - total_fixes: Total number of fixes
                - files_fixed: Number of unique files fixed
                - issue_types: Breakdown by issue type
        """
        with self._lock:
            all_fixes = self.get_all_fixes()

            if not all_fixes:
                return {"total_fixes": 0, "files_fixed": 0, "issue_types": {}}

            total_fixes = len(all_fixes)
            unique_files = len({fix.file_path for fix in all_fixes})
            issue_types: Dict[str, int] = {}

            for fix in all_fixes:
                issue_types[fix.issue_type] = issue_types.get(fix.issue_type, 0) + 1

            return {
                "total_fixes": total_fixes,
                "files_fixed": unique_files,
                "issue_types": issue_types,
            }


def generate_fix_id() -> str:
    """Generate a unique fix ID.

    Returns:
        A unique ID in the format 'fix-YYYYMMDDHHMMSS-<random>'.
    """
    import random

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_str = random.randint(1000, 9999)
    return f"fix-{timestamp}-{random_str}"
