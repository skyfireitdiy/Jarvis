"""交互历史分析器模块

分析用户交互历史，提取行为模式和偏好。
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter
import json


@dataclass
class TimePattern:
    """时间模式数据类

    记录用户的时间使用模式。
    """

    peak_hours: List[int] = field(default_factory=list)
    peak_days: List[int] = field(default_factory=list)
    average_session_duration: float = 0.0
    total_interactions: int = 0


@dataclass
class CommandPattern:
    """命令模式数据类

    记录用户的命令使用模式。
    """

    frequent_commands: List[Tuple[str, int]] = field(default_factory=list)
    command_categories: Dict[str, int] = field(default_factory=dict)
    average_command_length: float = 0.0


@dataclass
class QuestionPattern:
    """问题模式数据类

    记录用户的提问模式。
    """

    common_topics: List[Tuple[str, int]] = field(default_factory=list)
    question_types: Dict[str, int] = field(default_factory=dict)
    average_question_length: float = 0.0


@dataclass
class InteractionPattern:
    """交互模式数据类

    综合记录用户的交互行为模式。
    """

    time_pattern: TimePattern = field(default_factory=TimePattern)
    command_pattern: CommandPattern = field(default_factory=CommandPattern)
    question_pattern: QuestionPattern = field(default_factory=QuestionPattern)
    analysis_timestamp: str = ""
    data_range_start: str = ""
    data_range_end: str = ""
    confidence_score: float = 0.0


@dataclass
class WorkSchedule:
    """工作时间表数据类

    记录用户的工作时间安排。
    """

    work_start_hour: int = 9
    work_end_hour: int = 18
    work_days: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    break_hours: List[int] = field(default_factory=lambda: [12])
    productivity_hours: List[int] = field(default_factory=list)


@dataclass
class InteractionRecord:
    """交互记录数据类

    存储单次交互的信息。
    """

    timestamp: str = ""
    content: str = ""
    interaction_type: str = ""
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InteractionRecord":
        """从字典创建InteractionRecord对象"""
        return cls(
            timestamp=data.get("timestamp", data.get("created_at", "")),
            content=data.get("content", ""),
            interaction_type=data.get("type", data.get("interaction_type", "")),
            tags=data.get("tags", []),
        )


class HistoryAnalyzer:
    """交互历史分析器

    分析用户的交互历史，提取行为模式和偏好。
    """

    COMMAND_CATEGORIES: Dict[str, List[str]] = {
        "code": ["code", "function", "class", "method", "implement"],
        "test": ["test", "pytest", "unittest"],
        "refactor": ["refactor", "optimize", "improve"],
        "debug": ["debug", "error", "bug", "fix"],
        "doc": ["doc", "documentation", "comment", "readme"],
        "deploy": ["deploy", "deployment", "release"],
        "config": ["config", "configuration", "setting"],
        "search": ["search", "find", "grep"],
        "git": ["git", "commit", "branch", "merge"],
    }

    QUESTION_TYPES: Dict[str, List[str]] = {
        "how": ["how", "how to"],
        "what": ["what", "what is"],
        "why": ["why"],
        "where": ["where"],
        "when": ["when"],
        "which": ["which"],
        "debug": ["error", "fail", "not working", "problem"],
    }

    def __init__(
        self,
        project_memory_dir: Optional[Path] = None,
        global_memory_dir: Optional[Path] = None,
    ):
        """初始化历史分析器

        Args:
            project_memory_dir: 项目记忆目录
            global_memory_dir: 全局记忆目录
        """
        self.project_memory_dir = project_memory_dir or Path(".jarvis/memory")

        if global_memory_dir is None:
            try:
                from jarvis.jarvis_utils.config import get_data_dir

                self.global_memory_dir = Path(get_data_dir()) / "memory"
            except ImportError:
                self.global_memory_dir = Path.home() / ".jarvis" / "memory"
        else:
            self.global_memory_dir = global_memory_dir

        self._cached_records: Optional[List[InteractionRecord]] = None
        self._cached_pattern: Optional[InteractionPattern] = None

    def _load_memory_files(self, memory_dir: Path) -> List[Dict[str, Any]]:
        """加载记忆文件"""
        memories: List[Dict[str, Any]] = []

        if not memory_dir.exists():
            return memories

        for memory_file in memory_dir.glob("*.json"):
            try:
                with open(memory_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        memories.append(data)
            except (json.JSONDecodeError, IOError):
                continue

        return memories

    def _load_all_interactions(self) -> List[InteractionRecord]:
        """加载所有交互记录"""
        if self._cached_records is not None:
            return self._cached_records

        records: List[InteractionRecord] = []

        project_memories = self._load_memory_files(self.project_memory_dir)
        for memory in project_memories:
            records.append(InteractionRecord.from_dict(memory))

        short_term_dir = self.global_memory_dir / "short_term"
        short_term_memories = self._load_memory_files(short_term_dir)
        for memory in short_term_memories:
            records.append(InteractionRecord.from_dict(memory))

        long_term_dir = self.global_memory_dir / "global_long_term"
        long_term_memories = self._load_memory_files(long_term_dir)
        for memory in long_term_memories:
            records.append(InteractionRecord.from_dict(memory))

        self._cached_records = records
        return records

    def analyze_interactions(
        self,
        records: Optional[List[InteractionRecord]] = None,
    ) -> InteractionPattern:
        """分析交互记录，提取行为模式"""
        if records is None:
            records = self._load_all_interactions()

        if not records:
            return InteractionPattern(
                analysis_timestamp=datetime.now().isoformat(),
                confidence_score=0.0,
            )

        time_pattern = self._analyze_time_pattern(records)
        command_pattern = self._analyze_command_pattern(records)
        question_pattern = self._analyze_question_pattern(records)
        confidence = min(1.0, len(records) / 100)

        timestamps = [r.timestamp for r in records if r.timestamp]
        data_range_start = min(timestamps) if timestamps else ""
        data_range_end = max(timestamps) if timestamps else ""

        pattern = InteractionPattern(
            time_pattern=time_pattern,
            command_pattern=command_pattern,
            question_pattern=question_pattern,
            analysis_timestamp=datetime.now().isoformat(),
            data_range_start=data_range_start,
            data_range_end=data_range_end,
            confidence_score=confidence,
        )

        self._cached_pattern = pattern
        return pattern

    def _analyze_time_pattern(
        self,
        records: List[InteractionRecord],
    ) -> TimePattern:
        """分析时间模式"""
        hour_counts: Counter[int] = Counter()
        day_counts: Counter[int] = Counter()

        for record in records:
            if not record.timestamp:
                continue

            try:
                dt = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
                hour_counts[dt.hour] += 1
                day_counts[dt.weekday()] += 1
            except (ValueError, AttributeError):
                continue

        peak_hours = [hour for hour, _ in hour_counts.most_common(5)]
        peak_days = [day for day, _ in day_counts.most_common(3)]

        return TimePattern(
            peak_hours=sorted(peak_hours),
            peak_days=sorted(peak_days),
            average_session_duration=0.0,
            total_interactions=len(records),
        )

    def _analyze_command_pattern(
        self,
        records: List[InteractionRecord],
    ) -> CommandPattern:
        """分析命令模式"""
        command_counts: Counter[str] = Counter()
        category_counts: Counter[str] = Counter()
        total_length = 0
        command_count = 0

        for record in records:
            content = record.content.strip()
            if not content:
                continue

            command_key = content[:50] if len(content) > 50 else content
            command_counts[command_key] += 1

            for category, keywords in self.COMMAND_CATEGORIES.items():
                if any(kw in content.lower() for kw in keywords):
                    category_counts[category] += 1
                    break

                total_length += len(content)
            command_count += 1

        frequent_commands = command_counts.most_common(10)
        avg_length = total_length / command_count if command_count > 0 else 0.0

        return CommandPattern(
            frequent_commands=frequent_commands,
            command_categories=dict(category_counts),
            average_command_length=avg_length,
        )

    def _analyze_question_pattern(
        self,
        records: List[InteractionRecord],
    ) -> QuestionPattern:
        """分析问题模式"""
        topic_counts: Counter[str] = Counter()
        type_counts: Counter[str] = Counter()
        total_length = 0
        question_count = 0

        for record in records:
            content = record.content.strip()
            if not content:
                continue

            for tag in record.tags:
                topic_counts[tag] += 1

            for qtype, keywords in self.QUESTION_TYPES.items():
                if any(kw in content.lower() for kw in keywords):
                    type_counts[qtype] += 1
                    break

            if "?" in content:
                total_length += len(content)
                question_count += 1

        common_topics = topic_counts.most_common(10)
        avg_length = total_length / question_count if question_count > 0 else 0.0

        return QuestionPattern(
            common_topics=common_topics,
            question_types=dict(type_counts),
            average_question_length=avg_length,
        )

    def extract_patterns(
        self,
        records: Optional[List[InteractionRecord]] = None,
    ) -> Dict[str, Any]:
        """提取所有模式并返回字典格式"""
        pattern = self.analyze_interactions(records)

        return {
            "time_pattern": {
                "peak_hours": pattern.time_pattern.peak_hours,
                "peak_days": pattern.time_pattern.peak_days,
                "average_session_duration": pattern.time_pattern.average_session_duration,
                "total_interactions": pattern.time_pattern.total_interactions,
            },
            "command_pattern": {
                "frequent_commands": pattern.command_pattern.frequent_commands,
                "command_categories": pattern.command_pattern.command_categories,
                "average_command_length": pattern.command_pattern.average_command_length,
            },
            "question_pattern": {
                "common_topics": pattern.question_pattern.common_topics,
                "question_types": pattern.question_pattern.question_types,
                "average_question_length": pattern.question_pattern.average_question_length,
            },
            "metadata": {
                "analysis_timestamp": pattern.analysis_timestamp,
                "data_range_start": pattern.data_range_start,
                "data_range_end": pattern.data_range_end,
                "confidence_score": pattern.confidence_score,
            },
        }

    def get_work_schedule(
        self,
        records: Optional[List[InteractionRecord]] = None,
    ) -> WorkSchedule:
        """推断用户的工作时间表"""
        if records is None:
            records = self._load_all_interactions()

        if not records:
            return WorkSchedule()

        hour_counts: Counter[int] = Counter()
        day_counts: Counter[int] = Counter()

        for record in records:
            if not record.timestamp:
                continue

            try:
                dt = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
                hour_counts[dt.hour] += 1
                day_counts[dt.weekday()] += 1
            except (ValueError, AttributeError):
                continue

        if not hour_counts:
            return WorkSchedule()

        active_hours = [h for h, c in hour_counts.items() if c > 0]
        if active_hours:
            work_start = min(active_hours)
            work_end = max(active_hours)
        else:
            work_start = 9
            work_end = 18

        if day_counts:
            avg_count = sum(day_counts.values()) / 7
            work_days = [d for d in range(7) if day_counts.get(d, 0) >= avg_count * 0.5]
            if not work_days:
                work_days = [0, 1, 2, 3, 4]
        else:
            work_days = [0, 1, 2, 3, 4]

        if hour_counts:
            avg_hour_count = sum(hour_counts.values()) / 24
            break_hours = [
                h
                for h in range(work_start, work_end)
                if hour_counts.get(h, 0) < avg_hour_count * 0.3
            ]
        else:
            break_hours = [12]

        productivity_hours = [h for h, _ in hour_counts.most_common(3)]

        return WorkSchedule(
            work_start_hour=work_start,
            work_end_hour=work_end,
            work_days=sorted(work_days),
            break_hours=sorted(break_hours),
            productivity_hours=sorted(productivity_hours),
        )

    def get_common_commands(
        self,
        records: Optional[List[InteractionRecord]] = None,
        limit: int = 10,
    ) -> List[Tuple[str, int]]:
        """获取常用命令列表"""
        if records is None:
            records = self._load_all_interactions()

        command_counts: Counter[str] = Counter()

        for record in records:
            content = record.content.strip()
            if not content:
                continue

            command_key = content[:100] if len(content) > 100 else content
            command_counts[command_key] += 1

        return command_counts.most_common(limit)

    def clear_cache(self) -> None:
        """清除缓存数据"""
        self._cached_records = None
        self._cached_pattern = None
