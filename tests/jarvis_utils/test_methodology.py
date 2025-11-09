# -*- coding: utf-8 -*-
"""jarvis_utils.methodology 模块单元测试"""

import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock

from jarvis.jarvis_utils.methodology import _get_methodology_directory


class TestGetMethodologyDirectory:
    """测试 _get_methodology_directory 函数"""

    @patch("jarvis.jarvis_utils.methodology.get_data_dir")
    @patch("jarvis.jarvis_utils.methodology.os.path.exists")
    @patch("jarvis.jarvis_utils.methodology.os.makedirs")
    def test_existing_directory(self, mock_makedirs, mock_exists, mock_get_data_dir):
        """测试已存在的目录"""
        mock_get_data_dir.return_value = "/test/data"
        mock_exists.return_value = True
        
        result = _get_methodology_directory()
        assert result == "/test/data/methodologies"
        mock_makedirs.assert_not_called()

    @patch("jarvis.jarvis_utils.methodology.get_data_dir")
    @patch("jarvis.jarvis_utils.methodology.os.path.exists")
    @patch("jarvis.jarvis_utils.methodology.os.makedirs")
    def test_create_directory(self, mock_makedirs, mock_exists, mock_get_data_dir):
        """测试创建目录"""
        mock_get_data_dir.return_value = "/test/data"
        mock_exists.return_value = False
        
        result = _get_methodology_directory()
        assert result == "/test/data/methodologies"
        mock_makedirs.assert_called_once_with("/test/data/methodologies", exist_ok=True)

    @patch("jarvis.jarvis_utils.methodology.get_data_dir")
    @patch("jarvis.jarvis_utils.methodology.os.path.exists")
    @patch("jarvis.jarvis_utils.methodology.os.makedirs")
    def test_create_directory_error(self, mock_makedirs, mock_exists, mock_get_data_dir):
        """测试创建目录失败"""
        mock_get_data_dir.return_value = "/test/data"
        mock_exists.return_value = False
        mock_makedirs.side_effect = OSError("Permission denied")
        
        # 应该仍然返回路径，即使创建失败
        result = _get_methodology_directory()
        assert result == "/test/data/methodologies"

