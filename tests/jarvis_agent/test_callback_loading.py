# -*- coding: utf-8 -*-
"""回调/事件加载职责簇测试

覆盖 Agent 类中「回调/事件加载」职责簇的方法：
- _load_after_tool_callbacks
- _load_event_callbacks
- _load_all_event_callbacks
- _fire_after_tool_call

测试范式沿用 tests/jarvis_agent/test_history_compression.py：
使用 Mock 构造 agent，再把真实方法绑定上去，避免复杂初始化。
回调文件通过 tmp_path 构造真实目录与 .py 文件，覆盖目录不存在、
空目录、非法文件、工厂方法、hook/modifier/event 三种注册目标等场景。
"""

import sys
from unittest.mock import Mock

import pytest

from jarvis.jarvis_agent import Agent as RealAgent
from jarvis.jarvis_agent.event_bus import EventBus
from jarvis.jarvis_agent.events import AFTER_SUMMARY
from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_agent.events import BEFORE_MODEL_CALL
from jarvis.jarvis_agent.events import BEFORE_SUMMARY
from jarvis.jarvis_agent.events import BEFORE_TOOL_CALL


def _bind(agent, method_name):
    """把 RealAgent 上的真实方法绑定到 mock 的 agent 对象上"""
    setattr(
        agent,
        method_name,
        getattr(RealAgent, method_name).__get__(agent, Mock),
    )
    return agent


def _make_agent(**attrs):
    """创建一个 Mock agent，并设置本簇方法所需的最小属性"""
    from jarvis.jarvis_agent.callback_loader import CallbackLoader

    ag = Mock()
    # 真实 EventBus：本簇核心行为就是向它订阅回调，用真实实现才能验证
    ag.event_bus = EventBus()
    # Hook/Modifier 列表：真实列表，便于断言 append 行为
    ag._before_tool_call_hooks = []
    ag._before_model_call_modifiers = []
    ag._before_summary_modifiers = []
    # 重构后 Agent 侧方法委托给 self._callback_loader，绑定真实方法前需补齐
    ag._callback_loader = CallbackLoader(ag)
    for k, v in attrs.items():
        setattr(ag, k, v)
    return ag


def _write_cb_file(directory, name, content):
    """在指定目录写入一个回调 .py 文件并返回其路径"""
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


class TestFireAfterToolCall:
    """_fire_after_tool_call 触发 AFTER_TOOL_CALL 事件"""

    @pytest.fixture
    def agent(self):
        return _bind(_make_agent(), "_fire_after_tool_call")

    def test_emits_event_with_expected_payload(self, agent):
        """emit 一次，携带 agent/current_response/need_return/tool_prompt"""
        calls = []
        agent.event_bus.subscribe(AFTER_TOOL_CALL, lambda **kw: calls.append(kw))

        agent._fire_after_tool_call()

        assert len(calls) == 1
        payload = calls[0]
        assert payload["agent"] is agent
        assert payload["current_response"] == ""
        assert payload["need_return"] is False
        assert payload["tool_prompt"] == ""

    def test_subscriber_invoked_exactly_once(self, agent):
        """订阅回调只被调用一次（回归：此前存在双派发）"""
        cb = Mock()
        agent.event_bus.subscribe(AFTER_TOOL_CALL, cb)

        agent._fire_after_tool_call()

        assert cb.call_count == 1

    def test_exception_is_swallowed(self, agent):
        """event_bus.emit 抛异常时被捕获，不向外传播"""
        agent.event_bus = Mock()
        agent.event_bus.emit = Mock(side_effect=RuntimeError("boom"))

        # 不应抛出异常
        agent._fire_after_tool_call()

        assert agent.event_bus.emit.call_count == 1


