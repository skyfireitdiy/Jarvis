# -*- coding: utf-8 -*-
"""输入源 / 输出源扩展点测试（NLSpec: io-sources）

覆盖：
- 扩展点字段白名单（utils._PLUGIN_EXTENSION_FIELDS / _PLUGIN_EXTENSION_FIELD_API_VERSION）
- config.get_input_source_dirs / get_output_source_dirs
- PluginRegistry 输入/输出源登记与撤销（可逆效应）
- io_sources 模块：OutputMessage dataclass、输入/输出源加载、输出异步广播
- 卸载时 stop() 钩子调用

测试范式沿用 tests/jarvis_agent/test_callback_loading.py：
使用 tmp_path 构造真实目录与 .py 文件，Mock agent。
"""
import sys
import time
from unittest.mock import Mock

import pytest

from jarvis.jarvis_utils import utils as jarvis_utils
from jarvis.jarvis_utils import config as jarvis_config
from jarvis.jarvis_tools.plugin_registry import PluginRegistry


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _write_py(directory, name, content):
    """在指定目录写入一个 .py 文件并返回其路径"""
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


def _make_agent(**attrs):
    """创建一个 Mock agent，并设置 io_sources 所需的最小属性"""
    ag = Mock()
    ag.name = "test_agent"
    ag.model = Mock()
    ag.model.model_name = "test-model"
    for k, v in attrs.items():
        setattr(ag, k, v)
    return ag


@pytest.fixture(autouse=True)
def _reset_registry():
    """每个测试后清空 PluginRegistry，避免测试间干扰"""
    yield
    PluginRegistry.instance().clear()


@pytest.fixture(autouse=True)
def _reset_io_sources():
    """每个测试后清空 io_sources 模块的全局缓存与执行器，并清理测试导入的模块"""
    yield
    try:
        from jarvis.jarvis_agent import io_sources

        io_sources._registered_input_sources.clear()
        io_sources._registered_output_sources.clear()
        # 清理测试期间加载的 io_sources 模块，避免跨测试 sys.modules 缓存污染
        for name in list(sys.modules.keys()):
            if name.startswith("jarvis_io_sources_"):
                sys.modules.pop(name, None)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 1. 扩展点字段白名单
# ---------------------------------------------------------------------------
class TestExtensionFields:
    def test_extension_fields_whitelist_contains_io_sources(self):
        """_PLUGIN_EXTENSION_FIELDS 应包含 input_sources / output_sources"""
        assert "input_sources" in jarvis_utils._PLUGIN_EXTENSION_FIELDS
        assert "output_sources" in jarvis_utils._PLUGIN_EXTENSION_FIELDS

    def test_extension_field_api_version_contains_io_sources(self):
        """_PLUGIN_EXTENSION_FIELD_API_VERSION 应登记两个新字段"""
        assert "input_sources" in jarvis_utils._PLUGIN_EXTENSION_FIELD_API_VERSION
        assert "output_sources" in jarvis_utils._PLUGIN_EXTENSION_FIELD_API_VERSION


# ---------------------------------------------------------------------------
# 2. config getter
# ---------------------------------------------------------------------------
class TestConfigGetters:
    def test_get_input_source_dirs_reads_global_config(self, monkeypatch):
        """get_input_source_dirs 从 GLOBAL_CONFIG_DATA 读取并展开路径"""
        monkeypatch.setattr(
            jarvis_config,
            "GLOBAL_CONFIG_DATA",
            {"input_sources": ["~/src1", "${HOME}/src2"]},
        )
        monkeypatch.setenv("HOME", "/home/test")
        dirs = jarvis_config.get_input_source_dirs()
        assert dirs == ["/home/test/src1", "/home/test/src2"]

    def test_get_output_source_dirs_reads_global_config(self, monkeypatch):
        """get_output_source_dirs 从 GLOBAL_CONFIG_DATA 读取并展开路径"""
        monkeypatch.setattr(
            jarvis_config,
            "GLOBAL_CONFIG_DATA",
            {"output_sources": ["/abs/out"]},
        )
        dirs = jarvis_config.get_output_source_dirs()
        assert dirs == ["/abs/out"]

    def test_get_plugin_hook_dirs_expands_io_source_dirs(self, monkeypatch):
        """get_plugin_hook_dirs 的 dir_fields 应包含 input_sources/output_sources"""
        monkeypatch.setattr(
            jarvis_config,
            "GLOBAL_CONFIG_DATA",
            {
                "plugin_configs": {
                    "demo": {
                        "input_sources": ["/abs/in"],
                        "output_sources": ["/abs/out"],
                    }
                }
            },
        )
        hooks = jarvis_config.get_plugin_hook_dirs("demo")
        assert hooks.get("input_sources") == ["/abs/in"]
        assert hooks.get("output_sources") == ["/abs/out"]


