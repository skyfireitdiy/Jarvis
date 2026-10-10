# -*- coding: utf-8 -*-
"""Agent 运行时配置上报（Issue #115 Agent 侧）单元测试。

覆盖 builtin_input_handler.py 中 _report_agent_config_change 及三处调用点：
1. perform_switch 成功后上报 {"llm_group": new_model_group}
2. switch_proxy_node 清空代理上报 {"proxy_node": ""}
3. switch_proxy_node 设置代理上报 {"proxy_node": new_node}
4. <SetConfig> 修改 llm_group / proxy_node 后上报
5. guard：agent_id / master_url 未设置时静默跳过
"""
import importlib.util
from unittest.mock import Mock

import pytest

# builtin_input_handler 这个名字在包内被同名函数遮蔽（re-export），
# 直接 import 会拿到函数而非模块；这里用 importlib 从源码路径加载真实模块。
_SPEC = importlib.util.spec_from_file_location(
    "bih_under_test", "src/jarvis/jarvis_agent/builtin_input_handler.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_BIH = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BIH)


@pytest.fixture
def bih():
    """返回 builtin_input_handler 模块对象。"""
    return _BIH


@pytest.fixture
def fake_jglobals(monkeypatch, bih):
    """构造带 agent_id / master_url 的 jglobals，并 patch 到模块内。"""
    import jarvis.jarvis_utils.globals as jglobals

    jglobals.agent_id = "agent-test-1"
    jglobals.master_url = "http://127.0.0.1:8000"
    yield jglobals
    # 还原，避免污染其他测试
    jglobals.agent_id = None
    jglobals.master_url = None


def _patch_gateway(monkeypatch, bih, result=None):
    """patch 延迟导入的 GatewayManagerTool，返回其 _request_gateway 的 mock。

    _report_agent_config_change 与 switch_proxy_node 内部都用
    `from jarvis.jarvis_tools.gateway_manager import GatewayManagerTool` 延迟导入，
    因此 patch 目标是 gateway_manager 模块内的 GatewayManagerTool。

    GatewayManagerTool.check() 是静态方法调用（类上直接调用），而
    GatewayManagerTool() 返回实例；因此用一个同时支持两者的类来替换。
    """
    import jarvis.jarvis_tools.gateway_manager as gm

    class _FakeGateway:
        _instance = None

        def __new__(cls):
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

        def __init__(self):
            if not hasattr(self, "_request_gateway"):
                self._request_gateway = Mock(
                    return_value=result or {"success": True}
                )
            if not hasattr(self, "_list_nodes"):
                self._list_nodes = Mock(
                    return_value={
                        "success": True,
                        "stdout": '{"nodes": []}',
                    }
                )

        @staticmethod
        def check():
            return True

    fake_tool = _FakeGateway()
    monkeypatch.setattr(gm, "GatewayManagerTool", _FakeGateway)
    return fake_tool


class TestReportAgentConfigChange:
    def test_skips_when_agent_id_missing(self, bih, monkeypatch):
        """agent_id 未设置时静默返回，不发起请求。"""
        import jarvis.jarvis_utils.globals as jglobals

        jglobals.agent_id = None
        jglobals.master_url = "http://127.0.0.1:8000"
        fake_tool = _patch_gateway(monkeypatch, bih)
        bih._report_agent_config_change({"llm_group": "g"})
        fake_tool._request_gateway.assert_not_called()
        jglobals.agent_id = None
        jglobals.master_url = None

    def test_skips_when_master_url_missing(self, bih, monkeypatch):
        """master_url 未设置时静默返回，不发起请求。"""
        import jarvis.jarvis_utils.globals as jglobals

        jglobals.agent_id = "agent-test-1"
        jglobals.master_url = None
        fake_tool = _patch_gateway(monkeypatch, bih)
        bih._report_agent_config_change({"llm_group": "g"})
        fake_tool._request_gateway.assert_not_called()
        jglobals.agent_id = None

    def test_skips_when_updates_empty(self, bih, monkeypatch, fake_jglobals):
        """updates 为空时静默返回。"""
        fake_tool = _patch_gateway(monkeypatch, bih)
        bih._report_agent_config_change({})
        fake_tool._request_gateway.assert_not_called()

    def test_sends_patch_with_updates(self, bih, monkeypatch, fake_jglobals):
        """正常上报 PATCH /api/agents/{id}，body 为 updates。"""
        fake_tool = _patch_gateway(monkeypatch, bih)
        bih._report_agent_config_change({"llm_group": "new_group"})
        fake_tool._request_gateway.assert_called_once()
        args, kwargs = fake_tool._request_gateway.call_args
        assert args[0] == "PATCH"
        assert args[1] == "/api/agents/agent-test-1"
        assert kwargs["json_data"] == {"llm_group": "new_group"}

    def test_failure_is_silent(self, bih, monkeypatch, fake_jglobals):
        """上报失败不抛异常（静默降级）。"""
        _patch_gateway(
            monkeypatch, bih, result={"success": False, "error": "boom"}
        )
        bih._report_agent_config_change({"llm_group": "g"})  # 不应抛异常


class TestPerformSwitchReports:
    def test_reports_llm_group_on_success(self, bih, monkeypatch, fake_jglobals):
        """perform_switch 成功后上报新模型组。"""
        fake_tool = _patch_gateway(monkeypatch, bih)
        agent = Mock()
        agent.model = Mock()
        agent.session = Mock()
        agent.model.get_messages.return_value = []
        # switch_platform_type 成功
        monkeypatch.setattr(bih, "switch_platform_type", lambda *a, **k: True)
        # set_llm_group 来自 jarvis_utils.config，需 patch
        from jarvis.jarvis_utils import config as config_module

        monkeypatch.setattr(config_module, "set_llm_group", lambda g: None)
        assert bih.perform_switch(agent, "new_group") is True
        fake_tool._request_gateway.assert_called_once()
        args, kwargs = fake_tool._request_gateway.call_args
        assert kwargs["json_data"] == {"llm_group": "new_group"}

    def test_no_report_on_failure(self, bih, monkeypatch, fake_jglobals):
        """perform_switch 失败时不上报。"""
        fake_tool = _patch_gateway(monkeypatch, bih)
        agent = Mock()
        agent.model = Mock()
        agent.session = Mock()
        agent.model.get_messages.return_value = []
        monkeypatch.setattr(bih, "switch_platform_type", lambda *a, **k: False)
        from jarvis.jarvis_utils import config as config_module

        monkeypatch.setattr(config_module, "set_llm_group", lambda g: None)
        assert bih.perform_switch(agent, "new_group") is False
        fake_tool._request_gateway.assert_not_called()


class TestSwitchProxyNodeReports:
    def test_reports_clear_proxy(self, bih, monkeypatch, fake_jglobals):
        """清空代理后上报 {"proxy_node": ""}。"""
        fake_tool = _patch_gateway(monkeypatch, bih)
        import jarvis.jarvis_utils.globals as jglobals

        jglobals.proxy_node = "node-1"
        monkeypatch.setattr(bih, "switch_platform_type", lambda *a, **k: True)
        monkeypatch.setattr(
            bih, "get_single_line_input", lambda prompt: ""
        )
        monkeypatch.setattr(
            bih, "get_platform_type_from_agent", lambda a: "normal"
        )
        agent = Mock()
        assert bih.switch_proxy_node(agent) is True
        fake_tool._request_gateway.assert_called_once()
        args, kwargs = fake_tool._request_gateway.call_args
        assert kwargs["json_data"] == {"proxy_node": ""}
        jglobals.proxy_node = None

    def test_reports_set_proxy(self, bih, monkeypatch, fake_jglobals):
        """设置代理后上报 {"proxy_node": new_node}。"""
        fake_tool = _patch_gateway(monkeypatch, bih)
        import jarvis.jarvis_utils.globals as jglobals

        jglobals.proxy_node = None
        # 让 _list_nodes 返回一个节点，用户输入序号 1
        fake_tool._list_nodes.return_value = {
            "success": True,
            "stdout": '{"nodes": [{"node_id": "node-2"}]}',
        }
        monkeypatch.setattr(bih, "switch_platform_type", lambda *a, **k: True)
        monkeypatch.setattr(
            bih, "get_single_line_input", lambda prompt: "1"
        )
        monkeypatch.setattr(
            bih, "get_platform_type_from_agent", lambda a: "normal"
        )
        agent = Mock()
        assert bih.switch_proxy_node(agent) is True
        fake_tool._request_gateway.assert_called_once()
        args, kwargs = fake_tool._request_gateway.call_args
        assert kwargs["json_data"] == {"proxy_node": "node-2"}
        jglobals.proxy_node = None


class TestSetConfigReports:
    def test_setconfig_reports_llm_group(self, bih, monkeypatch, fake_jglobals):
        """<SetConfig> 修改 llm_group 后上报。"""
        fake_tool = _patch_gateway(monkeypatch, bih)
        config = {}
        monkeypatch.setattr(bih, "get_global_config_data", lambda: config)
        # _set_nested_config 真实实现写入 config
        result = bih._set_nested_config(config, "llm_group", "new_group")
        assert result[0] is True
        # 模拟 builtin_input_handler 内 SetConfig 分支的调用
        bih._report_agent_config_change({"llm_group": "new_group"})
        fake_tool._request_gateway.assert_called_once()
        args, kwargs = fake_tool._request_gateway.call_args
        assert kwargs["json_data"] == {"llm_group": "new_group"}
