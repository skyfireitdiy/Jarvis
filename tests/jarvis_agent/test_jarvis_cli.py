# -*- coding: utf-8 -*-
"""jarvis CLI 单元测试。"""

from unittest.mock import Mock

import typer

from jarvis.jarvis_agent import jarvis


class TestJarvisCliSessionSave:
    def test_run_cli_saves_session_before_exit(self, monkeypatch):
        mock_agent = Mock()
        mock_agent.run.return_value = "done"
        mock_agent.save_session = Mock()

        mock_agent_manager = Mock()
        mock_agent_manager.initialize.side_effect = [None, mock_agent]

        monkeypatch.setattr(jarvis, "init_env", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            jarvis, "preload_config_for_flags", lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            jarvis, "try_switch_to_jca_if_git_repo", lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            jarvis, "handle_builtin_config_selector", lambda *args, **kwargs: None
        )
        monkeypatch.setattr(jarvis, "handle_edit_option", lambda *args, **kwargs: False)
        monkeypatch.setattr(
            jarvis, "handle_share_methodology_option", lambda *args, **kwargs: False
        )
        monkeypatch.setattr(
            jarvis, "handle_share_tool_option", lambda *args, **kwargs: False
        )
        monkeypatch.setattr(
            jarvis, "handle_share_rule_option", lambda *args, **kwargs: False
        )
        monkeypatch.setattr(
            jarvis, "handle_interactive_config_option", lambda *args, **kwargs: False
        )
        monkeypatch.setattr(
            jarvis, "handle_backup_option", lambda *args, **kwargs: False
        )
        monkeypatch.setattr(
            jarvis, "handle_restore_option", lambda *args, **kwargs: False
        )
        monkeypatch.setattr(
            jarvis, "handle_quick_config_option", lambda *args, **kwargs: False
        )
        monkeypatch.setattr(jarvis, "handle_check_mode", lambda *args, **kwargs: False)
        monkeypatch.setattr(
            jarvis, "check_and_launch_tmux", lambda *args, **kwargs: (False, None)
        )
        monkeypatch.setattr(
            jarvis, "AgentManager", lambda *args, **kwargs: mock_agent_manager
        )
        monkeypatch.setattr(
            jarvis,
            "_run_with_builtin_handler",
            lambda user_input, agent, output_ref, exit_ref, error_ref: (
                user_input,
                False,
            ),
        )

        with monkeypatch.context() as context:
            context.setattr(typer, "Exit", typer.Exit)
            try:
                jarvis.run_cli(ctx=Mock(), task="test task")
            except typer.Exit:
                pass

        mock_agent.run.assert_called_once_with("test task")
        mock_agent.save_session.assert_called_once_with()
