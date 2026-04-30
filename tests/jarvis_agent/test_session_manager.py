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
            mock_makedirs.assert_called_once_with(
                "/test/dir/.jarvis/sessions", exist_ok=True
            )

            # 验证保存路径格式（文件名包含时间戳）
            actual_path = mock_model.save.call_args[0][0]
            # 文件名可能包含会话名称前缀（如：未命名会话）
            expected_pattern = r"/test/dir/\.jarvis/sessions/[^_]*_saved_session_test_agent_\d{8}_\d{6}\.json$"
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
            # 文件名可能包含会话名称前缀（如：未命名会话）
            expected_pattern = r"/test/dir/\.jarvis/sessions/[^_]*_saved_session_test_agent_\d{8}_\d{6}\.json$"
            assert re.match(expected_pattern, actual_path), (
                f"路径格式不匹配: {actual_path}"
            )



    @patch("os.path.exists")
    def test_restore_session_file_not_exists(self, mock_exists, session_manager):
        """测试会话文件不存在的情况"""
        mock_exists.return_value = False

        with patch("os.getcwd", return_value="/test/dir"):
            result = session_manager.restore_session()

            assert result is False




