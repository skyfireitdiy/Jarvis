# -*- coding: utf-8 -*-
"""
测试 input.py 模块
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from jarvis.jarvis_utils.input import (
    _display_width,
    _calc_prompt_rows,
    _multiline_hint_already_shown,
    _mark_multiline_hint_shown,
    get_single_line_input,
    get_choice,
    FileCompleter,
    get_all_rules_formatted,
    user_confirm,
    _get_fzf_completion_items,
)


class TestDisplayWidth:
    """测试 _display_width 函数"""

    def test_display_width_ascii(self):
        """测试ASCII字符宽度计算"""
        assert _display_width("hello") == 5

    def test_display_width_chinese(self):
        """测试中文字符宽度计算"""
        assert _display_width("你好") == 4  # 每个中文字符通常占2个宽度

    def test_display_width_mixed(self):
        """测试混合字符宽度计算"""
        assert _display_width("hello你好") == 9  # 5 + 4

    def test_display_width_empty(self):
        """测试空字符串宽度计算"""
        assert _display_width("") == 0

    def test_display_width_special_case(self):
        """测试特殊字符宽度计算"""
        assert _display_width("😀") >= 1  # emoji字符


class TestCalcPromptRows:
    """测试 _calc_prompt_rows 函数"""

    @patch("os.get_terminal_size")
    def test_calc_prompt_rows_single_line(self, mock_get_terminal_size):
        """测试单行文本行数计算"""
        mock_get_terminal_size.return_value = MagicMock(columns=80)
        result = _calc_prompt_rows("hello")
        assert result == 1

    @patch("os.get_terminal_size")
    def test_calc_prompt_rows_multi_line(self, mock_get_terminal_size):
        """测试多行文本行数计算"""
        mock_get_terminal_size.return_value = MagicMock(columns=20)
        result = _calc_prompt_rows(
            "This is a very long text that should wrap to multiple lines"
        )
        assert result >= 2  # 至少2行

    def test_calc_prompt_rows_no_terminal_size(self):
        """测试无法获取终端大小时的默认处理"""
        result = _calc_prompt_rows("hello")
        assert result >= 1


class TestMultilineHintFunctions:
    """测试多行输入提示相关函数"""

    def test_multiline_hint_shown_functions(self):
        """测试多行提示显示状态函数"""
        # 在临时目录下测试
        with tempfile.TemporaryDirectory() as temp_dir:
            # 临时修改 _MULTILINE_HINT_MARK_FILE 的路径
            temp_file = os.path.join(temp_dir, "multiline_enter_hint_shown")

            # 注意：由于 _MULTILINE_HINT_MARK_FILE 是模块级常量，
            # 我们需要通过模拟方法测试
            with patch(
                "jarvis.jarvis_utils.input._MULTILINE_HINT_MARK_FILE", temp_file
            ):
                # 验证初始状态
                assert not _multiline_hint_already_shown()

                # 标记为已显示
                _mark_multiline_hint_shown()

                # 验证状态已更新
                assert _multiline_hint_already_shown()


class TestGetSingleLineInput:
    """测试 get_single_line_input 函数"""

    @patch("jarvis.jarvis_utils.input.PromptSession")
    def test_get_single_line_input(self, mock_session_class):
        """测试单行输入获取"""
        mock_session = MagicMock()
        mock_session.prompt.return_value = "test input"
        mock_session_class.return_value = mock_session

        result = get_single_line_input("Enter something:")
        assert result == "test input"


class TestFileCompleter:
    """测试 FileCompleter 类"""

    def test_file_completer_init(self):
        """测试FileCompleter初始化"""
        completer = FileCompleter()
        assert completer.max_suggestions == 30
        assert completer.min_score == 10
        assert hasattr(completer, "path_completer")

    @patch("jarvis.jarvis_utils.input.get_replace_map")
    def test_get_description(self, mock_get_replace_map):
        """测试_get_description方法"""
        mock_get_replace_map.return_value = {
            "test": {"description": "test description", "append": True},
            "test2": {"description": "test2 description", "append": False},
        }

        completer = FileCompleter()
        assert completer._get_description("test") == "test description(Append)"
        # 根据实际实现，当append为False时，只返回'(Replace)'，不包含描述
        assert completer._get_description("test2") == "(Replace)"
        assert completer._get_description("nonexistent") == "nonexistent"


class TestGetAllRulesFormatted:
    """测试 get_all_rules_formatted 函数"""

    def test_get_all_rules_formatted_basic(self):
        """测试获取格式化规则列表"""
        # 由于该函数涉及外部依赖，我们测试基本返回格式
        result = get_all_rules_formatted()
        assert isinstance(result, list)
        # 验证规则格式
        for rule in result:
            assert isinstance(rule, str)
            assert rule.startswith("<rule:")


class TestUserConfirm:
    """测试 user_confirm 函数"""

    @patch("jarvis.jarvis_utils.input.get_single_line_input")
    def test_user_confirm_default_true(self, mock_get_single_line_input):
        """测试用户确认函数（默认为True）"""
        mock_get_single_line_input.return_value = ""
        assert user_confirm("Continue?", default=True) is True

    @patch("jarvis.jarvis_utils.input.get_single_line_input")
    def test_user_confirm_default_false(self, mock_get_single_line_input):
        """测试用户确认函数（默认为False）"""
        mock_get_single_line_input.return_value = ""
        assert user_confirm("Continue?", default=False) is False

    @patch("jarvis.jarvis_utils.input.get_single_line_input")
    def test_user_confirm_explicit_yes(self, mock_get_single_line_input):
        """测试用户显式输入yes"""
        mock_get_single_line_input.return_value = "y"
        assert user_confirm("Continue?", default=False) is True

    @patch("jarvis.jarvis_utils.input.get_single_line_input")
    def test_user_confirm_explicit_no(self, mock_get_single_line_input):
        """测试用户显式输入no"""
        mock_get_single_line_input.return_value = "n"
        assert user_confirm("Continue?", default=True) is False


class TestGetChoice:
    """测试 get_choice 函数"""

    @patch("os.get_terminal_size")
    def test_get_choice_empty(self, mock_get_terminal_size):
        """测试空选项列表"""
        mock_get_terminal_size.return_value = MagicMock(lines=25)
        with pytest.raises(ValueError, match="Choices cannot be empty"):
            get_choice("Pick one:", [])


class TestGetFzfCompletionItems:
    """测试 _get_fzf_completion_items 函数"""

    def test_get_fzf_completion_items_basic(self):
        """测试fzf补全项目基本功能"""
        specials = ["@", "#", "!", "Summary"]
        files = ["file1.txt", "file2.py", "folder/file3.js"]

        result = _get_fzf_completion_items(specials, files)

        # 检查结果类型
        assert isinstance(result, list)

        # 检查是否包含所有输入项目
        for item in specials:
            if item.strip():  # 跳过空字符串
                assert item in result

        for item in files:
            assert item in result


if __name__ == "__main__":
    pytest.main([__file__])
