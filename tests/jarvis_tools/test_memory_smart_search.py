# -*- coding: utf-8 -*-
"""MemoryTool._execute_smart_search 的 token 限制单测"""

from unittest.mock import MagicMock, patch

from jarvis.jarvis_memory_organizer.smart_retrieval import Memory
from jarvis.jarvis_tools.memory import MemoryTool


def _make_memory(mid: str, content: str) -> Memory:
    return Memory(
        id=mid,
        memory_type="project",
        nature="long_term",
        tags=["tag"],
        content=content,
        created_at="2026-01-01",
    )


class TestSmartSearchTokenLimit:
    """测试 _execute_smart_search 的 token 预算筛选"""

    def _make_tool(self):
        return object.__new__(MemoryTool)

    def _patch_retriever(self, memories):
        retriever = MagicMock()
        retriever.semantic_search.return_value = memories
        return patch(
            "jarvis.jarvis_tools.memory._get_smart_retriever",
            return_value=retriever,
        )

    def test_short_memories_all_returned(self):
        """记忆内容短时全部返回，不受 token 限制影响"""
        tool = self._make_tool()
        memories = [_make_memory("m1", "短记忆一"), _make_memory("m2", "短记忆二")]
        with (
            self._patch_retriever(memories),
            patch(
                "jarvis.jarvis_tools.memory.get_max_input_token_count",
                return_value=100000,
            ),
        ):
            result = tool._execute_smart_search(
                args={}, memory_types=["project"], query="测试", limit=None
            )
        assert result["success"] is True
        assert "m1" in result["stdout"]
        assert "m2" in result["stdout"]

    def test_oversized_memory_truncated_by_token_budget(self):
        """超长记忆超出 token 预算时被截断"""
        tool = self._make_tool()
        # 第一条超长，第二条很短
        memories = [
            _make_memory("m1", "x" * 10000),
            _make_memory("m2", "短记忆"),
        ]
        with (
            self._patch_retriever(memories),
            patch(
                "jarvis.jarvis_tools.memory.get_max_input_token_count",
                return_value=100,  # 极小预算，触发 token 限制
            ),
        ):
            result = tool._execute_smart_search(
                args={}, memory_types=["project"], query="测试", limit=None
            )
        assert result["success"] is True
        # m1 超长应被截断，m2 可能因 m1 已超预算也不返回
        assert "m1" not in result["stdout"]

    def test_uses_agent_remaining_tokens(self):
        """优先使用 agent 剩余 token 计算预算"""
        tool = self._make_tool()
        memories = [_make_memory("m1", "短记忆")]
        agent = MagicMock()
        agent.model.get_remaining_token_count.return_value = 1000

        with (
            self._patch_retriever(memories),
            patch(
                "jarvis.jarvis_tools.memory.calculate_token_limit",
                return_value=500,
            ) as mock_calc,
        ):
            result = tool._execute_smart_search(
                args={"agent": agent},
                memory_types=["project"],
                query="测试",
                limit=None,
            )
        mock_calc.assert_called_once_with(1000)
        assert result["success"] is True
        assert "m1" in result["stdout"]

    def test_fallback_to_input_window(self):
        """无 agent 时回退到输入窗口的 2/3"""
        tool = self._make_tool()
        memories = [_make_memory("m1", "短记忆")]
        with (
            self._patch_retriever(memories),
            patch(
                "jarvis.jarvis_tools.memory.get_max_input_token_count",
                return_value=3000,
            ),
        ):
            result = tool._execute_smart_search(
                args={}, memory_types=["project"], query="测试", limit=None
            )
        assert result["success"] is True
        assert "m1" in result["stdout"]
