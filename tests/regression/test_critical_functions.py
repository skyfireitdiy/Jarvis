# -*- coding: utf-8 -*-
"""测试关键功能是否正常工作"""

import pytest


class TestCriticalFunctions:
    """测试关键功能"""

    @pytest.mark.regression
    def test_jarvis_agent_import(self):
        """测试Agent可以导入"""
        from jarvis.jarvis_agent import Agent

        assert Agent is not None

    @pytest.mark.regression
    def test_jarvis_module_import(self):
        """测试jarvis模块可以导入"""
        from jarvis.jarvis_agent import LoopAction

        assert LoopAction is not None

    @pytest.mark.regression
    def test_git_utils_module_exists(self):
        """测试jarvis_git_utils模块存在"""
        import jarvis.jarvis_git_utils

        assert jarvis.jarvis_git_utils is not None
