# -*- coding: utf-8 -*-
"""模型/平台切换职责簇测试

覆盖 Agent 类中「模型/平台切换」职责簇的方法：
- _switch_model_by_difficulty
- _classify_and_switch_model
- _apply_task_temperature
- _create_temp_model

测试范式沿用 tests/jarvis_agent/test_history_compression.py /
test_callback_loading.py：使用 Mock 构造 agent，再把 RealAgent 上的真实方法
绑定上去，避免复杂初始化（不真实调用 LLM、不访问网络）。

设计要点：
- 断言的是「可观察行为」（返回值、副作用、被调用的参数），而非实现位置，
  因此这些用例在簇3 重构（方法迁往 model_switcher.py）前后都成立。
- 源码中存在函数体内的延迟 import（switch_platform_type / get_llm_config）
  与模块级 import（PlatformRegistry），patch 目标按实际实现选择：
    * switch_platform_type -> jarvis.jarvis_agent.builtin_input_handler
    * get_llm_config       -> jarvis.jarvis_utils.config
    * PlatformRegistry     -> jarvis.jarvis_agent.PlatformRegistry（模块全局名）
- Mock() 会自动生成任意属性且为真值，凡源码用 hasattr/getattr 判断的属性
  必须在测试中显式设置，否则断言会失真。
"""

from unittest.mock import Mock

import pytest

from jarvis.jarvis_agent import Agent as RealAgent


def _bind(agent, method_name):
    """把 RealAgent 上的真实方法绑定到 mock 的 agent 对象上"""
    setattr(
        agent,
        method_name,
        getattr(RealAgent, method_name).__get__(agent, Mock),
    )
    return agent


def _make_agent(**attrs):
    """创建一个 Mock agent，并显式设置本簇方法所需的最小属性

    注意：Mock() 对任意属性访问都会返回真值 Mock，因此源码中所有
    hasattr/getattr 判断的属性都必须显式赋值（含 None），否则分支会走错。
    """
    from jarvis.jarvis_agent.model_switcher import ModelSwitcher

    ag = Mock()
    # 重构后 Agent 侧方法委托给 self._model_switcher，绑定真实方法前需补齐
    ag._model_switcher = ModelSwitcher(ag)
    # 模型类型标记与手动切换开关（_switch_model_by_difficulty 依赖）
    ag._model_type = "normal"
    ag._manual_model_switch = False
    # 系统提示词与提示词管理器（切换成功后重建提示词依赖）
    ag.system_prompt = ""
    ag.prompt_manager = None
    # 模型实例
    ag.model = Mock()
    ag.model.platform_type = "normal"
    for k, v in attrs.items():
        setattr(ag, k, v)
    return ag


def _patch_switch_platform_type(monkeypatch, func):
    """patch 延迟导入的 switch_platform_type（位于 builtin_input_handler）

    注意：包内 `builtin_input_handler` 这个名字被同名函数遮蔽（re-export），
    因此 monkeypatch 的字符串路径解析会拿到函数而非模块；这里显式从
    sys.modules 取模块对象再 patch 其属性。
    """
    import sys

    module = sys.modules["jarvis.jarvis_agent.builtin_input_handler"]
    monkeypatch.setattr(module, "switch_platform_type", func)


def _patch_get_llm_config(monkeypatch, func):
    """patch 延迟导入的 get_llm_config（位于 jarvis_utils.config）"""
    import sys

    module = sys.modules["jarvis.jarvis_utils.config"]
    monkeypatch.setattr(module, "get_llm_config", func)


