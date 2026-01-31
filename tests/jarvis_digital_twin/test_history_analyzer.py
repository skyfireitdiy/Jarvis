"""HistoryAnalyzer测试模块"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pytest

from jarvis.jarvis_digital_twin.user_profile.history_analyzer import (
    CommandPattern,
    HistoryAnalyzer,
    InteractionPattern,
    InteractionRecord,
    QuestionPattern,
    TimePattern,
    WorkSchedule,
)


class TestTimePattern:
    """TimePattern数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        pattern = TimePattern()
        assert pattern.peak_hours == []
        assert pattern.peak_days == []
        assert pattern.average_session_duration == 0.0
        assert pattern.total_interactions == 0

    def test_custom_values(self) -> None:
        """测试自定义值"""
        pattern = TimePattern(
            peak_hours=[9, 10, 14],
            peak_days=[0, 1, 2],
            average_session_duration=30.5,
            total_interactions=100,
        )
        assert pattern.peak_hours == [9, 10, 14]
        assert pattern.peak_days == [0, 1, 2]
        assert pattern.average_session_duration == 30.5
        assert pattern.total_interactions == 100


class TestCommandPattern:
    """CommandPattern数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        pattern = CommandPattern()
        assert pattern.frequent_commands == []
        assert pattern.command_categories == {}
        assert pattern.average_command_length == 0.0

    def test_custom_values(self) -> None:
        """测试自定义值"""
        pattern = CommandPattern(
            frequent_commands=[("test", 10), ("build", 5)],
            command_categories={"code": 20, "test": 15},
            average_command_length=45.5,
        )
        assert len(pattern.frequent_commands) == 2
        assert pattern.command_categories["code"] == 20


class TestQuestionPattern:
    """QuestionPattern数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        pattern = QuestionPattern()
        assert pattern.common_topics == []
        assert pattern.question_types == {}
        assert pattern.average_question_length == 0.0


class TestInteractionPattern:
    """InteractionPattern数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        pattern = InteractionPattern()
        assert isinstance(pattern.time_pattern, TimePattern)
        assert isinstance(pattern.command_pattern, CommandPattern)
        assert isinstance(pattern.question_pattern, QuestionPattern)
        assert pattern.confidence_score == 0.0


class TestWorkSchedule:
    """WorkSchedule数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        schedule = WorkSchedule()
        assert schedule.work_start_hour == 9
        assert schedule.work_end_hour == 18
        assert schedule.work_days == [0, 1, 2, 3, 4]
        assert schedule.break_hours == [12]

    def test_custom_values(self) -> None:
        """测试自定义值"""
        schedule = WorkSchedule(
            work_start_hour=8,
            work_end_hour=20,
            work_days=[0, 1, 2, 3, 4, 5],
            break_hours=[12, 18],
            productivity_hours=[9, 10, 14],
        )
        assert schedule.work_start_hour == 8
        assert schedule.work_end_hour == 20
        assert 5 in schedule.work_days


class TestInteractionRecord:
    """InteractionRecord数据类测试"""

    def test_default_values(self) -> None:
        """测试默认值"""
        record = InteractionRecord()
        assert record.timestamp == ""
        assert record.content == ""
        assert record.interaction_type == ""
        assert record.tags == []

    def test_from_dict(self) -> None:
        """测试从字典创建"""
        data = {
            "timestamp": "2024-01-15T10:30:00",
            "content": "test content",
            "type": "command",
            "tags": ["test", "code"],
        }
        record = InteractionRecord.from_dict(data)
        assert record.timestamp == "2024-01-15T10:30:00"
        assert record.content == "test content"
        assert record.interaction_type == "command"
        assert "test" in record.tags

    def test_from_dict_with_created_at(self) -> None:
        """测试从字典创建（使用created_at字段）"""
        data = {
            "created_at": "2024-01-15T10:30:00",
            "content": "test content",
        }
        record = InteractionRecord.from_dict(data)
        assert record.timestamp == "2024-01-15T10:30:00"


