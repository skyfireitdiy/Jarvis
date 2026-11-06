# -*- coding: utf-8 -*-
"""code-update 流程依赖重装集成测试。

覆盖 NLSpec code-update-deps-reinstall 的 code-update 侧行为：
- git 成功后调用 reinstall_deps_after_update 并返回 deps_reinstall 字段
- 依赖重装失败不影响外层 success=true
- child 节点 include_frontend=False
- git 失败仍返回原错误码，不调用依赖重装
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.jarvis_web_gateway.node_manager import ChildNodeClient  # noqa: E402


def _make_manager(is_child: bool = False):
    """构造一个最小 ChildNodeClient（node_runtime 用 MagicMock）。"""
    node_runtime = MagicMock()
    node_runtime.config.is_child = is_child
    return ChildNodeClient(
        node_runtime=node_runtime,
        agent_manager=MagicMock(),
        agent_proxy_manager=MagicMock(),
        node_connection_manager=MagicMock(),
    )


class TestCodeUpdateDeps:
    """code-update 流程依赖重装。"""

    @patch(
        "jarvis.jarvis_utils.template_utils.get_jarvis_src_dir",
        return_value="/repo",
    )
    @patch(
        "jarvis.jarvis_utils.template_utils.checkout_jarvis_branch",
        return_value=(True, ""),
    )
    @patch(
        "jarvis.jarvis_utils.template_utils.pull_jarvis_code",
        return_value=(True, ""),
    )
    @patch(
        "jarvis.jarvis_utils.git_utils.reinstall_deps_after_update",
        return_value={
            "uv": {
                "attempted": True,
                "method": "uv_tool_install",
                "success": True,
                "detail": "uv tool install -e . --force 执行成功",
            },
            "npm": {
                "attempted": True,
                "success": True,
                "detail": "npm install 执行成功",
            },
        },
    )
    def test_git_success_calls_reinstall_and_returns_field(
        self, mock_reinstall, mock_pull, mock_checkout, mock_src
    ):
        """git 成功后调用依赖重装并返回 deps_reinstall 字段。"""
        m = _make_manager(is_child=False)
        result = asyncio.run(m._handle_code_update_to_main_request({"request_id": "r1"}))

        payload = result["payload"]
        assert payload["success"] is True
        data = payload["data"]
        assert "deps_reinstall" in data
        deps = data["deps_reinstall"]
        assert deps["uv"]["method"] == "uv_tool_install"
        assert deps["uv"]["success"] is True
        assert deps["npm"]["success"] is True
        # include_frontend 应为 True（master 节点）
        mock_reinstall.assert_called_once()
        kwargs = mock_reinstall.call_args
        assert kwargs.args[0] == "/repo"
        assert kwargs.kwargs.get("include_frontend") is True

    @patch(
        "jarvis.jarvis_utils.template_utils.get_jarvis_src_dir",
        return_value="/repo",
    )
    @patch(
        "jarvis.jarvis_utils.template_utils.checkout_jarvis_branch",
        return_value=(True, ""),
    )
    @patch(
        "jarvis.jarvis_utils.template_utils.pull_jarvis_code",
        return_value=(True, ""),
    )
    @patch(
        "jarvis.jarvis_utils.git_utils.reinstall_deps_after_update",
        return_value={
            "uv": {
                "attempted": True,
                "method": "uv_tool_install",
                "success": False,
                "detail": "uv tool install 失败: Permission denied",
            },
            "npm": {
                "attempted": True,
                "success": False,
                "detail": "npm install 失败",
            },
        },
    )
    def test_reinstall_failure_does_not_affect_success(
        self, mock_reinstall, mock_pull, mock_checkout, mock_src
    ):
        """依赖重装失败不影响外层 success=true。"""
        m = _make_manager(is_child=False)
        result = asyncio.run(m._handle_code_update_to_main_request({"request_id": "r2"}))

        payload = result["payload"]
        assert payload["success"] is True
        deps = payload["data"]["deps_reinstall"]
        assert deps["uv"]["success"] is False
        assert deps["npm"]["success"] is False

    @patch(
        "jarvis.jarvis_utils.template_utils.get_jarvis_src_dir",
        return_value="/repo",
    )
    @patch(
        "jarvis.jarvis_utils.template_utils.checkout_jarvis_branch",
        return_value=(True, ""),
    )
    @patch(
        "jarvis.jarvis_utils.template_utils.pull_jarvis_code",
        return_value=(True, ""),
    )
    @patch(
        "jarvis.jarvis_utils.git_utils.reinstall_deps_after_update",
        return_value={
            "uv": {
                "attempted": True,
                "method": "uv_tool_install",
                "success": True,
                "detail": "ok",
            },
            "npm": {"attempted": False, "success": False, "detail": "skipped"},
        },
    )
    def test_child_node_passes_include_frontend_false(
        self, mock_reinstall, mock_pull, mock_checkout, mock_src
    ):
        """child 节点 include_frontend=False。"""
        m = _make_manager(is_child=True)
        result = asyncio.run(m._handle_code_update_to_main_request({"request_id": "r3"}))

        payload = result["payload"]
        assert payload["success"] is True
        mock_reinstall.assert_called_once()
        kwargs = mock_reinstall.call_args
        assert kwargs.kwargs.get("include_frontend") is False

    @patch(
        "jarvis.jarvis_utils.template_utils.get_jarvis_src_dir",
        return_value="/repo",
    )
    @patch(
        "jarvis.jarvis_utils.template_utils.checkout_jarvis_branch",
        return_value=(False, "checkout error"),
    )
    @patch(
        "jarvis.jarvis_utils.git_utils.reinstall_deps_after_update",
        return_value={},
    )
    def test_git_failure_returns_error_without_reinstall(
        self, mock_reinstall, mock_checkout, mock_src
    ):
        """git checkout 失败返回原错误码，不调用依赖重装。"""
        m = _make_manager(is_child=False)
        result = asyncio.run(m._handle_code_update_to_main_request({"request_id": "r4"}))

        payload = result["payload"]
        assert payload["success"] is False
        assert payload["error"]["code"] == "CHECKOUT_FAILED"
        mock_reinstall.assert_not_called()

    @patch(
        "jarvis.jarvis_utils.template_utils.get_jarvis_src_dir",
        return_value="/repo",
    )
    @patch(
        "jarvis.jarvis_utils.template_utils.checkout_jarvis_branch",
        return_value=(True, ""),
    )
    @patch(
        "jarvis.jarvis_utils.template_utils.pull_jarvis_code",
        return_value=(False, "pull error"),
    )
    @patch(
        "jarvis.jarvis_utils.git_utils.reinstall_deps_after_update",
        return_value={},
    )
    def test_pull_failure_returns_error_without_reinstall(
        self, mock_reinstall, mock_pull, mock_checkout, mock_src
    ):
        """git pull 失败返回 PULL_FAILED，不调用依赖重装。"""
        m = _make_manager(is_child=False)
        result = asyncio.run(m._handle_code_update_to_main_request({"request_id": "r5"}))

        payload = result["payload"]
        assert payload["success"] is False
        assert payload["error"]["code"] == "PULL_FAILED"
        mock_reinstall.assert_not_called()