# ---------------------------------------------------------------------------
# 3. PluginRegistry 登记与撤销
# ---------------------------------------------------------------------------
class TestPluginRegistry:
    def test_register_and_get_input_source(self):
        """register_input_source 登记，get_plugin_input_sources 查询"""
        reg = PluginRegistry.instance()
        reg.register_input_source("demo", "mic")
        assert reg.get_plugin_input_sources("demo") == ["mic"]

    def test_register_and_get_output_source(self):
        """register_output_source 登记，get_plugin_output_sources 查询"""
        reg = PluginRegistry.instance()
        reg.register_output_source("demo", "speaker")
        assert reg.get_plugin_output_sources("demo") == ["speaker"]

    def test_register_batch(self):
        """register_input_sources / register_output_sources 批量登记"""
        reg = PluginRegistry.instance()
        reg.register_input_sources("demo", ["a", "b"])
        reg.register_output_sources("demo", ["c"])
        assert reg.get_plugin_input_sources("demo") == ["a", "b"]
        assert reg.get_plugin_output_sources("demo") == ["c"]

    def test_unregister_plugin_returns_io_sources(self):
        """unregister_plugin 返回 dict 应含 input_sources/output_sources 并清理"""
        reg = PluginRegistry.instance()
        reg.register_input_source("demo", "mic")
        reg.register_output_source("demo", "speaker")
        result = reg.unregister_plugin("demo")
        assert result["input_sources"] == ["mic"]
        assert result["output_sources"] == ["speaker"]
        assert reg.get_plugin_input_sources("demo") == []
        assert reg.get_plugin_output_sources("demo") == []

    def test_revoke_plugin_counts_io_sources(self):
        """revoke_plugin 返回 dict 应含 input_sources/output_sources 计数"""
        reg = PluginRegistry.instance()
        reg.register_input_source("demo", "mic")
        reg.register_output_source("demo", "speaker")
        result = reg.revoke_plugin("demo")
        assert result["input_sources"] == 1
        assert result["output_sources"] == 1
        assert not reg.has_plugin("demo")

    def test_has_plugin_considers_io_sources(self):
        """has_plugin 应识别仅登记了输入/输出源的插件"""
        reg = PluginRegistry.instance()
        assert not reg.has_plugin("demo")
        reg.register_input_source("demo", "mic")
        assert reg.has_plugin("demo")

    def test_registered_plugins_considers_io_sources(self):
        """registered_plugins 应包含仅登记了输入/输出源的插件"""
        reg = PluginRegistry.instance()
        reg.register_output_source("demo", "speaker")
        assert "demo" in reg.registered_plugins()

    def test_clear_resets_io_sources(self):
        """clear 应清空输入/输出源登记"""
        reg = PluginRegistry.instance()
        reg.register_input_source("demo", "mic")
        reg.clear()
        assert reg.get_plugin_input_sources("demo") == []


# ---------------------------------------------------------------------------
# 4. OutputMessage dataclass
# ---------------------------------------------------------------------------
class TestOutputMessage:
    def test_output_message_fields(self):
        """OutputMessage 应含 text/agent_name/model_name/timestamp/extra 字段"""
        from jarvis.jarvis_agent.io_sources import OutputMessage

        msg = OutputMessage(
            text="hello",
            agent_name="agent1",
            model_name="model-x",
            timestamp=123.0,
            extra={"k": "v"},
        )
        assert msg.text == "hello"
        assert msg.agent_name == "agent1"
        assert msg.model_name == "model-x"
        assert msg.timestamp == 123.0
        assert msg.extra == {"k": "v"}

    def test_output_message_frozen(self):
        """OutputMessage 应为 frozen dataclass（不可变）"""
        from dataclasses import FrozenInstanceError

        from jarvis.jarvis_agent.io_sources import OutputMessage

        msg = OutputMessage(text="hello", agent_name="a", model_name="", timestamp=1.0)
        with pytest.raises(FrozenInstanceError):
            msg.text = "changed"

    def test_output_message_extra_default(self):
        """extra 默认应为空 dict"""
        from jarvis.jarvis_agent.io_sources import OutputMessage

        msg = OutputMessage(text="hello", agent_name="a", model_name="", timestamp=1.0)
        assert msg.extra == {}


