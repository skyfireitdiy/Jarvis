# -*- coding: utf-8 -*-
"""完成校验 Hook（BEFORE_COMPLETE_CHECK）职责簇测试

覆盖：
- events.py 新增事件常量 BEFORE_COMPLETE_CHECK 与 EVENT_SHORT_NAMES
- Agent._run_before_complete_check 完成校验方法（拦截型 hook 语义）
- callback_loader 对 before_complete_check 的 hook 白名单与注册分支
- run_loop._execute_auto_complete 集成（校验失败阻止完成并注入提示，校验通过正常完成）

测试范式沿用 tests/jarvis_agent/test_callback_loading.py：
使用 Mock 构造 agent，再把真实方法绑定上去，避免复杂初始化。
"""

from unittest.mock import Mock

import pytest

from jarvis.jarvis_agent import Agent as RealAgent
from jarvis.jarvis_agent.callback_loader import CallbackLoader
from jarvis.jarvis_agent.events import BEFORE_COMPLETE_CHECK
from jarvis.jarvis_agent.events import EVENT_SHORT_NAMES
from jarvis.jarvis_agent.run_loop import AgentRunLoop


def _bind(agent, method_name):
    """把 RealAgent 上的真实方法绑定到 mock 的 agent 对象上"""
    setattr(
        agent,
        method_name,
        getattr(RealAgent, method_name).__get__(agent, Mock),
    )
    return agent


def _make_agent(**attrs):
    """创建一个 Mock agent，并设置完成校验所需的最小属性"""
    ag = Mock()
    ag._before_complete_check_hooks = []
    ag._before_tool_call_hooks = []
    ag._before_model_call_modifiers = []
    ag._before_summary_modifiers = []
    ag._callback_loader = CallbackLoader(ag)
    ag.event_bus = Mock()
    for k, v in attrs.items():
        setattr(ag, k, v)
    return ag


class TestEventsConstant:
    """events.py 新增 BEFORE_COMPLETE_CHECK 事件常量"""

    def test_constant_value(self):
        """常量值应为 before_complete_check"""
        assert BEFORE_COMPLETE_CHECK == "before_complete_check"

    def test_in_short_names(self):
        """应加入 EVENT_SHORT_NAMES，供插件 event_callbacks 探测/校验"""
        assert BEFORE_COMPLETE_CHECK in EVENT_SHORT_NAMES


class TestRunBeforeCompleteCheck:
    """Agent._run_before_complete_check 完成校验方法"""

    @pytest.fixture
    def agent(self):
        return _bind(_make_agent(), "_run_before_complete_check")

    def test_no_hooks_passes(self, agent):
        """未注册任何校验回调时返回 None（通过）"""
        assert agent._run_before_complete_check(
            auto_completed=True, need_summary=True
        ) is None

    def test_true_passes(self, agent):
        """hook 返回 True 视为通过"""
        agent._before_complete_check_hooks.append(
            lambda **kw: True
        )
        assert agent._run_before_complete_check(
            auto_completed=True, need_summary=True
        ) is None

    def test_false_rejects_with_default_reason(self, agent):
        """hook 返回 False 时返回默认拒绝原因（非空字符串）"""
        agent._before_complete_check_hooks.append(
            lambda **kw: False
        )
        reason = agent._run_before_complete_check(
            auto_completed=True, need_summary=True
        )
        assert isinstance(reason, str)
        assert reason.strip() != ""

    def test_tuple_false_rejects_with_reason(self, agent):
        """hook 返回 (False, "原因") 时返回该原因"""
        agent._before_complete_check_hooks.append(
            lambda **kw: (False, "未通过验收")
        )
        reason = agent._run_before_complete_check(
            auto_completed=True, need_summary=True
        )
        assert reason == "未通过验收"

    def test_tuple_true_passes(self, agent):
        """hook 返回 (True, "") 视为通过"""
        agent._before_complete_check_hooks.append(
            lambda **kw: (True, "")
        )
        assert agent._run_before_complete_check(
            auto_completed=True, need_summary=True
        ) is None

    def test_all_pass_required(self, agent):
        """多 hook AND 语义：全部通过才放行"""
        calls = []
        agent._before_complete_check_hooks.append(
            lambda **kw: calls.append("a") or True
        )
        agent._before_complete_check_hooks.append(
            lambda **kw: calls.append("b") or True
        )
        assert agent._run_before_complete_check(
            auto_completed=True, need_summary=True
        ) is None
        assert calls == ["a", "b"]

    def test_any_reject_stops_later_hooks(self, agent):
        """任一拦截即停止后续调用，并返回该回调的拒绝原因"""
        calls = []
        agent._before_complete_check_hooks.append(
            lambda **kw: calls.append("a") or (False, "第一个拒绝")
        )
        agent._before_complete_check_hooks.append(
            lambda **kw: calls.append("b") or True
        )
        reason = agent._run_before_complete_check(
            auto_completed=True, need_summary=True
        )
        assert reason == "第一个拒绝"
        assert calls == ["a"]

    def test_exception_treated_as_pass(self, agent):
        """回调抛异常时视为通过，不阻塞主流程"""
        def _boom(**kw):
            raise RuntimeError("boom")

        agent._before_complete_check_hooks.append(_boom)
        assert agent._run_before_complete_check(
            auto_completed=True, need_summary=True
        ) is None


