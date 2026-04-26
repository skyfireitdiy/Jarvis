# -*- coding: utf-8 -*-
"""jarvis_memory_organizer.memory_organizer 模块单元测试"""

import pytest
import json
from unittest.mock import patch

from jarvis.jarvis_memory_organizer.memory_organizer import MemoryOrganizer


class TestMemoryOrganizer:
    """测试 MemoryOrganizer 类"""

    @pytest.fixture
    def organizer(self):
        """创建测试用的 MemoryOrganizer 实例"""
        with patch("jarvis.jarvis_memory_organizer.memory_organizer.PlatformRegistry"):
            return MemoryOrganizer()

    def test_get_memory_files_project_type(self, organizer, temp_dir):
        """测试获取项目长期记忆文件"""
        # 创建项目记忆目录
        project_memory_dir = temp_dir / ".jarvis" / "memory"
        project_memory_dir.mkdir(parents=True)

        # 创建测试文件
        (project_memory_dir / "memory1.json").write_text('{"test": "data"}')
        (project_memory_dir / "memory2.json").write_text('{"test": "data2"}')

        with patch.object(organizer, "project_memory_dir", project_memory_dir):
            result = organizer._get_memory_files("project_long_term")
            assert len(result) == 2
            assert all(f.suffix == ".json" for f in result)

    def test_get_memory_files_global_type(self, organizer, temp_dir):
        """测试获取全局长期记忆文件"""
        # 创建全局记忆目录
        global_memory_dir = temp_dir / "memory" / "global_long_term"
        global_memory_dir.mkdir(parents=True)

        # 创建测试文件
        (global_memory_dir / "memory1.json").write_text('{"test": "data"}')

        with patch.object(organizer, "global_memory_dir", temp_dir / "memory"):
            result = organizer._get_memory_files("global_long_term")
            assert len(result) >= 1
            assert all(f.suffix == ".json" for f in result)

    def test_get_memory_files_invalid_type(self, organizer):
        """测试无效的记忆类型"""
        with pytest.raises(ValueError, match="不支持的记忆类型"):
            organizer._get_memory_files("invalid_type")

    def test_get_memory_files_nonexistent_dir(self, organizer, temp_dir):
        """测试不存在的目录"""
        with patch.object(organizer, "project_memory_dir", temp_dir / "nonexistent"):
            result = organizer._get_memory_files("project_long_term")
            assert result == []

    def test_load_memories_success(self, organizer, temp_dir):
        """测试成功加载记忆"""
        memory_dir = temp_dir / "memory"
        memory_dir.mkdir(parents=True)

        # 创建测试记忆文件
        memory1 = memory_dir / "memory1.json"
        memory1.write_text(
            json.dumps(
                {
                    "content": "Test memory 1",
                    "tags": ["test", "memory"],
                    "created_at": "2024-01-01",
                }
            )
        )

        memory2 = memory_dir / "memory2.json"
        memory2.write_text(
            json.dumps(
                {
                    "content": "Test memory 2",
                    "tags": ["test"],
                    "created_at": "2024-01-02",
                }
            )
        )

        with patch.object(
            organizer, "_get_memory_files", return_value=[memory1, memory2]
        ):
            result = organizer._load_memories("project_long_term")
            assert len(result) == 2
            assert result[0]["content"] == "Test memory 1"
            assert result[1]["content"] == "Test memory 2"

    def test_load_memories_invalid_json(self, organizer, temp_dir):
        """测试加载无效 JSON 文件"""
        memory_dir = temp_dir / "memory"
        memory_dir.mkdir(parents=True)

        invalid_file = memory_dir / "invalid.json"
        invalid_file.write_text("invalid json content")

        with patch.object(organizer, "_get_memory_files", return_value=[invalid_file]):
            result = organizer._load_memories("project_long_term")
            # 应该跳过无效文件
            assert len(result) == 0

    def test_find_overlapping_memories_basic(self, organizer):
        """测试查找重叠记忆（基本）"""
        memories = [
            {"tags": ["python", "api", "test"]},
            {"tags": ["python", "api", "web"]},
            {"tags": ["java", "api"]},
        ]

        result = organizer._find_overlapping_memories(memories, min_overlap=2)
        assert isinstance(result, dict)
        # 前两个记忆有2个重叠标签（python, api）
        assert 2 in result

    def test_find_overlapping_memories_no_overlap(self, organizer):
        """测试没有重叠的记忆"""
        memories = [
            {"tags": ["python"]},
            {"tags": ["java"]},
            {"tags": ["rust"]},
        ]

        result = organizer._find_overlapping_memories(memories, min_overlap=2)
        # 没有足够的重叠
        assert len(result) == 0 or all(len(groups) == 0 for groups in result.values())

    def test_find_overlapping_memories_high_overlap(self, organizer):
        """测试高重叠记忆"""
        memories = [
            {"tags": ["python", "api", "web", "test"]},
            {"tags": ["python", "api", "web", "frontend"]},
            {"tags": ["python", "api", "web", "backend"]},
        ]

        result = organizer._find_overlapping_memories(memories, min_overlap=3)
        # 三个记忆有3个重叠标签（python, api, web）
        assert 3 in result or 4 in result

    def test_find_overlapping_memories_empty_tags(self, organizer):
        """测试空标签的记忆"""
        memories = [
            {"tags": []},
            {"tags": []},
        ]

        result = organizer._find_overlapping_memories(memories, min_overlap=2)
        # 没有标签，不应该有重叠
        assert len(result) == 0 or all(len(groups) == 0 for groups in result.values())

    def test_find_overlapping_memories_no_tags_key(self, organizer):
        """测试没有 tags 键的记忆"""
        memories = [
            {"content": "test"},
            {"content": "test2"},
        ]

        result = organizer._find_overlapping_memories(memories, min_overlap=2)
        # 没有标签，不应该有重叠
        assert len(result) == 0 or all(len(groups) == 0 for groups in result.values())
