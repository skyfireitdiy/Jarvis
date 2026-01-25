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
    _get_current_agent_for_input,
    _is_non_interactive_for_current_agent,
    _is_auto_complete_for_current_agent,
    get_multiline_input,
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


class TestGetCurrentAgentForInput:
    """测试 _get_current_agent_for_input 函数"""

    @patch("jarvis.jarvis_utils.globals.get_current_agent_name")
    @patch("jarvis.jarvis_utils.globals.get_agent")
    def test_get_current_agent_success(self, mock_get_agent, mock_get_name):
        """测试成功获取当前agent"""
        mock_get_name.return_value = "test_agent"
        mock_agent = MagicMock()
        mock_get_agent.return_value = mock_agent

        result = _get_current_agent_for_input()

        assert result == mock_agent
        mock_get_name.assert_called_once()
        mock_get_agent.assert_called_once_with("test_agent")

    @patch("jarvis.jarvis_utils.globals.get_current_agent_name")
    def test_get_current_agent_no_name(self, mock_get_name):
        """测试没有当前agent名称"""
        mock_get_name.return_value = ""

        result = _get_current_agent_for_input()

        assert result is None

    @patch("jarvis.jarvis_utils.globals.get_current_agent_name")
    def test_get_current_agent_none_name(self, mock_get_name):
        """测试当前agent名称为None"""
        mock_get_name.return_value = None

        result = _get_current_agent_for_input()

        assert result is None

    @patch("jarvis.jarvis_utils.input.globals")
    def test_get_current_agent_import_error(self, mock_globals):
        """测试导入异常"""
        mock_globals.get_current_agent_name.side_effect = ImportError()

        result = _get_current_agent_for_input()

        assert result is None


class TestIsNonInteractiveForCurrentAgent:
    """测试 _is_non_interactive_for_current_agent 函数"""

    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    @patch("jarvis.jarvis_utils.config.is_non_interactive")
    def test_agent_has_non_interactive_true(
        self, mock_is_non_interactive, mock_get_agent
    ):
        """测试agent有non_interactive属性且为True"""
        mock_agent = MagicMock()
        mock_agent.non_interactive = True
        mock_get_agent.return_value = mock_agent

        result = _is_non_interactive_for_current_agent()

        assert result is True
        mock_get_agent.assert_called_once()

    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    def test_agent_has_non_interactive_false(self, mock_get_agent):
        """测试agent有non_interactive属性且为False"""
        mock_agent = MagicMock()
        mock_agent.non_interactive = False
        mock_get_agent.return_value = mock_agent

        result = _is_non_interactive_for_current_agent()

        assert result is False

    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    @patch("jarvis.jarvis_utils.config.is_non_interactive")
    def test_agent_no_non_interactive_global_true(
        self, mock_is_non_interactive, mock_get_agent
    ):
        """测试agent存在但无non_interactive属性时的行为"""
        # MagicMock的getattr会返回一个MagicMock对象，其bool()值为True
        # 所以即使属性不存在，也会返回True
        mock_agent = MagicMock()
        # 不设置non_interactive属性
        mock_get_agent.return_value = mock_agent
        mock_is_non_interactive.return_value = True

        result = _is_non_interactive_for_current_agent()

        # 由于agent存在且getattr返回MagicMock(bool=True)，所以结果为True
        assert result is True
        # 不会调用全局的is_non_interactive
        mock_is_non_interactive.assert_not_called()

    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    @patch("jarvis.jarvis_utils.config.is_non_interactive")
    def test_agent_no_non_interactive_global_false(
        self, mock_is_non_interactive, mock_get_agent
    ):
        """测试agent无non_interactive属性，使用全局配置（False）"""
        mock_agent = MagicMock()
        mock_get_agent.return_value = mock_agent
        # 模拟agent没有non_interactive属性
        type(mock_agent).non_interactive = []
        mock_is_non_interactive.return_value = False

        result = _is_non_interactive_for_current_agent()

        assert result is False

    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    @patch("jarvis.jarvis_utils.config.is_non_interactive")
    def test_no_agent_global_false(self, mock_is_non_interactive, mock_get_agent):
        """测试没有agent，使用全局配置（False）"""
        mock_get_agent.return_value = None
        mock_is_non_interactive.return_value = False

        result = _is_non_interactive_for_current_agent()

        assert result is False

    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    @patch("jarvis.jarvis_utils.config.is_non_interactive")
    def test_exception_returns_false(self, mock_is_non_interactive, mock_get_agent):
        """测试异常情况返回False"""
        mock_get_agent.side_effect = Exception()

        result = _is_non_interactive_for_current_agent()

        assert result is False


