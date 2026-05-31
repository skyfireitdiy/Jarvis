"""测试 _filter_tool_calls_from_response 方法

验证工具调用 JSON 及周围 ```json/``` 标记的过滤效果。
"""

from unittest.mock import MagicMock

import pytest

from jarvis.jarvis_agent.run_loop import AgentRunLoop


@pytest.fixture
def run_loop():
    """创建 AgentRunLoop 实例（mock agent 参数）"""
    agent = MagicMock()
    return AgentRunLoop(agent)


class TestBareJsonToolCall:
    """裸 JSON 工具调用（无 fence 包裹）"""

    def test_bare_tool_call_removed(self, run_loop):
        """裸工具调用 JSON 应被移除"""
        response = 'Some text\n{"name": "execute_script", "arguments": {"interpreter": "bash"}}\nMore text'
        result = run_loop._filter_tool_calls_from_response(response)
        assert '"name"' not in result
        assert "Some text" in result
        assert "More text" in result

    def test_non_tool_json_preserved(self, run_loop):
        """非工具调用 JSON（无 name+arguments）应保留"""
        response = 'Result: {"result": "success", "count": 5}\nDone'
        result = run_loop._filter_tool_calls_from_response(response)
        assert '"result"' in result
        assert '"count"' in result


class TestJsonFence:
    """```json ... ``` 包裹的工具调用"""

    def test_json_fence_removed(self, run_loop):
        """```json 包裹的工具调用应整体移除（包括 fence 标记）"""
        response = (
            "Text before\n"
            "```json\n"
            '{"name": "execute_script", "arguments": {"interpreter": "bash"}}\n'
            "```\n"
            "Text after"
        )
        result = run_loop._filter_tool_calls_from_response(response)
        assert "```json" not in result
        assert "```" not in result
        assert '"name"' not in result
        assert "Text before" in result
        assert "Text after" in result

    def test_plain_fence_removed(self, run_loop):
        """``` （无 json 关键字）包裹的工具调用应整体移除"""
        response = (
            "Text before\n"
            "```\n"
            '{"name": "read_code", "arguments": {"path": "test.py"}}\n'
            "```\n"
            "Text after"
        )
        result = run_loop._filter_tool_calls_from_response(response)
        assert '"name"' not in result
        assert "Text before" in result
        assert "Text after" in result

    def test_non_tool_json_fence_preserved(self, run_loop):
        """```json 包裹的非工具 JSON 应保留"""
        response = 'Result:\n```json\n{"result": "success", "count": 5}\n```\nDone'
        result = run_loop._filter_tool_calls_from_response(response)
        assert '"result"' in result
        assert '"count"' in result


class TestMultipleToolCalls:
    """多个工具调用"""

    def test_multiple_fenced_removed(self, run_loop):
        """多个 fence 包裹的工具调用应全部移除"""
        response = (
            "Start\n"
            "```json\n"
            '{"name": "tool1", "arguments": {"a": 1}}\n'
            "```\n"
            "Middle\n"
            "```\n"
            '{"name": "tool2", "arguments": {"b": 2}}\n'
            "```\n"
            "End"
        )
        result = run_loop._filter_tool_calls_from_response(response)
        assert '"name"' not in result
        assert "Start" in result
        assert "Middle" in result
        assert "End" in result

    def test_mixed_bare_and_fenced(self, run_loop):
        """裸 JSON 和 fence 包裹混合"""
        response = (
            "Start\n"
            '{"name": "tool1", "arguments": {"a": 1}}\n'
            "Middle\n"
            "```json\n"
            '{"name": "tool2", "arguments": {"b": 2}}\n'
            "```\n"
            "End"
        )
        result = run_loop._filter_tool_calls_from_response(response)
        assert '"name"' not in result
        assert "Start" in result
        assert "Middle" in result
        assert "End" in result


class TestEdgeCases:
    """边界情况"""

    def test_fence_no_close(self, run_loop):
        """只有开头 ```json 没有结尾 ```"""
        response = 'Text\n```json\n{"name": "tool1", "arguments": {"a": 1}}\nMore text'
        result = run_loop._filter_tool_calls_from_response(response)
        assert '"name"' not in result
        assert "Text" in result
        assert "More text" in result

    def test_fence_with_whitespace(self, run_loop):
        """```json 后有空白字符"""
        response = (
            "Text\n"
            "```json\n"
            "\n  \n"
            '{"name": "tool1", "arguments": {"a": 1}}\n'
            "```\n"
            "More text"
        )
        result = run_loop._filter_tool_calls_from_response(response)
        assert '"name"' not in result
        assert "Text" in result
        assert "More text" in result



    def test_excessive_newlines_cleaned(self, run_loop):
        """超过2个连续换行应被压缩为2个"""
        response = "Line1\n\n\n\n\nLine2"
        result = run_loop._filter_tool_calls_from_response(response)
        assert "\n\n\n" not in result

    def test_empty_response(self, run_loop):
        """空响应"""
        result = run_loop._filter_tool_calls_from_response("")
        assert result == ""

    def test_only_tool_call(self, run_loop):
        """整个响应只有一个工具调用"""
        response = '{"name": "tool1", "arguments": {"a": 1}}'
        result = run_loop._filter_tool_calls_from_response(response)
        assert result.strip() == ""

    def test_only_fenced_tool_call(self, run_loop):
        """整个响应只有一个 fence 包裹的工具调用"""
        response = '```json\n{"name": "tool1", "arguments": {"a": 1}}\n```'
        result = run_loop._filter_tool_calls_from_response(response)
        assert result.strip() == ""
