# -*- coding: utf-8 -*-
"""历史摘要/压缩职责簇测试

覆盖 Agent 类中「历史摘要/压缩」职责簇的方法：
- _validate_summary
- generate_summary
- _print_compression_summary
- _sliding_window_compression（边界补充）
- _check_and_use_pre_compressed_summary
- _format_compressed_summary
- _adaptive_compression
- _summarize_and_clear_history
- _format_summary_message

测试范式沿用 tests/jarvis_agent/test_sliding_window_compression.py：
使用 Mock 构造 agent，再把真实方法绑定上去，避免复杂初始化。
"""

from unittest.mock import Mock

import pytest

from jarvis.jarvis_agent import Agent as RealAgent


def _bind(agent, method_name):
    """把 RealAgent 上的真实方法绑定到 mock 的 agent 对象上

    重构后真实方法会委托给 self._history_compressor，因此绑定真实方法时
    需要补齐该属性；仅在确实需要时注入，避免 Mock 的自动属性掩盖
    ``self.agent.xxx`` 的委托调用（否则断言 .called 会失真）。
    """
    from jarvis.jarvis_agent.history_compressor import HistoryCompressor

    # 真实方法体内部会委托到 self._history_compressor，绑定前必须确保其存在
    agent._history_compressor = HistoryCompressor(agent)
    setattr(
        agent,
        method_name,
        getattr(RealAgent, method_name).__get__(agent, Mock),
    )
    return agent


def _make_agent(**attrs):
    """创建一个 Mock agent，并设置所需属性"""
    ag = Mock()
    # 预压缩状态相关（多数方法都会读写）
    ag._pre_compressed_summary = None
    ag._pre_compress_snapshot_count = 0
    ag._pre_compressing = False
    ag.pin_content = ""
    ag.recent_memories = []
    # Mock() 会自动生成任意属性（且为真值），这里显式置空，
    # 避免 hasattr(self, "start_commit") 恒为真导致测试失真
    ag.start_commit = None
    ag.summary_prompt = ""
    for k, v in attrs.items():
        setattr(ag, k, v)
    return ag


class TestValidateSummary:
    """_validate_summary 基础长度校验"""

    @pytest.fixture
    def agent(self):
        return _bind(_make_agent(), "_validate_summary")

    def test_empty_summary(self, agent):
        """空字符串判定失败"""
        ok, problems = agent._validate_summary("")
        assert ok is False
        assert problems == ["总结内容为空"]

    def test_too_short_summary(self, agent):
        """strip 后不足 20 字符判定失败"""
        ok, problems = agent._validate_summary("abc")
        assert ok is False
        assert problems == ["总结内容过短"]

    def test_whitespace_only_summary(self, agent):
        """纯空白 strip 后为空，判定失败"""
        ok, problems = agent._validate_summary("        ")
        assert ok is False
        # 非空字符串但 strip 后长度 < 20
        assert problems == ["总结内容过短"]

    def test_exactly_twenty_chars(self, agent):
        """刚好 20 字符判定通过"""
        summary = "a" * 20
        ok, problems = agent._validate_summary(summary)
        assert ok is True
        assert problems == []

    def test_nineteen_chars_fails(self, agent):
        """19 字符判定失败（边界）"""
        ok, problems = agent._validate_summary("a" * 19)
        assert ok is False
        assert problems == ["总结内容过短"]

    def test_normal_long_summary(self, agent):
        """正常长文本判定通过"""
        ok, problems = agent._validate_summary(
            "这是一段足够长的正常摘要内容，用于测试校验逻辑。"
        )
        assert ok is True
        assert problems == []


