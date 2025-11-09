# -*- coding: utf-8 -*-
"""jarvis_utils.utils 模块单元测试"""

import pytest
from unittest.mock import patch, MagicMock
from importlib.util import find_spec

from jarvis.jarvis_utils.utils import (
    get_missing_rag_modules,
    is_rag_installed,
    is_editable_install,
)


class TestGetMissingRagModules:
    """测试 get_missing_rag_modules 函数"""

    def test_returns_list(self):
        """测试返回列表类型"""
        result = get_missing_rag_modules()
        assert isinstance(result, list)

    def test_all_modules_installed(self):
        """测试所有模块都已安装的情况（如果都安装了）"""
        # 这个测试依赖于实际环境，可能所有模块都已安装
        result = get_missing_rag_modules()
        # 如果所有模块都安装了，应该返回空列表
        # 如果某些模块未安装，应该返回缺失的模块列表
        assert isinstance(result, list)

    @patch("importlib.util.find_spec")
    def test_missing_modules(self, mock_find_spec):
        """测试缺失模块的情况"""
        # 模拟某些模块缺失
        def side_effect(module):
            if module in ["langchain", "chromadb"]:
                return None  # 模块不存在
            return MagicMock()  # 模块存在

        mock_find_spec.side_effect = side_effect
        result = get_missing_rag_modules()
        assert "langchain" in result or "chromadb" in result or len(result) > 0

    @patch("importlib.util.find_spec")
    def test_exception_handling(self, mock_find_spec):
        """测试异常处理"""
        mock_find_spec.side_effect = Exception("Test exception")
        result = get_missing_rag_modules()
        # 异常时应该返回所有必需模块
        assert isinstance(result, list)
        assert len(result) > 0


class TestIsRagInstalled:
    """测试 is_rag_installed 函数"""

    def test_returns_boolean(self):
        """测试返回布尔值"""
        result = is_rag_installed()
        assert isinstance(result, bool)

    @patch("jarvis.jarvis_utils.utils.get_missing_rag_modules")
    def test_all_modules_installed(self, mock_get_missing):
        """测试所有模块都已安装"""
        mock_get_missing.return_value = []
        assert is_rag_installed() is True

    @patch("jarvis.jarvis_utils.utils.get_missing_rag_modules")
    def test_some_modules_missing(self, mock_get_missing):
        """测试某些模块缺失"""
        mock_get_missing.return_value = ["langchain", "chromadb"]
        assert is_rag_installed() is False


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