class TestCallbackLoaderHookWhitelist:
    """callback_loader 对 before_complete_check 的 hook 支持"""

    @pytest.fixture
    def agent(self):
        return _make_agent()

    def test_plugin_hook_whitelist_allows_before_complete_check(
        self, agent, tmp_path, monkeypatch
    ):
        """_load_plugin_event_callback 对 target=hook + before_complete_check 不再跳过"""
        # 写入真实回调文件
        cb_dir = tmp_path / "cb"
        cb_dir.mkdir()
        (cb_dir / "before_complete_check_cb.py").write_text(
            "def before_complete_check_cb(agent, auto_completed, need_summary):\n"
            "    return True\n",
            encoding="utf-8",
        )
        # 让 _load_event_callbacks 走真实加载（config_getter 返回该目录）
        agent._load_event_callbacks = RealAgent._load_event_callbacks.__get__(
            agent, Mock
        )
        agent._callback_loader._load_plugin_event_callback(
            str(cb_dir), BEFORE_COMPLETE_CHECK, "hook"
        )
        # 不应被白名单跳过：hook 已注册
        assert len(agent._before_complete_check_hooks) == 1

    def test_load_event_callbacks_hook_branch_registers(
        self, agent, tmp_path
    ):
        """load_event_callbacks 的 hook 分支把 before_complete_check 回调加入 hooks 列表"""
        cb_dir = tmp_path / "cb"
        cb_dir.mkdir()
        (cb_dir / "before_complete_check_cb.py").write_text(
            "def before_complete_check_cb(agent, auto_completed, need_summary):\n"
            "    return True\n",
            encoding="utf-8",
        )
        agent._load_event_callbacks = RealAgent._load_event_callbacks.__get__(
            agent, Mock
        )
        agent._load_event_callbacks(
            event_name=BEFORE_COMPLETE_CHECK,
            config_getter=lambda: [str(cb_dir)],
            callback_names=[
                "before_complete_check_cb",
                "get_before_complete_check_cb",
                "register_before_complete_check_cb",
            ],
            target="hook",
        )
        assert len(agent._before_complete_check_hooks) == 1


class TestExecuteAutoCompleteIntegration:
    """run_loop._execute_auto_complete 集成：校验失败阻止完成并注入提示"""

    @pytest.fixture
    def loop(self):
        ag = Mock()
        ag.git_manager = None
        ag.start_commit = None
        ag.return_control_on_auto_complete = False
        ag.non_interactive = False
        ag.need_summary = True
        ag._before_complete_check_hooks = []
        ag.set_addon_prompt = Mock()
        ag._complete_task = Mock(return_value="任务总结")
        # 绑定真实校验方法，避免 Mock 自动生成的方法返回 Mock 对象
        _bind(ag, "_run_before_complete_check")
        return AgentRunLoop(ag), ag

    def test_rejected_continues_next_round(self, loop):
        """校验失败：返回 (True, None) 继续下一轮，注入拒绝原因，不调用 _complete_task"""
        run_loop, ag = loop
        ag._before_complete_check_hooks.append(
            lambda **kw: (False, "缺少交付物")
        )
        should_continue, result = run_loop._execute_auto_complete(ag, "响应")
        assert should_continue is True
        assert result is None
        # 拒绝原因被注入 addon_prompt
        injected = ag.set_addon_prompt.call_args[0][0]
        assert "缺少交付物" in injected
        # 未走总结流程
        ag._complete_task.assert_not_called()

    def test_passed_completes_normally(self, loop):
        """校验通过：调用 _complete_task，返回 (False, result)"""
        run_loop, ag = loop
        ag._before_complete_check_hooks.append(
            lambda **kw: True
        )
        should_continue, result = run_loop._execute_auto_complete(ag, "响应")
        assert should_continue is False
        assert result == "任务总结"
        ag._complete_task.assert_called_once_with(auto_completed=True)

    def test_no_hooks_completes_normally(self, loop):
        """未注册校验回调：与现状一致，正常完成"""
        run_loop, ag = loop
        should_continue, result = run_loop._execute_auto_complete(ag, "响应")
        assert should_continue is False
        assert result == "任务总结"
        ag._complete_task.assert_called_once_with(auto_completed=True)

    def test_manual_complete_not_checked(self, loop):
        """手动结束（auto_completed=False）不触发校验"""
        run_loop, ag = loop
        calls = []
        ag._before_complete_check_hooks.append(
            lambda **kw: calls.append(1) or (False, "不应触发")
        )
        # 手动结束路径：run_loop 主循环中 action == "complete" 时直接调用
        # ag._complete_task(auto_completed=False)（见 run_loop.py:1199-1200），
        # 不经过 _execute_auto_complete，因此完成校验 hooks 不应被执行。
        ag._complete_task(auto_completed=False)
        assert calls == []