class TestGenerateSummary:
    """generate_summary 生成摘要"""

    @pytest.fixture
    def agent(self):
        ag = _make_agent()
        ag.summary_prompt = ""
        ag.model = Mock()
        ag.model.model_name = "test-model"
        ag.model.chat_until_success = Mock(return_value="a" * 50)
        ag.session = Mock()
        ag.session.prompt = "会话提示词"
        _bind(ag, "generate_summary")
        return ag

    def test_for_token_limit_returns_summary(self, agent):
        """for_token_limit=True 时正常返回摘要"""
        result = agent.generate_summary(for_token_limit=True)
        assert result == "a" * 50
        assert agent.model.chat_until_success.call_count == 1

    def test_token_limit_prompt_contains_session_prompt(self, agent):
        """for_token_limit=True 时 prompt 包含 session.prompt 与 SUMMARY_REQUEST_PROMPT"""
        agent.generate_summary(for_token_limit=True)
        used_prompt = agent.model.chat_until_success.call_args[0][0]
        assert "会话提示词" in used_prompt

    def test_for_token_limit_with_list_prompt(self, agent):
        """session.prompt 为多模态列表时只提取文本部分"""
        agent.session.prompt = [
            {"type": "text", "text": "文本A"},
            {"type": "image", "url": "http://x"},
            {"type": "text", "text": "文本B"},
        ]
        agent.generate_summary(for_token_limit=True)
        used_prompt = agent.model.chat_until_success.call_args[0][0]
        assert "文本A" in used_prompt
        assert "文本B" in used_prompt

    def test_task_complete_uses_summary_prompt(self, agent):
        """for_token_limit=False 时使用自定义 summary_prompt"""
        agent.summary_prompt = "自定义总结提示词内容"
        agent.generate_summary(for_token_limit=False)
        used_prompt = agent.model.chat_until_success.call_args[0][0]
        assert used_prompt == "自定义总结提示词内容"

    def test_task_complete_default_prompt_when_empty(self, agent):
        """summary_prompt 为空时使用 DEFAULT_SUMMARY_PROMPT"""
        from jarvis.jarvis_agent import DEFAULT_SUMMARY_PROMPT

        agent.summary_prompt = ""
        agent.generate_summary(for_token_limit=False)
        used_prompt = agent.model.chat_until_success.call_args[0][0]
        assert used_prompt == DEFAULT_SUMMARY_PROMPT

    def test_empty_response_returns_empty(self, agent):
        """模型返回空响应时返回空字符串且不重试"""
        agent.model.chat_until_success = Mock(return_value="")
        result = agent.generate_summary(for_token_limit=True)
        assert result == ""
        assert agent.model.chat_until_success.call_count == 1

    def test_model_none_returns_empty(self, agent):
        """model 为 None 时异常被捕获，返回空字符串"""
        agent.model = None
        result = agent.generate_summary(for_token_limit=False)
        assert result == ""

    def test_start_commit_hint_appended(self, agent):
        """存在 start_commit 时 prompt 追加 start_commit 提示"""
        agent.start_commit = "abc123"
        agent.generate_summary(for_token_limit=False)
        used_prompt = agent.model.chat_until_success.call_args[0][0]
        assert "abc123" in used_prompt
        assert "<start_commit_context>" in used_prompt


class TestPrintCompressionSummary:
    """_print_compression_summary 打印压缩摘要"""

    @pytest.fixture
    def agent(self):
        ag = _make_agent()
        ag.model = Mock()
        ag.model.model_name = "test-model"
        _bind(ag, "_print_compression_summary")
        return ag

    def test_calls_print_markdown(self, agent, monkeypatch):
        """正常路径调用 PrettyOutput.print_markdown"""
        import jarvis.jarvis_agent as mod

        called = {}
        monkeypatch.setattr(
            mod.PrettyOutput,
            "print_markdown",
            lambda *a, **k: called.setdefault("md", (a, k)),
        )
        agent._print_compression_summary("摘要内容", "滑动窗口压缩")
        assert "md" in called
        # 标题应包含压缩类型
        assert "滑动窗口压缩" in called["md"][1]["title"]

    def test_fallback_on_error(self, agent, monkeypatch):
        """print_markdown 抛异常时回退到 auto_print"""
        import jarvis.jarvis_agent as mod

        def _raise(*a, **k):
            raise RuntimeError("boom")

        printed = []
        monkeypatch.setattr(mod.PrettyOutput, "print_markdown", _raise)
        monkeypatch.setattr(
            mod.PrettyOutput, "auto_print", lambda *a, **k: printed.append(a)
        )
        agent._print_compression_summary("摘要内容", "滑动窗口压缩")
        assert len(printed) == 1
        assert "滑动窗口压缩" in printed[0][0]


class TestSlidingWindowCompressionEdge:
    """_sliding_window_compression 边界补充（基础路径已在 test_sliding_window_compression.py）"""

    @pytest.fixture
    def agent(self):
        ag = _make_agent()
        ag.model = Mock()
        _bind(ag, "_sliding_window_compression")
        _bind(ag, "_validate_summary")
        return ag

    def test_empty_history_returns_false(self, agent):
        """空历史返回 False"""
        agent.model.get_messages = Mock(return_value=[])
        assert agent._sliding_window_compression(window_size=5) is False

    def test_all_system_messages_returns_false(self, agent):
        """全部为 system 消息时返回 False"""
        agent.model.get_messages = Mock(
            return_value=[
                {"role": "system", "content": "s1"},
                {"role": "system", "content": "s2"},
            ]
        )
        assert agent._sliding_window_compression(window_size=5) is False

    def test_insufficient_messages_returns_false(self, agent):
        """非系统消息不足 window_size 时返回 False"""
        agent.model.get_messages = Mock(
            return_value=[
                {"role": "system", "content": "s"},
                {"role": "user", "content": "u1"},
                {"role": "assistant", "content": "a1"},
            ]
        )
        assert agent._sliding_window_compression(window_size=5) is False

    def test_model_without_set_messages_returns_false(self, agent):
        """model 无 set_messages 方法时返回 False"""
        # 构造足够多的消息以通过前置条件
        msgs = [{"role": "system", "content": "s"}]
        for i in range(12):
            msgs.append({"role": "user", "content": f"u{i}"})
            msgs.append({"role": "assistant", "content": f"a{i}"})
        agent.model.get_messages = Mock(return_value=msgs)
        # 用一个没有 set_messages 的 Mock 作为 temp_model
        temp_model = Mock(spec=["chat_until_success"])
        temp_model.chat_until_success = Mock(return_value="a" * 50)
        agent._create_temp_model = Mock(return_value=temp_model)
        agent._format_compressed_summary = Mock(side_effect=lambda x: x)
        agent._print_compression_summary = Mock()
        # model 本身也没有 set_messages
        del agent.model.set_messages
        assert agent._sliding_window_compression(window_size=5) is False


