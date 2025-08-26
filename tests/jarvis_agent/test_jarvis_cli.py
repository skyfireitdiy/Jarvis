# -*- coding: utf-8 -*-
"""jarvis CLI 回调测试（run_cli）"""
from typer.testing import CliRunner
from unittest.mock import Mock
import pytest

import jarvis.jarvis_agent.jarvis as jarvis_mod


runner = CliRunner()


class TestJarvisCLI:
    def test_edit_flag_calls_config_editor(self, monkeypatch):
        called = {"edit": False}

        def fake_edit(config_file):
            called["edit"] = True

        monkeypatch.setattr(
            jarvis_mod.ConfigEditor, "edit_config", staticmethod(fake_edit)
        )

        result = runner.invoke(jarvis_mod.app, ["--edit"])
        assert result.exit_code == 0
        assert called["edit"] is True

    def test_share_methodology_flag_runs_manager(self, monkeypatch):
        # 避免 init_env 副作用
        monkeypatch.setattr(jarvis_mod, "init_env", lambda *a, **k: None)
        # 返回一个带 run 的假对象
        mgr = Mock()
        monkeypatch.setattr(jarvis_mod, "MethodologyShareManager", lambda: mgr)

        result = runner.invoke(jarvis_mod.app, ["--share-methodology"])
        assert result.exit_code == 0
        mgr.run.assert_called_once()

    def test_share_tool_flag_runs_manager(self, monkeypatch):
        monkeypatch.setattr(jarvis_mod, "init_env", lambda *a, **k: None)
        mgr = Mock()
        monkeypatch.setattr(jarvis_mod, "ToolShareManager", lambda: mgr)

        result = runner.invoke(jarvis_mod.app, ["--share-tool"])
        assert result.exit_code == 0
        mgr.run.assert_called_once()

    def test_default_flow_constructs_agent_manager_with_args(self, monkeypatch):
        # 禁用可能触发交互/外部进程的分支
        monkeypatch.setattr(jarvis_mod, "is_enable_git_repo_jca_switch", lambda: False)
        monkeypatch.setattr(
            jarvis_mod, "is_enable_builtin_config_selector", lambda: False
        )
        monkeypatch.setattr(jarvis_mod, "init_env", lambda *a, **k: None)
        # 预加载配置不抛异常
        monkeypatch.setattr(jarvis_mod.jutils, "load_config", lambda: None)

        captured = {}

        class DummyAgentManager:
            def __init__(self, model_group, tool_group, restore_session):
                captured["model_group"] = model_group
                captured["tool_group"] = tool_group
                captured["restore_session"] = restore_session

            def initialize(self):
                captured["initialized"] = True

            def run_task(self, task):
                captured["task"] = task

        monkeypatch.setattr(jarvis_mod, "AgentManager", DummyAgentManager)

        args = [
            "--task",
            "do something",
            "-g",
            "mygroup",
            "-G",
            "tools",
            "-f",
            "config.yml",
            "--restore-session",
        ]
        result = runner.invoke(jarvis_mod.app, args)
        assert result.exit_code == 0

        # 校验构造参数与任务传递

        assert captured["model_group"] == "mygroup"
        assert captured["tool_group"] == "tools"
        assert captured["restore_session"] is True
        assert captured["initialized"] is True
        assert captured["task"] == "do something"