# ---------------------------------------------------------------------------
# 5. 输入源加载
# ---------------------------------------------------------------------------
class TestInputSourceLoading:
    def test_load_input_source_module_level_cb(self, tmp_path):
        """模块级 input_source_cb（带 source_name）应被加载并启动"""
        from jarvis.jarvis_agent import io_sources

        _write_py(
            tmp_path,
            "mic_source.py",
            "started = []\n"
            "def input_source_cb(agent, **kwargs):\n"
            "    started.append(agent.name)\n"
            "input_source_cb.source_name = 'mic'\n",
        )
        agent = _make_agent()
        io_sources.load_input_sources([str(tmp_path)], "demo", agent)
        assert io_sources._registered_input_sources.get("mic") is not None
        # 回调应已被调用（启动后台监听）
        mod_name = io_sources._unique_module_name("demo", tmp_path / "mic_source.py")
        assert sys.modules[mod_name].started == ["test_agent"]
        # 应登记到 PluginRegistry
        assert PluginRegistry.instance().get_plugin_input_sources("demo") == ["mic"]

    def test_load_input_source_factory(self, tmp_path):
        """get_input_source_cb() 工厂应被支持"""
        from jarvis.jarvis_agent import io_sources

        _write_py(
            tmp_path,
            "factory_source.py",
            "started = []\n"
            "def _cb(agent, **kwargs):\n"
            "    started.append(1)\n"
            "_cb.source_name = 'factory'\n"
            "def get_input_source_cb():\n"
            "    return _cb\n",
        )
        agent = _make_agent()
        io_sources.load_input_sources([str(tmp_path)], "demo", agent)
        assert io_sources._registered_input_sources.get("factory") is not None
        mod_name = io_sources._unique_module_name("demo", tmp_path / "factory_source.py")
        assert sys.modules[mod_name].started == [1]

    def test_load_input_source_register_factory(self, tmp_path):
        """register_input_source_cb() 工厂应被支持"""
        from jarvis.jarvis_agent import io_sources

        _write_py(
            tmp_path,
            "reg_source.py",
            "started = []\n"
            "def _cb(agent, **kwargs):\n"
            "    started.append(1)\n"
            "_cb.source_name = 'reg'\n"
            "def register_input_source_cb():\n"
            "    return _cb\n",
        )
        agent = _make_agent()
        io_sources.load_input_sources([str(tmp_path)], "demo", agent)
        assert io_sources._registered_input_sources.get("reg") is not None
        mod_name = io_sources._unique_module_name("demo", tmp_path / "reg_source.py")
        assert sys.modules[mod_name].started == [1]

    def test_load_input_source_missing_source_name_skipped(self, tmp_path):
        """缺少 source_name 的 input_source_cb 应被跳过（不启动、不登记）"""
        from jarvis.jarvis_agent import io_sources

        _write_py(
            tmp_path,
            "bad_source.py",
            "started = []\n"
            "def input_source_cb(agent, **kwargs):\n"
            "    started.append(1)\n",
        )
        agent = _make_agent()
        io_sources.load_input_sources([str(tmp_path)], "demo", agent)
        mod_name = io_sources._unique_module_name("demo", tmp_path / "bad_source.py")
        assert sys.modules[mod_name].started == []
        assert PluginRegistry.instance().get_plugin_input_sources("demo") == []

    def test_load_input_source_skips_init_py(self, tmp_path):
        """__init__.py 应被跳过"""
        from jarvis.jarvis_agent import io_sources

        _write_py(tmp_path, "__init__.py", "raise RuntimeError('should not import')")
        agent = _make_agent()
        # 不应抛异常
        io_sources.load_input_sources([str(tmp_path)], "demo", agent)
        assert PluginRegistry.instance().get_plugin_input_sources("demo") == []

    def test_load_input_source_requirements_comment(self, tmp_path, monkeypatch):
        """# requirements: 注释应被解析并触发依赖安装"""
        from jarvis.jarvis_agent import io_sources

        _write_py(
            tmp_path,
            "req_source.py",
            "# requirements: somepkg\n"
            "def input_source_cb(agent, **kwargs):\n"
            "    pass\n"
            "input_source_cb.source_name = 'req'\n",
        )
        installed = []

        def fake_run(cmd, **kwargs):
            installed.append(cmd)
            return Mock(returncode=0, stderr="")

        monkeypatch.setattr(io_sources.subprocess, "run", fake_run)
        agent = _make_agent()
        io_sources.load_input_sources([str(tmp_path)], "demo", agent)
        assert any("somepkg" in c for c in installed)

    def test_load_input_source_exception_isolated(self, tmp_path):
        """单个输入源启动失败不应影响其他源"""
        from jarvis.jarvis_agent import io_sources

        _write_py(
            tmp_path,
            "bad_source.py",
            "def input_source_cb(agent, **kwargs):\n"
            "    raise RuntimeError('boom')\n"
            "input_source_cb.source_name = 'bad'\n",
        )
        _write_py(
            tmp_path,
            "good_source.py",
            "def input_source_cb(agent, **kwargs):\n"
            "    pass\n"
            "input_source_cb.source_name = 'good'\n",
        )
        agent = _make_agent()
        # 不应抛异常
        io_sources.load_input_sources([str(tmp_path)], "demo", agent)
        assert PluginRegistry.instance().get_plugin_input_sources("demo") == ["good"]

    def test_load_input_source_same_name_different_dirs(self, tmp_path):
        """不同目录下的同名 .py 文件应独立加载（无 sys.modules 缓存碰撞）"""
        from jarvis.jarvis_agent import io_sources

        d1 = tmp_path / "d1"
        d2 = tmp_path / "d2"
        d1.mkdir()
        d2.mkdir()
        _write_py(
            d1,
            "mic.py",
            "def input_source_cb(agent, **kwargs):\n"
            "    pass\n"
            "input_source_cb.source_name = 'mic_pluginA'\n",
        )
        _write_py(
            d2,
            "mic.py",
            "def input_source_cb(agent, **kwargs):\n"
            "    pass\n"
            "input_source_cb.source_name = 'mic_pluginB'\n",
        )
        agent = _make_agent()
        io_sources.load_input_sources([str(d1)], "pluginA", agent)
        io_sources.load_input_sources([str(d2)], "pluginB", agent)
        # 两个插件的同名文件都应被独立登记
        assert PluginRegistry.instance().get_plugin_input_sources("pluginA") == [
            "mic_pluginA"
        ]
        assert PluginRegistry.instance().get_plugin_input_sources("pluginB") == [
            "mic_pluginB"
        ]
        assert io_sources._registered_input_sources.get("mic_pluginA") is not None
        assert io_sources._registered_input_sources.get("mic_pluginB") is not None

    def test_stop_hook_called_on_uninstall(self, tmp_path):
        """卸载时应对已登记输入源调用 stop() 钩子"""
        from jarvis.jarvis_agent import io_sources

        _write_py(
            tmp_path,
            "stop_source.py",
            "stopped = []\n"
            "def input_source_cb(agent, **kwargs):\n"
            "    pass\n"
            "input_source_cb.source_name = 'stopable'\n"
            "def stop():\n"
            "    stopped.append(1)\n",
        )
        agent = _make_agent()
        io_sources.load_input_sources([str(tmp_path)], "demo", agent)
        io_sources.stop_input_sources("demo")
        mod_name = io_sources._unique_module_name("demo", tmp_path / "stop_source.py")
        assert sys.modules[mod_name].stopped == [1]
        # 撤销后登记应清空
        assert PluginRegistry.instance().get_plugin_input_sources("demo") == []


