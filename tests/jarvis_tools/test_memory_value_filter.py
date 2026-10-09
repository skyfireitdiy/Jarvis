# -*- coding: utf-8 -*-
"""MemoryTool 写时记忆价值过滤（_should_store_memory）单测"""

from unittest.mock import patch

from jarvis.jarvis_tools.memory import MemoryTool


def _make_tool():
    return MemoryTool()


class TestShouldStoreMemory:
    """测试 _should_store_memory 的启发式价值判断"""

    def _call(self, memory_data):
        return _make_tool()._should_store_memory(memory_data)

    def test_explicit_importance_always_kept(self):
        """显式标注 importance 时一律保留（尊重显式意图）"""
        assert self._call({"content": "好的", "importance": "low"}) is True
        assert self._call({"content": "", "importance": "high"}) is True
        assert self._call({"content": "短", "importance": "medium"}) is True

    def test_empty_content_filtered(self):
        """空内容被丢弃"""
        assert self._call({"content": ""}) is False
        assert self._call({"content": "   "}) is False

    def test_too_short_content_filtered(self):
        """过短内容（<8字符）被丢弃"""
        assert self._call({"content": "你好"}) is False
        assert self._call({"content": "收到"}) is False

    def test_polite_placeholder_filtered(self):
        """纯客套/占位内容被丢弃"""
        for phrase in [
            "好的",
            "明白",
            "收到",
            "知道了",
            "没问题",
            "谢谢",
            "ok",
            "好的好的",
        ]:
            assert self._call({"content": phrase}) is False, f"{phrase} 应被过滤"

    def test_meaningful_content_kept(self):
        """有信息量的内容保守保留"""
        assert self._call({"content": "用户偏好使用 Python 编写测试"}) is True
        assert (
            self._call(
                {"content": "修复了 pipelineStore 持久化 bug，根因是 _persist 未调用"}
            )
            is True
        )
        assert self._call({"content": "决定采用双字段正交的记忆维度设计"}) is True


class TestSaveSingleMemoryFilter:
    """测试 _save_single_memory 接入过滤后的行为"""

    def _call(self, memory_data):
        return _make_tool()._save_single_memory(memory_data)

    def test_filtered_returns_filtered_result(self):
        """无价值内容被过滤，返回 storage=filtered 且不落盘"""
        with patch(
            "jarvis.jarvis_tools.memory.is_enable_memory_value_filter",
            return_value=True,
        ):
            result = self._call(
                {"memory_type": "project", "nature": "long_term", "content": "好的"}
            )
        assert result["storage"] == "filtered"
        assert result["memory_id"] is None

    def test_meaningful_saved(self):
        """有价值内容正常保存落盘"""
        with patch(
            "jarvis.jarvis_tools.memory.is_enable_memory_value_filter",
            return_value=True,
        ):
            result = self._call(
                {
                    "memory_type": "project",
                    "nature": "long_term",
                    "content": "用户偏好使用 Python 编写测试",
                }
            )
        assert result.get("storage") != "filtered"
        assert result["memory_id"] is not None

    def test_filter_disabled_saves_all(self):
        """过滤关闭时，即使内容无价值也保存"""
        with patch(
            "jarvis.jarvis_tools.memory.is_enable_memory_value_filter",
            return_value=False,
        ):
            result = self._call(
                {"memory_type": "project", "nature": "long_term", "content": "好的"}
            )
        assert result.get("storage") != "filtered"
        assert result["memory_id"] is not None
