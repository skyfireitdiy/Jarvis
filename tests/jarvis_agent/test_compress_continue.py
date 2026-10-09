# -*- coding: utf-8 -*-
"""全量压缩后强制继续标志测试（issue #86）

背景：单次工具调用输出过长触发全量压缩（_summarize_and_clear_history）时，
session.prompt 被清空、摘要放入 addon_prompt。若模型下一轮返回无工具调用的
纯文本，主循环会落入 _get_next_user_action 等待用户输入，导致任务中断。

修复：全量压缩成功路径设置 ag._force_continue_after_compress = True，
主循环在 _get_next_user_action 前消费该标志并 continue，使 Agent 继续执行。
"""

from unittest.mock import Mock

from jarvis.jarvis_agent.run_loop import AgentRunLoop


class _FakeSession:
    """最小 Session 替身：仅暴露压缩路径所需属性"""

    def __init__(self):
        self.prompt = ""
        self.addon_prompt = ""


def _make_agent():
    """构造一个最小 agent mock，覆盖 check_and_compress_context 全量压缩回退路径"""
    ag = Mock()
    ag.session = _FakeSession()
    # 预压缩状态（压缩路径会读写）
    ag._pre_compressed_summary = None
    ag._pre_compress_snapshot_count = 0
    ag._pre_compressing = False
    # 压缩标志（本次修复新增）
    ag._force_continue_after_compress = False
    # 全量压缩：_adaptive_compression 失败 -> _summarize_and_clear_history 返回摘要
    ag._adaptive_compression = Mock(return_value=False)
    ag._summarize_and_clear_history = Mock(return_value="【摘要】任务进行到 X 阶段")
    return ag


def _make_model():
    """构造一个触发 token 压缩的 model mock"""
    model = Mock()
    model.get_conversation_turn = Mock(return_value=10)
    model.get_remaining_token_count = Mock(return_value=100)
    model._get_platform_max_input_token_count = Mock(return_value=2000)
    return model


def test_full_compression_sets_force_continue_flag():
    """全量压缩成功路径应设置 _force_continue_after_compress 标志"""
    ag = _make_agent()
    loop = AgentRunLoop(ag)

    loop.check_and_compress_context(model_instance=_make_model())

    # 摘要已放入 addon_prompt，维持上下文连续性
    assert "【摘要】" in ag.session.addon_prompt
    # 关键断言：压缩后设置了强制继续标志
    assert ag._force_continue_after_compress is True


def test_no_compression_keeps_flag_false():
    """未触发压缩时标志保持 False，不影响交互模式正常行为"""
    ag = _make_agent()
    # 剩余 token 充足，不触发压缩
    model = Mock()
    model.get_conversation_turn = Mock(return_value=1)
    model.get_remaining_token_count = Mock(return_value=1900)
    model._get_platform_max_input_token_count = Mock(return_value=2000)
    loop = AgentRunLoop(ag)

    loop.check_and_compress_context(model_instance=model)

    assert ag._force_continue_after_compress is False
    assert ag._adaptive_compression.called is False


def test_adaptive_compression_success_keeps_flag_false():
    """自适应压缩成功时不设置强制继续标志（未清空 prompt，无需强制继续）"""
    ag = _make_agent()
    ag._adaptive_compression = Mock(return_value=True)
    loop = AgentRunLoop(ag)

    loop.check_and_compress_context(model_instance=_make_model())

    assert ag._force_continue_after_compress is False
    ag._summarize_and_clear_history.assert_not_called()