# ---------------------------------------------------------------------------
# 6. 输出源加载
# ---------------------------------------------------------------------------
class TestOutputSourceLoading:
    def test_load_output_source_module_level_cb(self, tmp_path):
        """模块级 output_source_cb（带 source_name）应被加载并登记"""
        from jarvis.jarvis_agent import io_sources

        _write_py(
            tmp_path,
            "speaker.py",
            "def output_source_cb(message, agent, **kwargs):\n"
            "    pass\n"
            "output_source_cb.source_name = 'speaker'\n",
        )
        agent = _make_agent()
        io_sources.load_output_sources([str(tmp_path)], "demo", agent)
        assert io_sources._registered_output_sources.get("speaker") is not None
        assert PluginRegistry.instance().get_plugin_output_sources("demo") == [
            "speaker"
        ]

    def test_load_output_source_factory(self, tmp_path):
        """get_output_source_cb() 工厂应被支持"""
        from jarvis.jarvis_agent import io_sources

        _write_py(
            tmp_path,
            "factory_out.py",
            "def _cb(message, agent, **kwargs):\n"
            "    pass\n"
            "_cb.source_name = 'factory_out'\n"
            "def get_output_source_cb():\n"
            "    return _cb\n",
        )
        agent = _make_agent()
        io_sources.load_output_sources([str(tmp_path)], "demo", agent)
        assert io_sources._registered_output_sources.get("factory_out") is not None

    def test_load_output_source_missing_source_name_skipped(self, tmp_path):
        """缺少 source_name 的 output_source_cb 应被跳过"""
        from jarvis.jarvis_agent import io_sources

        _write_py(
            tmp_path,
            "bad_out.py",
            "def output_source_cb(message, agent, **kwargs):\n"
            "    pass\n",
        )
        agent = _make_agent()
        io_sources.load_output_sources([str(tmp_path)], "demo", agent)
        assert PluginRegistry.instance().get_plugin_output_sources("demo") == []