class TestHistoryAnalyzer:
    """HistoryAnalyzer类测试"""

    @pytest.fixture
    def temp_memory_dir(self) -> Path:
        """创建临时记忆目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def analyzer(self, temp_memory_dir: Path) -> HistoryAnalyzer:
        """创建分析器实例"""
        return HistoryAnalyzer(
            project_memory_dir=temp_memory_dir / "project",
            global_memory_dir=temp_memory_dir / "global",
        )

    @pytest.fixture
    def sample_records(self) -> List[InteractionRecord]:
        """创建示例记录"""
        base_time = datetime(2024, 1, 15, 10, 0, 0)
        records = []
        for i in range(20):
            dt = base_time + timedelta(hours=i % 12, days=i % 5)
            records.append(
                InteractionRecord(
                    timestamp=dt.isoformat(),
                    content=f"test command {i}",
                    interaction_type="command",
                    tags=["test", f"tag{i % 3}"],
                )
            )
        return records

    def test_init_default(self) -> None:
        """测试默认初始化"""
        analyzer = HistoryAnalyzer()
        assert analyzer.project_memory_dir == Path(".jarvis/memory")

    def test_init_custom_dirs(self, temp_memory_dir: Path) -> None:
        """测试自定义目录初始化"""
        analyzer = HistoryAnalyzer(
            project_memory_dir=temp_memory_dir / "project",
            global_memory_dir=temp_memory_dir / "global",
        )
        assert analyzer.project_memory_dir == temp_memory_dir / "project"
        assert analyzer.global_memory_dir == temp_memory_dir / "global"

    def test_analyze_interactions_empty(self, analyzer: HistoryAnalyzer) -> None:
        """测试空记录分析"""
        pattern = analyzer.analyze_interactions([])
        assert pattern.confidence_score == 0.0
        assert pattern.time_pattern.total_interactions == 0

    def test_analyze_interactions_with_records(
        self, analyzer: HistoryAnalyzer, sample_records: List[InteractionRecord]
    ) -> None:
        """测试有记录的分析"""
        pattern = analyzer.analyze_interactions(sample_records)
        assert pattern.confidence_score > 0
        assert pattern.time_pattern.total_interactions == 20
        assert len(pattern.time_pattern.peak_hours) > 0

    def test_extract_patterns(
        self, analyzer: HistoryAnalyzer, sample_records: List[InteractionRecord]
    ) -> None:
        """测试提取模式"""
        patterns = analyzer.extract_patterns(sample_records)
        assert "time_pattern" in patterns
        assert "command_pattern" in patterns
        assert "question_pattern" in patterns
        assert "metadata" in patterns

    def test_get_work_schedule_empty(self, analyzer: HistoryAnalyzer) -> None:
        """测试空记录的工作时间表"""
        schedule = analyzer.get_work_schedule([])
        assert schedule.work_start_hour == 9
        assert schedule.work_end_hour == 18

    def test_get_work_schedule_with_records(
        self, analyzer: HistoryAnalyzer, sample_records: List[InteractionRecord]
    ) -> None:
        """测试有记录的工作时间表"""
        schedule = analyzer.get_work_schedule(sample_records)
        assert isinstance(schedule, WorkSchedule)
        assert len(schedule.productivity_hours) > 0

    def test_get_common_commands(
        self, analyzer: HistoryAnalyzer, sample_records: List[InteractionRecord]
    ) -> None:
        """测试获取常用命令"""
        commands = analyzer.get_common_commands(sample_records, limit=5)
        assert len(commands) <= 5
        assert all(isinstance(c, tuple) and len(c) == 2 for c in commands)

    def test_clear_cache(self, analyzer: HistoryAnalyzer) -> None:
        """测试清除缓存"""
        analyzer._cached_records = []
        analyzer._cached_pattern = InteractionPattern()
        analyzer.clear_cache()
        assert analyzer._cached_records is None
        assert analyzer._cached_pattern is None

    def test_load_memory_files_nonexistent(self, analyzer: HistoryAnalyzer) -> None:
        """测试加载不存在的目录"""
        memories = analyzer._load_memory_files(Path("/nonexistent/path"))
        assert memories == []

    def test_load_memory_files_with_data(
        self, analyzer: HistoryAnalyzer, temp_memory_dir: Path
    ) -> None:
        """测试加载有数据的目录"""
        memory_dir = temp_memory_dir / "test_memories"
        memory_dir.mkdir(parents=True)

        memory_data = {
            "content": "test memory",
            "tags": ["test"],
            "created_at": "2024-01-15T10:00:00",
        }
        with open(memory_dir / "test.json", "w") as f:
            json.dump(memory_data, f)

        memories = analyzer._load_memory_files(memory_dir)
        assert len(memories) == 1
        assert memories[0]["content"] == "test memory"
