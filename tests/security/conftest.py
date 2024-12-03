# -*- coding: utf-8 -*-
"""安全测试配置"""

import pytest


def pytest_configure(config):
    """配置pytest markers"""
    config.addinivalue_line("markers", "security: marks tests as security tests")


@pytest.fixture(scope="session")
def security_thresholds():
    """安全阈值配置"""
    return {
        "max_severity": "medium",  # 最大严重级别
        "max_issues": 0,  # 最大安全问题数量
    }
