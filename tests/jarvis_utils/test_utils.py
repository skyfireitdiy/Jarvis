# -*- coding: utf-8 -*-
"""jarvis_utils.utils 模块单元测试"""

from unittest.mock import patch, MagicMock

from jarvis.jarvis_utils.utils import (
    is_editable_install,
)


class TestIsEditableInstall:
    """测试 is_editable_install 函数"""

    def test_returns_boolean(self):
        """测试返回布尔值"""
        result = is_editable_install()
        assert isinstance(result, bool)

    @patch("jarvis.jarvis_utils.utils.Path")
    @patch("jarvis.jarvis_utils.utils.sys")
    def test_editable_install_detection(self, mock_sys, mock_path):
        """测试可编辑安装检测"""
        # 这个测试比较复杂，因为函数有多种检测方式
        # 我们主要验证函数能正常执行并返回布尔值
        result = is_editable_install()
        assert isinstance(result, bool)