class TestSwitchModelByDifficulty:
    """_switch_model_by_difficulty 按难度切换模型类型"""

    @pytest.fixture
    def agent(self):
        return _bind(_make_agent(), "_switch_model_by_difficulty")

    def test_manual_switch_disables_auto(self, agent, monkeypatch):
        """用户手动切换过模型时直接返回，不调用 switch_platform_type"""
        agent._manual_model_switch = True
        calls = []
        _patch_switch_platform_type(
            monkeypatch, lambda *a, **k: calls.append((a, k)) or True
        )
        agent._switch_model_by_difficulty("hard")
        assert calls == []
        # 模型类型保持不变
        assert agent._model_type == "normal"

    @pytest.mark.parametrize(
        "difficulty,expected",
        [
            ("easy", "normal"),
            ("medium", "normal"),
            ("hard", "smart"),
            ("unknown-difficulty", "normal"),
        ],
    )
    def test_difficulty_mapping(self, agent, monkeypatch, difficulty, expected):
        """难度到模型类型的映射：easy/medium->normal，hard->smart，未知->normal"""
        # 让当前模型类型与目标不同，确保会真正触发切换
        agent._model_type = "cheap" if expected != "cheap" else "smart"
        captured = {}

        def fake_switch(ag, platform_type, preserve_model_group=True):
            captured["platform_type"] = platform_type
            captured["preserve_model_group"] = preserve_model_group
            return True

        _patch_switch_platform_type(monkeypatch, fake_switch)
        agent._switch_model_by_difficulty(difficulty)
        assert captured["platform_type"] == expected
        assert captured["preserve_model_group"] is True
        assert agent._model_type == expected

    def test_same_model_type_skips_switch(self, agent, monkeypatch):
        """目标模型类型与当前一致时提前返回，不调用 switch_platform_type"""
        agent._model_type = "normal"
        calls = []
        _patch_switch_platform_type(
            monkeypatch, lambda *a, **k: calls.append((a, k)) or True
        )
        agent._switch_model_by_difficulty("easy")
        assert calls == []

    def test_switch_success_updates_type_and_prompt_without_prompt_manager(
        self, agent, monkeypatch
    ):
        """切换成功：更新 _model_type，并直接用 self.system_prompt 重建提示词"""
        agent._model_type = "normal"
        agent.system_prompt = "原始系统提示词"
        _patch_switch_platform_type(monkeypatch, lambda *a, **k: True)
        agent._switch_model_by_difficulty("hard")
        assert agent._model_type == "smart"
        agent.model.set_system_prompt.assert_called_once_with("原始系统提示词")

    def test_switch_success_uses_prompt_manager(self, agent, monkeypatch):
        """切换成功且有 prompt_manager 时，走 build_system_prompt 重建提示词"""
        agent._model_type = "normal"
        agent.system_prompt = "原始系统提示词"
        agent.prompt_manager = Mock()
        agent.prompt_manager.build_system_prompt = Mock(return_value="重建后的提示词")
        _patch_switch_platform_type(monkeypatch, lambda *a, **k: True)
        agent._switch_model_by_difficulty("hard")
        agent.prompt_manager.build_system_prompt.assert_called_once_with(agent)
        agent.model.set_system_prompt.assert_called_once_with("重建后的提示词")

    def test_switch_success_without_system_prompt_skips_set(self, agent, monkeypatch):
        """切换成功但无 system_prompt 时不调用 set_system_prompt"""
        agent._model_type = "normal"
        agent.system_prompt = ""
        _patch_switch_platform_type(monkeypatch, lambda *a, **k: True)
        agent._switch_model_by_difficulty("hard")
        assert agent._model_type == "smart"
        agent.model.set_system_prompt.assert_not_called()

    def test_switch_failure_keeps_model_type(self, agent, monkeypatch):
        """切换失败时不更新 _model_type，也不重建提示词"""
        agent._model_type = "normal"
        agent.system_prompt = "原始系统提示词"
        _patch_switch_platform_type(monkeypatch, lambda *a, **k: False)
        agent._switch_model_by_difficulty("hard")
        assert agent._model_type == "normal"
        agent.model.set_system_prompt.assert_not_called()


