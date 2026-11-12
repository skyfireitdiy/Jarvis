# -*- coding: utf-8 -*-
"""Goal / ClearGoal 内置命令职责簇测试（NLSpec: goal-command）

覆盖：
- builtin_input_handler 的 Goal 解析：
  - 替换语义（跨消息替换，非追加）
  - 同消息多个 '<Goal>' 以换行合并为一个 goal_content
  - 移除 '<Goal>' 标记本身，保留前后文本
  - ClearGoal 清空 goal_content
  - Pin 单独出现保持追加语义（固定到消息末尾）
  - Pin 与 Goal 共存时按标记切分互不吞并（每个标记只接管自己之后到下一个命令标记之前的文本）
- history_compressor 的 format_compressed_summary / handle_history_with_summary：
  - goal_content 非空时在最前面插入 ## 🎯 当前目标 区块（置于 Pin 区块之上）
- run_loop 的 _collect_auto_complete_context：goal_content 非空时追加 🎯 当前目标
- run_loop 的 _check_auto_complete：confirm_prompt 注入 goal_content，并要求先核对目标是否达成
- session_manager 的 _build_state_data：agent_runtime 保存 goal_content
- session_manager 的 _restore_agent_state：恢复 goal_content

测试范式沿用 tests/jarvis_agent/test_complete_check_hook.py：
使用轻量对象构造 agent，再把真实方法绑定上去，避免复杂初始化。
"""
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler
from jarvis.jarvis_agent.history_compressor import HistoryCompressor
from jarvis.jarvis_agent.run_loop import AgentRunLoop
from jarvis.jarvis_agent.session_manager import SessionManager


def _make_handler_agent(**attrs):
    """构造 builtin_input_handler 所需的轻量 agent 对象"""
    ag = SimpleNamespace()
    ag.pin_content = ""
    ag.goal_content = ""
    ag.set_addon_prompt = Mock()
    ag.rules_manager = Mock()
    ag.rules_manager.loaded_rules = set()
    ag.rules_manager.load_rule = Mock(return_value=False)
    ag.rules_manager._loaded_rules = {}
    ag._last_response_content = ""
    ag.allow_savesession = False
    ag.allow_model_switch = True
    ag.auto_complete = False
    ag.non_interactive = False
    ag.need_summary = True
    ag.return_control_on_auto_complete = False
    ag.session = SimpleNamespace(prompt="", addon_prompt="")
    ag.memory_manager = Mock()
    ag.memory_manager.prepare_memory_tags_prompt = Mock(return_value="")
    ag._summarize_and_clear_history = Mock(return_value="")
    ag.clear_history = Mock()
    ag.set_addon_prompt = Mock()
    for k, v in attrs.items():
        setattr(ag, k, v)
    return ag


class TestGoalParsing:
    """builtin_input_handler 的 Goal 解析"""

    def test_goal_sets_content(self):
        """输入 '<Goal>' 目标文本 后 goal_content 被替换为目标文本"""
        agent = _make_handler_agent()
        result, need_further = builtin_input_handler("'<Goal>' 目标文本", agent)
        assert agent.goal_content == "目标文本"
        # 标记被移除，保留前后文本
        assert "'<Goal>'" not in result
        assert need_further is False

    def test_goal_replaces_previous(self):
        """再次输入 '<Goal>' 新目标 后 goal_content 被替换为新目标（旧目标不残留）"""
        agent = _make_handler_agent()
        builtin_input_handler("'<Goal>' 旧目标", agent)
        assert agent.goal_content == "旧目标"
        builtin_input_handler("'<Goal>' 新目标", agent)
        assert agent.goal_content == "新目标"
        assert "旧目标" not in agent.goal_content

    def test_goal_merges_multiple_in_same_message(self):
        """同消息多个 '<Goal>' 内容以换行合并为一个 goal_content"""
        agent = _make_handler_agent()
        builtin_input_handler("'<Goal>' 目标A\n'<Goal>' 目标B", agent)
        assert agent.goal_content == "目标A\n目标B"

    def test_goal_removes_marker_keeps_text(self):
        """移除 '<Goal>' 标记本身，保留前后文本"""
        agent = _make_handler_agent()
        result, _ = builtin_input_handler("请先做这件事\n'<Goal>' 目标文本\n然后继续", agent)
        assert "'<Goal>'" not in result
        assert "请先做这件事" in result
        assert "然后继续" in result

    def test_clear_goal_clears_content(self):
        """ClearGoal 清空 goal_content"""
        agent = _make_handler_agent()
        builtin_input_handler("'<Goal>' 目标文本", agent)
        assert agent.goal_content == "目标文本"
        result, need_further = builtin_input_handler("'<ClearGoal>'", agent)
        assert agent.goal_content == ""
        assert need_further is True  # 立即返回

    def test_pin_alone_keeps_append_semantics(self):
        """Pin 单独出现时保持现有追加语义（固定到消息末尾）"""
        agent = _make_handler_agent()
        builtin_input_handler("'<Pin>' 固定内容1", agent)
        assert agent.pin_content == "固定内容1"
        builtin_input_handler("'<Pin>' 固定内容2", agent)
        assert agent.pin_content == "固定内容1\n固定内容2"

    def test_pin_and_goal_coexist_split(self):
        """Pin 与 Goal 共存时按标记切分互不吞并"""
        agent = _make_handler_agent()
        builtin_input_handler("'<Pin>' 固定内容\n'<Goal>' 目标内容", agent)
        # Pin 只接管自己之后到下一个命令标记之前的内容
        assert agent.pin_content == "固定内容"
        # Goal 接管自己之后到消息末尾的内容
        assert agent.goal_content == "目标内容"

    def test_pin_and_goal_coexist_order_reversed(self):
        """Pin 与 Goal 共存时标记顺序无关"""
        agent = _make_handler_agent()
        builtin_input_handler("'<Goal>' 目标内容\n'<Pin>' 固定内容", agent)
        assert agent.goal_content == "目标内容"
        assert agent.pin_content == "固定内容"


