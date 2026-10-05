# -*- coding: utf-8 -*-
"""MemoryManager.prepare_memory_context_prompt 单元测试"""

from unittest.mock import MagicMock, patch

from jarvis.jarvis_agent.memory_manager import MemoryManager
from jarvis.jarvis_memory_organizer.smart_retrieval import Memory


def _make_memory(mid: str, content: str, tags=None, mtype="project_long_term"):
    return Memory(
        id=mid,
        type=mtype,
        tags=tags or ["tag"],
        content=content,
        created_at="2026-01-01",
    )


def _make_manager():
    agent = MagicMock()
    agent.get_tool_registry.return_value = None
    return MemoryManager(agent)


class TestPrepareMemoryContextPrompt:
    """测试 prepare_memory_context_prompt 方法"""

    def test_empty_input_returns_empty(self):
        """空输入返回空字符串"""
        manager = _make_manager()
        assert manager.prepare_memory_context_prompt("") == ""
        assert manager.prepare_memory_context_prompt("   ") == ""

    def test_no_memory_dirs_returns_empty(self, monkeypatch, tmp_path):
        """记忆目录不存在时返回空字符串，不执行检索"""
        manager = _make_manager()
        # 模拟记忆目录不存在
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        result = manager.prepare_memory_context_prompt("测试任务")
        assert result == ""

    def test_no_related_memories_returns_empty(self, monkeypatch):
        """无相关记忆时返回空字符串"""
        manager = _make_manager()
        # 模拟记忆目录存在
        monkeypatch.setattr("pathlib.Path.exists", lambda self: True)
        retriever = MagicMock()
        retriever.semantic_search.return_value = []
        with patch(
            "jarvis.jarvis_memory_organizer.smart_retrieval.SmartRetriever",
            return_value=retriever,
        ):
            result = manager.prepare_memory_context_prompt("测试任务")
        assert result == ""

    def test_returns_formatted_memories(self, monkeypatch):
        """有相关记忆时返回格式化提示"""
        manager = _make_manager()
        monkeypatch.setattr("pathlib.Path.exists", lambda self: True)
        memories = [
            _make_memory(
                "m1", "项目配置：使用 pytest 进行测试", tags=["测试", "pytest"]
            ),
            _make_memory(
                "m2",
                "通用经验：代码审查要点",
                tags=["代码审查"],
                mtype="global_long_term",
            ),
        ]
        retriever = MagicMock()
        retriever.semantic_search.return_value = memories
        with patch(
            "jarvis.jarvis_memory_organizer.smart_retrieval.SmartRetriever",
            return_value=retriever,
        ):
            result = manager.prepare_memory_context_prompt("如何测试代码")
        assert "📚" in result
        assert "项目配置：使用 pytest 进行测试" in result
        assert "通用经验：代码审查要点" in result
        assert "project_long_term" in result
        assert "global_long_term" in result
        assert "测试/pytest" in result

    def test_long_content_truncated(self, monkeypatch):
        """超长记忆内容被截断到 500 字符"""
        manager = _make_manager()
        monkeypatch.setattr("pathlib.Path.exists", lambda self: True)
        long_content = "x" * 1000
        memories = [_make_memory("m1", long_content)]
        retriever = MagicMock()
        retriever.semantic_search.return_value = memories
        with patch(
            "jarvis.jarvis_memory_organizer.smart_retrieval.SmartRetriever",
            return_value=retriever,
        ):
            result = manager.prepare_memory_context_prompt("测试任务")
        assert "..." in result
        assert len(result) < 600

    def test_calls_semantic_search_with_correct_params(self, monkeypatch):
        """验证调用 semantic_search 时使用正确的参数"""
        manager = _make_manager()
        monkeypatch.setattr("pathlib.Path.exists", lambda self: True)
        retriever = MagicMock()
        retriever.semantic_search.return_value = []
        with patch(
            "jarvis.jarvis_memory_organizer.smart_retrieval.SmartRetriever",
            return_value=retriever,
        ):
            manager.prepare_memory_context_prompt("修复 bug")
        retriever.semantic_search.assert_called_once_with(
            query="修复 bug",
            memory_types=["project_long_term", "global_long_term"],
            limit=5,
        )

    def test_exception_returns_empty(self, monkeypatch):
        """检索异常时返回空字符串，不影响主流程"""
        manager = _make_manager()
        monkeypatch.setattr("pathlib.Path.exists", lambda self: True)
        with patch(
            "jarvis.jarvis_memory_organizer.smart_retrieval.SmartRetriever",
            side_effect=Exception("检索失败"),
        ):
            result = manager.prepare_memory_context_prompt("测试任务")
        assert result == ""