class TestClassifyAndSwitchModel:
    """_classify_and_switch_model 分类 -> 切换模型 -> 调温度 -> 更新提示词"""

    @pytest.fixture
    def agent(self):
        ag = _make_agent()
        _bind(ag, "_classify_and_switch_model")
        # 同簇内被调用的两个方法用 Mock 替换，便于断言调用参数
        # （重构后实现位于 ag._model_switcher 上，需替换该对象上的同名方法）
        ag._model_switcher.switch_model_by_difficulty = Mock()
        ag._model_switcher.apply_task_temperature = Mock()
        return ag

    def test_normal_flow_calls_substeps(self, agent):
        """正常流程：依次调用切换模型与调温度，并更新系统提示词"""
        agent.system_prompt = "旧提示词"
        agent.model = Mock()
        classify_fn = Mock(return_value=("coding", "hard", 0.7))
        get_prompt_fn = Mock(return_value="新提示词")

        agent._classify_and_switch_model("写一个函数", classify_fn, get_prompt_fn)

        classify_fn.assert_called_once_with("写一个函数")
        agent._model_switcher.switch_model_by_difficulty.assert_called_once_with("hard")
        agent._model_switcher.apply_task_temperature.assert_called_once_with(0.7)
        get_prompt_fn.assert_called_once_with("coding")
        assert agent.system_prompt == "新提示词"
        agent.model.set_system_prompt.assert_called_once_with("新提示词")

    def test_same_prompt_does_not_update(self, agent):
        """scenario_system_prompt 与当前 system_prompt 相同时不更新"""
        agent.system_prompt = "相同提示词"
        agent.model = Mock()
        classify_fn = Mock(return_value=("coding", "easy", 0.3))
        get_prompt_fn = Mock(return_value="相同提示词")

        agent._classify_and_switch_model("输入", classify_fn, get_prompt_fn)

        assert agent.system_prompt == "相同提示词"
        agent.model.set_system_prompt.assert_not_called()

    def test_uses_prompt_manager_when_available(self, agent):
        """有 prompt_manager 时通过 build_system_prompt 重建提示词"""
        agent.system_prompt = "旧提示词"
        agent.model = Mock()
        agent.prompt_manager = Mock()
        agent.prompt_manager.build_system_prompt = Mock(return_value="重建提示词")
        classify_fn = Mock(return_value=("coding", "hard", 0.5))
        get_prompt_fn = Mock(return_value="新提示词")

        agent._classify_and_switch_model("输入", classify_fn, get_prompt_fn)

        agent.prompt_manager.build_system_prompt.assert_called_once_with(agent)
        agent.model.set_system_prompt.assert_called_once_with("重建提示词")

    def test_classify_fn_exception_is_swallowed(self, agent):
        """classify_fn 抛异常时被捕获，不向外抛出，也不执行后续步骤"""
        agent.system_prompt = "旧提示词"

        def boom(_):
            raise RuntimeError("分类服务不可用")

        # 不应抛出异常
        agent._classify_and_switch_model("输入", boom, Mock())
        agent._model_switcher.switch_model_by_difficulty.assert_not_called()
        agent._model_switcher.apply_task_temperature.assert_not_called()
        assert agent.system_prompt == "旧提示词"

    def test_model_none_skips_set_system_prompt(self, agent):
        """self.model 为 None 时仍更新 system_prompt，但不调用 set_system_prompt"""
        agent.system_prompt = "旧提示词"
        agent.model = None
        classify_fn = Mock(return_value=("coding", "easy", 0.2))
        get_prompt_fn = Mock(return_value="新提示词")

        agent._classify_and_switch_model("输入", classify_fn, get_prompt_fn)

        assert agent.system_prompt == "新提示词"


class TestApplyTaskTemperature:
    """_apply_task_temperature 温度范围保护与显式配置优先"""

    @pytest.fixture
    def agent(self):
        ag = _make_agent()
        _bind(ag, "_apply_task_temperature")
        return ag

    def test_model_none_returns_early(self, agent):
        """model 为 None 时直接返回"""
        agent.model = None
        agent._apply_task_temperature(0.7)  # 不应抛异常

    def test_temperature_none_returns_early(self, agent, monkeypatch):
        """temperature 为 None 时直接返回，不修改模型温度"""
        agent.model = Mock()
        agent.model.temperature = 0.9
        _patch_get_llm_config(monkeypatch, lambda *a, **k: {"temperature": None})
        agent._apply_task_temperature(None)
        assert agent.model.temperature == 0.9

    def test_pinned_temperature_wins(self, agent, monkeypatch):
        """llm_config 显式锁定 temperature 时不做自动调整"""
        agent.model = Mock()
        agent.model.temperature = 0.9
        _patch_get_llm_config(monkeypatch, lambda *a, **k: {"temperature": 0.42})
        agent._apply_task_temperature(0.7)
        assert agent.model.temperature == 0.9

    def test_clamps_low_value(self, agent, monkeypatch):
        """低于 0.1 的温度被钳到 0.1"""
        agent.model = Mock()
        agent.model.temperature = 0.9
        _patch_get_llm_config(monkeypatch, lambda *a, **k: {})
        agent._apply_task_temperature(0.01)
        assert agent.model.temperature == 0.1

    def test_clamps_high_value(self, agent, monkeypatch):
        """高于 1.5 的温度被钳到 1.5"""
        agent.model = Mock()
        agent.model.temperature = 0.9
        _patch_get_llm_config(monkeypatch, lambda *a, **k: {})
        agent._apply_task_temperature(3.0)
        assert agent.model.temperature == 1.5

    def test_normal_value_applied(self, agent, monkeypatch):
        """正常范围内的温度被原样应用"""
        agent.model = Mock()
        agent.model.temperature = 0.9
        _patch_get_llm_config(monkeypatch, lambda *a, **k: {})
        agent._apply_task_temperature(0.7)
        assert agent.model.temperature == 0.7

    def test_invalid_value_not_applied(self, agent, monkeypatch):
        """非法值（无法转 float）不设置 temperature"""
        agent.model = Mock()
        agent.model.temperature = 0.9
        _patch_get_llm_config(monkeypatch, lambda *a, **k: {})
        agent._apply_task_temperature("not-a-number")
        assert agent.model.temperature == 0.9

    def test_model_without_temperature_attr(self, agent, monkeypatch):
        """model 无 temperature 属性时不设置，且不抛异常"""
        model = Mock(spec=["platform_type"])
        model.platform_type = "normal"
        agent.model = model
        _patch_get_llm_config(monkeypatch, lambda *a, **k: {})
        agent._apply_task_temperature(0.7)  # 不应抛异常

    def test_exception_is_swallowed(self, agent, monkeypatch):
        """内部异常被吞掉，不影响主流程"""
        agent.model = Mock()
        agent.model.temperature = 0.9

        def boom(*a, **k):
            raise RuntimeError("配置读取失败")

        _patch_get_llm_config(monkeypatch, boom)
        # get_llm_config 抛异常时 pinned 回退为 None，随后正常设置温度
        agent._apply_task_temperature(0.6)
        assert agent.model.temperature == 0.6


