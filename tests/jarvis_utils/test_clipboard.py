# -*- coding: utf-8 -*-
"""jarvis_utils.clipboard 模块单元测试"""

import subprocess
from unittest.mock import patch, MagicMock

from jarvis.jarvis_utils.clipboard import copy_to_clipboard


class TestCopyToClipboard:
    """测试 copy_to_clipboard 函数"""

    @patch("jarvis.jarvis_utils.clipboard.platform.system")
    @patch("jarvis.jarvis_utils.clipboard.subprocess.Popen")
    @patch("jarvis.jarvis_utils.clipboard.print")
    def test_windows_clipboard(self, mock_print, mock_popen, mock_platform):
        """测试 Windows 剪贴板"""
        mock_platform.return_value = "Windows"
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        copy_to_clipboard("test text")
        
        mock_popen.assert_called_once()
        mock_process.stdin.write.assert_called_once_with(b"test text")
        mock_process.stdin.close.assert_called_once()

    @patch("jarvis.jarvis_utils.clipboard.platform.system")
    @patch("jarvis.jarvis_utils.clipboard.subprocess.Popen")
    @patch("jarvis.jarvis_utils.clipboard.print")
    def test_macos_clipboard(self, mock_print, mock_popen, mock_platform):
        """测试 macOS 剪贴板"""
        mock_platform.return_value = "Darwin"
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        copy_to_clipboard("test text")
        
        mock_popen.assert_called_once_with(
            ["pbcopy"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        mock_process.stdin.write.assert_called_once_with(b"test text")

    @patch("jarvis.jarvis_utils.clipboard.platform.system")
    @patch("jarvis.jarvis_utils.clipboard.subprocess.Popen")
    @patch("jarvis.jarvis_utils.clipboard.print")
    def test_linux_xsel_clipboard(self, mock_print, mock_popen, mock_platform):
        """测试 Linux xsel 剪贴板"""
        mock_platform.return_value = "Linux"
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        copy_to_clipboard("test text")
        
        # 应该先尝试 xsel
        calls = mock_popen.call_args_list
        assert len(calls) >= 1
        assert calls[0][0][0] == ["xsel", "-b", "-i"]

    @patch("jarvis.jarvis_utils.clipboard.platform.system")
    @patch("jarvis.jarvis_utils.clipboard.subprocess.Popen")
    @patch("jarvis.jarvis_utils.clipboard.print")
    def test_linux_xsel_not_found_fallback_xclip(self, mock_print, mock_popen, mock_platform):
        """测试 Linux xsel 未找到时回退到 xclip"""
        mock_platform.return_value = "Linux"
        # 第一次调用（xsel）抛出 FileNotFoundError，第二次（xclip）成功
        mock_popen.side_effect = [
            FileNotFoundError(),
            MagicMock(stdin=MagicMock()),
        ]
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.side_effect = [FileNotFoundError(), mock_process]

        copy_to_clipboard("test text")
        
        # 应该尝试了 xsel 和 xclip
        assert mock_popen.call_count >= 2

    @patch("jarvis.jarvis_utils.clipboard.platform.system")
    @patch("jarvis.jarvis_utils.clipboard.subprocess.Popen")
    @patch("jarvis.jarvis_utils.clipboard.print")
    def test_windows_clipboard_error(self, mock_print, mock_popen, mock_platform):
        """测试 Windows 剪贴板错误处理"""
        mock_platform.return_value = "Windows"
        mock_popen.side_effect = Exception("Clip error")

        copy_to_clipboard("test text")
        
        # 应该打印警告
        mock_print.assert_called()

    @patch("jarvis.jarvis_utils.clipboard.platform.system")
    @patch("jarvis.jarvis_utils.clipboard.subprocess.Popen")
    @patch("jarvis.jarvis_utils.clipboard.print")
    def test_linux_no_clipboard_tools(self, mock_print, mock_popen, mock_platform):
        """测试 Linux 没有剪贴板工具"""
        mock_platform.return_value = "Linux"
        mock_popen.side_effect = FileNotFoundError()

        copy_to_clipboard("test text")
        
        # 应该打印警告
        mock_print.assert_called()

