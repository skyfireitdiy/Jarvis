# -*- coding: utf-8 -*-
"""wait_for_message 工具与 get_multiline_input ignore_auto_complete 参数测试"""
from unittest.mock import patch

from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_tools.wait_for_message import WaitForMessageTool
from jarvis.jarvis_utils.input import get_multiline_input


class TestGetMultilineInputIgnoreAutoComplete:
    """get_multiline_input 的 ignore_auto_complete 参数行为"""

    def test_default_behavior_non_interactive_auto_complete(self):
        """默认（ignore_auto_complete=False）：非交互 + auto_complete=True 时仍补 !!!COMPLETE!!!"""
        with patch(
            "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
            return_value=True,
        ), patch(
            "jarvis.jarvis_utils.input._is_auto_complete_for_current_agent",
            return_value=True,
        ):
            result = get_multiline_input("tip")
        assert "!!!COMPLETE!!!" in result

    def test_default_behavior_non_interactive_no_auto_complete(self):
        """默认：非交互 + auto_complete=False 时不补 !!!COMPLETE!!!，但仍走非交互分支"""
        with patch(
            "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
            return_value=True,
        ), patch(
            "jarvis.jarvis_utils.input._is_auto_complete_for_current_agent",
            return_value=False,
        ):
            result = get_multiline_input("tip")
        assert "!!!COMPLETE!!!" not in result

    def test_ignore_auto_complete_skips_non_interactive_branch(self):
        """ignore_auto_complete=True：即使非交互 + auto_complete=True 也不补 !!!COMPLETE!!!，进入真实等待"""
        with patch(
            "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
            return_value=True,
        ), patch(
            "jarvis.jarvis_utils.input._is_auto_complete_for_current_agent",
            return_value=True,
        ), patch(
            "jarvis.jarvis_utils.input.get_current_input_provider"
        ) as mock_provider, patch(
            "jarvis.jarvis_gateway.manager.get_current_gateway", return_value=None
        ):
            provider = mock_provider.return_value
            provider.get_multiline_input.return_value = "来自其他 Agent 的消息"
            result = get_multiline_input(
                "tip", print_on_empty=False, ignore_auto_complete=True
            )
        assert result == "来自其他 Agent 的消息"
        provider.get_multiline_input.assert_called_once()

    def test_timeout_passed_to_gateway_request(self):
        """timeout 透传到 GatewayInputRequest"""
        mock_gateway = _FakeGateway()
        with patch(
            "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
            return_value=False,
        ), patch(
            "jarvis.jarvis_gateway.manager.get_current_gateway",
            return_value=mock_gateway,
        ) as mock_get_gateway:
            result = get_multiline_input(
                "tip", print_on_empty=False, ignore_auto_complete=True, timeout=30
            )
        assert result == "收到消息"
        assert mock_gateway.captured["timeout"] == 30
        assert mock_gateway.captured["tip"] == "tip"
        assert mock_get_gateway.called


class GatewayInputResultStub:
    """GatewayInputResult 简化桩。"""

    def __init__(self, text):
        self.text = text
        self.metadata = None


class _FakeGateway:
    """记录 request_input 调用的假 Gateway。"""

    def __init__(self):
        self.captured = {}

    def request_input(self, request):
        self.captured["timeout"] = request.timeout
        self.captured["tip"] = request.tip
        return GatewayInputResultStub("收到消息")


class TestWaitForMessageTool:
    """wait_for_message 工具行为"""

    def test_check_only_gateway_mode(self):
        """check() 仅当存在 Gateway 时返回 True（CLI 模式不启用）"""
        with patch(
            "jarvis.jarvis_tools.wait_for_message.get_current_gateway",
            return_value=object(),
        ):
            assert WaitForMessageTool.check() is True
        with patch(
            "jarvis.jarvis_tools.wait_for_message.get_current_gateway",
            return_value=None,
        ):
            assert WaitForMessageTool.check() is False
        with patch(
            "jarvis.jarvis_tools.wait_for_message.get_current_gateway",
            side_effect=RuntimeError("boom"),
        ):
            assert WaitForMessageTool.check() is False

    def test_registration_skipped_without_gateway(self):
        """无 Gateway 时工具不注册（register_tool_by_file 跳过 check() 为 False 的工具）"""
        import jarvis.jarvis_tools.registry as registry_mod

        with patch(
            "jarvis.jarvis_tools.wait_for_message.get_current_gateway",
            return_value=None,
        ):
            registry_mod._BUILTIN_TOOLS_CACHE = None
            r = ToolRegistry()
            assert "wait_for_message" not in r.tools

    def test_registration_with_gateway(self):
        """有 Gateway 时工具注册"""
        import jarvis.jarvis_tools.registry as registry_mod

        with patch(
            "jarvis.jarvis_tools.wait_for_message.get_current_gateway",
            return_value=object(),
        ):
            registry_mod._BUILTIN_TOOLS_CACHE = None
            r = ToolRegistry()
            assert "wait_for_message" in r.tools

    def test_execute_returns_input(self):
        """execute 返回用户输入内容"""
        tool = WaitForMessageTool()
        with patch(
            "jarvis.jarvis_tools.wait_for_message.get_multiline_input",
            return_value="等待到的消息内容",
        ) as mock_input:
            result = tool.execute({})
        assert result["success"] is True
        assert result["stdout"] == "等待到的消息内容"
        # 必须传 ignore_auto_complete=True
        assert mock_input.call_args.kwargs.get("ignore_auto_complete") is True

    def test_execute_with_tip(self):
        """execute 透传 tip 参数"""
        tool = WaitForMessageTool()
        with patch(
            "jarvis.jarvis_tools.wait_for_message.get_multiline_input",
            return_value="内容",
        ) as mock_input:
            tool.execute({"tip": "请等待消息"})
        assert mock_input.call_args.args[0] == "请等待消息"

    def test_execute_with_timeout(self):
        """execute 透传 timeout 参数"""
        tool = WaitForMessageTool()
        with patch(
            "jarvis.jarvis_tools.wait_for_message.get_multiline_input",
            return_value="内容",
        ) as mock_input:
            tool.execute({"timeout": 30})
        assert mock_input.call_args.kwargs.get("timeout") == 30

    def test_execute_timeout_no_value(self):
        """未传 timeout 时默认为 None"""
        tool = WaitForMessageTool()
        with patch(
            "jarvis.jarvis_tools.wait_for_message.get_multiline_input",
            return_value="内容",
        ) as mock_input:
            tool.execute({})
        assert mock_input.call_args.kwargs.get("timeout") is None

    def test_execute_empty_input(self):
        """空输入返回 success: true, stdout: 空"""
        tool = WaitForMessageTool()
        with patch(
            "jarvis.jarvis_tools.wait_for_message.get_multiline_input",
            return_value="",
        ):
            result = tool.execute({})
        assert result["success"] is True
        assert result["stdout"] == ""

    def test_execute_exception(self):
        """异常时返回 success: false 与错误信息"""
        tool = WaitForMessageTool()
        with patch(
            "jarvis.jarvis_tools.wait_for_message.get_multiline_input",
            side_effect=RuntimeError("boom"),
        ):
            result = tool.execute({})
        assert result["success"] is False
        assert "boom" in result["stderr"]