class TestIsAutoCompleteForCurrentAgent:
    """测试 _is_auto_complete_for_current_agent 函数"""

    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    def test_agent_has_auto_complete_true(self, mock_get_agent):
        """测试agent有auto_complete属性且为True"""
        mock_agent = MagicMock()
        mock_agent.auto_complete = True
        mock_get_agent.return_value = mock_agent

        result = _is_auto_complete_for_current_agent()

        assert result is True

    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    def test_agent_has_auto_complete_false(self, mock_get_agent):
        """测试agent有auto_complete属性且为False"""
        mock_agent = MagicMock()
        mock_agent.auto_complete = False
        mock_get_agent.return_value = mock_agent

        result = _is_auto_complete_for_current_agent()

        assert result is False

    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    def test_agent_no_auto_complete(self, mock_get_agent):
        """测试agent没有auto_complete属性"""
        # MagicMock的getattr会返回一个MagicMock对象，其bool()值为True
        mock_agent = MagicMock()
        # 不设置auto_complete属性
        mock_get_agent.return_value = mock_agent

        result = _is_auto_complete_for_current_agent()

        # 由于getattr返回MagicMock(bool=True)，所以结果为True
        assert result is True

    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    def test_no_agent(self, mock_get_agent):
        """测试没有agent"""
        mock_get_agent.return_value = None

        result = _is_auto_complete_for_current_agent()

        assert result is False

    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    def test_exception_returns_false(self, mock_get_agent):
        """测试异常情况返回False"""
        mock_get_agent.side_effect = Exception()

        result = _is_auto_complete_for_current_agent()

        assert result is False


class TestGetAllRulesFormattedEnhanced:
    """增强测试 get_all_rules_formatted 函数"""

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_rules_manager_builtin_rules(self, mock_rules_manager_class):
        """测试RulesManager成功返回内置规则"""
        mock_manager = MagicMock()
        mock_manager.get_all_available_rule_names.return_value = {
            "builtin": ["rule1", "rule2"],
            "files": [],
            "yaml": [],
        }
        mock_rules_manager_class.return_value = mock_manager

        result = get_all_rules_formatted()

        assert len(result) == 2
        assert "<rule:rule1>" in result
        assert "<rule:rule2>" in result

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_rules_manager_file_rules(self, mock_rules_manager_class):
        """测试RulesManager成功返回文件规则"""
        mock_manager = MagicMock()
        mock_manager.get_all_available_rule_names.return_value = {
            "builtin": [],
            "files": ["file_rule1", "file_rule2"],
            "yaml": [],
        }
        mock_rules_manager_class.return_value = mock_manager

        result = get_all_rules_formatted()

        assert len(result) == 2
        assert "<rule:file_rule1>" in result
        assert "<rule:file_rule2>" in result

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_rules_manager_yaml_rules(self, mock_rules_manager_class):
        """测试RulesManager成功返回YAML规则"""
        mock_manager = MagicMock()
        mock_manager.get_all_available_rule_names.return_value = {
            "builtin": [],
            "files": [],
            "yaml": ["yaml_rule1", "yaml_rule2"],
        }
        mock_rules_manager_class.return_value = mock_manager

        result = get_all_rules_formatted()

        assert len(result) == 2
        assert "<rule:yaml_rule1>" in result
        assert "<rule:yaml_rule2>" in result

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_rules_manager_mixed_rules(self, mock_rules_manager_class):
        """测试RulesManager成功返回混合规则"""
        mock_manager = MagicMock()
        mock_manager.get_all_available_rule_names.return_value = {
            "builtin": ["builtin1"],
            "files": ["file1"],
            "yaml": ["yaml1"],
        }
        mock_rules_manager_class.return_value = mock_manager

        result = get_all_rules_formatted()

        assert len(result) == 3
        assert "<rule:builtin1>" in result
        assert "<rule:file1>" in result
        assert "<rule:yaml1>" in result

    @patch(
        "jarvis.jarvis_agent.rules_manager.RulesManager",
        side_effect=ImportError(),
    )
    @patch("jarvis.jarvis_agent.builtin_rules.list_builtin_rules")
    def test_rules_manager_import_error(
        self, mock_list_builtin_rules, mock_rules_manager_class
    ):
        """测试RulesManager导入失败，使用内置规则"""
        mock_list_builtin_rules.return_value = ["builtin1", "builtin2"]

        result = get_all_rules_formatted()

        assert len(result) == 2
        assert "<rule:builtin1>" in result
        assert "<rule:builtin2>" in result
        mock_list_builtin_rules.assert_called_once()

    @patch(
        "jarvis.jarvis_agent.rules_manager.RulesManager",
        side_effect=ImportError(),
    )
    @patch(
        "jarvis.jarvis_agent.builtin_rules.list_builtin_rules",
        side_effect=ImportError(),
    )
    def test_all_import_errors(self, mock_list_builtin_rules, mock_rules_manager_class):
        """测试所有导入都失败"""
        result = get_all_rules_formatted()

        assert result == []

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_rules_manager_exception(self, mock_rules_manager_class):
        """测试RulesManager抛出异常"""
        mock_rules_manager_class.side_effect = Exception()

        result = get_all_rules_formatted()

        assert result == []


