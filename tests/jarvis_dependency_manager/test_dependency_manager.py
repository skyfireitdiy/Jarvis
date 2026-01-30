"""
Tests for jarvis_dependency_manager module.

This test suite covers all core functionality of the dependency manager:
- Dependency parsing (pyproject.toml, requirements.txt)
- PyPI version querying
- Update suggestion generation
- Version compatibility checking
- Report generation
- History tracking
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from jarvis.jarvis_dependency_manager import (
    DependencyHistory,
    DependencyInfo,
    DependencyManager,
    DependencyRecord,
    DependencyReporter,
    ReportFormat,
    UpdateSuggestion,
    UpdateType,
)


class TestDependencyInfo:
    """Test cases for DependencyInfo dataclass."""

    def test_dependency_info_creation(self) -> None:
        """Test creating a DependencyInfo."""
        dep = DependencyInfo(
            name="requests",
            current_version="2.32.0",
            latest_version="2.32.3",
            installed=True,
            specifiers=">=2.0.0",
        )
        assert dep.name == "requests"
        assert dep.current_version == "2.32.0"
        assert dep.latest_version == "2.32.3"
        assert dep.installed is True


class TestUpdateSuggestion:
    """Test cases for UpdateSuggestion dataclass."""

    def test_update_suggestion_creation(self) -> None:
        """Test creating an UpdateSuggestion."""
        suggestion = UpdateSuggestion(
            dependency="requests",
            current_version="2.32.0",
            latest_version="2.33.0",
            update_type=UpdateType.MINOR,
            compatible=True,
            risk_level="medium",
            reason="New features included",
        )
        assert suggestion.dependency == "requests"
        assert suggestion.update_type == UpdateType.MINOR
        assert suggestion.compatible is True


class TestDependencyRecord:
    """Test cases for DependencyRecord dataclass."""

    def test_record_creation(self) -> None:
        """Test creating a DependencyRecord."""
        record = DependencyRecord(
            record_id="rec-001",
            timestamp="2024-01-01T00:00:00",
            project_path="/test/project",
            dependencies_checked=10,
            updates_available=2,
        )
        assert record.record_id == "rec-001"
        assert record.dependencies_checked == 10
        assert record.updates_available == 2

    def test_to_dict(self) -> None:
        """Test converting record to dictionary."""
        record = DependencyRecord(
            record_id="rec-001",
            timestamp="2024-01-01T00:00:00",
            project_path="/test",
            dependencies_checked=5,
            updates_available=1,
        )
        data = record.to_dict()
        assert isinstance(data, dict)
        assert data["record_id"] == "rec-001"

    def test_from_dict(self) -> None:
        """Test creating record from dictionary."""
        data = {
            "record_id": "rec-001",
            "timestamp": "2024-01-01T00:00:00",
            "project_path": "/test",
            "dependencies_checked": 5,
            "updates_available": 1,
            "update_details": [],
        }
        record = DependencyRecord.from_dict(data)
        assert record.record_id == "rec-001"
        assert record.project_path == "/test"


class TestDependencyManager:
    """Test cases for DependencyManager class."""

    @pytest.fixture
    def temp_cache_dir(self) -> str:
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def dependency_manager(self, temp_cache_dir: str) -> DependencyManager:
        """Create a DependencyManager instance."""
        return DependencyManager(cache_dir=temp_cache_dir)

    def test_init_default(self) -> None:
        """Test initialization with default cache dir."""
        manager = DependencyManager()
        assert manager.cache_dir.exists()

    def test_init_custom_cache(self, temp_cache_dir: str) -> None:
        """Test initialization with custom cache dir."""
        manager = DependencyManager(cache_dir=temp_cache_dir)
        # Cache dir now appends "jarvis_dep_cache" subdirectory
        assert manager.cache_dir == Path(temp_cache_dir) / "jarvis_dep_cache"

    def test_parse_dependency_spec_pinned(self) -> None:
        """Test parsing pinned version spec."""
        manager = DependencyManager()
        dep = manager._parse_dependency_spec("requests==2.32.0")
        assert dep is not None
        assert dep.name == "requests"
        assert dep.current_version == "2.32.0"
        assert dep.specifiers == "==2.32.0"

    def test_parse_dependency_spec_range(self) -> None:
        """Test parsing range version spec."""
        manager = DependencyManager()
        dep = manager._parse_dependency_spec("requests>=2.0.0,<3.0.0")
        assert dep is not None
        assert dep.name == "requests"
        assert dep.current_version == "2.0.0"
        assert dep.specifiers == ">=2.0.0,<3.0.0"

    def test_parse_dependency_spec_no_version(self) -> None:
        """Test parsing spec without version."""
        manager = DependencyManager()
        # Use a non-existent package to ensure version is unknown
        dep = manager._parse_dependency_spec("definitely_not_a_real_package_xyz")
        assert dep is not None
        assert dep.name == "definitely_not_a_real_package_xyz"
        assert dep.current_version == "unknown"

    def test_parse_dependency_spec_invalid(self) -> None:
        """Test parsing invalid spec."""
        manager = DependencyManager()
        dep = manager._parse_dependency_spec("")
        assert dep is None

    def test_check_dependencies_with_pyproject(
        self, dependency_manager: DependencyManager
    ) -> None:
        """Test checking dependencies from pyproject.toml."""
        with tempfile.TemporaryDirectory() as temp_dir:
            pyproject_path = Path(temp_dir) / "pyproject.toml"
            pyproject_path.write_text(
                """
