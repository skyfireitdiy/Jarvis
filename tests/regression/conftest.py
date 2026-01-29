# -*- coding: utf-8 -*-
"""回归测试配置"""

import pytest


def pytest_configure(config):
    """配置pytest markers"""
    config.addinivalue_line("markers", "regression: marks tests as regression tests")


@pytest.fixture(scope="session")
def regression_test_data():
    """回归测试数据"""
    return {
        "critical_functions": [
            "jarvis_agent",
            "code_agent",
            "git_utils",
        ],
        "api_endpoints": [
            "/api/agent/chat",
            "/api/code/analyze",
        ],
    }
