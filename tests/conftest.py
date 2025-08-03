# -*- coding: utf-8 -*-
"""pytest 配置文件"""
import sys
import os
import pytest

# 将项目根目录添加到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture(scope="session")
def test_data_dir():
    """测试数据目录"""
    return os.path.join(os.path.dirname(__file__), "test_data")


@pytest.fixture(scope="function")
def temp_dir(tmp_path):
    """临时目录 fixture，每个测试函数都会获得一个新的临时目录"""
    return tmp_path


@pytest.fixture(autouse=True)
def reset_globals():
    """自动重置全局状态，防止测试之间的干扰"""

    yield
    
    # 测试后清理全局状态
    # 如果有需要重置的全局变量或单例，在这里处理