class TestGoalCompression:
    """history_compressor 的 goal_content 压缩保留"""

    def _make_compressor_agent(self, **attrs):
        ag = SimpleNamespace()
        ag.pin_content = ""
        ag.goal_content = ""
        ag.recent_memories = []
        ag.start_commit = None
        ag.summary_prompt = ""
        ag._pre_compressed_summary = None
        ag._pre_compress_snapshot_count = 0
        ag._pre_compressing = False
        ag.task_list_manager = Mock()
        ag.task_list_manager.task_lists = {}
        ag.model = Mock()
        ag.model.reset = Mock()
        ag.model.get_messages = Mock(return_value=[])
        ag.memory_manager = Mock()
        ag.memory_manager._ensure_memory_prompt = Mock()
        ag.event_bus = Mock()
        ag.event_bus.emit = Mock()
        ag.session = SimpleNamespace(prompt="", addon_prompt="", clear_history=Mock())
        ag._no_tool_call_count = 0
        ag.run_input_handlers_next_turn = False
        ag._setup_system_prompt = Mock()
        ag._get_task_list_info = Mock(return_value="")
        for k, v in attrs.items():
            setattr(ag, k, v)
        return ag

    def test_format_compressed_summary_goal_on_top(self):
        """format_compressed_summary：goal_content 非空时在最前面插入 ## 🎯 当前目标 区块"""
        agent = self._make_compressor_agent()
        agent.goal_content = "当前目标ABC"
        agent.pin_content = "固定内容XYZ"
        compressor = HistoryCompressor(agent)
        result = compressor.format_compressed_summary("压缩内容")
        # goal 区块在最前面
        goal_idx = result.find("## 🎯 当前目标")
        pin_idx = result.find("## 🎯 用户的原始需求和要求")
        assert goal_idx != -1
        assert pin_idx != -1
        assert goal_idx < pin_idx  # goal 在 Pin 之上
        assert "当前目标ABC" in result

    def test_format_compressed_summary_goal_empty_no_section(self):
        """format_compressed_summary：goal_content 为空时不插入 goal 区块"""
        agent = self._make_compressor_agent()
        agent.goal_content = ""
        compressor = HistoryCompressor(agent)
        result = compressor.format_compressed_summary("压缩内容")
        assert "## 🎯 当前目标" not in result

    def test_handle_history_with_summary_goal_on_top(self):
        """handle_history_with_summary：goal_content 非空时在最前面插入 goal 区块"""
        agent = self._make_compressor_agent()
        agent.goal_content = "当前目标ABC"
        agent.pin_content = "固定内容XYZ"
        compressor = HistoryCompressor(agent)
        # 让 generate_summary 返回空，走格式化分支
        with patch.object(
            compressor, "generate_summary", return_value=""
        ) as mock_gen:
            result = compressor.handle_history_with_summary()
            mock_gen.assert_called_once()
        goal_idx = result.find("## 🎯 当前目标")
        pin_idx = result.find("## 🎯 用户的原始需求和要求")
        assert goal_idx != -1
        assert pin_idx != -1
        assert goal_idx < pin_idx
        assert "当前目标ABC" in result


