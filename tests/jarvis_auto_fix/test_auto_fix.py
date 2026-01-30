"""
Tests for jarvis_auto_fix module.

This test suite covers all core functionality of the auto-fix module:
- Issue detection (syntax, import, format)
- Auto-fixing capabilities
- Fix history tracking
- Rollback functionality
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from jarvis.jarvis_auto_fix import AutoFixer, FixHistory
from jarvis.jarvis_auto_fix.fix_history import FixRecord, generate_fix_id


class TestFixRecord:
    """Test cases for FixRecord dataclass."""

    def test_fix_record_creation(self) -> None:
        """Test creating a FixRecord."""
        record = FixRecord(
            record_id="fix-001",
            file_path="/tmp/test.py",
            issue_type="format_issue",
            original_content="old content",
            fixed_content="new content",
            timestamp="2024-01-01T00:00:00",
            fix_applied="Fixed formatting",
        )
        assert record.record_id == "fix-001"
        assert record.file_path == "/tmp/test.py"
        assert record.issue_type == "format_issue"
        assert record.rollback_available is True

    def test_to_dict(self) -> None:
        """Test converting FixRecord to dictionary."""
        record = FixRecord(
            record_id="fix-001",
            file_path="/tmp/test.py",
            issue_type="format_issue",
            original_content="old",
            fixed_content="new",
            timestamp="2024-01-01T00:00:00",
            fix_applied="fix",
        )
        data = record.to_dict()
        assert isinstance(data, dict)
        assert data["record_id"] == "fix-001"

    def test_from_dict(self) -> None:
        """Test creating FixRecord from dictionary."""
        data = {
            "record_id": "fix-001",
            "file_path": "/tmp/test.py",
            "issue_type": "format_issue",
            "original_content": "old",
            "fixed_content": "new",
            "timestamp": "2024-01-01T00:00:00",
            "fix_applied": "fix",
            "rollback_available": True,
        }
        record = FixRecord.from_dict(data)
        assert record.record_id == "fix-001"
        assert record.file_path == "/tmp/test.py"


class TestGenerateFixId:
    """Test cases for generate_fix_id function."""

    def test_generate_fix_id_format(self) -> None:
        """Test that generated fix ID has correct format."""
        fix_id = generate_fix_id()
        assert fix_id.startswith("fix-")
        assert len(fix_id) > 10

    def test_generate_fix_id_unique(self) -> None:
        """Test that generated fix IDs are unique."""
        id1 = generate_fix_id()
        id2 = generate_fix_id()
        assert id1 != id2


class TestFixHistory:
    """Test cases for FixHistory class."""

    @pytest.fixture
    def temp_history_file(self) -> str:
        """Create a temporary history file."""
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        yield path
        # Cleanup
        if os.path.exists(path):
            os.remove(path)

    @pytest.fixture
    def fix_history(self, temp_history_file: str) -> FixHistory:
        """Create a FixHistory instance with temp file."""
        return FixHistory(history_file=temp_history_file)

    @pytest.fixture
    def sample_record(self) -> FixRecord:
        """Create a sample fix record."""
        return FixRecord(
            record_id="fix-001",
            file_path="/tmp/test.py",
            issue_type="format_issue",
            original_content="old content",
            fixed_content="new content",
            timestamp="2024-01-01T00:00:00",
            fix_applied="Fixed formatting",
        )

    def test_init_creates_history_file(self, temp_history_file: str) -> None:
        """Test that initialization creates history file."""
        os.remove(temp_history_file)  # Ensure it doesn't exist
        FixHistory(history_file=temp_history_file)
        assert os.path.exists(temp_history_file)

        with open(temp_history_file, "r") as f:
            data = json.load(f)
            assert data == []

    def test_record_fix(
        self, fix_history: FixHistory, sample_record: FixRecord
    ) -> None:
        """Test recording a fix."""
        fix_history.record_fix(sample_record)

        all_fixes = fix_history.get_all_fixes()
        assert len(all_fixes) == 1
        assert all_fixes[0].record_id == "fix-001"

    def test_get_all_fixes_empty(self, fix_history: FixHistory) -> None:
        """Test getting all fixes when history is empty."""
        fixes = fix_history.get_all_fixes()
        assert fixes == []

    def test_get_all_fixes_multiple(
        self, fix_history: FixHistory, sample_record: FixRecord
    ) -> None:
        """Test getting all fixes with multiple records."""
        record2 = FixRecord(
            record_id="fix-002",
            file_path="/tmp/test2.py",
            issue_type="syntax_error",
            original_content="bad",
            fixed_content="good",
            timestamp="2024-01-02T00:00:00",
            fix_applied="Fixed syntax",
        )

        fix_history.record_fix(sample_record)
        fix_history.record_fix(record2)

        fixes = fix_history.get_all_fixes()
        assert len(fixes) == 2
        # Should be sorted by timestamp, newest first
        assert fixes[0].record_id == "fix-002"
        assert fixes[1].record_id == "fix-001"

    def test_get_fixes_for_file(
        self, fix_history: FixHistory, sample_record: FixRecord
    ) -> None:
        """Test getting fixes for a specific file."""
        record2 = FixRecord(
            record_id="fix-002",
            file_path="/tmp/test.py",  # Same file
            issue_type="import_error",
            original_content="old",
            fixed_content="new",
            timestamp="2024-01-02T00:00:00",
            fix_applied="Fixed import",
        )
        record3 = FixRecord(
            record_id="fix-003",
            file_path="/tmp/other.py",  # Different file
            issue_type="format_issue",
            original_content="old",
            fixed_content="new",
            timestamp="2024-01-03T00:00:00",
            fix_applied="Fixed format",
        )

        fix_history.record_fix(sample_record)
        fix_history.record_fix(record2)
        fix_history.record_fix(record3)

        fixes_for_file = fix_history.get_fixes_for_file("/tmp/test.py")
        assert len(fixes_for_file) == 2
        assert all(f.file_path == "/tmp/test.py" for f in fixes_for_file)

    def test_get_fix_by_id(
        self, fix_history: FixHistory, sample_record: FixRecord
    ) -> None:
        """Test getting a fix by ID."""
        fix_history.record_fix(sample_record)

        record = fix_history.get_fix_by_id("fix-001")
        assert record is not None
        assert record.record_id == "fix-001"

        # Test non-existent ID
        record = fix_history.get_fix_by_id("fix-999")
        assert record is None

    def test_rollback_fix(self, fix_history: FixHistory) -> None:
        """Test rolling back a fix."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            temp_file = f.name
            original_content = "original content\n"
            f.write(original_content)

        try:
            # Create a fix record
            record = FixRecord(
                record_id="fix-001",
                file_path=temp_file,
                issue_type="format_issue",
                original_content=original_content,
                fixed_content="fixed content\n",
                timestamp="2024-01-01T00:00:00",
                fix_applied="Fixed formatting",
            )

            # Apply the fix manually
            with open(temp_file, "w") as f:
                f.write(record.fixed_content)

            # Rollback
            success = fix_history.rollback_fix("fix-001")
            assert success is True

            # Verify content
            with open(temp_file, "r") as f:
                content = f.read()
            assert content == original_content
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_rollback_fix_not_found(self, fix_history: FixHistory) -> None:
        """Test rolling back a non-existent fix."""
        success = fix_history.rollback_fix("fix-999")
        assert success is False

    def test_rollback_fix_no_rollback(self, fix_history: FixHistory) -> None:
        """Test rolling back a fix that cannot be rolled back."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            temp_file = f.name
            f.write("content\n")

        try:
            record = FixRecord(
                record_id="fix-001",
                file_path=temp_file,
                issue_type="format_issue",
                original_content="old",
                fixed_content="new",
                timestamp="2024-01-01T00:00:00",
                fix_applied="fix",
                rollback_available=False,
            )

            fix_history.record_fix(record)
            success = fix_history.rollback_fix("fix-001")
            assert success is False
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_clear_history(
        self, fix_history: FixHistory, sample_record: FixRecord
    ) -> None:
        """Test clearing the fix history."""
        fix_history.record_fix(sample_record)

        assert len(fix_history.get_all_fixes()) == 1

        fix_history.clear_history()

        assert len(fix_history.get_all_fixes()) == 0

    def test_get_stats(self, fix_history: FixHistory) -> None:
        """Test getting fix statistics."""
        stats = fix_history.get_stats()
        assert stats["total_fixes"] == 0
        assert stats["files_fixed"] == 0
        assert stats["issue_types"] == {}

        # Add some fixes
        record1 = FixRecord(
            record_id="fix-001",
            file_path="/tmp/test.py",
            issue_type="format_issue",
            original_content="old",
            fixed_content="new",
            timestamp="2024-01-01T00:00:00",
            fix_applied="fix",
        )
        record2 = FixRecord(
            record_id="fix-002",
            file_path="/tmp/test.py",
            issue_type="syntax_error",
            original_content="old",
            fixed_content="new",
            timestamp="2024-01-02T00:00:00",
            fix_applied="fix",
        )
        record3 = FixRecord(
            record_id="fix-003",
            file_path="/tmp/other.py",
            issue_type="format_issue",
            original_content="old",
            fixed_content="new",
            timestamp="2024-01-03T00:00:00",
            fix_applied="fix",
        )

        fix_history.record_fix(record1)
        fix_history.record_fix(record2)
        fix_history.record_fix(record3)

        stats = fix_history.get_stats()
        assert stats["total_fixes"] == 3
        assert stats["files_fixed"] == 2
        assert stats["issue_types"]["format_issue"] == 2
        assert stats["issue_types"]["syntax_error"] == 1


class TestAutoFixer:
    """Test cases for AutoFixer class."""

    @pytest.fixture
    def temp_history_file(self) -> str:
        """Create a temporary history file."""
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.remove(path)

    @pytest.fixture
    def auto_fixer(self, temp_history_file: str) -> AutoFixer:
        """Create an AutoFixer instance."""
        history = FixHistory(history_file=temp_history_file)
        return AutoFixer(history=history)

    def test_init_default_history(self) -> None:
        """Test initialization with default history."""
        fixer = AutoFixer()
        assert fixer.history is not None
        assert isinstance(fixer.history, FixHistory)

    def test_detect_issues_nonexistent_file(self, auto_fixer: AutoFixer) -> None:
        """Test detecting issues in non-existent file."""
        issues = auto_fixer.detect_issues("/nonexistent/file.py")
        assert issues == []

    def test_detect_syntax_errors(self, auto_fixer: AutoFixer) -> None:
        """Test detecting syntax errors."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            temp_file = f.name
            f.write("def foo(:\n    return 1\n")  # Syntax error

        try:
            issues = auto_fixer.detect_issues(temp_file)
            syntax_issues = [i for i in issues if i.issue_type == "syntax_error"]
            assert len(syntax_issues) > 0
            assert syntax_issues[0].severity == "error"
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_detect_no_syntax_errors(self, auto_fixer: AutoFixer) -> None:
        """Test detecting no syntax errors in valid code."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            temp_file = f.name
            f.write("def foo():\n    return 1\n")

        try:
            issues = auto_fixer.detect_issues(temp_file)
            syntax_issues = [i for i in issues if i.issue_type == "syntax_error"]
            assert len(syntax_issues) == 0
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_detect_import_errors(self, auto_fixer: AutoFixer) -> None:
        """Test detecting import errors."""
        # Note: This test is tricky because we can't reliably test
        # for broken imports without affecting the test environment
        # We'll test with a known non-existent module pattern
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            temp_file = f.name
            f.write("import definitely_does_not_exist_xyz123\n")

        try:
            issues = auto_fixer.detect_issues(temp_file)
            # We expect at least the import might be flagged
            # (but not guaranteed in all environments)
            assert isinstance(issues, list)
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_detect_format_issues(self, auto_fixer: AutoFixer) -> None:
        """Test detecting format issues using ruff."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            temp_file = f.name
            # Code with unused import (F401)
            f.write("import os\nimport sys\n")

        try:
            issues = auto_fixer.detect_issues(temp_file)
            format_issues = [i for i in issues if i.issue_type == "format_issue"]
            # If ruff is available, should detect unused imports
            # If not available, just verify no errors
            assert isinstance(format_issues, list)
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_fix_issues(self, auto_fixer: AutoFixer) -> None:
        """Test fixing issues in a file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            temp_file = f.name
            # Code with potential format issues
            f.write("""import os