class TestFileCompleterEnhanced:
    """增强的 FileCompleter 类测试"""

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_get_all_rule_completions_builtin(self, mock_rules_manager_class):
        """测试获取内置规则补全"""
        mock_manager = MagicMock()
        mock_manager.get_all_available_rule_names.return_value = {
            "builtin": ["rule1", "rule2"],
            "files": [],
            "yaml": [],
        }
        mock_rules_manager_class.return_value = mock_manager

        completer = FileCompleter()
        result = completer._get_all_rule_completions()

        assert result == ["<rule:rule1>", "<rule:rule2>"]

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_get_all_rule_completions_files(self, mock_rules_manager_class):
        """测试获取文件规则补全"""
        mock_manager = MagicMock()
        mock_manager.get_all_available_rule_names.return_value = {
            "builtin": [],
            "files": ["file_rule1", "file_rule2"],
            "yaml": [],
        }
        mock_rules_manager_class.return_value = mock_manager

        completer = FileCompleter()
        result = completer._get_all_rule_completions()

        assert result == ["<rule:file_rule1>", "<rule:file_rule2>"]

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_get_all_rule_completions_yaml(self, mock_rules_manager_class):
        """测试获取YAML规则补全"""
        mock_manager = MagicMock()
        mock_manager.get_all_available_rule_names.return_value = {
            "builtin": [],
            "files": [],
            "yaml": ["yaml_rule1", "yaml_rule2"],
        }
        mock_rules_manager_class.return_value = mock_manager

        completer = FileCompleter()
        result = completer._get_all_rule_completions()

        assert result == ["<rule:yaml_rule1>", "<rule:yaml_rule2>"]

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_get_all_rule_completions_mixed(self, mock_rules_manager_class):
        """测试获取混合规则补全"""
        mock_manager = MagicMock()
        mock_manager.get_all_available_rule_names.return_value = {
            "builtin": ["builtin_rule"],
            "files": ["file_rule"],
            "yaml": ["yaml_rule"],
        }
        mock_rules_manager_class.return_value = mock_manager

        completer = FileCompleter()
        result = completer._get_all_rule_completions()

        assert result == [
            "<rule:builtin_rule>",
            "<rule:file_rule>",
            "<rule:yaml_rule>",
        ]

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager", side_effect=ImportError())
    @patch(
        "jarvis.jarvis_agent.builtin_rules.list_builtin_rules",
        return_value=["fallback_rule1", "fallback_rule2"],
    )
    def test_get_all_rule_completions_import_error(
        self, mock_list_builtin, mock_rules_manager_class
    ):
        """测试导入错误时使用内置规则"""
        completer = FileCompleter()
        result = completer._get_all_rule_completions()

        assert result == [
            "<rule:fallback_rule1>",
            "<rule:fallback_rule2>",
        ]

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_get_all_rules_cached(self, mock_rules_manager_class):
        """测试规则缓存机制"""
        mock_manager = MagicMock()
        mock_manager.get_all_available_rule_names.return_value = {
            "builtin": ["rule1"],
            "files": [],
            "yaml": [],
        }
        mock_rules_manager_class.return_value = mock_manager

        completer = FileCompleter()

        # 第一次调用
        result1 = completer._get_all_rules()
        assert len(result1) == 1

        # 第二次调用应该使用缓存
        result2 = completer._get_all_rules()
        assert len(result2) == 1
        assert mock_manager.get_all_available_rule_names.call_count == 1

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_get_all_rules_builtin(self, mock_rules_manager_class):
        """测试获取内置规则（带描述）"""
        mock_manager = MagicMock()
        mock_manager.get_all_available_rule_names.return_value = {
            "builtin": ["rule1", "rule2"],
            "files": [],
            "yaml": [],
        }
        mock_rules_manager_class.return_value = mock_manager

        completer = FileCompleter()
        result = completer._get_all_rules()

        assert result == [
            ("rule1", "📚 内置规则: rule1"),
            ("rule2", "📚 内置规则: rule2"),
        ]

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_get_all_rules_files(self, mock_rules_manager_class):
        """测试获取文件规则（带描述）"""
        mock_manager = MagicMock()
        mock_manager.get_all_available_rule_names.return_value = {
            "builtin": [],
            "files": ["file_rule1", "file_rule2"],
            "yaml": [],
        }
        mock_rules_manager_class.return_value = mock_manager

        completer = FileCompleter()
        result = completer._get_all_rules()

        assert result == [
            ("file_rule1", "📄 文件规则: file_rule1"),
            ("file_rule2", "📄 文件规则: file_rule2"),
        ]

    @patch("jarvis.jarvis_agent.rules_manager.RulesManager")
    def test_get_all_rules_yaml(self, mock_rules_manager_class):
        """测试获取YAML规则（带描述）"""
        mock_manager = MagicMock()
        mock_manager.get_all_available_rule_names.return_value = {
            "builtin": [],
            "files": [],
            "yaml": ["yaml_rule1", "yaml_rule2"],
        }
        mock_rules_manager_class.return_value = mock_manager

        completer = FileCompleter()
        result = completer._get_all_rules()

        assert result == [
            ("yaml_rule1", "📝 YAML规则: yaml_rule1"),
            ("yaml_rule2", "📝 YAML规则: yaml_rule2"),
        ]

    @patch("jarvis.jarvis_utils.input._subprocess.run")
    def test_get_completions_at_symbol(self, mock_subprocess_run):
        """测试@符号补全（git文件）"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"file1.py\nfile2.py\n"
        mock_subprocess_run.return_value = mock_result

        completer = FileCompleter()
        from prompt_toolkit.document import Document
        from prompt_toolkit.completion import CompleteEvent

        doc = Document("@file1", cursor_position=6)
        event = CompleteEvent()

        completions = list(completer.get_completions(doc, event))

        # 应该有补全项（包括内置命令、规则等）
        assert len(completions) > 0
        # 检查git文件被添加到补全列表
        completion_texts = [c.text for c in completions]
        # c.text 返回的是带引号的文本，如 'file1.py'
        assert "'file1.py'" in completion_texts or "'file2.py'" in completion_texts

    @patch("jarvis.jarvis_utils.input._os.walk")
    def test_get_completions_hash_symbol(self, mock_walk):
        """测试#符号补全（所有文件）"""
        # 模拟文件系统遍历
        mock_walk.return_value = [
            (".", ["dir1"], ["file1.py", "file2.py"]),
            ("./dir1", [], ["file3.py"]),
        ]

        completer = FileCompleter()
        from prompt_toolkit.document import Document
        from prompt_toolkit.completion import CompleteEvent

        doc = Document("#file1", cursor_position=6)
        event = CompleteEvent()

        completions = list(completer.get_completions(doc, event))

        # 应该有补全项
        assert len(completions) > 0

    def test_get_completions_no_symbol(self):
        """测试无符号时不补全"""
        completer = FileCompleter()
        from prompt_toolkit.document import Document
        from prompt_toolkit.completion import CompleteEvent

        doc = Document("file1", cursor_position=5)
        event = CompleteEvent()

        completions = list(completer.get_completions(doc, event))

        # 应该没有补全项
        assert len(completions) == 0

    def test_get_completions_empty_token(self):
        """测试空token显示所有建议"""
        completer = FileCompleter()
        from prompt_toolkit.document import Document
        from prompt_toolkit.completion import CompleteEvent

        doc = Document("@", cursor_position=1)
        event = CompleteEvent()

        completions = list(completer.get_completions(doc, event))

        # 应该有补全项（内置命令、规则等）
        assert len(completions) > 0

    def test_get_completions_with_space(self):
        """测试token包含空格时不补全"""
        completer = FileCompleter()
        from prompt_toolkit.document import Document
        from prompt_toolkit.completion import CompleteEvent

        doc = Document("@file 1", cursor_position=7)
        event = CompleteEvent()

        completions = list(completer.get_completions(doc, event))

        # 应该没有补全项
        assert len(completions) == 0

    def test_get_completions_punctuation_only(self):
        """测试只有标点符号的token"""
        completer = FileCompleter()
        from prompt_toolkit.document import Document
        from prompt_toolkit.completion import CompleteEvent

        # 使用只有标点符号的token
        doc = Document("@!!!", cursor_position=4)
        event = CompleteEvent()

        completions = list(completer.get_completions(doc, event))

        # 应该有补全项（不进行模糊匹配，直接显示前30个）
        assert len(completions) > 0