class TestCheckAndUsePreCompressedSummary:
    """_check_and_use_pre_compressed_summary 使用预压缩摘要"""

    @pytest.fixture
    def agent(self):
        ag = _make_agent()
        ag.model = Mock()
        _bind(ag, "_check_and_use_pre_compressed_summary")
        return ag

    def test_hit_uses_summary_and_clears_state(self, agent):
        """命中：有预压缩摘要且 model 支持 set_messages，返回 True 且状态被清空"""
        agent._pre_compressed_summary = "[历史摘要] 预压缩内容"
        agent._pre_compress_snapshot_count = 5
        agent.model.get_messages = Mock(
            return_value=[
                {"role": "system", "content": "s"},
                {"role": "user", "content": "u1"},
                {"role": "assistant", "content": "a1"},
            ]
        )
        result = agent._check_and_use_pre_compressed_summary()
        assert result is True
        assert agent.model.set_messages.called
        # 状态被清空
        assert agent._pre_compressed_summary is None
        assert agent._pre_compress_snapshot_count == 0
        assert agent._pre_compressing is False
        # 重建后的历史包含系统消息 + 压缩摘要
        new_history = agent.model.set_messages.call_args[0][0]
        assert new_history[0]["role"] == "system"
        assert new_history[1]["content"] == "[历史摘要] 预压缩内容"

    def test_miss_returns_false_and_clears_state(self, agent):
        """未命中：无预压缩摘要，返回 False 且状态被清空"""
        agent._pre_compressed_summary = None
        agent._pre_compress_snapshot_count = 3
        result = agent._check_and_use_pre_compressed_summary()
        assert result is False
        assert agent._pre_compressed_summary is None
        assert agent._pre_compress_snapshot_count == 0
        assert agent._pre_compressing is False

    def test_hit_but_no_set_messages_returns_false(self, agent):
        """命中但 model 不支持 set_messages，返回 False 且状态清空"""
        agent._pre_compressed_summary = "[历史摘要] 内容"
        agent.model.get_messages = Mock(
            return_value=[
                {"role": "system", "content": "s"},
                {"role": "user", "content": "u1"},
            ]
        )
        agent.model = Mock(spec=["get_messages"])
        agent.model.get_messages = Mock(
            return_value=[
                {"role": "system", "content": "s"},
                {"role": "user", "content": "u1"},
            ]
        )
        result = agent._check_and_use_pre_compressed_summary()
        assert result is False
        assert agent._pre_compressed_summary is None


class TestAdaptiveCompression:
    """_adaptive_compression 分支选择

    重构后 _adaptive_compression 的实现位于 HistoryCompressor，Agent 侧仅做
    委托。真实实现内部通过 ``self.agent.xxx`` 调用 Agent 上的同名委托方法
    （保持对外可覆盖语义），因此这里 mock 的是 Agent 侧的委托方法。
    """

    @pytest.fixture
    def agent(self):
        from jarvis.jarvis_agent.history_compressor import HistoryCompressor

        ag = _make_agent()
        hc = HistoryCompressor(ag)
        # 把真实实现绑定到 hc 实例，模拟 Agent 侧委托后的实际执行体
        hc.adaptive_compression = HistoryCompressor.adaptive_compression.__get__(
            hc, Mock
        )
        ag._history_compressor = hc
        return ag

    def test_uses_pre_compressed_when_hit(self, agent):
        """预压缩命中时走 True 分支，不调用滑动窗口"""
        agent._check_and_use_pre_compressed_summary = Mock(return_value=True)
        agent._sliding_window_compression = Mock(return_value=True)
        result = agent._history_compressor.adaptive_compression()
        assert result is True
        assert agent._check_and_use_pre_compressed_summary.called
        assert not agent._sliding_window_compression.called

    def test_fallback_to_sliding_window(self, agent):
        """未命中时回退到滑动窗口压缩"""
        agent._check_and_use_pre_compressed_summary = Mock(return_value=False)
        agent._sliding_window_compression = Mock(return_value=True)
        result = agent._history_compressor.adaptive_compression()
        assert result is True
        assert agent._sliding_window_compression.called
        # 回退前清理预压缩状态
        assert agent._pre_compressed_summary is None
        assert agent._pre_compressing is False

    def test_exception_returns_false(self, agent):
        """异常时返回 False 且清理状态"""
        agent._check_and_use_pre_compressed_summary = Mock(
            side_effect=RuntimeError("boom")
        )
        result = agent._history_compressor.adaptive_compression()
        assert result is False
        assert agent._pre_compressed_summary is None


