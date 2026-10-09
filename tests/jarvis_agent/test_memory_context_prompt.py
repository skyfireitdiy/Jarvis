# -*- coding: utf-8 -*-
"""MemoryManager.prepare_memory_context_prompt 单元测试"""

from unittest.mock import MagicMock, patch

from jarvis.jarvis_agent.memory_manager import MemoryManager
from jarvis.jarvis_memory_organizer.smart_retrieval import Memory


def _make_memory(mid: str, content: str, tags=None, mtype="project_long_term"):
    # 兼容平铺类型名（如 project_long_term / global_long_term），拆分为双字段
    if mtype.startswith("global"):
        memory_type, nature = "global", mtype.split("_", 1)[1]
    else:
        memory_type, nature = "project", mtype.split("_", 1)[1]
    return Memory(
        id=mid,
        memory_type=memory_type,
        nature=nature,
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
        assert "project/long_term" in result
        assert "global/long_term" in result
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
            memory_types=["project", "global"],
            natures=["long_term"],
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

    def test_retrieval_budget_truncation(self, monkeypatch):
        """检索结果累计 token 超过预算时截断"""
        from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA

        manager = _make_manager()
        monkeypatch.setattr("pathlib.Path.exists", lambda self: True)
        # 5 条记忆，每条 token 估算约 25（含标签与编号前缀）
        memories = [_make_memory(f"m{i}", f"记忆内容 {i}") for i in range(5)]
        retriever = MagicMock()
        retriever.semantic_search.return_value = memories
        key = "context_memory_retrieval_budget"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            # 预算 60：只够放 2 条（25×2=50），第 3 条累计 75 超预算被截断
            GLOBAL_CONFIG_DATA[key] = 60
            with patch(
                "jarvis.jarvis_memory_organizer.smart_retrieval.SmartRetriever",
                return_value=retriever,
            ):
                result = manager.prepare_memory_context_prompt("测试任务")
        finally:
            if original is None:
                GLOBAL_CONFIG_DATA.pop(key, None)
            else:
                GLOBAL_CONFIG_DATA[key] = original
        # 应只注入前 2 条，后续被截断
        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" not in result

    def test_retrieval_budget_no_truncation_when_under(self, monkeypatch):
        """检索结果未超预算时全部注入"""
        from jarvis.jarvis_utils.config import GLOBAL_CONFIG_DATA

        manager = _make_manager()
        monkeypatch.setattr("pathlib.Path.exists", lambda self: True)
        memories = [_make_memory(f"m{i}", f"记忆内容 {i}") for i in range(3)]
        retriever = MagicMock()
        retriever.semantic_search.return_value = memories
        key = "context_memory_retrieval_budget"
        original = GLOBAL_CONFIG_DATA.get(key)
        try:
            GLOBAL_CONFIG_DATA[key] = 10000  # 大预算，不截断
            with patch(
                "jarvis.jarvis_memory_organizer.smart_retrieval.SmartRetriever",
                return_value=retriever,
            ):
                result = manager.prepare_memory_context_prompt("测试任务")
        finally:
            if original is None:
                GLOBAL_CONFIG_DATA.pop(key, None)
            else:
                GLOBAL_CONFIG_DATA[key] = original
        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result
