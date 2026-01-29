# -*- coding: utf-8 -*-
"""性能测试配置"""

import pytest


def pytest_configure(config):
    """配置pytest markers"""
    config.addinivalue_line("markers", "performance: marks tests as performance tests")


@pytest.fixture(scope="session")
def performance_thresholds():
    """性能阈值配置"""
    return {
        "response_time_max": 1.0,  # 响应时间最大1秒
        "memory_mb_max": 100,  # 内存最大100MB
        "cpu_percent_max": 80,  # CPU最大80%
    }