class TestGoalAutoComplete:
    """run_loop 的 goal_content 完成判断"""

    def _make_run_loop_agent(self, **attrs):
        ag = SimpleNamespace()
        ag.goal_content = ""
        ag.start_commit = None
        ag.task_list_manager = Mock()
        ag.task_list_manager.task_lists = {}
        ag.auto_complete = True
        ag.non_interactive = True
        ag.need_summary = True
        ag._summary_on_complete = False
        ag.return_control_on_auto_complete = False
        ag.git_manager = None
        ag._before_complete_check_hooks = []
        ag.set_addon_prompt = Mock()
        ag._complete_task = Mock(return_value="任务总结")
        ag._call_model = Mock(return_value="<!!!YES!!!>")
        ag._no_tool_call_count = 0
        for k, v in attrs.items():
            setattr(ag, k, v)
        return ag

    def test_collect_context_includes_goal(self):
        """_collect_auto_complete_context：goal_content 非空时追加 🎯 当前目标"""
        agent = self._make_run_loop_agent()
        agent.goal_content = "完成登录功能"
        loop = AgentRunLoop(agent)
        context = loop._collect_auto_complete_context(agent)
        assert "🎯 当前目标" in context
        assert "完成登录功能" in context

    def test_collect_context_no_goal_when_empty(self):
        """_collect_auto_complete_context：goal_content 为空时不追加 goal 信息"""
        agent = self._make_run_loop_agent()
        agent.goal_content = ""
        loop = AgentRunLoop(agent)
        context = loop._collect_auto_complete_context(agent)
        assert "🎯 当前目标" not in context

    def test_check_auto_complete_confirm_prompt_includes_goal(self):
        """_check_auto_complete：confirm_prompt 注入 goal_content 并要求先核对目标"""
        agent = self._make_run_loop_agent()
        agent.goal_content = "完成登录功能"
        loop = AgentRunLoop(agent)
        # 需要 is_auto_complete 返回 True
        with patch(
            "jarvis.jarvis_agent.run_loop.is_auto_complete", return_value=True
        ):
            loop._check_auto_complete(agent, "!!!COMPLETE!!!")
        # 检查注入 LLM 的 confirm_prompt 包含 goal 与核对要求
        call_args = agent._call_model.call_args
        assert call_args is not None
        prompt = call_args[0][0]
        assert "完成登录功能" in prompt
        assert "核对当前目标是否已达成" in prompt


class TestGoalSession:
    """session_manager 的 goal_content 会话持久化"""

    def _make_session_manager(self, **attrs):
        model = Mock()
        model.platform_name.return_value = "test_platform"
        model.name.return_value = "test_model"
        model.reset = Mock()
        model.save = Mock(return_value=True)
        model.restore = Mock(return_value=True)
        agent = SimpleNamespace()
        agent.goal_content = "会话目标"
        agent.pin_content = "固定内容"
        agent._addon_prompt_skip_rounds = 0
        agent._no_tool_call_count = 0
        agent._last_response_content = ""
        agent.recent_memories = []
        agent.MAX_RECENT_MEMORIES = 10
        agent.memory_tags = set()
        agent.first = True
        agent._pre_compressed_summary = None
        agent._pre_compressing = False
        agent._pre_compress_snapshot_count = 0
        agent.secret_guard_mapping = {}
        for k, v in attrs.items():
            setattr(agent, k, v)
        sm = SessionManager(model, "test_agent")
        sm.agent = agent
        return sm

    def test_build_state_data_saves_goal(self):
        """_build_agent_state：agent_runtime 保存 goal_content"""
        sm = self._make_session_manager()
        state = sm._build_agent_state("2026-01-01T00:00:00")
        assert state["agent_runtime"]["goal_content"] == "会话目标"

    def test_restore_agent_state_restores_goal(self):
        """_restore_agent_state：恢复 goal_content"""
        sm = self._make_session_manager()
        sm.agent.goal_content = ""
        # 构造会话 meta
        meta = {
            "state": {
                "agent_runtime": {
                    "goal_content": "恢复的目标",
                    "recent_memories": [],
                    "MAX_RECENT_MEMORIES": 10,
                    "memory_tags": [],
                    "pin_content": "",
                    "pre_compressed_summary": None,
                    "pre_compressing": False,
                }
            }
        }
        with patch.object(
            sm, "_load_session_meta", return_value=meta
        ), patch.object(
            sm, "_load_session_meta", return_value=meta
        ):
            sm.last_restored_session = "test_session"
            sm._restore_agent_state()
        assert sm.agent.goal_content == "恢复的目标"