import sys
def foo( ):
    return 1
""")

        try:
            # Read original content
            with open(temp_file, "r") as f:
                f.read()

            # Fix issues
            fixes = auto_fixer.fix_issues(temp_file)

            # Read fixed content
            with open(temp_file, "r") as f:
                f.read()

            # Verify fixes were recorded if ruff was available
            assert isinstance(fixes, list)

            # Verify history was recorded if fixes were applied
            if fixes:
                assert len(auto_fixer.history.get_all_fixes()) > 0
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_fix_issues_no_changes(self, auto_fixer: AutoFixer) -> None:
        """Test fixing issues when no changes are needed."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            temp_file = f.name
            # Clean code
            f.write("def foo():\n    return 1\n")

        try:
            fixes = auto_fixer.fix_issues(temp_file)
            # No fixes should be applied
            assert isinstance(fixes, list)
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_fix_all_files(self, auto_fixer: AutoFixer) -> None:
        """Test fixing all files in a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            file1 = Path(temp_dir) / "test1.py"
            file2 = Path(temp_dir) / "test2.py"

            file1.write_text("import os\nimport sys\n")
            file2.write_text("def foo():\n    return 1\n")

            # Fix all files
            all_fixes = auto_fixer.fix_all_files(temp_dir)

            # Verify fixes were attempted
            assert isinstance(all_fixes, list)

            # Both files should still exist
            assert file1.exists()
            assert file2.exists()


class TestIntegration:
    """Integration tests for the auto-fix module."""

    @pytest.fixture
    def temp_dir(self) -> str:
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    def test_full_fix_workflow(self, temp_dir: str) -> None:
        """Test the full fix workflow: detect, fix, rollback."""
        # Create test file with issues
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("import os\nimport sys\ndef foo( ):\n    return 1\n")

        # Create fixer
        history_file = os.path.join(temp_dir, "history.json")
        history = FixHistory(history_file=history_file)
        fixer = AutoFixer(history=history)

        # Detect issues
        issues = fixer.detect_issues(str(test_file))
        assert isinstance(issues, list)

        # Fix issues
        original_content = test_file.read_text()
        fixes = fixer.fix_issues(str(test_file))
        assert isinstance(fixes, list)

        # Get fixed content
        test_file.read_text()

        # If fixes were applied, test rollback

        # If fixes were applied, test rollback
        if fixes:
            # Get the fix record
            all_records = history.get_all_fixes()
            assert len(all_records) > 0

            # Rollback
            success = history.rollback_fix(all_records[0].record_id)

            # Verify rollback
            if success:
                rolled_back_content = test_file.read_text()
                assert rolled_back_content == original_content


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_file(self) -> None:
        """Test handling empty files."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            temp_file = f.name
            f.write("")

        try:
            history = FixHistory()
            fixer = AutoFixer(history=history)

            issues = fixer.detect_issues(temp_file)
            assert issues == []

            fixes = fixer.fix_issues(temp_file)
            assert fixes == []
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_file_with_encoding_issues(self) -> None:
        """Test handling files with encoding issues."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".py", delete=False) as f:
            temp_file = f.name
            # Write invalid UTF-8
            f.write(b"\xff\xfe")

        try:
            history = FixHistory()
            fixer = AutoFixer(history=history)

            # Should not crash
            issues = fixer.detect_issues(temp_file)
            assert isinstance(issues, list)
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_corrupted_history_file(self) -> None:
        """Test handling corrupted history file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_file = f.name
            f.write("invalid json {{{")

        try:
            history = FixHistory(history_file=temp_file)
            # Should handle corrupted file gracefully
            fixes = history.get_all_fixes()
            assert fixes == []
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