# ---------------------------------------------------------------------------
# 7. 输出异步广播
# ---------------------------------------------------------------------------
class TestOutputBroadcast:
    def test_broadcast_delivers_to_all_output_sources(self, tmp_path):
        """广播应让所有已注册输出源都收到同一 OutputMessage"""
        from jarvis.jarvis_agent import io_sources
        from jarvis.jarvis_agent.io_sources import OutputMessage

        received = []

        def cb1(message, agent, **kwargs):
            received.append((message, agent.name))

        cb1.source_name = "out1"

        def cb2(message, agent, **kwargs):
            received.append((message, agent.name))

        cb2.source_name = "out2"

        io_sources._registered_output_sources["out1"] = cb1
        io_sources._registered_output_sources["out2"] = cb2

        agent = _make_agent()
        io_sources.broadcast_output_message(agent, "final reply")

        # 等待异步投递完成
        deadline = time.time() + 5
        while len(received) < 2 and time.time() < deadline:
            time.sleep(0.05)

        assert len(received) == 2
        for msg, agent_name in received:
            assert isinstance(msg, OutputMessage)
            assert msg.text == "final reply"
            assert msg.agent_name == "test_agent"
            assert msg.model_name == "test-model"
            assert agent_name == "test_agent"

    def test_broadcast_exception_isolated(self, tmp_path):
        """单个输出源异常不应影响其他输出源"""
        from jarvis.jarvis_agent import io_sources

        received = []

        def bad_cb(message, agent, **kwargs):
            raise RuntimeError("boom")

        bad_cb.source_name = "bad"

        def good_cb(message, agent, **kwargs):
            received.append(message.text)

        good_cb.source_name = "good"

        io_sources._registered_output_sources["bad"] = bad_cb
        io_sources._registered_output_sources["good"] = good_cb

        agent = _make_agent()
        # 不应抛异常
        io_sources.broadcast_output_message(agent, "reply")

        deadline = time.time() + 5
        while not received and time.time() < deadline:
            time.sleep(0.05)
        assert received == ["reply"]

    def test_broadcast_no_output_sources(self):
        """无输出源时广播不应报错"""
        from jarvis.jarvis_agent import io_sources

        agent = _make_agent()
        io_sources.broadcast_output_message(agent, "reply")

    def test_broadcast_does_not_block(self):
        """广播应异步返回，不等待输出源处理完成"""
        from jarvis.jarvis_agent import io_sources

        entered = []

        def slow_cb(message, agent, **kwargs):
            entered.append(1)
            time.sleep(1.0)

        slow_cb.source_name = "slow"
        io_sources._registered_output_sources["slow"] = slow_cb

        agent = _make_agent()
        start = time.time()
        io_sources.broadcast_output_message(agent, "reply")
        elapsed = time.time() - start
        # 广播本身应立即返回（远小于 1 秒）
        assert elapsed < 0.5