class TestCreateTempModel:
    """_create_temp_model 创建临时模型实例"""

    @pytest.fixture
    def agent(self):
        ag = _make_agent()
        _bind(ag, "_create_temp_model")
        # 默认模型（未被强制指定时使用其 platform_type）
        ag.model = Mock()
        ag.model.platform_type = "normal"
        return ag

    def _patch_registry(self, monkeypatch, registry):
        """patch 模块级 PlatformRegistry 名字为返回指定 registry 的工厂

        重构后实现位于 model_switcher.py，需 patch 该模块的全局名。
        """
        monkeypatch.setattr(
            "jarvis.jarvis_agent.model_switcher.PlatformRegistry",
            lambda *a, **k: registry,
        )

    def test_create_platform_uses_current_platform_type(self, agent, monkeypatch):
        """无 force_model_type 时使用当前模型的 platform_type 创建平台"""
        temp_model = Mock()
        registry = Mock()
        registry.create_platform = Mock(return_value=temp_model)
        self._patch_registry(monkeypatch, registry)

        result = agent._create_temp_model()

        registry.create_platform.assert_called_once_with("normal")
        assert result is temp_model
        temp_model.set_suppress_output.assert_called_once_with(False)
        temp_model.set_system_prompt.assert_not_called()

    @pytest.mark.parametrize(
        "force_type,getter",
        [
            ("smart", "get_smart_platform"),
            ("cheap", "get_cheap_platform"),
            ("normal", "get_normal_platform"),
        ],
    )
    def test_force_model_type_dispatches(self, agent, monkeypatch, force_type, getter):
        """force_model_type 分别走对应的 get_*_platform 分支"""
        temp_model = Mock()
        registry = Mock()
        setattr(registry, getter, Mock(return_value=temp_model))
        self._patch_registry(monkeypatch, registry)

        result = agent._create_temp_model(force_model_type=force_type)

        getattr(registry, getter).assert_called_once()
        assert result is temp_model

    def test_system_prompt_applied_when_non_empty(self, agent, monkeypatch):
        """system_prompt 非空时调用 set_system_prompt"""
        temp_model = Mock()
        registry = Mock()
        registry.create_platform = Mock(return_value=temp_model)
        self._patch_registry(monkeypatch, registry)

        agent._create_temp_model(system_prompt="你是助手")

        temp_model.set_system_prompt.assert_called_once_with("你是助手")

    def test_creation_failure_raises_runtime_error(self, agent, monkeypatch):
        """创建失败（返回 None）时抛 RuntimeError"""
        registry = Mock()
        registry.create_platform = Mock(return_value=None)
        self._patch_registry(monkeypatch, registry)

        with pytest.raises(RuntimeError):
            agent._create_temp_model()

    def test_always_disables_output_suppression(self, agent, monkeypatch):
        """无论是否传 system_prompt，始终调用 set_suppress_output(False)"""
        temp_model = Mock()
        registry = Mock()
        registry.create_platform = Mock(return_value=temp_model)
        self._patch_registry(monkeypatch, registry)

        agent._create_temp_model(system_prompt="提示词")

        temp_model.set_suppress_output.assert_called_once_with(False)