class TestSummarizeAndClearHistory:
    """_summarize_and_clear_history 设置触发原因并委托"""

    @pytest.fixture
    def agent(self):
        ag = _make_agent()
        _bind(ag, "_summarize_and_clear_history")
        return ag

    def test_sets_trigger_reason_and_returns(self, agent):
        """trigger_reason 被保存且返回值来自 _handle_history_with_summary"""
        agent._history_compressor.handle_history_with_summary = Mock(
            return_value="结果摘要"
        )
        result = agent._summarize_and_clear_history(trigger_reason="手动触发")
        assert result == "结果摘要"
        assert agent._history_compressor._summary_trigger_reason == "手动触发"

    def test_default_trigger_reason(self, agent):
        """默认 trigger_reason 为「Token限制触发」"""
        agent._history_compressor.handle_history_with_summary = Mock(return_value="x")
        agent._summarize_and_clear_history()
        assert agent._history_compressor._summary_trigger_reason == "Token限制触发"


class TestFormatSummaryMessage:
    """_format_summary_message 格式化摘要消息"""

    @pytest.fixture
    def agent(self):
        ag = _make_agent()
        ag.rules_manager = Mock()
        ag.rules_manager.loaded_rules = set()
        ag._get_task_list_info = Mock(return_value="")
        _bind(ag, "_format_summary_message")
        return ag

    def test_contains_summary_title(self, agent):
        """返回内容包含摘要标题与摘要正文"""
        result = agent._format_summary_message("这是摘要正文内容")
        assert "以下是从先前对话提取的要点摘要" in result
        assert "这是摘要正文内容" in result

    def test_contains_initial_commit_when_present(self, agent):
        """存在 start_commit 时包含初始 commit 提示"""
        agent.start_commit = "deadbeef"
        result = agent._format_summary_message("摘要")
        assert "初始 Git Commit" in result
        assert "deadbeef" in result

    def test_no_commit_section_when_absent(self, agent):
        """无 start_commit 时不包含初始 commit 提示"""
        # 不设置 start_commit 属性
        result = agent._format_summary_message("摘要")
        assert "初始 Git Commit" not in result

    def test_task_list_info_appended(self, agent):
        """任务列表信息被追加到消息末尾"""
        agent._get_task_list_info = Mock(return_value="## 任务列表状态")
        result = agent._format_summary_message("摘要")
        assert "## 任务列表状态" in result


class TestFormatCompressedSummary:
    """_format_compressed_summary 格式化压缩摘要"""

    @pytest.fixture
    def agent(self):
        ag = _make_agent()
        ag.task_list_manager = Mock()
        ag.task_list_manager.task_lists = {}
        _bind(ag, "_format_compressed_summary")
        return ag

    def test_prefix(self, agent):
        """前缀为 [历史摘要]"""
        result = agent._format_compressed_summary("压缩内容")
        assert result.startswith("[历史摘要] 压缩内容")

    def test_pin_content_injected(self, agent):
        """pin_content 非空时注入用户固定内容"""
        agent.pin_content = "固定内容ABC"
        result = agent._format_compressed_summary("压缩内容")
        assert "用户的原始需求和要求" in result
        assert "固定内容ABC" in result

    def test_recent_memories_injected(self, agent):
        """recent_memories 非空时注入最近记忆"""
        agent.recent_memories = ["记忆1", "记忆2"]
        result = agent._format_compressed_summary("压缩内容")
        assert "最近记忆" in result
        assert "记忆1" in result
        assert "记忆2" in result

    def test_start_commit_injected(self, agent):
        """start_commit 非空时注入初始 commit 提示"""
        agent.start_commit = "cafe1234"
        result = agent._format_compressed_summary("压缩内容")
        assert "初始 Git Commit" in result
        assert "cafe1234" in result

    def test_no_extra_sections_when_empty(self, agent):
        """无额外信息时仅返回前缀 + 内容"""
        result = agent._format_compressed_summary("压缩内容")
        assert "用户的原始需求和要求" not in result
        assert "最近记忆" not in result
        assert "初始 Git Commit" not in result
