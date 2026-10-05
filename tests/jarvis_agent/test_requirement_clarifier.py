# -*- coding: utf-8 -*-
"""需求澄清模块单元测试"""

from unittest.mock import MagicMock, patch

from jarvis.jarvis_agent.requirement_clarifier import (
    build_clarification_prompt,
    detect_ambiguous_requirement,
)


class TestDetectAmbiguousRequirement:
    """测试 detect_ambiguous_requirement 函数"""

    def test_clear_requirement_with_file_path(self):
        """包含文件路径的明确需求不被判定为模糊"""
        ambiguous, reasons = detect_ambiguous_requirement(
            "给 utils.py 里的 parse_config 函数添加一个 timeout 参数"
        )
        assert not ambiguous, f"应判定为明确，但得到: {reasons}"

    def test_clear_requirement_with_specific_action(self):
        """包含具体操作的明确需求不被判定为模糊"""
        ambiguous, reasons = detect_ambiguous_requirement(
            "把 config.py 里的 MAX_RETRIES 从 3 改成 5"
        )
        assert not ambiguous, f"应判定为明确，但得到: {reasons}"

    def test_clear_english_requirement(self):
        """包含具体文件的英文需求不被判定为模糊"""
        ambiguous, reasons = detect_ambiguous_requirement(
            "Refactor the Database class in db.py to use connection pooling"
        )
        assert not ambiguous, f"应判定为明确，但得到: {reasons}"

    def test_ambiguous_short_text(self):
        """过短且无具体对象的文本被判定为模糊"""
        ambiguous, reasons = detect_ambiguous_requirement("看看这个")
        assert ambiguous
        assert len(reasons) > 0

    def test_ambiguous_vague_expression(self):
        """包含模糊表述的需求被判定为模糊"""
        ambiguous, reasons = detect_ambiguous_requirement("帮我优化一下这个函数")
        assert ambiguous
        assert any("优化一下" in r for r in reasons)

    def test_ambiguous_no_specific_object(self):
        """缺少具体对象的文本被判定为模糊"""
        ambiguous, reasons = detect_ambiguous_requirement("把代码写得更好一点")
        assert ambiguous
        assert any("缺少具体对象" in r for r in reasons)

    def test_ambiguous_pronoun(self):
        """使用模糊代词且无具体对象的文本被判定为模糊"""
        ambiguous, reasons = detect_ambiguous_requirement(
            "那个东西有点问题，你处理一下"
        )
        assert ambiguous
        assert any("模糊代词" in r for r in reasons)

    def test_ambiguous_english(self):
        """模糊的英文需求被判定为模糊"""
        ambiguous, reasons = detect_ambiguous_requirement(
            "Improve the error handling in this project"
        )
        assert ambiguous

    def test_empty_input(self):
        """空输入被判定为模糊"""
        ambiguous, reasons = detect_ambiguous_requirement("")
        assert ambiguous
        assert "空输入" in reasons

    def test_whitespace_input(self):
        """纯空白输入被判定为模糊"""
        ambiguous, _ = detect_ambiguous_requirement("   ")
        assert ambiguous

    def test_clear_requirement_with_number(self):
        """包含具体数值的需求不被判定为模糊"""
        ambiguous, _ = detect_ambiguous_requirement(
            "把 MAX_RETRIES 从 3 改成 5，然后跑一下测试"
        )
        assert not ambiguous


class TestBuildClarificationPrompt:
    """测试 build_clarification_prompt 函数"""

    def test_prompt_not_empty(self):
        """澄清提示词非空且包含关键信息"""
        prompt = build_clarification_prompt()
        assert prompt
        assert "补充" in prompt
        assert "文件" in prompt or "对象" in prompt


class TestAgentClarifyAmbiguousRequirement:
    """测试 Agent._clarify_ambiguous_requirement 方法"""

    def _make_agent(self, non_interactive=False):
        """创建一个模拟 Agent 实例（使用 object.__new__ 避免完整初始化）"""
        from jarvis.jarvis_agent import Agent

        agent = object.__new__(Agent)
        agent.non_interactive = non_interactive
        agent._multiline_input = MagicMock(return_value="")
        return agent

    def test_non_interactive_skips_clarification(self):
        """非交互模式下跳过澄清，返回原始输入"""
        agent = self._make_agent(non_interactive=True)
        result = agent._clarify_ambiguous_requirement("帮我优化一下这个函数")
        assert result == "帮我优化一下这个函数"

    def test_clear_requirement_no_clarification(self):
        """明确需求不触发澄清"""
        agent = self._make_agent()
        result = agent._clarify_ambiguous_requirement("给 utils.py 添加 timeout 参数")
        assert result == "给 utils.py 添加 timeout 参数"
        agent._multiline_input.assert_not_called()

    def test_ambiguous_requirement_triggers_clarification(self):
        """模糊需求触发澄清，用户补充后返回增强输入"""
        agent = self._make_agent()
        agent._multiline_input.return_value = "优化 parse_config 函数的性能"
        with patch(
            "jarvis.jarvis_agent.requirement_clarifier.detect_ambiguous_requirement",
            return_value=(True, ["测试原因"]),
        ):
            result = agent._clarify_ambiguous_requirement("帮我优化一下这个函数")
        assert "[补充信息]" in result
        assert "优化 parse_config 函数的性能" in result

    def test_user_says_continue_no_change(self):
        """用户输入'继续'时不修改原始输入"""
        agent = self._make_agent()
        agent._multiline_input.return_value = "继续"
        with patch(
            "jarvis.jarvis_agent.requirement_clarifier.detect_ambiguous_requirement",
            return_value=(True, ["测试原因"]),
        ):
            result = agent._clarify_ambiguous_requirement("帮我优化一下这个函数")
        assert result == "帮我优化一下这个函数"

    def test_exception_returns_original(self):
        """异常时返回原始输入，不影响主流程"""
        agent = self._make_agent()
        with patch(
            "jarvis.jarvis_agent.requirement_clarifier.detect_ambiguous_requirement",
            side_effect=Exception("检测失败"),
        ):
            result = agent._clarify_ambiguous_requirement("帮我优化一下这个函数")
        assert result == "帮我优化一下这个函数"
