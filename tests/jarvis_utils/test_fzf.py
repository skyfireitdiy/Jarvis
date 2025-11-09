# -*- coding: utf-8 -*-
"""jarvis_utils.fzf 模块单元测试"""

import pytest
from unittest.mock import patch, MagicMock

from jarvis.jarvis_utils.fzf import fzf_select


class TestFzfSelect:
    """测试 fzf_select 函数"""

    def test_fzf_not_available(self):
        """测试 fzf 不可用"""
        with patch("jarvis.jarvis_utils.fzf.shutil.which", return_value=None):
            result = fzf_select(["option1", "option2"])
            assert result is None

    def test_empty_options(self):
        """测试空选项列表"""
        with patch("jarvis.jarvis_utils.fzf.shutil.which", return_value="/usr/bin/fzf"):
            result = fzf_select([])
            assert result is None

    def test_string_options_success(self):
        """测试字符串选项成功选择"""
        with patch("jarvis.jarvis_utils.fzf.shutil.which", return_value="/usr/bin/fzf"):
            with patch("jarvis.jarvis_utils.fzf.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="option2\n",
                    stderr=""
                )
                result = fzf_select(["option1", "option2", "option3"])
                assert result == "option2"
                assert mock_run.called

    def test_string_options_cancelled(self):
        """测试取消选择"""
        with patch("jarvis.jarvis_utils.fzf.shutil.which", return_value="/usr/bin/fzf"):
            with patch("jarvis.jarvis_utils.fzf.subprocess.run") as mock_run:
                # CalledProcessError 表示用户取消
                import subprocess
                mock_run.side_effect = subprocess.CalledProcessError(1, "fzf")
                result = fzf_select(["option1", "option2"])
                assert result is None

    def test_dict_options_with_key(self):
        """测试字典选项（带 key）"""
        with patch("jarvis.jarvis_utils.fzf.shutil.which", return_value="/usr/bin/fzf"):
            with patch("jarvis.jarvis_utils.fzf.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="value2\n",
                    stderr=""
                )
                options = [
                    {"name": "option1", "value": "value1"},
                    {"name": "option2", "value": "value2"},
                ]
                result = fzf_select(options, key="name")
                assert result == "value2"

    def test_dict_options_without_key(self):
        """测试字典选项（不带 key）应该抛出错误"""
        with patch("jarvis.jarvis_utils.fzf.shutil.which", return_value="/usr/bin/fzf"):
            options = [{"name": "option1"}, {"name": "option2"}]
            with pytest.raises(ValueError, match="key must be provided"):
                fzf_select(options)

    def test_custom_prompt(self):
        """测试自定义提示"""
        with patch("jarvis.jarvis_utils.fzf.shutil.which", return_value="/usr/bin/fzf"):
            with patch("jarvis.jarvis_utils.fzf.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="option1\n",
                    stderr=""
                )
                fzf_select(["option1"], prompt="Choose> ")
                # 验证 prompt 参数被传递
                call_args = mock_run.call_args[0][0]
                assert "--prompt" in call_args
                prompt_index = call_args.index("--prompt")
                assert call_args[prompt_index + 1] == "Choose> "

    def test_file_not_found_error(self):
        """测试 FileNotFoundError 处理"""
        with patch("jarvis.jarvis_utils.fzf.shutil.which", return_value="/usr/bin/fzf"):
            with patch("jarvis.jarvis_utils.fzf.subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError("fzf not found")
                result = fzf_select(["option1", "option2"])
                assert result is None

