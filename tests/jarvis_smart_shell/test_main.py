# -*- coding: utf-8 -*-
"""jarvis_smart_shell.main 模块单元测试"""

from unittest.mock import patch

from jarvis.jarvis_smart_shell.main import (
    _get_markers,
    _get_zsh_markers,
    _check_bash_shell,
)


class TestGetMarkers:
    """测试 _get_markers 函数"""

    def test_returns_tuple(self):
        """测试返回元组"""
        result = _get_markers()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_markers_are_strings(self):
        """测试标记是字符串"""
        start_marker, end_marker = _get_markers()
        assert isinstance(start_marker, str)
        assert isinstance(end_marker, str)

    def test_markers_contain_fish(self):
        """测试标记包含 fish"""
        start_marker, end_marker = _get_markers()
        assert "FISH" in start_marker.upper()
        assert "FISH" in end_marker.upper()

    def test_markers_are_different(self):
        """测试开始和结束标记不同"""
        start_marker, end_marker = _get_markers()
        assert start_marker != end_marker


class TestGetZshMarkers:
    """测试 _get_zsh_markers 函数"""

    def test_returns_tuple(self):
        """测试返回元组"""
        result = _get_zsh_markers()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_markers_are_strings(self):
        """测试标记是字符串"""
        start_marker, end_marker = _get_zsh_markers()
        assert isinstance(start_marker, str)
        assert isinstance(end_marker, str)

    def test_markers_contain_zsh(self):
        """测试标记包含 zsh"""
        start_marker, end_marker = _get_zsh_markers()
        assert "ZSH" in start_marker.upper()
        assert "ZSH" in end_marker.upper()

    def test_markers_are_different(self):
        """测试开始和结束标记不同"""
        start_marker, end_marker = _get_zsh_markers()
        assert start_marker != end_marker


class TestCheckBashShell:
    """测试 _check_bash_shell 函数"""

    @patch("jarvis.jarvis_smart_shell.main.get_shell_name")
    def test_bash_shell(self, mock_get_shell_name):
        """测试 bash shell"""
        mock_get_shell_name.return_value = "bash"
        result = _check_bash_shell()
        assert result is True

    @patch("jarvis.jarvis_smart_shell.main.get_shell_name")
    def test_non_bash_shell(self, mock_get_shell_name):
        """测试非 bash shell"""
        mock_get_shell_name.return_value = "fish"
        result = _check_bash_shell()
        assert result is False

    @patch("jarvis.jarvis_smart_shell.main.get_shell_name")
    def test_zsh_shell(self, mock_get_shell_name):
        """测试 zsh shell"""
        mock_get_shell_name.return_value = "zsh"
        result = _check_bash_shell()
        assert result is False

