# -*- coding: utf-8 -*-
"""SessionManager 单元测试"""

from unittest.mock import Mock, patch
import pytest

from jarvis.jarvis_agent.session_manager import SessionManager


class TestSessionManager:
    """SessionManager 类的测试"""

    @pytest.fixture
    def mock_model(self):
        """创建模拟的 BasePlatform 对象"""
        model = Mock()
        model.platform_name.return_value = "test_platform"
        model.name.return_value = "test_model"
        model.reset = Mock()
        model.save = Mock(return_value=True)
        model.restore = Mock(return_value=True)
        return model

    @pytest.fixture
    def session_manager(self, mock_model):
        """创建 SessionManager 实例"""
        return SessionManager(mock_model, "test_agent")

    def test_init(self, session_manager, mock_model):
        """测试初始化"""
        assert session_manager.model == mock_model
        assert session_manager.agent_name == "test_agent"
        assert session_manager.prompt == ""
        assert session_manager.conversation_length == 0
        assert session_manager.user_data == {}
        assert session_manager.addon_prompt == ""

    def test_set_get_user_data(self, session_manager):
        """测试用户数据的设置和获取"""
        # 设置数据
        session_manager.set_user_data("key1", "value1")
        session_manager.set_user_data("key2", 123)

        # 获取数据
        assert session_manager.get_user_data("key1") == "value1"
        assert session_manager.get_user_data("key2") == 123
        assert session_manager.get_user_data("non_existent") is None

    def test_set_addon_prompt(self, session_manager):
        """测试设置附加提示"""
        test_prompt = "This is an addon prompt"
        session_manager.set_addon_prompt(test_prompt)
        assert session_manager.addon_prompt == test_prompt

    def test_clear(self, session_manager, mock_model):
        """测试清空会话"""
        # 设置一些数据
        session_manager.prompt = "test prompt"
        session_manager.conversation_length = 5
        session_manager.set_user_data("key", "value")

        # 清空会话
        session_manager.clear()

        # 验证状态
        assert session_manager.prompt == ""
        assert session_manager.conversation_length == 0
        assert session_manager.user_data == {"key": "value"}  # user_data 不会被清空
        mock_model.reset.assert_called_once()

    def test_clear_history(self, session_manager, mock_model):
        """测试清空历史记录"""
        # 设置一些数据
        session_manager.prompt = "test prompt"
        session_manager.conversation_length = 5

        # 清空历史
        session_manager.clear_history()

        # 验证状态
        assert session_manager.prompt == ""
        assert session_manager.conversation_length == 0
        mock_model.reset.assert_called_once()

    @patch("os.makedirs")
    def test_save_session_success(self, mock_makedirs, session_manager, mock_model):
        """测试成功保存会话"""
        import re

        with patch("os.getcwd", return_value="/test/dir"):
            result = session_manager.save_session()

            # 验证结果
            assert result is True
            mock_makedirs.assert_called_once_with("/test/dir/.jarvis", exist_ok=True)

            # 验证保存路径格式（文件名包含时间戳）
            actual_path = mock_model.save.call_args[0][0]
            expected_pattern = r"/test/dir/\.jarvis/saved_session_test_agent_test_platform_test_model_\d{8}_\d{6}\.json$"
            assert re.match(expected_pattern, actual_path), (
                f"路径格式不匹配: {actual_path}"
            )

    @patch("os.makedirs")
    def test_save_session_with_special_chars(
        self, mock_makedirs, session_manager, mock_model
    ):
        """测试带特殊字符的模型名称"""
        import re

        mock_model.name.return_value = "test/model\\name"

        with patch("os.getcwd", return_value="/test/dir"):
            session_manager.save_session()

            # 验证特殊字符被替换，且文件名包含时间戳
            actual_path = mock_model.save.call_args[0][0]
            expected_pattern = r"/test/dir/\.jarvis/saved_session_test_agent_test_platform_test_model_name_\d{8}_\d{6}\.json$"
            assert re.match(expected_pattern, actual_path), (
                f"路径格式不匹配: {actual_path}"
            )

    @patch("jarvis.jarvis_utils.output.PrettyOutput.auto_print")
    def test_restore_session_success(
        self, mock_auto_print, session_manager, mock_model
    ):
        """测试成功恢复会话"""
        # Mock _parse_session_files 返回一个模拟的会话文件
        mock_session_file = "/test/dir/.jarvis/saved_session_test_agent_test_platform_test_model_20250107_120000.json"
        with patch.object(
            session_manager,
            "_parse_session_files",
            return_value=[(mock_session_file, "20250107_120000")],
        ):
            result = session_manager.restore_session()

            # 验证结果
            assert result is True

            # 验证文件路径
            mock_model.restore.assert_called_once_with(mock_session_file)

            # 验证输出：应该有两次print调用（显示恢复的文件名和成功消息）
            assert mock_auto_print.call_count == 2
            # 第一次调用显示恢复的文件名
            first_call = mock_auto_print.call_args_list[0][0][0]
            assert "📂 恢复会话:" in first_call
            # 第二次调用显示成功消息
            second_call = mock_auto_print.call_args_list[1][0][0]
            assert "✅ 会话已恢复。" == second_call

    @patch("os.path.exists")
    def test_restore_session_file_not_exists(self, mock_exists, session_manager):
        """测试会话文件不存在的情况"""
        mock_exists.return_value = False

        with patch("os.getcwd", return_value="/test/dir"):
            result = session_manager.restore_session()

            assert result is False

    @patch("jarvis.jarvis_utils.output.PrettyOutput.auto_print")
    def test_restore_session_non_interactive_mode(
        self, mock_auto_print, session_manager, mock_model
    ):
        """测试非交互模式下自动恢复最新会话"""
        # 设置非交互模式
        session_manager.non_interactive = True

        # Mock _parse_session_files 返回两个会话文件
        mock_newer_file = "/test/dir/.jarvis/saved_session_test_agent_test_platform_test_model_20250107_120000.json"
        mock_older_file = "/test/dir/.jarvis/saved_session_test_agent_test_platform_test_model_20250106_080000.json"
        with patch.object(
            session_manager,
            "_parse_session_files",
            return_value=[
                (mock_newer_file, "20250107_120000"),
                (mock_older_file, "20250106_080000"),
            ],
        ):
            result = session_manager.restore_session()

            # 验证结果
            assert result is True

            # 验证恢复的是最新的会话文件（列表第一个）
            mock_model.restore.assert_called_once_with(mock_newer_file)

            # 验证输出：应该有两次print调用
            assert mock_auto_print.call_count == 2
            # 第一次调用显示非交互模式自动恢复的消息
            first_call = mock_auto_print.call_args_list[0][0][0]
            assert "🤖 非交互模式" in first_call
            # 第二次调用显示成功消息
            second_call = mock_auto_print.call_args_list[1][0][0]
            assert "✅ 会话已恢复。" == second_call

    @patch("jarvis.jarvis_utils.output.PrettyOutput.auto_print")
    def test_restore_session_restore_failure(
        self, mock_auto_print, session_manager, mock_model
    ):
        """测试恢复会话失败的情况"""
        # Mock _parse_session_files 返回一个模拟的会话文件
        mock_session_file = "/test/dir/.jarvis/saved_session_test_agent_test_platform_test_model_20250107_120000.json"
        with patch.object(
            session_manager,
            "_parse_session_files",
            return_value=[(mock_session_file, "20250107_120000")],
        ):
            # 模拟 restore 失败
            mock_model.restore.return_value = False

            result = session_manager.restore_session()

            # 验证结果
            assert result is False

            # 验证输出：应该有两次print调用（显示恢复的文件名和失败消息）
            assert mock_auto_print.call_count == 2
            # 第一次调用显示恢复的文件名
            first_call = mock_auto_print.call_args_list[0][0][0]
            assert "📂 恢复会话:" in first_call
            # 第二次调用显示失败消息
            second_call = mock_auto_print.call_args_list[1][0][0]
            assert "❌ 会话恢复失败。" == second_call
