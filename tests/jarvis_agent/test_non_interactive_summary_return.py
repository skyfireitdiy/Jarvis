# -*- coding: utf-8 -*-
"""非交互模式返回任务总结（NLSpec: non-interactive-summary-return）职责簇测试

覆盖：
- set_non_interactive 的非交互总结开关（_summary_on_complete）语义：
  进入非交互模式时启用，退出时恢复；need_summary 交互语义不被破坏
- run_loop._execute_auto_complete 在非交互模式下返回 _complete_task 的
  总结结果，而非 current_response（!!!COMPLETE!!!）
- 交互模式下行为完全不变（need_summary=False 时仍返回 current_response）
- 总结失败/为空时回退「任务完成」，不抛异常阻塞主流程

测试范式沿用 tests/jarvis_agent/test_complete_check_hook.py：
使用轻量对象构造 agent，再把真实方法绑定上去，避免复杂初始化。
set_non_interactive 依赖 hasattr 首次备份语义，故用普通对象而非 Mock
（Mock 的 hasattr 恒真会破坏备份/恢复逻辑）。
"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from jarvis.jarvis_agent import Agent as RealAgent
from jarvis.jarvis_agent.run_loop import AgentRunLoop


def _bind(agent, method_name):
    """把 RealAgent 上的真实方法绑定到 agent 对象上"""
    setattr(
        agent,
        method_name,
        getattr(RealAgent, method_name).__get__(agent, type(agent)),
    )
    return agent


def _make_agent(**attrs):
    """创建一个轻量 agent 对象，并设置非交互总结所需的最小属性"""
    ag = SimpleNamespace()
    ag.auto_complete = False
    ag.need_summary = True
    ag.non_interactive = False
    ag._summary_on_complete = False
    ag.session = SimpleNamespace(non_interactive=False)
    for k, v in attrs.items():
        setattr(ag, k, v)
    return ag


class TestSetNonInteractiveSummarySwitch:
    """set_non_interactive 的非交互总结开关语义"""

    def test_enter_non_interactive_enables_summary_switch(self):
        """进入非交互模式：_summary_on_complete 应被启用"""
        ag = _make_agent(need_summary=False)
        _bind(ag, "set_non_interactive")
        ag.set_non_interactive(True)
        assert ag.non_interactive is True
        assert ag._summary_on_complete is True

    def test_enter_non_interactive_keeps_need_summary_untouched(self):
        """进入非交互模式：不强制覆盖 need_summary 的原始值（交互语义不被破坏）"""
        ag = _make_agent(need_summary=True)
        _bind(ag, "set_non_interactive")
        ag.set_non_interactive(True)
        # 非交互模式不应把 need_summary 强制改为 False（保留原始值）
        assert ag.need_summary is True

    def test_exit_non_interactive_restores_summary_switch(self):
        """退出非交互模式：_summary_on_complete 应恢复为 False"""
        ag = _make_agent(need_summary=False)
        _bind(ag, "set_non_interactive")
        ag.set_non_interactive(True)
        ag.set_non_interactive(False)
        assert ag.non_interactive is False
        assert ag._summary_on_complete is False

    def test_exit_non_interactive_restores_original_need_summary(self):
        """退出非交互模式：need_summary 恢复原始值（与既有 set_non_interactive 语义一致）"""
        ag = _make_agent(need_summary=True)
        _bind(ag, "set_non_interactive")
        ag.set_non_interactive(True)
        ag.set_non_interactive(False)
        assert ag.need_summary is True


def _make_execute_agent(**attrs):
    """构造 _execute_auto_complete 所需的 agent 对象"""
    ag = SimpleNamespace()
    ag.git_manager = None
    ag.start_commit = None
    ag.return_control_on_auto_complete = False
    ag.non_interactive = True
    ag.need_summary = False
    ag._summary_on_complete = True
    ag._before_complete_check_hooks = []
    ag.set_addon_prompt = Mock()
    ag._complete_task = Mock(return_value="任务总结")
    _bind(ag, "_run_before_complete_check")
    for k, v in attrs.items():
        setattr(ag, k, v)
    return ag


class TestConstructorNonInteractiveEntry:
    """构造函数传入 non_interactive 的非交互入口（code_agent CLI / jvs CLI /
    pipeline_runner / send_to_agent / sub_agent）也应统一生效。

    这些入口通过 Agent(non_interactive=True, ...) 构造，从不调用
    set_non_interactive(True)。_init_config 需在构造时同步置位
    _summary_on_complete，否则 _execute_auto_complete 的新分支不命中，
    仍返回 !!!COMPLETE!!! 标记。
    """

    def test_constructor_non_interactive_enables_summary_switch(self):
        """构造函数传入 non_interactive=True：_summary_on_complete 应被启用"""
        ag = _make_agent()
        _bind(ag, "_init_config")
        # 模拟 _init_config 中 auto_complete 解析后的状态
        ag.in_multi_agent = False
        ag.non_interactive = True
        ag.auto_complete = False
        ag._init_config(
            use_methodology=None,
            use_analysis=None,
            execute_tool_confirm=None,
            force_save_memory=None,
            summary_prompt=None,
        )
        assert ag._summary_on_complete is True

    def test_constructor_interactive_keeps_summary_switch_off(self):
        """构造函数传入 non_interactive=False：_summary_on_complete 保持 False"""
        ag = _make_agent()
        _bind(ag, "_init_config")
        ag.in_multi_agent = False
        ag.non_interactive = False
        ag.auto_complete = False
        ag._init_config(
            use_methodology=None,
            use_analysis=None,
            execute_tool_confirm=None,
            force_save_memory=None,
            summary_prompt=None,
        )
        assert ag._summary_on_complete is False

    def test_constructor_non_interactive_returns_summary(self):
        """构造函数非交互入口：_execute_auto_complete 返回总结而非完成标记"""
        ag = _make_execute_agent(
            need_summary=False,
            _summary_on_complete=True,  # 构造函数路径由 _init_config 置位
        )
        run_loop = AgentRunLoop(ag)
        should_continue, result = run_loop._execute_auto_complete(ag, "!!!COMPLETE!!!")
        assert should_continue is False
        assert result == "任务总结"
        assert result != "!!!COMPLETE!!!"


class TestExecuteAutoCompleteNonInteractive:
    """_execute_auto_complete 在非交互模式下返回总结而非完成标记"""

    @pytest.fixture
    def loop(self):
        ag = _make_execute_agent()
        return AgentRunLoop(ag), ag

    def test_non_interactive_returns_summary_not_complete_marker(self, loop):
        """非交互模式：返回 _complete_task 的总结结果，而非 current_response"""
        run_loop, ag = loop
        should_continue, result = run_loop._execute_auto_complete(ag, "!!!COMPLETE!!!")
        assert should_continue is False
        assert result == "任务总结"
        assert result != "!!!COMPLETE!!!"
        ag._complete_task.assert_called_once_with(auto_completed=True)

    def test_non_interactive_summary_empty_falls_back(self, loop):
        """非交互模式：总结为空时回退「任务完成」"""
        run_loop, ag = loop
        ag._complete_task = Mock(return_value="")
        should_continue, result = run_loop._execute_auto_complete(ag, "!!!COMPLETE!!!")
        assert should_continue is False
        assert result == "任务完成"

    def test_non_interactive_summary_exception_falls_back(self, loop):
        """非交互模式：总结抛异常时回退「任务完成」，不抛异常"""
        run_loop, ag = loop
        ag._complete_task = Mock(side_effect=RuntimeError("summary boom"))
        should_continue, result = run_loop._execute_auto_complete(ag, "!!!COMPLETE!!!")
        assert should_continue is False
        assert result == "任务完成"


class TestExecuteAutoCompleteInteractiveUnchanged:
    """交互模式下行为完全不变"""

    @pytest.fixture
    def loop(self):
        ag = _make_execute_agent(
            non_interactive=False,
            need_summary=False,
            _summary_on_complete=False,
        )
        return AgentRunLoop(ag), ag

    def test_interactive_no_summary_returns_current_response(self, loop):
        """交互模式 + need_summary=False：仍返回 current_response（行为不变）"""
        run_loop, ag = loop
        should_continue, result = run_loop._execute_auto_complete(ag, "!!!COMPLETE!!!")
        assert should_continue is False
        assert result == "!!!COMPLETE!!!"

    def test_interactive_with_summary_returns_summary(self, loop):
        """交互模式 + need_summary=True：返回 _complete_task 总结结果（行为不变）"""
        run_loop, ag = loop
        ag.need_summary = True
        should_continue, result = run_loop._execute_auto_complete(ag, "!!!COMPLETE!!!")
        assert should_continue is False
        assert result == "任务总结"
        ag._complete_task.assert_called_once_with(auto_completed=True)