class TestLoadAfterToolCallbacks:
    """_load_after_tool_callbacks 扫描目录并注册 after_tool_call 回调"""

    @pytest.fixture
    def agent(self):
        return _bind(_make_agent(), "_load_after_tool_callbacks")

    @pytest.fixture
    def cb_dirs(self, monkeypatch):
        """把 get_after_tool_call_cb_dirs 替换为可配置的 mock"""
        import jarvis.jarvis_agent.callback_loader as mod

        holder = Mock(return_value=[])
        monkeypatch.setattr(mod, "get_after_tool_call_cb_dirs", holder)
        return holder

    def test_no_dirs_does_nothing(self, agent, cb_dirs):
        """未配置回调目录时不注册任何回调"""
        cb_dirs.return_value = []
        agent._load_after_tool_callbacks()
        assert agent.event_bus._listeners[AFTER_TOOL_CALL] == []

    def test_nonexistent_dir_is_skipped(self, agent, cb_dirs, tmp_path):
        """目录不存在时跳过，不报错"""
        cb_dirs.return_value = [str(tmp_path / "not-exist")]
        agent._load_after_tool_callbacks()
        assert agent.event_bus._listeners[AFTER_TOOL_CALL] == []

    def test_empty_dir_registers_nothing(self, agent, cb_dirs, tmp_path):
        """空目录不注册任何回调"""
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_after_tool_callbacks()
        assert agent.event_bus._listeners[AFTER_TOOL_CALL] == []

    def test_module_level_callback_registered(self, agent, cb_dirs, tmp_path):
        """模块级 after_tool_call_cb 被包装注册，wrapper 以 agent 调用原回调"""
        _write_cb_file(
            tmp_path,
            "cb_mod.py",
            "def after_tool_call_cb(agent):\n    agent.recorded = True\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_after_tool_callbacks()

        listeners = agent.event_bus._listeners[AFTER_TOOL_CALL]
        assert len(listeners) == 1
        # emit 触发 wrapper，wrapper 从 kwargs 取 agent 传给原回调
        agent.event_bus.emit(AFTER_TOOL_CALL, agent=agent)
        assert agent.recorded is True

    def test_factory_method_returning_single(self, agent, cb_dirs, tmp_path):
        """工厂方法 get_after_tool_call_cb 返回单个可调用对象"""
        _write_cb_file(
            tmp_path,
            "cb_factory.py",
            "def _impl(agent):\n"
            "    agent.hit = True\n"
            "def get_after_tool_call_cb():\n"
            "    return _impl\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_after_tool_callbacks()

        assert len(agent.event_bus._listeners[AFTER_TOOL_CALL]) == 1
        agent.event_bus.emit(AFTER_TOOL_CALL, agent=agent)
        assert agent.hit is True

    def test_factory_method_returning_list(self, agent, cb_dirs, tmp_path):
        """工厂方法返回列表时逐个注册"""
        _write_cb_file(
            tmp_path,
            "cb_factory_list.py",
            "def _a(agent):\n"
            "    agent.a_called = True\n"
            "def _b(agent):\n"
            "    agent.b_called = True\n"
            "def register_after_tool_call_cb():\n"
            "    return [_a, _b]\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_after_tool_callbacks()

        assert len(agent.event_bus._listeners[AFTER_TOOL_CALL]) == 2
        agent.event_bus.emit(AFTER_TOOL_CALL, agent=agent)
        assert agent.a_called is True
        assert agent.b_called is True

    def test_init_py_is_skipped(self, agent, cb_dirs, tmp_path):
        """__init__.py 被跳过"""
        _write_cb_file(
            tmp_path,
            "__init__.py",
            "def after_tool_call_cb(agent):\n    agent.should_not_run = True\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_after_tool_callbacks()
        assert agent.event_bus._listeners[AFTER_TOOL_CALL] == []

    def test_invalid_python_file_is_tolerated(self, agent, cb_dirs, tmp_path):
        """语法错误的文件被容错跳过，不影响整体流程"""
        _write_cb_file(tmp_path, "broken.py", "def (:\n    pass\n")
        cb_dirs.return_value = [str(tmp_path)]
        # 不应抛出异常
        agent._load_after_tool_callbacks()
        assert agent.event_bus._listeners[AFTER_TOOL_CALL] == []

    def test_factory_exception_is_tolerated(self, agent, cb_dirs, tmp_path):
        """工厂方法抛异常时被捕获，不注册回调也不报错"""
        _write_cb_file(
            tmp_path,
            "cb_bad_factory.py",
            "def get_after_tool_call_cb():\n    raise RuntimeError('factory boom')\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_after_tool_callbacks()
        assert agent.event_bus._listeners[AFTER_TOOL_CALL] == []

    def test_callback_exception_is_tolerated(self, agent, cb_dirs, tmp_path):
        """回调执行抛异常时被 wrapper 捕获，不影响其它回调"""
        _write_cb_file(
            tmp_path,
            "cb_raise.py",
            "def after_tool_call_cb(agent):\n    raise RuntimeError('cb boom')\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_after_tool_callbacks()

        # emit 不应抛出异常
        agent.event_bus.emit(AFTER_TOOL_CALL, agent=agent)

    def test_sys_path_restored_after_load(self, agent, cb_dirs, tmp_path):
        """加载结束后 sys.path 被还原（不残留回调目录）"""
        _write_cb_file(
            tmp_path,
            "cb_path.py",
            "def after_tool_call_cb(agent):\n    agent.ok = True\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        before = list(sys.path)
        agent._load_after_tool_callbacks()
        assert sys.path == before

    def test_config_getter_exception_is_tolerated(self, agent, cb_dirs):
        """目录获取函数抛异常时被外层捕获，不向外传播"""
        cb_dirs.side_effect = RuntimeError("config boom")
        agent._load_after_tool_callbacks()
        assert agent.event_bus._listeners[AFTER_TOOL_CALL] == []


class TestLoadEventCallbacks:
    """_load_event_callbacks 通用回调加载（hook/modifier/event 三种目标）"""

    @pytest.fixture
    def agent(self):
        return _bind(_make_agent(), "_load_event_callbacks")

    @pytest.fixture
    def cb_dirs(self, monkeypatch):
        import jarvis.jarvis_agent.callback_loader as mod

        holder = Mock(return_value=[])
        monkeypatch.setattr(mod, "get_before_tool_call_cb_dirs", holder)
        return holder

    def test_no_dirs_does_nothing(self, agent, cb_dirs):
        """未配置目录时不注册任何回调"""
        cb_dirs.return_value = []
        agent._load_event_callbacks(
            event_name=BEFORE_TOOL_CALL,
            config_getter=cb_dirs,
            callback_names=["before_tool_call_cb"],
            target="hook",
        )
        assert agent._before_tool_call_hooks == []
        assert agent.event_bus._listeners[BEFORE_TOOL_CALL] == []

    def test_hook_target_registers_hook_and_event(self, agent, cb_dirs, tmp_path):
        """target=hook：既加入 hooks 列表，又订阅 EventBus"""
        _write_cb_file(
            tmp_path,
            "hook_cb.py",
            "def before_tool_call_cb(agent):\n    return True\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_event_callbacks(
            event_name=BEFORE_TOOL_CALL,
            config_getter=cb_dirs,
            callback_names=["before_tool_call_cb"],
            target="hook",
        )
        assert len(agent._before_tool_call_hooks) == 1
        assert len(agent.event_bus._listeners[BEFORE_TOOL_CALL]) == 1

    def test_modifier_target_model_call(self, agent, cb_dirs, tmp_path):
        """target=modifier + BEFORE_MODEL_CALL：加入 _before_model_call_modifiers"""
        _write_cb_file(
            tmp_path,
            "mod_cb.py",
            "def before_model_call_cb(agent, message):\n    return message\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_event_callbacks(
            event_name=BEFORE_MODEL_CALL,
            config_getter=cb_dirs,
            callback_names=["before_model_call_cb"],
            target="modifier",
        )
        assert len(agent._before_model_call_modifiers) == 1
        # modifier 不订阅 EventBus
        assert agent.event_bus._listeners[BEFORE_MODEL_CALL] == []

    def test_modifier_target_summary(self, agent, cb_dirs, tmp_path):
        """target=modifier + BEFORE_SUMMARY：加入 _before_summary_modifiers"""
        _write_cb_file(
            tmp_path,
            "sum_cb.py",
            "def before_summary_cb(agent, prompt, auto_completed):\n"
            "    return prompt\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_event_callbacks(
            event_name=BEFORE_SUMMARY,
            config_getter=cb_dirs,
            callback_names=["before_summary_cb"],
            target="modifier",
        )
        assert len(agent._before_summary_modifiers) == 1
        assert agent.event_bus._listeners[BEFORE_SUMMARY] == []

    def test_event_target_subscribes_only(self, agent, cb_dirs, tmp_path):
        """target=event_bus（默认）：仅订阅 EventBus"""
        _write_cb_file(
            tmp_path,
            "evt_cb.py",
            "def after_summary_cb(agent):\n    return None\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_event_callbacks(
            event_name=AFTER_SUMMARY,
            config_getter=cb_dirs,
            callback_names=["after_summary_cb"],
        )
        assert len(agent.event_bus._listeners[AFTER_SUMMARY]) == 1
        assert agent._before_summary_modifiers == []

    def test_callback_priority_order(self, agent, cb_dirs, tmp_path):
        """多个回调名按 callback_names 顺序收集（高优先级在前）"""
        _write_cb_file(
            tmp_path,
            "multi_cb.py",
            "def before_tool_call_cb(agent):\n"
            "    return 'direct'\n"
            "def get_before_tool_call_cb():\n"
            "    def _factory(agent):\n"
            "        return 'factory'\n"
            "    return _factory\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_event_callbacks(
            event_name=BEFORE_TOOL_CALL,
            config_getter=cb_dirs,
            callback_names=[
                "before_tool_call_cb",
                "get_before_tool_call_cb",
            ],
            target="hook",
        )
        # 两个回调都被注册
        assert len(agent._before_tool_call_hooks) == 2
        assert len(agent.event_bus._listeners[BEFORE_TOOL_CALL]) == 2

    def test_factory_method_invoked(self, agent, cb_dirs, tmp_path):
        """get_/register_ 前缀的回调名被当作工厂方法调用"""
        _write_cb_file(
            tmp_path,
            "factory_cb.py",
            "def get_before_tool_call_cb():\n"
            "    def _cb(agent):\n"
            "        return True\n"
            "    return _cb\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_event_callbacks(
            event_name=BEFORE_TOOL_CALL,
            config_getter=cb_dirs,
            callback_names=["get_before_tool_call_cb"],
            target="hook",
        )
        assert len(agent._before_tool_call_hooks) == 1

    def test_invalid_file_is_tolerated(self, agent, cb_dirs, tmp_path):
        """语法错误文件容错跳过"""
        _write_cb_file(tmp_path, "broken.py", "def (:\n    pass\n")
        cb_dirs.return_value = [str(tmp_path)]
        agent._load_event_callbacks(
            event_name=BEFORE_TOOL_CALL,
            config_getter=cb_dirs,
            callback_names=["before_tool_call_cb"],
            target="hook",
        )
        assert agent._before_tool_call_hooks == []

    def test_sys_path_restored(self, agent, cb_dirs, tmp_path):
        """加载结束后 sys.path 被还原"""
        _write_cb_file(
            tmp_path,
            "path_cb.py",
            "def before_tool_call_cb(agent):\n    return True\n",
        )
        cb_dirs.return_value = [str(tmp_path)]
        before = list(sys.path)
        agent._load_event_callbacks(
            event_name=BEFORE_TOOL_CALL,
            config_getter=cb_dirs,
            callback_names=["before_tool_call_cb"],
            target="hook",
        )
        assert sys.path == before


class TestLoadAllEventCallbacks:
    """_load_all_event_callbacks 编排四类事件回调的加载"""

    @pytest.fixture
    def agent(self):
        return _bind(_make_agent(), "_load_all_event_callbacks")

    def test_invokes_load_event_callbacks_four_times(self, agent):
        """按四种事件各调用一次 _load_event_callbacks"""
        agent._load_event_callbacks = Mock()
        agent._load_all_event_callbacks()

        assert agent._load_event_callbacks.call_count == 4
        kwargs_list = [c.kwargs for c in agent._load_event_callbacks.call_args_list]
        events = [kw["event_name"] for kw in kwargs_list]
        assert events == [
            BEFORE_TOOL_CALL,
            BEFORE_MODEL_CALL,
            BEFORE_SUMMARY,
            AFTER_SUMMARY,
        ]

    def test_target_kinds_are_correct(self, agent):
        """hook/modifier/modifier/event 四种目标类型正确"""
        agent._load_event_callbacks = Mock()
        agent._load_all_event_callbacks()

        kwargs_list = [c.kwargs for c in agent._load_event_callbacks.call_args_list]
        targets = [kw.get("target", "event_bus") for kw in kwargs_list]
        assert targets == ["hook", "modifier", "modifier", "event_bus"]

    def test_config_getters_are_wired(self, agent):
        """各事件使用对应的目录获取函数"""
        import jarvis.jarvis_agent.callback_loader as mod

        agent._load_event_callbacks = Mock()
        agent._load_all_event_callbacks()

        kwargs_list = [c.kwargs for c in agent._load_event_callbacks.call_args_list]
        getters = [kw["config_getter"] for kw in kwargs_list]
        assert getters[0] is mod.get_before_tool_call_cb_dirs
        assert getters[1] is mod.get_before_model_call_cb_dirs
        assert getters[2] is mod.get_summary_cb_dirs
        assert getters[3] is mod.get_summary_cb_dirs

    def test_callback_names_are_wired(self, agent):
        """各事件使用对应的回调名列表"""
        agent._load_event_callbacks = Mock()
        agent._load_all_event_callbacks()

        kwargs_list = [c.kwargs for c in agent._load_event_callbacks.call_args_list]
        names = [kw["callback_names"] for kw in kwargs_list]
        assert names[0] == [
            "before_tool_call_cb",
            "get_before_tool_call_cb",
            "register_before_tool_call_cb",
        ]
        assert names[1] == [
            "before_model_call_cb",
            "get_before_model_call_cb",
            "register_before_model_call_cb",
        ]
        assert names[2] == [
            "before_summary_cb",
            "get_before_summary_cb",
            "register_before_summary_cb",
        ]
        assert names[3] == [
            "after_summary_cb",
            "get_after_summary_cb",
            "register_after_summary_cb",
        ]