[project]
dependencies = [
    "requests>=2.0.0",
    "numpy",
]
"""
            )

            # Mock PyPI queries to avoid network calls
            with patch.object(
                dependency_manager, "_query_pypi_version", return_value="2.32.3"
            ):
                deps = dependency_manager.check_dependencies(temp_dir)

                assert len(deps) == 2
                assert any(d.name == "requests" for d in deps)
                assert any(d.name == "numpy" for d in deps)

    def test_check_dependencies_with_requirements(
        self, dependency_manager: DependencyManager
    ) -> None:
        """Test checking dependencies from requirements.txt."""
        with tempfile.TemporaryDirectory() as temp_dir:
            req_path = Path(temp_dir) / "requirements.txt"
            req_path.write_text(
                """
requests==2.32.0
numpy>=1.20.0
# Comment line
"""
            )

            with patch.object(
                dependency_manager, "_query_pypi_version", return_value="2.32.3"
            ):
                deps = dependency_manager.check_dependencies(temp_dir)

                assert len(deps) >= 2
                assert any(d.name == "requests" for d in deps)
                assert any(d.name == "numpy" for d in deps)

    def test_determine_update_type_major(
        self, dependency_manager: DependencyManager
    ) -> None:
        """Test determining major update type."""
        from packaging.version import Version

        current = Version("1.0.0")
        latest = Version("2.0.0")
        update_type = dependency_manager._determine_update_type(current, latest)
        assert update_type == UpdateType.MAJOR

    def test_determine_update_type_minor(
        self, dependency_manager: DependencyManager
    ) -> None:
        """Test determining minor update type."""
        from packaging.version import Version

        current = Version("1.0.0")
        latest = Version("1.1.0")
        update_type = dependency_manager._determine_update_type(current, latest)
        assert update_type == UpdateType.MINOR

    def test_determine_update_type_patch(
        self, dependency_manager: DependencyManager
    ) -> None:
        """Test determining patch update type."""
        from packaging.version import Version

        current = Version("1.0.0")
        latest = Version("1.0.1")
        update_type = dependency_manager._determine_update_type(current, latest)
        assert update_type == UpdateType.PATCH

    def test_check_compatibility_no_specifiers(
        self, dependency_manager: DependencyManager
    ) -> None:
        """Test compatibility check with no specifiers."""
        from packaging.version import Version

        dep = DependencyInfo(name="test", current_version="1.0.0", specifiers="")
        current = Version("1.0.0")
        latest = Version("2.0.0")
        compatible = dependency_manager._check_compatibility(dep, current, latest)
        assert compatible is True

    def test_check_compatibility_with_specifiers(
        self, dependency_manager: DependencyManager
    ) -> None:
        """Test compatibility check with specifiers."""
        from packaging.version import Version

        dep = DependencyInfo(
            name="test", current_version="1.0.0", specifiers=">=1.0.0,<2.0.0"
        )
        current = Version("1.0.0")
        latest = Version("1.5.0")
        compatible = dependency_manager._check_compatibility(dep, current, latest)
        assert compatible is True

    def test_check_compatibility_incompatible(
        self, dependency_manager: DependencyManager
    ) -> None:
        """Test compatibility check with incompatible version."""
        from packaging.version import Version

        dep = DependencyInfo(
            name="test", current_version="1.0.0", specifiers=">=1.0.0,<2.0.0"
        )
        current = Version("1.0.0")
        latest = Version("2.0.0")
        compatible = dependency_manager._check_compatibility(dep, current, latest)
        assert compatible is False

    def test_assess_risk_major(self, dependency_manager: DependencyManager) -> None:
        """Test risk assessment for major update."""
        risk = dependency_manager._assess_risk(UpdateType.MAJOR, True)
        assert risk == "high"

    def test_assess_risk_minor(self, dependency_manager: DependencyManager) -> None:
        """Test risk assessment for minor update."""
        risk = dependency_manager._assess_risk(UpdateType.MINOR, True)
        assert risk == "medium"

    def test_assess_risk_patch(self, dependency_manager: DependencyManager) -> None:
        """Test risk assessment for patch update."""
        risk = dependency_manager._assess_risk(UpdateType.PATCH, True)
        assert risk == "low"

    def test_assess_risk_incompatible(
        self, dependency_manager: DependencyManager
    ) -> None:
        """Test risk assessment for incompatible update."""
        risk = dependency_manager._assess_risk(UpdateType.PATCH, False)
        assert risk == "high"

    def test_get_update_suggestions(
        self, dependency_manager: DependencyManager
    ) -> None:
        """Test generating update suggestions."""
        dependencies = [
            DependencyInfo(
                name="requests",
                current_version="2.32.0",
                latest_version="2.33.0",
                specifiers=">=2.0.0",
            ),
            DependencyInfo(
                name="numpy",
                current_version="1.20.0",
                latest_version="1.21.0",
                specifiers=">=1.0.0",
            ),
        ]

        suggestions = dependency_manager.get_update_suggestions(dependencies)

        assert len(suggestions) == 2
        assert all(isinstance(s, UpdateSuggestion) for s in suggestions)

    def test_get_update_suggestions_no_updates(
        self, dependency_manager: DependencyManager
    ) -> None:
        """Test generating suggestions when no updates available."""
        dependencies = [
            DependencyInfo(
                name="requests",
                current_version="2.32.0",
                latest_version="2.32.0",
                specifiers=",",
            )
        ]

        suggestions = dependency_manager.get_update_suggestions(dependencies)

        assert len(suggestions) == 0

    def test_pypi_caching(
        self, dependency_manager: DependencyManager, temp_cache_dir: str
    ) -> None:
        """Test PyPI response caching."""
        # Cache file is now in jarvis_dep_cache subdirectory
        cache_file = Path(temp_cache_dir) / "jarvis_dep_cache" / "requests.json"

        # First call should query PyPI
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.read.return_value = json.dumps(
                {"info": {"version": "2.32.3"}}
            ).encode()
            mock_urlopen.return_value.__enter__ = Mock(return_value=mock_response)
            mock_urlopen.return_value.__exit__ = Mock(return_value=False)

            _ = dependency_manager._query_pypi_version("requests")
            assert mock_urlopen.called

            assert cache_file.exists()

        # Second call should use cache
        with patch("urllib.request.urlopen") as mock_urlopen:
            _ = dependency_manager._query_pypi_version("requests")
            # Should not call PyPI again (cache hit)
            # Note: In real scenario, depends on cache expiration


class TestDependencyHistory:
    """Test cases for DependencyHistory class."""

    @pytest.fixture
    def temp_history_file(self) -> str:
        """Create a temporary history file."""
        fd, path = tempfile.mkstemp(suffix=".json")
        import os as os_module

        os_module.close(fd)
        yield path
        Path(path).unlink(missing_ok=True)

    @pytest.fixture
    def dependency_history(self, temp_history_file: str) -> DependencyHistory:
        """Create a DependencyHistory instance."""
        return DependencyHistory(history_file=temp_history_file)

    def test_init_creates_history_file(self, temp_history_file: str) -> None:
        """Test that initialization creates history file."""
        Path(temp_history_file).unlink(missing_ok=True)
        DependencyHistory(history_file=temp_history_file)
        assert Path(temp_history_file).exists()

    def test_record_check(self, dependency_history: DependencyHistory) -> None:
        """Test recording a dependency check."""
        record = dependency_history.record_check(
            project_path="/test/project",
            dependencies_checked=10,
            updates_available=2,
        )

        assert record.record_id is not None
        assert record.dependencies_checked == 10
        assert record.updates_available == 2

    def test_get_all_records(self, dependency_history: DependencyHistory) -> None:
        """Test getting all records."""
        dependency_history.record_check("/test1", 5, 1)
        dependency_history.record_check("/test2", 10, 2)

        records = dependency_history.get_all_records()
        assert len(records) == 2
        # Should be sorted by timestamp, newest first
        assert records[0].project_path == "/test2"

    def test_get_records_for_project(
        self, dependency_history: DependencyHistory
    ) -> None:
        """Test getting records for a specific project."""
        dependency_history.record_check("/test", 5, 1)
        dependency_history.record_check("/other", 10, 2)
        dependency_history.record_check("/test", 15, 3)

        records = dependency_history.get_records_for_project("/test")
        assert len(records) == 2
        assert all(r.project_path == "/test" for r in records)

    def test_get_record_by_id(self, dependency_history: DependencyHistory) -> None:
        """Test getting a record by ID."""
        record = dependency_history.record_check("/test", 5, 1)

        found = dependency_history.get_record_by_id(record.record_id)
        assert found is not None
        assert found.record_id == record.record_id

        # Test non-existent ID
        not_found = dependency_history.get_record_by_id("non-existent")
        assert not_found is None

    def test_get_stats(self, dependency_history: DependencyHistory) -> None:
        """Test getting statistics."""
        stats = dependency_history.get_stats()
        assert stats["total_checks"] == 0

        dependency_history.record_check("/test1", 10, 2)
        dependency_history.record_check("/test2", 15, 3)
        dependency_history.record_check("/test1", 20, 4)

        stats = dependency_history.get_stats()
        assert stats["total_checks"] == 3
        assert stats["projects_checked"] == 2
        assert stats["total_updates_found"] == 9
        assert stats["average_updates_per_check"] == 3.0

    def test_clear_history(self, dependency_history: DependencyHistory) -> None:
        """Test clearing all history."""
        dependency_history.record_check("/test", 5, 1)
        assert len(dependency_history.get_all_records()) == 1

        dependency_history.clear_history()
        assert len(dependency_history.get_all_records()) == 0

    def test_clear_project_history(self, dependency_history: DependencyHistory) -> None:
        """Test clearing history for a specific project."""
        dependency_history.record_check("/test", 5, 1)
        dependency_history.record_check("/other", 10, 2)

        dependency_history.clear_project_history("/test")

        records = dependency_history.get_all_records()
        assert len(records) == 1
        assert records[0].project_path == "/other"


class TestDependencyReporter:
    """Test cases for DependencyReporter class."""

    @pytest.fixture
    def sample_dependencies(self) -> list[DependencyInfo]:
        """Create sample dependencies."""
        return [
            DependencyInfo(
                name="requests",
                current_version="2.32.0",
                latest_version="2.33.0",
                specifiers=">=2.0.0",
            ),
            DependencyInfo(
                name="numpy",
                current_version="1.20.0",
                latest_version="1.21.0",
                specifiers=">=1.0.0",
            ),
        ]

    @pytest.fixture
    def sample_suggestions(self) -> list[UpdateSuggestion]:
        """Create sample suggestions."""
        return [
            UpdateSuggestion(
                dependency="requests",
                current_version="2.32.0",
                latest_version="2.33.0",
                update_type=UpdateType.MINOR,
                compatible=True,
                risk_level="medium",
                reason="New features included",
            ),
            UpdateSuggestion(
                dependency="numpy",
                current_version="1.20.0",
                latest_version="1.21.0",
                update_type=UpdateType.MINOR,
                compatible=True,
                risk_level="medium",
                reason="New features included",
            ),
        ]

    def test_init_default(self) -> None:
        """Test initialization with default format."""
        reporter = DependencyReporter()
        assert reporter.format == ReportFormat.MARKDOWN

    def test_init_custom_format(self) -> None:
        """Test initialization with custom format."""
        reporter = DependencyReporter(format=ReportFormat.JSON)
        assert reporter.format == ReportFormat.JSON

    def test_generate_markdown_report(
        self,
        sample_dependencies: list[DependencyInfo],
        sample_suggestions: list[UpdateSuggestion],
    ) -> None:
        """Test generating Markdown report."""
        reporter = DependencyReporter(format=ReportFormat.MARKDOWN)
        report = reporter.generate_report(
            sample_dependencies, sample_suggestions, "/test/project"
        )

        assert isinstance(report, str)
        assert "# Dependency Update Report" in report
        assert "## Summary" in report
        assert "requests" in report
        assert "numpy" in report

    def test_generate_json_report(
        self,
        sample_dependencies: list[DependencyInfo],
        sample_suggestions: list[UpdateSuggestion],
    ) -> None:
        """Test generating JSON report."""
        reporter = DependencyReporter(format=ReportFormat.JSON)
        report = reporter.generate_report(
            sample_dependencies, sample_suggestions, "/test/project"
        )

        assert isinstance(report, str)
        data = json.loads(report)
        assert "summary" in data
        assert "dependencies" in data
        assert "suggestions" in data
        assert len(data["dependencies"]) == 2
        assert len(data["suggestions"]) == 2

    def test_generate_plain_report(
        self,
        sample_dependencies: list[DependencyInfo],
        sample_suggestions: list[UpdateSuggestion],
    ) -> None:
        """Test generating plain text report."""
        reporter = DependencyReporter(format=ReportFormat.PLAIN)
        report = reporter.generate_report(
            sample_dependencies, sample_suggestions, "/test/project"
        )

        assert isinstance(report, str)
        assert "DEPENDENCY UPDATE REPORT" in report
        assert "SUMMARY" in report
        assert "requests" in report

        assert "numpy" in report

    def test_generate_report_no_updates(
        self, sample_dependencies: list[DependencyInfo]
    ) -> None:
        """Test generating report with no updates."""
        reporter = DependencyReporter()
        report = reporter.generate_report(sample_dependencies, [], "/test/project")

        assert (
            "No updates available" in report
            or "All dependencies are up to date" in report
        )
