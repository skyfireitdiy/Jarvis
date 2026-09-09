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

    def test_generate_session_name_empty_conversation(
        self, session_manager, mock_model
    ):
        """对话记录为空时返回默认名称"""
        mock_model.get_messages.return_value = []
        assert session_manager._generate_session_name() == "未命名会话"

    def test_generate_session_name_llm_success(self, session_manager, mock_model):
        """LLM成功生成会话名称"""
        mock_model.get_messages.return_value = [
            {"role": "user", "content": "帮我分析这段代码的性能问题"},
            {"role": "assistant", "content": "好的，我来分析性能瓶颈"},
        ]
        mock_model.complete.return_value = "代码性能分析"

        with patch.object(
            session_manager, "_iter_name_platforms", return_value=[mock_model]
        ):
            assert session_manager._generate_session_name() == "代码性能分析"

    def test_generate_session_name_llm_cleans_special_chars(
        self, session_manager, mock_model
    ):
        """LLM返回的名称会清理特殊字符并限制长度"""
        mock_model.get_messages.return_value = [
            {"role": "user", "content": "帮我写一个Python脚本"}
        ]
        mock_model.complete.return_value = "「Python脚本」编写指南！"

        with patch.object(
            session_manager, "_iter_name_platforms", return_value=[mock_model]
        ):
            name = session_manager._generate_session_name()
            # 特殊字符被清理，只保留中文、英文、数字、下划线和连字符
            assert name == "Python脚本编写指南"

    def test_generate_session_name_all_platforms_fail(
        self, session_manager, mock_model
    ):
        """所有平台都失败时返回默认名称"""
        mock_model.get_messages.return_value = [
            {"role": "user", "content": "帮我分析代码"}
        ]
        mock_model.complete.side_effect = Exception("LLM调用失败")

        with patch.object(
            session_manager, "_iter_name_platforms", return_value=[mock_model]
        ):
            assert session_manager._generate_session_name() == "未命名会话"

    def test_generate_session_name_llm_empty_result(self, session_manager, mock_model):
        """LLM返回空结果时回退到默认名称"""
        mock_model.get_messages.return_value = [
            {"role": "user", "content": "帮我分析代码"}
        ]
        mock_model.complete.return_value = ""

        with patch.object(
            session_manager, "_iter_name_platforms", return_value=[mock_model]
        ):
            assert session_manager._generate_session_name() == "未命名会话"

    def test_generate_session_name_skips_compressed_summary(
        self, session_manager, mock_model
    ):
        """压缩摘要消息（含代码变更统计等元信息）被跳过，不污染会话主题判断"""
        compressed_summary = (
            "[历史摘要] ## 任务浓缩上下文\n\n"
            "**当前目标**：修复所有 ty 告警\n\n"
            "## 代码变更统计\n```\n3 files changed, 278 insertions\n```\n"
            "## 任务列表状态\n- 已完成: 5\n"
        )
        mock_model.get_messages.return_value = [
            {"role": "user", "content": compressed_summary},
            {"role": "assistant", "content": "好的，我来分析这段代码的性能瓶颈"},
            {"role": "user", "content": "帮我优化这个排序算法"},
        ]
        mock_model.complete.return_value = "算法优化"

        with patch.object(
            session_manager, "_iter_name_platforms", return_value=[mock_model]
        ):
            name = session_manager._generate_session_name()
            assert name == "算法优化"
            # 验证传给 LLM 的 prompt 不含压缩摘要的元信息
            prompt_arg = mock_model.complete.call_args[0][0]
            assert "代码变更统计" not in prompt_arg
            assert "任务列表状态" not in prompt_arg
            assert "帮我优化这个排序算法" in prompt_arg

    def test_generate_session_name_only_compressed_summary(
        self, session_manager, mock_model
    ):
        """历史中只有压缩摘要（无真实对话）时返回默认名称"""
        mock_model.get_messages.return_value = [
            {
                "role": "user",
                "content": "[历史摘要] ## 任务浓缩上下文\n\n**当前目标**：修复 ty 告警",
            }
        ]

        with patch.object(
            session_manager, "_iter_name_platforms", return_value=[mock_model]
        ):
            assert session_manager._generate_session_name() == "未命名会话"

    def test_is_compressed_summary_msg(self, session_manager):
        """_is_compressed_summary_msg 正确识别压缩摘要消息"""
        assert session_manager._is_compressed_summary_msg(
            {"role": "user", "content": "[历史摘要] 摘要内容"}
        )
        assert session_manager._is_compressed_summary_msg(
            {"role": "user", "content": "  [历史摘要] 带前导空格"}
        )
        # 普通用户消息不是压缩摘要
        assert not session_manager._is_compressed_summary_msg(
            {"role": "user", "content": "帮我分析代码"}
        )
        # assistant 消息即使以 [历史摘要] 开头也不算（压缩摘要总是 user 角色）
        assert not session_manager._is_compressed_summary_msg(
            {"role": "assistant", "content": "[历史摘要] 不是压缩摘要"}
        )
        # 空 content 不是压缩摘要
        assert not session_manager._is_compressed_summary_msg(
            {"role": "user", "content": ""}
        )