class TestGetMultilineInputEnhanced:
    """增强的 get_multiline_input 函数测试"""

    @patch("jarvis.jarvis_utils.input._is_non_interactive_for_current_agent")
    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    @patch(
        "jarvis.jarvis_utils.input._is_auto_complete_for_current_agent",
        return_value=False,
    )
    def test_non_interactive_mode_without_auto_complete(
        self, mock_auto_complete, mock_get_agent, mock_is_non_interactive
    ):
        """测试非交互模式（不自动完成）"""
        mock_is_non_interactive.return_value = True
        mock_get_agent.return_value = None

        result = get_multiline_input("请输入:")

        assert "当前是非交互模式" in result

    @patch("jarvis.jarvis_utils.input._is_non_interactive_for_current_agent")
    @patch("jarvis.jarvis_utils.input._get_current_agent_for_input")
    @patch(
        "jarvis.jarvis_utils.input._is_auto_complete_for_current_agent",
        return_value=True,
    )
    def test_non_interactive_mode_with_auto_complete(
        self, mock_auto_complete, mock_get_agent, mock_is_non_interactive
    ):
        """测试非交互模式（自动完成）"""
        mock_is_non_interactive.return_value = True
        mock_get_agent.return_value = None

        result = get_multiline_input("请输入:")

        assert "当前是非交互模式" in result
        assert "!!!COMPLETE!!!" in result

    @patch(
        "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
        return_value=False,
    )
    @patch("jarvis.jarvis_utils.input._get_multiline_input_internal")
    def test_normal_multiline_input(self, mock_internal_input, mock_is_non_interactive):
        """测试正常多行输入"""
        mock_internal_input.return_value = "normal input"

        result = get_multiline_input("请输入:")

        assert result == "normal input"
        mock_internal_input.assert_called_once()

    @patch(
        "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
        return_value=False,
    )
    @patch("jarvis.jarvis_utils.input._get_multiline_input_internal")
    @patch("jarvis.jarvis_utils.input._show_history_and_copy")
    def test_ctrl_o_sentinel_handling(
        self, mock_show_history, mock_internal_input, mock_is_non_interactive
    ):
        """测试 Ctrl+O (CTRL_O_SENTINEL) 处理"""
        # 第一次返回 CTRL_O_SENTINEL，第二次返回正常输入
        from jarvis.jarvis_utils.input import CTRL_O_SENTINEL

        mock_internal_input.side_effect = [CTRL_O_SENTINEL, "normal input"]

        result = get_multiline_input("请输入:")

        assert result == "normal input"
        mock_show_history.assert_called_once()
        assert mock_internal_input.call_count == 2

    @patch(
        "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
        return_value=False,
    )
    @patch("jarvis.jarvis_utils.input._get_multiline_input_internal")
    def test_ctrl_x_sentinel_handling(
        self, mock_internal_input, mock_is_non_interactive
    ):
        """测试 Ctrl+X (CTRL_X_SENTINEL) 处理"""
        from jarvis.jarvis_utils.input import CTRL_X_SENTINEL

        mock_internal_input.return_value = CTRL_X_SENTINEL

        with pytest.raises(SystemExit) as exc_info:
            get_multiline_input("请输入:")

        assert exc_info.value.code == 0

    @patch(
        "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
        return_value=False,
    )
    @patch("jarvis.jarvis_utils.input._get_multiline_input_internal")
    @patch("jarvis.jarvis_utils.input._shutil.which")
    @patch("jarvis.jarvis_utils.input._subprocess.run")
    def test_fzf_request_git_files(
        self,
        mock_subprocess_run,
        mock_which,
        mock_internal_input,
        mock_is_non_interactive,
    ):
        """测试 FZF_REQUEST_SENTINEL_PREFIX 处理（@模式，git文件）"""
        from jarvis.jarvis_utils.input import FZF_REQUEST_SENTINEL_PREFIX
        import base64

        # 第一次返回 FZF 请求，第二次返回正常输入
        text = "test text"
        cursor = 9
        payload = f"{cursor}:{base64.b64encode(text.encode('utf-8')).decode('ascii')}"
        mock_internal_input.side_effect = [
            FZF_REQUEST_SENTINEL_PREFIX + payload,
            "normal input",
        ]

        # Mock fzf available and git ls-files
        mock_which.return_value = "/usr/bin/fzf"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"file1.py\n"
        mock_subprocess_run.return_value = mock_result

        result = get_multiline_input("请输入:")

        assert result == "normal input"
        # FZF 应该被调用两次（git ls-files 和 fzf）
        assert mock_subprocess_run.call_count >= 2

    @patch(
        "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
        return_value=False,
    )
    @patch("jarvis.jarvis_utils.input._get_multiline_input_internal")
    @patch("jarvis.jarvis_utils.input._shutil.which")
    @patch("jarvis.jarvis_utils.input._os.walk")
    @patch("jarvis.jarvis_utils.input._subprocess.run")
    def test_fzf_request_all_files(
        self,
        mock_subprocess_run,
        mock_walk,
        mock_which,
        mock_internal_input,
        mock_is_non_interactive,
    ):
        """测试 FZF_REQUEST_ALL_SENTINEL_PREFIX 处理（#模式，所有文件）"""
        from jarvis.jarvis_utils.input import FZF_REQUEST_ALL_SENTINEL_PREFIX
        import base64

        # 第一次返回 FZF 请求，第二次返回正常输入
        text = "test text"
        cursor = 9
        payload = f"{cursor}:{base64.b64encode(text.encode('utf-8')).decode('ascii')}"
        mock_internal_input.side_effect = [
            FZF_REQUEST_ALL_SENTINEL_PREFIX + payload,
            "normal input",
        ]

        # Mock fzf available and os.walk
        mock_which.return_value = "/usr/bin/fzf"
        mock_walk.return_value = [(".", [], ["file1.py", "file2.py"])]

        # Mock fzf subprocess
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_subprocess_run.return_value = mock_result

        result = get_multiline_input("请输入:")

        assert result == "normal input"
        mock_walk.assert_called()

    @patch(
        "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
        return_value=False,
    )
    @patch("jarvis.jarvis_utils.input._get_multiline_input_internal")
    def test_empty_input(self, mock_internal_input, mock_is_non_interactive):
        """测试空输入"""
        mock_internal_input.return_value = ""

        result = get_multiline_input("请输入:")

        assert result == ""

    @patch(
        "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
        return_value=False,
    )
    @patch("jarvis.jarvis_utils.input._get_multiline_input_internal")
    def test_empty_input_no_print(self, mock_internal_input, mock_is_non_interactive):
        """测试空输入（不打印）"""
        mock_internal_input.return_value = ""

        result = get_multiline_input("请输入:", print_on_empty=False)

        assert result == ""

    @patch(
        "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
        return_value=False,
    )
    @patch("jarvis.jarvis_utils.input._get_multiline_input_internal")
    @patch("jarvis.jarvis_utils.input._shutil.which")
    @patch("jarvis.jarvis_utils.input._subprocess.run")
    @patch("jarvis.jarvis_utils.input._get_files_for_fzf")
    def test_fzf_no_fzf_installed(
        self,
        mock_get_files,
        mock_subprocess_run,
        mock_which,
        mock_internal_input,
        mock_is_non_interactive,
    ):
        """测试 FZF 请求但 fzf 未安装"""
        from jarvis.jarvis_utils.input import FZF_REQUEST_SENTINEL_PREFIX
        import base64

        text = "test text"
        cursor = 9
        payload = f"{cursor}:{base64.b64encode(text.encode('utf-8')).decode('ascii')}"
        mock_internal_input.side_effect = [
            FZF_REQUEST_SENTINEL_PREFIX + payload,
            "normal input",
        ]

        # Mock fzf not available
        mock_which.return_value = None
        # Mock file list to avoid subprocess.run calls in _get_files_for_fzf
        mock_get_files.return_value = []

        result = get_multiline_input("请输入:")

        assert result == "normal input"
        # 不应该调用 subprocess.run（因为 fzf 不可用）
        assert mock_subprocess_run.call_count == 0

    @patch(
        "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
        return_value=False,
    )
    @patch("jarvis.jarvis_utils.input._get_multiline_input_internal")
    @patch("jarvis.jarvis_utils.input._shutil.which")
    @patch("jarvis.jarvis_utils.input._subprocess.run")
    def test_fzf_malformed_payload(
        self,
        mock_subprocess_run,
        mock_which,
        mock_internal_input,
        mock_is_non_interactive,
    ):
        """测试 FZF 请求但 payload 格式错误"""
        from jarvis.jarvis_utils.input import FZF_REQUEST_SENTINEL_PREFIX

        mock_internal_input.side_effect = [
            FZF_REQUEST_SENTINEL_PREFIX + "malformed",
            "normal input",
        ]

        result = get_multiline_input("请输入:")

        assert result == "normal input"
        # 不应该调用 subprocess.run（因为 payload 错误）
        assert mock_subprocess_run.call_count == 0

    @patch(
        "jarvis.jarvis_utils.input._is_non_interactive_for_current_agent",
        return_value=False,
    )
    @patch("jarvis.jarvis_utils.input._get_multiline_input_internal")
    @patch("jarvis.jarvis_utils.input._shutil.which")
    @patch("jarvis.jarvis_utils.input._subprocess.run")
    def test_fzf_no_git_files_fallback(
        self,
        mock_subprocess_run,
        mock_which,
        mock_internal_input,
        mock_is_non_interactive,
    ):
        """测试 git ls-files 返回空，fallback 到 os.walk"""
        from jarvis.jarvis_utils.input import FZF_REQUEST_SENTINEL_PREFIX
        import base64

        text = "test text"
        cursor = 9
        payload = f"{cursor}:{base64.b64encode(text.encode('utf-8')).decode('ascii')}"
        mock_internal_input.side_effect = [
            FZF_REQUEST_SENTINEL_PREFIX + payload,
            "normal input",
        ]

        mock_which.return_value = "/usr/bin/fzf"

        # git ls-files 返回空
        mock_git_result = MagicMock()
        mock_git_result.returncode = 1

        # fzf subprocess
        mock_fzf_result = MagicMock()
        mock_fzf_result.returncode = 0
        mock_fzf_result.stdout = ""

        mock_subprocess_run.side_effect = [mock_git_result, mock_fzf_result]

        result = get_multiline_input("请输入:")

        assert result == "normal input"


if __name__ == "__main__":
    pytest.main([__file__])
