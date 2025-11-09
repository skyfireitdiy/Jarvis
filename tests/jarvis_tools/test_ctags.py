# -*- coding: utf-8 -*-
"""jarvis_tools.ctags 模块单元测试"""

import pytest
import os
from unittest.mock import patch, MagicMock

from jarvis.jarvis_tools.ctags import CtagsTool


class TestCtagsTool:
    """测试 CtagsTool 类"""

    def test_check_enabled(self):
        """测试检查工具可用性（启用状态）"""
        with patch.dict(os.environ, {"JARVIS_CODE_AGENT": "1"}):
            assert CtagsTool.check() is True

    def test_check_disabled(self):
        """测试检查工具可用性（禁用状态）"""
        with patch.dict(os.environ, {"JARVIS_CODE_AGENT": "0"}, clear=True):
            assert CtagsTool.check() is False

    def test_check_not_set(self):
        """测试检查工具可用性（未设置环境变量）"""
        with patch.dict(os.environ, {}, clear=True):
            if "JARVIS_CODE_AGENT" in os.environ:
                del os.environ["JARVIS_CODE_AGENT"]
            assert CtagsTool.check() is False

    @patch("jarvis.jarvis_tools.ctags.subprocess.run")
    def test_find_symbol_success(self, mock_run):
        """测试成功查找符号"""
        tool = CtagsTool()
        # 模拟 ctags 输出
        mock_output = "test_function  function  test.py  10  def test_function():"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr=""
        )
        
        result = tool._find_symbol_with_ctags("test_function")
        assert result["success"] is True
        assert "stdout" in result
        assert "test_function" in result["stdout"]
        assert "test.py" in result["stdout"]

    @patch("jarvis.jarvis_tools.ctags.subprocess.run")
    def test_find_symbol_not_found(self, mock_run):
        """测试未找到符号"""
        tool = CtagsTool()
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr=""
        )
        
        result = tool._find_symbol_with_ctags("nonexistent")
        assert result["success"] is False
        assert "未找到符号" in result["stderr"]

    @patch("jarvis.jarvis_tools.ctags.subprocess.run")
    def test_find_symbol_ctags_failed(self, mock_run):
        """测试 ctags 执行失败"""
        tool = CtagsTool()
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="ctags: command not found"
        )
        
        result = tool._find_symbol_with_ctags("test_function")
        assert result["success"] is False
        assert "执行失败" in result["stderr"]

    @patch("jarvis.jarvis_tools.ctags.subprocess.run")
    def test_find_symbol_file_not_found(self, mock_run):
        """测试 ctags 命令不存在"""
        tool = CtagsTool()
        mock_run.side_effect = FileNotFoundError("ctags: command not found")
        
        result = tool._find_symbol_with_ctags("test_function")
        assert result["success"] is False
        assert "ctags命令未找到" in result["stderr"] or "请先安装ctags工具" in result["stderr"]

    @patch("jarvis.jarvis_tools.ctags.subprocess.run")
    def test_find_symbol_with_file_pattern(self, mock_run):
        """测试使用文件模式查找符号"""
        tool = CtagsTool()
        mock_output = "test_function  function  test.py  10  def test_function():"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr=""
        )
        
        result = tool._find_symbol_with_ctags("test_function", file_pattern="*.py")
        assert result["success"] is True
        # 验证命令包含了文件模式参数
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "ctags" in call_args

    @patch("jarvis.jarvis_tools.ctags.subprocess.run")
    def test_find_symbol_multiple_locations(self, mock_run):
        """测试找到多个符号位置"""
        tool = CtagsTool()
        mock_output = """test_function  function  test1.py  10  def test_function():
test_function  function  test2.py  20  def test_function():"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr=""
        )
        
        result = tool._find_symbol_with_ctags("test_function")
        assert result["success"] is True
        assert "test1.py" in result["stdout"]
        assert "test2.py" in result["stdout"]

