"""
Dependency History - Track Dependency Check History

This module provides functionality to track dependency check history
and store records for future reference.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class DependencyRecord:
    """Represents a dependency check record.

    Attributes:
        record_id: Unique identifier for this record.
        timestamp: ISO format timestamp of the check.
        project_path: Path to the project that was checked.
        dependencies_checked: Number of dependencies checked.
        updates_available: Number of updates available.
        update_details: Details about available updates.
    """

    record_id: str
    timestamp: str
    project_path: str
    dependencies_checked: int
    updates_available: int
    update_details: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert record to dictionary.

        Returns:
            Dictionary representation of the record.
        """
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "project_path": self.project_path,
            "dependencies_checked": self.dependencies_checked,
            "updates_available": self.updates_available,
            "update_details": self.update_details,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DependencyRecord":
        """Create record from dictionary.

        Args:
            data: Dictionary containing record data.

        Returns:
            DependencyRecord instance.
        """
        return cls(
            record_id=data["record_id"],
            timestamp=data["timestamp"],
            project_path=data["project_path"],
            dependencies_checked=data["dependencies_checked"],
            updates_available=data["updates_available"],
            update_details=data.get("update_details", []),
        )


class DependencyHistory:
    """Manages dependency check history.

    This class provides functionality to:
    - Record dependency checks
    - Retrieve history
    - Get statistics
    - Clear history

    Attributes:
        history_file: Path to the history JSON file.
    """

    def __init__(self, history_file: Optional[str] = None) -> None:
        """Initialize DependencyHistory.

        Args:
            history_file: Path to the history file. If None, uses default.
        """
        if history_file is None:
            # Use jarvis data directory
            history_dir = Path.home() / ".jarvis" / "jarvis_dependency_manager"
            history_dir.mkdir(parents=True, exist_ok=True)
            history_file = str(history_dir / "history.json")

        self.history_file = Path(history_file)
        self._ensure_history_file()

    def _ensure_history_file(self) -> None:
        """Ensure history file exists."""
        if not self.history_file.exists():
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w") as f:
                json.dump([], f)

    def _load_history(self) -> List[dict]:
        """Load history from file.

        Returns:
            List of history records as dictionaries.
        """
        try:
            with open(self.history_file, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_history(self, records: List[dict]) -> None:
        """Save history to file.

        Args:
            records: List of history records to save.
        """
        with open(self.history_file, "w") as f:
            json.dump(records, f, indent=2)

    def record_check(
        self,
        project_path: str,
        dependencies_checked: int,
        updates_available: int,
        update_details: Optional[List[dict]] = None,
    ) -> DependencyRecord:
        """Record a dependency check.

        Args:
            project_path: Path to the project that was checked.
            dependencies_checked: Number of dependencies checked.
            updates_available: Number of updates available.
            update_details: Details about available updates.

        Returns:
            The created DependencyRecord.
        """
        record = DependencyRecord(
            record_id=str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            project_path=project_path,
            dependencies_checked=dependencies_checked,
            updates_available=updates_available,
            update_details=update_details or [],
        )

        records = self._load_history()
        records.append(record.to_dict())
        self._save_history(records)

        return record

    def get_all_records(self) -> List[DependencyRecord]:
        """Get all dependency check records.

        Returns:
            List of all records, sorted by timestamp (newest first).
        """
        records = self._load_history()
        return [
            DependencyRecord.from_dict(r)
            for r in sorted(records, key=lambda x: x["timestamp"], reverse=True)
        ]

    def get_records_for_project(self, project_path: str) -> List[DependencyRecord]:
        """Get records for a specific project.

        Args:
            project_path: Path to the project.

        Returns:
            List of records for the project, sorted by timestamp (newest first).
        """
        records = self._load_history()
        project_records = [r for r in records if r["project_path"] == project_path]
        return [
            DependencyRecord.from_dict(r)
            for r in sorted(project_records, key=lambda x: x["timestamp"], reverse=True)
        ]

    def get_record_by_id(self, record_id: str) -> Optional[DependencyRecord]:
        """Get a record by ID.

        Args:
            record_id: ID of the record to retrieve.

        Returns:
            DependencyRecord if found, None otherwise.
        """
        records = self._load_history()
        for r in records:
            if r["record_id"] == record_id:
                return DependencyRecord.from_dict(r)
        return None

    def get_stats(self) -> dict:
        """Get statistics about dependency checks.

        Returns:
            Dictionary containing statistics:
            - total_checks: Total number of checks performed.
            - projects_checked: Number of unique projects checked.
            - total_updates_found: Total number of updates found across all checks.
            - average_updates_per_check: Average updates per check.
        """
        records = self._load_history()

        if not records:
            return {
                "total_checks": 0,
                "projects_checked": 0,
                "total_updates_found": 0,
                "average_updates_per_check": 0.0,
            }

        total_checks = len(records)
        projects = set(r["project_path"] for r in records)
        total_updates = sum(r["updates_available"] for r in records)

        return {
            "total_checks": total_checks,
            "projects_checked": len(projects),
            "total_updates_found": total_updates,
            "average_updates_per_check": round(total_updates / total_checks, 2),
        }

    def clear_history(self) -> None:
        """Clear all history records."""
        self._save_history([])

    def clear_project_history(self, project_path: str) -> None:
        """Clear history for a specific project.

        Args:
            project_path: Path to the project.
        """
        records = self._load_history()
        filtered_records = [r for r in records if r["project_path"] != project_path]
        self._save_history(filtered_records)
